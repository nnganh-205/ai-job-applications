import React, { useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams, useParams, Navigate, Link } from "react-router-dom";
import { send } from "./ResumeLibrary.jsx";
import { request } from "../../lib/api.js";
import TemplatePicker from "./TemplatePicker.jsx";

export default function ResumeNew() {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const [items, setItems] = useState(null);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const pending = useRef(null);
  const templateId = params.get("template") || (params.get("profileUpdate") === "1" ? "classic" : "");
  const profile = params.get("profile") || null;
  const existingDraft = params.get("draft") || null;
  const profileUpdate = params.get("profileUpdate") === "1";
  const returnTo = params.get("returnTo") || "";
  const selected = items?.find((item) => item.id === templateId);
  useEffect(() => {
    const controller = new AbortController();
    request("/api/cv/templates", { signal: controller.signal }).then(setItems).catch((failure) => { if (failure.name !== "AbortError") setError(failure.message); });
    return () => controller.abort();
  }, [attempt]);
  useEffect(() => {
    if (!selected) return;
    let cancelled = false;
    const key = JSON.stringify([profile, selected.id, existingDraft, profileUpdate, returnTo, attempt]);
    if (pending.current?.key !== key) {
      pending.current = { key, promise: existingDraft ? Promise.resolve({ draft_id: existingDraft }) : send("/api/profile-drafts", {
        base_profile_id: profile,
        presentation: { template: selected.id, template_version: selected.version, font: selected.font, color: selected.color, font_size: selected.font_size, line_height: selected.line_height },
      }) };
    }
    setError("");
    pending.current.promise.then((draft) => {
      if (!cancelled) navigate(`/workspace/resumes/new/${draft.draft_id}?${new URLSearchParams({ resumeTemplate: selected.id, ...(profileUpdate ? { profileUpdate: "1" } : {}), ...(returnTo ? { returnTo } : {}) })}`, { replace: true });
    }).catch((failure) => { if (!cancelled) setError(failure.message); });
    return () => { cancelled = true; };
  }, [selected, profile, existingDraft, profileUpdate, returnTo, attempt, navigate]);
  return <main className="template-gallery template-picker-page">
    <Link to="/workspace">← Tổng quan</Link>
    <h1>Chọn mẫu CV</h1>
    {error && <div><p role="alert" className="error">{error}</p><button onClick={() => setAttempt((value) => value + 1)}>Thử lại</button></div>}
    {!items && !error && <p role="status">Đang tải các mẫu CV…</p>}
    {selected && !error && <p role="status">Đang chuẩn bị form…</p>}
    {items && !selected && <TemplatePicker items={items} onSelect={(item) => { const next = new URLSearchParams(params); next.set("template", item.id); setParams(next); }} />}
  </main>;
}
export function LegacyResumeForm() {
  const { id } = useParams();
  const [params] = useSearchParams();
  return <Navigate replace to={`/workspace/resumes/new?${new URLSearchParams({ draft: id, ...(params.get("resumeTemplate") ? { template: params.get("resumeTemplate") } : {}) })}`} />;
}
