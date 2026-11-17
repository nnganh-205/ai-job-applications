import React, { useEffect, useRef, useState } from "react";
import {
  useNavigate,
  useSearchParams,
  useParams,
  Navigate,
} from "react-router-dom";
import { send } from "./ResumeLibrary.jsx";

/** Every create-CV entry opens the same editable form, never the AI task console. */
export default function ResumeNew() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const template = params.get("template") || "classic";
  const profile = params.get("profile") || null;
  const pending = useRef(null);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let cancelled = false;
    const key = JSON.stringify([profile, template, attempt]);
    if (pending.current?.key !== key) {
      pending.current = {
        key,
        promise: send("/api/profile-drafts", { base_profile_id: profile }),
      };
    }
    setError("");
    pending.current.promise
      .then((draft) => {
        if (!cancelled)
          navigate(
            `/workspace/resumes/new/${draft.draft_id}?resumeTemplate=${encodeURIComponent(template)}`,
            { replace: true },
          );
      })
      .catch((error) => {
        if (!cancelled) setError(error.message);
      });
    return () => {
      cancelled = true;
    };
  }, [profile, template, attempt, navigate]);
  return (
    <main>
      <p className="eyebrow">TẠO CV MỚI</p>
      <h1>Chuẩn bị form thông tin CV</h1>
      {error ? (
        <>
          <p role="alert" className="error">
            {error}
          </p>
          <button onClick={() => setAttempt((n) => n + 1)}>Thử lại</button>
        </>
      ) : (
        <p role="status">Đang mở form nhập thông tin…</p>
      )}
    </main>
  );
}

export function LegacyResumeForm() {
  const { id } = useParams();
  const [params] = useSearchParams();
  return (
    <Navigate
      replace
      to={`/workspace/resumes/new/${id}?resumeTemplate=${encodeURIComponent(params.get("resumeTemplate") || "classic")}`}
    />
  );
}
