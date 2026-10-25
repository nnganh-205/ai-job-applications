import React, { useEffect, useState } from 'react';
import { request } from '../services/api.js';
import { getDashboard, jobRequest } from '../services/jobs.js';
import JobCard from '../components/JobCard.jsx';
import JobDetail from '../components/JobDetail.jsx';
import MyProfilePanel from '../components/MyProfilePanel.jsx';
import MatchingPanel from '../components/MatchingPanel.jsx';
import SearchFilters from '../components/SearchFilters.jsx';
import ProfileSessionPanel from '../components/ProfileSessionPanel.jsx';
import CVWorkspace from '../components/CVWorkspace.jsx';

const initialFilters = { q: '', location: '', employment_type: '', workplace_type: '', source_name: '', saved: false, domestic_sources_only: false };

export default function Dashboard({ confirmedProfileId, onOpenProfile, onProfileConfirmed }) {
  const [catalog, setCatalog] = useState({ jobs: [], profiles: [], filters: {}, total: 0 });
  const [filters, setFilters] = useState(initialFilters);
  const [profileId, setProfileId] = useState(confirmedProfileId || '');
  const [profile, setProfile] = useState(null);
  const [selectedId, setSelectedId] = useState('');
  const [detail, setDetail] = useState(null);
  const [evaluation, setEvaluation] = useState(null);
  const [catalogBusy, setCatalogBusy] = useState(true);
  const [busy, setBusy] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [reload, setReload] = useState(0);
  const [retry, setRetry] = useState(0);
  const [importMode, setImportMode] = useState('url');
  const [importText, setImportText] = useState('');
  const [sourceUrl, setSourceUrl] = useState('');
  const [importing, setImporting] = useState(false);
  const [showUpdate, setShowUpdate] = useState(false);
  const [showCV, setShowCV] = useState(false);

  function updatedProfile(id) {
    setProfileId(id); setReload(value => value + 1); setRetry(value => value + 1);
    onProfileConfirmed?.(id);
  }

  useEffect(() => { setShowUpdate(false); setShowCV(false); }, [selectedId, profileId]);

  useEffect(() => {
    if (confirmedProfileId) { setProfileId(confirmedProfileId); setReload(value => value + 1); }
  }, [confirmedProfileId]);

  useEffect(() => {
    const controller = new AbortController();
    setCatalogBusy(true);
    const timer = setTimeout(() => {
      getDashboard(filters, controller.signal).then(data => {
        if (controller.signal.aborted) return;
        setCatalog(data);
        let stored;
        try { stored = localStorage.getItem('kltn.confirmedProfileId'); } catch { /* Storage can be unavailable in private browsing. */ }
        setProfileId(current => data.profiles.some(item => item.profile_id === current) ? current : data.profiles.some(item => item.profile_id === stored) ? stored : data.active_profile_id || '');
      }).catch(error => { if (error.name !== 'AbortError') setMessage(`Không tải được danh sách: ${error.message}`); })
        .finally(() => { if (!controller.signal.aborted) setCatalogBusy(false); });
    }, 200);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [filters, reload]);

  useEffect(() => {
    const controller = new AbortController();
    setProfile(null);
    if (profileId) {
      request(`/api/profiles/${encodeURIComponent(profileId)}`, { signal: controller.signal, timeoutMs: 15000 })
        .then(data => { if (!controller.signal.aborted) setProfile(data.profile); })
        .catch(error => { if (error.name !== 'AbortError') setMessage(error.message); });
      try { localStorage.setItem('kltn.confirmedProfileId', profileId); } catch { /* Only the ID is persisted in the browser. */ }
    }
    return () => controller.abort();
  }, [profileId]);

  useEffect(() => {
    if (!selectedId) return;
    const controller = new AbortController();
    setBusy(true); setError(''); setEvaluation(null); setDetail(null);
    async function evaluate() {
      try {
        const job = await request(`/api/dashboard/jobs/${selectedId}`, { signal: controller.signal, timeoutMs: 15000 });
        if (controller.signal.aborted) return;
        setDetail(job);
        const result = await jobRequest(`/jobs/${selectedId}/evaluate`, { profile_id: profileId || null }, 'POST', controller.signal);
        if (controller.signal.aborted) return;
        setEvaluation(result); setDetail(result.job);
        if (result.profile) setProfile(result.profile);
        setReload(value => value + 1);
      } catch (error) {
        if (error.name !== 'AbortError') setError(error.message);
      } finally { if (!controller.signal.aborted) setBusy(false); }
    }
    evaluate();
    return () => controller.abort();
  }, [selectedId, profileId, retry]);

  async function sync() {
    setSyncing(true); setMessage('');
    try {
      const result = await jobRequest('/jobs/sync', {});
      setMessage(result.status === 'source_not_configured' || result.cooldown ? result.errors.join(' ') : `Đã lấy ${result.fetched} tin: ${result.inserted} mới, ${result.updated} thay đổi, ${result.unchanged} không đổi. ${result.cached_sources?.length ? `Nguồn đang dùng cache: ${result.cached_sources.join(', ')}. ` : ''}${result.errors.join(' ')}`);
      setReload(value => value + 1);
      if (selectedId && result.fetched > 0 && !result.cooldown) setRetry(value => value + 1);
    } catch (error) { setMessage(`Không đồng bộ được. Các snapshots vẫn được giữ: ${error.message}`); }
    finally { setSyncing(false); }
  }

  async function save(job) {
    try {
      await jobRequest(`/jobs/${job.posting_id}/saved`, { saved: !job.saved }, 'PATCH');
      setReload(value => value + 1);
    } catch (error) { setMessage(error.message); }
  }

  async function refresh() {
    setRefreshing(true); setMessage('');
    try {
      const result = await jobRequest(`/jobs/${selectedId}/refresh`, {});
      setDetail(result.job); setMessage(result.warning || 'Đã cập nhật snapshot từ nguồn.');
      setReload(value => value + 1);
      if (!result.warning) setRetry(value => value + 1);
    } catch (error) { setMessage(error.message); }
    finally { setRefreshing(false); }
  }

  async function importJob(event) {
    event.preventDefault(); setImporting(true); setMessage('');
    try {
      const job = await jobRequest('/jobs', importMode === 'url' ? { source_url: importText.trim() } : { job_description_text: importText.trim(), source_url: sourceUrl.trim() || null });
      setImportText(''); setSourceUrl(''); setReload(value => value + 1); setSelectedId(job.posting_id);
    } catch (error) { setMessage(`${error.message} Nếu website chặn truy cập, hãy chuyển sang dán JD text.`); }
    finally { setImporting(false); }
  }

  return <>
    <div className="dashboard-intro"><div><p className="eyebrow">CÔNG VIỆC THẬT · HỒ SƠ CỦA BẠN</p><h1>Tìm công việc phù hợp với bạn</h1><p>Khám phá cơ hội nghề nghiệp phù hợp với kỹ năng và kinh nghiệm của bạn.</p></div><span className="market-label">Cơ hội nghề nghiệp</span></div>
    <SearchFilters filters={filters} options={catalog.filters} onChange={(key, value) => setFilters(current => ({ ...current, [key]: value }))} syncing={syncing} onSync={sync} />
    {message && <p className="notice" role="status">{message}</p>}
    {catalog.sync?.errors?.length > 0 && <p className="notice">Nguồn gặp lỗi lần đồng bộ gần nhất. Danh sách có thể dùng snapshot cũ; xem thời điểm lấy trên từng tin.</p>}
    <details className="import-panel"><summary>Thêm công việc từ URL hoặc JD text</summary><form onSubmit={importJob}><label>Nguồn nhập<select value={importMode} onChange={event => { setImportMode(event.target.value); setImportText(''); }}><option value="url">URL cho phép truy xuất tự động</option><option value="text">Dán JD kèm URL nguồn</option></select></label><p className="muted">Chỉ nhập nội dung bạn có quyền sử dụng. Nhập JD kèm URL giúp ghi nhận TopCV, ITviec, JobsGO, Indeed hoặc LinkedIn; không đồng nghĩa đã kết nối API hay xác minh tin còn tuyển.</p>{importMode === 'text' && <label>URL nguồn (nếu có)<input type="url" value={sourceUrl} onChange={event => setSourceUrl(event.target.value)} placeholder="https://…" /></label>}<label>{importMode === 'url' ? 'URL công việc' : 'Nội dung JD'}<textarea rows={importMode === 'url' ? 2 : 8} value={importText} onChange={event => setImportText(event.target.value)} required /></label><button disabled={importing || !importText.trim()}>{importing ? 'Đang nhập…' : 'Nhập và chọn công việc'}</button></form></details>
    <div className="recruitment-grid">
      <aside className="job-list" aria-label="Danh sách công việc"><div className="panel-heading"><h2>Công việc ({catalog.jobs.length})</h2>{catalogBusy && <span role="status">Đang tải…</span>}</div>{!catalogBusy && catalog.jobs.length === 0 && <div className="empty-panel"><p>{catalog.total ? 'Không có công việc phù hợp bộ lọc.' : 'Chưa có tin trong kho. Bấm Refresh tin tuyển dụng để lấy dữ liệu từ các API công khai.'}</p></div>}{catalog.jobs.map(job => <JobCard key={job.posting_id} job={job} selected={job.posting_id === selectedId} onSelect={() => setSelectedId(job.posting_id)} onSave={() => save(job)} />)}</aside>
      <div className="detail-panel"><JobDetail key={selectedId} job={detail} evaluation={evaluation} busy={busy} refreshing={refreshing} onRefresh={refresh} /></div>
      <aside className="candidate-panel"><MyProfilePanel profile={profile} profiles={catalog.profiles} profileId={profileId} onSelect={setProfileId} onOpenProfile={onOpenProfile} /><MatchingPanel evaluation={evaluation} busy={busy} error={error} onRetry={() => setRetry(value => value + 1)} onUpdateProfile={() => setShowUpdate(true)} onOptimizeCV={() => setShowCV(true)} />{showUpdate && <ProfileSessionPanel mode="update" profileId={profileId} postingId={selectedId} profile={profile} onProfileConfirmed={updatedProfile} onClose={() => setShowUpdate(false)} />}</aside>
    </div>
    {showCV && <CVWorkspace key={`${profileId}:${selectedId}`} profileId={profileId} postingId={selectedId} jobTitle={detail?.title} onClose={() => setShowCV(false)} />}
  </>;
}
