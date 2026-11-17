import React, { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import Icon from "../../components/ui/Icon.jsx";
import PageHeading from "../../components/ui/PageHeading.jsx";
import CVPreviewFrame from "../../components/ui/CVPreviewFrame.jsx";
import { EmptyState } from "../../components/ui/PageState.jsx";
import { request } from "../../services/api.js";
export const send = (path, body, method = "POST") =>
  request(path, {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
export default function ResumeLibrary() {
  const [items, setItems] = useState(null),
    [profiles, setProfiles] = useState([]),
    [selected, setSelected] = useState(""),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const template = params.get("template") || "classic";
  useEffect(() => {
    const c = new AbortController();
    Promise.all([
      request("/api/resumes", { signal: c.signal }),
      request("/api/profile-drafts/profiles", { signal: c.signal }),
    ])
      .then(([r, p]) => {
        if (!c.signal.aborted) {
          setItems(r);
          setProfiles(p);
        }
      })
      .catch((e) => {
        if (e.name !== "AbortError") setError(e.message);
      });
    return () => c.abort();
  }, []);
  async function create() {
    setBusy(true);
    setError("");
    try {
      const d = await send("/api/profile-drafts", {
        base_profile_id: selected || null,
      });
      navigate(
        `/workspace/resumes/new/${d.draft_id}?resumeTemplate=${encodeURIComponent(template)}`,
      );
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="resume-library">
      <PageHeading
        eyebrow="THƯ VIỆN CÁ NHÂN"
        title="Thư viện CV của bạn"
        action={
          <Link className="button-link secondary-button" to="/templates">
            <Icon name="grid" size={16} /> Khám phá mẫu CV
          </Link>
        }
      >
        Tạo CV bằng form hoặc trò chuyện với AI. Mọi bản nháp và thiết kế của
        bạn đều ở đây.
      </PageHeading>
      <div className="resume-create-methods">
        <section className="resume-method-card method-form">
          <span className="resume-method-icon">
            <Icon name="edit" size={25} />
          </span>
          <p className="resume-method-kicker">TỪNG MỤC RÕ RÀNG</p>
          <h2>Điền form tạo CV</h2>
          <p>
            Nhập thông tin theo từng phần, có hướng dẫn và ví dụ. AI giúp câu
            chữ gọn hơn từ những gì bạn đã viết.
          </p>
          <div className="resume-method-tags">
            <span>Chú thích từng ô</span>
            <span>Lưu nháp</span>
            <span>Đổi mẫu linh hoạt</span>
          </div>
          <label>
            Điền sẵn từ thông tin đã lưu
            <select
              name="profile_id"
              value={selected}
              onChange={(e) => setSelected(e.target.value)}
            >
              <option value="">Nhập mới từ đầu</option>
              {profiles.map((p) => (
                <option key={p.profile_id} value={p.profile_id}>
                  {p.full_name || "Thông tin chưa có tên"}
                </option>
              ))}
            </select>
          </label>
          <button disabled={busy} onClick={create}>
            {busy ? "Đang mở form…" : "Bắt đầu điền form"}
            <Icon name="arrow" size={16} />
          </button>
        </section>
        <section className="resume-method-card method-chat">
          <span className="resume-method-icon">
            <Icon name="spark" size={25} />
          </span>
          <p className="resume-method-kicker">BẮT ĐẦU BẰNG CÂU CHUYỆN</p>
          <h2>Chat tạo CV với AI</h2>
          <p>
            Kể về học vấn, kinh nghiệm và dự án của bạn. AI sắp xếp thông tin
            thành bản nháp để bạn xem lại trước khi tạo CV.
          </p>
          <div className="resume-method-tags">
            <span>Hội thoại tự nhiên</span>
            <span>Kiểm tra trước khi lưu</span>
          </div>
          <div className="resume-method-chat-sample">
            <Icon name="chat" size={17} />
            <span>
              “Mình là sinh viên năm cuối, đã làm một dự án nhóm bằng React…”
            </span>
          </div>
          <Link
            className="button-link"
            to={`/workspace/resumes/chat?template=${encodeURIComponent(template)}`}
          >
            Bắt đầu chat tạo CV
            <Icon name="arrow" size={16} />
          </Link>
        </section>
      </div>
      <div className="resume-import-inline">
        <Icon name="file" size={18} />
        <span>
          Đã có CV? Tải lên để điền sẵn thông tin và tiếp tục chỉnh sửa.
        </span>
        <Link
          to={`/workspace/import?resumeTemplate=${encodeURIComponent(template)}`}
        >
          Tải CV lên
          <Icon name="arrow" size={14} />
        </Link>
      </div>
      <div className="library-section-heading">
        <h2>Tất cả CV {items && <span>{items.length}</span>}</h2>
        <Link to="/workspace/assistant">
          <Icon name="spark" size={15} /> Nhờ AI rà soát CV
        </Link>
      </div>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {!items && !error && <p role="status">Đang tải thư viện…</p>}
      {items?.length === 0 && (
        <EmptyState
          title="Câu chuyện của bạn đang chờ được kể"
          action={
            <Link
              className="button-link secondary-button"
              to="/workspace/resumes/new"
            >
              Bắt đầu điền form <Icon name="arrow" size={15} />
            </Link>
          }
        >
          Tạo bản CV đầu tiên từ hồ sơ đã xác nhận. Bạn có thể đổi mẫu và điều
          chỉnh nội dung bất cứ lúc nào.
        </EmptyState>
      )}
      <div className="resume-library-grid">
        {items?.map((r) => (
          <article className="resume-card" key={r.resume_id}>
            <Link
              className="resume-card-preview"
              to={"/workspace/resumes/" + r.resume_id + "/edit"}
              aria-label={"Chỉnh sửa " + r.title}
            >
              <div className="resume-preview-paper">
                <CVPreviewFrame
                  decorative
                  title={"Xem trước " + r.title}
                  src={"/api/resumes/" + r.resume_id + "/preview"}
                />
              </div>
              <span className="resume-preview-cta">
                <Icon name="edit" size={16} /> Tiếp tục chỉnh sửa
              </span>
            </Link>
            <div className="resume-card-body">
              <div className="resume-card-title">
                <h3>{r.title}</h3>
                <span
                  className={
                    "status-pill " + (r.latest_cv_id ? "completed" : "draft")
                  }
                >
                  {r.has_editing_draft
                    ? "Đang chỉnh sửa"
                    : r.latest_cv_id
                      ? "Có bản PDF đã xuất"
                      : "CV chưa xuất PDF"}
                </span>
              </div>
              <p>
                Cập nhật {new Date(r.updated_at).toLocaleDateString("vi-VN")}
              </p>
              {r.latest_cv_id && r.published_version !== r.version && (
                <p className="muted">
                  PDF đã xuất thuộc bản trước. Mở CV và xuất lại để lấy phiên
                  bản hiện tại.
                </p>
              )}
              <div className="resume-card-actions">
                <Link to={"/workspace/resumes/" + r.resume_id + "/edit"}>
                  <Icon name="edit" size={15} /> Chỉnh sửa
                </Link>
                {r.latest_cv_id && (
                  <a href={"/api/cv/versions/" + r.latest_cv_id + "/pdf"}>
                    <Icon name="download" size={15} /> PDF đã xuất
                    {r.published_version ? ` · v${r.published_version}` : ""}
                  </a>
                )}
              </div>
            </div>
          </article>
        ))}
      </div>
    </main>
  );
}
