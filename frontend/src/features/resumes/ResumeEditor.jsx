import React, { useEffect, useState, useRef } from "react";
import { Link, useParams, useNavigate, useBlocker } from "react-router-dom";
import CVVersionNotice from "../../components/CVVersionNotice.jsx";
import ResumeHistory from "./ResumeHistory.jsx";
import ProfileEditor from "../profile/ProfileEditor.jsx";
import AIWriter from "../profile/AIWriter.jsx";
import ResumeDesignToolbar from "./ResumeDesignToolbar.jsx";
import CVPreviewFrame from "../../components/ui/CVPreviewFrame.jsx";
import { request } from "../../services/api.js";
import { send } from "./ResumeLibrary.jsx";
export default function ResumeEditor() {
  const { id } = useParams(),
    navigate = useNavigate();
  const [draft, setDraft] = useState(null),
    [edit, setEdit] = useState(null),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [message, setMessage] = useState(""),
    [preview, setPreview] = useState(""),
    [templates, setTemplates] = useState([]);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [sourceDraft, setSourceDraft] = useState(null);
  const [sourceOpen, setSourceOpen] = useState(false);
  const [sourceDirty, setSourceDirty] = useState(false);
  const [view, setView] = useState("preview");
  const [previewBusy, setPreviewBusy] = useState(false);
  const [previewError, setPreviewError] = useState("");
  const history = useRef([]);
  const allowNavigation = useRef(false);
  const publicationEvent = useRef(null);
  const dirty =
    !!draft &&
    !!edit &&
    JSON.stringify(edit) !==
      JSON.stringify({
        title: draft.title,
        document: draft.document,
        presentation: draft.presentation,
      });
  const blocker = useBlocker(
    () => (dirty || sourceDirty) && !allowNavigation.current,
  );
  useEffect(() => {
    if (blocker.state === "blocked") {
      if (window.confirm("CV có thay đổi chưa lưu. Rời trang và bỏ thay đổi?"))
        blocker.proceed();
      else blocker.reset();
    }
  }, [blocker]);
  useEffect(() => {
    const guard = (e) => {
      if (dirty || sourceDirty) {
        e.preventDefault();
        e.returnValue = "";
      }
    };
    window.addEventListener("beforeunload", guard);
    return () => window.removeEventListener("beforeunload", guard);
  }, [dirty, sourceDirty]);
  function loaded(d) {
    setDraft(d);
    setEdit({
      title: d.title,
      document: d.document,
      presentation: d.presentation,
    });
    history.current = [];
  }
  useEffect(() => {
    const c = new AbortController();
    allowNavigation.current = false;
    publicationEvent.current = null;
    setDraft(null);
    setEdit(null);
    setSourceDraft(null);
    setSourceOpen(false);
    setSourceDirty(false);
    setError("");
    Promise.all([
      request(`/api/resumes/${id}`, { signal: c.signal }),
      request("/api/cv/templates", { signal: c.signal }),
    ])
      .then(([d, t]) => {
        if (!c.signal.aborted) {
          loaded(d);
          setTemplates(t);
        }
      })
      .catch((e) => {
        if (e.name !== "AbortError") setError(e.message);
      });
    return () => c.abort();
  }, [id]);
  function change(mutator) {
    history.current.push(structuredClone(edit));
    if (history.current.length > 30) history.current.shift();
    const next = structuredClone(edit);
    mutator(next);
    setEdit(next);
    setPreview("");
  }
  useEffect(() => {
    if (!edit || !draft || !dirty) {
      setPreviewBusy(false);
      return;
    }
    const controller = new AbortController();
    setPreviewError("");
    setPreviewBusy(true);
    const timer = setTimeout(async () => {
      try {
        const response = await fetch(`/api/resumes/${id}/preview`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ ...edit, expected_version: draft.version }),
          signal: controller.signal,
        });
        if (!response.ok)
          throw new Error(
            "Chưa thể cập nhật xem trước. Kiểm tra nội dung và chọn Xem trước để biết chi tiết.",
          );
        const html = await response.text();
        if (!controller.signal.aborted) setPreview(html);
      } catch (error) {
        if (!controller.signal.aborted) setPreviewError(error.message);
      } finally {
        if (!controller.signal.aborted) setPreviewBusy(false);
      }
    }, 500);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [edit, draft, dirty, id]);
  async function save() {
    const d = await send(
      `/api/resumes/${id}`,
      { ...edit, expected_version: draft.version },
      "PUT",
    );
    loaded(d);
    return d;
  }
  async function act(action) {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      if (action === "preview") {
        const response = await fetch(`/api/resumes/${id}/preview`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ ...edit, expected_version: draft.version }),
        });
        if (!response.ok) {
          const data = await response.json().catch(() => ({}));
          throw new Error(
            typeof data.detail === "string"
              ? data.detail
              : "Không tạo được bản xem trước.",
          );
        }
        setPreview(await response.text());
        setView("preview");
        return;
      }
      const d = dirty ? await save() : draft;
      if (action === "publish" || action === "export") {
        const existing = Object.entries(d.publications).find(
          ([, v]) => v.draft_version === d.version,
        )?.[0];
        if (publicationEvent.current?.version !== d.version)
          publicationEvent.current = {
            version: d.version,
            event: existing || crypto.randomUUID(),
          };
        const event = publicationEvent.current.event;
        const result = await send(`/api/resumes/${id}/publish`, {
          expected_version: d.version,
          event_id: event,
        });
        setDraft({
          ...d,
          latest_cv_id: result.cv_id,
          publications: { ...d.publications, [event]: result },
        });
        setMessage("Đã lưu bản CV đã xác nhận.");
        if (action === "export") {
          const link = document.createElement("a");
          link.href = `/api/cv/versions/${result.cv_id}/pdf`;
          link.download = `${result.cv_id}.pdf`;
          link.click();
        }
      } else if (action === "duplicate") {
        const result = await send(`/api/resumes/${id}/duplicate`, {});
        allowNavigation.current = true;
        navigate(`/workspace/resumes/${result.resume_id}/edit`);
      } else setMessage("Đã lưu bản nháp.");
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  async function editSource() {
    setBusy(true);
    setError("");
    try {
      const current = dirty ? await save() : draft;
      const next = await send(`/api/resumes/${id}/source-edit`, {
        expected_version: current.version,
      });
      setDraft({ ...current, source_edit: next });
      setSourceDraft(next.draft_id);
      setSourceOpen(true);
    } catch (error) {
      setError(error.message);
    } finally {
      setBusy(false);
    }
  }
  async function uploadPhoto(file) {
    if (!file) return;
    setBusy(true);
    setError("");
    try {
      const body = new FormData();
      body.append("file", file);
      const asset = await request("/api/assets/photos", {
        method: "POST",
        body,
      });
      change((d) => {
        d.presentation.photo_asset_id = asset.asset_id;
      });
      setMessage("Ảnh đã được xử lý. Lưu bản nháp để áp dụng.");
    } catch (error) {
      setError(error.message);
    } finally {
      setBusy(false);
    }
  }
  if (sourceOpen && sourceDraft)
    return (
      <div className="resume-inline-editor">
        <ProfileEditor
          resumeId={id}
          draftId={sourceDraft}
          template={edit.presentation.template}
          embedded
          onDirtyChange={setSourceDirty}
          onClose={() => {
            if (
              sourceDirty &&
              !window.confirm(
                "Có thay đổi chưa lưu. Quay lại bản CV và bỏ các thay đổi này?",
              )
            )
              return;
            setSourceOpen(false);
            setSourceDirty(false);
          }}
          onComplete={(resume) => {
            loaded(resume);
            setPreview("");
            setSourceDraft(null);
            setSourceOpen(false);
            setSourceDirty(false);
            setMessage(
              "Đã cập nhật CV. Nội dung và thiết kế được giữ trên cùng bản CV.",
            );
          }}
        />
      </div>
    );
  return (
    <main className={"resume-editor cv-design-editor design-" + view}>
      <p className="eyebrow">Chỉnh sửa CV</p>
      <h1>Thiết kế bản CV của bạn</h1>
      <Link to="/workspace/resumes">← Thư viện CV</Link>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {!edit && !error && <p role="status">Đang tải CV…</p>}
      {edit && (
        <>
          <p role="status">
            {dirty ? "Có thay đổi chưa lưu" : "Bản nháp đã lưu"} · v
            {draft.version}
          </p>
          {draft.source_cv_id && (
            <CVVersionNotice
              cvId={draft.source_cv_id}
              postingId={draft.source_posting_id}
            />
          )}
          {draft.form_refinement && (
            <p className="cv-refinement-status" role="status">
              {draft.form_refinement.status === "fallback"
                ? "AI tạm thời không khả dụng. Bản CV đang dùng nội dung bạn đã nhập."
                : `AI đã tinh chỉnh ${draft.form_refinement.applied} câu. Bạn có thể kiểm tra nội dung trong bản xem trước.`}
            </p>
          )}
          {message && <p role="status">{message}</p>}
          {draft.source_edit?.status === "editing" && (
            <p className="cv-editing-status" role="status">
              Có bản nháp chỉnh sửa đã lưu, chưa áp dụng vào CV. Chọn Chỉnh sửa
              CV để tiếp tục.
            </p>
          )}
          {historyOpen && (
            <ResumeHistory
              id={id}
              onClose={() => setHistoryOpen(false)}
              onRestored={(resume) => {
                loaded(resume);
                setPreview("");
                setSourceDraft(null);
                setHistoryOpen(false);
                setMessage(
                  `Đã khôi phục thành phiên bản ${resume.version}. Các bản trước vẫn được giữ nguyên.`,
                );
              }}
            />
          )}
          <ResumeDesignToolbar
            onHistory={() => setHistoryOpen(true)}
            edit={edit}
            templates={templates}
            busy={busy}
            dirty={dirty}
            onChange={change}
            onSave={() => act("save")}
            onExport={() => act("export")}
            onSourceEdit={editSource}
          />
          <div className={"resume-editor-grid mode-" + view}>
            <div className="editor-form">
              <fieldset disabled={busy}>
                <legend>Trình bày</legend>
                <div className="form-actions">
                  <label>
                    Ảnh hồ sơ (JPEG, PNG, WebP · tối đa 5 MB)
                    <input
                      type="file"
                      accept="image/jpeg,image/png,image/webp"
                      onChange={(e) => uploadPhoto(e.target.files[0])}
                    />
                  </label>
                  {edit.presentation.photo_asset_id && (
                    <>
                      <img
                        className="editor-photo"
                        alt="Ảnh đang chọn cho CV"
                        src={"/api/assets/" + edit.presentation.photo_asset_id}
                      />
                      <button
                        onClick={() =>
                          change((d) => {
                            d.presentation.photo_asset_id = null;
                          })
                        }
                      >
                        Bỏ ảnh khỏi CV
                      </button>
                    </>
                  )}
                </div>
                <div className="form-grid">
                  <label>
                    Tên CV
                    <input
                      value={edit.title}
                      maxLength={120}
                      onChange={(e) =>
                        change((d) => {
                          d.title = e.target.value;
                        })
                      }
                    />
                  </label>
                  <label>
                    Mẫu
                    <select
                      aria-label="Mẫu CV"
                      value={edit.presentation.template}
                      onChange={(e) =>
                        change((d) => {
                          d.presentation.template = e.target.value;
                          const selected = templates.find(
                            (t) => t.id === e.target.value,
                          );
                          if (selected) {
                            d.presentation.template_version = selected.version;
                            d.presentation.font = selected.font;
                            d.presentation.color = selected.color;
                          }
                        })
                      }
                    >
                      {templates.map((t) => (
                        <option key={t.id} value={t.id}>
                          {t.name}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    Màu nhấn
                    <input
                      type="color"
                      value={edit.presentation.color}
                      onChange={(e) =>
                        change((d) => {
                          d.presentation.color = e.target.value;
                        })
                      }
                    />
                  </label>
                  <label>
                    Font
                    <select
                      value={edit.presentation.font}
                      onChange={(e) =>
                        change((d) => {
                          d.presentation.font = e.target.value;
                        })
                      }
                    >
                      <option value="sans">Sans serif</option>
                      <option value="serif">Serif</option>
                    </select>
                  </label>
                  <label>
                    Cỡ chữ
                    <select
                      value={edit.presentation.font_size}
                      onChange={(e) =>
                        change((d) => {
                          d.presentation.font_size = Number(e.target.value);
                        })
                      }
                    >
                      {[9, 10, 11, 12].map((n) => (
                        <option key={n}>{n}</option>
                      ))}
                    </select>
                  </label>
                  <label>
                    Giãn dòng
                    <select
                      value={edit.presentation.line_height}
                      onChange={(e) =>
                        change((d) => {
                          d.presentation.line_height = Number(e.target.value);
                        })
                      }
                    >
                      {[1.2, 1.4, 1.5, 1.7].map((n) => (
                        <option key={n}>{n}</option>
                      ))}
                    </select>
                  </label>
                </div>
              </fieldset>
              {draft.review?.items?.length > 0 && (
                <details className="editor-review">
                  <summary>
                    Đề xuất để bạn kiểm tra ({draft.review.items.length})
                  </summary>
                  {draft.review.items.map((r, index) => (
                    <article className="cv-review-item" key={index}>
                      <p>
                        <strong>Hiện tại:</strong> {r.original_text}
                      </p>
                      <p>
                        <strong>Đề xuất:</strong> {r.proposed_text}
                      </p>
                      <p>{r.reason}</p>
                      <button
                        disabled={busy}
                        onClick={() =>
                          change((d) => {
                            for (const s of d.document.sections)
                              for (const e of s.entries)
                                for (const b of e.bullets)
                                  if (
                                    b.source_refs.includes(r.source_ref) &&
                                    b.text === r.original_text
                                  )
                                    b.text = r.proposed_text;
                          })
                        }
                      >
                        Tôi đã kiểm tra — áp dụng đề xuất
                      </button>
                    </article>
                  ))}
                </details>
              )}
              {draft.form_refinement && (
                <p role="status">
                  {draft.form_refinement.status === "fallback"
                    ? "AI tạm thời không khả dụng. CV đang dùng nội dung form."
                    : `Đã tinh chỉnh ${draft.form_refinement.applied} câu. ${draft.form_refinement.rejected ? `Giữ câu nguồn cho ${draft.form_refinement.rejected} đề xuất lỗi.` : ""}`}
                </p>
              )}
              {Object.keys(draft.summary_options || {}).length > 0 && (
                <fieldset disabled={busy}>
                  <legend>Tóm tắt</legend>
                  {Object.entries(draft.summary_options).map(([ref, text]) => (
                    <label key={ref}>
                      <input
                        type="checkbox"
                        checked={
                          edit.document.summary?.source_refs.includes(ref) ||
                          false
                        }
                        disabled={
                          !edit.document.summary?.source_refs.includes(ref) &&
                          (edit.document.summary?.source_refs.length || 0) >= 2
                        }
                        onChange={(event) =>
                          change((next) => {
                            const refs = (
                              next.document.summary?.source_refs || []
                            ).filter((item) => item !== ref);
                            if (event.target.checked) refs.push(ref);
                            const text =
                              refs.length === 1 && refs[0] === "/summary"
                                ? draft.summary_options["/summary"]
                                : refs
                                    .map(
                                      (item) =>
                                        draft.summary_options[item].replace(
                                          /\.+$/,
                                          "",
                                        ) + ".",
                                    )
                                    .join(" ");
                            next.document.summary = refs.length
                              ? { text, source_refs: refs }
                              : null;
                          })
                        }
                      />
                      {text}
                    </label>
                  ))}
                  {edit.document.summary && <p>{edit.document.summary.text}</p>}
                </fieldset>
              )}
              <p className="note">
                Tên công ty, thời gian và liên hệ lấy từ hồ sơ đã xác nhận. Cập
                nhật hồ sơ khi cần sửa dữ kiện.
              </p>
              <fieldset disabled={busy}>
                <legend>Nội dung CV</legend>
                {edit.document.sections.map((s, si) => (
                  <section key={s.kind}>
                    <h2>{s.heading}</h2>
                    <div className="form-actions">
                      <button
                        disabled={si === 0}
                        onClick={() =>
                          change((d) => {
                            [
                              d.document.sections[si - 1],
                              d.document.sections[si],
                            ] = [
                              d.document.sections[si],
                              d.document.sections[si - 1],
                            ];
                          })
                        }
                      >
                        Đưa mục lên
                      </button>
                      <button
                        disabled={si === edit.document.sections.length - 1}
                        onClick={() =>
                          change((d) => {
                            [
                              d.document.sections[si + 1],
                              d.document.sections[si],
                            ] = [
                              d.document.sections[si],
                              d.document.sections[si + 1],
                            ];
                          })
                        }
                      >
                        Đưa mục xuống
                      </button>
                    </div>
                    {s.entries.map((e, ei) => (
                      <fieldset key={e.source_entry_id}>
                        <legend>{e.title}</legend>
                        <p>
                          {e.subtitle} {e.period}
                        </p>
                        {[
                          "experience",
                          "project",
                          "involvement",
                          "education",
                        ].includes(s.kind) && (
                          <>
                            {dirty && (
                              <small>
                                Lưu bản nháp để AI Writer sử dụng nội dung mới
                                nhất.
                              </small>
                            )}
                            <AIWriter
                              section={s.kind}
                              entry={e}
                              value={e.bullets.map((b) => b.text)}
                              disabled={busy || dirty}
                              onGenerate={(payload) =>
                                send(`/api/resumes/${id}/writer`, {
                                  expected_version: draft.version,
                                  section: s.kind,
                                  entry_id: e.source_entry_id,
                                  style: payload.style,
                                  count: payload.count,
                                })
                              }
                              onApply={async (
                                lines,
                                result,
                                selected,
                                mode,
                              ) => {
                                const updated = await send(
                                  `/api/resumes/${id}/writer/apply`,
                                  {
                                    expected_version: draft.version,
                                    proposal_id: result.proposal_id,
                                    selected,
                                    mode,
                                  },
                                );
                                loaded(updated);
                                setMessage("Đã áp dụng các bullet bạn chọn.");
                              }}
                            />
                          </>
                        )}
                        {e.bullets.map((b, bi) => (
                          <label key={b.source_refs.join("|")}>
                            Nội dung {bi + 1}
                            <textarea
                              value={b.text}
                              rows={3}
                              onChange={(ev) =>
                                change((d) => {
                                  d.document.sections[si].entries[ei].bullets[
                                    bi
                                  ].text = ev.target.value;
                                })
                              }
                            />
                            <button
                              className="secondary-button"
                              onClick={() =>
                                change((d) => {
                                  d.document.sections[si].entries[
                                    ei
                                  ].bullets.splice(bi, 1);
                                })
                              }
                            >
                              Ẩn nội dung
                            </button>
                          </label>
                        ))}
                      </fieldset>
                    ))}
                  </section>
                ))}
              </fieldset>
              <div className="form-actions">
                <button disabled={busy || !dirty} onClick={() => act("save")}>
                  Lưu bản nháp
                </button>
                <button
                  disabled={busy || history.current.length === 0}
                  onClick={() => {
                    setEdit(history.current.pop());
                    setPreview("");
                  }}
                >
                  Hoàn tác
                </button>
                <button disabled={busy} onClick={() => act("preview")}>
                  Xem trước
                </button>
                <button
                  disabled={busy}
                  onClick={() =>
                    change((d) => {
                      d.document = structuredClone(draft.baseline);
                    })
                  }
                >
                  Khôi phục nội dung nguồn
                </button>
                <button
                  disabled={busy}
                  onClick={() =>
                    act(draft.form_refinement ? "export" : "publish")
                  }
                >
                  {draft.form_refinement
                    ? "Lưu và xuất PDF"
                    : "Tôi đã kiểm tra — xác nhận CV"}
                </button>
                <button disabled={busy} onClick={() => act("duplicate")}>
                  Nhân bản CV
                </button>
                {draft.latest_cv_id && (
                  <a href={`/api/cv/versions/${draft.latest_cv_id}/pdf`}>
                    Tải PDF đã xác nhận
                  </a>
                )}
              </div>
            </div>
            <aside className="editor-preview">
              <div className="panel-heading">
                <h2>Bản xem trước</h2>
                <span role="status">
                  {previewBusy
                    ? "Đang cập nhật…"
                    : preview && dirty
                      ? "Xem thay đổi chưa lưu"
                      : "Bản đã lưu"}
                </span>
              </div>
              <p>
                {previewError ||
                  "Mẫu, màu sắc và kiểu chữ cập nhật theo lựa chọn của bạn."}
              </p>
              <CVPreviewFrame
                title="Xem trước CV"
                srcDoc={preview || undefined}
                src={
                  preview
                    ? undefined
                    : `/api/resumes/${id}/preview?v=${draft.version}`
                }
              />
            </aside>
          </div>
        </>
      )}
    </main>
  );
}
