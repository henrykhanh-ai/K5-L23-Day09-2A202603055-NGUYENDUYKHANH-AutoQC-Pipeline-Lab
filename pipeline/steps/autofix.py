"""BƯỚC 2/4 — Sửa tự động những lỗi bắt buộc mà máy sửa được AN TOÀN.   ★★

Test:  pytest tests/test_autofix.py -q

`fix(ds, issues, cfg) -> list[dict]`: duyệt `issues` (chỉ lỗi severity ERROR), sửa thẳng vào thư mục `ds`,
và trả về danh sách thay đổi; mỗi phần tử có khoá: image, line, action, before, after
(đây chính là file `03_fixes.csv` — bằng chứng pipeline đã làm gì, người có thể kiểm lại).

| code lỗi                                       | cách sửa                                    | action           |
|------------------------------------------------|---------------------------------------------|------------------|
| BAD_FORMAT, BAD_CLASS_ID, BOX_ZERO, DUP_BOX    | xoá dòng đó khỏi file nhãn                  | "drop_line"      |
| BOX_OUT_OF_IMAGE                               | cắt box về trong [0,1] (giữ nguyên lớp)     | "clip_box"       |
| MISSING_LABEL_FILE                             | KHÔNG sửa file (máy không thể bịa nhãn): ghi 1 dòng fix, before="(không có file)", after="chuyển người gán" | "needs_label" |
| BAD_CLASS_NAME                                 | ghi lại `names` trong data.yaml đúng `cfg["classes"]` | "rename_classes" |
| DUP_IMAGE_*, LEAK_TEST, CORRUPT_IMAGE, BAD_SIZE| xoá ảnh + nhãn khỏi `ds`                    | "remove_image"   |

Bẫy cần nghĩ tới (có test cho từng cái)
- Một file có NHIỀU dòng lỗi: số dòng trong `issues` là số dòng GỐC. Nếu xoá từng dòng một thì số dòng lệch.
  Gom theo file, rồi ghi lại MỘT lần.
- Sau khi cắt, box có thể không còn diện tích (nằm hẳn ngoài ảnh): lúc đó xoá dòng thay vì ghi box rỗng.
- Một dòng có 2 lỗi (vd. BOX_OUT_OF_IMAGE + DUP_BOX): xoá dòng thắng, chỉ ghi 1 fix `drop_line`, không ghi thêm `clip_box`. Dòng trống ở giữa file vẫn đếm vào số dòng gốc.
- Ảnh vừa bị xoá (DUP_IMAGE_*...) mà còn issue dòng của chính nó: bỏ qua êm, không được báo lỗi/chết.
- Không động tới lỗi WARN (cảnh báo là việc của người). Không sửa file ở `data/raw/` — chỉ sửa `ds`.
- Chạy lần 2 trên dữ liệu đã sửa phải không làm gì thêm (idempotent) — NGOẠI LỆ duy nhất: `needs_label` được ghi lại mỗi lần còn lỗi `MISSING_LABEL_FILE` (vì ảnh vẫn chưa có nhãn).

- `needs_label` KHÔNG tạo file nhãn rỗng (rỗng = "ảnh nền", khác với "chưa gán"). `review_queue` sẽ đẩy ảnh này lên đầu hàng đợi cho người.

Gợi ý: `yaml.safe_load / safe_dump`.
"""
from collections import defaultdict  # noqa: F401

import yaml  # noqa: F401

from ..common import ERROR, parse_yolo_line  # noqa: F401


DROP_CODES = {"BAD_FORMAT", "BAD_CLASS_ID", "BOX_ZERO", "DUP_BOX"}
CLIP_CODES = {"BOX_OUT_OF_IMAGE"}
REMOVE_CODES = {"LEAK_TEST", "CORRUPT_IMAGE", "BAD_SIZE"}          # + mọi mã bắt đầu bằng DUP_IMAGE_


def _is_remove(code):
    return code in REMOVE_CODES or code.startswith("DUP_IMAGE_")


def _fix(image, line, action, before, after):
    return dict(image=image, line="" if line is None else line, action=action, before=before, after=after)


def _clip(text):
    """Cắt box về [0,1]. Trả dòng mới, hoặc None nếu box không còn diện tích (nằm hẳn ngoài ảnh)."""
    c, cx, cy, w, h = parse_yolo_line(text)
    x1, x2 = max(0.0, cx - w / 2), min(1.0, cx + w / 2)
    y1, y2 = max(0.0, cy - h / 2), min(1.0, cy + h / 2)
    if x2 - x1 <= 0 or y2 - y1 <= 0:
        return None
    return f"{c} {(x1 + x2) / 2:.6f} {(y1 + y2) / 2:.6f} {x2 - x1:.6f} {y2 - y1:.6f}"


def _remove_image(ds, stem):
    img = ds.image_path(stem)
    lab = ds.label_path(stem)
    if img is None and not lab.exists():
        return None                                     # đã xoá ở lần trước: idempotent
    before = ", ".join(x for x in [img.name if img else "", lab.name if lab.exists() else ""] if x)
    if img is not None:
        img.unlink()
    lab.unlink(missing_ok=True)
    ds._size_cache.pop(stem, None)
    return before


def _rename_classes(ds, cfg):
    if not ds.yaml_path.exists():
        data, old = {}, {}
    else:
        data = yaml.safe_load(ds.yaml_path.read_text(encoding="utf-8")) or {}
        old = data.get("names", {})
    want = list(cfg["classes"])
    new = {i: n for i, n in enumerate(want)} if isinstance(old, dict) else want
    if old == new:
        return None
    data["names"] = new
    ds.yaml_path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return str(old), str(new)


def fix(ds, issues, cfg):
    errors = [i for i in issues if i.severity == ERROR]          # WARN là việc của người: không động tới
    fixes = []

    # 1) Loại ảnh (trùng / rò rỉ test / hỏng / sai kích thước): làm trước để bỏ qua các issue dòng của ảnh đó
    removed = set()
    for stem in dict.fromkeys(i.image for i in errors if _is_remove(i.code)):
        codes = sorted({i.code for i in errors if i.image == stem and _is_remove(i.code)})
        removed.add(stem)
        before = _remove_image(ds, stem)
        if before is not None:
            fixes.append(_fix(stem, None, "remove_image", before, f"(đã xoá: {', '.join(codes)})"))

    # 2) data.yaml: tên lớp sai -> ghi lại đúng cfg["classes"]
    if any(i.code == "BAD_CLASS_NAME" for i in errors):
        r = _rename_classes(ds, cfg)
        if r:
            fixes.append(_fix("data.yaml", None, "rename_classes", r[0], r[1]))

    # 3) Thiếu file nhãn: KHÔNG bịa nhãn (kể cả file rỗng) -> chuyển người gán
    for stem in dict.fromkeys(i.image for i in errors if i.code == "MISSING_LABEL_FILE"):
        if stem in removed or ds.image_path(stem) is None or ds.label_path(stem).exists():
            continue
        fixes.append(_fix(stem, None, "needs_label", "(không có file)", "chuyển người gán"))

    # 4) Lỗi dòng: gom theo file, dùng số dòng GỐC, ghi lại file MỘT lần
    drop, clip = defaultdict(set), defaultdict(set)
    for i in errors:
        if i.line is None or i.image in removed:
            continue
        if i.code in DROP_CODES:
            drop[i.image].add(int(i.line))
        elif i.code in CLIP_CODES:
            clip[i.image].add(int(i.line))
    for stem in sorted(set(drop) | set(clip)):
        lp = ds.label_path(stem)
        if not lp.exists():
            continue
        raw_lines = lp.read_text(encoding="utf-8", errors="replace").splitlines()
        out, changed = [], False
        for ln, text in enumerate(raw_lines, 1):
            if ln in drop[stem] and text.strip():                 # xoá dòng thắng clip (một dòng 2 lỗi -> 1 fix)
                fixes.append(_fix(stem, ln, "drop_line", text.strip(), "(xoá)"))
                changed = True
                continue
            if ln in clip[stem] and text.strip():
                try:
                    new = _clip(text)
                except ValueError:                                # dòng hỏng mà chỉ bị báo tràn: xoá cho an toàn
                    new = None
                if new is None:
                    fixes.append(_fix(stem, ln, "drop_line", text.strip(), "(xoá: box nằm ngoài ảnh sau khi cắt)"))
                else:
                    fixes.append(_fix(stem, ln, "clip_box", text.strip(), new))
                    out.append(new)
                changed = True
                continue
            out.append(text)
        if changed:
            lp.write_text("".join(l + "\n" for l in out), encoding="utf-8")
    return fixes
