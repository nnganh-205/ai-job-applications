import React, { useEffect, useRef, useState } from 'react';
import { request } from '../services/api.js';

const call = (path, body) => request(`/api/profile-sessions${path}`, body === undefined ? {} : {
  method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
});

export default function ProfileSessionPanel({ mode, profileId, postingId, profile, onProfileConfirmed, onClose }) {
  const [session, setSession] = useState(null);
  const [resumeId, setResumeId] = useState('');
  const [message, setMessage] = useState('');
  const [skills, setSkills] = useState([]);
  const [section, setSection] = useState('project');
  const [entryId, setEntryId] = useState('');
  const [entryName, setEntryName] = useState('');
  const [draftText, setDraftText] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const notified = useRef(null);

  useEffect(() => {
    try { setResumeId(localStorage.getItem(`kltn.${mode}Session`) || ''); } catch { /* IDs only. */ }
  }, [mode]);

  useEffect(() => {
    if (!session) return;
    setDraftText(session.draft_profile ? JSON.stringify(session.draft_profile, null, 2) : '');
    setMessage(''); setSkills([]); setEntryId(''); setEntryName('');
  }, [session]);

  useEffect(() => {
    if (!session) return;
    if (session.profile_id && session.profile_id !== profileId && notified.current !== session.profile_id) {
      notified.current = session.profile_id;
      onProfileConfirmed(session.profile_id);
    }
  }, [session, profileId, onProfileConfirmed]);

  async function run(action) {
    setBusy(true); setError('');
    try {
      const result = await action(); setSession(result);
      try { localStorage.setItem(`kltn.${mode}Session`, result.session_id); } catch { /* Ignore unavailable storage. */ }
      setResumeId(result.session_id);
    } catch (error) { setError(error.message); }
    finally { setBusy(false); }
  }

  const start = () => run(() => call(mode === 'update' ? '/update' : '/build', mode === 'update' ? { profile_id: profileId, posting_id: postingId } : {}));
  const resume = () => run(() => call(`/${resumeId}`));
  const send = decision => run(() => call(`/${session.session_id}/actions`, {
    action_id: session.action_id, event_id: crypto.randomUUID(), decision, message,
    target_section: section, entry_id: entryId || null, entry_name: entryName || null,
    confirmed_skills: skills, profile: mode === 'build' && decision === 'approve' ? JSON.parse(draftText) : null,
  }));
  const entries = profile?.[section] || [];
  const finished = ['completed', 'cancelled'].includes(session?.status);

  return <section className="profile-session" aria-label={mode === 'update' ? 'Agent 4 cập nhật hồ sơ' : 'Chat tạo hồ sơ'}>
    <div className="panel-heading"><h2>{mode === 'update' ? 'Update Profile · Agent 4' : 'Tạo hồ sơ qua trò chuyện'}</h2>{onClose && <button className="text-button" onClick={onClose} disabled={busy}>Đóng</button>}</div>
    <p className="muted">Câu trả lời tạo bản nháp. Chỉ nút xác nhận mới lưu hồ sơ/revision. Có thể đóng và tiếp tục phiên sau.</p>
    {!session && <div className="job-actions"><button onClick={start} disabled={busy}>{busy ? 'Đang chuẩn bị…' : 'Bắt đầu phiên mới'}</button>{resumeId && <button onClick={resume} disabled={busy}>Tiếp tục phiên đã lưu</button>}</div>}
    {error && <div className="error" role="alert"><p>{error}</p>{session && <button disabled={busy} onClick={() => run(() => call(`/${session.session_id}/retry`, {}))}>Thử lại bước đang dở</button>}</div>}
    {busy && <p className="loading" role="status">Đang xử lý bằng Qwen và lưu trạng thái phiên…</p>}
    {session && <>
      {!session.persistent_checkpoints && <p className="notice">Chế độ JSON: có thể tiếp tục sau khi tải lại trang, nhưng phiên chưa xác nhận sẽ mất nếu backend khởi động lại. PostgreSQL checkpoint chưa được bật.</p>}
      <p className="source-line">Phiên: {session.session_id}</p>
      {mode === 'update' && session.posting_id !== postingId && <p className="notice">Bạn đang tiếp tục phiên của công việc đã chọn trước đó. Các câu hỏi vẫn theo yêu cầu của công việc gốc.</p>}
      <div className="chat-messages">{session.messages.map((item, i) => <p key={i} className={item.role === 'user' ? 'user-message' : 'assistant-message'}><strong>{item.role === 'user' ? 'Bạn' : 'Trợ lý'}: </strong>{item.content}</p>)}</div>
      {session.warnings.map((warning, i) => <p key={i} className="notice">{warning}</p>)}
      {!finished && session.status === 'pending_answer' && <>
        <p><strong>{session.question}</strong></p>
        {session.target && <p className="muted">Yêu cầu đang hỏi: {session.target.label}</p>}
        <label>Thông tin thật của bạn<textarea rows={5} value={message} onChange={event => setMessage(event.target.value)} disabled={busy} /></label>
        {mode === 'update' && <>
          {session.target?.skill_options?.length > 0 && <fieldset><legend>Chỉ chọn kỹ năng bạn xác nhận đã có</legend>{session.target.skill_options.map(name => <label className="skill-confirmation" key={name}><input type="checkbox" checked={skills.includes(name)} onChange={event => setSkills(current => event.target.checked ? [...current, name] : current.filter(item => item !== name))} /> {name}</label>)}</fieldset>}
          <label>Đề xuất bổ sung vào<select value={section} onChange={event => { setSection(event.target.value); setEntryId(''); }}><option value="project">Dự án</option><option value="experience">Kinh nghiệm đã có</option><option value="skills">Kỹ năng khai báo</option></select></label>
          {section !== 'skills' && <><label>Chọn mục<select value={entryId} onChange={event => setEntryId(event.target.value)}><option value="">{section === 'project' ? 'Dự án mới' : 'Chọn kinh nghiệm đã có'}</option>{entries.map((entry, i) => <option key={entry.id || i} value={entry.id || ''}>{entry.project_name || [entry.job_title, entry.company].filter(Boolean).join(' · ') || `Mục ${i+1}`}</option>)}</select></label>{section === 'project' && !entryId && <label>Tên dự án thật<input value={entryName} onChange={event => setEntryName(event.target.value)} /></label>}</>}
        </>}
        <div className="job-actions">{mode === 'update' ? <><button onClick={() => send('yes')} disabled={busy || !message.trim()}>Có — tạo bản nháp</button><button onClick={() => send('no')} disabled={busy}>Chưa có kinh nghiệm này</button><button onClick={() => send('skip')} disabled={busy}>Bỏ qua</button></> : <button onClick={() => send('message')} disabled={busy || !message.trim()}>Gửi thông tin</button>}<button className="secondary-button" onClick={() => send('finish')} disabled={busy}>Kết thúc phiên</button></div>
      </>}
      {session.status === 'pending_approval' && <>
        <h3>Kiểm tra trước khi lưu</h3><p className="muted">{mode === 'update' ? `Đề xuất thay đổi: ${session.changed_paths.join(', ')}. Hồ sơ gốc vẫn giữ nguyên.` : 'Bạn có thể sửa JSON hoặc tiếp tục bổ sung trước khi xác nhận.'}</p>
        <textarea aria-label="Hồ sơ đề xuất" rows={16} spellCheck={false} value={draftText} onChange={event => setDraftText(event.target.value)} readOnly={mode === 'update'} disabled={busy} />
        <div className="job-actions"><button onClick={() => send('approve')} disabled={busy}>Tôi xác nhận — lưu hồ sơ</button><button className="secondary-button" onClick={() => send(mode === 'build' ? 'continue' : 'reject')} disabled={busy}>{mode === 'build' ? 'Tiếp tục bổ sung' : 'Không lưu đề xuất'}</button></div>
      </>}
      {finished && <p className="notice">{session.status === 'completed' ? 'Phiên đã hoàn thành. Chỉ các cập nhật bạn duyệt mới được lưu; Matching sẽ dùng revision mới.' : 'Phiên đã kết thúc; các đề xuất chưa duyệt không được lưu.'}</p>}
    </>}
  </section>;
}
