import React, { useState, useEffect } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { request } from "../../services/api.js";
import ProfileSessionPanel from "../../components/ProfileSessionPanel.jsx";
import ProfileForm, { sections, label } from "./ProfileForm.jsx";

export default function ImportProfile({ onConfirmed }) {
  const [file, setFile] = useState(null),
    [draft, setDraft] = useState(null),
    [profile, setProfile] = useState(null),
    [schema, setSchema] = useState(null),
    [section, setSection] = useState("contact"),
    [chat, setChat] = useState(false),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const resumeTemplate = params.get("resumeTemplate");
  useEffect(() => {
    const c = new AbortController();
    request("/api/profile-drafts/schema", { signal: c.signal })
      .then(setSchema)
      .catch((e) => {
        if (e.name !== "AbortError") setError(e.message);
      });
    return () => c.abort();
  }, []);
  function confirmed(id) {
    onConfirmed(id);
    navigate("/workspace/resumes");
  }
  async function extract(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const data = new FormData();
      data.append("file", file);
      const d = await request("/api/profiles/extract", {
        method: "POST",
        body: data,
      });
      setDraft(d);
      setProfile(d.profile);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  async function confirm() {
    setBusy(true);
    setError("");
    try {
      await request(`/api/profiles/${draft.thread_id}/confirm`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ profile }),
      });
      if (resumeTemplate) {
        const form = await request("/api/profile-drafts", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ base_profile_id: draft.thread_id }),
        });
        onConfirmed(draft.thread_id);
        navigate(
          `/workspace/resumes/new/${form.draft_id}?resumeTemplate=${encodeURIComponent(resumeTemplate)}`,
        );
      } else confirmed(draft.thread_id);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <main>
      <p className="eyebrow">Hồ sơ của bạn</p>
      <h1>Tạo hồ sơ từ CV</h1>
      <p>
        Tải lên PDF/DOCX có văn bản, tối đa 5 MB. Kiểm tra dữ kiện trước khi xác
        nhận.
      </p>
      <form onSubmit={extract}>
        <label>
          CV của bạn
          <input
            type="file"
            accept=".pdf,.docx"
            disabled={busy}
            onChange={(e) => setFile(e.target.files[0] || null)}
          />
        </label>
        <button disabled={!file || busy}>
          {busy ? "Đang xử lý…" : "Đọc thông tin CV"}
        </button>
      </form>
      <button
        className="secondary-button"
        disabled={busy}
        onClick={() => setChat(!chat)}
      >
        Tạo hồ sơ qua trò chuyện
      </button>
      {chat && (
        <ProfileSessionPanel
          mode="build"
          onProfileConfirmed={confirmed}
          onClose={() => setChat(false)}
        />
      )}
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {draft && schema && (
        <section>
          <h2>Kiểm tra kết quả trích xuất</h2>
          {draft.warnings.length > 0 && (
            <details open>
              <summary>Các mục cần kiểm tra</summary>
              <ul>
                {draft.warnings.map((w, i) => (
                  <li key={i}>{w}</li>
                ))}
              </ul>
            </details>
          )}
          <nav className="section-tabs">
            {sections.map((s) => (
              <button key={s} disabled={busy} onClick={() => setSection(s)}>
                {label(s)}
              </button>
            ))}
          </nav>
          <ProfileForm
            schema={schema}
            profile={profile}
            section={section}
            onChange={setProfile}
            disabled={busy}
          />
          <button disabled={busy} onClick={confirm}>
            Tôi đã kiểm tra — xác nhận lưu
          </button>
        </section>
      )}
    </main>
  );
}
