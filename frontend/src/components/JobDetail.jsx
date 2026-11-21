import React, { useState } from "react";
import ApplicationPanel from "../features/applications/ApplicationPanel.jsx";
import {formatSalary} from "../features/jobs/formatters.js";

export function splitJobSections(text) {
  const headings = /^(mô tả công việc|yêu cầu (ứng viên|công việc)|quyền lợi|phúc lợi|responsibilities|requirements|qualifications|benefits|about (the )?role|what you.ll do|what you.ll bring)\s*:?\s*$/i;
  const result=[];let current={heading:'Thông tin công việc',lines:[]};
  for (const line of text.split('\n')) {
    if (headings.test(line.trim())) { if(current.lines.length)result.push(current);current={heading:line.trim().replace(/:$/,''),lines:[]}; }
    else current.lines.push(line);
  }
  if(current.lines.length)result.push(current);
  return result;
}

export default function JobDetail({
  job,
  evaluation,
  busy,
  error,
}) {
  const [review, setReview] = useState(false);
  if (!job && busy) return <div className="empty-panel" role="status"><h2>Đang tải công việc…</h2><p>Nội dung tin sẽ xuất hiện trước khi có kết quả đánh giá.</p></div>;
  if (!job && error) return <div className="error" role="alert"><h2>Chưa tải được công việc</h2><p>{error}</p><p>Thử lại đánh giá hoặc trở về kết quả tìm kiếm để chọn tin khác.</p></div>;
  if (!job)
    return (
      <div className="empty-panel">
        <h2>Khám phá công việc tiếp theo</h2>
        <p>
          Chọn một tin bên trái để xem JD, phân tích yêu cầu và so sánh với hồ
          sơ của bạn.
        </p>
        <p className="muted">
          Chọn CV để đối chiếu các yêu cầu công việc.
        </p>
      </div>
    );
  return (
    <article className="job-detail">
      <h1>{job.title}</h1>
      <h2 className="company-name">
        {job.company ||
          "Công ty: Không công bố"}
      </h2>
      <div className="job-facts">
        {[
          ["Địa điểm", job.location],
          ["Hình thức", job.employment_type],
          ["Môi trường", job.workplace_type],
          [
            "Mức lương",
            formatSalary(job),
          ],
        ].map(([label, value]) => (
          <div key={label}>
            <span>{label}</span>
            <strong>{value || "Không công bố"}</strong>
          </div>
        ))}
      </div>
      <div className="job-actions">
        {(job.apply_url || job.source_url) && (
          <button onClick={() => setReview(!review)}>
            {review ? "Đóng bước chuẩn bị" : "Chuẩn bị ứng tuyển →"}
          </button>
        )}
      </div>
      {review && (
        <ApplicationPanel
          key={job.posting_id}
          job={job}
          evaluation={evaluation}
        />
      )}
      {job.timezone_restrictions?.length > 0 && (
        <details>
          <summary>Yêu cầu múi giờ</summary>
          <p>{job.timezone_restrictions.join(", ")}</p>
          <p className="muted">
            Remote không tự động đồng nghĩa có thể ứng tuyển từ mọi quốc gia.
          </p>
        </details>
      )}
      {job.work_locations?.length > 0 && <section className="job-locations"><h2>Địa điểm làm việc</h2><ul>{job.work_locations.map((place,index)=><li key={index}>{place}</li>)}</ul></section>}
      <div className="detail-tabs"><h2>Chi tiết công việc</h2></div>
      <div className="job-description">
        {splitJobSections(job.description).map((section,index)=><section className="job-section" key={index}><h2>{section.heading}</h2><p>{section.lines.join("\n")}</p></section>)}
      </div>
    </article>
  );
}
