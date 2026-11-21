import React, { useEffect, useState } from "react";
import { Link, Navigate, useSearchParams } from "react-router-dom";
import { request } from "../../lib/api.js";
import Icon from "../../components/ui/Icon.jsx";
import ResumeLibrary from "../resumes/ResumeLibrary.jsx";
import CVWorkspace from "../../components/CVWorkspace.jsx";
import { useAuth } from "../auth/AuthContext.jsx";
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
  const { user } = useAuth();
  const [jobs, setJobs] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    request("/api/dashboard?saved=true", { signal: controller.signal })
      .then((data) => {
        if (!controller.signal.aborted) setJobs(data.jobs);
      })
      .catch((error) => {
        if (error.name !== "AbortError") setError(error.message);
      });
    return () => controller.abort();
  }, []);
  return (
    <main className="workspace-overview">
      <header className="overview-welcome">
        <div>
          <h1>Hồ sơ cá nhân của {user?.full_name || 'bạn'}</h1>
          <Link className="button-link" to="/workspace/assistant">
            <Icon name="chat" size={17} /> Trợ lý AI
          </Link>
        </div>
        <div className="overview-art" aria-hidden="true">
          <div className="overview-art-paper"><Icon name="file" size={34} /><span /><span /><span /><span /><span /></div>
          <div className="overview-art-check"><Icon name="check" size={25} /></div>
        </div>
      </header>
      <div className="home-feature-grid workspace-stats workspace-saved-jobs">
        <article>
          <span className="stat-icon"><Icon name="bookmark" /></span>
          <span className="workspace-stat">{jobs ? jobs.length : "—"}</span>
          <h2>Việc đã lưu</h2>
          {error && <p className="error" role="alert">{error}</p>}
          {!jobs && !error && <p role="status">Đang tải việc đã lưu…</p>}
          <Link to="/jobs?saved=true">Xem cơ hội đã lưu →</Link>
        </article>
      </div>
      <ResumeLibrary embedded />
    </main>
  );
}
