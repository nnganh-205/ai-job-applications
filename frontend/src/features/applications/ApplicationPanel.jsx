import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { request } from "../../services/api.js";
export const statusNames = {
  untracked: "Chưa theo dõi",
  saved: "Đang chuẩn bị",
  opened_source: "Đã mở nguồn",
  applied: "Đã xác nhận gửi hồ sơ",
  interviewing: "Đang phỏng vấn",
  offer: "Có offer",
  rejected: "Đã nhận từ chối",
  withdrawn: "Đã rút hồ sơ",
};
export default function ApplicationPanel({ job, evaluation }) {
  const [tracker, setTracker] = useState(null),
    [versions, setVersions] = useState([]),
    [cv, setCV] = useState(
      evaluation?.input_type === "cv" ? evaluation.input_id : "",
    ),
    [error, setError] = useState(""),
    [message, setMessage] = useState(""),
    [busy, setBusy] = useState(false);
  useEffect(() => {
    const c = new AbortController();
    setTracker(null);
    setError("");
    Promise.all([
      request("/api/applications/" + job.posting_id, { signal: c.signal }),
      request("/api/resumes/published", { signal: c.signal }),
    ])
      .then(([a, v]) => {
        if (!c.signal.aborted) {
          setTracker(a);
          setVersions(v);
          setCV(
            evaluation?.input_type === "cv"
              ? evaluation.input_id
              : a.cv_id || "",
          );
        }
      })
      .catch((e) => {
        if (e.name !== "AbortError") setError(e.message);
      });
    return () => c.abort();
  }, [job.posting_id]);
  async function save(status) {
    setBusy(true);
    setError("");
    try {
      const result = await request(
        "/api/applications/" + job.posting_id + "/events",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            status,
            expected_version: tracker.version,
            event_id: crypto.randomUUID(),
            job_content_hash: job.content_hash,
            cv_id: cv || null,
            profile_id: cv
              ? null
              : evaluation?.input_type === "profile"
                ? evaluation.profile_id
                : null,
          }),
        },
      );
      setTracker(result);
      setMessage(
        status === "opened_source"
          ? "Đã ghi nhận thao tác mở nguồn. Chưa xác nhận bạn đã gửi hồ sơ."
          : "Đã lưu trạng thái do bạn xác nhận.",
      );
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  const url = job.apply_url || job.source_url;
  return (
    <section className="application-review" aria-label="Chuẩn bị ứng tuyển">
      <h2>Kiểm tra trước khi ứng tuyển</h2>
      <p>
        Chọn đúng bản CV đã publish. Điểm phù hợp chỉ hỗ trợ đối chiếu JD, không
        phải xác suất được tuyển.
      </p>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {!tracker && !error && <p role="status">Đang tải lịch sử theo dõi…</p>}
      {tracker && (
        <>
          <label>
            CV dự định dùng
            <select
              value={cv}
              disabled={busy}
              onChange={(e) => setCV(e.target.value)}
            >
              <option value="">Chưa liên kết CV</option>
              {versions.map((v) => (
                <option key={v.cv_id} value={v.cv_id}>
                  {v.title || "CV đã publish"} · {v.cv_id.slice(-6)}
                </option>
              ))}
            </select>
          </label>
          {cv ? (
            <a href={"/api/cv/versions/" + cv + "/pdf"}>
              Kiểm tra PDF đã publish ↗
            </a>
          ) : (
            <p className="notice">
              Chưa chọn CV. Bạn có thể{" "}
              <Link to="/workspace/resumes">chuẩn bị CV trong thư viện</Link>{" "}
              hoặc tự tiếp tục trên nguồn.
            </p>
          )}
          {evaluation?.matching?.score != null && (
            <p>
              Mức đáp ứng{" "}
              {evaluation.input_type === "cv"
                ? "của CV đang được đánh giá"
                : "của Master Profile"}
              : <strong>{Math.round(evaluation.matching.score)}%</strong>.{" "}
              {cv && evaluation.input_id !== cv
                ? "Kết quả này chưa đánh giá CV bạn vừa chọn; đổi đầu vào ở đầu trang để đối chiếu đúng version."
                : ""}
            </p>
          )}
          <p>
            <strong>Trạng thái:</strong> {statusNames[tracker.status]}
          </p>
          <div className="form-actions">
            <button disabled={busy} onClick={() => save("saved")}>
              Theo dõi / chuẩn bị
            </button>
            {url && !busy && (
              <a
                className="button-link"
                href={url}
                target="_blank"
                rel="noopener noreferrer"
                onClick={() => save("opened_source")}
              >
                Mở trang ứng tuyển nguồn ↗
              </a>
            )}
            <button disabled={busy} onClick={() => save("applied")}>
              Tôi xác nhận đã gửi hồ sơ
            </button>
          </div>
          <label>
            Cập nhật quá trình
            <select
              value={
                ["interviewing", "offer", "rejected", "withdrawn"].includes(
                  tracker.status,
                )
                  ? tracker.status
                  : ""
              }
              disabled={busy}
              onChange={(e) => {
                if (e.target.value) save(e.target.value);
              }}
            >
              <option value="">Chọn trạng thái bạn đã nhận</option>
              <option value="interviewing">Đang phỏng vấn</option>
              <option value="offer">Có offer</option>
              <option value="rejected">Đã nhận từ chối</option>
              <option value="withdrawn">Đã rút hồ sơ</option>
            </select>
          </label>
          <p className="note">
            Mở link không đồng nghĩa đã nộp CV. Ứng dụng không tự gửi hồ sơ cho
            nhà tuyển dụng.
          </p>
          {message && <p role="status">{message}</p>}
          {tracker.events.length > 0 && (
            <details>
              <summary>Lịch sử ({tracker.events.length})</summary>
              <ol>
                {tracker.events.map((e) => (
                  <li key={e.event_id}>
                    {statusNames[e.action]} ·{" "}
                    {new Date(e.at).toLocaleString("vi-VN")}
                  </li>
                ))}
              </ol>
            </details>
          )}
        </>
      )}
    </section>
  );
}
