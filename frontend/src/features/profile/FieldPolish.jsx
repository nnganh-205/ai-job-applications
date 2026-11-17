import React, { useEffect, useRef, useState } from "react";
import { request } from "../../services/api.js";

export default function FieldPolish({ value, field, disabled, onApply }) {
  const [busy, setBusy] = useState(false),
    [suggestion, setSuggestion] = useState(null),
    [error, setError] = useState("");
  const version = useRef(0);
  const [undo, setUndo] = useState(null);
  useEffect(() => {
    version.current++;
    setSuggestion(null);
    setError("");
    setBusy(false);
  }, [value]);
  async function polish(e) {
    e.preventDefault();
    e.stopPropagation();
    const current = ++version.current;
    setBusy(true);
    setError("");
    try {
      const result = await request("/api/profile-drafts/polish", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: value, field }),
      });
      if (version.current === current) setSuggestion(result);
    } catch (e) {
      if (version.current === current) setError(e.message);
    } finally {
      if (version.current === current) setBusy(false);
    }
  }
  if (!value?.trim()) return null;
  return (
    <div className="cv-wording-panel">
      <button type="button" disabled={disabled || busy} onClick={polish}>
        {busy ? "Đang tinh chỉnh…" : "✦ Tinh chỉnh câu từ"}
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
          <div>
            <strong>Gợi ý viết cho CV</strong>
            <div className="writer-before-after">
              <strong>Trước khi chỉnh</strong>
              <p className="cv-wording-text">{suggestion.original}</p>
              <strong>Đề xuất sau khi chỉnh</strong>
              <p className="cv-wording-text">{suggestion.proposed}</p>
            </div>
            <small>
              Kiểm tra để chắc rằng câu viết lại đúng với việc bạn đã làm.
            </small>
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
          <small>Nội dung hiện tại đã phù hợp; chưa có đề xuất thay đổi.</small>
        ))}
    </div>
  );
}
