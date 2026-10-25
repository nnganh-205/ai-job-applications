# KLTN Job Search và ATS CV

Dự án gồm backend FastAPI, frontend React và pipeline AI/QLoRA. Phiên bản hiện tại triển
khai Profile Agent và JD Analysis Agent bằng Qwen3-4B chạy local qua Ollama,
Matching Agent dùng Python xác định, không gọi model để tạo điểm.

## Giao diện Matching và model được yêu cầu

Matching hiển thị điểm và các nhóm nhãn ngắn; diễn giải/evidence/cache/version vẫn
nằm trong API, không bày trên panel người dùng. Đã kiểm tra browser với backend thật.

Model [med2425/resume-ats-fit](https://huggingface.co/med2425/resume-ats-fit) **chưa
được bật**. Đã đọc model card/config/file metadata ở revision
`79191e8a8dc8ac99771fecb8e9853d25feb508c9`: checkpoint khoảng 552 MB, base Nomic
khoảng 547 MB. Ví dụ inference phụ thuộc lớp `NomicContrastive` chưa được công bố
trong các file của model. Đang cần mã inference chính xác và xác nhận tải model
(trước đó người dùng yêu cầu không tải). Không thay bằng Nomic base rồi gắn nhãn
checkpoint fine-tuned; điểm đang hiển thị vẫn từ Matching engine hiện có.
Cosine similarity của model mới cần được phân biệt với điểm đáp ứng yêu cầu và
không phải xác suất tuyển dụng. Chưa kiểm chứng chất lượng trên CV/JD tiếng Việt.

## Ngày 4 — Review/tạo CV và xuất PDF

Tại **http://127.0.0.1:5173/**, chọn job → **Optimize CV**, hoặc mở tab **Tạo CV**
để tạo/review CV tổng quát. Qwen tạo bản nháp có nguồn; chọn ATS đơn giản hoặc
Truyền thống, chỉnh bullet, xem trước, xác nhận rồi tải PDF thật. Không tự sửa
Master Profile. PDF dùng PyMuPDF/Unicode, chưa dùng XeLaTeX hoặc xuất DOCX.

Đã qua Qwen thật, browser E2E trên storage tạm và test PostgreSQL/checkpoint/PDF
riêng. Full regression 201 tests: 190 pass, 11 opt-in skip. Chưa có adapter QLoRA:
audit phát hiện dataset hiện tại khác contract runtime; scripts chuẩn bị/đánh giá
và training opt-in đã có, CUDA training/export chưa được thực thi.
Chi tiết: [báo cáo, cách dùng và giới hạn Ngày 4](docs/day4_evidence.md).

## Ngày 3 — đang triển khai

Đã có Profile Update Agent (Agent 4), interrupt/approve, revision bất biến,
confirmed-answer ledger, tự chấm lại từ Dashboard và chat tạo Master Profile.
JSON mode đã qua unit/API/Qwen/browser tests. Bản thử nghiệm PostgreSQL thật tại
**http://127.0.0.1:8013/**, có 23 jobs và hồ sơ đã xác nhận hiện có.

Đã cài driver/checkpointer vào Conda `kltn`, migrate bổ sung, import 70 bản ghi JSON
không sửa file gốc và kiểm tra import lại không trùng. Test PostgreSQL riêng đã qua
checkpoint/reconnect, đọc phiên chờ duyệt bằng tiến trình Python mới, approval,
revision và rematch. Chưa nghiệm thu browser E2E đầy đủ trên PostgreSQL.
Xem [báo cáo và cách chạy ngày 3](docs/day3_evidence.md),
[dependencies ngày 3](requirements-day3.txt).
Đã dọn file kết quả/dữ liệu phiên kiểm thử; giữ mã nguồn tests, CV và jobs thật.

## Mốc ngày 2 — T05–T08

Recruitment Dashboard là trang chính, hiện dùng các nguồn thay thế đã được chấp thuận:
Himalayas, Remote OK, Greenhouse (Grafana Labs) và Lever (Palantir/Spotify).
Đây là nguồn quốc tế/remote, không phải nguồn tổng hợp việc làm Việt Nam. Dashboard có
search theo công việc/kỹ năng/công ty, lọc địa điểm/hình thức, lưu việc và refresh
thủ công. Chọn job để xem JD đầy đủ, Agent 2 phân tích ngầm rồi Agent 3 tính điểm
từ Master Profile đã xác nhận; không cần upload CV lại khi đổi job.

Analysis được cache theo content hash, extractor version và model; matching theo
profile snapshot, analysis, algorithm version và ngày tính. Thiếu hồ sơ hoặc dữ liệu
thì không tạo phần trăm giả; quan hệ yêu cầu mơ hồ được yêu cầu kiểm tra. Snapshot
có nguồn và thời điểm lấy, không bảo đảm tin vẫn mở ở thời điểm xem.

Nguồn Việt Nam: form **Dán JD kèm URL nguồn** nhận nội dung người dùng có quyền
sử dụng và nhận diện TopCV, ITviec, JobsGO, Indeed, LinkedIn theo hostname.
Dashboard có bộ lọc nguồn. Đây là nhập nội dung người dùng cung cấp, **chưa phải
đồng bộ tự động** từ năm nền tảng này: không tạo thời điểm fetch giả và không tự
fetch lại JD đã nhập bằng text. Nhập lại cùng URL sẽ cập nhật cùng posting và giữ
snapshot nội dung cũ. Các tin đã nhập vẫn được giữ nguyên; chưa tự động đồng bộ từ
TopCV, ITviec hoặc JobsGO.

Refresh lấy một tập nhỏ từ mỗi nguồn, không gọi Qwen. Himalayas dùng search theo
software engineer/country VN nhưng điều kiện địa lý trong JD vẫn cần được kiểm tra;
không mặc định remote là làm được từ Việt Nam. Greenhouse/Lever theo company board,
không phải search toàn bộ thị trường. Greenhouse lấy danh sách nhẹ rồi tải tối đa
hai JD chi tiết để giữ giới hạn response 2 MB. Remote OK bỏ entry chứa điều khoản.
Tin có ngày hết hạn được ẩn khỏi danh sách và không chạy matching, snapshot vẫn giữ.

Cache feed: Himalayas 24 giờ; Remote OK/Greenhouse 1 giờ; cooldown chung 30 giây.
Lỗi nguồn ngoài giữ snapshot và hiển thị thông báo. Attribution/link nguồn được
hiển thị trong Job Details; Himalayas giữ nguyên applicationLink, Remote OK dẫn
về tin gốc, không sử dụng logo nền tảng.

Bản này chỉ phục vụ demo local cá nhân. [Điều khoản Himalayas](https://himalayas.app/terms)
hạn chế phân phối lại tin sang job board/aggregator khác; cần kiểm tra lại phạm vi
sử dụng trước khi mở public. Tài liệu nguồn:
[Himalayas](https://himalayas.app/api), [Remote OK](https://remoteok.com/api),
[Greenhouse](https://docs.greenhouse.io/job-board), [Lever](https://github.com/lever/postings-api).

PostgreSQL persistence/Update Profile đã có ở ngày 3; Optimize CV được nối Agent 5
ở ngày 4. Kho JSON cũ được giữ nguyên.

- Công thức, trọng số, API và giới hạn: [docs/day2_matching.md](docs/day2_matching.md).
- Báo cáo thực thi ngày 2: [docs/day2_evidence.md](docs/day2_evidence.md).
- Dashboard và nguồn thay thế: [docs/day2_dashboard.md](docs/day2_dashboard.md).
- API mới: `GET /api/jobs/{job_id}`, `POST /api/matches`, `GET /api/matches/{result_id}`.
- Matching chỉ nhận `profile_id` của hồ sơ đã xác nhận và `job_id` đã phân tích.
  Không tự sửa hồ sơ khi tìm thấy khoảng thiếu.

Kiểm tra nhanh trên website:

1. Mở `http://127.0.0.1:5173/` (Vite, proxy 8013) hoặc `http://127.0.0.1:8013/` (build).
2. Vào **Hồ sơ của tôi**, upload PDF/DOCX, kiểm tra và xác nhận lưu.
3. Trở lại **Tìm việc**, chọn job trong danh sách; chờ phân tích và Matching.
4. Mở tab **Yêu cầu đã phân tích** để đối chiếu JD; xem các nhóm điểm/gaps bên cạnh.
5. Chọn job khác, thử search/filter/lưu việc. **Refresh tin tuyển dụng** chỉ lấy
   dữ liệu nguồn, không gọi Qwen hàng loạt. Có thể thêm URL hoặc JD text riêng.

Dashboard API bổ sung dưới `/api/dashboard`: bootstrap/search, nhập job,
`POST /jobs/sync`, đọc job, `POST /jobs/{posting_id}/evaluate`,
`POST /jobs/{posting_id}/refresh`, `PATCH /jobs/{posting_id}/saved`.
Posting ID và analysis Job ID là hai đối tượng khác nhau; frontend dùng evaluate
để backend điều phối chúng. Các API Profile/JD/Matching cũ vẫn hoạt động.

## Mốc ngày 1 — T01–T04

Đã triển khai và kiểm chứng extraction PDF/DOCX → JSON bảy nhóm → confirmation →
lưu/đọc lại bằng Qwen thật. Có giao diện React tối thiểu để upload, kiểm tra JSON và
xác nhận. Đây chưa phải frontend đầy đủ của ngày 5 hoặc hệ thống năm Agent.

- Báo cáo tests, readiness, file thay đổi và giới hạn: [docs/demo_evidence.md](docs/demo_evidence.md).
- Contracts đã chốt: [docs/day1_contracts.md](docs/day1_contracts.md).
- Backend đọc config từ biến môi trường, **không tự đọc `.env`**. Xem `.env.example`;
  không ghi đè `.env` chứa secrets.

### Chạy bản kiểm tra cùng frontend

Trên máy hiện tại Node/Homebrew thiếu `libllhttp.9.3.dylib`; Bun sẵn có đã được dùng
để build Vite, không sửa Node hệ thống. Không cần tạo Conda environment mới.

```bash
conda activate kltn
cd /Users/nguyenngocanh/Downloads/Documents/KLTN
docker compose -f docker-compose.preflight.yml up -d --pull never db
KLTN_STORAGE=postgres DATABASE_URL=postgresql://kltn_demo:local-preflight-only@127.0.0.1:55432/kltn_demo python -B -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8013
```

Nếu chưa có frontend build, chạy ở terminal khác:

```bash
cd /Users/nguyenngocanh/Downloads/Documents/KLTN/frontend
bun install
bun --bun run build
```

Khởi động backend sau khi build; mở `http://127.0.0.1:8013/`. API và frontend build
cùng origin. 8011/8012 là runtime cũ, không dùng để kiểm tra bản sửa mới.
Database local cần được khởi tạo theo [hướng dẫn ngày 3](docs/day3_evidence.md).

Development với Vite proxy tới backend PostgreSQL 8013:

```bash
cd /Users/nguyenngocanh/Downloads/Documents/KLTN/frontend
API_PROXY_TARGET=http://127.0.0.1:8013 bun --bun run dev --port 5173 --strictPort
```

Mở `http://127.0.0.1:5173/`. Nếu Node hoạt động bình thường, có thể dùng npm scripts;
`bun.lock` ghi lại dependency versions đã kiểm chứng trong mốc ngày 1.

### Kiểm thử và dọn file

Theo yêu cầu làm gọn project, các file test bổ sung và script kiểm thử trình duyệt
đã được xóa. Giữ hai file test ban đầu `test_profile_agent.py`, `test_jd_agent.py`.
Số liệu kiểm thử trong các báo cáo là kết quả lịch sử trước khi dọn, không phải
số test còn lại trong repository hiện tại.

```bash
conda activate kltn
python -B -m unittest discover -s backend/tests -t . -v
```

Thử chức năng thực tế tại http://127.0.0.1:5173/: xác nhận hồ sơ → chọn công việc →
Matching → Update Profile hoặc Optimize CV → duyệt và tải PDF.

### PostgreSQL readiness

```bash
docker compose -p kltn_day1 -f docker-compose.preflight.yml up -d --wait db
docker compose -p kltn_day1 -f docker-compose.preflight.yml exec -T db psql -U kltn_demo -d kltn_demo -c 'SELECT current_database(), version();'
```

Đây là database local riêng ở `127.0.0.1:55432`, volume mới, password công khai chỉ dành
cho preflight. Không dùng cấu hình này cho public deployment. Chưa chạy migrations
nghiệp vụ; Profile Agent ngày 1 vẫn lưu JSON sau confirmation. Không xóa volume để reset.

### Giới hạn ngày 1

- Draft/checkpoint vẫn ở RAM; backend restart làm mất phiên chưa xác nhận. PostgreSQL
  checkpoint và revision history thuộc ngày 3.
- File mới lưu envelope version 2 với profile, evidence, warnings và text nguồn; loader
  vẫn đọc JSON bảy nhóm cũ và không rewrite file cũ.
- Evidence là đối chiếu chuỗi và phạm vi entry, không chứng minh tính đúng ngoài đời.
  Cần người dùng kiểm tra warnings và xác nhận thông tin.
- PDF scan cần OCR; PDF password phải bỏ password trước. Layout phức tạp/textboxes
  chưa được đảm bảo. Lỗi hậu xử lý Agent 2 đã được sửa trong mốc ngày 2;
  JD phức tạp vẫn cần kiểm tra evidence và cảnh báo.
- `bge-m3` chưa được tải hoặc kiểm chứng; RAG chưa triển khai. Chưa training QLoRA.

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
