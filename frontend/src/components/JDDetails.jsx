import React from 'react';

const requirementTypes = { required: 'Bắt buộc', preferred: 'Ưu tiên', unspecified: 'Chưa nêu rõ bắt buộc/ưu tiên' };

function RequirementList({ title, field, items = [], choiceGroups = [] }) {
  const standalone = items.filter(item => !choiceGroups.some(group => item.id && group.requirement_ids?.length
    ? group.requirement_ids.includes(item.id)
    : group.members.includes(item.name)));
  const count = standalone.length + choiceGroups.length;
  return <div className="jd-group">
    <h4>{title} ({count})</h4>
    {count === 0 ? <p className="jd-empty">Chưa có dữ liệu trích xuất.</p> : <ul className="jd-items">
      {standalone.map((item, index) => <li key={item.id || index}>
        {item.name || item.description}
        {!['required_skills', 'preferred_skills', 'unspecified_skills'].includes(field) && <span className="jd-meta"> — {requirementTypes[item.requirement_type]}</span>}
        {item.minimum_years != null && <span className="jd-meta"> · Tối thiểu {item.minimum_years} năm</span>}
      </li>)}
      {choiceGroups.map((group, index) => <li key={group.id || `choice-${index}`}>
        <strong>Nhóm lựa chọn — ít nhất một:</strong> {group.members.join(' HOẶC ')}
        <span className="jd-meta"> — {requirementTypes[group.requirement_type]}; không yêu cầu có tất cả.</span>
      </li>)}
    </ul>}
  </div>;
}

export default function JDDetails({ job }) {
  const jd = job.job_requirements;
  const fields = [
    ['Vị trí tuyển dụng', 'job_title'], ['Công ty', 'company'],
    ['Địa điểm', 'location'], ['Loại hình làm việc', 'employment_type'],
    ['Mức lương', 'salary'], ['Tóm tắt công việc', 'job_summary'],
  ];
  const groups = [
    ['Kỹ năng bắt buộc', 'required_skills'], ['Kỹ năng ưu tiên', 'preferred_skills'],
    ['Kỹ năng chưa nêu rõ mức yêu cầu', 'unspecified_skills'],
    ['Yêu cầu kỹ thuật', 'technical_requirements'], ['Kinh nghiệm', 'experience_requirements'],
    ['Học vấn', 'education_requirements'], ['Chứng chỉ', 'certifications'],
    ['Ngôn ngữ', 'languages'], ['Trách nhiệm công việc', 'responsibilities'],
    ['Yêu cầu cốt lõi', 'core_requirements'],
  ];
  return <article className="jd-details" aria-label="Các trường thông tin JD">
    <h3>Thông tin JD đã trích xuất</h3>
    <p className="jd-empty">“Chưa có dữ liệu” nghĩa là hệ thống chưa trích xuất được trường đó; hãy đối chiếu JD gốc.</p>
    <div className="jd-group">
      <h4>Thông tin công việc</h4>
      <ul className="jd-items">
        {fields.map(([label, field]) => <li key={field}><strong>{label}:</strong> {jd[field] || <span className="jd-empty">Chưa có dữ liệu</span>}</li>)}
        {job.source_url && <li><strong>URL nguồn:</strong> {job.source_url}</li>}
      </ul>
    </div>
    {groups.map(([title, field]) => <RequirementList key={field} title={title} field={field} items={jd[field]}
      choiceGroups={(jd.requirement_groups || []).filter(group => group.operator === 'any' && ({required_skills: 'required', preferred_skills: 'preferred', unspecified_skills: 'unspecified'})[field] === group.requirement_type)} />)}
    <div className="jd-group">
      <h4>Nhóm yêu cầu đồng thời (AND)</h4>
      {!jd.requirement_groups?.some(group => group.operator === 'all') ? <p className="jd-empty">Chưa có nhóm AND được xác định.</p> : <ul className="jd-items">
        {jd.requirement_groups.filter(group => group.operator === 'all').map((group, index) => <li key={group.id || index}>
          {group.members.join(' VÀ ')}
          <span className="jd-meta"> — Cần tất cả · {requirementTypes[group.requirement_type] || 'Chưa xác định'}</span>
        </li>)}
      </ul>}
    </div>
    <details><summary>Đối chiếu nội dung JD gốc</summary><pre>{job.job_description_raw || jd.job_description_raw || 'Chưa có dữ liệu'}</pre></details>
  </article>;
}
