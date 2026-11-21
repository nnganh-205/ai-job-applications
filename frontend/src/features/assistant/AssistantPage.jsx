import React, { useEffect, useLayoutEffect, useRef, useState } from "react";
import {
  Link,
  useNavigate,
  useParams,
  useSearchParams,
} from "react-router-dom";
import { request } from "../../lib/api.js";
import { getTask, retryTask } from "../../lib/tasks.js";
import Icon from "../../components/ui/Icon.jsx";
import AssistantIntakeCard from "./AssistantIntakeCard.jsx";
import CVVersionNotice from "../../components/CVVersionNotice.jsx";
import MatchingPanel from "../../components/MatchingPanel.jsx";
const actions = [
  ["build_cv", "Tạo CV qua chat"],
  ["review_cv", "Rà soát CV"],
  ["tailor_cv", "Điều chỉnh CV theo JD"],
  ["evaluate", "Xem độ phù hợp"],
  ["update_profile", "Bổ sung hồ sơ"],
  ["find_jobs", "Tìm việc phù hợp"],
  ["labor_law", "Hỏi luật lao động"],
];
const send = (path, body) =>
  request(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    timeoutMs: 15000,
  });
export default function AssistantRoute() {
  const { id } = useParams();
  return <AssistantPage key={id || "new"} id={id} />;
}
function AssistantPage({ id }) {
  const navigate = useNavigate();
  const conversationEnd = useRef(null);
  const pageRef = useRef(null);
  const [params] = useSearchParams();
  const creatingCV = params.get("create") === "cv";
  const [history, setHistory] = useState([]);
  const source = params.get("cv") ? "cv:" + params.get("cv") : "";
  const posting = params.get("job") || "";
  const language = "vi";
  const [session, setSession] = useState(null),
    [task, setTask] = useState(null),
    [text, setText] = useState(
      creatingCV
        ? "Mình muốn tạo CV mới. Hãy hướng dẫn mình từng bước."
        : params.get("task") === "tailor"
          ? "Hãy điều chỉnh CV đã chọn theo JD này, giữ đúng thông tin của tôi."
          : "",
    ),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [reload, setReload] = useState(0);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [startKey, setStartKey] = useState(() => crypto.randomUUID()),
    [messageKey, setMessageKey] = useState(() => crypto.randomUUID());
  useEffect(
    () => setStartKey(crypto.randomUUID()),
    [source, posting, language],
  );
  useEffect(() => setMessageKey(crypto.randomUUID()), [text]);
  useEffect(() => {
    const c = new AbortController();
    request("/api/assistant", { signal: c.signal })
      .then((history) => {
        if (!c.signal.aborted) setHistory(history);
      })
      .catch((e) => {
        if (e.name !== "AbortError") setError(e.message);
      });
    return () => c.abort();
  }, [reload]);
  useEffect(() => {
    if (!id) return;
    const c = new AbortController();
    let timer;
    let failures = 0;
    async function load() {
      try {
        const s = await request("/api/assistant/" + id, { signal: c.signal });
        if (c.signal.aborted) return;
        setSession(s);
        failures = 0;
        setError("");
        if (s.pending) {
          const t = await getTask(s.pending.task_id, c.signal);
          if (c.signal.aborted) return;
          setTask(t);
          if (t.status !== "failed") timer = setTimeout(load, 1500);
        } else setTask(null);
      } catch (e) {
        if (e.name !== "AbortError" && !c.signal.aborted) {
          setError(e.message);
          if (++failures <= 3) timer = setTimeout(load, 4000);
        }
      }
    }
    load();
    return () => {
      c.abort();
      clearTimeout(timer);
    };
  }, [id, reload]);
  useEffect(() => {
    conversationEnd.current?.scrollIntoView({
      behavior: "smooth",
      block: "nearest",
    });
  }, [session?.messages.length, !!session?.pending]);
  useLayoutEffect(() => {
    if (!id || !pageRef.current) return;
    const element = pageRef.current;
    const viewport = window.visualViewport;
    const fit = () => {
      const bottom =
        (viewport?.height || window.innerHeight) + (viewport?.offsetTop || 0);
      element.style.setProperty(
        "--assistant-available-height",
        `${Math.max(200, bottom - element.getBoundingClientRect().top - 8)}px`,
      );
    };
    const observer = new ResizeObserver(fit);
    for (const selector of [".site-header", ".workspace-sidebar"]) {
      const node = document.querySelector(selector);
      if (node) observer.observe(node);
    }
    fit();
    window.addEventListener("resize", fit);
    viewport?.addEventListener("resize", fit);
    viewport?.addEventListener("scroll", fit);
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", fit);
      viewport?.removeEventListener("resize", fit);
      viewport?.removeEventListener("scroll", fit);
    };
  }, [id]);
  function composerKeyDown(e) {
    if (
      e.key === "Enter" &&
      !e.shiftKey &&
      !e.nativeEvent.isComposing &&
      !busy &&
      !session?.pending &&
      text.trim()
    ) {
      e.preventDefault();
      e.currentTarget.form.requestSubmit();
    }
  }
  async function start(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const [kind, key] = source.split(":");
      const s = await send("/api/assistant", {
        profile_id: kind === "profile" ? key : null,
        cv_id: kind === "cv" ? key : null,
        posting_id: posting || null,
        language,
        event_id: startKey,
      });
      if (text.trim())
        await send("/api/assistant/" + s.session_id + "/messages", {
          expected_version: s.version,
          event_id: messageKey,
          text: text.trim(),
          intent: null,
        });
      navigate("/workspace/assistant/" + s.session_id);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  async function message(intent = null, explicitText = null) {
    setBusy(true);
    setError("");
    try {
      const s = await send("/api/assistant/" + id + "/messages", {
        expected_version: session.version,
        event_id: intent || explicitText ? crypto.randomUUID() : messageKey,
        text: explicitText ?? (intent ? "" : text),
        intent,
      });
      setSession(s);
      if (explicitText === null) setText("");
      setReload((n) => n + 1);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  async function retry() {
    setBusy(true);
    setError("");
    try {
      await retryTask(task.task_id);
      setReload((n) => n + 1);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <main
      ref={pageRef}
      className={"assistant-page" + (id ? " has-conversation" : "")}
    >
      <div className="assistant-toolbar">
        <Link
          className="assistant-new-chat"
          to="/workspace/assistant"
          onClick={() => {
            setText("");
            setError("");
          }}
        >
          <Icon name="plus" size={16} /> Trò chuyện mới
        </Link>
        <button
          type="button"
          className="assistant-history-toggle"
          aria-expanded={historyOpen}
          aria-controls="assistant-history"
          onClick={() => setHistoryOpen((v) => !v)}
        >
          <Icon name="clock" size={17} />
          <span>Lịch sử trò chuyện</span>
        </button>
      </div>
      {error && (
        <p className="error" role="alert">
          {error}{" "}
          <button onClick={() => setReload((n) => n + 1)}>Tải lại</button>
        </p>
      )}
      <div className={"assistant-grid" + (historyOpen ? " history-open" : "")}>
        <aside
          id="assistant-history"
          className="assistant-history"
          hidden={!historyOpen}
        >
          <h2>
            <Icon name="chat" size={16} /> Cuộc trò chuyện
          </h2>
          <nav className="assistant-history-list" aria-label="Danh sách cuộc trò chuyện" tabIndex={0}>
          {history.length ? (
            history.map((h) => (
              <Link
                aria-current={h.session_id === id ? "page" : undefined}
                key={h.session_id}
                to={"/workspace/assistant/" + h.session_id}
              >
                <strong>{h.title}</strong>
                <small>
                  {h.context.source_name || "Tạo CV mới"} ·{" "}
                  {new Date(h.updated_at).toLocaleDateString("vi-VN")}
                </small>
              </Link>
            ))
          ) : (
            <div className="history-empty">
              <Icon name="chat" size={28} />
              <p>
                Chưa có cuộc trò chuyện.
                <br />
                Bắt đầu một phiên và quay lại bất cứ lúc nào.
              </p>
            </div>
          )}
          </nav>
        </aside>
        <div className="assistant-main">
          {!id ? (
            <section className="assistant-welcome">
              <h1>
                {creatingCV
                  ? "Cùng tạo CV qua trò chuyện."
                  : "Hôm nay, bạn cần AI hỗ trợ điều gì?"}
              </h1>
              <p className="assistant-welcome-description">
                Hỏi bất cứ điều gì về CV, hoặc kể về bạn để cùng tạo một bản CV
                mới.
              </p>
              <form className="assistant-start-form" onSubmit={start}>
                <div className="assistant-input-box">
                  <label
                    className="assistant-sr-only"
                    htmlFor="assistant-first-message"
                  >
                    Yêu cầu của bạn
                  </label>
                  <textarea
                    id="assistant-first-message"
                    onKeyDown={composerKeyDown}
                    rows={2}
                    maxLength={4000}
                    value={text}
                    disabled={busy}
                    onChange={(e) => setText(e.target.value)}
                    placeholder="Thêm CV hoặc mô tả điều bạn đang cần hỗ trợ…"
                  />
                  <div className="assistant-input-tools">
                    <div className="assistant-attachments">
                      <Link to="/workspace/import">
                        <Icon name="file" size={15} /> Tải CV lên{" "}
                        <small>PDF, DOCX</small>
                      </Link>
                    </div>
                    <button
                      className="assistant-send"
                      aria-label="Gửi yêu cầu"
                      disabled={busy || !text.trim()}
                    >
                      <Icon name="arrow" size={19} />
                    </button>
                  </div>
                </div>
                <small className="assistant-input-note">
                  AI giúp diễn đạt rõ hơn dựa trên thông tin bạn cung cấp. Bạn
                  luôn là người duyệt thay đổi.
                </small>
              </form>
              <div className="assistant-starters" aria-label="Gợi ý bắt đầu">
                {[
                  [
                    "chat",
                    "Tạo CV mới từ thông tin của tôi",
                    "Mình muốn tạo một CV mới qua trò chuyện. Bạn hướng dẫn mình nhé.",
                  ],
                  [
                    "chat",
                    "Rà soát và cải thiện câu chữ CV",
                    "Hãy rà soát CV và đề xuất cách diễn đạt ngắn gọn, rõ ràng hơn, giữ nguyên các thông tin của tôi.",
                  ],
                  [
                    "shield",
                    "Hỏi luật lao động Việt Nam",
                    "Hỏi luật lao động",
                  ],
                ].map(([icon, label, prompt]) => (
                  <button
                    type="button"
                    key={icon}
                    disabled={busy}
                    onClick={() => {
                      setText(prompt);
                    }}
                  >
                    <Icon name={icon} size={17} />
                    <span>{label}</span>
                    <Icon name="arrow" size={15} />
                  </button>
                ))}
              </div>
            </section>
          ) : !session ? (
            <p role="status">Đang mở cuộc trò chuyện…</p>
          ) : (
            <>
              {(session.context.profile_id ||
                session.context.cv_id ||
                session.context.posting_id) && (
                <>
                  <div className="assistant-context">
                    <span>
                      ◎ {session.context.source_name || "Chưa chọn hồ sơ / CV"}
                    </span>
                    <span>
                      ↗ {session.context.job_title || "Chưa chọn công việc"}
                    </span>
                    <small>
                      Muốn đổi nguồn? Tạo cuộc trò chuyện mới để giữ kết quả
                      đúng nội dung.
                    </small>
                  </div>
                </>
              )}
              {session.context.cv_id && (
                <CVVersionNotice
                  cvId={session.context.cv_id}
                  postingId={session.context.posting_id}
                />
              )}
              <div
                className="assistant-messages"
                aria-label="Lịch sử trò chuyện"
              >
                {session.messages.map((m, i) => (
                  <article key={i} className={"assistant-bubble " + m.role}>
                    <p>{m.text}</p>
                    {m.result?.type === "labor_law" && m.result.sources?.length > 0 && (
                      <div className="assistant-law-sources">
                        <strong>Nguồn đối chiếu</strong>
                        {m.result.sources.map((source, index) => (
                          <a key={`${source.url}-${source.page}-${index}`} href={source.url} target="_blank" rel="noopener noreferrer">
                            {source.title}{source.article ? ` · ${source.article}` : ""} · trang {source.page} ↗
                          </a>
                        ))}
                        <small>Kiểm tra tình trạng hiệu lực và sửa đổi trên cổng văn bản trước khi áp dụng.</small>
                      </div>
                    )}
                    {m.result?.type === "cv_intake" &&
                      i ===
                        session.messages.findLastIndex(
                          (item) => item.result?.type === "cv_intake",
                        ) && <AssistantIntakeCard result={m.result} />}
                    {m.result?.wording_suggestions?.length > 0 && (
                      <div className="cv-wording-panel">
                        <strong>Gợi ý diễn đạt cho CV</strong>
                        {m.result.wording_suggestions.map((suggestion, j) => (
                          <div key={j}>
                            <small>
                              {{
                                description: "Mô tả",
                                summary: "Tóm tắt",
                              }[suggestion.field] || "Nội dung CV"}
                            </small>
                            {Array.isArray(suggestion.proposed) ? (
                              <ul className="assistant-writer-bullets">
                                {suggestion.proposed.map((bullet, bi) => (
                                  <li key={bi}>
                                    {bullet}
                                    {suggestion.bullet_sources?.[bi] && (
                                      <details>
                                        <summary>Thông tin nguồn</summary>
                                        {suggestion.bullet_sources[bi].map(
                                          (quote, qi) => (
                                            <p key={qi}>{quote}</p>
                                          ),
                                        )}
                                      </details>
                                    )}
                                  </li>
                                ))}
                              </ul>
                            ) : (
                              <p className="cv-wording-text">
                                {suggestion.proposed}
                              </p>
                            )}
                            {suggestion.questions?.length > 0 && (
                              <details>
                                <summary>Có thể bổ sung để viết rõ hơn</summary>
                                <ul>
                                  {suggestion.questions.map((q) => (
                                    <li key={q}>{q}</li>
                                  ))}
                                </ul>
                              </details>
                            )}
                            <details>
                              <summary>Nội dung bạn nhập</summary>
                              <p>
                                {Array.isArray(suggestion.original)
                                  ? suggestion.original.join("\n")
                                  : suggestion.original}
                              </p>
                            </details>
                          </div>
                        ))}
                        <small>
                          Thông tin gốc vẫn được giữ nguyên cho đến khi bạn áp
                          dụng.
                        </small>
                        {i ===
                          session.messages.findLastIndex(
                            (item) => item.result?.type === "cv_intake",
                          ) && (
                          <button
                            disabled={busy || !!session.pending}
                            onClick={() => message(null, "áp dụng cách viết")}
                          >
                            Áp dụng cách viết
                          </button>
                        )}
                      </div>
                    )}
                    {m.result?.type === "cv_intake" &&
                      i ===
                        session.messages.findLastIndex(
                          (item) => item.result?.type === "cv_intake",
                        ) && (
                        <div className="assistant-writer-actions">
                          {["project", "experience"]
                            .filter(
                              (section) =>
                                m.result.intake?.profile?.[section]?.length,
                            )
                            .map((section) => (
                              <button
                                key={section}
                                disabled={busy || !!session.pending}
                                onClick={() =>
                                  message(
                                    null,
                                    section === "project"
                                      ? "viết bullet cho dự án"
                                      : "viết bullet cho kinh nghiệm",
                                  )
                                }
                              >
                                AI Writer ·{" "}
                                {section === "project"
                                  ? "Dự án"
                                  : "Kinh nghiệm"}
                              </button>
                            ))}
                        </div>
                      )}
                    {m.result?.type === "cv_draft" && (
                      <>
                        <Link className="button-link" to={m.result.href}>
                          Kiểm tra và chỉnh bản CV →
                        </Link>
                        <details>
                          <summary>Nhận xét nội dung</summary>
                          {m.result.review.items.map((r, j) => (
                            <div className="cv-review-item" key={j}>
                              <p>
                                <strong>Nội dung hiện tại:</strong>{" "}
                                {r.original_text}
                              </p>
                              <p>
                                <strong>Đề xuất:</strong> {r.proposed_text}
                              </p>
                              <p>{r.reason}</p>
                            </div>
                          ))}
                        </details>
                      </>
                    )}
                    {m.result?.evaluation && (
                      <MatchingPanel
                        evaluation={m.result.evaluation}
                        onUpdateProfile={() => message("update_profile")}
                        onOptimizeCV={() => message("tailor_cv")}
                      />
                    )}
                    {m.result?.type === "jobs" && (
                      <div className="assistant-job-results">
                        {m.result.jobs.length ? (
                          m.result.jobs.map((j) => (
                            <Link
                              key={j.posting_id}
                              to={
                                "/jobs/" +
                                j.posting_id +
                                (session.context.cv_id
                                  ? "?cv=" + session.context.cv_id
                                  : "")
                              }
                            >
                              <strong>{j.title}</strong>
                              <small>
                                {j.company || "Công ty chưa công bố"} · Từ khóa:{" "}
                                {j.terms.join(", ")}
                              </small>
                            </Link>
                          ))
                        ) : (
                          <p>
                            Chưa có tin trùng từ khóa kỹ năng đã khai báo.{" "}
                            <Link to="/jobs">Mở tìm kiếm việc làm</Link>.
                          </p>
                        )}
                      </div>
                    )}
                    {m.result?.href &&
                      m.result.type !== "cv_draft" &&
                      m.result.type !== "cv_intake" && (
                        <Link className="button-link" to={m.result.href}>
                          {m.result.type === "profile_update"
                            ? "Tiếp tục bổ sung có duyệt"
                            : "Mở thư viện CV"}{" "}
                          →
                        </Link>
                      )}
                  </article>
                ))}
                {session.pending && task?.status !== "failed" && (
                  <div
                    className="assistant-typing"
                    role="status"
                    aria-label="AI đang trả lời"
                  >
                    <span aria-hidden="true" />
                    <span aria-hidden="true" />
                    <span aria-hidden="true" />
                  </div>
                )}
                <div ref={conversationEnd} />
              </div>
              {session.pending && task?.status === "failed" && (
                <div className="assistant-task" role="alert">
                  <p className="error">{task.error}</p>
                  <button disabled={busy} onClick={retry}>
                    Thử lại yêu cầu này
                  </button>
                  <Link to="/workspace/assistant">Tạo phiên với nguồn mới</Link>
                </div>
              )}
              <div className="assistant-action-chips" aria-label="Gợi ý tác vụ">
                {actions.map(([intent, label]) => (
                  <button
                    className="secondary-button"
                    key={intent}
                    disabled={busy || !!session.pending}
                    onClick={() => message(intent)}
                  >
                    {label}
                  </button>
                ))}
              </div>
              <form
                className="assistant-composer assistant-conversation-composer"
                onSubmit={(e) => {
                  e.preventDefault();
                  message();
                }}
              >
                <div className="assistant-input-box">
                  <label
                    className="assistant-sr-only"
                    htmlFor="assistant-message"
                  >
                    Bạn đang cần hỗ trợ điều gì?
                  </label>
                  <textarea
                    id="assistant-message"
                    onKeyDown={composerKeyDown}
                    rows={2}
                    maxLength={4000}
                    value={text}
                    disabled={busy || !!session.pending}
                    onChange={(e) => setText(e.target.value)}
                    placeholder="Viết yêu cầu hoặc câu hỏi tiếp theo…"
                  />
                  <div className="assistant-input-tools">
                    <span className="assistant-composer-source">
                      <Icon name="file" size={14} />
                      {session.context.source_name ||
                        "Trò chuyện với trợ lý AI"}
                    </span>
                    <button
                      className="assistant-send"
                      aria-label="Gửi yêu cầu"
                      disabled={busy || !!session.pending || !text.trim()}
                    >
                      <Icon name="arrow" size={19} />
                    </button>
                  </div>
                </div>
                <small className="assistant-input-note">
                  AI có thể nhận xét chưa chính xác. Hồ sơ chỉ thay đổi sau khi
                  bạn duyệt.
                </small>
              </form>
            </>
          )}
        </div>
      </div>
    </main>
  );
}
