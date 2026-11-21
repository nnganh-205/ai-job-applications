import React, { useEffect, useRef, useState } from "react";
import { request } from "../../lib/api.js";
import { send } from "./ResumeLibrary.jsx";
import ProfileLivePreview from "./ProfileLivePreview.jsx";
import CVPreviewFrame from "../../components/ui/CVPreviewFrame.jsx";

export default function ResumeHistory({ id, onClose, onRestored }) {
  const dialog = useRef(null),
    event = useRef(null);
  const [data, setData] = useState(null),
    [selected, setSelected] = useState(null),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [archive, setArchive] = useState(false),
    [confirm, setConfirm] = useState(false);
  useEffect(() => {
    dialog.current.showModal();
    const c = new AbortController();
    request(`/api/resumes/${id}/history`, { signal: c.signal })
      .then((d) => {
        setData(d);
        setSelected(d.versions[0]?.version);
      })
      .catch((e) => {
        if (e.name !== "AbortError") setError(e.message);
      });
    return () => c.abort();
  }, [id]);
  const [archived, setArchived] = useState(null);
  const target = data?.versions.find((v) => v.version === selected);
  async function restore() {
    setBusy(true);
    setError("");
    if (event.current?.version !== selected)
      event.current = { version: selected, id: crypto.randomUUID() };
    try {
      const result = await send(`/api/resumes/${id}/history/restore`, {
        expected_version: data.current_version,
        target_version: selected,
        event_id: event.current.id,
        editing_draft_version: archive ? data.editing_draft?.version : null,
      });
      onRestored(result);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <dialog
      className="resume-history-dialog"
      ref={dialog}
      aria-labelledby="resume-history-title"
      onCancel={(e) => {
        if (busy) e.preventDefault();
        else onClose();
      }}
    >
      <header>
        <div>
          <h2 id="resume-history-title">Lịch sử phiên bản</h2>
          <p>
            Khôi phục tạo phiên bản mới. Các bản cũ và PDF đã xuất vẫn được giữ
            nguyên.
          </p>
        </div>
        <button
          type="button"
          className="secondary-button"
          disabled={busy}
          aria-label="Đóng lịch sử"
          onClick={onClose}
        >
          ×
        </button>
      </header>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {!data && !error && <p role="status">Đang tải lịch sử…</p>}
      {data && (
        <div className="resume-history-layout">
          <aside aria-label="Danh sách phiên bản">
            {data.versions.map((v) => (
              <button
                type="button"
                disabled={busy}
                key={v.version}
                aria-pressed={v.version === selected}
                className={v.version === selected ? "selected" : ""}
                onClick={() => {
                  setArchived(null);
                  setSelected(v.version);
                  setConfirm(false);
                  setArchive(false);
                }}
              >
                <strong>
                  Phiên bản {v.version}
                  {v.current ? " · Hiện tại" : ""}
                </strong>
                <span>{v.title}</span>
                <small>
                  {v.created_at
                    ? new Date(v.created_at).toLocaleString("vi-VN")
                    : "Bản lưu trước đây"}
                </small>
              </button>
            ))}
            {data.archived_drafts?.length > 0 && (
              <details>
                <summary>
                  Bản nháp được lưu giữ ({data.archived_drafts.length})
                </summary>
                {data.archived_drafts.map((d) => (
                  <button
                    type="button"
                    key={d.draft_id}
                    disabled={busy}
                    onClick={async () => {
                      setBusy(true);
                      setError("");
                      try {
                        setArchived(
                          await request(
                            `/api/resumes/${id}/history/drafts/${d.draft_id}`,
                          ),
                        );
                      } catch (e) {
                        setError(e.message);
                      } finally {
                        setBusy(false);
                      }
                    }}
                  >
                    Xem bản nháp ·{" "}
                    {new Date(d.updated_at).toLocaleString("vi-VN")}
                  </button>
                ))}
              </details>
            )}
            <small>
              Chỉ hiển thị các phiên bản có dữ liệu lịch sử được lưu; không tạo
              lại những bản chưa từng được lưu.
            </small>
          </aside>
          <section aria-label="Xem phiên bản đã chọn">
            {archived ? (
              <>
                <h3>Bản nháp lưu giữ · Chỉ xem</h3>
                <p>Nội dung này chưa được áp dụng vào CV hiện tại.</p>
                <ProfileLivePreview profile={archived.profile} />
              </>
            ) : (
              <>
                <h3>
                  Phiên bản {selected}
                  {target?.current ? " · Đang dùng" : ""}
                </h3>
                <CVPreviewFrame
                  key={selected}
                  title={`Xem trước phiên bản ${selected}`}
                  src={`/api/resumes/${id}/history/${selected}/preview`}
                />
              </>
            )}
            {!archived && !target?.current && (
              <div className="resume-history-restore">
                {!target?.restorable ? (
                  <p>
                    Bản cũ này thiếu dữ liệu kiểm chứng nguồn nên hiện chỉ xem
                    lại được.
                  </p>
                ) : (
                  <>
                    {data.editing_draft && (
                      <label>
                        <input
                          type="checkbox"
                          checked={archive}
                          disabled={busy}
                          onChange={(e) => setArchive(e.target.checked)}
                        />{" "}
                        Giữ bản nháp đang sửa trong lịch sử và mở CV theo phiên
                        bản đã chọn.
                      </label>
                    )}
                    <label>
                      <input
                        type="checkbox"
                        checked={confirm}
                        disabled={busy}
                        onChange={(e) => setConfirm(e.target.checked)}
                      />{" "}
                      Khôi phục nội dung và thiết kế của phiên bản {selected}{" "}
                      thành phiên bản {data.current_version + 1}.
                    </label>
                    <button
                      type="button"
                      disabled={
                        busy || !confirm || (!!data.editing_draft && !archive)
                      }
                      onClick={restore}
                    >
                      {busy ? "Đang khôi phục…" : "Khôi phục phiên bản này"}
                    </button>
                  </>
                )}
              </div>
            )}
          </section>
        </div>
      )}
    </dialog>
  );
}
