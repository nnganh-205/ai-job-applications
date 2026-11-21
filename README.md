# KLTN Career Workspace

Ứng dụng tìm việc và tạo CV với React/Vite, FastAPI, PostgreSQL và Ollama. Mã AI được dùng chung bởi backend và quy trình huấn luyện, nên nằm ở thư mục `ai/` thay vì sao chép vào `backend/app/ai/`.

## Cấu trúc

```text
frontend/
  src/app/          Điều hướng và bố cục
  src/features/     Các trang theo chức năng: việc làm, CV, trợ lý, phỏng vấn
  src/components/   Thành phần giao diện dùng chung
  src/lib/          API client và hàm gọi backend
  src/styles/       CSS
backend/
  app/api/          REST endpoints hiện có
  app/core/         Cấu hình môi trường
  app/db/           PostgreSQL, migration và repository
  app/schemas/      Pydantic schemas
  app/services/     Nghiệp vụ và tác vụ nền
  tests/            Kiểm tra backend
ai/
  agents/           Phân tích CV, JD và matching
  graph/            Luồng xử lý AI
  llm/              Kết nối Ollama
  prompts/          Prompt cho từng tác vụ
  training/         Chuẩn bị và rà soát dữ liệu
  colab/            Notebook, mã train và checkpoint 8B
  models/           Model/adapter cục bộ
  data/             Nguồn và các tập dữ liệu AI
  rag/              PDF luật lao động, OCR và tìm nguồn cho chatbot
scripts/           Công cụ nhập dữ liệu và kiểm tra thủ công
output/            Gói dữ liệu Colab đang dùng, ghi chú dự án; kết quả kiểm tra được tạo khi chạy scripts
docker-compose.yml PostgreSQL cục bộ
.env.example       Mẫu biến môi trường
requirements.txt   Thư viện Python
```

Frontend hiện dùng **JavaScript**, nên không có `types/` TypeScript. Backend hiện dùng worker nội bộ, chưa dùng Celery, Redis, Qdrant hoặc JWT; không tạo thư mục và dịch vụ rỗng cho chúng. API giữ đường dẫn `/api/...` để frontend và dữ liệu hiện có hoạt động như trước.

## Chạy cục bộ

1. Khởi động PostgreSQL: `docker compose up -d db`.
2. Sao chép `.env.example` thành `.env` và điền cấu hình. Backend tự đọc `.env` ở thư mục gốc khi khởi động; biến đã export trong terminal được ưu tiên.
3. Cài Python dependencies từ `requirements.txt` trong môi trường Python của dự án.
4. Trong `frontend/`, chạy `bun install` và `bun --bun run build`.
5. Từ thư mục gốc, chạy `python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8013`.

Mở `http://127.0.0.1:8013`. Các tính năng AI cần Ollama và model đã cấu hình trong `.env.example`.

## Tài khoản và không gian cá nhân

Nút **Đăng ký** trên thanh điều hướng mở `/register`; `/login` dành cho tài khoản đã có.
Đăng ký bằng họ tên, email và mật khẩu từ 8 ký tự. Sau đăng ký, hệ thống đăng nhập
và khởi tạo hồ sơ chỉ gồm tên/email đã cung cấp; người dùng tiếp tục bổ sung dữ kiện như trước.
Trang chủ, mẫu CV và danh sách việc làm vẫn có thể xem khi chưa đăng nhập.

Mật khẩu được băm bằng scrypt với salt riêng; phiên đăng nhập dùng cookie HttpOnly,
có thể thu hồi khi đăng xuất, thời hạn 7 ngày. Yêu cầu thay đổi dữ liệu sử dụng token CSRF.
Không lưu mật khẩu hoặc token phiên trong localStorage. Khi triển khai HTTPS, đặt
`AUTH_COOKIE_SECURE=1`; cấu hình mặc định hỗ trợ chạy HTTP trên localhost.

Hồ sơ, CV, ảnh, hội thoại, phỏng vấn, tin đã lưu và tác vụ được tách theo tài khoản.
Dữ liệu demo cũ vẫn giữ nguyên trong namespace cũ, không tự gán cho người đăng ký đầu tiên.
Backend tự chạy các migration bổ sung khi khởi động ở chế độ PostgreSQL. Chế độ JSON
lưu tài khoản trong `backend/storage/accounts.sqlite3`; có thể đổi bằng `AUTH_SQLITE_PATH`.

Kiểm thử tài khoản không gọi mô hình: `KLTN_ENV_FILE=/dev/null python -B -m unittest backend.tests.test_auth`.

## Trang quản trị

Mở `/login?next=/admin` để đăng nhập quản trị. Khi khởi động lần đầu, backend tạo
một Admin với email mặc định `admin@career.local` và mật khẩu ngẫu nhiên, lưu riêng
trong `backend/storage/admin-bootstrap.json` với quyền đọc/ghi chỉ cho chủ máy.
File này bị loại khỏi Git và không được phục vụ qua HTTP. Có thể cấu hình `ADMIN_EMAIL`
và `ADMIN_PASSWORD` trước lần khởi tạo đầu; mật khẩu tự cấu hình cần ít nhất 12 ký tự.
Khởi động lại không đổi mật khẩu, không cấp quyền cho một email đã đăng ký từ trước.
Có thể đặt `ADMIN_BOOTSTRAP_PATH` nếu cần đổi nơi lưu thông tin đăng nhập ban đầu.

Dashboard CRM tại `/admin` có tổng quan dữ liệu thật, quản lý tài khoản, tài liệu,
mẫu CV, theo dõi/thử lại tác vụ lỗi và nhật ký quản trị. API kiểm tra quyền Admin phía
backend. Khóa tài khoản hoặc đổi quyền/mật khẩu sẽ thu hồi các phiên của tài khoản đó;
không cho tự khóa, tự hạ quyền hoặc làm mất Admin cuối cùng. Worker bỏ qua hàng chờ
của tài khoản đang khóa. Thử lại tác vụ có thể gọi mô hình theo cấu hình hiện có.

Kho RAG nhập một lần 5 nguồn và các đoạn đã có trong `ai/rag/index.json`, giữ số trang,
điều luật và đường dẫn nguồn. Admin có thể sửa nội dung, thêm văn bản, tải PDF có lớp
văn bản, chuyển bản nháp/đang sử dụng/lưu trữ, và thử tra cứu nguồn không gọi LLM.
Mỗi lần sửa cập nhật chỉ mục ngay; phiên bản tránh ghi đè khi hai quản trị viên cùng sửa.
Chỉ nguồn đang sử dụng tham gia `ai.rag.labor_law.retrieve`, áp dụng cho các câu hỏi
luật của trợ lý hiện có. PDF tải lên tối đa 10 MB/300 trang; PDF scan cần OCR trước.
Nguồn được lưu bền vững trong PostgreSQL, hoặc cùng SQLite tài khoản ở chế độ JSON;
các thay đổi quản trị không ghi đè PDF/index gốc. Nhật ký không lưu mật khẩu.

Mục **Mẫu CV** tại `/admin/templates` cho phép thiết kế mẫu mới độc lập: một/hai cột,
vị trí và độ rộng cột phụ, thứ tự và vị trí các mục, ảnh, kiểu tiêu đề, lề trang,
màu và phông chữ. Bản xem trước cập nhật từ cấu hình trước khi lưu. Mẫu mới có
renderer riêng, không cần chọn một bố cục cũ. Các mẫu gốc vẫn chỉnh tên, nhóm,
màu, phông chữ, ẩn/hiện hoặc xóa khỏi thư viện được.
Danh mục được lưu trong PostgreSQL hoặc SQLite và cập nhật trực tiếp thư viện người
dùng. Xóa giữ lại thông tin bố cục để CV đã tạo vẫn mở và xuất PDF được. Không cho
ẩn hoặc xóa mẫu đang hiển thị cuối cùng; cập nhật kiểm tra phiên bản và ghi nhật ký.
Mỗi thiết kế phải chứa đủ các nhóm dữ liệu chuẩn, mỗi nhóm xuất hiện đúng một lần.
Thiết kế chỉ thay đổi trình bày; schema hồ sơ, CVDocument và source_refs của AI được
giữ nguyên, áp dụng cho phân tích, đối chiếu JD, luyện phỏng vấn và xuất PDF.
Ba cột Tài liệu có cùng chiều cao và cuộn độc lập để giữ bố cục cân đối.

Mục Sự kiện được gỡ khỏi thanh điều hướng, footer và API công khai; `/events` chuyển
về trang chủ. Lịch sử sự kiện nghiệp vụ trong quy trình ứng tuyển vẫn được giữ nguyên.

Kiểm thử quản trị không gọi mô hình: `KLTN_ENV_FILE=/dev/null python -B -m unittest backend.tests.test_admin`.

Với máy M2/RAM 16 GB, thoát ứng dụng Ollama trước rồi chạy `sh scripts/serve_ollama.sh` từ thư mục gốc. Script bật Flash Attention, KV cache q8_0, context mặc định 8K và chỉ nạp một model cùng lúc để giảm bộ nhớ. Backend tự tăng context cho tài liệu dài; model vẫn là Qwen3 8B. Không chạy script khi một Ollama server khác còn chiếm cổng 11434. Các tuỳ chọn server này không có hiệu lực chỉ bằng việc thêm vào `.env.example` của backend.

Luồng import CV dùng schema trích xuất gọn, không yêu cầu model chép lại một bullet vào nhiều trường. Kết quả thành công của cùng nội dung được tái sử dụng trong bộ nhớ tối đa 10 phút/8 CV trên mỗi tiến trình backend; upload đồng thời cùng CV dùng chung lượt trích xuất. Các phiên và dữ liệu form vẫn độc lập. Khởi động lại backend để áp dụng thay đổi code nếu không dùng `--reload`.

Để tạo lại chỉ mục luật lao động sau khi thay PDF trong `ai/rag/`, chạy `python -m ai.rag.labor_law` từ thư mục gốc.

## Dùng Groq cho trích xuất CV và chatbot

Trong terminal đã cấu hình PostgreSQL và đang chạy backend, dừng backend bằng Ctrl+C. Với zsh, nhập key qua prompt ẩn để không lưu key trong lịch sử lệnh:

```sh
read -rs "GROQ_API_KEY?Dán Groq API key rồi nhấn Enter: "
export GROQ_API_KEY
export GROQ_TASKS=profile,assistant
export GROQ_MODEL=openai/gpt-oss-120b
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8013
```

Dùng đúng môi trường Python của dự án (`conda activate kltn` nếu cần). Có thể điền `GROQ_API_KEY`, `GROQ_MODEL` và `GROQ_TASKS` trực tiếp trong `.env` thay vì nhập qua terminal. Giữ nguyên cấu hình PostgreSQL/DATABASE_URL. Khởi động lại backend sau khi sửa `.env`; sửa `.env.example` hoặc chỉ reload trang không kích hoạt kết nối. Biến đã export được ưu tiên hơn `.env`; dùng `unset GROQ_API_KEY GROQ_TASKS GROQ_MODEL` nếu muốn đọc lại ba giá trị này từ file. Key không được đưa vào frontend hay commit vào repo.

`GROQ_TASKS` chỉ chuyển những tác vụ được liệt kê sang Groq. Mặc định để trống vẫn dùng Ollama. Các task hợp lệ: `default,profile,jd,update,cv,form,interview,assistant,writer,verifier`. Model fine-tune vẫn phục vụ `writer` local nếu không đưa task này vào danh sách. Chuyển thêm task cần chủ động thêm vào danh sách. Groq dùng JSON Schema best-effort, sau đó luôn kiểm tra lại bằng Pydantic và các quy tắc dữ kiện hiện có. Hết quota trả thông báo chờ, không tự chuyển sang model local hoặc dịch vụ trả phí.

Để quay về local, đặt `GROQ_TASKS=` trong `.env`, bỏ biến `GROQ_TASKS` đã export nếu có, rồi khởi động lại backend. Việc chỉ thêm key không tự gửi dữ liệu lên cloud; routing chỉ bật khi `GROQ_TASKS` có task tương ứng. Khi bật, nội dung cần thiết của task đó sẽ được gửi đến Groq. Khi chạy unit tests độc lập với cấu hình thật, dùng `KLTN_ENV_FILE=/dev/null python -B -m unittest discover -s backend/tests`.

## Cloudflare Workers AI

Điền `CLOUDFLARE_ACCOUNT_ID` và `CLOUDFLARE_API_TOKEN` trong `.env`, rồi chọn các task:

```dotenv
CLOUDFLARE_MODEL=@cf/openai/gpt-oss-20b
CLOUDFLARE_CV_MODEL=
CLOUDFLARE_TASKS=jd,interview,cv,verifier
CLOUDFLARE_TIMEOUT_SECONDS=120
CLOUDFLARE_MAX_OUTPUT_TOKENS=2048
GROQ_TASKS=profile,assistant,update
GROQ_ASSISTANT_MODEL=openai/gpt-oss-20b
GROQ_PROFILE_MODEL=openai/gpt-oss-120b
GROQ_UPDATE_MODEL=openai/gpt-oss-20b
```

Để trống `CLOUDFLARE_CV_MODEL` sẽ dùng model Cloudflare chung; chỉ đặt `@cf/qwen/qwen3.8-27b` khi chủ động chọn model mạnh hơn cho rà soát CV. `writer`/`refine` giữ trên Qwen8B fine-tune qua Ollama. Hai nhà cung cấp không được nhận trùng task. Cloudflare dùng endpoint Chat Completions tương thích OpenAI, JSON Schema và kiểm tra Pydantic; không tự retry request hay chuyển nhà cung cấp khi lỗi. Task nghiệp vụ có thể cần nhiều lần gọi để tạo/kiểm tra/sửa kết quả. Cache JD phân biệt provider và model; phiên phỏng vấn mới ghim đúng provider/model đang chạy.

Sau khi đổi `.env`, khởi động lại backend. Để kiểm tra một task bằng dữ liệu giả lập và đúng một lần gọi API, chạy một lệnh, ví dụ:

```sh
python -B -m scripts.check_cloudflare --task jd
```

Các lựa chọn là `jd`, `interview`, `cv`, `verifier`. Lệnh không tự thử lại khi lỗi, không sửa CV/hồ sơ và không hiển thị token. Unit tests dùng MockTransport, không tiêu hao API thật.
