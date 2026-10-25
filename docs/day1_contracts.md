# Contracts ngày 1

Các schema thực thi nằm trong `backend/app/schemas/`, có Pydantic validation và tests.
Đây là hợp đồng cho các task tiếp theo, không phải báo cáo Agent 3–5 đã triển khai.

## Master Profile

Giữ đúng bảy top-level keys: `contact`, `experience`, `project`, `education`,
`involvement`, `skills`, `summary`. Scalar thiếu là null, collection thiếu là [].
Sáu nhóm đầu vẫn bắt buộc xuất hiện để phát hiện output LLM sai schema.

Contact giữ wire names cũ: `email`, `phone`, `website`, `linkedin`, `github`;
chấp nhận input aliases `email_address`, `phone_number`, `personal_website`,
`linkedin_url`, `github_url`. Thêm địa chỉ có cấu trúc và portfolio tùy chọn.

Experience/project/education/involvement có trường chi tiết tùy chọn và ID ổn định
do Python gán. Không yêu cầu model sinh ID. `description`, `details`, `period`,
`end_date` cũ vẫn được giữ để tương thích. Không đổi GPA/ngày tháng thành giá trị
được suy đoán. Các trường mới không có bằng chứng để null hoặc [].

Skills giữ `items` nguyên gốc và `normalized_items` do Python chuẩn hóa; group label
và IDs là metadata, không bị coi là facts được trích từ nguồn. Chỉ phục hồi kỹ năng
trong section Skills/Kỹ năng có nhãn, không suy ra từ tên dự án hoặc chức danh.

## Evidence và persistence

`SourceEvidence`: field_path, source_id, origin, quote, start, end.

- `document`: quote phải đúng `source_text[start:end]`; chỉ là span match, không phải
  semantic verification hoặc xác minh ứng viên thật sự có năng lực.
- `user_confirmation`: dữ liệu người dùng xác nhận mà chưa đối chiếu được trong CV;
  không có offsets. Không trình bày nguồn này như evidence trích từ CV.
- Employer/institution không định vị duy nhất được thì hạn chế tự điền và cảnh báo.

API không trả toàn bộ text nguồn mặc định. JSON đã xác nhận lưu private envelope
version 2: profile, evidence, warnings, source_text, source_filename. Loader hỗ trợ
legacy raw-profile JSON. Ghi mới được publish atomically và không overwrite ID cũ.
Checkpoint RAM không phải hồ sơ chính thức: không ghi file khi mới extract.

## API hiện tại

| Endpoint | Kết quả |
|---|---|
| POST /api/profiles/extract | Pending profile + thread_id + warnings + evidence |
| GET /api/profiles/{thread_id}/draft | Đọc lại pending draft trong phiên backend hiện tại |
| POST /api/profiles/{thread_id}/confirm | Resume graph và lưu đúng profile người dùng duyệt |
| GET /api/profiles/{thread_id} | Chỉ đọc profile đã xác nhận, cùng evidence/warnings |

File quá lớn: 413; file hỏng/không hỗ trợ: 422; không kết nối Ollama: 503;
Ollama timeout: 504; output model không hợp lệ: 502. Không trả validation payload
của model có thể chứa PII. Thread ID sai định dạng: 422. Unknown confirmation: 400.

## Hợp đồng các ngày sau

- `CVDocument`: language, contact, summary có nguồn, sections/entries/bullets,
  source_profile_revision_id và optional job_analysis_id. Chưa có renderer ngày 1.
- `MatchResult`: version IDs, algorithm version, score nullable, dimension scores,
  assessments với met/partially_met/unknown/not_met, strengths và gaps.
- `ProfilePatch`: base revision, proposed profile, changed paths, evidence; chưa có
  endpoint tự động áp dụng patch ngày 1.
- `WorkflowResponse`: intent, thread ID, status và pending action. Trạng thái waiting
  bắt buộc có pending action; trạng thái khác không được mang pending action.

Ngày 2 bổ sung requirement IDs và AND/OR vào JD contract. Không có Match Score
hardcode, fake Agent hoặc endpoint placeholder trong bản ngày 1.
