import React, { useEffect, useState, useRef } from "react";
import {
  Link,
  useParams,
  useNavigate,
  useBlocker,
  useSearchParams,
} from "react-router-dom";
import { request } from "../../lib/api.js";
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
  initialPresentation,
}) {
  const { id: routeId } = useParams(),
    navigate = useNavigate();
  const id = draftId || routeId;
  const draftEndpoint = resumeId
    ? `/api/resumes/${resumeId}/source-edit`
    : `/api/profile-drafts/${id}`;
  const completionEvent = useRef(null);
  const [params, setParams] = useSearchParams();
  const resumeTemplate = template || params.get("resumeTemplate") || "classic";
  const profileUpdate = params.get("profileUpdate") === "1";
  const returnTo = /^\/jobs(?:\/|\?|$)/.test(params.get("returnTo") || "")
    ? params.get("returnTo")
    : "/jobs";
  const [refine, setRefine] = useState(false);
  const [templates, setTemplates] = useState([]);
  const [photoAssetId, setPhotoAssetId] = useState(initialPresentation?.photo_asset_id || null);
  const [returnAfterSave, setReturnAfterSave] = useState(false);
  const [draft, setDraft] = useState(null),
    [schema, setSchema] = useState(null),
    [profile, setProfile] = useState(null),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [message, setMessage] = useState("");
  const selectedTemplate = templates.find((item) => item.id === resumeTemplate);
  const basePresentation = draft?.presentation || initialPresentation || {};
  const presentation = {
    ...basePresentation,
    template: resumeTemplate,
    template_version: selectedTemplate?.version || basePresentation.template_version || 3,
    font: basePresentation.template === resumeTemplate ? basePresentation.font || "sans" : selectedTemplate?.font || "sans",
    color: basePresentation.template === resumeTemplate ? basePresentation.color || "#000000" : selectedTemplate?.color || "#000000",
    font_size: basePresentation.template === resumeTemplate ? basePresentation.font_size || selectedTemplate?.font_size || 10 : selectedTemplate?.font_size || 10,
    line_height: basePresentation.template === resumeTemplate ? basePresentation.line_height || selectedTemplate?.line_height || 1.4 : selectedTemplate?.line_height || 1.4,
    photo_asset_id: photoAssetId,
  };
  const dirty = !!draft && (JSON.stringify(draft.profile) !== JSON.stringify(profile) ||
    (!resumeId && !profileUpdate && JSON.stringify(draft.presentation || {}) !== JSON.stringify(presentation)));
  useEffect(() => {
    onDirtyChange?.(dirty);
  }, [dirty, onDirtyChange]);
  useEffect(() => {
    if (returnAfterSave) navigate(returnTo);
  }, [returnAfterSave, navigate, returnTo]);
  useEffect(() => {
    const c = new AbortController();
    setDraft(null);
    setProfile(null);
    setError("");
    Promise.all([
      request(draftEndpoint, { signal: c.signal }),
      request("/api/profile-drafts/schema", { signal: c.signal }),
      request("/api/cv/templates", { signal: c.signal }),
    ])
      .then(([d, s, choices]) => {
        if (!c.signal.aborted) {
          setDraft(d);
          setProfile(d.profile);
          setSchema(s);
          setTemplates(choices);
          setPhotoAssetId(d.presentation?.photo_asset_id || initialPresentation?.photo_asset_id || null);
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
      { profile, expected_version: draft.version, ...(!resumeId && !profileUpdate ? { presentation } : {}) },
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
      if (confirm && profileUpdate) {
        setReturnAfterSave(true);
        return;
      }
      if (confirm && resumeTemplate) {
        if (!selectedTemplate) throw new Error("Chọn mẫu CV trước khi tạo bản CV.");
        const resume = await send("/api/resumes", {
          profile_id: d.confirmed_profile_id,
          refine_form: refine,
          title: `CV ${d.profile.contact.full_name || "của tôi"}`.slice(0, 120),
          presentation,
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
        presentation,
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
  async function uploadPhoto(file) {
    if (!file) return;
    setBusy(true); setError("");
    try {
      const body = new FormData(); body.append("file", file);
      const asset = await request("/api/assets/photos", { method: "POST", body });
      setPhotoAssetId(asset.asset_id);
    } catch (failure) { setError(failure.message); }
    finally { setBusy(false); }
  }
  function chooseTemplate(item) {
    const next = new URLSearchParams(params); next.set("resumeTemplate", item.id);
    setParams(next, { replace: true });
  }
  if (resumeTemplate && draft && schema)
    return (
      <>
        {!embedded && <NavigationGuard dirty={dirty} />}
        {draft.warnings?.length > 0 && <details className="cv-form-builder">
          <summary>Các thông tin trích xuất cần kiểm tra ({draft.warnings.length})</summary>
          <ul>{draft.warnings.map((warning, index) => <li key={index}>{warning}</li>)}</ul>
        </details>}
        <ResumeFormBuilder
          embedded={embedded}
          onClose={onClose}
          profile={profile}
          template={profileUpdate ? undefined : selectedTemplate}
          templates={templates}
          presentation={presentation}
          onTemplateChange={!embedded && !profileUpdate ? chooseTemplate : null}
          onPhotoUpload={!embedded && !profileUpdate ? uploadPhoto : null}
          onPhotoRemove={() => setPhotoAssetId(null)}
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
          profileUpdate={profileUpdate}
        />
      </>
    );
  return (
    <main className="cv-form-builder">
      <h1>Thông tin CV của bạn</h1>
      {error ? (
        <p className="error" role="alert">
          {error}
        </p>
      ) : (
        <p role="status">Đang mở form thông tin…</p>
      )}
      <Link to="/workspace">← Tổng quan</Link>
    </main>
  );
}
