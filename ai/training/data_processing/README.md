# Các file xử lý dữ liệu CV

Mục tiêu: tạo dữ liệu CV phù hợp JD, chỉ dùng thông tin có trong CV gốc. Không tự thêm kinh nghiệm, kỹ năng hoặc thành tích từ JD.

## 1. File xử lý

### `prepare_data.py` — Chuẩn bị từng mẫu

Tách CV gốc, JD và CV đầu ra từ dataset; chuẩn hóa khoảng trắng/giá trị thiếu; kiểm tra schema và các dữ kiện cần giữ nguyên. Có hàm xử lý từng mẫu để các bước sau sử dụng lại.

File này chỉ chứa các hàm mà pipeline cần. Lệnh chạy duy nhất nằm trong `build_data.py`.

### `audit_data.py` — Kiểm tra dấu hiệu lỗi

Kiểm tra kỹ năng/công nghệ chưa tìm thấy trong nguồn, số mới, dữ kiện thiếu, bản ghi trùng và CV trùng giữa các tập. Kết quả là dấu hiệu cần duyệt, không phải kết luận chắc chắn sai.

### `clean_data.py` — Tạo đáp án từ CV gốc

Thay đáp án sinh chưa được xác minh bằng nội dung CV gốc. Chỉ ưu tiên thứ tự kỹ năng/bullet liên quan JD, giữ nguyên công ty, chức danh, ngày và nội dung kinh nghiệm. Kiểm tra đáp án không thêm hoặc xóa dữ kiện nguồn.

### `source_review_decisions.json` — Quyết định duyệt nguồn

Lưu quyết định giữ/loại, lý do và bằng chứng cho 35 mẫu đã xem xét: giữ 24, tạm loại 11. Mỗi quyết định có checksum để tránh áp dụng vào mẫu đã thay đổi. Đây là dữ liệu quyết định, không phải code hay dữ liệu train.

### `apply_source_review.py` — Áp dụng quyết định duyệt

Đọc quyết định ở file trên; tách 11 mẫu có vấn đề và chuẩn hóa metadata thiếu/bị che của 24 mẫu giữ lại. Áp dụng đồng nhất cho CV input/output, không suy đoán giá trị thiếu.

### `rewrite_data.py` — Viết lại summary và bullet

Tạo summary từ chức danh/kỹ năng trong CV gốc, ưu tiên phần liên quan JD. Chỉnh một số cách diễn đạt bullet, chủ ngữ và dấu câu; giữ nguyên số liệu và mức trách nhiệm. Lưu câu trước/sau và căn cứ summary. Đây là cách viết bằng quy tắc, văn phong còn theo mẫu.

### `export_data.py` — Chia tập và xuất dữ liệu train

Kiểm tra target, xử lý cặp CV/JD trùng, gom các CV giống nhau hoặc có dấu mốc chung vào một nhóm. Mỗi nhóm chỉ thuộc một tập train/validation/test. Xuất JSON dạng prompt(system/user) và completion(assistant), kèm phân nhóm và checksum. Cách nhận diện nhóm là heuristic, chưa xác minh danh tính ứng viên.

### `build_data.py` — Điều phối toàn bộ

Đọc snapshot raw và kiểm tra checksum, gọi lần lượt các hàm chuẩn bị → clean → duyệt nguồn → viết lại → xuất split. Sau khi thành công, xóa các file trung gian cũ đã biết trong processed. Đây là file nên chạy khi muốn tái tạo bản dữ liệu hiện tại.

### `check_data.ipynb` — Xem dữ liệu

Đọc bản viết lại bằng `dataset[0]`, xem CV/JD, so sánh câu trước/sau, đọc báo cáo và xem mẫu trong các tập train. Có cell chạy lại pipeline khi cần.

### `__init__.py` — Khai báo package

Cho phép import các module trong thư mục và chạy bằng `python -m`. Không xử lý dữ liệu.

## 2. File kiểm thử trong `tests/`

| File | Kiểm tra |
|---|---|
| `test_data_processing.py` | Tách JSON, chuẩn hóa, schema, đối chiếu dữ kiện, checksum và dấu hiệu lỗi |
| `test_clean_data.py` | Loại nội dung thêm thiếu căn cứ, ưu tiên thứ tự và bảo toàn nguồn |
| `test_source_review.py` | Áp dụng giữ/loại, chuẩn hóa giá trị thiếu, phát hiện quyết định lỗi thời |
| `test_rewrite_data.py` | Summary có căn cứ, bullet giữ số/mức trách nhiệm và phát hiện chỉnh sửa ngoài quy tắc |
| `test_export_data.py` | Gom nhóm, định dạng hội thoại, xử lý trùng và kết quả chia tập tái lập |
| `test_data_io.py` | Đọc, ghi JSON nhiều dòng và tạo checksum ổn định |

## 3. Cách chạy

Tại thư mục gốc KLTN:

```bash
conda activate kltn
python -m ai.training.data_processing.build_data
```

Chạy kiểm thử:

```bash
python -m unittest discover -s ai/training/data_processing/tests
```

Chỉ `build_data.py` có lệnh chạy. Những file còn lại là các hàm nhỏ được build và test gọi trực tiếp.

## 4. File dữ liệu đầu ra

Trong `ai/data/processed` (JSON nhiều dòng, một danh sách mẫu):

| File | Nội dung |
|---|---|
| `rewritten_dataset.json` | Bản hiện tại có summary/bullet viết lại |
| `rewrite_changes.json` | Câu trước/sau và căn cứ từng phần summary |
| `rewrite_report.json` | Thống kê viết lại và giới hạn |
| `source_review_changes.json` | Metadata được chuẩn hóa sau duyệt |
| `excluded_by_source_review.json` | Mẫu tạm loại và lý do |

`ai/data/raw` giữ snapshot gốc và manifest. `ai/data/splits` giữ train/validation/test, assignments và báo cáo xuất. File `duplicate_pairs.json` chỉ xuất hiện khi thực sự có cặp trùng.

## 5. Trạng thái hiện tại

Có 589 mẫu: 471 train, 59 validation, 59 test. Đã viết lại 589 summary và chỉnh 270 bullet thuộc 147 mẫu; 24 kiểm thử đạt.

Đáp án được kiểm chứng theo quy tắc, chưa được duyệt thủ công toàn bộ về ý nghĩa. Trước train cần chốt Qwen/tokenizer, kiểm tra độ dài token và đánh giá chất lượng câu. `user_info` hiện rỗng, chưa dạy mô hình xử lý thông tin người dùng bổ sung.

## 6. Định dạng dễ đọc

Các file dữ liệu là JSON chứa một danh sách mẫu, được ghi với indent=2 và UTF-8. Dùng json.load/json.loads để đọc cả file, không đọc từng dòng như JSONL. Hugging Face load_dataset("json", ...) vẫn đọc được các tập train/validation/test.

Content của message vẫn là chuỗi theo định dạng hội thoại của mô hình, nên JSON trong chuỗi có ký tự escape. Muốn xem CV dàn dòng đầy đủ trong file, mở rewritten_dataset.json; trong notebook có thể dùng json.loads(message["content"]) để xem nội dung message. Không đổi content thành dict vì sẽ làm sai kiểu dữ liệu cho trainer.
