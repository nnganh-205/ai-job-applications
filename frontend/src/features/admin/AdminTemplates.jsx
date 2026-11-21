import React, { useEffect, useState } from 'react';
import Icon from '../../components/ui/Icon.jsx';
import CVPreviewFrame from '../../components/ui/CVPreviewFrame.jsx';
import { request } from '../../lib/api.js';
import Modal from './AdminDialog.jsx';
import AdminTemplateDesigner from './AdminTemplateDesigner.jsx';

const categories = { basic: 'Đơn giản', professional: 'Chuyên nghiệp', modern: 'Hiện đại', impressive: 'Ấn tượng', harvard: 'Harvard', ats: 'ATS' };
const send = (path, method, body) => request(path, { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });

function TemplateDialog({ item, bases, onClose, onSaved }) {
  const first = bases[0];
  const [values, setValues] = useState(item || { name: '', description: '', base_template: first?.id || '', category: first?.category || 'basic', color: first?.color || '#000000', font: first?.font || 'sans', enabled: true });
  const [busy, setBusy] = useState(false), [error, setError] = useState('');
  const base = bases.find(t => t.id === values.base_template) || item;
  function change(event) { setValues(old => ({ ...old, [event.target.name]: event.target.value })); }
  function changeBase(event) {
    const next = bases.find(t => t.id === event.target.value);
    setValues(old => ({ ...old, base_template: next.id, category: next.category, color: next.color, font: next.font }));
  }
  async function submit(event) {
    event.preventDefault(); setBusy(true); setError('');
    try {
      const body = Object.fromEntries(['name', 'base_template', 'category', 'color', 'font', 'enabled'].map(key => [key, values[key]]));
      if (item) body.expected_revision = item.revision;
      await send('/api/admin/templates' + (item ? '/' + item.id : ''), item ? 'PUT' : 'POST', body);
      await onSaved(item ? 'Đã cập nhật mẫu CV.' : 'Đã thêm mẫu CV vào thư viện.');
    } catch (failure) { setError(failure.message); } finally { setBusy(false); }
  }
  return <Modal title={item ? 'Chỉnh sửa mẫu CV' : 'Thêm mẫu CV'} onClose={onClose} busy={busy}><form className="crm-form" onSubmit={submit}>
    <div className="crm-template-editor">
      <div className="crm-template-fields">
        <label>Tên mẫu<input name="name" required minLength={3} maxLength={100} value={values.name} onChange={change} disabled={busy} autoFocus placeholder="Nhập tên mẫu CV" /></label>
        <label>Bố cục gốc<select name="base_template" value={values.base_template} onChange={changeBase} disabled={busy || !!item} required>{bases.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}{item && !bases.some(t => t.id === item.base_template) && <option value={item.base_template}>{item.base_template}</option>}</select></label>
        <label>Nhóm phong cách<select name="category" value={values.category} onChange={change} disabled={busy}>{Object.entries(categories).map(([id, name]) => <option key={id} value={id}>{name}</option>)}</select></label>
        <div className="crm-form-row"><label>Màu chủ đạo<div className="crm-color-field"><input name="color" type="color" value={values.color} onChange={change} disabled={busy} /><span>{values.color.toUpperCase()}</span></div></label><label>Phông chữ<select name="font" value={values.font} onChange={change} disabled={busy}><option value="sans">Không chân</option><option value="serif">Có chân</option></select></label></div>
      </div>
      <div className="crm-template-sample">{base && <img src={base.thumbnail} alt="Bố cục gốc của mẫu CV" />}<span>Bố cục gốc</span></div>
    </div>
    <label className="crm-checkbox"><input type="checkbox" checked={values.enabled} onChange={e => setValues(old => ({ ...old, enabled: e.target.checked }))} disabled={busy} />Hiển thị trong thư viện mẫu CV</label>
    {error && <p className="crm-error" role="alert">{error}</p>}
    <div className="crm-form-actions"><button type="button" className="crm-button secondary" disabled={busy} onClick={onClose}>Hủy</button><button className="crm-button" disabled={busy}>{busy ? 'Đang lưu…' : item ? 'Lưu thay đổi' : 'Thêm mẫu CV'}</button></div>
  </form></Modal>;
}

export default function AdminTemplates({ refreshKey }) {
  const [items, setItems] = useState(null), [error, setError] = useState(''), [notice, setNotice] = useState('');
  const [bases, setBases] = useState([]);
  const [query, setQuery] = useState(''), [filter, setFilter] = useState('all'), [modal, setModal] = useState(null), [busy, setBusy] = useState(false);
  const [reload, setReload] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    Promise.all(['/api/admin/templates', '/api/admin/templates/bases'].map(path => request(path, { signal: controller.signal }))).then(([rows, layouts]) => { setItems(rows); setBases(layouts); setError(''); }).catch(failure => { if (failure.name !== 'AbortError') setError(failure.message); });
    return () => controller.abort();
  }, [refreshKey, reload]);
  function saved(message) { setModal(null); setNotice(message); setReload(n => n + 1); }
  async function remove() {
    setBusy(true); setError('');
    try { await send('/api/admin/templates/' + modal.item.id, 'DELETE', { expected_revision: modal.item.revision }); saved('Đã xóa mẫu khỏi thư viện. Các CV đã tạo vẫn được giữ nguyên.'); }
    catch (failure) { setError(failure.message); setModal(null); } finally { setBusy(false); }
  }
  const visible = (items || []).filter(t => (t.name).toLocaleLowerCase('vi').includes(query.trim().toLocaleLowerCase('vi')) && (filter === 'all' || filter === 'enabled' && t.enabled || filter === 'hidden' && !t.enabled));
  return <>
    <div className="crm-toolbar"><label className="crm-search"><Icon name="search" size={18} /><input aria-label="Tìm mẫu CV" type="search" placeholder="Tìm mẫu CV…" value={query} onChange={e => setQuery(e.target.value)} /></label><div className="crm-toolbar-actions"><label className="crm-filter"><Icon name="filter" size={15} /><select aria-label="Lọc mẫu CV" value={filter} onChange={e => setFilter(e.target.value)}><option value="all">Tất cả mẫu</option><option value="enabled">Đang hiển thị</option><option value="hidden">Đang ẩn</option></select></label><button className="crm-button" disabled={!bases.length} onClick={() => setModal({ type: 'edit' })}><Icon name="plus" size={16} />Thêm mẫu CV</button></div></div>
    {error && <p className="crm-error" role="alert">{error}<button className="crm-button subtle" onClick={() => setReload(n => n + 1)}>Thử lại</button></p>}
    {notice && <p className="crm-success" role="status"><Icon name="check" size={16} />{notice}</p>}
    {items && <div className="crm-knowledge-summary"><span><i />{items.filter(t => t.enabled).length} mẫu đang hiển thị</span><span>{items.length} mẫu trong thư viện</span></div>}
    {!items && !error && <div className="crm-loading" role="status">Đang tải mẫu CV…</div>}
    {items && !visible.length && <div className="crm-panel crm-empty"><Icon name="file" size={27} /><p>Không có mẫu CV phù hợp.</p></div>}
    <div className="crm-template-grid">{visible.map(item => <article className="crm-template-card" key={item.id}>
      <button type="button" className="crm-template-cover" aria-label={'Xem trước mẫu ' + item.name} onClick={() => setModal({ type: 'preview', item })}><img src={item.thumbnail} alt={'Bố cục mẫu ' + item.name} loading="lazy" /><span className={'crm-pill ' + (item.enabled ? 'published' : 'archived')}>{item.enabled ? 'Đang hiển thị' : 'Đang ẩn'}</span></button>
      <div className="crm-template-content"><span className="crm-template-category"><i style={{ background: item.color }} />{categories[item.category]}</span><h2>{item.name}</h2><div className="crm-template-actions"><button className="crm-button subtle" onClick={() => setModal({ type: 'preview', item })} aria-label={'Xem trước ' + item.name}><Icon name="search" size={14} />Xem trước</button><button className="crm-button subtle" onClick={() => setModal({ type: 'edit', item })} aria-label={'Sửa mẫu ' + item.name}><Icon name="edit" size={14} />Sửa</button><button className="crm-button subtle crm-danger" onClick={() => setModal({ type: 'delete', item })} aria-label={'Xóa mẫu ' + item.name}><Icon name="trash" size={14} />Xóa</button></div></div>
    </article>)}</div>
    {modal?.type === 'edit' && (!modal.item || modal.item.renderer === 'designed') && <AdminTemplateDesigner item={modal.item} onClose={() => setModal(null)} onSaved={saved} />}
    {modal?.type === 'edit' && modal.item && modal.item.renderer !== 'designed' && <TemplateDialog item={modal.item} bases={bases} onClose={() => setModal(null)} onSaved={saved} />}
    {modal?.type === 'preview' && <Modal title={modal.item.name} onClose={() => setModal(null)}><div className="crm-template-preview"><CVPreviewFrame title={'Xem trước ' + modal.item.name} src={'/api/cv/templates/' + modal.item.id + '/preview'} pageWidth={modal.item.page_width} pageHeight={modal.item.page_height} /></div></Modal>}
    {modal?.type === 'delete' && <Modal title="Xóa mẫu CV" busy={busy} onClose={() => setModal(null)}><div className="crm-form"><p className="crm-delete-message">Xóa mẫu <strong>{modal.item.name}</strong> khỏi thư viện?</p><p className="crm-help">Người dùng sẽ không chọn được mẫu này khi tạo CV mới. Các CV đã tạo bằng mẫu vẫn mở và xuất PDF được.</p><div className="crm-form-actions"><button className="crm-button secondary" disabled={busy} onClick={() => setModal(null)}>Hủy</button><button className="crm-button danger" disabled={busy} onClick={remove}>{busy ? 'Đang xóa…' : 'Xóa mẫu CV'}</button></div></div></Modal>}
  </>;
}
