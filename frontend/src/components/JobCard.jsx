import React from 'react';
import Icon from './ui/Icon.jsx';
import {formatSalary,employmentLabel} from '../features/jobs/formatters.js';
export function sourceTime(value) {
  return value ? new Date(value).toLocaleString('vi-VN') : 'Chưa có thời điểm lấy nguồn';
}
export default function JobCard({ job, selected, onSelect, onSave }) {
  return <article className={`job-card ${selected ? 'selected' : ''}`}>
    <div className="job-card-top"><button className="job-card-select" onClick={onSelect} aria-pressed={selected}>
      <span className="company-avatar" aria-hidden="true">{(job.company || 'JD').split(/\s+/).slice(0,2).map(w=>w[0]).join('').toUpperCase()}</span>
      <span className="job-card-heading"><strong>{job.title}</strong><span>{job.company || 'Công ty chưa công bố'}</span></span>
    </button><button className="save-job" aria-label={job.saved ? `Bỏ lưu ${job.title}` : `Lưu ${job.title}`} aria-pressed={job.saved} onClick={onSave}><Icon name="bookmark" size={18}/></button></div>
    <div className="job-card-meta"><span className="salary">{formatSalary(job)}</span><span><Icon name="pin" size={14}/>{job.location || 'Chưa công bố địa điểm'}</span><span>{employmentLabel(job.employment_type)}</span>{job.workplace_type&&<span>{job.workplace_type}</span>}</div>
    {job.skills?.length > 0 && <div className="pills skills">{job.skills.slice(0,4).map(skill=><span key={skill}>{skill}</span>)}</div>}
    <div className="card-footer"><span className="job-source-badge">{job.source_name}</span></div>
  </article>;
}
