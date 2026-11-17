import React, { useEffect, useState, useMemo } from "react";
import {
  useSearchParams,
  useParams,
  useNavigate,
  Link,
} from "react-router-dom";
import {
  createTask,
  getTask,
  waitTask,
  retryTask,
  taskLabel,
} from "../services/tasks.js";
import { request } from "../services/api.js";
import { getDashboard, jobRequest } from "../services/jobs.js";
import { JobSkeletons } from "../components/ui/PageState.jsx";
import JobCard from "../components/JobCard.jsx";
import JobDetail from "../components/JobDetail.jsx";
import MyProfilePanel from "../components/MyProfilePanel.jsx";
import MatchingPanel from "../components/MatchingPanel.jsx";
import SearchFilters from "../components/SearchFilters.jsx";
import ProfileSessionPanel from "../components/ProfileSessionPanel.jsx";
import CVWorkspace from "../components/CVWorkspace.jsx";

const initialFilters = {
  q: "",
  location: "",
  employment_type: "",
  workplace_type: "",
  source_name: "",
  industry: "",
  experience_level: "",
  salary_min: "",
  salary_currency: "VND",
  salary_period: "month",
  saved: false,
  domestic_sources_only: false,
};

export default function Dashboard({
  confirmedProfileId,
  onOpenProfile,
  onProfileConfirmed,
}) {
  const [profilesReady, setProfilesReady] = useState(false);
  const [analysisTask, setAnalysisTask] = useState(null);
  const [catalog, setCatalog] = useState({
    jobs: [],
    profiles: [],
    filters: {},
    total: 0,
  });
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const cvId = searchParams.get("cv") || "";
  const [cvVersions, setCVVersions] = useState([]);
  useEffect(() => {
    const c = new AbortController();
    request("/api/resumes/published", { signal: c.signal })
      .then(setCVVersions)
      .catch((e) => {
        if (e.name !== "AbortError") setMessage(e.message);
      });
    return () => c.abort();
  }, [cvId]);
  const { id: selectedId = "" } = useParams();
  const filters = useMemo(
    () =>
      Object.fromEntries(
        Object.entries(initialFilters).map(([key, value]) => [
          key,
          typeof value === "boolean"
            ? searchParams.get(key) === "true"
            : searchParams.get(key) || value,
        ]),
      ),
    [searchParams],
  );
  function setFilters(update) {
    const next = typeof update === "function" ? update(filters) : update;
    const query = new URLSearchParams(searchParams);
    Object.entries(next).forEach(([key, value]) => {
      if (value) query.set(key, String(value));
      else query.delete(key);
    });
    query.delete("page");
    setSearchParams(query);
  }
  function setSelectedId(id) {
    navigate(`/jobs/${id}?${searchParams.toString()}`);
  }
  const sort = searchParams.get("sort") === "title" ? "title" : "recent";
  const page = Math.max(
    1,
    Number.parseInt(searchParams.get("page") || "1", 10) || 1,
  );
  const sortedJobs = useMemo(
    () =>
      [...catalog.jobs].sort((a, b) =>
        sort === "title"
          ? a.title.localeCompare(b.title, "vi") ||
            a.posting_id.localeCompare(b.posting_id)
          : (b.fetched_at || b.imported_at).localeCompare(
              a.fetched_at || a.imported_at,
            ) || a.posting_id.localeCompare(b.posting_id),
      ),
    [catalog.jobs, sort],
  );
  const pageCount = Math.max(1, Math.ceil(sortedJobs.length / 10));
  const activePage = Math.min(page, pageCount);
  const visibleJobs = sortedJobs.slice((activePage - 1) * 10, activePage * 10);
  function setPage(value) {
    const q = new URLSearchParams(searchParams);
    q.set("page", String(value));
    setSearchParams(q);
  }

  const [profileId, setProfileId] = useState(confirmedProfileId || "");
  const [profile, setProfile] = useState(null);
  const [detail, setDetail] = useState(null);
  const [evaluation, setEvaluation] = useState(null);
  const [catalogBusy, setCatalogBusy] = useState(true);
  const [catalogError, setCatalogError] = useState("");
  const [busy, setBusy] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [reload, setReload] = useState(0);
  const [retry, setRetry] = useState(0);
  const [showUpdate, setShowUpdate] = useState(false);
  const [showCV, setShowCV] = useState(false);

  function updatedProfile(id) {
    setProfileId(id);
    setReload((value) => value + 1);
    setRetry((value) => value + 1);
    onProfileConfirmed?.(id);
  }

  useEffect(() => {
    setShowUpdate(false);
    setShowCV(false);
  }, [selectedId, profileId, cvId]);

  useEffect(() => {
    if (confirmedProfileId) {
      setProfileId(confirmedProfileId);
      setReload((value) => value + 1);
    }
  }, [confirmedProfileId]);

  useEffect(() => {
    const controller = new AbortController();
    setCatalogBusy(true);
    setCatalogError("");
    const timer = setTimeout(() => {
      getDashboard(filters, controller.signal)
        .then((data) => {
          if (controller.signal.aborted) return;
          setCatalog(data);
          setProfilesReady(true);
          let stored;
          try {
            stored = localStorage.getItem("kltn.confirmedProfileId");
          } catch {
            /* Storage can be unavailable in private browsing. */
          }
          setProfileId((current) =>
            data.profiles.some((item) => item.profile_id === current)
              ? current
              : data.profiles.some((item) => item.profile_id === stored)
                ? stored
                : data.active_profile_id || "",
          );
        })
        .catch((error) => {
          if (error.name !== "AbortError")
            setCatalogError(`Không tải được danh sách: ${error.message}`);
        })
        .finally(() => {
          if (!controller.signal.aborted) setCatalogBusy(false);
        });
    }, 200);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [filters, reload]);

  useEffect(() => {
    const controller = new AbortController();
    setProfile(null);
    if (profileId) {
      request(`/api/profiles/${encodeURIComponent(profileId)}`, {
        signal: controller.signal,
        timeoutMs: 15000,
      })
        .then((data) => {
          if (!controller.signal.aborted) setProfile(data.profile);
        })
        .catch((error) => {
          if (error.name !== "AbortError") setMessage(error.message);
        });
      try {
        localStorage.setItem("kltn.confirmedProfileId", profileId);
      } catch {
        /* Only the ID is persisted in the browser. */
      }
    }
    return () => controller.abort();
  }, [profileId]);

  useEffect(() => {
    if (!selectedId || !profilesReady) return;
    const controller = new AbortController();
    setBusy(true);
    setError("");
    setEvaluation(null);
    setDetail(null);
    setAnalysisTask(null);
    async function evaluate() {
      try {
        const job = await request(`/api/dashboard/jobs/${selectedId}`, {
          signal: controller.signal,
          timeoutMs: 15000,
        });
        if (controller.signal.aborted) return;
        setDetail(job);
        const payload = cvId
          ? { profile_id: null, cv_id: cvId }
          : { profile_id: profileId || null, cv_id: null };
        const scope = `kltn.evaluate:${selectedId}:${profileId}:${cvId}:${job.content_hash}:${new Date().toISOString().slice(0, 10)}`;
        let task;
        try {
          const id = localStorage.getItem(scope);
          if (id) task = await getTask(id, controller.signal);
        } catch (error) {
          if (error.name === "AbortError") throw error;
        }
        if (
          task &&
          (task.payload.posting_id !== selectedId ||
            (task.payload.profile_id || null) !== payload.profile_id ||
            (task.payload.cv_id || null) !== payload.cv_id)
        )
          task = null;
        if (!task || task.status === "completed") {
          task = await createTask(
            `/evaluate/${selectedId}`,
            payload,
            crypto.randomUUID(),
            controller.signal,
          );
          try {
            localStorage.setItem(scope, task.task_id);
          } catch {}
        }
        const result = await waitTask(task.task_id, {
          signal: controller.signal,
          onProgress: setAnalysisTask,
        });
        if (controller.signal.aborted) return;
        setEvaluation(result);
        setDetail(result.job);
        if (result.profile) setProfile(result.profile);
        setReload((value) => value + 1);
      } catch (error) {
        if (error.name !== "AbortError") setError(error.message);
      } finally {
        if (!controller.signal.aborted) setBusy(false);
      }
    }
    evaluate();
    return () => controller.abort();
  }, [selectedId, profileId, cvId, retry, profilesReady]);

  async function sync() {
    setSyncing(true);
    setMessage("");
    try {
      const result = await jobRequest("/jobs/sync", {});
      setMessage(
        result.status === "source_not_configured" || result.cooldown
          ? result.errors.join(" ")
          : `Đã lấy ${result.fetched} tin: ${result.inserted} mới, ${result.updated} thay đổi, ${result.unchanged} không đổi. ${result.cached_sources?.length ? `Nguồn đang dùng cache: ${result.cached_sources.join(", ")}. ` : ""}${result.errors.join(" ")}`,
      );
      setReload((value) => value + 1);
      if (selectedId && result.fetched > 0 && !result.cooldown)
        setRetry((value) => value + 1);
    } catch (error) {
      setMessage(
        `Không đồng bộ được. Các snapshots vẫn được giữ: ${error.message}`,
      );
    } finally {
      setSyncing(false);
    }
  }

  async function save(job) {
    try {
      await jobRequest(
        `/jobs/${job.posting_id}/saved`,
        { saved: !job.saved },
        "PATCH",
      );
      setReload((value) => value + 1);
    } catch (error) {
      setMessage(error.message);
    }
  }

  async function refresh() {
    setRefreshing(true);
    setMessage("");
    try {
      const result = await jobRequest(`/jobs/${selectedId}/refresh`, {});
      setDetail(result.job);
      setMessage(result.warning || "Đã cập nhật snapshot từ nguồn.");
      setReload((value) => value + 1);
      if (!result.warning) setRetry((value) => value + 1);
    } catch (error) {
      setMessage(error.message);
    } finally {
      setRefreshing(false);
    }
  }

  return (
    <>
      {selectedId ? (
        <Link className="back-link" to={"/jobs?" + searchParams.toString()}>
          ← Kết quả tìm việc
        </Link>
      ) : (
        <>
          <div className="dashboard-intro">
            <div>
              <p className="eyebrow">CÔNG VIỆC THẬT · HỒ SƠ CỦA BẠN</p>
              <h1>Cơ hội tiếp theo, bắt đầu từ đây.</h1>
              <p>
                Khám phá cơ hội nghề nghiệp phù hợp với kỹ năng và kinh nghiệm
                của bạn.
              </p>
            </div>
            <span className="market-label">
              Khám phá · Chuẩn bị · Ứng tuyển
            </span>
          </div>
          {cvId && (
            <p className="notice">
              Đang đánh giá nội dung CV version đã chọn. Đổi sang Master Profile
              để bổ sung dữ kiện hoặc tạo phiên tailor mới.
            </p>
          )}
          <SearchFilters
            filters={filters}
            options={catalog.filters}
            onChange={(key, value) =>
              setFilters((current) => ({ ...current, [key]: value }))
            }
            onReset={() => setFilters(initialFilters)}
            syncing={syncing}
            onSync={sync}
          />
        </>
      )}
      {analysisTask && (
        <p role="status" className="notice">
          {taskLabel(analysisTask)}. Bạn có thể rời trang và mở lại công việc
          này.
        </p>
      )}
      {message && (
        <p className="notice" role="status">
          {message}
        </p>
      )}
      {catalog.sync?.errors?.length > 0 && (
        <p className="notice">
          Nguồn gặp lỗi lần đồng bộ gần nhất. Danh sách có thể dùng snapshot cũ;
          xem thời điểm lấy trên từng tin.
        </p>
      )}
      <div className={selectedId ? "job-detail-layout" : "job-results-layout"}>
        {!selectedId && (
          <aside className="job-list" aria-label="Danh sách công việc">
            <div className="panel-heading">
              <h2>Công việc ({catalog.jobs.length})</h2>
              {catalogBusy && <span role="status">Đang tải…</span>}
            </div>
            {!catalogBusy && catalog.jobs.length === 0 && (
              <div className="empty-panel">
                <p>
                  {catalog.total
                    ? "Không có công việc phù hợp bộ lọc."
                    : "Chưa có tin trong kho. Bấm Refresh tin tuyển dụng để lấy dữ liệu từ các API công khai."}
                </p>
              </div>
            )}
            {catalogError && (
              <p className="error" role="alert">
                {catalogError}{" "}
                <button onClick={() => setReload((v) => v + 1)}>
                  Thử tải lại
                </button>
              </p>
            )}
            {catalogBusy ? (
              <JobSkeletons />
            ) : (
              !catalogError &&
              visibleJobs.map((job) => (
                <JobCard
                  key={job.posting_id}
                  job={job}
                  selected={job.posting_id === selectedId}
                  onSelect={() => setSelectedId(job.posting_id)}
                  onSave={() => save(job)}
                />
              ))
            )}
            <div className="form-actions">
              <label>
                Sắp xếp
                <select
                  name="sort"
                  value={sort}
                  onChange={(e) => {
                    const q = new URLSearchParams(searchParams);
                    q.set("sort", e.target.value);
                    q.delete("page");
                    setSearchParams(q);
                  }}
                >
                  <option value="recent">Mới nhất</option>
                  <option value="title">Tên công việc</option>
                </select>
              </label>
              <button
                disabled={activePage === 1}
                onClick={() => setPage(activePage - 1)}
              >
                Trước
              </button>
              <span>
                Trang {activePage}/{pageCount}
              </span>
              <button
                disabled={activePage === pageCount}
                onClick={() => setPage(activePage + 1)}
              >
                Sau
              </button>
            </div>
          </aside>
        )}
        {selectedId && (
          <div className="detail-panel">
            <JobDetail
              key={selectedId}
              job={detail}
              evaluation={evaluation}
              error={error}
              busy={busy}
              refreshing={refreshing}
              onRefresh={refresh}
            />
          </div>
        )}
        {selectedId && (
          <aside className="candidate-panel">
            <label>
              Đầu vào đánh giá
              <select
                name="evaluation_cv_id"
                value={cvId}
                onChange={(e) => {
                  const q = new URLSearchParams(searchParams);
                  if (e.target.value) q.set("cv", e.target.value);
                  else q.delete("cv");
                  setSearchParams(q);
                }}
              >
                <option value="">Hồ sơ đã xác nhận</option>
                {cvVersions.map((v) => (
                  <option key={v.cv_id} value={v.cv_id}>
                    {v.title || "CV đã xác nhận"} ·{" "}
                    {new Date(v.created_at).toLocaleDateString("vi-VN")} ·{" "}
                    {v.draft_version
                      ? `v${v.draft_version}`
                      : v.cv_id.slice(-6)}
                    {v.cv_version?.content_stale ? " · Nội dung cũ" : ""}
                  </option>
                ))}
              </select>
            </label>
            {detail && (
              <section className="company-info-card">
                <h2>Thông tin công ty</h2>
                <strong>{detail.company || "Chưa công bố tên công ty"}</strong>
                <dl>
                  {[
                    ["Địa điểm", detail.location],
                    ["Ngành nghề", detail.industry],
                    ["Kinh nghiệm", detail.experience_level],
                    [
                      "Hạn tuyển",
                      detail.expires_at
                        ? new Date(detail.expires_at).toLocaleDateString(
                            "vi-VN",
                          )
                        : null,
                    ],
                  ].map(([label, value]) => (
                    <React.Fragment key={label}>
                      <dt>{label}</dt>
                      <dd>{value || "Chưa công bố"}</dd>
                    </React.Fragment>
                  ))}
                </dl>
              </section>
            )}

            {!cvId && (
              <MyProfilePanel
                profile={profile}
                profiles={catalog.profiles}
                profileId={profileId}
                onSelect={setProfileId}
                onOpenProfile={onOpenProfile}
              />
            )}
            <MatchingPanel
              inputCVId={cvId}
              postingId={selectedId}
              evaluation={evaluation}
              busy={busy}
              error={error}
              onRetry={() => {
                if (analysisTask?.status === "failed")
                  retryTask(analysisTask.task_id)
                    .then(() => setRetry((v) => v + 1))
                    .catch((e) => setError(e.message));
                else setRetry((v) => v + 1);
              }}
              onUpdateProfile={() => setShowUpdate(true)}
              onOptimizeCV={() => setShowCV(true)}
            />
            {showUpdate && (
              <ProfileSessionPanel
                mode="update"
                profileId={profileId}
                postingId={selectedId}
                profile={profile}
                onProfileConfirmed={updatedProfile}
                onClose={() => setShowUpdate(false)}
              />
            )}
          </aside>
        )}
      </div>
      {showCV && (
        <CVWorkspace
          key={`${profileId}:${selectedId}`}
          profileId={profileId}
          postingId={selectedId}
          jobTitle={detail?.title}
          onClose={() => setShowCV(false)}
        />
      )}
    </>
  );
}
