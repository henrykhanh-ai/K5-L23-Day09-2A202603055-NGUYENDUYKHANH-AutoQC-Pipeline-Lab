"""BƯỚC 4 — Cửa chặn: quyết định Release / Hold / Rework.   ★

Test:  pytest tests/test_gate.py -q

Cây quyết định Day 07 (slide Day 09: "Lỗi bắt buộc chặn pipeline; lỗi cảnh báo chuyển người xem"):

  còn ≥ 1 lỗi bắt buộc (severity ERROR)                          -> "Rework"
  không còn lỗi bắt buộc, nhưng tỉ lệ ẢNH còn cảnh báo
      >= cfg["gate"]["warn_ratio_hold"]                          -> "Hold"
  còn lại                                                        -> "Release"

Tỉ lệ cảnh báo = (số ẢNH khác nhau có ≥ 1 cảnh báo) / (tổng số ảnh).  Chú ý:
- chỉ đếm issue có `image` nằm trong `image_stems` (bỏ "<dataset>", "data.yaml");
- bỏ qua ảnh nằm trong `reviewed` (người đã xem, cảnh báo của ảnh đó coi như đã xử lý) — nhưng LỖI BẮT BUỘC thì không bao giờ được bỏ qua;
- mẫu số là số ảnh, không phải số issue.

Trả về dict: decision, n_errors, n_warn_images, n_images, warn_ratio (làm tròn 4 chữ số), reasons (list[str], giải thích bằng tiếng Việt, có số liệu).
"""
from ..common import ERROR, WARN  # noqa: F401


def decide(issues, image_stems, cfg, reviewed=frozenset()):
    stems = set(image_stems)
    reviewed = set(reviewed)
    limit = cfg["gate"]["warn_ratio_hold"]

    errors = [i for i in issues if i.severity == ERROR]                 # lỗi bắt buộc: KHÔNG bao giờ bỏ qua (kể cả ảnh đã duyệt)
    warn_imgs = {i.image for i in issues
                 if i.severity == WARN and i.image in stems and i.image not in reviewed}
    n_img = len(stems)
    ratio = round(len(warn_imgs) / n_img, 4) if n_img else 0.0

    reasons = []
    if errors:
        decision = "Rework"
        codes = sorted({i.code for i in errors})
        reasons.append(f"còn {len(errors)} lỗi bắt buộc ({', '.join(codes)}) trên "
                       f"{len({i.image for i in errors})} ảnh/file: phải sửa trước khi phát hành")
    elif ratio >= limit:
        decision = "Hold"
        reasons.append(f"{len(warn_imgs)}/{n_img} ảnh ({ratio:.1%}) còn cảnh báo chưa người duyệt >= ngưỡng {limit:.0%}")
    else:
        decision = "Release"
        reasons.append(f"không còn lỗi bắt buộc; {len(warn_imgs)}/{n_img} ảnh ({ratio:.1%}) còn cảnh báo chưa duyệt < ngưỡng {limit:.0%}")
    if decision == "Rework":
        reasons.append(f"tỉ lệ ảnh còn cảnh báo chưa duyệt: {len(warn_imgs)}/{n_img} ({ratio:.1%}), ngưỡng Hold {limit:.0%}")
    return dict(decision=decision, n_errors=len(errors), n_warn_images=len(warn_imgs),
                n_images=n_img, warn_ratio=ratio, reasons=reasons)
