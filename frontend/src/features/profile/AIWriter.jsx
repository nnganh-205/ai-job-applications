import React, { useEffect, useRef, useState } from "react";
import {
  changedLineIndices,
  mergeWriterEdits,
  coveredTargetIndices,
} from "./writerEdits.js";
import { request } from "../../services/api.js";

export default function AIWriter({
  section,
  field,
  initialValue,
  entry,
  value = [],
  disabled,
  onApply,
  onGenerate,
  action = null,
}) {
  const [open, setOpen] = useState(false),
    [tasks, setTasks] = useState(""),
    [tools, setTools] = useState(""),
    [results, setResults] = useState("");
  const [style, setStyle] = useState("professional"),
    [count, setCount] = useState(4),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const [preview, setPreview] = useState(null),
    [selected, setSelected] = useState([]);
  const writerRef = useRef(null);
  const baseline = useRef(initialValue || value);
  const [scope, setScope] = useState("changed");
  const [undo, setUndo] = useState(null);
  const changed = changedLineIndices(value, baseline.current);
  const targets =
    !onGenerate && scope === "changed" && changed.length
      ? changed
      : value.flatMap((text, index) => (text.trim() ? [index] : []));

  const [menu, setMenu] = useState(false),
    [showNotes, setShowNotes] = useState(!value.length),
    [applyMode, setApplyMode] = useState("replace");
  useEffect(() => {
    if (action?.nonce) {
      setOpen(true);
      setStyle(action.style);
      requestAnimationFrame(() =>
        writerRef.current?.scrollIntoView({
          block: "center",
          behavior: window.matchMedia("(prefers-reduced-motion: reduce)")
            .matches
            ? "auto"
            : "smooth",
        }),
      );
    }
  }, [action?.nonce]);
  const context = JSON.stringify({ entry, value });
  const version = useRef(0);
  useEffect(() => {
    if (!menu) return;
    const close = (event) => {
      if (event.key === "Escape" || !writerRef.current?.contains(event.target))
        setMenu(false);
    };
    document.addEventListener("pointerdown", close);
    document.addEventListener("keydown", close);
    return () => {
      document.removeEventListener("pointerdown", close);
      document.removeEventListener("keydown", close);
    };
  }, [menu]);
  useEffect(() => {
    version.current++;
    setPreview(null);
    setError("");
    setBusy(false);
  }, [context, tasks, tools, results, style, count, scope]);
  async function generate(e) {
    e.preventDefault();
    e.stopPropagation();
    setOpen(true);
    setMenu(false);
    const current = ++version.current;
    setBusy(true);
    setError("");
    const payload = {
      section,
      entry,
      text: (onGenerate ? value : targets.map((index) => value[index])).join(
        "\n",
      ),
      ...(field ? { field } : {}),
      tasks,
      tools,
      results,
      style,
      count,
    };
    try {
      const response = onGenerate
        ? await onGenerate(payload)
        : await request("/api/profile-drafts/writer", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
          });
      if (current === version.current) {
        setPreview({
          ...response,
          originalLines: [...value],
          targets: [...targets],
        });
        setSelected(response.bullets.map((_, i) => i));
      }
    } catch (e) {
      if (current === version.current) setError(e.message);
    } finally {
      if (current === version.current) setBusy(false);
    }
  }
  async function apply(e) {
    e.preventDefault();
    e.stopPropagation();
    setBusy(true);
    setError("");
    try {
      const before = [...value];
      const proposals = selected.map((i) => preview.bullets[i].text);
      const next = onGenerate
        ? proposals
        : mergeWriterEdits(
            before,
            coveredTargetIndices(
              before,
              preview.targets,
              selected.map((i) => preview.bullets[i]),
            ),
            proposals,
            applyMode,
          );
      await onApply(next, preview, selected, applyMode);
      if (!onGenerate) {
        setUndo({ before, after: next });
        baseline.current = [...next];
      }
      setPreview(null);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div
      ref={writerRef}
      className="ai-writer writer-inline"
      onClick={(e) => e.stopPropagation()}
    >
      <div className="writer-toolbar">
        <span>
          <span className="writer-spark">✦</span>{" "}
          {value.length
            ? `${value.filter(Boolean).length} bullet · Viết rõ phần bạn trực tiếp thực hiện`
            : "Kể ý thô, AI giúp viết thành bullet"}
        </span>
        <div className="writer-split">
          <button
            type="button"
            disabled={busy || disabled}
            className="ai-writer-generate"
            onClick={generate}
          >
            {busy ? (
              <span
                className="ai-writer-loading"
                role="status"
                aria-label="Đang viết bullet"
              >
                <i />
                <i />
                <i />
              </span>
            ) : (
              <>
                ✦{" "}
                {preview
                  ? "Tạo lại"
                  : style === "concise"
                    ? "Viết gọn"
                    : count === 1
                      ? "Đề xuất bullet"
                      : "AI Writer · Tạo bullet"}
              </>
            )}
          </button>
          <button
            type="button"
            className="writer-menu-toggle"
            aria-label="Các lựa chọn AI Writer"
            aria-expanded={menu}
            disabled={busy || disabled}
            onClick={(e) => {
              e.preventDefault();
              setMenu(!menu);
            }}
          >
            ⌄
          </button>
          {menu && (
            <div className="writer-menu" role="menu">
              {[
                ["professional", "Viết lại chuyên nghiệp"],
                ["concise", "Viết ngắn gọn"],
                ["detailed", "Làm rõ cách thực hiện"],
                ["quantified", "Ưu tiên kết quả / số liệu đã có"],
              ].map(([key, title]) => (
                <button
                  type="button"
                  role="menuitem"
                  key={key}
                  onClick={(e) => {
                    e.preventDefault();
                    setStyle(key);
                    setCount(4);
                    setMenu(false);
                    setOpen(true);
                  }}
                >
                  {style === key ? "✓ " : ""}
                  {title}
                </button>
              ))}
              <button
                type="button"
                role="menuitem"
                onClick={(e) => {
                  e.preventDefault();
                  setCount(1);
                  setApplyMode("append");
                  setOpen(true);
                  setMenu(false);
                }}
              >
                + Đề xuất thêm một bullet
              </button>
              <button
                type="button"
                role="menuitem"
                onClick={(e) => {
                  e.preventDefault();
                  setShowNotes(true);
                  setOpen(true);
                  setMenu(false);
                }}
              >
                Bổ sung thông tin cho AI
              </button>
            </div>
          )}
        </div>
      </div>
      {!onGenerate &&
        undo &&
        JSON.stringify(value) === JSON.stringify(undo.after) && (
          <div className="writer-undo" role="status">
            Đã áp dụng cách viết cho phần đã chọn.
            <button
              type="button"
              disabled={busy || disabled}
              onClick={async () => {
                setBusy(true);
                setError("");
                try {
                  await onApply(undo.before);
                  baseline.current = [...undo.before];
                  setUndo(null);
                } catch (e) {
                  setError(e.message);
                } finally {
                  setBusy(false);
                }
              }}
            >
              Hoàn tác chỉnh câu
            </button>
          </div>
        )}
      {open && (
        <div className="ai-writer-body">
          <div className="writer-panel-heading">
            <div>
              <strong>
                {preview ? "Đề xuất của AI Writer" : "Chuẩn bị viết bullet"}
              </strong>
              <small>
                {entry.project_name ||
                  entry.company ||
                  entry.title ||
                  entry.activity_name ||
                  "Nội dung CV"}
              </small>
            </div>
            <button
              type="button"
              aria-label="Thu gọn AI Writer"
              onClick={(e) => {
                e.preventDefault();
                setOpen(false);
              }}
            >
              ×
            </button>
          </div>
          {!onGenerate && value.some((line) => line.trim()) && (
            <div className="writer-scope">
              <label>
                Phạm vi chỉnh câu
                <select
                  aria-label="Phạm vi chỉnh câu"
                  value={scope}
                  disabled={busy}
                  onChange={(e) => {
                    setScope(e.target.value);
                    setPreview(null);
                    version.current++;
                  }}
                >
                  <option value="changed">
                    {changed.length
                      ? `Chỉ ${changed.length} bullet mới / vừa sửa`
                      : "Các bullet trong ô này"}
                  </option>
                  <option value="all">Toàn bộ bullet trong ô này</option>
                </select>
              </label>
              <small>Các ô khác và bullet ngoài phạm vi được giữ nguyên.</small>
            </div>
          )}
          <div className="ai-writer-options">
            <select
              aria-label="Phong cách AI Writer"
              value={style}
              onChange={(e) => setStyle(e.target.value)}
              disabled={busy}
            >
              <option value="professional">Chuyên nghiệp</option>
              <option value="concise">Ngắn gọn</option>
              <option value="detailed">Làm rõ cách thực hiện</option>
              <option value="quantified">Ưu tiên kết quả đã có</option>
            </select>
            <select
              aria-label="Số bullet tối đa"
              value={count}
              onChange={(e) => setCount(Number(e.target.value))}
              disabled={busy}
            >
              {[1, 2, 3, 4, 5, 6].map((n) => (
                <option key={n} value={n}>
                  Tối đa {n} bullet
                </option>
              ))}
            </select>
          </div>
          {!onGenerate && (
            <details
              open={showNotes}
              onToggle={(e) => setShowNotes(e.currentTarget.open)}
              className="writer-notes"
            >
              <summary>Bổ sung công việc, công cụ hoặc kết quả thực tế</summary>
              <span className="ai-writer-label">Bạn đã trực tiếp làm gì?</span>
              <textarea
                aria-label="AI Writer: công việc thực tế"
                value={tasks}
                onChange={(e) => setTasks(e.target.value)}
                disabled={busy || disabled}
                placeholder="Mỗi dòng một việc bạn thực sự làm; không cần viết trau chuốt."
              />
              <span className="ai-writer-label">
                Công cụ / cách làm · tùy chọn
              </span>
              <input
                aria-label="AI Writer: công cụ"
                value={tools}
                onChange={(e) => setTools(e.target.value)}
                disabled={busy || disabled}
                placeholder="Chỉ những công cụ bạn đã sử dụng"
              />
              <span className="ai-writer-label">
                Đầu ra / kết quả · tùy chọn
              </span>
              <textarea
                aria-label="AI Writer: kết quả"
                value={results}
                onChange={(e) => setResults(e.target.value)}
                disabled={busy || disabled}
                placeholder="Sản phẩm hoặc kết quả có thật. Không cần tự đặt số liệu."
              />
            </details>
          )}
          {showNotes && (
            <button
              type="button"
              disabled={busy || disabled}
              onClick={generate}
            >
              ✦ Tạo từ thông tin bổ sung
            </button>
          )}
          {error && <p role="alert">{error}</p>}
          {preview && (
            <div className="ai-writer-preview">
              <strong>
                {preview.status === "needs_input"
                  ? "Cần thêm thông tin để viết đúng"
                  : "Chọn bullet bạn muốn sử dụng"}
              </strong>
              {preview.engine === "editorial" && (
                <small>
                  Bản biên tập từ nguồn đang được hiển thị; bạn có thể thử tạo
                  lại bằng mô hình.
                </small>
              )}
              {preview.engine === "mixed" && (
                <small>
                  Một số câu được giữ theo bản gốc vì đề xuất AI chưa đạt kiểm tra nội dung.
                </small>
              )}
              {preview.remaining_facts?.length > 0 && (
                <p role="status">
                  Còn {preview.remaining_facts.length} ý ngoài số bullet đã chọn.
                  Các ý này sẽ được giữ nguyên khi áp dụng; bạn có thể chỉnh tiếp từng phần.
                </p>
              )}
              <div className="writer-before-after">
                <strong>Trước khi chỉnh</strong>
                <ul>
                  {preview.targets.map((index) => (
                    <li key={index}>{preview.originalLines[index]}</li>
                  ))}
                </ul>
                {!preview.targets.length && (
                  <p>Nội dung từ thông tin bổ sung bên dưới.</p>
                )}
                <strong>Đề xuất sau khi chỉnh</strong>
              </div>
              {preview.rejected > 0 && (
                <p role="status">
                  Đã loại {preview.rejected} đề xuất không đạt kiểm tra nguồn.
                </p>
              )}
              {preview.bullets.map((b, i) => (
                <div className="ai-writer-bullet" key={i}>
                  <label>
                    <input
                      type="checkbox"
                      checked={selected.includes(i)}
                      disabled={busy}
                      onChange={(e) =>
                        setSelected(
                          e.target.checked
                            ? [...selected, i].sort((a, b) => a - b)
                            : selected.filter((x) => x !== i),
                        )
                      }
                    />
                    <span>{b.text}</span>
                  </label>
                  <details>
                    <summary>Đối chiếu nội dung gốc</summary>
                    {b.sources.map((t, j) => (
                      <p key={j}>{t}</p>
                    ))}
                  </details>
                </div>
              ))}
              {preview.questions.length > 0 && (
                <details open={preview.status === "needs_input"}>
                  <summary>Bổ sung gì để bullet rõ hơn?</summary>
                  <ul>
                    {preview.questions.map((q) => (
                      <li key={q}>{q}</li>
                    ))}
                  </ul>
                </details>
              )}
              {preview.bullets.length > 0 && (
                <>
                  <div className="writer-apply-mode">
                    <label>
                      <input
                        type="radio"
                        checked={applyMode === "replace"}
                        onChange={() => setApplyMode("replace")}
                      />
                      Thay các bullet trong phạm vi đã chọn
                    </label>
                    <label>
                      <input
                        type="radio"
                        checked={applyMode === "append"}
                        onChange={() => setApplyMode("append")}
                      />
                      Thêm vào cuối danh sách
                    </label>
                  </div>
                  <small>
                    Chỉ áp dụng các câu đúng với phần bạn đã làm. Đề xuất chưa
                    thay đổi nội dung hiện tại.
                  </small>
                  <div className="writer-result-actions">
                    <button
                      type="button"
                      className="writer-apply"
                      disabled={busy || disabled || !selected.length}
                      onClick={apply}
                    >
                      Áp dụng {selected.length} bullet
                    </button>
                    <button
                      type="button"
                      disabled={busy}
                      onClick={(e) => {
                        e.preventDefault();
                        setPreview(null);
                      }}
                    >
                      Bỏ đề xuất
                    </button>
                  </div>
                </>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
