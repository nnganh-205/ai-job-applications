import React, { useEffect, useState } from "react";
import { Link, Navigate, useSearchParams } from "react-router-dom";
import { request } from "../../services/api.js";
import Icon from "../../components/ui/Icon.jsx";
import { EmptyState } from "../../components/ui/PageState.jsx";
import CVWorkspace from "../../components/CVWorkspace.jsx";
const statuses = {
  queued: "Đang chờ",
  running: "Đang xử lý",
  completed: "Đã hoàn tất",
  failed: "Cần thử lại",
};
export function CVGenerationPage() {
  const [params] = useSearchParams(),
    [title, setTitle] = useState("");
  const posting = params.get("posting");
  const mode = params.get("mode") === "review" ? "review" : "generate";
  const language = params.get("language") === "vi" ? "vi" : "en";
  useEffect(() => {
    setTitle("");
    if (!posting) return;
    const c = new AbortController();
    request("/api/dashboard/jobs/" + encodeURIComponent(posting), {
      signal: c.signal,
    })
      .then((d) => setTitle(d.title))
      .catch(() => {});
    return () => c.abort();
  }, [posting]);
  if (!posting && !params.has("mode"))
    return (
      <Navigate
        replace
        to={
          "/workspace/resumes/new" +
          (params.get("profile")
            ? "?profile=" + encodeURIComponent(params.get("profile"))
            : "")
        }
      />
    );
  return (
    <main>
      <CVWorkspace
        key={
          (params.get("profile") || "") +
          ":" +
          (posting || "") +
          ":" +
          mode +
          ":" +
          language
        }
        profileId={params.get("profile") || undefined}
        postingId={posting || undefined}
        jobTitle={title || undefined}
        initialMode={mode}
        initialLanguage={language}
      />
    </main>
  );
}
export default function WorkspacePage() {
  const [data, setData] = useState(null),
    [error, setError] = useState("");
  useEffect(() => {
    const c = new AbortController();
    Promise.all([
      request("/api/profile-drafts/profiles", { signal: c.signal }),
      request("/api/resumes", { signal: c.signal }),
      request("/api/dashboard?saved=true", { signal: c.signal }),
      request("/api/tasks", { signal: c.signal }),
    ])
      .then(([profiles, resumes, jobs, tasks]) => {
        if (!c.signal.aborted)
          setData({ profiles, resumes, jobs: jobs.jobs, tasks });
      })
      .catch((e) => {
        if (e.name !== "AbortError") setError(e.message);
      });
    return () => c.abort();
  }, []);
  return (
    <main className="workspace-overview">
      <header className="overview-welcome">
        <div>
          <p className="eyebrow">KHÔNG GIAN CỦA BẠN</p>
          <h1>
            Một bước nhỏ hôm nay.
            <br />
            <span>Một cơ hội mới ngày mai.</span>
          </h1>
          <p>
            Chăm chút hồ sơ, chuẩn bị CV và tiếp tục hành trình của riêng bạn.
          </p>
          <Link className="button-link" to="/workspace/assistant">
            <Icon name="spark" size={17} /> Cùng trợ lý chuẩn bị
          </Link>
        </div>
        <div className="overview-art" aria-hidden="true">
          <div className="overview-art-paper">
            <Icon name="file" size={34} />
            <span />
            <span />
            <span />
            <span />
            <span />
          </div>
          <div className="overview-art-check">
            <Icon name="check" size={25} />
          </div>
        </div>
      </header>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {!data && !error && <p role="status">Đang tải workspace…</p>}
      {data && (
        <>
          <div className="home-feature-grid workspace-stats">
            <article>
              <span className="stat-icon">
                <Icon name="user" />
              </span>
              <span className="workspace-stat">{data.profiles.length}</span>
              <h2>Bản hồ sơ đã xác nhận</h2>
              <Link to="/workspace/resumes">Mở thư viện CV →</Link>
            </article>
            <article>
              <span className="stat-icon">
                <Icon name="file" />
              </span>
              <span className="workspace-stat">{data.resumes.length}</span>
              <h2>CV trong thư viện</h2>
              <Link to="/workspace/resumes">Mở thư viện CV →</Link>
            </article>
            <article>
              <span className="stat-icon">
                <Icon name="bookmark" />
              </span>
              <span className="workspace-stat">{data.jobs.length}</span>
              <h2>Việc đã lưu</h2>
              <Link to="/jobs?saved=true">Xem cơ hội đã lưu →</Link>
            </article>
          </div>
          <section>
            <div className="panel-heading">
              <h2>CV gần đây</h2>
              <Link to="/templates">Tạo với mẫu mới ↗</Link>
            </div>
            {data.resumes.length ? (
              data.resumes.slice(0, 4).map((r) => (
                <article className="workspace-row" key={r.resume_id}>
                  <div>
                    <h3>{r.title}</h3>
                    <p>
                      Cập nhật {new Date(r.updated_at).toLocaleString("vi-VN")}
                    </p>
                  </div>
                  <Link to={"/workspace/resumes/" + r.resume_id + "/edit"}>
                    Tiếp tục chỉnh sửa →
                  </Link>
                </article>
              ))
            ) : (
              <EmptyState
                title="Bản CV đầu tiên, bắt đầu từ bạn"
                action={
                  <Link
                    className="button-link secondary-button"
                    to="/workspace/resumes/new"
                  >
                    Tạo CV mới <Icon name="plus" size={15} />
                  </Link>
                }
              >
                Từ hồ sơ đã xác nhận, chọn một thiết kế và kể rõ những điều bạn
                đã làm.
              </EmptyState>
            )}
          </section>
          <section>
            <div className="panel-heading">
              <h2>Tác vụ AI gần đây</h2>
              <Link to="/workspace/assistant">Mở trợ lý AI ↗</Link>
            </div>
            {data.tasks.length ? (
              data.tasks.slice(0, 8).map((t) => (
                <article className="workspace-row" key={t.task_id}>
                  <div>
                    <h3>
                      {t.kind === "assistant"
                        ? "Trợ lý AI"
                        : t.kind === "interview"
                          ? "Luyện phỏng vấn"
                          : t.kind === "cv"
                            ? "Review / tạo CV"
                            : "Đánh giá độ phù hợp"}
                    </h3>
                    <p>
                      <span className={"status-pill " + t.status}>
                        {statuses[t.status]}
                      </span>{" "}
                      · {new Date(t.updated_at).toLocaleString("vi-VN")}
                    </p>
                  </div>
                  <Link
                    to={
                      t.kind === "assistant"
                        ? "/workspace/assistant/" + t.payload.session_id
                        : t.kind === "interview"
                          ? "/workspace/interviews/" + t.payload.session_id
                          : t.kind === "cv"
                            ? "/workspace/resumes/generate?profile=" +
                              t.payload.profile_id +
                              "&mode=" +
                              t.payload.mode +
                              "&language=" +
                              t.payload.language +
                              (t.payload.posting_id
                                ? "&posting=" + t.payload.posting_id
                                : "")
                            : "/jobs/" +
                              t.payload.posting_id +
                              (t.payload.cv_id ? "?cv=" + t.payload.cv_id : "")
                    }
                  >
                    Mở lại →
                  </Link>
                </article>
              ))
            ) : (
              <div className="quiet-empty">
                <Icon name="clock" size={23} />
                <div>
                  <strong>Mọi bước chuẩn bị được lưu lại</strong>
                  <p>
                    Kết quả rà soát CV và đánh giá công việc sẽ xuất hiện tại
                    đây.
                  </p>
                </div>
              </div>
            )}
          </section>
        </>
      )}
    </main>
  );
}
