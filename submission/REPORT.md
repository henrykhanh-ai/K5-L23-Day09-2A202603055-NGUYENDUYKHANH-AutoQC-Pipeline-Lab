# Báo cáo Day 09 — Nguyễn Duy Khánh, 2A202603055

## 1. Kết luận trước
Pipeline kết luận **Hold** (mã thoát 10). Vào **224** ảnh raw → bước 1 loại **22** ảnh → **202** ảnh vào QC và được xuất thành bản **nháp** `submission/export/clean_v1/` (manifest ghi `decision=Hold`, chưa phải bản phát hành).
Lý do: sau sửa tự động và người duyệt thì **0 lỗi bắt buộc**, nhưng **38/202 ảnh (18,8%)** vẫn còn cảnh báo chưa có người xem, ≥ ngưỡng 10%. Hàng đợi có **125** ảnh, ngân sách duyệt chỉ **80**, nên 45 ảnh cuối hàng không ai xem.

## 2. Lỗi và phân việc
Số liệu từ `01_intake` + `02_error_list_v1` (mẫu số: 224 ảnh quét ở bước 1, 202 ảnh ở QC vòng 1). Dạng "số dòng / số ảnh".

| Mã lỗi | Số dòng / ảnh | Ai sửa | Vì sao |
|---|---:|---|---|
| CORRUPT_IMAGE | 2 / 2 (trên 224) | máy: loại ảnh | `load()` lỗi (ảnh cắt cụt), không train được |
| BAD_SIZE | 3 / 3 | máy: loại ảnh | cạnh ngắn < 250 px |
| DUP_IMAGE_EXACT | 8 / 8 | máy: loại ảnh | trùng md5, giữ ảnh đầu tiên |
| DUP_IMAGE_NEAR | 4 / 4 | máy: loại ảnh | phash ≤ 10 (khoảng cách 0, 0, 6, 10; đã mở xem: đều là trùng thật) |
| LEAK_TEST | 5 / 5 | máy: loại ảnh | trùng ảnh test/gold_val → rò rỉ, làm đẹp mAP giả |
| BAD_CLASS_ID | 6 / 6 (trên 202) | máy: `drop_line` | id 93/4/−1 không có lớp, không đoán được lớp đúng |
| BAD_FORMAT | 3 / 3 | máy: `drop_line` | thiếu cột / `nan` |
| BOX_ZERO | 4 / 4 | máy: `drop_line` | box rộng/cao 0 |
| DUP_BOX | 7 / 7 | máy: `drop_line` | cùng lớp, IoU > 0.9 với dòng trước |
| BOX_OUT_OF_IMAGE | 8 / 8 | máy: `clip_box` | cắt về [0,1], giữ lớp |
| BAD_CLASS_NAME | 2 dòng / data.yaml | máy: `rename_classes` | ghi lại `names` theo `classes` của dự án |
| MISSING_LABEL_FILE | 6 / 6 | **người** (`needs_label`) | máy không được bịa nhãn, kể cả file rỗng |
| POSSIBLE_MISSING | 53 / 52 | người | model thấy vật mà nhãn không có |
| POSSIBLE_LOOSE_BOX | 28 / 24 | người | cùng vật, cùng lớp nhưng IoU < 0.5 |
| POSSIBLE_FALSE_POS | 29 / 27 | người | box nhãn không khớp vật nào model thấy |
| POSSIBLE_WRONG_CLASS | 18 / 18 | người | model nói lớp khác với IoU ≥ 0.5 (chủ yếu car↔truck↔bus) |
| EMPTY_LABEL | 12 / 12 | người | rỗng: ảnh nền hay thiếu nhãn? |
| BOX_TINY / BOX_HUGE / CLASS_RARE | 6/4 · 3/3 · 4/1 | người (ưu tiên thấp) | quy tắc dự án, chỉ cảnh báo |

Máy tự sửa **35** thay đổi (`03_fixes.csv`: 20 `drop_line`, 8 `clip_box`, 6 `needs_label`, 1 `rename_classes`) và loại 22 ảnh ở cửa vào. Sau sửa (`04_error_list_v2`) chỉ còn **6 lỗi bắt buộc**, đều là `MISSING_LABEL_FILE`, đúng thiết kế. Hai hệ quả phụ của autofix: EMPTY_LABEL tăng 12 → 15 (file chỉ có dòng hỏng nên bị xoá hết dòng) và BOX_TINY 6 → 7 (một box bị cắt thành nhỏ). Cả hai đều được đưa vào hàng đợi người.

**Hàng đợi (`05_review_queue.csv`, 125 ảnh):** điểm = Σ trọng số mã × (1 + conf). `NEEDS_LABEL` = 10 nên 6 ảnh chưa có nhãn nằm ngay đầu hàng (chỉ đứng sau img_0020, ảnh có 11,5 điểm do cộng WRONG_CLASS + MISSING + FIXED_DROP_LINE). Tiếp theo là WRONG_CLASS (3) và MISSING/FALSE_POS (2), trong đó dự đoán model càng chắc thì càng lên trước. Với ngân sách 80 ảnh, người duyệt xử lý hết 6 ảnh thiếu nhãn và phần lớn cờ ngữ nghĩa nặng. Sau khi duyệt (`07_error_list_v3`), WRONG_CLASS giảm 18 → 3, MISSING 53 → 13, LOOSE_BOX 28 → 20. 45 ảnh cuối hàng (điểm ≤ 3,3, chủ yếu một cờ MISSING/FALSE_POS) không ai xem.

## 3. Calibration (2 ngưỡng)
Trên `data/calib`, mỗi ô là precision / recall (`submission/calibration/calibration_report.md`).

| Tham số | Khởi đầu | Đã chọn | Precision / Recall (trước → sau) | Lý do (đánh đổi) |
|---|---|---|---|---|
| `duplicates.phash_dist` | 2 | **10** | DUP_NEAR 1.00/0.50 → 1.00/0.67; DUP_EXACT 1.00/1.00 giữ nguyên | Lỗi này dẫn tới **xoá ảnh**, nên ưu tiên precision. Từ 4 đến 14 cho cùng kết quả trên calib. Trên raw, cặp trùng thật xa nhất có khoảng cách 10 (img_0186/img_0061), còn cặp gộp nhầm gần nhất là 16. Chọn 10 là mức nhỏ nhất vẫn bắt đủ 4 cặp trùng thật đã mở xem, và còn cách xa mức bắt đầu gộp nhầm (16), nên không xoá oan ảnh nào. Đánh đổi: một ảnh trùng biến đổi mạnh hơn (khoảng cách 11–15) sẽ lọt qua |
| `second_opinion.conf` | 0.25 | **0.6** | WRONG_CLASS 0.56/0.83 → 0.62/0.83; MISSING 0.50/1.00 → 0.57/1.00; LOOSE 0.29/0.40 → 0.20/0.20; FALSE_POS 0.31/1.00 (không đổi, do `fp_conf` cố định) | Là ngưỡng cao nhất mà recall của WRONG_CLASS và MISSING vẫn đạt tối đa; precision tăng, hàng đợi giảm 143 → 125 ảnh. Lên 0.7 thì recall MISSING tụt còn 0.88, lên 0.8 còn 0.75 |

**Chỗ calibration đánh lừa (có bằng chứng):**
- **`phash_dist = 16` đẹp nhất trên calib** (DUP_NEAR recall 0.83, precision 1.00), nhưng trên raw thì số ảnh bị loại nhảy từ 17 lên 26: LEAK_TEST 5 → 11, DUP_NEAR 4 → 7. Mình mở xem từng cặp mới thì **8/9 là ảnh khác hẳn nhau** (chỉ img_0084/img_0074 là trùng thật) (vd. img_0011 tennis "trùng" img_0008 trượt tuyết, img_0013 bàn laptop "rò rỉ" test_087 sân bóng chày, img_0177 lướt sóng "trùng" img_0113 người đàn ông ngồi bàn). Tới 20 thì 105 ảnh bị coi là rò rỉ test. Calib chỉ có 39 ảnh nên không chứa đủ cặp "khác nhau nhưng phash gần nhau" để lộ ra FP.
- **`conf = 0.8` cho Release**: trên raw, tỉ lệ ảnh còn cảnh báo giảm từ 18,8% xuống 7,9%. Nhưng trong 25 cờ nằm ở dải conf [0.6, 0.8) mà ngưỡng này sẽ bỏ, mình mở xem 12 cờ và thấy khoảng 8 cờ là **lỗi thật** (người bị sót ở img_0030, img_0032, img_0093, img_0116, img_0117; xe ở img_0004). Vì vậy đây là một bản Release giả do checker bị làm mù. Mình chọn giữ conf 0.6 và báo Hold.

## 4. Cửa chặn và điều pipeline KHÔNG bắt được
**(a) Gate chặn thật.** Chạy `python -m pipeline.run --budget 0 --reports work/rep_nb --export-dir work/exp_nb` thì nhận kết luận **REWORK**, **mã thoát 20**, log in "KHÔNG xuất: còn lỗi bắt buộc (Rework)" và thư mục `work/exp_nb` **không được tạo**. Lý do: 6 ảnh `MISSING_LABEL_FILE` không có người gán. Autofix chỉ ghi `needs_label` (xem `03b_fixes_after_review.csv`) chứ không tạo file nhãn, nên lỗi bắt buộc vẫn còn. Lúc này tỉ lệ ảnh còn cảnh báo là 112/202 (55,5%). Ngoài ra `gate.decide` không bỏ qua lỗi ERROR, kể cả với ảnh đã duyệt (`test_error_cannot_be_hidden_by_reviewed`). Chạy hai lần liên tiếp cho ra các file `02`–`07` và `manifest.json` có sha1 giống hệt nhau.

**(b) Điểm mù (có bằng chứng):**
1. **Ảnh trùng bị biến đổi mạnh lọt qua:** cặp img_0084/img_0074 là cùng một ảnh đã bị cắt (mình xem bằng mắt), nhưng phash cách nhau 16 > 10 nên cả hai vẫn nằm trong dataset. Trên calib cũng sót 2/6 ảnh gần trùng ở mức biến đổi cao. Muốn bắt mà không gộp nhầm thì cần thêm đặc trưng khác (ORB/embedding), vì chỉ tăng `phash_dist` thì sẽ gộp nhầm.
2. **Box lỏng nhẹ:** recall LOOSE_BOX trên calib chỉ **0.20** (bắt 1/5 box bị phình ×1,45–1,58), và sau duyệt vẫn còn 20 cờ LOOSE. Box phình thêm khoảng 30% gần như không bị phát hiện.
3. **Nhầm lớp mà model lớn cũng nhầm:** WRONG_CLASS trên calib sót 1/6. Raw có nhiều nhầm car↔truck mà yolo26l cũng không chắc chắn. Bên cạnh đó, FALSE_POS có precision chỉ 0.31 (11 báo động giả trên calib), nên phần lớn thời gian của người duyệt bị tiêu vào cờ sai.

## 5. Train: raw vs clean (tùy chọn, chấm riêng)
**Chưa chạy.** Môi trường làm bài không có GPU/Colab trong buổi này. Phần train 15 điểm sẽ làm sau theo `docs/COLAB.md` (push repo public → notebook `day09_train_compare.ipynb`, 2 seed × 20 epoch). Khi có kết quả, mình sẽ so chênh mAP50 với độ lệch giữa các seed trước khi kết luận.

## 6. Quyết định và ghi chú AI
**(a) Quyết định: Hold.** Bản xuất `clean_v1` chỉ là bản nháp. Để chuyển sang Release thì cần **duyệt thêm ít nhất 18 ảnh trong 45 ảnh cuối hàng đợi** (tăng ngân sách duyệt hoặc chia sang vòng 2), sao cho số ảnh còn cảnh báo dưới 21/202 (dưới 10%). Cách làm **không** được chấp nhận là nâng `conf` để hàng đợi nhỏ lại (xem §3). Nếu người duyệt để lại lỗi cú pháp thì autofix sẽ sửa lại một vòng. Nếu còn `MISSING_LABEL_FILE` thì kết luận chuyển thành Rework.

**(b) Dùng AI: có (Claude).**
- *Prompt chính:* "Clone repo, đọc kỹ từng phần, triển khai từng bước". AI đọc docstring và test của từng stub (đầu vào/đầu ra, ngưỡng lấy từ `cfg`, ca biên, không ghi vào `data/raw`) rồi viết 4 module theo thứ tự label_format → gate → autofix → second_opinion.
- *Cách kiểm:* chạy `pytest` cho từng file rồi toàn bộ (79 passed). Chạy calibrate trên bộ lỗi chèn và `make run` 2 lần để so sha1. Mở xem bằng mắt các cặp ảnh "trùng" và các cờ MISSING. Chạy `--budget 0` để thấy Rework. Kiểm tay thêm các ca: một dòng dính 2 lỗi (tràn + DUP_BOX, chỉ ghi 1 `drop_line`) và dòng trống ở giữa file (số dòng gốc giữ nguyên).
- *Chọn ngưỡng:* AI chạy 2 sweep, thử trên raw và đề xuất `phash_dist = 12`, `conf = 0.6` kèm bằng chứng (bảng sweep, các cặp ảnh "trùng", các cờ MISSING). Tôi xem lại rồi **giữ `conf = 0.6`** và **chọn `phash_dist = 10`** (mức nhỏ nhất vẫn bắt đủ các cặp trùng thật trên raw). Kết quả pipeline không đổi: Hold, 38/202.
- *Một lần AI sai:* bản nháp đầu của `gate.decide` có chữ ký sai (thêm một tham số thừa trước `reviewed`). Lỗi này được phát hiện khi đọc lại so với cách `run.py` gọi `decide(..., set(reviewed))` và đã sửa trước khi chạy test. Ngoài ra, nếu tin bảng sweep thì AI sẽ chọn `phash_dist = 16`; chỉ khi mở ảnh ra xem mới thấy đó là sai.
