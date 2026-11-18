"""CHECK 2 — Dòng nhãn YOLO: sai định dạng, ID lớp lạ, box tràn ảnh, box rỗng, box lặp.   (Script 2 trong slide)   ★★

Test:  pytest tests/test_label_format.py -q

Mỗi dòng nhãn: `id cx cy w h` (5 số, toạ độ 0–1). Trả về list[Issue]; `Issue.line` = số dòng (đếm từ 1).

| code             | severity | khi nào                                                                  |
|------------------|----------|--------------------------------------------------------------------------|
| BAD_FORMAT       | ERROR    | không đúng 5 cột số (dùng `parse_yolo_line`, bắt `ValueError`)           |
| BAD_CLASS_ID     | ERROR    | id lớp ngoài 0..len(ds.classes)-1                                        |
| BOX_ZERO         | ERROR    | w <= 0 hoặc h <= 0                                                       |
| BOX_OUT_OF_IMAGE | ERROR    | mép box vượt [0,1] quá `cfg["label_format"]["overflow_tol"]`; extra={"overflow": mức tràn} |
| DUP_BOX          | ERROR    | cùng lớp với một dòng TRƯỚC ĐÓ và IoU > `dup_box_iou`; báo ở dòng SAU    |
| BOX_TINY         | WARN     | cạnh ngắn của box (px) < `min_box_px`  (cần `ds.image_size(stem)`)       |
| BOX_HUGE         | WARN     | w*h > `max_box_frac`                                                     |

Gợi ý
- Mép trái = x - w/2, mép phải = x + w/2 (xem câu hỏi "dòng YOLO nào lỗi?" trong slide).
- Một dòng hỏng (BAD_FORMAT, BAD_CLASS_ID, BOX_ZERO) thì `continue`, đừng kiểm tiếp hình học của dòng đó.
- Dòng thiếu cột làm script của slide dừng giữa chừng: đây là lý do phải `try/except`.
- `iou_xywh(a, b)` có sẵn trong common.py.
- Ngưỡng nằm trong `cfg["label_format"]` — đừng viết cứng số vào code.
"""
from ..common import ERROR, WARN, Issue, iou_xywh, parse_yolo_line  # noqa: F401


def _overflow(cx, cy, w, h) -> float:
    """Mức tràn lớn nhất của 4 mép box ra ngoài [0, 1] (0 nếu nằm gọn trong ảnh)."""
    x1, x2, y1, y2 = cx - w / 2, cx + w / 2, cy - h / 2, cy + h / 2
    return max(0.0, -x1, x2 - 1.0, -y1, y2 - 1.0)


def run(ds, cfg):
    lf = cfg["label_format"]
    tol, min_px, max_frac, dup_iou = lf["overflow_tol"], lf["min_box_px"], lf["max_box_frac"], lf["dup_box_iou"]
    n_cls = len(ds.classes)
    issues = []
    for lp in ds.label_files():
        stem = lp.stem
        size = ds.image_size(stem) if ds.image_path(stem) else None     # (W, H) hoặc None (ảnh hỏng / không có ảnh)
        kept = []                                                         # (số dòng, box) các dòng hợp lệ phía trước, để so DUP_BOX
        for ln, text in ds.read_label_lines(stem) or []:                  # số dòng GỐC (dòng trống vẫn được đếm)
            try:
                c, cx, cy, w, h = parse_yolo_line(text)
            except ValueError as e:
                issues.append(Issue("label_format", ERROR, "BAD_FORMAT", stem, f"dòng không đúng 5 cột số: {e} ({text.strip()!r})", ln))
                continue
            if not 0 <= c < n_cls:
                issues.append(Issue("label_format", ERROR, "BAD_CLASS_ID", stem, f"id lớp {c} ngoài 0..{n_cls - 1}", ln, {"class_id": c}))
                continue
            if w <= 0 or h <= 0:
                issues.append(Issue("label_format", ERROR, "BOX_ZERO", stem, f"box rộng/cao không dương (w={w}, h={h})", ln))
                continue
            over = _overflow(cx, cy, w, h)
            if over > tol:
                issues.append(Issue("label_format", ERROR, "BOX_OUT_OF_IMAGE", stem, f"box tràn ảnh {over:.4f} > {tol}", ln, {"overflow": round(over, 6)}))
            box = (cx, cy, w, h)
            prev = next(((pl, iou_xywh(pb[1:], box)) for pl, pb in kept if pb[0] == c and iou_xywh(pb[1:], box) > dup_iou), None)
            if prev:
                issues.append(Issue("label_format", ERROR, "DUP_BOX", stem, f"trùng box dòng {prev[0]} (cùng lớp, IoU {prev[1]:.3f})", ln,
                                    {"of_line": prev[0], "iou": round(prev[1], 4)}))
            if size:
                short = min(w * size[0], h * size[1])
                if short < min_px:
                    issues.append(Issue("label_format", WARN, "BOX_TINY", stem, f"cạnh ngắn {short:.1f}px < {min_px}px", ln, {"short_px": round(short, 2)}))
            if w * h > max_frac:
                issues.append(Issue("label_format", WARN, "BOX_HUGE", stem, f"box chiếm {w * h:.3f} > {max_frac} diện tích ảnh", ln, {"frac": round(w * h, 4)}))
            kept.append((ln, (c, *box)))
    return issues
