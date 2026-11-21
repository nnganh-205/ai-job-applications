import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link, NavLink, useLocation } from 'react-router-dom';
import Icon from '../../components/ui/Icon.jsx';
import { request } from '../../lib/api.js';
import { useAuth } from '../auth/AuthContext.jsx';
import Modal from './AdminDialog.jsx';
import AdminTemplates from './AdminTemplates.jsx';

const navigation = [
  ['overview', '/admin', 'grid', 'Tổng quan'],
  ['users', '/admin/users', 'user', 'Tài khoản'],
  ['knowledge', '/admin/knowledge', 'file', 'Tài liệu'],
  ['templates', '/admin/templates', 'layers', 'Mẫu CV'],
  ['tasks', '/admin/tasks', 'chat', 'Tác vụ AI'],
  ['activity', '/admin/activity', 'clock', 'Nhật ký quản trị'],
];
const adminRequest = (path, options = {}) => request(path, { timeoutMs: 30000, ...options });
const states = { draft: 'Bản nháp', published: 'Đang sử dụng', archived: 'Đã lưu trữ' };
const taskStates = { queued: 'Đang chờ', running: 'Đang xử lý', completed: 'Hoàn thành', failed: 'Thất bại' };
const taskNames = { cv: 'Tạo CV', evaluate: 'Đối chiếu JD', assistant: 'Trợ lý AI', interview: 'Phỏng vấn' };
const actionNames = { 'admin.bootstrap': 'Khởi tạo quản trị', 'account.update': 'Cập nhật tài khoản', 'knowledge.create': 'Thêm tài liệu', 'knowledge.update': 'Sửa tài liệu', 'knowledge.status': 'Đổi trạng thái nguồn', 'task.retry': 'Thử lại tác vụ', 'template.create': 'Thêm mẫu CV', 'template.update': 'Sửa mẫu CV', 'template.delete': 'Xóa mẫu CV' };
const fmt = value => new Intl.NumberFormat('vi-VN').format(value || 0);
function when(value, full = false) { return new Date(typeof value === 'number' ? value * 1000 : value).toLocaleString('vi-VN', { day: '2-digit', month: '2-digit', ...(full ? { year: 'numeric' } : {}), hour: '2-digit', minute: '2-digit' }); }
function matches(row, query) { return Object.values(row).filter(value => typeof value === 'string').join(' ').toLocaleLowerCase('vi').includes(query.trim().toLocaleLowerCase('vi')); }
function Avatar({ name = '', small = false }) { return <span className={`crm-avatar${small ? ' small' : ''}`}>{name.trim().split(/\s+/).slice(-2).map(word => word[0]).join('').toLocaleUpperCase('vi') || 'QT'}</span>; }
function Pill({ value, children }) { return <span className={`crm-pill ${value}`}>{children || states[value] || taskStates[value] || value}</span>; }
function Empty({ children }) { return <div className="crm-empty"><Icon name="file" size={27} /><p>{children}</p></div>; }
function PanelTitle({ title, subtitle, children }) { return <div className="crm-panel-title"><div><h2>{title}</h2>{subtitle && <p>{subtitle}</p>}</div>{children}</div>; }

function UserDialog({ member, currentId, onClose, onSaved }) {
  const [role, setRole] = useState(member.role);
  const [active, setActive] = useState(member.is_active);
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const self = member.user_id === currentId;
  async function submit(event) {
    event.preventDefault(); setBusy(true); setError('');
    try {
      await adminRequest('/api/admin/users/' + member.user_id, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ role, is_active: active, ...(password ? { password } : {}) }) });
      await onSaved(password && self ? 'password' : 'saved');
    } catch (failure) { setError(failure.message); } finally { setBusy(false); }
  }
  return <Modal title="Quản lý tài khoản" onClose={onClose} busy={busy}><form className="crm-form" onSubmit={submit}>
    <div className="crm-member"><Avatar name={member.full_name} /><div><strong>{member.full_name}</strong><span>{member.email}</span></div></div>
    <label>Vai trò<select value={role} onChange={e => setRole(e.target.value)} disabled={self || busy}><option value="user">Người dùng</option><option value="admin">Quản trị viên</option></select></label>
    <label className="crm-checkbox"><input type="checkbox" checked={active} onChange={e => setActive(e.target.checked)} disabled={self || busy} />Cho phép tài khoản hoạt động</label>
    <label>Đặt lại mật khẩu<input type="password" autoComplete="new-password" minLength={12} maxLength={128} value={password} onChange={e => setPassword(e.target.value)} placeholder="Để trống nếu giữ mật khẩu hiện tại" disabled={busy} /></label>
    <p className="crm-help">Đổi quyền, khóa tài khoản hoặc đặt lại mật khẩu sẽ thu hồi các phiên đăng nhập hiện có.</p>
    {error && <p className="crm-error" role="alert">{error}</p>}
    <div className="crm-form-actions"><button type="button" className="crm-button secondary" onClick={onClose} disabled={busy}>Hủy</button><button className="crm-button" disabled={busy}>{busy ? 'Đang lưu…' : 'Lưu thay đổi'}</button></div>
  </form></Modal>;
}

function DocumentDialog({ document, upload, onClose, onSaved }) {
  const [values, setValues] = useState(document || { title: '', text: '', url: '', effective: '', status: 'draft' });
  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  function change(e) { setValues(old => ({ ...old, [e.target.name]: e.target.value })); }
  async function submit(event) {
    event.preventDefault(); setBusy(true); setError('');
    try {
      if (upload) {
        if (!file) throw new Error('Chọn tệp PDF để tiếp tục.');
        if (file.size > 10*1024*1024) throw new Error('PDF tối đa 10 MB.');
        const body = new FormData(); body.append('file', file); body.append('title', values.title); body.append('url', values.url); body.append('effective', values.effective);
        await adminRequest('/api/admin/knowledge/upload', { method: 'POST', body, timeoutMs: 120000 });
      } else {
        const body = { title: values.title, text: values.text, url: values.url, effective: values.effective, status: values.status, ...(document ? { expected_version: document.version } : {}) };
        await adminRequest('/api/admin/knowledge' + (document ? '/' + document.document_id : ''), { method: document ? 'PUT' : 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
      }
      await onSaved();
    } catch (failure) { setError(failure.message); } finally { setBusy(false); }
  }
  return <Modal title={document ? 'Chỉnh sửa tài liệu' : upload ? 'Tải tài liệu PDF' : 'Thêm tài liệu'} busy={busy} onClose={onClose}>
    <form className="crm-form" onSubmit={submit}>
      {upload && <label className="crm-upload"><Icon name="file" size={26} /><strong>{file?.name || 'Chọn tệp PDF'}</strong><span>Tối đa 10 MB · 300 trang · PDF có lớp văn bản</span><input type="file" accept="application/pdf,.pdf" required disabled={busy} onChange={e => { const next = e.target.files[0]; setFile(next); if (next && !values.title) setValues(old => ({ ...old, title: next.name.replace(/\.pdf$/i, '') })); }} /></label>}
      <label>Tên tài liệu<input name="title" value={values.title} onChange={change} required minLength={3} maxLength={200} disabled={busy} autoFocus={!upload} placeholder="Tên văn bản hoặc tài liệu hướng dẫn" /></label>
      <div className="crm-form-row"><label>Đường dẫn nguồn<input name="url" type="url" value={values.url} onChange={change} maxLength={2000} disabled={busy} placeholder="https://…" /></label><label>Ngày hiệu lực<input type="date" name="effective" value={values.effective} onChange={change} disabled={busy} /></label></div>
      {!upload && <><label>Nội dung tài liệu<textarea rows={12} name="text" value={values.text} onChange={change} required minLength={80} maxLength={500000} disabled={busy} placeholder="Nhập nội dung có nguồn rõ ràng để bổ sung vào kho tri thức…" /></label><label>Trạng thái<select name="status" value={values.status} onChange={change} disabled={busy}>{Object.entries(states).map(([id, label]) => <option key={id} value={id}>{label}</option>)}</select></label></>}
      <p className="crm-help">{upload ? 'Tài liệu tải lên được lưu thành bản nháp để bạn kiểm tra trước khi xuất bản.' : 'Chỉ tài liệu “Đang sử dụng” được đưa vào tra cứu của trợ lý.'}</p>
      {error && <p className="crm-error" role="alert">{error}</p>}
      <div className="crm-form-actions"><button type="button" className="crm-button secondary" onClick={onClose} disabled={busy}>Hủy</button><button className="crm-button" disabled={busy}>{busy ? 'Đang lưu…' : upload ? 'Tải lên và lập chỉ mục' : 'Lưu tài liệu'}</button></div>
    </form>
  </Modal>;
}

function RetrievalDialog({ onClose }) {
  const [query, setQuery] = useState('');
  const [hits, setHits] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function submit(e) {
    e.preventDefault(); setBusy(true); setError('');
    try { setHits((await adminRequest('/api/admin/knowledge/search', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ query }) })).hits); }
    catch (failure) { setError(failure.message); } finally { setBusy(false); }
  }
  return <Modal title="Kiểm tra tra cứu RAG" busy={busy} onClose={onClose}><form className="crm-form" onSubmit={submit}>
    <p className="crm-help">Xem các đoạn nguồn đang được truy xuất, không gọi mô hình AI.</p>
    <label>Câu hỏi tra cứu<input value={query} onChange={e => setQuery(e.target.value)} required minLength={2} maxLength={500} autoFocus placeholder="Nhập câu hỏi cần tìm nguồn…" disabled={busy} /></label>
    <button className="crm-button" disabled={busy}><Icon name="search" size={16} />{busy ? 'Đang tìm…' : 'Tra cứu nguồn'}</button>
    {error && <p className="crm-error" role="alert">{error}</p>}
  </form><div className="crm-retrieval-results" aria-live="polite">{hits?.length === 0 && <Empty>Chưa tìm thấy nguồn phù hợp trong các tài liệu đang sử dụng.</Empty>}{hits?.map((hit, i) => <article key={hit.id}><span className="crm-kicker">NGUỒN {i + 1}{hit.page ? ` · TRANG ${hit.page}` : ''}</span><h3>{hit.title}</h3>{hit.article && <Pill value="draft">{hit.article}</Pill>}<p>{hit.text}</p>{hit.url && <a href={hit.url} target="_blank" rel="noreferrer">Mở nguồn gốc ↗</a>}</article>)}</div></Modal>;
}

function UserTable({ items, onEdit }) {
  if (!items.length) return <Empty>Không có tài khoản phù hợp.</Empty>;
  return <div className="crm-table-scroll"><table className="crm-table"><thead><tr><th>Tài khoản</th><th>Vai trò</th><th>Trạng thái</th><th>Ngày tham gia</th><th><span className="crm-sr-only">Thao tác</span></th></tr></thead><tbody>{items.map(member => <tr key={member.user_id}>
    <td><div className="crm-member"><Avatar name={member.full_name} small /><div><strong>{member.full_name}</strong><span>{member.email}</span></div></div></td>
    <td><Pill value={member.role}>{member.role === 'admin' ? 'Quản trị viên' : 'Người dùng'}</Pill></td>
    <td><span className={`crm-dot-label ${member.is_active ? '' : 'inactive'}`}>{member.is_active ? 'Hoạt động' : 'Đã khóa'}</span></td>
    <td className="crm-muted">{when(member.created_at, true)}</td><td><button className="crm-button subtle" onClick={() => onEdit(member)}>Quản lý <Icon name="arrow" size={14} /></button></td>
  </tr>)}</tbody></table></div>;
}

export default function AdminPage() {
  const { user, logout } = useAuth();
  const location = useLocation();
  const section = navigation.find(([, path]) => path === location.pathname)?.[0];
  const title = navigation.find(([id]) => id === section)?.[3] || 'Không tìm thấy trang';
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState('');
  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState('all');
  const [modal, setModal] = useState(null);
  const [mobileNav, setMobileNav] = useState(false);
  const mounted = useRef(true);
  const controller = useRef(null);
  const load = useCallback(async () => {
    controller.current?.abort(); controller.current = new AbortController();
    setLoading(true);
    try {
      const values = await Promise.all(['overview', 'users', 'knowledge', 'tasks', 'activity'].map(path => adminRequest('/api/admin/' + path, { signal: controller.current.signal, timeoutMs: 20000 })));
      if (mounted.current) { setData(Object.fromEntries(['overview', 'users', 'knowledge', 'tasks', 'activity'].map((key, i) => [key, values[i]]))); setError(''); }
    } catch (failure) { if (mounted.current && failure.name !== 'AbortError') setError(failure.message); }
    finally { if (mounted.current) setLoading(false); }
  }, []);
  useEffect(() => { mounted.current = true; load(); return () => { mounted.current = false; controller.current?.abort(); }; }, [load]);
  useEffect(() => { const closeMenu = event => { if (event.key === 'Escape') setMobileNav(false); }; window.addEventListener('keydown', closeMenu); return () => window.removeEventListener('keydown', closeMenu); }, []);
  useEffect(() => { setQuery(''); setFilter('all'); setMobileNav(false); setNotice(''); document.title = `${title} · Quản trị`; }, [location.pathname, title]);
  async function signOut() { setBusy('logout'); try { await logout(); window.location.replace('/'); } catch (failure) { setError(failure.message); } finally { setBusy(''); } }
  async function saved(type) {
    setModal(null);
    if (type === 'password') { window.location.replace('/login?next=/admin'); return; }
    setNotice('Đã lưu thay đổi.'); await load();
  }
  async function editDocument(document) {
    setBusy(document.document_id);
    try { setModal({ type: 'document', document: await adminRequest('/api/admin/knowledge/' + document.document_id) }); }
    catch (failure) { setError(failure.message); } finally { setBusy(''); }
  }
  async function status(document, next) {
    setBusy(document.document_id); setNotice('');
    try {
      await adminRequest(`/api/admin/knowledge/${document.document_id}/status`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ status: next, expected_version: document.version }) });
      setNotice(next === 'published' ? 'Tài liệu đã được đưa vào tra cứu RAG.' : next === 'archived' ? 'Đã lưu trữ tài liệu và ngừng sử dụng khi tra cứu.' : 'Đã chuyển tài liệu về bản nháp.');
      await load();
    } catch (failure) { setError(failure.message); } finally { setBusy(''); }
  }
  async function retry(task) {
    setBusy(task.task_id);
    try { await adminRequest(`/api/admin/tasks/${task.task_id}/retry`, { method: 'POST' }); setNotice('Đã đưa tác vụ trở lại hàng chờ.'); await load(); }
    catch (failure) { setError(failure.message); } finally { setBusy(''); }
  }
  const visible = useMemo(() => {
    if (!data) return [];
    const rows = section === 'users' ? data.users : section === 'knowledge' ? data.knowledge : section === 'tasks' ? data.tasks.items : section === 'activity' ? data.activity : [];
    return rows.filter(row => matches(row, query) && (filter === 'all' || (section === 'users' ? filter === 'locked' ? !row.is_active : row.role === filter : row.status === filter)));
  }, [data, section, query, filter]);
  const quickResults = data && section === 'overview' && query.trim() ? [
    ...data.users.filter(row => matches(row, query)).slice(0, 3).map(row => ({ name: row.full_name, detail: row.email, path: '/admin/users', icon: 'user' })),
    ...data.knowledge.filter(row => matches(row, query)).slice(0, 3).map(row => ({ name: row.title, detail: states[row.status], path: '/admin/knowledge', icon: 'file' })),
  ] : null;

  return <div className="crm-shell">
    <aside id="crm-administration-nav" className={`crm-sidebar${mobileNav ? ' is-open' : ''}`} aria-label="Điều hướng quản trị">
      <Link className="crm-brand" to="/admin"><span className="crm-brand-symbol"><i /><i /></span><span>Quản trị</span></Link>
      <nav>{navigation.map(([id, path, icon, label]) => <NavLink key={id} to={path} end={id === 'overview'} onClick={() => setMobileNav(false)}><Icon name={icon} size={18} />{label}{id === 'knowledge' && data && <span className="crm-nav-count">{data.knowledge.length}</span>}{id === 'tasks' && data?.overview.tasks.failed > 0 && <span className="crm-nav-count alert">{data.overview.tasks.failed}</span>}</NavLink>)}</nav>
      <div className="crm-sidebar-bottom"><Link className="crm-back-site" to="/"><Icon name="diagonal" size={16} />Về website</Link><button type="button" className="crm-back-site" onClick={signOut} disabled={busy === 'logout'}><Icon name="arrow" size={16} />{busy === 'logout' ? 'Đang đăng xuất…' : 'Đăng xuất'}</button></div>
      <div className="crm-sidebar-account"><Avatar name={user.full_name} small /><div><strong>{user.full_name}</strong><span>Quản trị viên</span></div><Icon name="shield" size={15} /></div>
    </aside>
    {mobileNav && <button className="crm-nav-overlay" aria-label="Đóng điều hướng" onClick={() => setMobileNav(false)} />}
    <div className="crm-body">
      <header className="crm-topbar"><div className="crm-breadcrumb"><button type="button" className="crm-icon-button crm-mobile-menu" aria-label="Mở điều hướng quản trị" aria-expanded={mobileNav} aria-controls="crm-administration-nav" onClick={() => setMobileNav(!mobileNav)}><Icon name="menu" /></button><Icon name={navigation.find(([id]) => id === section)?.[2] || 'grid'} size={18} /><span>Quản trị</span><span>/</span><strong>{title}</strong></div><div className="crm-topbar-end"><Avatar name={user.full_name} small /></div></header>
      <main className="crm-main" id="page-content">
        <div className="crm-page-heading"><div><h1>{title}</h1>{section !== 'overview' && <p>{({ users: 'Quản lý quyền truy cập và trạng thái của từng tài khoản.', knowledge: 'Quản lý tài liệu được trợ lý sử dụng để trả lời.', templates: 'Thêm, chỉnh sửa và sắp xếp thư viện mẫu CV của hệ thống.', tasks: 'Theo dõi tiến độ xử lý và kiểm tra những tác vụ cần chú ý.', activity: 'Lịch sử các thay đổi được thực hiện trong trang quản trị.' })[section]}</p>}</div><button className="crm-button secondary" onClick={load} disabled={loading}><Icon name="refresh" size={16} />{loading ? 'Đang cập nhật…' : 'Làm mới'}</button></div>
        {section !== 'templates' && <div className="crm-toolbar"><label className="crm-search"><Icon name="search" size={18} /><input aria-label="Tìm kiếm trong trang quản trị" placeholder={section === 'overview' ? 'Tìm nhanh tài khoản, tài liệu…' : section === 'users' ? 'Tìm theo tên hoặc email…' : section === 'knowledge' ? 'Tìm tài liệu…' : section === 'tasks' ? 'Tìm mã tác vụ, người dùng…' : 'Tìm nội dung nhật ký…'} value={query} onChange={e => setQuery(e.target.value)} /></label><div className="crm-toolbar-actions">
          {['users', 'knowledge', 'tasks'].includes(section) && <label className="crm-filter"><Icon name="filter" size={15} /><select aria-label="Lọc danh sách" value={filter} onChange={e => setFilter(e.target.value)}><option value="all">Tất cả</option>{Object.entries(section === 'users' ? { user: 'Người dùng', admin: 'Quản trị viên', locked: 'Đã khóa' } : section === 'knowledge' ? states : taskStates).map(([id, label]) => <option key={id} value={id}>{label}</option>)}</select></label>}
          {section === 'knowledge' && <><button className="crm-button secondary" onClick={() => setModal({ type: 'search' })}><Icon name="search" size={16} />Thử tra cứu</button><button className="crm-button secondary" onClick={() => setModal({ type: 'upload' })}><Icon name="download" size={16} />Tải PDF</button><button className="crm-button" onClick={() => setModal({ type: 'document' })}><Icon name="plus" size={16} />Thêm tài liệu</button></>}
          {section === 'overview' && <span className="crm-date">{new Date().toLocaleDateString('vi-VN', { day: 'numeric', month: 'long', year: 'numeric' })}</span>}
        </div></div>}
        {error && <div className="crm-error crm-alert" role="alert">{error}<button className="crm-button subtle" onClick={load}>Thử lại</button></div>}
        {notice && <p className="crm-success" role="status"><Icon name="check" size={16} />{notice}</p>}
        {!data && !error && <div className="crm-loading" role="status">Đang tải dữ liệu quản trị…</div>}
        {quickResults && <section className="crm-panel crm-quick-results"><PanelTitle title="Kết quả tìm nhanh" />{quickResults.length ? quickResults.map((row, i) => <Link key={i} to={row.path}><Icon name={row.icon} size={18} /><div><strong>{row.name}</strong><span>{row.detail}</span></div><Icon name="arrow" size={16} /></Link>) : <Empty>Không có kết quả phù hợp.</Empty>}</section>}
        {data && section === 'overview' && <Overview data={data} onEdit={member => setModal({ type: 'user', member })} />}
        {data && section === 'templates' && <AdminTemplates refreshKey={data} />}
        {data && section === 'users' && <section className="crm-panel"><PanelTitle title="Danh sách tài khoản" subtitle={`${visible.length} tài khoản · ${data.overview.active_accounts} đang hoạt động`} /><UserTable items={visible} onEdit={member => setModal({ type: 'user', member })} /></section>}
        {data && section === 'knowledge' && <><div className="crm-knowledge-summary"><span><i />{data.overview.published} tài liệu đang sử dụng</span><span>{data.knowledge.length} tài liệu trong kho</span></div><div className="crm-board">{Object.entries(states).map(([state, label]) => <section key={state} className={`crm-column ${state}`}><h2><span><i />{label}</span><b>{visible.filter(d => d.status === state).length}</b></h2><div className="crm-column-cards" tabIndex={0} role="region" aria-label={'Danh sách tài liệu ' + label.toLocaleLowerCase('vi')}>{visible.filter(d => d.status === state).map(document => <article className="crm-source-card" key={document.document_id}><div className="crm-source-tags"><Pill value={state} /><span>{document.origin === 'builtin' ? 'Nguồn có sẵn' : document.origin === 'uploaded' ? 'PDF tải lên' : 'Văn bản'}</span></div><div className="crm-source-title"><span className="crm-document-icon"><Icon name="file" size={19} /></span><h3>{document.title}</h3></div><p>{document.effective ? `Hiệu lực từ ${document.effective.split('-').reverse().join('/')}` : 'Chưa đặt ngày hiệu lực'}</p><div className="crm-source-meta"><span>{fmt(document.chunk_count)} đoạn nguồn</span><span>v{document.version}</span></div><div className="crm-source-actions"><button className="crm-button subtle" onClick={() => editDocument(document)} disabled={busy === document.document_id}><Icon name="edit" size={14} />Chỉnh sửa</button>{document.status !== 'published' ? <button className="crm-button subtle" onClick={() => status(document, 'published')} disabled={busy === document.document_id}>Xuất bản <Icon name="arrow" size={14} /></button> : <button className="crm-button subtle" onClick={() => status(document, 'archived')} disabled={busy === document.document_id}>Lưu trữ</button>}</div>{document.status === 'archived' && <button className="crm-restore" onClick={() => status(document, 'draft')} disabled={busy === document.document_id}>Chuyển về bản nháp</button>}</article>)}{!visible.some(d => d.status === state) && <div className="crm-column-empty"><Icon name={state === 'draft' ? 'edit' : state === 'published' ? 'check' : 'file'} size={24} /><p>{state === 'draft' ? 'Chưa có tài liệu nháp' : state === 'published' ? 'Chưa có tài liệu đang sử dụng' : 'Các nguồn tạm ngừng sử dụng'}</p>{state === 'draft' && <button className="crm-button subtle" onClick={() => setModal({ type: 'document' })}><Icon name="plus" size={14} />Thêm tài liệu</button>}</div>}</div></section>)}</div></>}
        {data && section === 'tasks' && <section className="crm-panel"><PanelTitle title="Hoạt động xử lý AI" subtitle="100 tác vụ gần nhất · Chọn Làm mới để cập nhật trạng thái" />{!data.tasks.available ? <Empty>Tác vụ nền cần PostgreSQL. Hiện hệ thống đang chạy chế độ JSON.</Empty> : !visible.length ? <Empty>Chưa có tác vụ phù hợp.</Empty> : <div className="crm-table-scroll"><table className="crm-table"><thead><tr><th>Tác vụ</th><th>Tài khoản</th><th>Trạng thái</th><th>Lần chạy</th><th>Cập nhật</th><th>Thao tác</th></tr></thead><tbody>{visible.map(task => <tr key={task.task_id}><td><strong>{taskNames[task.kind] || task.kind}</strong><code className="crm-task-id">{task.task_id}</code>{task.error && <p className="crm-task-error">{task.error}</p>}</td><td><strong>{task.owner_name || 'Dữ liệu cũ'}</strong><span className="crm-table-secondary">{task.owner_email || 'Không gắn tài khoản'}</span></td><td><Pill value={task.status} /></td><td>{task.attempt}</td><td className="crm-muted">{when(task.updated_at)}</td><td>{task.status === 'failed' ? <button className="crm-button secondary" disabled={busy === task.task_id || task.owner_active === 0} onClick={() => retry(task)}><Icon name="refresh" size={14} />Thử lại</button> : '—'}</td></tr>)}</tbody></table></div>}</section>}
        {data && section === 'activity' && <section className="crm-panel"><PanelTitle title="Nhật ký thay đổi" subtitle="100 thao tác quản trị gần nhất" />{visible.length ? <div className="crm-table-scroll"><table className="crm-table"><thead><tr><th>Thao tác</th><th>Người thực hiện</th><th>Nội dung</th><th>Thời gian</th></tr></thead><tbody>{visible.map(row => <tr key={row.audit_id}><td><span className="crm-activity-action"><Icon name={row.action.startsWith('knowledge') ? 'file' : row.action.startsWith('task') ? 'chat' : 'shield'} size={17} />{actionNames[row.action] || row.action}</span></td><td>{row.actor_name || row.actor_id}</td><td>{row.detail}</td><td className="crm-muted">{when(row.created_at, true)}</td></tr>)}</tbody></table></div> : <Empty>Chưa có thao tác phù hợp.</Empty>}</section>}
        {!section && <Empty>Không tìm thấy trang quản trị. <Link to="/admin">Về tổng quan</Link></Empty>}

      </main>
    </div>
    {modal?.type === 'user' && <UserDialog member={modal.member} currentId={user.user_id} onClose={() => setModal(null)} onSaved={saved} />}
    {['document', 'upload'].includes(modal?.type) && <DocumentDialog document={modal.document} upload={modal.type === 'upload'} onClose={() => setModal(null)} onSaved={saved} />}
    {modal?.type === 'search' && <RetrievalDialog onClose={() => setModal(null)} />}
  </div>;
}

function Overview({ data, onEdit }) {
  const info = data.overview;
  const totalTasks = Object.values(info.tasks).reduce((a, b) => a + b, 0);
  const barsMax = Math.max(1, ...info.trend.map(day => day.accounts));
  return <>
    <div className="crm-metrics">{[
      ['user', 'Tổng tài khoản', info.accounts, `${info.active_accounts} đang hoạt động`, 'violet', '/admin/users'],
      ['file', 'Tài liệu', info.documents, `${info.published} tài liệu đang sử dụng`, 'blue', '/admin/knowledge'],
      ['briefcase', 'Tin tuyển dụng', info.jobs, info.tasks_available ? 'Cơ hội hiện có trong hệ thống' : 'Thống kê cần PostgreSQL', 'peach', '/jobs'],
      ['chat', 'Tác vụ AI', totalTasks, info.tasks_available ? `${info.tasks.running} đang xử lý · ${info.tasks.failed} thất bại` : 'Tác vụ nền cần PostgreSQL', 'mint', '/admin/tasks'],
    ].map(([icon, label, value, caption, color, path]) => <Link className={`crm-metric ${color}`} to={path} key={label}><div><span>{label}</span><Icon name={icon} size={20} /></div><strong>{fmt(value)}</strong><p>{caption}<Icon name="diagonal" size={15} /></p></Link>)}</div>
    <div className="crm-overview-grid">
      <section className="crm-panel crm-growth"><PanelTitle title="Tài khoản mới" subtitle="Số tài khoản được tạo trong 7 ngày gần nhất" ><span className="crm-mini-label">7 ngày</span></PanelTitle><div className="crm-chart" role="img" aria-label={info.trend.map(day => `${day.date}: ${day.accounts} tài khoản`).join('; ')}>{info.trend.map((day, i) => <div className="crm-chart-column" key={day.date}><b>{day.accounts}</b><div><span style={{ height: day.accounts ? `${Math.max(5, day.accounts/barsMax*100)}%` : '3px' }} className={i === 6 ? 'today' : ''} /></div><span>{day.date.slice(8)}/{day.date.slice(5, 7)}</span></div>)}</div></section>
      <section className="crm-panel crm-recent-users"><PanelTitle title="Tài khoản gần đây" subtitle="Những thành viên mới của không gian" ><Link to="/admin/users">Xem tất cả <Icon name="arrow" size={14} /></Link></PanelTitle><UserTable items={info.recent_accounts} onEdit={onEdit} /></section>
      <section className="crm-panel crm-recent-activity"><PanelTitle title="Hoạt động gần đây"><Link to="/admin/activity" aria-label="Xem nhật ký quản trị"><Icon name="diagonal" size={17} /></Link></PanelTitle><div className="crm-timeline">{data.activity.slice(0, 5).map(row => <div key={row.audit_id}><span className="crm-timeline-icon"><Icon name={row.action.startsWith('knowledge') ? 'file' : 'shield'} size={15} /></span><div><strong>{actionNames[row.action] || row.action}</strong><p>{row.detail}</p><span>{when(row.created_at)}</span></div></div>)}</div><div className="crm-job-count"><Icon name="briefcase" size={18} /><span><strong>{fmt(info.jobs)}</strong> tin tuyển dụng trong hệ thống</span><Link to="/jobs" aria-label="Xem tin tuyển dụng"><Icon name="arrow" size={16} /></Link></div></section>
    </div>
  </>;
}
