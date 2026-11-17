import React, { useEffect, useState, useRef } from "react";
import {
  Link,
  useParams,
  useNavigate,
  useBlocker,
  useSearchParams,
} from "react-router-dom";
import { request } from "../../services/api.js";
import ResumeFormBuilder from "../resumes/ResumeFormBuilder.jsx";

const send = (path, body, method = "POST") =>
  request(path, {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

function NavigationGuard({ dirty }) {
  const blocker = useBlocker(
    ({ currentLocation, nextLocation }) =>
      dirty &&
      currentLocation.pathname.slice(
        0,
        currentLocation.pathname.lastIndexOf("/"),
      ) !==
        nextLocation.pathname.slice(0, nextLocation.pathname.lastIndexOf("/")),
  );
  useEffect(() => {
    if (blocker.state === "blocked") {
      if (
        window.confirm(
          "Có thay đổi chưa lưu. Rời trang và bỏ các thay đổi này?",
        )
      )
        blocker.proceed();
      else blocker.reset();
    }
  }, [blocker]);
  return null;
}

export default function ProfileEditor({
  onConfirmed,
  draftId,
  template,
  embedded = false,
  onClose,
  onDirtyChange,
  onComplete,
  resumeId,
}) {
  const { id: routeId } = useParams(),
    navigate = useNavigate();
  const id = draftId || routeId;
  const draftEndpoint = resumeId
    ? `/api/resumes/${resumeId}/source-edit`
    : `/api/profile-drafts/${id}`;
  const completionEvent = useRef(null);
  const [params] = useSearchParams();
  const resumeTemplate = template || params.get("resumeTemplate") || "classic";
  const [refine, setRefine] = useState(true);
  const [draft, setDraft] = useState(null),
    [schema, setSchema] = useState(null),
    [profile, setProfile] = useState(null),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [message, setMessage] = useState("");
  const dirty =
    !!draft && JSON.stringify(draft.profile) !== JSON.stringify(profile);
  useEffect(() => {
    onDirtyChange?.(dirty);
  }, [dirty, onDirtyChange]);
  useEffect(() => {
    const c = new AbortController();
    setDraft(null);
    setProfile(null);
    setError("");
    Promise.all([
      request(draftEndpoint, { signal: c.signal }),
      request("/api/profile-drafts/schema", { signal: c.signal }),
    ])
      .then(([d, s]) => {
        if (!c.signal.aborted) {
          setDraft(d);
          setProfile(d.profile);
          setSchema(s);
        }
      })
      .catch((e) => {
        if (e.name !== "AbortError") setError(e.message);
      });
    return () => c.abort();
  }, [id, draftEndpoint]);
  useEffect(() => {
    const guard = (e) => {
      if (dirty) {
        e.preventDefault();
        e.returnValue = "";
      }
    };
    window.addEventListener("beforeunload", guard);
    return () => window.removeEventListener("beforeunload", guard);
  }, [dirty]);
  async function save() {
    const d = await send(
      draftEndpoint,
      { profile, expected_version: draft.version },
      "PUT",
    );
    setDraft(d);
    setProfile(d.profile);
    return d;
  }
  async function act(confirm) {
    setBusy(true);
    setError("");
    try {
      let d = dirty ? await save() : draft;
      if (resumeId) {
        if (confirm) {
          if (completionEvent.current?.version !== d.version)
            completionEvent.current = {
              version: d.version,
              id: crypto.randomUUID(),
            };
          const result = await send(`${draftEndpoint}/complete`, {
            draft_id: d.draft_id,
            expected_version: d.version,
            event_id: completionEvent.current.id,
          });
          onComplete?.(result);
        } else
          setMessage(
            "Đã lưu bản nháp chỉnh sửa. Chọn Hoàn tất chỉnh sửa để cập nhật CV hiện tại.",
          );
        return;
      }
      if (confirm && d.status !== "confirmed") {
        d = await send(`/api/profile-drafts/${id}/confirm`, {
          expected_version: d.version,
          event_id: crypto.randomUUID(),
        });
        setDraft(d);
        setProfile(d.profile);
        onConfirmed?.(d.confirmed_profile_id);
        setMessage("Đã xác nhận hồ sơ. Lịch sử thay đổi được giữ nguyên.");
      }
      if (confirm && resumeTemplate) {
        const templates = await request("/api/cv/templates");
        const template =
          templates.find((item) => item.id === resumeTemplate) ||
          templates.find((item) => item.id === "classic");
        const resume = await send("/api/resumes", {
          profile_id: d.confirmed_profile_id,
          refine_form: refine,
          title: `CV ${d.profile.contact.full_name || "của tôi"}`.slice(0, 120),
          presentation: {
            template: template.id,
            template_version: template.version,
            font: template.font,
            color: template.color,
          },
        });
        if (onComplete) onComplete(resume);
        else
          navigate(`/workspace/resumes/${resume.resume_id}/edit?view=design`);
      } else if (!confirm)
        setMessage(
          embedded
            ? "Đã lưu bản nháp chỉnh sửa. Chọn Hoàn tất chỉnh sửa để tạo bản CV cập nhật."
            : "Đã lưu bản nháp. Bạn có thể mở lại đường dẫn này để tiếp tục.",
        );
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  async function editConfirmedForm() {
    setBusy(true);
    setError("");
    try {
      const next = await send("/api/profile-drafts", {
        base_profile_id: draft.confirmed_profile_id,
      });
      navigate(
        `/workspace/resumes/new/${next.draft_id}?resumeTemplate=${encodeURIComponent(resumeTemplate)}`,
      );
    } catch (error) {
      setError(error.message);
    } finally {
      setBusy(false);
    }
  }
  if (resumeTemplate && draft && schema)
    return (
      <>
        {!embedded && <NavigationGuard dirty={dirty} />}
        <ResumeFormBuilder
          embedded={embedded}
          onClose={onClose}
          profile={profile}
          initialProfile={draft.initial_profile || draft.profile}
          schema={schema}
          onChange={setProfile}
          busy={busy}
          confirmed={draft.status === "confirmed"}
          dirty={dirty}
          version={draft.version}
          error={error}
          message={message}
          refine={refine}
          setRefine={setRefine}
          onSave={() => act(false)}
          onPreview={() => act(true)}
          onEdit={editConfirmedForm}
        />
      </>
    );
  return (
    <main className="cv-form-builder">
      <p className="eyebrow">TẠO CV</p>
      <h1>Thông tin CV của bạn</h1>
      {error ? (
        <p className="error" role="alert">
          {error}
        </p>
      ) : (
        <p role="status">Đang mở form thông tin…</p>
      )}
      <Link to="/workspace/resumes">← Thư viện CV</Link>
    </main>
  );
}
