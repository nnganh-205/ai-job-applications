import React, { useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { extractCVToForm } from "../../lib/profileImport.js";

export default function ImportProfile() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const input = useRef(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const template = params.get("resumeTemplate") || params.get("template") || "";
  async function upload(event) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    setBusy(true);
    setError("");
    try {
      const draft = await extractCVToForm(file);
      navigate(`/workspace/resumes/new?${new URLSearchParams({ draft: draft.draft_id, ...(template ? { template } : {}) })}`, { replace: true });
    } catch (error) {
      setError(error.message);
    } finally {
      setBusy(false);
    }
  }
  return <main className="cv-form-builder">
    <h1>Điền form từ CV có sẵn</h1>
    <p>Chọn PDF hoặc DOCX có văn bản, tối đa 5 MB. Thông tin được điền sẵn vào form để bạn chỉnh sửa.</p>
    <input ref={input} type="file" accept=".pdf,.docx" hidden onChange={upload} disabled={busy} />
    <button type="button" disabled={busy} onClick={() => input.current?.click()}>
      {busy ? "Đang tách thông tin CV…" : "Chọn CV từ máy"}
    </button>
    {busy && <p role="status">Đang đọc CV và chuẩn bị form thông tin…</p>}
    {error && <p className="error" role="alert">{error}</p>}
    <p><Link to="/workspace">← Tổng quan</Link></p>
  </main>;
}
