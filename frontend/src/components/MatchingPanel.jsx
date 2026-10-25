import React, { useState } from 'react';

const dimensions = {
  required_skills: 'Kỹ năng chuyên môn',
  experience: 'Kinh nghiệm',
  education: 'Học vấn',
};

function RequirementTags({ title, items, kind = '' }) {
  const [expanded, setExpanded] = useState(false);
  const labels = [...new Set(items.map(item => item.label).filter(Boolean))];
  if (!labels.length) return null;
  return <section className={`match-group ${kind}`}>
    <h3>{title}<span>{labels.length}</span></h3>
    <div className="match-tags">{(expanded ? labels : labels.slice(0, 6)).map(label => <span key={label}>{label}</span>)}</div>
    {labels.length > 6 && <button className="text-button" onClick={() => setExpanded(value => !value)}>{expanded ? 'Thu gọn' : `Xem thêm ${labels.length - 6} tiêu chí`}</button>}
  </section>;
}

export default function MatchingPanel({ evaluation, busy, error, onRetry, onUpdateProfile, onOptimizeCV }) {
  const match = evaluation?.matching;
  const units = match?.assessments.filter(item => item.counted_in_score) || [];
  const hasScore = match?.score != null;
  return <div className="matching-panel" aria-live="polite">
    <div className="panel-heading"><h2>Độ phù hợp hồ sơ</h2></div>
    {busy && <div className="match-loading" role="status"><span className="match-loading-dot" />Đang đánh giá hồ sơ…</div>}
    {!busy && error && <div className="error" role="alert"><p>Chưa thể đánh giá lúc này. Vui lòng thử lại.</p><button onClick={onRetry}>Thử lại</button></div>}
    {!busy && !error && !evaluation && <p className="muted">Chọn công việc để xem độ phù hợp.</p>}
    {!busy && !error && evaluation && !hasScore && <p className="notice">{({ needs_profile: 'Hoàn thiện hồ sơ để xem độ phù hợp.', insufficient_data: 'Chưa đủ thông tin để đánh giá.', needs_review: 'Thông tin công việc cần được kiểm tra thêm.' })[evaluation.status] || 'Chưa đủ thông tin để đánh giá.'}</p>}
    {!busy && !error && hasScore && <>
      <div className="score-box"><strong className="match-score" data-testid="match-score">{match.score.toLocaleString('vi-VN', { maximumFractionDigits: 0 })}<small>%</small></strong><span>Mức đáp ứng yêu cầu</span></div>
      <div className="dimension-scores">{Object.entries(dimensions).filter(([key]) => match.dimension_scores[key] != null).map(([key, label]) => {
        const value = match.dimension_scores[key];
        return <div key={key}><div><span>{label}</span><strong>{value.toLocaleString('vi-VN', { maximumFractionDigits: 0 })}%</strong></div><meter min="0" max="100" value={value} aria-label={label} /></div>;
      })}</div>
      <RequirementTags title="Điểm phù hợp" items={units.filter(item => item.status === 'met')} kind="positive" />
      <RequirementTags title="Đáp ứng một phần" items={units.filter(item => item.status === 'partially_met')} />
      <RequirementTags title="Cần bổ sung thông tin" items={units.filter(item => item.status === 'unknown')} />
      <RequirementTags title="Chưa đáp ứng" items={units.filter(item => item.status === 'not_met')} kind="negative" />
    </>}
    <div className="future-actions"><button disabled={busy || !match} onClick={onUpdateProfile}>Cập nhật hồ sơ</button><button disabled={busy || !match} onClick={onOptimizeCV}>Tối ưu CV</button></div>
  </div>;
}
