import React, { useEffect, useState } from 'react';
import { request } from '../services/api.js';

export default function MyProfilePanel({ profile, profiles, profileId, onSelect, onOpenProfile }) {
  const [history, setHistory] = useState(null);
  useEffect(() => {
    setHistory(null);
    if (!profileId) return;
    const controller = new AbortController();
    request(`/api/profile-sessions/profiles/${profileId}/revisions`, {signal: controller.signal}).then(setHistory).catch(() => {});
    return () => controller.abort();
  }, [profileId]);
  return <div className="my-profile">
    <div className="panel-heading"><h2>Hồ sơ của tôi</h2><span className="analysis-badge ready">{profile ? 'Đã xác nhận' : 'Chưa có hồ sơ'}</span></div>
    {profiles.length > 1 && <label>Chọn hồ sơ đã xác nhận<select value={profileId} onChange={event => onSelect(event.target.value)}>{profiles.map(item => <option key={item.profile_id} value={item.profile_id}>{item.full_name || 'Hồ sơ không có tên'} · {item.parent_profile_id ? 'Revision' : 'Gốc'} {item.profile_id.slice(-6)}</option>)}</select></label>}
    {!profile ? <div className="empty-panel"><p>Upload CV và xác nhận Master Profile để xem mức độ phù hợp. Không cần upload lại khi đổi công việc.</p><button onClick={onOpenProfile}>Tạo / upload hồ sơ</button></div> : <>
      <h3>{profile.contact.full_name || 'Chưa có tên'}</h3>
      {profile.summary && <p className="profile-summary">{profile.summary}</p>}
      <details><summary>Kỹ năng ({profile.skills.length} nhóm)</summary>{profile.skills.length ? profile.skills.map((group, index) => <div className="profile-group" key={group.id || index}><strong>{group.group || 'Kỹ năng'}</strong><div className="pills skills">{group.items.map((skill, i) => <span key={`${skill}-${i}`}>{skill}</span>)}</div></div>) : <p className="muted">Chưa có dữ liệu.</p>}</details>
      {[
        ['Kinh nghiệm', profile.experience, item => [item.job_title, item.company].filter(Boolean).join(' · ')],
        ['Dự án', profile.project, item => item.project_name],
        ['Học vấn', profile.education, item => [item.degree, item.institution].filter(Boolean).join(' · ')],
      ].map(([title, entries, name]) => <details key={title}><summary>{title} ({entries.length})</summary>{entries.length ? entries.map((item, index) => <div className="profile-group" key={item.id || index}><strong>{name(item) || 'Chưa có tên'}</strong><p className="muted">{[item.start_date, item.end_date || item.graduation_date].filter(Boolean).join(' – ')}</p>{item.description?.length > 0 && <ul>{item.description.map((text, i) => <li key={i}>{text}</li>)}</ul>}</div>) : <p className="muted">Chưa có dữ liệu.</p>}</details>)}
      <button className="text-button" onClick={onOpenProfile}>Xem / tạo hồ sơ khác</button>
      {history && <details><summary>Lịch sử hồ sơ ({history.revisions.length})</summary><ul>{history.revisions.map(item => <li key={item.profile_id}>{item.parent_profile_id ? 'Bản cập nhật' : 'Hồ sơ gốc'} · {item.profile_id.slice(-6)}{item.created_at && ` · ${new Date(item.created_at).toLocaleString('vi-VN')}`}</li>)}</ul>{history.current_profile_id !== profileId && <button className="text-button" onClick={() => onSelect(history.current_profile_id)}>Dùng revision mới nhất</button>}</details>}
    </>}
  </div>;
}
