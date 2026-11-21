import React, { useEffect, useRef, useState } from "react";
import CVPreviewFrame from "../../components/ui/CVPreviewFrame.jsx";
const names = { basic: "Đơn giản", professional: "Chuyên nghiệp", modern: "Hiện đại", harvard: "Harvard", impressive: "Ấn tượng", ats: "ATS" };
export default function TemplatePicker({ items, selected, onSelect, disabled = false }) {
  const [category, setCategory] = useState("all");
  const [preview, setPreview] = useState(null);
  const dialog = useRef(null);
  useEffect(() => {
    if (preview) dialog.current?.showModal();
    return () => { if (dialog.current?.open) dialog.current.close(); };
  }, [preview]);
  const groups = [...new Set(items.map((item) => item.category))];
  return <section className="template-picker" aria-label="Chọn mẫu CV">
    <div className="template-categories">
      {["all", ...groups].map((group) => <button type="button" key={group} aria-pressed={category === group} className={category === group ? "selected" : "secondary-button"} onClick={() => setCategory(group)}>{names[group] || "Tất cả"}</button>)}
    </div>
    <div className="template-grid">
      {items.filter((item) => category === "all" || item.category === category).map((item) => <article className={"template-card" + (item.id === selected ? " template-selected" : "")} key={item.id}>
        <button type="button" className="template-image-button" onClick={() => setPreview(item)} aria-label={"Xem mẫu " + item.name}><img src={item.thumbnail} alt={item.name} loading="lazy" /></button>
        <div className="template-card-body"><h3>{item.name}</h3><div className="form-actions">
          <button type="button" disabled={disabled} onClick={() => onSelect(item)}>{item.id === selected ? "Dùng mẫu đang chọn" : "Dùng mẫu này"}</button>
          <button type="button" className="text-button" onClick={() => setPreview(item)}>Xem trước</button>
        </div></div>
      </article>)}
    </div>
    {preview && <dialog className="template-expanded" ref={dialog} onCancel={() => setPreview(null)} onClick={(event) => { if (event.target === event.currentTarget) setPreview(null); }} aria-label={"Xem mẫu " + preview.name}>
      <div className="panel-heading"><h2>{preview.name}</h2><button type="button" autoFocus onClick={() => setPreview(null)}>Đóng</button></div>
      <CVPreviewFrame title={preview.name} src={`/api/cv/templates/${preview.id}/preview`} pageWidth={preview.page_width} pageHeight={preview.page_height} />
      <button type="button" disabled={disabled} onClick={() => { onSelect(preview); setPreview(null); }}>Dùng mẫu này</button>
    </dialog>}
  </section>;
}
