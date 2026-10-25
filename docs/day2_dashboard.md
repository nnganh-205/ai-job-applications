# Ngày 2 — Dashboard và nguồn dữ liệu thay thế

Bổ sung cho báo cáo lịch sử `day2_evidence.md`; không bắt đầu Ngày 3.
Không cài package, tải model/dataset, chạy training hoặc thay đổi `.env`.
Profile Agent và API cũ được giữ; không ghi hồ sơ người dùng chưa xác nhận.

## Chức năng đã tích hợp

- React Recruitment Dashboard là trang chính, không có chatbot/trang JD riêng.
- Danh sách/cards, search theo title/company/JD, lọc nguồn/địa điểm/hình thức,
  lưu việc, nhập URL hoặc JD kèm URL nguồn, refresh thủ công, loading/error states.
- Chọn job: backend đọc snapshot, dùng cache hoặc gọi JD StateGraph/Qwen;
  lấy Master Profile đã xác nhận và gọi Matching Agent Python. Không upload lại CV.
- Job Details hiển thị JD đầy đủ, yêu cầu được gom heading/bullets, link nguồn,
  thời điểm lấy và giới hạn múi giờ nếu có. Evidence vẫn được giữ trong JSON.
- My Profile và Matching có điểm/dimensions, matched/partial/unknown/not_met,
  core gaps, strengths, explanations. Nhóm OR chỉ tính một lần.
- Không đủ dữ liệu hoặc quan hệ/evidence cần review: không dựng phần trăm giả.
- Update Profile/Optimize CV được vô hiệu hóa và ghi “Sắp có”, chờ Agent 4/5.

## Nguồn thật đang sử dụng

| Nguồn | Cách lấy | Giới hạn bản demo |
|---|---|---|
| Himalayas | Public search API, software engineer/country VN | 3 tin mỗi lần hết cache; vẫn phải xem giới hạn trong JD |
| Remote OK | Public JSON feed, bỏ entry điều khoản | Chọn tối đa 3 tin công nghệ; không dùng logo |
| Greenhouse | Grafana Labs board: list rồi GET detail | Tối đa 2 tin; tránh tải cả board kèm JD vượt 2 MB |
| Lever | Palantir Delta và Spotify Platform | Tối đa 2 tin/board; dữ liệu company-specific |

Lần đồng bộ đầu của lần triển khai này: 12 tin lấy được, 8 inserted, 4 unchanged,
0 errors. Lần đồng bộ thực tế tiếp theo: 12 tin, 1 inserted, 11 unchanged,
0 updated, 0 errors. Tin mới có external ID mới; không nhân bản tin cùng source ID.
Kho hiện tại: 23 postings (10 Lever, 2 Greenhouse, 4 Remote OK, 3 Himalayas,
4 nhóm JD đã lưu). Đây là snapshot tại lúc kiểm chứng, không phải số lượng cố định.

JobPosting có source_url/source_name/external_id/fetched_at, apply_url, source board,
ngày nguồn cung cấp, expiry và restrictions nếu có. Không suy đoán lương, currency,
employment type hoặc remote eligibility khi nguồn không nêu rõ. Empty country
restrictions không được hiển thị như bằng chứng mọi quốc gia đều ứng tuyển được.

JSON postings đặt trong `backend/storage/jobs/postings`; analysis và match cũ
không bị rewrite. Nội dung thay đổi có snapshot lịch sử. Dedupe theo provider,
board và external ID; chưa hợp nhất cùng một việc được đăng trên nhiều nền tảng.

Himalayas cache 24 giờ; Remote OK/Greenhouse 1 giờ; cooldown chung 30 giây.
Lỗi/429/JSON sai/response quá 2 MB giữ snapshot đã lưu, không retry vòng lặp hay
đổi proxy. Dùng transport SSRF-safe hiện có (DNS/IP pinning, redirect validation,
timeout/size limit). Không gọi Qwen khi tải danh sách hoặc đồng bộ nguồn.
Tin đã hết hạn theo expiry được ẩn và không chạy matching, không xóa lịch sử.

Himalayas applicationLink giữ nguyên; nguồn có visible backlink. Remote OK dẫn
về tin gốc và được ghi đúng tên. Bản này chạy loopback phục vụ demo cá nhân;
[điều khoản Himalayas](https://himalayas.app/terms) hạn chế phân phối lại sang job
board/aggregator khác. Cần đánh giá lại phạm vi sử dụng trước khi mở public.

## Analysis và Matching

JD analysis cache theo content hash + `jd-dashboard-v8` + model. Matching theo
profile snapshot/revision, analysis, `evidence-v3` và ngày tính. Prompt mới bỏ
ví dụ cụ thể dễ bị Qwen sao chép vào JD ngắn, cho phép skills rỗng khi nguồn
không nêu kỹ năng. Bản v8 bổ sung phục hồi các câu nêu rõ kinh nghiệm/nhiệm vụ
của ứng viên khi JD không có heading; không lấy lịch sử công ty làm kinh nghiệm
ứng viên. Không dùng lại analysis của phiên bản cũ như kết quả mới.

Các thay đổi trước đó được giữ: required/preferred/unspecified, one-of ANY,
headings career pages, kiểm tra evidence theo từng item, không lấy tùy ý năm skill
làm core. Một số JD phức tạp vẫn trả needs_review; đây là giới hạn hiện tại.
Không suy từ tests pass thành độ chính xác AI trên mọi CV/JD.

## Bằng chứng kiểm chứng

- Offline: **178 tests discovered, 171 pass, 7 live/network tests skip**, 0 failures.
- Python AST: **62 files** hợp lệ. `git diff --check`: pass.
- React build bằng `bun --bun run build`: **33 modules**, pass.
- HTTP thật: FastAPI `8011/api/dashboard` và Vite proxy `5173/api/dashboard`
  trả 200 với dữ liệu nguồn thật (22 tin tại lần probe, sau đồng bộ tiếp là 23).
- Chrome headless thật, backend riêng và storage `/private/tmp`, CV DOCX tổng hợp,
  Qwen thật: extraction, không persist trước xác nhận, explicit confirm, My Profile,
  hai job matches, requirements tab, cache, search, save/filter, reload, mobile
  390 px không overflow, không có browser exceptions/API errors: **pass**.
- Lần Chrome cuối dùng `jd-dashboard-v8`, tự phân tích hai JD khi chưa có cache
  trong kho thử: Spotify Platform Security **6,25%**, Palantir Forward Deployed AI
  Engineer **4,49%** cho cùng hồ sơ tổng hợp có Python. Các lần quay lại dùng cache
  và giữ nguyên điểm. Điểm thấp phù hợp giới hạn bằng chứng của fixture; không phải
  điểm của người dùng hoặc phép đo accuracy.
- Himalayas JD Canonical Senior Software Engineer Python/Golang/Kubernetes mới (v7):
  API + Qwen thật, HTTP 200/completed, **18,06%** cho profile tổng hợp chỉ có bằng
  chứng Python; 35,61 giây; không có warnings.
- Qwen hồi quy riêng câu “một trong…”: **1/1 pass**, 12,47 giây; giữ ba options
  unspecified trong một nhóm ANY, không phạt thiếu từng option như bắt buộc.
- Himalayas JD Askable ngắn: prompt cũ sinh Python/Docker ngoài nguồn và bị evidence
  guard chặn. Prompt v7 không còn các skill đó; HTTP 200/**insufficient_data**,
  score=null, 6,25 giây. Lần gọi lại cache analysis/matching và giữ score=null.
  Hạn chế mất câu kinh nghiệm/nhiệm vụ của v7 được xử lý ở v8 và có regression
  test headingless, bảo đảm không lấy “company has 20 years experience” làm
  số năm kinh nghiệm của ứng viên.
- Chạy lại Askable qua API/Qwen v8: HTTP 200/completed, **0%** cho profile thử chỉ
  có project Python và không có work experience; giữ đúng câu kinh nghiệm và câu
  nhiệm vụ từ nguồn, không sinh Python/Docker thành yêu cầu, minimum_years=null,
  3,41 giây, 0 warnings. Gọi lại dùng cả hai cache và giữ nguyên điểm. Đây là mức
  bằng chứng cho yêu cầu kinh nghiệm chung, không phải khẳng định ứng viên không
  có năng lực. Kết quả nằm trong artifact `feed-live-result.json`.

Hồ sơ và matching thử được lưu ở thư mục tạm, tự dọn. Kho Master Profile chính
vẫn chưa có profile được xác nhận tại lúc kiểm chứng; không tự đưa CV cá nhân
trong hội thoại vào storage. Analysis của public JD có thể được cache ở kho jobs.
Artifacts test (gitignored): `output/evaluation/dashboard/browser-result.json`
và `dashboard-desktop.png`. Hai ca Chrome là so sánh điểm trên dữ liệu thật với
fixture đơn giản, chưa phải đánh giá độc lập bởi chuyên gia tuyển dụng.

## File/module liên quan

- Backend: `services/job_importer.py`, `dashboard_service.py`, `job_fetcher.py`;
  `api/dashboard.py`; `schemas/dashboard.py`; `db/job_posting_repository.py`.
- AI: tái sử dụng `jd_workflow.py`, `jd_agent.py`, `matching_agent.py`;
  sửa giới hạn prompt trong `ai/prompts/jd_prompt.py`.
- Frontend: `pages/Dashboard.jsx`; JobCard, JobDetail, MyProfilePanel,
  MatchingPanel, SearchFilters; API client hiện có.
- Tests: `test_job_feeds.py`, `test_dashboard.py`, `run_dashboard_browser.py`,
  `frontend/scripts/check-dashboard.mjs`; hồi quy Agent 1/2/Matching hiện có.
- Hướng dẫn: README, `day2_matching.md` và báo cáo này.

## Chạy và kiểm tra trên máy

```bash
conda activate kltn
python -B -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8011
```

Terminal khác:

```bash
cd frontend
API_PROXY_TARGET=http://127.0.0.1:8011 bun --bun run dev --port 5173 --strictPort
```

Mở `http://127.0.0.1:5173/`. Upload CV → kiểm tra → xác nhận trong Hồ sơ của tôi,
trở lại Tìm việc, chọn job và đợi Qwen. Có thể dùng filter source_name để kiểm tra
từng nguồn. Refresh không vượt TTL; lần xem JD đầu tiên có thể mất vài phút.
Mở `http://127.0.0.1:8011/` để dùng frontend đã build cùng backend.

## Mốc tiếp theo sau khi duyệt Ngày 2

Ngày 3: PostgreSQL và persistent checkpoint, Agent 4 + human approval/chat profile,
kết nối Update Profile và chấm lại. Ngày 4: Agent 5 base Qwen, CVDocument/templates/
PDF, nút Optimize CV, chuẩn bị QLoRA. Ngày 5: hoàn thiện workspace/editor/preview,
QLoRA pilot nếu đủ điều kiện. Ngày 6: saved jobs/application status, RAG có nguồn,
đánh giá/export pilot. Ngày 7: E2E/restart, sửa lỗi, build và hướng dẫn demo.
Không tạo lại Dashboard, không để QLoRA chặn các Agent, vẫn giữ ngân sách tối đa
84 giờ của kế hoạch; chưa tuyên bố hệ thống năm Agent hoặc public deployment hoàn tất.
