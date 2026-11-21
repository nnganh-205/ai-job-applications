import React, { useEffect, useRef, useState } from "react";
import {
  changedLineIndices, applyWriterSuggestions, groupWriterSuggestions, isChangedSuggestion,
} from "./writerEdits.js";
import { request } from "../../lib/api.js";
import { writingQuality } from "../resumes/writingQuality.js";

const styles = [
  ["professional", "Chuyên nghiệp"], ["concise", "Ngắn gọn"],
  ["detailed", "Rõ cách thực hiện"], ["quantified", "Ưu tiên kết quả đã có"],
];

export default function AIWriter({ section, field, initialValue, entry, value = [], disabled,
  onApply, onGenerate, renderSource, action = null }) {
  const [style, setStyle] = useState("professional");
  const [count, setCount] = useState(4);
  const [scope, setScope] = useState("changed");
  const [tasks, setTasks] = useState(""), [tools, setTools] = useState(""), [results, setResults] = useState("");
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [notesOpen, setNotesOpen] = useState(false);
  const [busy, setBusy] = useState(false), [error, setError] = useState("");
  const [preview, setPreview] = useState(null), [selected, setSelected] = useState([]);
  const [undo, setUndo] = useState(null);
  const controller = useRef(null), version = useRef(0), baseline = useRef(initialValue || value);
  const handledAction = useRef(null);
  const context = JSON.stringify({ section, field, entry, value });
  const currentContext = useRef(context);
  currentContext.current = context;
  const changed = changedLineIndices(value, baseline.current);
  const targets = action?.issue
    ? value.flatMap((text,index) => writingQuality({description:[text]}).checks
        .some((check) => check.id === action.issue && check.status === "warning") ? [index] : [])
    : !onGenerate && scope === "changed" && changed.length
      ? changed : value.flatMap((text, index) => text.trim() ? [index] : []);
  const visible = (preview?.bullets || []).flatMap((bullet, index) => isChangedSuggestion(bullet) ? [index] : []);
  const groups = preview ? groupWriterSuggestions(value, preview.targets, preview.bullets) : [];

  useEffect(() => {
    version.current++;
    controller.current?.abort();
    setPreview(null);
    setSelected([]);
    setError("");
    setBusy(false);
  }, [context, tasks, tools, results, style, count, scope]);
  useEffect(() => () => { version.current++; controller.current?.abort(); }, []);
  useEffect(() => {
    if (!action?.nonce || handledAction.current === action.nonce) return;
    if (action.style && action.style !== style) { setStyle(action.style); return; }
    handledAction.current = action.nonce;
    if (action.edits?.length) {
      const edit = action.edits.find((item) => item.field === field);
      if (!edit || JSON.stringify(edit.original) !== JSON.stringify(value)) return;
      version.current++;
      controller.current?.abort();
      const bullets = edit.proposed.flatMap((text, index) => text !== edit.original[index]
        ? [{ text, sources: [edit.original[index]], origin: "editorial", change_kind: "editorial_quickfix" }] : []);
      setBusy(false); setError("");
      setPreview({ bullets, questions: [], status: "review_required", originalLines: [...value],
        targets: value.map((_, index) => index), contextKey: context });
      setSelected(bullets.map((_, index) => index));
      return;
    }
    generate();
  }, [action?.nonce, style]);

  async function generate() {
    if (disabled) return;
    controller.current?.abort();
    const abort = new AbortController();
    controller.current = abort;
    const current = ++version.current;
    const contextKey = context;
    setBusy(true); setError(""); setPreview(null);
    try {
      const lines = onGenerate ? value : targets.map((i) => value[i]);
      const issues = action?.issue ? [action.issue] : writingQuality({description:lines}).checks
        .filter((check) => check.status === "warning").map((check) => check.id);
      const payload = { section, entry, text: lines.join("\n"),
        ...(field ? { field } : {}), tasks, tools, results, style, count, issues };
      const response = onGenerate ? await onGenerate(payload, abort.signal)
        : await request("/api/profile-drafts/writer", { method: "POST",
          headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload), signal: abort.signal });
      if (current !== version.current || currentContext.current !== contextKey) return;
      setPreview({ ...response, bullets: response.bullets || [], originalLines: [...value], targets: [...targets], contextKey });
      setSelected((response.bullets || []).flatMap((b, i) => isChangedSuggestion(b) ? [i] : []));
    } catch (error) {
      if (current === version.current && error.name !== "AbortError") setError(error.message);
    } finally { if (current === version.current) setBusy(false); }
  }

  async function apply(indices = selected) {
    if (!preview || disabled || busy || !indices.length || preview.contextKey !== currentContext.current) return;
    setBusy(true); setError("");
    try {
      const before = [...value];
      const next = applyWriterSuggestions(before, preview.targets, indices.map((i) => ({
        ...preview.bullets[i], targetIndices: groups.find((g) => g.proposalIndex === i)?.indices || [],
      })));
      await onApply(next, preview, indices, "replace");
      if (!onGenerate) { setUndo({ before, after: next }); baseline.current = [...next]; }
      setPreview(null); setSelected([]);
    } catch (error) { setError(error.message); }
    finally { setBusy(false); }
  }

  function dismiss(index) {
    setSelected((old) => old.filter((i) => i !== index));
    setPreview((old) => old ? { ...old, dismissed: [...(old.dismissed || []), index] } : old);
  }
  function suggestions(anchor) {
    const matches = groups.filter((g) => g.anchor === anchor && visible.includes(g.proposalIndex)
      && !preview.dismissed?.includes(g.proposalIndex));
    if (!matches.length) return null;
    return <div className="writer-inline-suggestions" aria-label="Đề xuất tinh chỉnh">
      {matches.map(({ bullet, proposalIndex, indices }) => <div className="writer-inline-suggestion" key={proposalIndex}>
        <span className="writer-inline-kicker">Đề xuất{indices.length > 1 ? ` · Gộp ${indices.length} câu nguồn` : ""}</span>
        <label className="writer-suggestion-choice">
          <input type="checkbox" aria-label={`Chọn đề xuất ${proposalIndex + 1}`} checked={selected.includes(proposalIndex)}
            disabled={busy || disabled} onChange={(event) => setSelected((old) => event.target.checked
              ? [...old, proposalIndex].sort((a, b) => a - b) : old.filter((i) => i !== proposalIndex))} />
          <span>{bullet.replacement_lines?.length > 1
            ? bullet.replacement_lines.map((line,index) => <span key={index} style={{display:'block'}}>• {line}</span>)
            : bullet.text}</span>
        </label>
        <div className="writer-inline-actions">
          <button type="button" disabled={busy || disabled} onClick={() => apply([proposalIndex])}>Dùng câu này</button>
          <button type="button" disabled={busy || disabled} onClick={() => dismiss(proposalIndex)}>Bỏ qua</button>
        </div>
      </div>)}
    </div>;
  }

  return <div className="ai-writer writer-inline writer-refinement" onClick={(event) => event.stopPropagation()}>
    {renderSource ? renderSource(suggestions, !!preview) : value.map((line, index) =>
      <div className="writer-source-line" key={index}><p>{line}</p>{suggestions(index)}</div>)}
    {suggestions(null)}
    <div className="writer-toolbar">
      <div className="writer-split">
        <button type="button" disabled={busy || disabled} className="ai-writer-generate" onClick={() => generate()}>
          {busy ? <span role="status">Đang tinh chỉnh…</span> : preview ? "Thử cách viết khác" : "Tinh chỉnh"}
        </button>
        <button type="button" className="writer-menu-toggle" aria-label="Tùy chọn tinh chỉnh" aria-expanded={settingsOpen}
          disabled={busy || disabled} onClick={() => setSettingsOpen((open) => !open)}>⌄</button>
      </div>
    </div>
    {settingsOpen && <div className="writer-inline-options">
      <label>Phong cách<select aria-label="Phong cách tinh chỉnh" value={style} disabled={busy || disabled} onChange={(event) => setStyle(event.target.value)}>
        {styles.map(([key, label]) => <option key={key} value={key}>{label}</option>)}
      </select></label>
      <label>Số đề xuất tối đa<select aria-label="Số đề xuất tối đa" value={count} disabled={busy || disabled} onChange={(event) => setCount(Number(event.target.value))}>
        {[1, 2, 3, 4, 5, 6].map((n) => <option key={n} value={n}>{n}</option>)}
      </select></label>
      {!onGenerate && <label>Phạm vi<select aria-label="Phạm vi tinh chỉnh" value={scope} disabled={busy || disabled} onChange={(event) => setScope(event.target.value)}>
        <option value="changed">{changed.length ? `${changed.length} câu mới hoặc vừa sửa` : "Các câu trong ô này"}</option>
        <option value="all">Toàn bộ câu trong ô này</option>
      </select></label>}
    </div>}
    {!onGenerate && <details className="writer-inline-notes" open={notesOpen} onToggle={(event) => setNotesOpen(event.currentTarget.open)}>
      <summary>Bổ sung dữ kiện cho đề xuất · tùy chọn</summary>
      <label>Công việc thực tế<textarea aria-label="Công việc bổ sung" value={tasks} disabled={busy || disabled}
        onChange={(event) => setTasks(event.target.value)} placeholder="Mỗi dòng một việc bạn trực tiếp thực hiện" /></label>
      <label>Công cụ hoặc phương pháp<input aria-label="Công cụ bổ sung" value={tools} disabled={busy || disabled} onChange={(event) => setTools(event.target.value)} /></label>
      <label>Kết quả đã có<textarea aria-label="Kết quả bổ sung" value={results} disabled={busy || disabled}
        onChange={(event) => setResults(event.target.value)} placeholder="Chỉ thêm kết quả có thật; có thể để trống" /></label>
    </details>}
    {error && <p className="error" role="alert">{error}</p>}
    {preview && <div className="writer-inline-status" aria-live="polite">
      {preview.error_message && <p className="error" role="alert">{preview.error_message}</p>}
      {visible.length === 0 && preview.status !== "needs_input" && <p role="status">
        {preview.status === "unavailable" ? "Chưa kết nối được AI để sửa câu. Bạn thử lại." : preview.status === "no_safe_improvement" || preview.unresolved?.length
          ? "Chưa có cách sửa đạt tiêu chí và giữ đủ dữ kiện. Nội dung gốc được giữ nguyên."
          : "Chưa có đề xuất thay đổi câu này."}
      </p>}
      {visible.length > 0 && preview.unresolved?.length > 0 && <p role="status">Một số lỗi vẫn cần chỉnh thêm; các đề xuất bên dưới chỉ áp dụng phần đã sửa được.</p>}
      {preview.status === "needs_input" && preview.questions?.length > 0 && <details open>
        <summary>{preview.status === "needs_input" ? "Cần thêm dữ kiện để tinh chỉnh" : "Gợi ý bổ sung thông tin"}</summary>
        <ul>{preview.questions.map((question) => <li key={question}>{question}</li>)}</ul>
      </details>}
      {visible.length > 0 && <div className="writer-result-actions">
        <button type="button" className="writer-apply" disabled={busy || disabled || !selected.length} onClick={() => apply()}>
          Áp dụng {selected.length} đề xuất đã chọn
        </button>
        <button type="button" disabled={busy || disabled} onClick={() => { setPreview(null); setSelected([]); }}>Giữ nguyên tất cả</button>
      </div>}
    </div>}
    {!onGenerate && undo && JSON.stringify(value) === JSON.stringify(undo.after) && <div className="writer-undo">
      <button type="button" disabled={busy || disabled} onClick={async () => {
        setBusy(true); setError("");
        try { await onApply(undo.before); baseline.current = [...undo.before]; setUndo(null); }
        catch (error) { setError(error.message); } finally { setBusy(false); }
      }}>Hoàn tác</button>
    </div>}
  </div>;
}
