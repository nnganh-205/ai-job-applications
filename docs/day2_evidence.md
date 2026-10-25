# Báo cáo thực thi ngày 2 — T05–T08

Ngày kiểm chứng: 2026-10-19. Chưa bắt đầu ngày 3. Môi trường Conda `kltn`, Qwen
`qwen3:4b` qua Ollama local; không cài package, không training/tải model/dataset.

## Các task đã hoàn thành

| Task | Thay đổi thực tế | Bằng chứng |
|---|---|---|
| T05 | Giữ kết quả JD đã extract, chỉ merge phần thiếu; required/preferred theo clause và section; IDs và AND/OR; years từ evidence | Regression tests, hai JD tổng hợp, hai URL JD thật với Qwen |
| T06 | Public URL validation, IP pinning/Host/SNI, kiểm tra redirect, giới hạn nội dung/IO, inline HTML và JSON-LD | MockTransport/DNS safety tests và hai lần fetch HTTPS thật |
| T07 | Agent 3 Python xác định; weighted scoring, core cap, OR, evidence paths, years không cộng trùng, immutable results | Property/ranking regression tests, API persistence/readback |
| T08 | CV đã xác nhận → JD → Matching; React gọi API thật; reload JD/result; hồi quy Agent 1 | Live-model API integration, Chrome render, HTTP thật qua Vite/backend |

Ngày 2 tái sử dụng Profile Agent, JD Agent, hai StateGraph, Ollama client và JSON
repositories cũ. Chưa có master workflow 5 Agent; chưa có Agent 4/5. Matching là
function xác định để đưa vào workflow ngày 3, không tạo StateGraph riêng chỉ để gọi
một function.

## Kết quả tests thật

- Baseline đầu ngày 2: 90 discovered, 88 pass, 2 live tests skip có chủ đích.
- Offline sau sửa: **131 discovered, 125 pass, 6 live/network tests skip**, 0,292 s.
- Nghiệm thu cuối có Ollama và mạng: **131/131 pass, không skip**, 252,030 s.
- Python AST: 51 files hợp lệ. `git diff --check`: pass.
- Frontend build bằng Bun: 26 modules, thành công trong 407 ms.

Lệnh nghiệm thu cuối:

```bash
conda activate kltn
RUN_LIVE_MODEL_TESTS=1 RUN_PUBLIC_JOB_TESTS=1 python -B -m unittest discover -s backend/tests -t .
```

| Ca live | Đầu vào | Kết quả | Thời gian cuối |
|---|---|---|---:|
| Ngày 2 EN | CV DOCX tổng hợp + JD tiếng Anh tổng hợp | Extract → chưa xác nhận bị từ chối match → confirm → JD → match → readback/idempotency, pass | 38,42 s |
| Ngày 2 VI | CV DOCX tổng hợp + JD tiếng Việt tổng hợp | Cùng flow; kiểm tra required/preferred, minimum 2 years và OR SQL/MongoDB, pass | 52,15 s |
| Public ML | https://www.python.org/jobs/8176/ | HTTPS fetch → Qwen → LangGraph; 6 required, 0 preferred, 2 warnings cần review | 49,14 s |
| Public Backend | https://www.python.org/jobs/8174/ | HTTPS fetch → Qwen → LangGraph; Docker required, PostgreSQL/Kubernetes preferred; 4 nhóm OR; pass | 30,51 s |
| Hồi quy Profile EN | PDF tổng hợp có hyperlink ẩn | Extract/confirm/readback và contact/evidence, pass | 36,68 s |
| Hồi quy Profile VI | DOCX tổng hợp | Extract/confirm/readback và evidence, pass | 44,80 s |

Tất cả ghi thử profile/JD/match dùng temporary directories riêng. Public URL tests
chỉ đọc hai tin tuyển dụng, không crawl hoặc ghi dataset. JD live có cảnh báo vẫn
được trả status review; không che cảnh báo để đánh dấu completed.

Đây là pilot và tests tính chất, không phải phép đo accuracy/recall toàn bộ yêu cầu.
Không suy từ số tests pass thành độ chính xác AI 100%. Nội dung trang thật có thể
thay đổi hoặc hết hạn, nên public URL tests được bật riêng.

## Lỗi được tests thật phát hiện và đã sửa

- Qwen gộp `SQL or MongoDB` thành một name và không sinh OR group: tách các tên
  ngắn có connector rõ, tạo group có evidence/IDs; không tách compound phrase như
  `unit and integration testing` thành skill vô nghĩa.
- Model tự điền employment_type: kiểm tra evidence/marker và để null khi thiếu.
- Một output ban đầu có skills nhưng bỏ cả phần Nice to Have: focused extraction
  luôn merge vào output cũ; lần preferred extraction nhận đúng section riêng.
- Nhãn preferred của một câu/section lan sang requirement khác: xác định scope theo
  section + clause từ nguồn. Giữ loại ưu tiên của experience/education khi scoring.
- Bullets không có dấu chấm bị ghép với degree rồi mất skills: giữ độc lập từng
  dòng, chỉ nối những continuation rõ của legacy HTML inline.
- Range `2–3+ years` trước đây có thể lấy 3: nay lấy lower bound 2; không coi maximum
  years là minimum; không giữ số năm do model tự tạo.

## API và website đã kiểm chứng

Đang chạy local: backend/build tại http://127.0.0.1:8011/ và Vite tại
http://127.0.0.1:5173/ (proxy backend 8011).

- Chrome headless với browser profile tạm render được “Phân tích JD và Matching”
  và “FastAPI đã kết nối”. Không dùng browser profile cá nhân.
- HTTP thật trên cả hai cổng: root/health 200, missing JD 404, unconfirmed profile
  match 404, private URL analysis 400. OpenAPI có routes mới.
- `POST /api/jobs/analyze` và API Profile cũ giữ nguyên. Thêm GET JD và POST/GET match.
- Chưa tự động hóa chuỗi upload/click đầy đủ trong browser. Luồng có model đã được
  kiểm chứng qua TestClient/API; browser kiểm chứng render và API connectivity.
- Chưa triển khai public/staging, không gọi hệ thống production-ready.

Để kiểm tra thủ công:

1. Mở http://127.0.0.1:5173/ hoặc http://127.0.0.1:8011/.
2. Upload CV và kiểm tra JSON; bấm xác nhận lưu.
3. Cuộn tới “Ngày 2 · Phân tích JD và Matching”. Dán JD/nhập URL rồi phân tích.
4. Xem warnings/evidence/AND-OR. Bấm tính Match Score từ hồ sơ đã xác nhận.
5. Xem dimension scores, strengths/gaps và refs. Lưu Profile ID/Job ID để tải lại;
   có thể nhập Profile ID đã xác nhận và chọn nguồn “Mã JD đã phân tích”.

Backend đã restart để nạp code; draft RAM chưa xác nhận trước restart cần upload lại.
Profile/JD đã lưu trước đó không bị rewrite hoặc xóa.

## File tạo/sửa trong ngày 2

Tạo:

- `backend/app/ai/agents/matching_agent.py`
- `backend/app/schemas/matching.py`
- `backend/app/api/matching.py`
- `backend/app/db/match_repository.py`
- `backend/tests/test_jd_regressions.py`
- `backend/tests/test_fetch_safety.py`
- `backend/tests/test_matching.py`
- `backend/tests/test_day2_live.py`
- `backend/tests/test_job_url_live.py`
- `frontend/src/components/JobMatching.jsx`
- `docs/day2_matching.md`, `docs/day2_evidence.md`

Sửa:

- `backend/app/ai/agents/jd_agent.py`, `backend/app/ai/prompts/jd_prompt.py`
- `backend/app/schemas/job.py`, `backend/app/services/job_fetcher.py`
- `backend/app/api/jobs.py`, `backend/app/db/job_repository.py`, `backend/app/main.py`
- `backend/tests/test_jd_agent.py` (mock trả vetted IP theo contract mới và fixture
  JSON-LD có description đủ dài)
- `frontend/src/App.jsx`, `frontend/src/style.css`, `.gitignore`, `README.md`

Không sửa Agent 1/schema Profile, client Ollama, requirements, .env hay training
trong ngày 2. Hash cả sáu raw/processed dataset splits vẫn khớp manifests hiện có.
Không rewrite JSON cũ, không thay đổi Git index/commits, không chạy migrations.

## Giới hạn và ngày tiếp theo

- Công thức/aliases/domain map v1 minh bạch nhưng chưa được hiệu chỉnh bởi chuyên
  gia; cần evaluation set có nhãn. Chi tiết ở day2_matching.md.
- Extraction còn có thể thiếu kỹ năng hoặc trả phrasing khó đối chiếu. AND/OR lồng
  nhau/phủ định phức tạp/equivalent qualifications cần review, không bảo đảm tự động.
- Cảnh báo là điều kiện cần kiểm tra; mock tests không chứng minh chất lượng AI.
- Profile/JD/match vẫn JSON; checkpoint vẫn RAM. Chưa có auth public hoặc tenant
  isolation, chỉ chạy loopback demo. OS DNS timeout vẫn có giới hạn riêng.
- Ngày 3: PostgreSQL + migrations có bảo toàn JSON cũ; profile revisions; Agent 4
  đề xuất bổ sung có xác nhận; persistent interrupt/resume; tính lại Matching.

Dừng ở mốc ngày 2 để người dùng kiểm tra trước khi thực hiện ngày 3.

## Sửa sau phản hồi: phân biệt lựa chọn với bắt buộc

- Thêm unspecified_skills tương thích dữ liệu cũ; tách required/preferred/unstated
  khỏi quan hệ all/any. Parser xử lý “một trong/one of” và danh sách con, không biến
  từng lựa chọn thành bắt buộc. Matching evidence-v2 không phạt các options unstated.
- UI giữ bố cục tiêu đề/bullets và không hiện evidence; ANY hiển thị thành một bullet
  trong đúng nhóm required/preferred/unspecified.
- Offline: 141 discovered, 134 pass, 7 live tests skip, 0,314 s. Thêm 9 regression
  cases cho nhóm tùy chọn, bắt buộc, ưu tiên, sibling scope, semicolon và Matching.
- Qwen thật: ca mới one-of + hai ca API hồi quy ngày 2 đạt 3/3 trong 85,582 s.
  Ca one-of được chạy lại sau điều chỉnh scope cuối: 1/1 pass, 14,141 s; ba options
  unspecified, một ANY group, không trừ điểm thiếu từng option.
- Frontend build pass (27 modules, 406 ms); server render kiểm tra một bullet lựa
  chọn, nhãn unspecified và không rò evidence/không lặp các option riêng lẻ.
- Đối chiếu read-only JD lưu gần nhất: tìm thấy 2 one-of blocks; normalization tạo
  2 ANY groups unspecified với 3 và 2 options; bytes file gốc không đổi. Chưa suy
  rộng thành đánh giá accuracy cho toàn bộ JD.
- Backend local 8011 được nạp lại. JD đã lưu không tự rewrite; người dùng cần phân
  tích lại để nhận classification mới.
