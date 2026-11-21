import CVVersionNotice from "./CVVersionNotice.jsx";
import React, { useState } from "react";
import { jobScore } from "../features/jobs/jobScore.js";

function RequirementTags({ title, items, kind = "" }) {
  const [expanded, setExpanded] = useState(false);
  const labels = [...new Set(items.map((item) => item.label).filter(Boolean))];
  if (!labels.length) return null;
  return (
    <section className={`match-group ${kind}`}>
      <h3>
        {title}
        <span>{labels.length}</span>
      </h3>
      <div className="match-tags">
        {(expanded ? labels : labels.slice(0, 6)).map((label) => (
          <span key={label}>{label}</span>
        ))}
      </div>
      {labels.length > 6 && (
        <button
          className="text-button"
          onClick={() => setExpanded((value) => !value)}
        >
          {expanded ? "Thu gọn" : `Xem thêm ${labels.length - 6} tiêu chí`}
        </button>
      )}
    </section>
  );
}

export default function MatchingPanel({
  evaluation,
  inputCVId,
  postingId,
  busy,
  error,
  onRetry,
  onUpdateProfile,
}) {
  const isCV = evaluation?.input_type === "cv" || !!inputCVId;
  const match = evaluation?.matching;
  const units =
    match?.assessments.filter((item) => item.counted_in_score) || [];
  const hasScore = match?.score != null;
  const technical = jobScore(evaluation);
  return (
    <div className="matching-panel" aria-live="polite">
      <div className="panel-heading">
        <h2>{isCV ? "Độ phù hợp CV" : "Độ phù hợp hồ sơ"}</h2>
      </div>
      {isCV && (
        <CVVersionNotice
          cvId={evaluation?.input_id || inputCVId}
          postingId={evaluation?.job?.posting_id || postingId}
        />
      )}
      {busy && (
        <div className="match-loading" role="status">
          <span className="match-loading-dot" />
          Đang đánh giá hồ sơ…
        </div>
      )}
      {!busy && error && (
        <div className="error" role="alert">
          <p>Chưa thể đánh giá lúc này. Vui lòng thử lại.</p>
          <button onClick={onRetry}>Thử lại</button>
        </div>
      )}
      {!busy && !error && !evaluation && (
        <p className="muted">Chọn công việc để xem độ phù hợp.</p>
      )}
      {!busy && !error && evaluation && !hasScore && (
        <p className="notice">
          {{
            needs_profile: "Hoàn thiện hồ sơ để xem độ phù hợp.",
            insufficient_data: "Chưa đủ thông tin để đánh giá.",
            needs_review: "Thông tin công việc cần được kiểm tra thêm.",
          }[evaluation.status] || "Chưa đủ thông tin để đánh giá."}
        </p>
      )}
      {!busy && !error && hasScore && (
        <>
          <div className="score-box">
            <strong className="match-score" data-testid="match-score">
              {(technical?.score ?? match.score).toLocaleString("vi-VN", {
                maximumFractionDigits: 0,
              })}
              <small>%</small>
            </strong>
            <span>Mức đáp ứng yêu cầu chuyên môn</span>
          </div>
          <p className="match-summary">{technical?.summary}</p>
          <div className="score-weights">
            <span>Chuyên môn bắt buộc 70%</span>
            <span>Kỹ thuật ưu tiên 25%</span>
            <span>Kinh nghiệm & môi trường 5%</span>
          </div>
          {technical?.categories?.length > 0 && <div className="technical-groups">
            {technical.categories.map(([label, items]) => <div key={label}>
              <strong>{label}</strong>
              <span>{[...new Set(items.map((item) => item.label))].slice(0, 4).join(" · ")}</span>
            </div>)}
          </div>}
          <RequirementTags
            title="Điểm phù hợp"
            items={units.filter((item) => item.status === "met")}
            kind="positive"
          />
          <RequirementTags
            title="Đáp ứng một phần"
            items={units.filter((item) => item.status === "partially_met")}
          />
          <RequirementTags
            title="Cần bổ sung thông tin"
            items={units.filter((item) => item.status === "unknown")}
          />
          <RequirementTags
            title="Chưa đáp ứng"
            items={units.filter((item) => item.status === "not_met")}
            kind="negative"
          />
        </>
      )}
      {units.length > 0 && (
        <details className="match-evidence">
          <summary>Vì sao có kết quả này?</summary>
          <p className="muted">
            Chưa đủ thông tin khác với chưa đáp ứng. Điểm này không phải xác
            suất được tuyển.
          </p>
          {units.map((item) => (
            <article key={item.requirement_id}>
              <strong>{item.label}</strong>
              <small>
                {" "}
                ·{" "}
                {
                  {
                    met: "Đáp ứng",
                    partially_met: "Đáp ứng một phần",
                    unknown: "Chưa đủ thông tin",
                    not_met: "Chưa đáp ứng",
                  }[item.status]
                }
              </small>
              <p>{item.explanation}</p>
              {item.evidence_refs.map(
                (ref) =>
                  evaluation.evidence_quotes?.[ref] && (
                    <blockquote key={ref}>
                      {evaluation.evidence_quotes[ref]}
                    </blockquote>
                  ),
              )}
            </article>
          ))}
        </details>
      )}
      {!isCV && (
        <div className="future-actions">
          <button disabled={busy} onClick={onUpdateProfile}>
            Cập nhật hồ sơ
          </button>
        </div>
      )}
    </div>
  );
}
