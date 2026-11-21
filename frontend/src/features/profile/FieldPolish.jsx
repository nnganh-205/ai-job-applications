import React, { useEffect, useRef, useState } from "react";
import { request } from "../../lib/api.js";

export default function FieldPolish({ value, field, disabled, onApply }) {
  const [busy, setBusy] = useState(false),
    [suggestion, setSuggestion] = useState(null),
    [error, setError] = useState("");
  const version = useRef(0);
  const controller = useRef(null);
  const [undo, setUndo] = useState(null);
  useEffect(() => {
    version.current++;
    controller.current?.abort();
    setSuggestion(null);
    setError("");
    setBusy(false);
  }, [value]);
  useEffect(() => () => { version.current++; controller.current?.abort(); }, []);
  async function polish(e) {
    e.preventDefault();
    e.stopPropagation();
    const current = ++version.current;
    controller.current?.abort();
    const abort = new AbortController();
    controller.current = abort;
    setBusy(true);
    setError("");
    try {
      const result = await request("/api/profile-drafts/polish", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: value, field }),
        signal: abort.signal,
      });
      if (version.current === current) setSuggestion(result);
    } catch (e) {
      if (version.current === current && e.name !== "AbortError") setError(e.message);
    } finally {
      if (version.current === current) setBusy(false);
    }
  }
  if (!value?.trim()) return null;
  return (
    <div className="cv-wording-panel">
      <button type="button" disabled={disabled || busy} onClick={polish}>
        {busy ? "Đang tinh chỉnh…" : "Tinh chỉnh câu từ"}
      </button>
      {error && <small role="alert">{error}</small>}
      {undo && value === undo.after && (
        <button
          type="button"
          disabled={disabled || busy}
          onClick={(e) => {
            e.preventDefault();
            e.stopPropagation();
            onApply(undo.before);
            setUndo(null);
          }}
        >
          Hoàn tác chỉnh câu
        </button>
      )}
      {suggestion &&
        (suggestion.changed ? (
          <div className="writer-inline-suggestion">
            <span className="writer-inline-kicker">Đề xuất tinh chỉnh</span>
            <p className="cv-wording-text">{suggestion.proposed}</p>
            <button
              type="button"
              disabled={disabled}
              onClick={(e) => {
                e.preventDefault();
                e.stopPropagation();
                setUndo({ before: value, after: suggestion.proposed });
                onApply(suggestion.proposed);
                setSuggestion(null);
              }}
            >
              Áp dụng cách viết
            </button>
            <button
              type="button"
              onClick={(e) => {
                e.preventDefault();
                setSuggestion(null);
              }}
            >
              Giữ nguyên
            </button>
          </div>
        ) : (
          null
        ))}
    </div>
  );
}
