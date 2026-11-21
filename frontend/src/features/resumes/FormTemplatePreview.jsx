import React, { useEffect, useState } from "react";
import { request } from "../../lib/api.js";
import CVPreviewFrame from "../../components/ui/CVPreviewFrame.jsx";
export default function FormTemplatePreview({ profile, presentation, template }) {
  const [html, setHtml] = useState("");
  const [error, setError] = useState("");
  const [pending, setPending] = useState(true);
  useEffect(() => {
    const controller = new AbortController();
    setPending(true);
    setError("");
    const timer = setTimeout(() => {
      request("/api/profile-drafts/preview", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ profile, presentation }), signal: controller.signal })
        .then((data) => { if (!controller.signal.aborted) { setHtml(data.html); setPending(false); } })
        .catch((failure) => { if (failure.name !== "AbortError" && !controller.signal.aborted) { setError(failure.message); setPending(false); } });
    }, 450);
    return () => { controller.abort(); clearTimeout(timer); };
  }, [profile, presentation]);
  return <div>{pending && <p role="status">Đang cập nhật bản xem trước…</p>}{error && <p role="alert" className="error">{error}</p>}{html && <CVPreviewFrame title="CV từ thông tin đang nhập" srcDoc={html} pageWidth={template?.page_width} pageHeight={template?.page_height} />}</div>;
}
