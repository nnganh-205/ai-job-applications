import React, { useEffect, useState } from 'react';
import { request } from '../services/api.js';

export default function CVWorkspace({ profileId, postingId, jobTitle, onClose }) {
  const [profiles, setProfiles] = useState([]);
  const [selectedProfile, setSelectedProfile] = useState(profileId || '');
  const [mode, setMode] = useState('generate');
  const [language, setLanguage] = useState('en');
  const [templates, setTemplates] = useState([]);
  const [template, setTemplate] = useState('ats');
  const [session, setSession] = useState(null);
  const [document, setDocument] = useState(null);
  const [preview, setPreview] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [savedSession, setSavedSession] = useState('');

  useEffect(() => {
    let alive = true;
    Promise.all([request('/api/dashboard'), request('/api/cv/templates')]).then(([data, items]) => {
      if (!alive) return;
      setProfiles(data.profiles); setTemplates(items);
      setSelectedProfile(current => current || data.active_profile_id || '');
    }).catch(error => { if (alive) setError(error.message); });
    try { setSavedSession(localStorage.getItem('kltn.cvSession') || ''); } catch { /* Optional browser storage. */ }
    return () => { alive = false; };
  }, []);

  function loaded(data) {
    setSession(data); setDocument(data.document); setTemplate(data.template); setPreview('');
    try { localStorage.setItem('kltn.cvSession', data.session_id); setSavedSession(data.session_id); } catch { /* ID only. */ }
  }
  async function run(action) {
    setBusy(true); setError('');
    try { await action(); } catch (error) { setError(error.message); }
    finally { setBusy(false); }
  }
  function begin() {
    run(async () => loaded(await request('/api/cv/sessions', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ profile_id: selectedProfile, posting_id: postingId || null, mode, language }) })));
  }
  function edit(sectionIndex, entryIndex, bulletIndex, text) {
    setDocument(current => {
      const next = structuredClone(current);
      next.sections[sectionIndex].entries[entryIndex].bullets[bulletIndex].text = text;
      return next;
    });
    setPreview('');
  }
  function apply(item) {
    const next = structuredClone(document);
    let changed = false;
    next.sections.forEach(section => section.entries.forEach(entry => entry.bullets.forEach(bullet => {
      if (bullet.source_refs.includes(item.source_ref) && bullet.text === item.original_text) { bullet.text = item.proposed_text; changed = true; }
    })));
    if (changed) { setDocument(next); setPreview(''); } else setError('Nội dung đã đổi hoặc không được chọn vào CV. Hãy kiểm tra thủ công.');
  }
  function showPreview() {
    run(async () => {
      const response = await fetch(`/api/cv/sessions/${session.session_id}/preview`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ decision: 'approve', document, template }), signal: AbortSignal.timeout(30000) });
      if (!response.ok) { const data = await response.json(); throw new Error(typeof data.detail === 'string' ? data.detail : 'Không tạo được bản xem trước.'); }
      setPreview(await response.text());
    });
  }
  const editable = session?.status === 'pending_approval';
  return <section className="cv-workspace" aria-label="Review và tạo CV">
    <div className="panel-heading"><h2>Review và tạo CV</h2>{onClose && <button className="text-button" onClick={onClose}>Đóng</button>}</div>
    <p>{jobTitle ? `CV cho công việc: ${jobTitle}` : 'Tạo CV tổng quát hoặc review hồ sơ của bạn. Chọn Optimize CV tại một công việc để tạo theo JD.'}</p>
    <p className="muted">Qwen base chọn nội dung có trong hồ sơ. Đề xuất viết lại cần bạn kiểm tra; không tự thêm kinh nghiệm hay cập nhật Master Profile.</p>
    <div className="cv-controls"><label>Hồ sơ đã xác nhận<select value={selectedProfile} disabled={busy || Boolean(profileId)} onChange={e => setSelectedProfile(e.target.value)}><option value="">Chọn hồ sơ</option>{profiles.map(p => <option key={p.profile_id} value={p.profile_id}>{p.full_name || 'Hồ sơ đã xác nhận'} · {p.profile_id.slice(0, 8)}</option>)}</select></label>
      <label>Chế độ<select value={mode} disabled={busy} onChange={e => setMode(e.target.value)}><option value="generate">Tạo CV</option><option value="review">Review CV</option></select></label>
      <label>Ngôn ngữ tiêu đề<select value={language} disabled={busy} onChange={e => setLanguage(e.target.value)}><option value="en">English</option><option value="vi">Tiếng Việt</option></select></label>
      <button onClick={begin} disabled={busy || !selectedProfile}>{busy ? 'Đang xử lý…' : 'Tạo bản nháp bằng Qwen'}</button>
      {savedSession && <button className="secondary-button" disabled={busy} onClick={() => run(async () => loaded(await request(`/api/cv/sessions/${savedSession}`)))}>Tiếp tục CV đã mở</button>}
    </div>
    {!selectedProfile && <p className="notice">Hãy upload CV hoặc tạo và xác nhận hồ sơ trong Hồ sơ của tôi trước.</p>}
    {busy && <p className="loading" role="status">Đang xử lý. Qwen local có thể cần vài phút với CV/JD dài.</p>}
    {error && <p className="error" role="alert">{error}</p>}
    {session && document && <>
      <p className="notice">{session.status === 'confirmed' ? 'CV đã được bạn xác nhận và lưu.' : session.status === 'cancelled' ? 'Đã hủy; không lưu phiên bản CV.' : 'Bản nháp chưa được lưu thành phiên bản CV chính thức.'}</p>
      <p className="muted">Nguồn hồ sơ: {document.source_profile_revision_id.slice(0, 12)}. {document.job_analysis_id ? 'Có đối chiếu JD.' : 'CV tổng quát.'} Nội dung nguồn giữ nguyên ngôn ngữ gốc.</p>
      <details open><summary>Nhận xét và đề xuất</summary>{session.review.items.length ? session.review.items.map((item, i) => <article className="cv-review-item" key={i}><p><strong>{item.reason}</strong></p><p>Gốc: {item.original_text}</p><p>Đề xuất: {item.proposed_text}</p>{editable && item.proposed_text !== item.original_text && <button disabled={busy} onClick={() => apply(item)}>Áp dụng vào bản nháp để kiểm tra</button>}</article>) : <p>Model không đưa ra đề xuất chỉnh sửa cụ thể.</p>}<ul>{[...new Set(session.warnings)].map((text, i) => <li key={i}>{text}</li>)}</ul></details>
      <label>Mẫu CV<select value={template} disabled={busy || !editable} onChange={e => { setTemplate(e.target.value); setPreview(''); }}>{templates.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}</select></label>
      <details open><summary>Chỉnh sửa nội dung CV</summary><p className="muted">Chỉ chỉnh cách diễn đạt từ nguồn đã có. Muốn bổ sung kỹ năng, công ty hoặc thành tích mới, hãy cập nhật Master Profile trước.</p>
        {document.sections.map((section, si) => <div key={section.kind}><h3>{section.heading}</h3>{section.entries.map((entry, ei) => <fieldset key={entry.source_entry_id}><legend>{entry.title}</legend>{entry.subtitle && <p>{entry.subtitle}</p>}{entry.period && <p className="muted">{entry.period}</p>}{entry.bullets.map((bullet, bi) => <label key={bullet.source_refs[0]}>Nội dung {bi + 1}<textarea rows={3} value={bullet.text} disabled={busy || !editable} onChange={e => edit(si, ei, bi, e.target.value)} /></label>)}</fieldset>)}</div>)}
      </details>
      <div className="cv-controls"><button disabled={busy || session.status === 'cancelled'} onClick={showPreview}>Xem trước</button>{editable && <><button disabled={busy} onClick={() => run(async () => loaded(await request(`/api/cv/sessions/${session.session_id}/approve`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ decision: 'approve', document, template }) })))}>Tôi đã kiểm tra — xác nhận lưu CV</button><button className="secondary-button" disabled={busy} onClick={() => run(async () => loaded(await request(`/api/cv/sessions/${session.session_id}/approve`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ decision: 'reject' }) })))}>Hủy bản nháp</button></>}{session.cv_id && <a className="cv-download" href={`/api/cv/versions/${session.cv_id}/pdf`}>Tải PDF đã xác nhận</a>}</div>
      {preview && <iframe className="cv-preview-frame" title="Xem trước CV" sandbox="" srcDoc={preview} />}
    </>}
  </section>;
}
