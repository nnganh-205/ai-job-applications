import React, { useEffect, useRef, useState } from "react";
import Icon from "../../components/ui/Icon.jsx";

export default function ResumeDesignToolbar({
  edit,
  templates,
  busy,
  dirty,
  onChange,
  onSave,
  onExport,
  onSourceEdit,
  onHistory,
}) {
  const [open, setOpen] = useState(false);
  const modal = useRef(null);
  const settingsRef = useRef(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  useEffect(() => {
    if (!settingsOpen) return;
    const close = (e) => {
      if (e.key === "Escape" || !settingsRef.current?.contains(e.target))
        setSettingsOpen(false);
    };
    document.addEventListener("pointerdown", close);
    document.addEventListener("keydown", close);
    return () => {
      document.removeEventListener("pointerdown", close);
      document.removeEventListener("keydown", close);
    };
  }, [settingsOpen]);
  useEffect(() => {
    if (open) modal.current?.showModal();
    else modal.current?.close();
  }, [open]);
  const selected = templates.find((t) => t.id === edit.presentation.template);
  function presentation(key, value) {
    onChange((d) => {
      d.presentation[key] = value;
    });
  }
  return (
    <>
      <div
        className="cv-design-toolbar cv-design-toolbar-compact"
        aria-label="Thiết kế CV"
      >
        <div className="cv-toolbar-main">
          <button
            className="secondary-button"
            disabled={busy}
            onClick={onSourceEdit}
          >
            <Icon name="edit" size={15} />
            Chỉnh sửa CV
          </button>
          <div className="cv-toolbar-settings" ref={settingsRef}>
            <button
              className="secondary-button"
              disabled={busy}
              aria-expanded={settingsOpen}
              aria-controls="cv-design-settings"
              onClick={() => setSettingsOpen(!settingsOpen)}
            >
              <Icon name="filter" size={15} />
              Thiết kế <span aria-hidden="true">⌄</span>
            </button>
            {settingsOpen && (
              <section
                className="cv-design-settings-panel"
                id="cv-design-settings"
                aria-label="Tùy chọn thiết kế CV"
              >
                <strong>Trình bày CV</strong>
                <button
                  className="cv-toolbar-template"
                  disabled={busy}
                  onClick={() => {
                    setSettingsOpen(false);
                    setOpen(true);
                  }}
                >
                  <Icon name="grid" size={16} />
                  <span>{selected?.name || "Chọn mẫu CV"}</span>
                  <span>Đổi mẫu →</span>
                </button>
                <div className="cv-design-settings-grid">
                  <label>
                    Màu nhấn
                    <input
                      aria-label="Màu nhấn"
                      type="color"
                      value={edit.presentation.color}
                      disabled={busy}
                      onChange={(e) => presentation("color", e.target.value)}
                    />
                  </label>
                  <label>
                    Phông chữ
                    <select
                      value={edit.presentation.font}
                      disabled={busy}
                      onChange={(e) => presentation("font", e.target.value)}
                    >
                      <option value="serif">Serif</option>
                      <option value="sans">Sans serif</option>
                    </select>
                  </label>
                  <label>
                    Cỡ chữ
                    <select
                      value={edit.presentation.font_size}
                      disabled={busy}
                      onChange={(e) =>
                        presentation("font_size", Number(e.target.value))
                      }
                    >
                      {[9, 10, 11, 12].map((n) => (
                        <option key={n} value={n}>
                          {n} pt
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    Giãn dòng
                    <select
                      value={edit.presentation.line_height}
                      disabled={busy}
                      onChange={(e) =>
                        presentation("line_height", Number(e.target.value))
                      }
                    >
                      {[1.2, 1.4, 1.5, 1.7].map((n) => (
                        <option key={n} value={n}>
                          {n}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>
              </section>
            )}
          </div>
        </div>
        <div className="cv-toolbar-output">
          <button
            className="secondary-button"
            disabled={busy || dirty}
            onClick={onHistory}
            title={
              dirty
                ? "Lưu thay đổi trước khi xem lịch sử"
                : "Xem và khôi phục phiên bản cũ"
            }
          >
            Lịch sử
          </button>
          <button
            className="secondary-button"
            disabled={busy || !dirty}
            onClick={onSave}
          >
            <Icon name="check" size={15} />
            Lưu
          </button>
          <button disabled={busy} onClick={onExport}>
            <Icon name="download" size={15} />
            {busy ? "Đang xử lý…" : "Xuất PDF"}
          </button>
        </div>
      </div>
      <dialog
        className="cv-template-dialog"
        ref={modal}
        onCancel={() => setOpen(false)}
        onClose={() => setOpen(false)}
        aria-labelledby="cv-template-title"
      >
        <header>
          <div>
            <p className="eyebrow">THIẾT KẾ CỦA BẠN</p>
            <h2 id="cv-template-title">Chọn mẫu CV</h2>
            <p>Cùng thông tin của bạn, một cách trình bày mới.</p>
          </div>
          <button
            aria-label="Đóng chọn mẫu"
            className="secondary-button"
            onClick={() => setOpen(false)}
          >
            <Icon name="close" size={19} />
          </button>
        </header>
        <div className="cv-template-options">
          {templates.map((t) => (
            <button
              key={t.id}
              className={
                "cv-template-option" +
                (t.id === edit.presentation.template ? " selected" : "")
              }
              onClick={() => {
                onChange((d) => {
                  d.presentation.template = t.id;
                  d.presentation.template_version = t.version;
                  d.presentation.font = t.font;
                  d.presentation.color = t.color;
                });
                setOpen(false);
              }}
              aria-pressed={t.id === edit.presentation.template}
            >
              <img
                src={t.thumbnail}
                alt={`Bố cục mẫu ${t.name}`}
                loading="lazy"
              />
              <span>
                <strong>{t.name}</strong>
                {t.id === edit.presentation.template ? (
                  <Icon name="check" size={17} />
                ) : (
                  <small>Dùng mẫu</small>
                )}
              </span>
            </button>
          ))}
        </div>
      </dialog>
    </>
  );
}
