# Ngày 4 — Agent 5, templates và xuất PDF

## Trạng thái

Luồng CV bằng Qwen base đã implemented, unit tested, live-model tested và browser
E2E verified trong JSON storage tạm. Persistence/checkpoint/approval/PDF cũng đã
integration tested riêng bằng PostgreSQL, gồm đọc draft từ một tiến trình mới.
Website local 5173 proxy backend PostgreSQL 8013 đã nhận API CV và hai templates.
Chưa công khai Internet, không gọi đây là production-ready. Chưa training adapter.

## Cách dùng

1. Mở http://127.0.0.1:5173/ (hoặc build tại http://127.0.0.1:8013/).
2. Dùng Master Profile đã xác nhận, chọn một job có Matching hợp lệ.
3. Bấm **Optimize CV**, chọn Tạo CV hoặc Review CV, bấm Tạo bản nháp bằng Qwen.
4. Đọc nhận xét, kiểm tra các bullet, chỉnh cách diễn đạt nếu cần.
5. Chọn **ATS đơn giản** hoặc **Truyền thống**, bấm Xem trước.
6. Bấm **Tôi đã kiểm tra — xác nhận lưu CV**, sau đó Tải PDF đã xác nhận.
7. Reload, vào **Tạo CV → Tiếp tục CV đã mở** để xem lại phiên đã lưu.

Tab Tạo CV cũng tạo/review CV tổng quát, không cần JD. Không cần upload lại CV khi
chọn job. Tiêu đề có thể chọn Việt/Anh; nội dung nguồn giữ nguyên ngôn ngữ, không
được báo là đã dịch. User chỉ chỉnh bullet; thay contact/chức danh/ngày tháng hoặc
bổ sung sự kiện mới cần cập nhật Master Profile trước. CV đã lưu là bất biến;
tạo phiên mới để chỉnh sửa tiếp. LocalStorage chỉ lưu session ID.

## Hành vi thực tế và giới hạn

- Agent 5 gọi Qwen qua LLM client task `cv`, model cấu hình CV_MODEL, hiện qwen3:4b.
- Generation chọn/sắp xếp bullet có thật, có source_refs; không sinh nội dung mới
  từ kỹ năng trong JD. Review đề xuất diễn đạt riêng, không tự áp dụng vào CV.
- Server kiểm tra nguồn, original_text, số liệu và phủ định cho đề xuất. Đây là
  kiểm tra xác định có giới hạn, không phải bộ chứng minh tương đương ngữ nghĩa.
  Đề xuất viết lại và chỉnh sửa thủ công vẫn phải được người dùng đối chiếu.
- LangGraph: generate → approval interrupt → save hoặc cancelled. Hồ sơ phải đã
  xác nhận và là revision mới nhất khi bắt đầu. Preview không lưu cv_versions;
  approve mới lưu một version, không thay Master Profile. Yêu cầu lặp không tạo
  version trùng; phiên bản đã lưu không được overwrite.
- Dashboard reuse Agent 2/3 và cache hiện có. Agent 1/4 giữ graph riêng; không viết
  lại orchestration đã chạy. Luồng 5 Agent phối hợp qua confirmed profile revision
  và selected posting, không tuyên bố đã có một graph monolithic chung cho mọi intent.
- Hai template một cột, HTML escape và iframe sandbox. Font Unicode local.
- PDF text thực tế bằng PyMuPDF đã cài, không dùng LLM tạo PDF, không shell/LaTeX.
  XeLaTeX chưa có trên máy; chưa triển khai renderer LaTeX hoặc DOCX.
- PDF được render trong bộ nhớ khi tải xuống. Không tạo hàng loạt PDF/screenshot
  trong project. CV JSON đã xác nhận nằm trong PostgreSQL `cv_versions` hoặc
  JSON workflow storage khi chạy JSON mode; draft nằm trong checkpoint.

## API

- GET /api/cv/templates
- POST /api/cv/sessions: profile_id, optional posting_id, mode, language
- GET /api/cv/sessions/{session_id}
- POST /api/cv/sessions/{session_id}/preview: document/template
- POST /api/cv/sessions/{session_id}/approve: approve/reject
- GET /api/cv/versions/{cv_id}
- GET /api/cv/versions/{cv_id}/pdf

API Profile/JD/Matching/Agent 4 cũ được giữ nguyên. Không thêm migration vì generic
JSONB records hiện có đáp ứng persistence CV.

## Bằng chứng đã chạy

**Ghi chú sau nghiệm thu:** các file test bổ sung/browser runner đã được xóa theo
yêu cầu làm gọn project. Những lệnh và số liệu dưới đây ghi nhận lần kiểm thử
trước khi dọn; không phải bộ tests hiện còn trong repository.


- Full regression: **201 discovered, 190 pass, 11 opt-in skip**, 0 failure.
- Một file test mới tổng hợp `backend/tests/test_cv.py`: nguồn giả, số liệu thêm,
  metadata bị đổi, duplicate, reject, preview không lưu, approve/readback/idempotency,
  master bytes không đổi, hai template, Unicode/multi-page PDF, HTML escaping.
- Actual Qwen API: **1/1 pass, 50.707 giây**. Bản nháp → explicit approval → real PDF,
  profile gốc không đổi. Dữ liệu tổng hợp trong TemporaryDirectory, không CV cá nhân.
- Chrome + actual Qwen + public Spotify JD: **pass**. Upload/extract/confirm,
  Matching, Optimize CV, sửa bullet, chọn classic, preview, không lưu trước approve,
  đúng một CV version, PDF thật, original profile preserved, reload/resume. Search,
  save/filter, mobile width và không API/JS errors đều qua. Dùng runner cũ mở rộng,
  không tạo một bộ test/browser app mới. Artifacts nằm ở temp và đã tự dọn.
- PostgreSQL riêng `kltn_day3_test`: **1/1 pass, 0.731 giây**. New graph/connection và
  new Python process đọc pending_approval; approve → cv_versions → PDF. Qwen được
  mock trong riêng test persistence này; không gọi đó là live-model PostgreSQL E2E.
- Frontend build: **35 modules pass**. Qua cổng 5173, templates trả ats/classic;
  hồ sơ không tồn tại bị từ chối 404.

Lệnh lặp lại kiểm tra không tạo dữ liệu fixture vào kho hồ sơ thật:

```sh
conda activate kltn
python -B -m unittest discover -s backend/tests -q
RUN_LIVE_MODEL_TESTS=1 python -B -m unittest backend.tests.test_cv.CVTests.test_live_qwen_generates_grounded_cv_then_approval_exports_real_pdf -v
BROWSER_TEST_DAY4=1 python -B -m backend.tests.run_dashboard_browser
```

## Chuẩn bị QLoRA — chưa training

Đã đọc cấu trúc dataset và notebook hiện có; giữ nguyên mọi file nguồn. Các split
cũ: train 471 / validation 59 / test 59. Target dùng personal_info, projects,
awards, leadership, khác CVDocument/CVPlan runtime hiện tại. Audit train: **471
incompatible / 0 compatible** với hợp đồng CVPlan nguồn tham chiếu. Đây là kết quả
kiểm tra tương thích, không phải kết luận 471 mẫu có nội dung sai.

- `ai/training/prepare_data.py`: audit-only mặc định; export mới bằng file mode x,
  từ chối overwrite và target không tương thích. Validate CVPlan/ref/quotes, dedup,
  group split theo catalog để cùng CV không rơi vào các split khác nhau.
- `train_qlora.py`: default chỉ kiểm tra data; `--execute` mới training trên CUDA,
  `--allow-download` riêng mới cho tải base model. QLoRA NF4 + LoRA, loss chỉ tính
  answer, bỏ mẫu quá dài thay vì cắt hỏng JSON, export Hugging Face PEFT adapter và
  manifest chưa đánh giá. Không push Hub, không tự cài dependency.
- `evaluate.py`: đánh giá các prediction đã sinh thật, schema validity, grounded
  refs/quotes và selection F1 trên cùng held-out references. Không tạo kết quả AI
  giả và không thay thế đánh giá factual preservation bằng người.
- Unit test đã kiểm tra prepare/dedup/reject, metric trên fixture và training dry
  run không tạo adapter, không load model. **Chưa kiểm chứng CUDA training/export**,
  chưa chọn/pin training dependency trên Colab, chưa merge/GGUF/Ollama adapter.

Để pilot Ngày 5 có ý nghĩa cần chuẩn hóa/gán nhãn một tập mẫu đã ẩn danh sang hợp
đồng runtime, hoặc chốt adapter chỉ xử lý rewriting rồi có adapter output mapping
được đánh giá riêng. Không âm thầm đổi dataset cũ hoặc dùng schema sai để training.
Không dùng CV người dùng làm dữ liệu training khi chưa có chấp thuận riêng.

Thiết kế QLoRA theo tài liệu chính thức:
[PEFT quantization](https://huggingface.co/docs/peft/developer_guides/quantization),
[Transformers Trainer](https://huggingface.co/docs/transformers/en/main_classes/trainer).

## Files trong lượt Ngày 4

Tạo: cv_agent.py, cv_workflow.py, api/cv.py, services/cv_renderer.py,
CVWorkspace.jsx, test_cv.py, prepare_data.py, train_qlora.py, evaluate.py và báo cáo.
Sửa: schemas/cv.py, main.py, App.jsx, Dashboard.jsx, MatchingPanel.jsx, style.css,
browser runner/script và README. Không cài package, tải model/dataset hoặc chạy
training. Không sửa .env, không xóa dữ liệu, không viết lại Agent 1/2/3/4.

## Việc tiếp theo — Ngày 5

Hoàn thiện Workspace/editor, điều hướng/resume các phiên và tích hợp toàn luồng;
chuẩn bị tập data pilot tương thích, chọn môi trường Colab/GPU, chạy base baseline
và QLoRA pilot khi đủ điều kiện. Agent 5 tiếp tục hoạt động với base model dù pilot
chưa đạt. Cần đánh giá riêng chất lượng review/tailoring trên tập CV–JD gán nhãn;
không suy diễn độ chính xác từ mock, một ca Qwen hoặc một ca browser.
