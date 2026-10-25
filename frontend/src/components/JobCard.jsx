import React from 'react';

export function sourceTime(value) {
  return value ? new Date(value).toLocaleString('vi-VN') : 'Chưa có thời điểm lấy nguồn';
}

export default function JobCard({ job, selected, onSelect, onSave }) {
  return <article className={`job-card ${selected ? 'selected' : ''}`}>
    <button className="job-card-select" onClick={onSelect} aria-pressed={selected}>
      <span className="company-avatar" aria-hidden="true">{(job.company || 'JD').slice(0, 2).toUpperCase()}</span>
      <span className="job-card-heading"><strong>{job.title}</strong><span>{job.company || 'Không công bố'}</span></span>
    </button>
    <p className="salary">{job.salary || 'Lương: Không công bố'}</p>
    <p className="muted">{job.location || 'Địa điểm: Không công bố'}</p>
    <div className="pills"><span>{job.employment_type || 'Hình thức: Không công bố'}</span>{job.workplace_type && <span>{job.workplace_type}</span>}</div>
    {job.skills?.length > 0 && <div className="pills skills">{job.skills.slice(0, 4).map(skill => <span key={skill}>{skill}</span>)}</div>}
    <p className="source-line">{job.source_name}{job.source_board && ` · ${job.source_board}`}<br />{job.import_method === 'text' ? `Người dùng nhập: ${sourceTime(job.imported_at)} · chưa xác minh nguồn` : job.fetched_at ? `Đồng bộ: ${sourceTime(job.fetched_at)}` : 'Snapshot đã lưu · chưa xác minh lại nguồn'}</p>
    <div className="card-footer"><span className={`analysis-badge ${job.analysis_status === 'analyzed' ? 'ready' : ''}`}>{job.analysis_status === 'analyzed' ? 'Đã phân tích' : 'Chưa phân tích'}</span>
      <button className="text-button save-job" aria-label={job.saved ? `Bỏ lưu ${job.title}` : `Lưu ${job.title}`} aria-pressed={job.saved} onClick={onSave}>{job.saved ? '♥ Đã lưu' : '♡ Lưu việc'}</button>
    </div>
  </article>;
}
