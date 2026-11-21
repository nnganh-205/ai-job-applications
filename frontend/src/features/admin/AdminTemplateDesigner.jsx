import React, { useEffect, useState } from 'react';
import Icon from '../../components/ui/Icon.jsx';
import CVPreviewFrame from '../../components/ui/CVPreviewFrame.jsx';
import { request } from '../../lib/api.js';
import Modal from './AdminDialog.jsx';

const labels = { summary: 'Giới thiệu', education: 'Học vấn', experience: 'Kinh nghiệm', project: 'Dự án', skills: 'Kỹ năng', certifications: 'Chứng chỉ', awards: 'Giải thưởng', references: 'Người giới thiệu', involvement: 'Hoạt động' };
const categories = { basic: 'Đơn giản', professional: 'Chuyên nghiệp', modern: 'Hiện đại', impressive: 'Ấn tượng', harvard: 'Harvard', ats: 'ATS' };
const defaultDesign = { layout: 'one-column', sidebar_position: 'left', sidebar_width: 32, header_align: 'left', heading_style: 'line', show_photo: false, photo_shape: 'circle', margin_mm: 16, section_gap: 14, main_sections: Object.keys(labels), sidebar_sections: [] };
const apiOptions = body => ({ method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });

export default function AdminTemplateDesigner({ item, onClose, onSaved }) {
  const [values, setValues] = useState(item ? { name: item.name, category: item.category, color: item.color, font: item.font, enabled: item.enabled, design: item.design } : { name: '', category: 'basic', color: '#7045b8', font: 'sans', enabled: true, design: defaultDesign });
  const [html, setHtml] = useState(''), [previewError, setPreviewError] = useState(''), [previewBusy, setPreviewBusy] = useState(false);
  const [error, setError] = useState(''), [busy, setBusy] = useState(false);
  const design = values.design;
  const payload = { ...values, base_template: null, ...(item ? { expected_revision: item.revision } : {}) };
  function field(event) { setValues(old => ({ ...old, [event.target.name]: event.target.value })); }
  function changeDesign(key, value) { setValues(old => ({ ...old, design: { ...old.design, [key]: value } })); }
  function layout(value) {
    if (value === 'one-column') setValues(old => ({ ...old, design: { ...old.design, layout: value, main_sections: [...old.design.main_sections, ...old.design.sidebar_sections], sidebar_sections: [] } }));
    else setValues(old => {
      const side = old.design.sidebar_sections.length ? old.design.sidebar_sections : ['skills', 'certifications', 'awards', 'references'];
      return { ...old, design: { ...old.design, layout: value, main_sections: old.design.main_sections.filter(key => !side.includes(key)), sidebar_sections: side } };
    });
  }
  function move(key, from, to) {
    if (from === 'main_sections' && design.main_sections.length === 1) return;
    setValues(old => ({ ...old, design: { ...old.design, [from]: old.design[from].filter(value => value !== key), [to]: [...old.design[to], key] } }));
  }
  function reorder(column, index, delta) {
    const list = [...design[column]]; [list[index], list[index + delta]] = [list[index + delta], list[index]]; changeDesign(column, list);
  }
  useEffect(() => {
    const controller = new AbortController(); setPreviewBusy(true);
    const timer = setTimeout(() => {
      request('/api/admin/templates/preview', { ...apiOptions({ ...values, name: values.name.trim().length >= 3 ? values.name : 'Mẫu CV mới', base_template: null }), signal: controller.signal })
        .then(result => { setHtml(result.html); setPreviewError(''); })
        .catch(failure => { if (failure.name !== 'AbortError') setPreviewError(failure.message); })
        .finally(() => { if (!controller.signal.aborted) setPreviewBusy(false); });
    }, 450);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [values]);
  async function submit(event) {
    event.preventDefault(); setBusy(true); setError('');
    try {
      await request('/api/admin/templates' + (item ? '/' + item.id : ''), { ...apiOptions(payload), method: item ? 'PUT' : 'POST' });
      await onSaved(item ? 'Đã cập nhật thiết kế mẫu CV.' : 'Đã thêm mẫu CV mới.');
    } catch (failure) { setError(failure.message); } finally { setBusy(false); }
  }
  return <Modal title={item ? 'Chỉnh sửa thiết kế CV' : 'Thiết kế mẫu CV mới'} onClose={onClose} busy={busy} className="crm-designer-dialog">
    <form className="crm-form crm-designer-form" onSubmit={submit}>
      <div className="crm-designer-layout"><div className="crm-designer-settings"><fieldset disabled={busy}>
        <label>Tên mẫu<input name="name" required minLength={3} maxLength={100} value={values.name} onChange={field} placeholder="Tên mẫu CV mới" /></label>
        <div className="crm-form-row"><label>Nhóm phong cách<select name="category" value={values.category} onChange={field}>{Object.entries(categories).map(([key, value]) => <option key={key} value={key}>{value}</option>)}</select></label><label>Bố cục<select value={design.layout} onChange={e => layout(e.target.value)}><option value="one-column">Một cột</option><option value="two-column">Hai cột</option></select></label></div>
        <div className="crm-form-row"><label>Màu chủ đạo<div className="crm-color-field"><input name="color" type="color" value={values.color} onChange={field} /><span>{values.color.toUpperCase()}</span></div></label><label>Phông chữ<select name="font" value={values.font} onChange={field}><option value="sans">Không chân</option><option value="serif">Có chân</option></select></label></div>
        <div className="crm-form-row"><label>Căn phần đầu<select value={design.header_align} onChange={e => changeDesign('header_align', e.target.value)}><option value="left">Bên trái</option><option value="center">Ở giữa</option></select></label><label>Kiểu tiêu đề mục<select value={design.heading_style} onChange={e => changeDesign('heading_style', e.target.value)}><option value="line">Gạch chân</option><option value="filled">Nền màu</option><option value="plain">Chữ đơn giản</option></select></label></div>
        {design.layout === 'two-column' && <div className="crm-form-row"><label>Vị trí cột phụ<select value={design.sidebar_position} onChange={e => changeDesign('sidebar_position', e.target.value)}><option value="left">Bên trái</option><option value="right">Bên phải</option></select></label><label>Độ rộng cột phụ (%)<input type="number" min={25} max={40} value={design.sidebar_width} onChange={e => changeDesign('sidebar_width', Number(e.target.value))} /></label></div>}
        <div className="crm-form-row"><label>Lề trang (mm)<input type="number" min={10} max={24} value={design.margin_mm} onChange={e => changeDesign('margin_mm', Number(e.target.value))} /></label><label>Khoảng cách mục (pt)<input type="number" min={8} max={24} value={design.section_gap} onChange={e => changeDesign('section_gap', Number(e.target.value))} /></label></div>
        <div className="crm-form-row"><label className="crm-checkbox"><input type="checkbox" checked={design.show_photo} onChange={e => changeDesign('show_photo', e.target.checked)} />Có ảnh đại diện</label>{design.show_photo && <label>Kiểu ảnh<select value={design.photo_shape} onChange={e => changeDesign('photo_shape', e.target.value)}><option value="circle">Tròn</option><option value="square">Vuông</option></select></label>}</div>
        <div className="crm-section-editor"><h3>Sắp xếp các mục</h3>{(design.layout === 'two-column' ? ['main_sections', 'sidebar_sections'] : ['main_sections']).map(column => <section className="crm-section-column" key={column}><h4>{column === 'main_sections' ? 'Cột chính' : 'Cột phụ'}</h4>{design[column].map((key, index) => <div className="crm-section-row" key={key}><span>{labels[key]}</span><button type="button" aria-label={'Đưa ' + labels[key] + ' lên'} disabled={index === 0} onClick={() => reorder(column, index, -1)}>↑</button><button type="button" aria-label={'Đưa ' + labels[key] + ' xuống'} disabled={index === design[column].length - 1} onClick={() => reorder(column, index, 1)}>↓</button>{design.layout === 'two-column' && <button type="button" disabled={column === 'main_sections' && design.main_sections.length === 1} aria-label={'Chuyển ' + labels[key] + (column === 'main_sections' ? ' sang cột phụ' : ' sang cột chính')} onClick={() => move(key, column, column === 'main_sections' ? 'sidebar_sections' : 'main_sections')}>{column === 'main_sections' ? 'Cột phụ →' : '← Cột chính'}</button>}</div>)}{!design[column].length && <p>Chưa có mục.</p>}</section>)}</div>
        <label className="crm-checkbox"><input type="checkbox" checked={values.enabled} onChange={e => setValues(old => ({ ...old, enabled: e.target.checked }))} />Hiển thị trong thư viện mẫu CV</label>
      </fieldset></div>
      <aside className="crm-designer-preview"><div className="crm-preview-heading"><h3>Xem trước</h3><span role="status">{previewBusy ? 'Đang cập nhật…' : 'Dữ liệu minh họa'}</span></div>{previewError && <p className="crm-error" role="alert">{previewError}</p>}{html && <CVPreviewFrame title="Xem trước thiết kế mẫu CV mới" srcDoc={html} />}</aside></div>
      {error && <p className="crm-error" role="alert">{error}</p>}
      <div className="crm-form-actions"><button type="button" className="crm-button secondary" onClick={onClose} disabled={busy}>Hủy</button><button className="crm-button" disabled={busy || previewBusy || !!previewError || !html}><Icon name="check" size={16} />{busy ? 'Đang lưu…' : item ? 'Lưu thiết kế' : 'Thêm mẫu CV'}</button></div>
    </form>
  </Modal>;
}
