# KLTN Job Search và ATS CV

Dự án gồm backend FastAPI, frontend React và pipeline AI/QLoRA. Phiên bản hiện tại triển
khai Profile Agent và JD Analysis Agent bằng Qwen3-4B chạy local qua Ollama.

## Chạy Profile Agent

```bash
conda activate kltn
python -m pip install -r requirements.txt
ollama pull qwen3:4b
ollama serve
python -m uvicorn backend.app.main:app --reload
```

Mở `http://127.0.0.1:8000/docs`, gọi `POST /api/profiles/extract` để upload CV. Sau khi
kiểm tra và sửa JSON, gọi `POST /api/profiles/{thread_id}/confirm`. Hồ sơ đã xác nhận có
thể đọc bằng `GET /api/profiles/{thread_id}`.

Có thể upload nhanh từ terminal:

```bash
curl -F "file=@/duong-dan-den/CV.pdf" http://127.0.0.1:8000/api/profiles/extract
```

## Phân tích Job Description

Mở Swagger tại `http://127.0.0.1:8000/docs` và gọi `POST /api/jobs/analyze`.

Phân tích JD dạng text:

```json
{
  "job_description_text": "Backend Developer. Python is required. Docker is a plus."
}
```

Phân tích JD từ URL công khai:

```json
{
  "source_url": "https://example.com/jobs/backend-developer"
}
```

Đọc lại một JD đã lưu mà không tải website lần nữa:

```json
{
  "saved_job_id": "job_id_từ_lần_phân_tích_trước"
}
```

Agent chỉ trích xuất và phân loại yêu cầu. Agent không so sánh CV, tính match score hay
đề xuất chỉnh sửa CV. Kết quả được lưu tạm dưới dạng JSON trong `backend/storage/jobs/`.

## Luồng xử lý

1. Kiểm tra file và đọc văn bản bằng PyMuPDF hoặc python-docx.
2. Qwen3-4B đọc CV tiếng Anh, tiếng Việt hoặc song ngữ và chỉ phân loại thông tin có
   sẵn thành 7 nhóm trong schema. Nội dung gốc không được dịch hoặc viết lại.
3. Pydantic kiểm tra cấu trúc; validator tạo cảnh báo khi thông tin quan trọng không
   tìm thấy nguyên văn trong CV.
4. LangGraph dừng chờ người dùng kiểm tra. Chỉ profile đã xác nhận mới được lưu.

Ollama được cấu hình context 16K token và timeout 10 phút để xử lý CV dài. Lần gọi đầu
có thể chậm hơn vì model phải được nạp vào bộ nhớ.

Dữ liệu gốc và các split cũ vẫn được giữ trong `ai/data/raw/` và `ai/data/splits/` để
đối chiếu. Pipeline tiền xử lý cũ đã được dọn khỏi `ai/training/` để có thể thiết kế lại
theo hướng mới mà không lẫn logic cũ.
