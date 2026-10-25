import React, { useEffect, useState } from 'react';
import { request } from './services/api.js';
import Dashboard from './pages/Dashboard.jsx';
import ProfileSessionPanel from './components/ProfileSessionPanel.jsx';
import CVWorkspace from './components/CVWorkspace.jsx';

export default function App() {
  const [view, setView] = useState('jobs');
  const [health, setHealth] = useState('Đang kiểm tra API…');
  const [file, setFile] = useState(null);
  const [draft, setDraft] = useState(null);
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [confirmed, setConfirmed] = useState(false);
  const [showChat, setShowChat] = useState(false);

  async function chatProfileSaved(id) {
    try {
      const saved = await request(`/api/profiles/${id}`);
      setDraft(saved); setText(JSON.stringify(saved.profile, null, 2)); setConfirmed(true);
    } catch (error) { setError(error.message); }
  }

  useEffect(() => {
    request('/health').then(data => setHealth(data.status === 'ok' ? 'FastAPI đã kết nối' : 'API chưa sẵn sàng')).catch(error => setHealth(error.message));
  }, []);

  async function extract(event) {
    event.preventDefault();
    if (!file) return;
    setBusy(true); setError(''); setDraft(null); setConfirmed(false);
    try {
      const body = new FormData(); body.append('file', file);
      const result = await request('/api/profiles/extract', { method: 'POST', body });
      setDraft(result); setText(JSON.stringify(result.profile, null, 2));
    } catch (error) { setError(error.message); }
    finally { setBusy(false); }
  }

  async function confirm() {
    setBusy(true); setError('');
    try {
      const profile = JSON.parse(text);
      await request(`/api/profiles/${draft.thread_id}/confirm`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ profile }),
      });
      const saved = await request(`/api/profiles/${draft.thread_id}`);
      setDraft(saved); setText(JSON.stringify(saved.profile, null, 2)); setConfirmed(true);
    } catch (error) { setError(error.message); }
    finally { setBusy(false); }
  }

  return <><header className="site-header"><a href="#" className="brand" onClick={event => { event.preventDefault(); setView('jobs'); }}>KLTN<span>Career Workspace</span></a><nav aria-label="Điều hướng chính"><button className={view === 'jobs' ? 'active' : ''} onClick={() => setView('jobs')}>Tìm việc</button><button className={view === 'profile' ? 'active' : ''} onClick={() => setView('profile')}>Hồ sơ của tôi</button><button className={view === 'cv' ? 'active' : ''} onClick={() => setView('cv')}>Tạo CV</button></nav><span className="api-status" role="status">{health}</span></header>
    {view === 'jobs' ? <main className="dashboard-shell"><Dashboard confirmedProfileId={confirmed ? draft.thread_id : null} onOpenProfile={() => setView('profile')} onProfileConfirmed={chatProfileSaved} /></main> : view === 'cv' ? <main><CVWorkspace profileId={confirmed ? draft.thread_id : null} /></main> : <main>
    <p className="eyebrow">KLTN · Mốc ngày 3</p>
    <h1>Trích xuất hồ sơ từ CV</h1>
    <p role="status">{health}</p>
    <p>Upload PDF/DOCX có văn bản, tối đa 5 MB. Qwen local trích xuất thông tin; hồ sơ chỉ được lưu sau khi bạn xác nhận.</p>
    <form onSubmit={extract}>
      <label>CV của bạn <input type="file" accept=".pdf,.docx" disabled={busy} onChange={event => setFile(event.target.files[0] || null)} /></label>
      <button disabled={!file || busy}>{busy ? 'Đang xử lý…' : 'Trích xuất bằng Qwen'}</button>
    </form>
    <button className="secondary-button" onClick={() => setShowChat(value => !value)}>Chưa có CV? Tạo hồ sơ qua trò chuyện</button>
    {showChat && <ProfileSessionPanel mode="build" onProfileConfirmed={chatProfileSaved} onClose={() => setShowChat(false)} />}
    {error && <p className="error" role="alert">{error}</p>}
    {draft && <section>
      <h2>{confirmed ? 'Master Profile đã lưu' : 'Kiểm tra bản nháp'}</h2>
      <p>Phiên: {draft.thread_id}</p>
      {draft.warnings.length > 0 && <details open><summary>Các mục cần kiểm tra ({draft.warnings.length})</summary><ul>{draft.warnings.map((warning, index) => <li key={index}>{warning}</li>)}</ul></details>}
      <label htmlFor="profile">Hồ sơ bảy nhóm — bản kiểm tra JSON ngày 1</label>
      <textarea id="profile" spellCheck={false} rows={24} value={text} disabled={busy || confirmed} onChange={event => setText(event.target.value)} />
      {!confirmed && <button type="button" disabled={busy} onClick={confirm}>Tôi đã kiểm tra — xác nhận lưu hồ sơ</button>}
      {confirmed && <p role="status">Đã xác nhận và đọc lại hồ sơ từ backend.</p>}
    </section>}
    {confirmed && <button onClick={() => setView('jobs')}>Đến Dashboard tìm việc và Matching →</button>}
    <p className="note">Hồ sơ chỉ được lưu sau khi bạn xác nhận. Chọn công việc và xem Matching tại Dashboard.</p>
  </main>}</>;
}
