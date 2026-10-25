import React, { useState } from 'react';
import { request } from '../services/api.js';
import JDDetails from './JDDetails.jsx';

export default function JobMatching({ confirmedProfileId }) {
  const [source, setSource] = useState('text');
  const [input, setInput] = useState('');
  const [profileId, setProfileId] = useState('');
  const [job, setJob] = useState(null);
  const [match, setMatch] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const selectedProfile = confirmedProfileId || profileId.trim();

  async function analyze(event) {
    event.preventDefault();
    setBusy(true); setError(''); setJob(null); setMatch(null);
    try {
      const key = source === 'url' ? 'source_url' : source === 'saved' ? 'saved_job_id' : 'job_description_text';
      const result = await request('/api/jobs/analyze', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ [key]: input.trim() }),
      });
      setJob(result);
    } catch (error) { setError(`${error.message}${source === 'url' ? ' Bạn có thể chuyển sang dán JD thủ công.' : ''}`); }
    finally { setBusy(false); }
  }

  async function calculate() {
    setBusy(true); setError(''); setMatch(null);
    try {
      const result = await request('/api/matches', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ profile_id: selectedProfile, job_id: job.job_id }),
      });
      setMatch(result);
    } catch (error) { setError(error.message); }
    finally { setBusy(false); }
  }

  return <section aria-labelledby="jd-heading">
    <h2 id="jd-heading">Ngày 2 · Phân tích JD và Matching</h2>
    <form onSubmit={analyze}>
      <label>Nguồn JD <select value={source} disabled={busy} onChange={event => { setSource(event.target.value); setInput(''); setJob(null); setMatch(null); }}>
        <option value="text">Dán nội dung JD</option><option value="url">URL tuyển dụng công khai</option><option value="saved">Mã JD đã phân tích</option>
      </select></label>
      <label htmlFor="jd-source">{source === 'url' ? 'URL http/https' : source === 'saved' ? 'Job ID' : 'Nội dung JD'}
        <textarea id="jd-source" rows={source === 'text' ? 10 : 2} value={input} disabled={busy} maxLength={source === 'text' ? 60000 : source === 'url' ? 2048 : 128} onChange={event => setInput(event.target.value)} required />
      </label>
      <button disabled={busy || !input.trim()}>{busy ? 'Đang xử lý…' : source === 'saved' ? 'Tải JD đã lưu' : 'Phân tích JD bằng Qwen'}</button>
    </form>
    {error && <p className="error" role="alert">{error}</p>}
    {job && <>
      <h3>{job.job_requirements.job_title || 'Kết quả phân tích JD'}</h3>
      <p>Job ID: <code>{job.job_id}</code> · {job.status === 'review' ? 'Cần kiểm tra cảnh báo' : 'Đã phân tích'}</p>
      {job.warnings.length > 0 && <ul>{job.warnings.map((warning, i) => <li key={i}>{warning}</li>)}</ul>}
      <JDDetails job={job} />
      <label>Master Profile đã xác nhận
        <input value={selectedProfile} readOnly={Boolean(confirmedProfileId)} disabled={busy} placeholder="Nhập mã hồ sơ đã xác nhận hoặc xác nhận CV ở trên" onChange={event => setProfileId(event.target.value)} />
      </label>
      <button type="button" disabled={busy || !selectedProfile} onClick={calculate}>Tính Match Score từ hồ sơ đã lưu</button>
    </>}
    {match && <article aria-live="polite">
      <h3>Match Score: {match.score === null ? 'Chưa đủ căn cứ' : `${match.score.toFixed(2)} / 100`}</h3>
      <p>Đây là mức phù hợp dựa trên bằng chứng, không phải xác suất được tuyển dụng. Kết quả: <code>{match.result_id}</code></p>
      <p>Độ phủ bằng chứng: {(match.evidence_coverage * 100).toFixed(0)}%{match.core_coverage === null ? '' : ` · Độ đáp ứng cốt lõi: ${(match.core_coverage * 100).toFixed(0)}%`}</p>
      <ul>{Object.entries(match.dimension_scores).map(([key, value]) => <li key={key}>{key}: {value.toFixed(1)} / 100</li>)}</ul>
      <h4>Điểm có bằng chứng</h4><ul>{match.strengths.map((item, i) => <li key={i}>{item}</li>)}</ul>
      <h4>Khoảng thiếu / chưa có bằng chứng</h4><ul>{match.gaps.map((item, i) => <li key={i}>{item}</li>)}</ul>
      <details><summary>Giải thích từng yêu cầu, trọng số và cảnh báo</summary><pre>{JSON.stringify(match, null, 2)}</pre></details>
    </article>}
  </section>;
}
