# Ngày 3 — trạng thái thực thi và bằng chứng

**Đã mở bản PostgreSQL để thử nghiệm thật. Luồng chọn JD → Matching đã được kiểm tra trên trình duyệt với PostgreSQL; toàn bộ luồng Agent 4 trên PG vẫn cần nghiệm thu E2E.**
Người dùng đã cho phép cài dependencies. Đã cài psycopg 3.3.6, psycopg-pool 3.3.3,
langgraph-checkpoint-postgres 3.2.0 và dependency langgraph-checkpoint 4.3.0 vào Conda
`kltn`; pip check không có xung đột. Không tải model/dataset, không training hoặc sửa `.env`.

## Đã có chức năng thực tế

- Agent 4 dùng Qwen hỏi các yêu cầu chưa có bằng chứng trong Matching.
- Câu trả lời yes cần chi tiết và chọn chính xác skill đã có; OR chỉ thêm option
  người dùng chọn. Qwen chọn verbatim quotes, server kiểm tra từng quote trong câu
  trả lời. Không cho model tự viết lại thành tích, thêm số liệu hoặc kỹ năng khác.
- Bản nháp là checkpoint, không phải Master Profile. Có interrupt riêng cho trả
  lời và cho duyệt. Chỉ approve mới tạo revision đã xác nhận.
- Revision mới giữ root/parent, source evidence và lịch sử. Bản gốc không overwrite.
  Compare-and-set ngăn hai phiên ghi đè nhau. Event IDs ngăn double submit.
- Câu trả lời no nằm trong ledger riêng: không thêm Docker vào CV. Matching trả
  not_met cho mục chưa có bằng chứng đã được user xác nhận no, thay cho unknown;
  không ghi đè bằng chứng dương có trong profile. Các câu đã xác nhận không hỏi lại.
- Matching version `evidence-v4`: giữ công thức/trọng số, thêm user-confirmation
  context vào result ID để không dùng lại cache unknown sau câu trả lời no.
- Chat xây profile từ đầu dùng extraction Agent 1 hiện có trên lời người dùng;
  tiếp tục nhiều lượt, xem/sửa JSON, xác nhận rồi mới lưu. Không cần CV giả.
- React có Update Profile từ Matching, chat tạo hồ sơ trong Hồ sơ của tôi,
  review/approve/reject, resume session, history và dùng revision mới để chấm lại.
  Callback cập nhật profile ở App để đổi trang không quay về revision cũ.
- Optimize CV vẫn disabled, chờ Ngày 4; không triển khai Agent 5/training ở đây.

Phạm vi MVP của phiên Agent 4: tối đa 5 câu về kỹ năng/kinh nghiệm mỗi phiên,
có thể mở phiên kế tiếp. Mục học vấn/chứng chỉ chưa có bằng chứng giữ trong Gap
Analysis và có thông báo, không tự biến thành dự án. Tạo kinh nghiệm làm việc mới
chưa có form riêng: chỉ gắn câu trả lời vào experience đã có hoặc dự án thật do
người dùng đặt tên, hoặc nhóm skills. Chat tạo hồ sơ mới vẫn nhận đủ bảy nhóm.

## PostgreSQL: phần đã tạo và phần còn phải kiểm chứng

- PostgreSQL 16 demo local có sẵn được khởi chạy ở `127.0.0.1:55432` bằng
  docker-compose.preflight.yml, `--pull never`. Không reset/xóa volume.
- Đã chạy migration additive `backend/app/db/migrations/001_day3.sql` qua psql:
  hai schemas, ba application tables và một index được tạo thành công.
- `kltn_app.records`: JSONB cho profiles, postings, JD analyses, matches, cache,
  session metadata, events và confirmed answers. `profile_heads` và
  `profile_revisions` lưu quan hệ/head/CAS revision. Không dựng bảng riêng cho
  mọi entry experience/project/education.
- Checkpoint schema `kltn_checkpoints` đã được setup thành công. Kiểm thử PG trên
  database riêng `kltn_day3_test` đã qua: reconnect, proposal, explicit approval,
  revision bất biến và rematch. Một tiến trình Python mới cũng đọc được checkpoint
  pending_approval và đúng action_id; không phụ thuộc bộ nhớ của tiến trình tạo phiên.
- `KLTN_STORAGE=postgres` bật nhánh PG; mặc định json để không phá backend cũ/tests.
  DATABASE_URL chỉ đọc từ process environment. Lỗi kết nối không âm thầm chuyển
  sang ghi JSON. Driver thiếu được báo rõ, không tự cài.
- `import_legacy.py` là importer chỉ đọc JSON, insert-if-absent, không overwrite
  dữ liệu PG đã có, kiểm tra hash file sau import; không xóa file nguồn. Đã import
  70 bản ghi hợp lệ (0 invalid), chạy lại 0 inserted/70 existing. Kho có một hồ sơ
  đã xác nhận và 23 jobs hiển thị trên dashboard, không thêm CV giả vào ứng dụng.
- Hai dependencies đề xuất/pin trong requirements-day3.txt:
  `psycopg[binary,pool]==3.3.6`, `langgraph-checkpoint-postgres==3.2.0`.

Đã sửa lỗi migration psycopg "multiple commands into a prepared statement" bằng
`prepare=False` cho SQL migration nhiều câu. Database ứng dụng và database kiểm thử
được tách riêng, không reset/xóa volume. Chưa chạy đầy đủ browser E2E ở PG mode;
bằng chứng browser dưới đây là JSON mode. Không đánh đồng với kiểm thử PG.

## Bằng chứng kiểm thử hiện có

- Baseline đầu lượt: 178 discovered, 171 pass, 7 live/network skip.
- Sau thay đổi: **188 discovered, 179 pass, 9 skip**, 0 failures (0,795 s).
  Thêm 8 ca Agent 4/revision/chat; hai test opt-in mới là actual Qwen và PG.
- Agent 4 unit/integration: chưa approve không lưu; reject không lưu; exact quote
  sai không được áp dụng; no không thêm skill; không hỏi lại; double-submit idempotent;
  stale action/CAS 409; OR không thêm tất cả options; chat tiếp tục rồi xác nhận.
- Live Qwen API (opt-in): **1/1 pass**, 15,223 s. Qwen hỏi Docker, lấy exact quote,
  draft chưa tạo profile, approve tạo revision, Python matching tăng **50 → 100**
  trên fixture tổng hợp; chat Qwen tạo profile rồi confirm/readback. Không phải
  điểm của người dùng hay độ chính xác trên tập dữ liệu.
- Chrome thật + Qwen + public Spotify JD + CV tổng hợp, JSON mode: **pass**.
  Upload/extract/confirm → match **6,25%** → Agent 4 hỏi/nhận chi tiết → review →
  approve → một revision, giữ nguyên bytes profile gốc → rematch **10,76%** →
  reload và resume UI. Search/save/filter, requirements tab, mobile width,
  không browser exceptions/API errors đều qua. Đây là reload trong cùng backend,
  **không phải kiểm chứng resume sau backend restart**.
- React build: 34 modules, pass. Python syntax và git diff whitespace được kiểm tra.

## Dọn dữ liệu test theo yêu cầu

Đã xóa 16 file sinh ra bởi kiểm thử: 7 JSON/screenshot trong output/evaluation và
9 session/event/answer/head/revision files của fixture trình duyệt. Đã đối chiếu
session IDs và xác nhận fixture profile không thuộc kho hồ sơ người dùng trước khi
xóa. Giữ nguyên hồ sơ thật, jobs/JD, training/dataset và mã nguồn tests.
Browser runner nay ghi cả workflow storage lẫn ảnh/kết quả vào private temporary
directory và tự dọn; từ chối chạy với database ứng dụng để tránh lẫn dữ liệu.

## Thử nghiệm thật

Mở **http://127.0.0.1:8013/**: React build và FastAPI cùng nguồn, dùng PostgreSQL.
Đã kiểm tra `/`, `/health`, `/api/dashboard`, `/openapi.json` đều HTTP 200.
Vite 5173 đã chuyển proxy sang 8013; hai địa chỉ dùng cùng backend PostgreSQL.
8011 là runtime ngày 2 cũ; 8012 là JSON preview, không dùng để kiểm tra bản sửa mới.

1. Hồ sơ của tôi: chọn hồ sơ đã lưu hoặc upload CV thật, xem lại và xác nhận lưu.
2. Chọn job có JD/Matching hợp lệ, bấm Update Profile.
3. Trả lời chi tiết thật, chọn đúng skill và dự án/experience liên quan.
4. Kiểm tra đề xuất; chưa duyệt thì Master Profile không thay đổi.
5. Xác nhận lưu, xem revision và Matching được tính lại.
6. Thử Chưa có/Bỏ qua/Không lưu đề xuất; không được thêm dữ liệu đó vào CV.
7. Reload và Tiếp tục phiên đã lưu; checkpoint PG lưu trong database.

Khởi động lại bản demo (database local đã được tạo; không reset dữ liệu):

```sh
docker compose -f docker-compose.preflight.yml up -d --pull never db
conda activate kltn
KLTN_STORAGE=postgres DATABASE_URL=postgresql://kltn_demo:local-preflight-only@127.0.0.1:55432/kltn_demo python -B -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8013
```

Thông tin kết nối trên dành riêng database demo local trong compose, không dùng
cho triển khai public. Server chỉ bind loopback. Các phiên JSON chưa xác nhận
ở runtime cũ không tự chuyển thành checkpoint PG.

JD needs_review vẫn cần xử lý Agent 2; Agent 4 không bỏ guard để ép một Match Score.
Chưa công khai dịch vụ, chưa có auth nhiều người dùng, chưa gọi đây là production-ready.

## File đã tạo/sửa trong lượt Ngày 3

- DB mới: database.py, migrations/001_day3.sql, checkpoints.py,
  workflow_repository.py, profile_revision_repository.py, import_legacy.py.
- DB/API cũ mở rộng tương thích: profile_repository.py, job_repository.py,
  match_repository.py, job_posting_repository.py; main.py; api/dashboard.py,
  api/matching.py; services/dashboard_service.py, job_importer.py.
- AI/API mới: schemas/profile_update.py, ai/agents/profile_update_agent.py,
  ai/graph/profile_update_workflow.py, profile_chat_workflow.py;
  services/profile_sessions.py, profile_answers.py; api/profile_sessions.py.
- Contracts/runtime cũ: StoredProfile thêm root/parent tùy chọn; profile_workflow
  dùng checkpointer factory; Matching thêm confirmed-unmet context.
- UI: ProfileSessionPanel.jsx mới, App/Dashboard/MatchingPanel/MyProfilePanel/CSS.
- Tests: test_profile_update.py, test_profile_update_live.py, test_day3_postgres.py;
  browser runner/script có chế độ Day3 và storage/artifacts tạm riêng.
- requirements-day3.txt, .gitignore (private workflow storage), README và báo cáo này.

Giữ nguyên dữ liệu JSON/dataset/model/training code cũ. Không triển khai Ngày 4
trong lượt này. Còn cần kiểm thử trình duyệt đầy đủ trên runtime PostgreSQL trước khi nghiệm thu toàn bộ.

## Sửa lỗi Matching bị chặn bởi JD có ví dụ lồng nhau

- Nhóm dạng “A or frameworks like B, C or D” được xác thực theo source và tính
  một đơn vị OR; nhóm ví dụ con trùng lặp không làm tăng mẫu số. Không gộp qua
  mệnh đề AND hoặc câu độc lập. Quan hệ thực sự chưa rõ vẫn không tạo điểm.
- Dashboard tái xác thực nhóm trong analysis đã cache thay vì dùng cảnh báo
  lịch sử để chặn vĩnh viễn. Giữ nguyên dữ liệu JD gốc, không gọi Qwen lại khi
  nội dung không đổi. Matching `evidence-v5` tạo result ID mới cho cách nhóm đã sửa.
- Thêm bốn ca hồi quy vào hai file tests sẵn có, cập nhật một ca phản ánh hành vi
  đã sửa; không tạo file test mới. 192 discovered: 183 pass, 9 opt-in skip.
- Đối chiếu hai JD Data Platform thật với Master Profile đã xác nhận qua PG:
  cả hai completed, không còn cảnh báo quan hệ khiến điểm bị chặn. Đây là kiểm tra
  tích hợp, không phải báo cáo độ chính xác Matching trên tập đánh giá.
- Kiểm thử trình duyệt dùng Chrome profile tạm và không tạo screenshot/report
  hoặc dữ liệu CV giả trong project. Kho dữ liệu kiểm thử vẫn tách khỏi ứng dụng.

## Sửa kết nối frontend còn trỏ backend cũ

Đã tái hiện cùng JD Data Platform: 5173/8011/8012 trả needs_review, nhưng 8013
trả completed/evidence-v5. Nguyên nhân 5173 còn giữ API_PROXY_TARGET=8011 của
tiến trình Vite cũ. Đã khởi động lại đúng Vite ở 5173 với proxy 8013, đổi default
vite.config.js sang 8013 và sửa lệnh README để không tái dùng runtime cũ. Không
dừng backend JSON cũ vì có thể còn draft RAM. Không thay đổi hồ sơ hoặc JD.
