import React, { useState } from "react";
import ApplicationPanel from "../features/applications/ApplicationPanel.jsx";
import {formatSalary} from "../features/jobs/formatters.js";
import JDDetails from "./JDDetails.jsx";
import { sourceTime } from "./JobCard.jsx";

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
  refreshing,
  onRefresh,
  error,
}) {
  const [tab, setTab] = useState("description");
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
      <p className="eyebrow">
        {job.source_name}
        {job.source_board && ` · ${job.source_board}`}
      </p>
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
        <button
          className="secondary-button"
          disabled={
            refreshing || !job.source_url || job.import_method === "text"
          }
          onClick={onRefresh}
        >
          {refreshing ? "Đang cập nhật…" : "Cập nhật JD từ nguồn"}
        </button>
      </div>
      {review && (
        <ApplicationPanel
          key={job.posting_id}
          job={job}
          evaluation={evaluation}
        />
      )}
      {job.expiry_conflict&&<p className="notice">Thông tin hạn tuyển chưa thống nhất trên trang nguồn. Hạn đang hiển thị: {job.source_expires_at_text}. Hãy kiểm tra lại tin gốc trước khi ứng tuyển.</p>}
      <p className="source-line">
        {job.fetched_at
          ? `Lần lấy thành công: ${sourceTime(job.fetched_at)}.`
          : "Tin đã lưu chưa có thời điểm cập nhật từ nguồn."}{" "}
        Hãy kiểm tra nguồn để xác nhận công việc còn nhận hồ sơ.
      </p>
      {job.source_url && (
        <p className="source-line">
          Nguồn:{" "}
          <a href={job.source_url} target="_blank" rel="noopener noreferrer">
            {job.source_name} ↗
          </a>
          {job.source_updated_at &&
            ` · Cập nhật theo nguồn: ${sourceTime(job.source_updated_at)}`}
          {job.expires_at && ` · Hạn theo nguồn: ${sourceTime(job.expires_at)}`}
        </p>
      )}
      {job.timezone_restrictions?.length > 0 && (
        <details>
          <summary>Giới hạn múi giờ theo nguồn</summary>
          <p>{job.timezone_restrictions.join(", ")}</p>
          <p className="muted">
            Remote không tự động đồng nghĩa có thể ứng tuyển từ mọi quốc gia.
          </p>
        </details>
      )}
      {job.work_locations?.length>0&&<details><summary>Địa điểm làm việc theo nguồn</summary><ul>{job.work_locations.map((place,index)=><li key={index}>{place}</li>)}</ul></details>}
      <div
        className="detail-tabs"
        role="tablist"
        aria-label="Thông tin công việc"
      >
        <button
          role="tab"
          aria-selected={tab === "description"}
          onClick={() => setTab("description")}
        >
          JD đầy đủ
        </button>
        <button
          role="tab"
          aria-selected={tab === "requirements"}
          onClick={() => setTab("requirements")}
        >
          Yêu cầu đã phân tích{busy ? "…" : ""}
        </button>
      </div>
      {tab === "description" ? (
        <div className="job-description" role="tabpanel">
          {splitJobSections(job.description).map((section,index)=><section className="job-section" key={index}><h2>{section.heading}</h2><p>{section.lines.join("\n")}</p></section>)}
        </div>
      ) : (
        <div role="tabpanel">
          {busy ? (
            <p className="loading">Đang phân tích yêu cầu công việc…</p>
          ) : evaluation ? (
            <JDDetails job={evaluation.analysis} />
          ) : (
            <p className="notice">
              Chưa có phân tích hợp lệ. Xem thông báo ở khu vực Matching.
            </p>
          )}
        </div>
      )}
    </article>
  );
}
