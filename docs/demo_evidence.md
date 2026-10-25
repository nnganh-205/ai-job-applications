# Báo cáo thực thi — ngày 1 (2026-10-19)

Phạm vi: T01–T04 trong kế hoạch 7 ngày được duyệt. Chưa bắt đầu ngày 2.

## T01 — baseline và readiness

- Baseline: 47/47 unit/integration tests pass, 0,160 giây; tests model/network vẫn mock.
- Python 3.11.15, Conda `kltn`.
- Ollama 0.40.3; model có sẵn: `qwen3:4b`.
- Qwen JSON smoke test thật: `{ready: true}`, 4,40 giây; không có dữ liệu cá nhân.
- Docker Desktop đã mở theo approval; PostgreSQL 16.15 preflight healthy.
- SQL `SELECT current_database(), version()` thành công trên `kltn_demo`.
- Database dùng volume mới `kltn_day1_day1_preflight`, chỉ loopback port 55432.
- Node/Homebrew thiếu libllhttp.9.3.dylib; không sửa/cài lại Node hệ thống.
- Bun 1.4.2 có sẵn, đã cài frontend dependencies theo approval và build thành công.
- Embedding model chưa có: `bge-m3` chưa tải, chưa gọi embedding; ghi nhận cho ngày 6.

## T02 — configuration và contracts

- Config từ process environment, không mở/ghi .env.
- Client cũ được mở rộng theo task/model; không thêm provider/framework mới.
- Giữ API paths và field names cũ; canonical contact aliases được validate.
- Pydantic contracts cho Profile/evidence, CVDocument, MatchResult, patch và workflow.
- Tests kiểm tra task selection, schema errors không lộ payload, source offsets,
  pending-action invariant và source requirements cho CV bullets.
- Requirements Python được pin theo versions đang chạy và đã test; không cài thêm
  dependency Python trong ngày 1.

## T03 — sửa Agent 1 và tương thích

- Regression tests tái hiện lỗi trước khi sửa: tên nghề thành tên người; GPA theo thứ
  tự output thay vì đúng trường; job title lấy từ công ty khác; skill group gây warning giả.
- Thu hẹp fallback tên vào header có ngữ cảnh contact; bổ sung từ loại trừ nghề nghiệp.
- GPA/job title được đối chiếu theo block institution/employer khi anchor duy nhất.
- Python gán IDs, giữ IDs khi người dùng sửa và chuẩn hóa skill names riêng.
- Evidence có offsets và quote; warnings được tính lại sau chỉnh sửa.
- DOCX giữ thứ tự paragraph/table và đọc header/footer text; PDF password được xử lý.
- Giới hạn đọc upload 5 MB + 1 byte, lỗi HTTP rõ ràng; graph chạy ở threadpool.
- JSON profile cũ đọc được mà không rewrite. Hồ sơ mới không overwrite ID đã tồn tại.

## T04 — kiểm chứng thật

Lần live đầu: English PDF pass (22,22 giây); Vietnamese DOCX thất bại kiểm tra
skills vì Python có trong nguồn nhưng chưa trả đúng skills.items. Không nới test.
Đã sửa prompt và bổ sung recovery chỉ từ section kỹ năng có nhãn, không infer từ project.

Lần live sau sửa:

| Ca tổng hợp | Kết quả | Thời gian |
|---|---|---:|
| PDF tiếng Anh | Extract → pending → confirm → file riêng → readback, pass | 17,45 s |
| DOCX tiếng Việt | Extract → pending → confirm → file riêng → readback, pass | 18,63 s |

Hai ca kiểm tra bảy nhóm, name, GPA, Python, summary có/không; file không tồn tại
trước confirm; persisted evidence quote khớp offsets. Tất cả dùng tempfile storage,
không tạo profile thử ở backend/storage/master_profiles.

- Offline suite sau sửa: 83 discovered, 81 pass, 2 live tests skip có chủ đích.
- Final suite với `RUN_LIVE_MODEL_TESTS=1`: **83/83 pass, không skip**, 42,316 giây.
  Lần cuối: English PDF 16,01 giây; Vietnamese DOCX 26,01 giây; cả hai 0 source
  warnings trên đúng hai mẫu tổng hợp. Không suy rộng thành accuracy 100%.
- Frontend: React 19.3.1, React DOM 19.3.1, Vite 7.3.7; bun.lock được tạo.
- `bun --bun run build`: thành công, 25 modules, 513 ms ở lần build kiểm chứng.
- Chrome headless với profile tạm đã render React, gọi /health và hiển thị
  “FastAPI đã kết nối”; không chỉ kiểm tra index.html có tồn tại.
- HTTP build server 8011 và Vite proxy 5173: / trả HTML 200, /health trả JSON 200,
  unknown draft trả JSON 404 qua API thật.
- Chưa tự động hóa browser upload/click confirm; luồng extract/confirm dùng TestClient
  với Qwen thật, còn browser đã kiểm tra boot/API connectivity.
- AST backend hợp lệ; git diff --check pass.
- Hash sáu dataset splits khớp manifest cũ. Notebook và code untracked cũ giữ nguyên.

## File đã tạo/sửa

Tạo: `.env.example`, `docker-compose.preflight.yml`, `backend/app/core/{__init__,config}.py`,
`backend/app/schemas/{cv,workflow}.py`, năm file tests
`test_day1_contracts.py`, `test_document_regressions.py`, `test_profile_api.py`,
`test_profile_live.py`, `test_profile_regressions.py`; `frontend/index.html`,
`frontend/bun.lock`, `frontend/src/style.css`; hai tài liệu trong docs/.

Sửa: `.gitignore`, `requirements.txt`, `README.md`; profile agent/workflow/prompt/extractor,
Ollama client, Profile API/schema/repository, document_reader, main.py;
test_profile_agent.py (fake_save nhận thêm metadata); frontend package/config,
App.jsx/main.jsx/services/api.js. Không sửa JD Agent, dataset, notebook, .env hoặc
các untracked modules cũ `ollama_service.py`, `storage/job_store.py`.

## Giới hạn và mốc tiếp theo

| Task | Trạng thái nghiệm thu ngày 1 |
|---|---|
| T01 | Baseline, Qwen, SQL preflight kiểm chứng; Node lỗi dùng Bun; embedding thiếu model được ghi nhận |
| T02 | Config/contracts và task-based client đã có tests; React/Vite build + API connectivity đạt |
| T03 | Agent 1 fixes và schema tương thích qua regression/API/legacy storage tests |
| T04 | Hai ca live Qwen + confirmation/readback đạt; final suite 83/83 pass |

- Chưa đánh giá accuracy tổng quát; hai CV tổng hợp chỉ là pilot live-model.
- Heuristic block/span không bảo đảm semantic attribution cho mọi CV, đặc biệt
  employer/institution lặp lại và layout phức tạp. Người dùng phải review.
- Checkpoint pending vẫn ở RAM; business persistence vẫn JSON. PostgreSQL mới preflight.
- Frontend hiện là trang kiểm chứng JSON, chưa phải form editor/website đầy đủ ngày 5.
- Chưa có Agent 3/4/5, RAG, rendering PDF hoặc training; không đánh dấu các module đó DONE.
- Ngày 2: T05 sửa JD retention/required/preferred/AND-OR; T06 fetch safety;
  T07 matching xác định có giải thích; T08 integration và live-model JD tests.

## Cách tái kiểm chứng

```bash
conda activate kltn
python -B -m unittest discover -s backend/tests -t . -v
RUN_LIVE_MODEL_TESTS=1 python -B -m unittest discover -s backend/tests -t . -v
```

Chỉ gắn nhãn End-to-end API verified cho extraction/confirmation đã thử; không gọi
toàn website Deployment verified hay production-ready ở mốc ngày 1.

## Sửa contact sau phản hồi ngày 1

- Prompt yêu cầu đầy đủ contact fields; không suy nơi ở từ số điện thoại/trường/công ty.
- Đọc đích hyperlink PDF/DOCX (bao gồm header và table DOCX), giữ URL trong văn bản
  trích xuất để có evidence; không truy cập các URL này.
- Recovery link cá nhân và địa chỉ có nhãn trong header/contact section; loại link
  GitHub repository, domain giả và địa chỉ công ty trong section Experience.
- Không tách dấu phẩy trong tên kỹ năng có ngoặc, tránh tạo fragments trùng lặp.
- Full suite với Qwen thật: **90/90 pass**, 40,860 giây, không skip. PDF tiếng Anh
  20,17 giây (có hyperlink LinkedIn ẩn và các trường contact chi tiết); DOCX tiếng
  Việt 20,37 giây. Cả hai kiểm chứng confirm/readback trong storage tạm và evidence.
- Đây vẫn là dữ liệu tổng hợp; chưa đối chiếu CV gốc của phản hồi người dùng.
- Backend demo localhost:8011 đã khởi động lại để nhận thay đổi. Draft chưa xác nhận
  ở RAM cần upload lại; hồ sơ đã xác nhận trên đĩa không bị chỉnh sửa.
