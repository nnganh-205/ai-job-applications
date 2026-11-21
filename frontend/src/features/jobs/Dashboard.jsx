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
} from "../../lib/tasks.js";
import { request } from "../../lib/api.js";
import { getDashboard, jobRequest } from "../../lib/jobs.js";
import { JobSkeletons } from "../../components/ui/PageState.jsx";
import JobCard from "../../components/JobCard.jsx";
import JobDetail from "../../components/JobDetail.jsx";
import MatchingPanel from "../../components/MatchingPanel.jsx";
import SearchFilters from "../../components/SearchFilters.jsx";

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
  function openProfileUpdate() {
    const returnQuery = new URLSearchParams(searchParams);
    returnQuery.delete("cv");
    const returnTo = `/jobs/${selectedId}${returnQuery.size ? `?${returnQuery}` : ""}`;
    navigate(`/workspace/resumes/new?${new URLSearchParams({
      profile: profileId,
      profileUpdate: "1",
      returnTo,
    })}`);
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
  const [detail, setDetail] = useState(null);
  const [evaluation, setEvaluation] = useState(null);
  const [catalogBusy, setCatalogBusy] = useState(true);
  const [catalogError, setCatalogError] = useState("");
  const [busy, setBusy] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [reload, setReload] = useState(0);
  const [retry, setRetry] = useState(0);

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
    if (profileId) {
      try {
        localStorage.setItem("kltn.confirmedProfileId", profileId);
      } catch {
        /* Only the ID is persisted in the browser. */
      }
    }
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
      setMessage(result.errors?.length ? "Một số nguồn chưa cập nhật được." : "Danh sách đã cập nhật.");
      setReload((value) => value + 1);
      if (selectedId && result.fetched > 0 && !result.cooldown)
        setRetry((value) => value + 1);
    } catch (error) {
      setMessage(`Chưa cập nhật được danh sách: ${error.message}`);
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
              <h1>Tìm kiếm việc làm</h1>
              <p>
                Khám phá cơ hội nghề nghiệp phù hợp với kỹ năng và kinh nghiệm
                của bạn.
              </p>
            </div>
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
      {message && (
        <p className="notice" role="status">
          {message}
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
            />
          </div>
        )}
        {selectedId && (
          <aside className="candidate-panel">
            {detail && (
              <section className="company-info-card">
                <h2>Thông tin công ty</h2>
                <strong>{detail.company || "Chưa công bố tên công ty"}</strong>
                <dl>
                  {[
                    ["Địa điểm", detail.location],
                    ["Ngành nghề", detail.industry],
                    ["Kinh nghiệm", detail.experience_level],
                  ].map(([label, value]) => (
                    <React.Fragment key={label}>
                      <dt>{label}</dt>
                      <dd>{value || "Chưa công bố"}</dd>
                    </React.Fragment>
                  ))}
                </dl>
              </section>
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
              onUpdateProfile={openProfileUpdate}
            />
          </aside>
        )}
      </div>
    </>
  );
}
