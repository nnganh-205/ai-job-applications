import React, { useEffect, useState, useRef } from "react";
import { Link, useSearchParams } from "react-router-dom";
import Icon from "../../components/ui/Icon.jsx";
import CVPreviewFrame from "../../components/ui/CVPreviewFrame.jsx";
import { request } from "../../services/api.js";
const categories = {
  all: "Tất cả",
  basic: "Đơn giản",
  modern: "Hiện đại",
  creative: "Sáng tạo",
  academic: "Học thuật",
};
export default function TemplateGallery() {
  const [items, setItems] = useState([]),
    [error, setError] = useState(""),
    [preview, setPreview] = useState(null);
  const dialog = useRef(null);
  useEffect(() => {
    if (preview) dialog.current?.showModal();
    return () => {
      if (dialog.current?.open) dialog.current.close();
    };
  }, [preview]);
  function closePreview() {
    dialog.current?.close();
    setPreview(null);
  }
  const [params, setParams] = useSearchParams();
  const q = params.get("q") || "",
    category = params.get("category") || "all";
  useEffect(() => {
    const c = new AbortController();
    request("/api/cv/templates", { signal: c.signal })
      .then(setItems)
      .catch((e) => {
        if (e.name !== "AbortError") setError(e.message);
      });
    return () => c.abort();
  }, []);
  function filter(key, value) {
    const next = new URLSearchParams(params);
    if (value && value !== "all") next.set(key, value);
    else next.delete(key);
    setParams(next);
  }
  const visible = items.filter(
    (t) =>
      (category === "all" || t.category === category) &&
      (t.name + " " + t.description)
        .toLocaleLowerCase("vi")
        .includes(q.toLocaleLowerCase("vi")),
  );
  return (
    <main className="template-gallery">
      <div className="gallery-hero">
        <div className="gallery-heading">
          <p className="eyebrow">Bắt đầu bằng một thiết kế phù hợp</p>
          <h1>
            Nội dung của bạn.
            <br />
            Một diện mạo mới.
          </h1>
          <p>
            Sáu bố cục nguyên bản để trình bày kinh nghiệm rõ ràng. Đổi mẫu bất
            cứ lúc nào trong editor mà không mất nội dung.
          </p>
        </div>
        <div className="gallery-hero-art" aria-hidden="true">
          <img src="/templates/previews/classic.png" alt="" />
          <img src="/templates/previews/modern.png" alt="" />
          <span>
            <Icon name="check" size={14} /> Sáu thiết kế · Nội dung của bạn
          </span>
        </div>
      </div>
      <div className="gallery-controls">
        <label>
          Tìm thiết kế phù hợp
          <input
            name="template_search"
            type="search"
            placeholder="Tên hoặc phong cách mẫu…"
            value={q}
            onChange={(e) => filter("q", e.target.value)}
          />
        </label>
        <div className="template-categories" aria-label="Nhóm mẫu CV">
          {Object.entries(categories).map(([key, name]) => (
            <button
              key={key}
              aria-pressed={category === key}
              className={category === key ? "selected" : "secondary-button"}
              onClick={() => filter("category", key)}
            >
              {name}
            </button>
          ))}
        </div>
      </div>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {!error && !items.length && <p role="status">Đang tải thư viện mẫu…</p>}
      <div className="template-grid">
        {visible.map((t) => (
          <article className="template-card" key={t.id}>
            <button
              className="template-image-button"
              onClick={() => setPreview(t)}
              aria-label={"Xem mẫu " + t.name}
            >
              <img
                src={t.thumbnail}
                alt={"Bố cục CV " + t.name}
                loading="lazy"
              />
            </button>
            <div className="template-card-body">
              <div className="template-title">
                <h2>{t.name}</h2>
                <span>{t.layout === "two-column" ? "Hai cột" : "Một cột"}</span>
              </div>
              <p>{t.description}</p>
              <div className="form-actions">
                <Link
                  className="button-link"
                  to={"/workspace/resumes/new?template=" + t.id}
                >
                  Dùng mẫu này <Icon name="arrow" size={15} />
                </Link>
                <button className="text-button" onClick={() => setPreview(t)}>
                  Xem lớn
                </button>
              </div>
            </div>
          </article>
        ))}
      </div>
      {!!items.length && !visible.length && (
        <p>Không có mẫu khớp bộ lọc. Hãy thử từ khóa khác.</p>
      )}
      {preview && (
        <dialog
          ref={dialog}
          onCancel={(e) => {
            e.preventDefault();
            closePreview();
          }}
          onClick={(e) => {
            if (e.target === e.currentTarget) closePreview();
          }}
          className="template-expanded"
          aria-label={"Xem mẫu " + preview.name}
        >
          <div className="panel-heading">
            <h2>{preview.name}</h2>
            <button autoFocus onClick={closePreview}>
              Đóng xem trước
            </button>
          </div>
          <p>Nội dung minh họa, không phải hồ sơ cá nhân.</p>
          <CVPreviewFrame
            title={"Mẫu CV " + preview.name}
            src={"/api/cv/templates/" + preview.id + "/preview"}
          />
          <Link
            className="button-link"
            to={"/workspace/resumes/new?template=" + preview.id}
          >
            Tạo CV với mẫu {preview.name}
          </Link>
        </dialog>
      )}
      <section className="template-footnote">
        <h2>Thiết kế phục vụ nội dung</h2>
        <p>
          Một cột giúp trình bày gọn gàng; hai cột tạo phân cấp rõ giữa năng lực
          và kinh nghiệm. Mọi mẫu đều xuất PDF có thể trích xuất văn bản. Không
          có bố cục nào bảo đảm kết quả của mọi hệ thống ATS.
        </p>
      </section>
    </main>
  );
}
