import React, { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { request } from "../services/api.js";

export default function CVVersionNotice({
  cvId,
  postingId,
  allowActions = true,
}) {
  const [status, setStatus] = useState(null),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  const navigate = useNavigate(),
    event = useRef(null);
  useEffect(() => {
    if (!cvId) return;
    const c = new AbortController();
    let running = false;
    setStatus(null);
    setError("");
    async function refresh() {
      if (running || document.visibilityState === "hidden") return;
      running = true;
      try {
        const s = await request(`/api/cv/versions/${cvId}/status`, {
          signal: c.signal,
          timeoutMs: 15000,
        });
        if (!c.signal.aborted) {
          setStatus(s);
          setError("");
        }
      } catch (e) {
        if (!c.signal.aborted)
          setError(
            "Chưa kiểm tra được phiên bản CV. Kết quả bên dưới vẫn thuộc bản CV đã chọn.",
          );
      } finally {
        running = false;
      }
    }
    refresh();
    const timer = setInterval(refresh, 30000);
    window.addEventListener("focus", refresh);
    document.addEventListener("visibilitychange", refresh);
    return () => {
      c.abort();
      clearInterval(timer);
      window.removeEventListener("focus", refresh);
      document.removeEventListener("visibilitychange", refresh);
    };
  }, [cvId]);
  async function useLatest(task) {
    setBusy(true);
    setError("");
    try {
      const fresh = await request(`/api/cv/versions/${cvId}/status`);
      setStatus(fresh);
      let latest = fresh.latest_published_cv_id;
      if (!latest) {
        if (event.current?.version !== fresh.current_version)
          event.current = {
            version: fresh.current_version,
            id: crypto.randomUUID(),
          };
        const result = await request(
          `/api/resumes/${fresh.resume_id}/publish`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              expected_version: fresh.current_version,
              event_id: event.current.id,
            }),
          },
        );
        latest = result.cv_id;
      }
      navigate(
        task === "tailor"
          ? `/workspace/assistant?cv=${latest}&job=${postingId}&task=tailor`
          : `/jobs/${postingId}?cv=${latest}`,
      );
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  if (!cvId) return null;
  return (
    <section
      className={
        "cv-version-notice" + (status?.content_stale ? " is-stale" : "")
      }
      aria-label="Phiên bản CV đang sử dụng"
    >
      <small>
        Đầu vào: {status?.title || "CV đã chọn"}
        {status?.source_version
          ? ` · phiên bản ${status.source_version}`
          : ` · ${cvId.slice(-6)}`}
      </small>
      {status?.content_stale && (
        <p role="status">
          CV đã được sửa lên phiên bản {status.current_version}. Kết quả này
          dùng nội dung cũ, cần đánh giá lại nếu bạn muốn dùng CV mới.
        </p>
      )}
      {status?.version_changed && !status.content_stale && (
        <p>
          Nội dung CV không đổi; phiên bản mới có thể có thiết kế khác. PDF cũ
          vẫn giữ thiết kế tại lúc xuất.
        </p>
      )}
      {status?.has_editing_draft && (
        <p>
          Có bản nháp đang sửa chưa áp dụng; bản nháp đó chưa được dùng để đánh
          giá.
        </p>
      )}
      {error && <p role="alert">{error}</p>}
      <div>
        {status?.resume_id && (
          <Link to={`/workspace/resumes/${status.resume_id}/edit`}>
            Mở CV hiện tại
          </Link>
        )}
        {allowActions && postingId && status?.resume_id && (
          <>
            {status.content_stale && (
              <button
                type="button"
                disabled={busy}
                onClick={() => useLatest("evaluate")}
              >
                {busy ? "Đang chuẩn bị…" : "Đánh giá CV mới nhất"}
              </button>
            )}
            <button
              type="button"
              disabled={busy}
              onClick={() => useLatest("tailor")}
            >
              Điều chỉnh CV mới nhất theo JD
            </button>
          </>
        )}
      </div>
    </section>
  );
}
