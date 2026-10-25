import React, { useState } from 'react';
import JDDetails from './JDDetails.jsx';
import { sourceTime } from './JobCard.jsx';

export default function JobDetail({ job, evaluation, busy, refreshing, onRefresh }) {
  const [tab, setTab] = useState('description');
  if (!job) return <div className="empty-panel"><h2>Khám phá công việc tiếp theo</h2><p>Chọn một tin bên trái để xem JD, phân tích yêu cầu và so sánh với hồ sơ của bạn.</p><p className="muted">Chỉ công việc bạn chọn mới được phân tích bằng Qwen.</p></div>;
  return <article className="job-detail">
    <p className="eyebrow">{job.source_name}{job.source_board && ` · ${job.source_board}`}</p>
    <h1>{job.title}</h1><h2 className="company-name">{job.company || evaluation?.analysis.job_requirements.company || 'Công ty: Không công bố'}</h2>
    <div className="job-facts">{[
      ['Địa điểm', job.location], ['Hình thức', job.employment_type], ['Môi trường', job.workplace_type],
      ['Mức lương', job.salary || evaluation?.analysis.job_requirements.salary],
    ].map(([label, value]) => <div key={label}><span>{label}</span><strong>{value || 'Không công bố'}</strong></div>)}</div>
    <div className="job-actions">{(job.apply_url || job.source_url) && <a className="button-link" href={job.apply_url || job.source_url} target="_blank" rel="noopener noreferrer">Mở trang ứng tuyển gốc ↗</a>}<button className="secondary-button" disabled={refreshing || !job.source_url || job.import_method === 'text'} onClick={onRefresh}>{refreshing ? 'Đang cập nhật…' : 'Cập nhật JD từ nguồn'}</button></div>
    <p className="source-line">{job.fetched_at ? `Lần lấy thành công: ${sourceTime(job.fetched_at)}.` : 'Chưa có thời điểm fetch nguồn cho bản đã lưu.'} Snapshot không bảo đảm công việc vẫn đang tuyển ở thời điểm hiện tại.</p>
    {job.source_url && <p className="source-line">Nguồn: <a href={job.source_url} target="_blank" rel="noopener noreferrer">{job.source_name} ↗</a>{job.source_updated_at && ` · Cập nhật theo nguồn: ${sourceTime(job.source_updated_at)}`}{job.expires_at && ` · Hạn theo nguồn: ${sourceTime(job.expires_at)}`}</p>}
    {job.timezone_restrictions?.length > 0 && <details><summary>Giới hạn múi giờ theo nguồn</summary><p>{job.timezone_restrictions.join(', ')}</p><p className="muted">Remote không tự động đồng nghĩa có thể ứng tuyển từ mọi quốc gia.</p></details>}
    <div className="detail-tabs" role="tablist" aria-label="Thông tin công việc">
      <button role="tab" aria-selected={tab === 'description'} onClick={() => setTab('description')}>JD đầy đủ</button>
      <button role="tab" aria-selected={tab === 'requirements'} onClick={() => setTab('requirements')}>Yêu cầu đã phân tích{busy ? '…' : ''}</button>
    </div>
    {tab === 'description' ? <div className="job-description" role="tabpanel">{job.description}</div> : <div role="tabpanel">{busy ? <p className="loading">Analyzing Job Description…</p> : evaluation ? <JDDetails job={evaluation.analysis} /> : <p className="notice">Chưa có phân tích hợp lệ. Xem thông báo ở khu vực Matching.</p>}</div>}
  </article>;
}
