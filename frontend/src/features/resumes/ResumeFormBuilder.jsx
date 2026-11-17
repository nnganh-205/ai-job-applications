import React, { useState, useRef, useLayoutEffect } from "react";
import { Link } from "react-router-dom";
import Icon from "../../components/ui/Icon.jsx";
import ProfileForm from "../profile/ProfileForm.jsx";
import ProfileLivePreview from "./ProfileLivePreview.jsx";
import {
  writingQuality,
  entryTitle,
  quickEditorialEdits,
} from "./writingQuality.js";

const groups = [
  [
    "contact",
    "Về bạn",
    "user",
    "Thông tin để nhà tuyển dụng liên hệ với bạn.",
    "Dùng email chuyên nghiệp. Chỉ cung cấp thông tin liên hệ bạn muốn xuất hiện trên CV.",
  ],
  [
    "education",
    "Học vấn",
    "file",
    "Nền tảng học tập và những kiến thức liên quan.",
    "Ưu tiên chương trình gần đây nhất. GPA và môn học liên quan là tùy chọn.",
  ],
  [
    "experience",
    "Kinh nghiệm",
    "briefcase",
    "Kể rõ vai trò, công việc và đóng góp thực tế của bạn.",
    "Mỗi dòng một ý. Giữ đúng mức độ đóng góp; chỉ thêm số liệu khi bạn có dữ liệu thật.",
  ],
  [
    "project",
    "Dự án",
    "grid",
    "Thể hiện những gì bạn đã trực tiếp thực hiện.",
    "Nêu mục tiêu, vai trò, công nghệ và kết quả. Dự án học phần cũng là kinh nghiệm hữu ích.",
  ],
  [
    "skills",
    "Kỹ năng",
    "spark",
    "Những công cụ và kỹ năng bạn có thể sử dụng.",
    "Chia nhóm kỹ thuật và kỹ năng mềm. Mỗi dòng một kỹ năng, không thêm kỹ năng chỉ vì JD yêu cầu.",
  ],
  [
    "involvement",
    "Hoạt động",
    "user",
    "Hoạt động ngoại khóa, tình nguyện hoặc cộng đồng.",
    "Nêu tổ chức, vai trò và đóng góp. Bạn có thể bỏ qua mục không phù hợp.",
  ],
  [
    "summary",
    "Tóm tắt",
    "edit",
    "Giới thiệu ngắn gọn về định hướng và điểm mạnh của bạn.",
    "Có thể để trống. Khi bật AI, hệ thống có thể ghép tóm tắt từ những dữ kiện bạn đã nhập.",
  ],
];

const sectionOrder = [
  "contact",
  "experience",
  "project",
  "education",
  "involvement",
  "skills",
  "summary",
];
groups.sort((a, b) => sectionOrder.indexOf(a[0]) - sectionOrder.indexOf(b[0]));

export default function ResumeFormBuilder({
  profile,
  initialProfile,
  schema,
  onChange,
  busy,
  confirmed,
  dirty,
  version,
  error,
  message,
  refine,
  setRefine,
  onSave,
  onPreview,
  onEdit,
  embedded = false,
  onClose,
}) {
  const pageRef = useRef(null),
    toolbarRef = useRef(null);
  useLayoutEffect(() => {
    const header = document.querySelector(".site-header");
    const measure = () => {
      pageRef.current?.style.setProperty(
        "--compose-header-height",
        `${header?.getBoundingClientRect().height || 78}px`,
      );
      pageRef.current?.style.setProperty(
        "--compose-toolbar-height",
        `${toolbarRef.current?.getBoundingClientRect().height || 74}px`,
      );
    };
    const observer = new ResizeObserver(measure);
    if (header) observer.observe(header);
    if (toolbarRef.current) observer.observe(toolbarRef.current);
    measure();
    return () => observer.disconnect();
  }, []);
  const [quick, setQuick] = useState([]),
    [undo, setUndo] = useState([]);
  const [active, setActive] = useState(
    profile.experience.length
      ? "experience"
      : profile.project.length
        ? "project"
        : "contact",
  );
  const [indices, setIndices] = useState({}),
    [showPreview, setShowPreview] = useState(false),
    [writerAction, setWriterAction] = useState(null);
  const meta = groups.find((g) => g[0] === active) || groups[0];
  const entries = Array.isArray(profile[active]) ? profile[active] : [];
  const index = Math.min(indices[active] || 0, Math.max(0, entries.length - 1));
  const entry = entries[index] || {};
  const quality = writingQuality(entry),
    narrative = ["experience", "project", "education", "involvement"].includes(
      active,
    );
  const ready = !!profile.contact.full_name?.trim();
  const disabled = busy || confirmed;
  function select(section) {
    setActive(section);
    setWriterAction(null);
    setQuick([]);
    setUndo([]);
  }
  function add() {
    setQuick([]);
    setUndo([]);
    onChange({ ...profile, [active]: [...entries, {}] });
    setIndices({ ...indices, [active]: entries.length });
  }
  function remove() {
    setQuick([]);
    setUndo([]);
    onChange({ ...profile, [active]: entries.filter((_, i) => i !== index) });
    setIndices({ ...indices, [active]: Math.max(0, index - 1) });
  }
  function reorder(delta) {
    setQuick([]);
    setUndo([]);
    const next = [...entries];
    [next[index], next[index + delta]] = [next[index + delta], next[index]];
    onChange({ ...profile, [active]: next });
    setIndices({ ...indices, [active]: index + delta });
  }
  function optimize(check) {
    const fixes = quickEditorialEdits(entry, check);
    if (fixes.length) {
      setQuick(fixes);
      return;
    }
    setQuick([]);
    setWriterAction({
      style: check === "length" ? "concise" : "professional",
      nonce: Date.now(),
    });
  }
  function applyQuick(revert = false) {
    const changes = revert ? undo : quick;
    if (
      !changes.length ||
      changes.some(
        (e) =>
          JSON.stringify(entry[e.field]) !==
          JSON.stringify(revert ? e.proposed : e.original),
      )
    ) {
      setQuick([]);
      setUndo([]);
      return;
    }
    const next = { ...entry };
    for (const e of changes) next[e.field] = revert ? e.original : e.proposed;
    onChange({
      ...profile,
      [active]: entries.map((e, i) => (i === index ? next : e)),
    });
    setUndo(revert ? [] : changes);
    setQuick([]);
  }
  return (
    <main
      ref={pageRef}
      className={
        "resume-compose" + (embedded ? " resume-compose-embedded" : "")
      }
    >
      <header ref={toolbarRef} className="compose-toolbar">
        {embedded ? (
          <button className="compose-back" onClick={onClose} disabled={busy}>
            ← Bản CV
          </button>
        ) : (
          <Link to="/workspace/resumes" className="compose-brand">
            <span>
              <Icon name="file" size={22} />
            </span>
            <div>
              CV của bạn<small>Không gian biên tập</small>
            </div>
          </Link>
        )}
        <span className="compose-save-state" role="status">
          <i className={dirty ? "unsaved" : ""} />
          {busy
            ? "Đang xử lý…"
            : confirmed
              ? "Đã xác nhận"
              : dirty
                ? "Chưa lưu thay đổi"
                : `Đã lưu · v${version}`}
        </span>
        {confirmed ? (
          <button onClick={onEdit} disabled={busy}>
            Chỉnh sửa thông tin
          </button>
        ) : (
          <button onClick={onSave} disabled={busy || !dirty}>
            <Icon name="check" size={14} /> Lưu nháp
          </button>
        )}
        <button
          onClick={() => setShowPreview(!showPreview)}
          aria-pressed={showPreview}
        >
          <Icon name="file" size={14} />
          {showPreview ? "Ẩn xem trước" : "Xem trước"}
        </button>
        <button
          className="compose-finish"
          onClick={onPreview}
          disabled={busy || !ready}
        >
          {embedded ? "Hoàn tất chỉnh sửa" : "Hoàn tất & chọn mẫu"}{" "}
          <Icon name="arrow" size={14} />
        </button>
      </header>
      <nav className="compose-tabs" aria-label="Các phần của CV">
        {groups.map(([key, title, icon]) => (
          <button
            key={key}
            className={active === key ? "active" : ""}
            aria-current={active === key ? "step" : undefined}
            onClick={() => select(key)}
          >
            <Icon name={icon} size={15} />
            {title}
            {(key === "contact"
              ? ready
              : key === "summary"
                ? !!profile.summary
                : profile[key]?.length > 0) && (
              <span className="compose-tab-dot" />
            )}
          </button>
        ))}
      </nav>
      {error && (
        <p className="error compose-notice" role="alert">
          {error}
        </p>
      )}
      {message && (
        <p className="compose-notice" role="status">
          {message}
        </p>
      )}
      <div className={"compose-layout" + (showPreview ? " with-preview" : "")}>
        <aside className="compose-sidebar">
          {narrative ? (
            <section className="compose-quality">
              <div
                className="compose-score"
                style={{ "--score": quality.score + "%" }}
              >
                <span>{quality.lines.length ? quality.score : "—"}</span>
              </div>
              <div>
                <strong>Chất lượng câu chữ</strong>
                <p>
                  {!quality.lines.length
                    ? "Bắt đầu bằng việc bạn đã làm"
                    : quality.score === 100
                      ? "Câu chữ rõ ràng, nhất quán"
                      : "Còn những điểm có thể cải thiện"}
                </p>
              </div>
              <small>
                Kiểm tra cách trình bày, không phải điểm phù hợp tuyển dụng.
              </small>
            </section>
          ) : (
            <section className="compose-section-note">
              <Icon name={meta[2]} size={24} />
              <h2>{meta[1]}</h2>
              <p>{meta[3]}</p>
            </section>
          )}
          <div className="compose-list-heading">
            <h2>{meta[1]}</h2>
            {Array.isArray(profile[active]) && (
              <button
                aria-label={"Thêm " + meta[1].toLowerCase()}
                disabled={disabled}
                onClick={add}
              >
                +
              </button>
            )}
          </div>
          <div className="compose-entry-list">
            {entries.map((e, i) => (
              <button
                key={e.id || i}
                className={i === index ? "selected" : ""}
                onClick={() => {
                  setIndices({ ...indices, [active]: i });
                  setWriterAction(null);
                  setQuick([]);
                  setUndo([]);
                }}
              >
                <Icon name={meta[2]} size={15} />
                <span>
                  <strong>{entryTitle(e, active, i)}</strong>
                  <small>
                    {[
                      e.company || e.role || e.major || e.organization,
                      e.start_date,
                      e.end_date,
                    ]
                      .filter(Boolean)
                      .join(" · ") || "Bổ sung thông tin"}
                  </small>
                </span>
                <span className="compose-entry-index">
                  {String(i + 1).padStart(2, "0")}
                </span>
              </button>
            ))}
          </div>
          {narrative && entries.length > 0 && (
            <section className="compose-checks">
              <h3>Gợi ý tối ưu</h3>
              {quality.checks.map((check) => (
                <button
                  key={check.id}
                  className={"compose-check " + check.status}
                  onClick={() => optimize(check.id)}
                  disabled={disabled || check.status === "empty"}
                >
                  <span>
                    {check.status === "pass"
                      ? "✓"
                      : check.status === "empty"
                        ? "·"
                        : "!"}
                  </span>
                  <div>
                    <strong>{check.label}</strong>
                    {check.status === "warning" && (
                      <small>
                        Bullet {check.bad.join(", ")} · {check.help}
                      </small>
                    )}
                  </div>
                  <Icon name="arrow" size={12} />
                </button>
              ))}
              {quick.length > 0 && (
                <div className="compose-quickfix">
                  <strong>Đề xuất sửa nhanh</strong>
                  {quick.map((edit) => (
                    <div key={edit.field}>
                      <small>Trước</small>
                      <p>{edit.original.join("\n")}</p>
                      <small>Đề xuất</small>
                      <p>{edit.proposed.join("\n")}</p>
                    </div>
                  ))}
                  <button disabled={disabled} onClick={() => applyQuick()}>
                    Áp dụng gợi ý
                  </button>
                  <button onClick={() => setQuick([])}>Giữ nguyên</button>
                </div>
              )}
              {undo.length > 0 && (
                <button
                  className="compose-undo"
                  disabled={disabled}
                  onClick={() => applyQuick(true)}
                >
                  ↶ Hoàn tác sửa nhanh
                </button>
              )}
              <details>
                <summary>
                  {quality.passed}/{quality.total} tiêu chí trình bày đạt
                </summary>
                <p>
                  Chỉ mô tả phần bạn thực sự làm. Có thể bổ sung kết quả định
                  tính; số liệu chỉ dùng khi bạn đã có dữ liệu thật.
                </p>
              </details>
              <div className="compose-metric-note">
                <Icon name="spark" size={15} />
                <p>
                  {quality.hasMetric
                    ? "Đã có thông tin định lượng. Kiểm tra lại số liệu trước khi dùng."
                    : "Có kết quả thực tế? Bạn có thể bổ sung để bullet rõ hơn. Không bắt buộc thêm số liệu."}
                </p>
              </div>
            </section>
          )}
          <p className="compose-help">{meta[4]}</p>
        </aside>
        <section
          className="compose-editor"
          aria-label={"Biên tập " + meta[1].toLowerCase()}
        >
          <header className="compose-editor-heading">
            <div>
              <p className="eyebrow">
                {narrative
                  ? "KINH NGHIỆM CỦA BẠN, BẰNG LỜI CỦA BẠN"
                  : "THÔNG TIN CV"}
              </p>
              <h1>
                {entries.length ? entryTitle(entry, active, index) : meta[1]}
              </h1>
              <p>
                {entries.length
                  ? [
                      entry.company || entry.role || entry.major,
                      entry.start_date,
                      entry.end_date,
                    ]
                      .filter(Boolean)
                      .join(" · ")
                  : meta[3]}
              </p>
            </div>
            {entries.length > 0 && (
              <div className="compose-entry-tools">
                <button
                  title="Đưa lên"
                  aria-label="Đưa mục lên"
                  disabled={disabled || index === 0}
                  onClick={() => reorder(-1)}
                >
                  ↑
                </button>
                <button
                  title="Đưa xuống"
                  aria-label="Đưa mục xuống"
                  disabled={disabled || index === entries.length - 1}
                  onClick={() => reorder(1)}
                >
                  ↓
                </button>
                <button
                  aria-label="Xóa mục đang chọn"
                  disabled={disabled}
                  onClick={remove}
                >
                  <Icon name="close" size={14} />
                  <span>Xóa</span>
                </button>
              </div>
            )}
          </header>
          {Array.isArray(profile[active]) && !entries.length ? (
            <div className="compose-empty">
              <span>
                <Icon name={meta[2]} size={28} />
              </span>
              <h2>Thêm {meta[1].toLowerCase()} đầu tiên</h2>
              <p>
                {meta[3]} Chưa có mục này thì bạn có thể chuyển sang phần khác.
              </p>
              <button disabled={disabled} onClick={add}>
                + Thêm {meta[1].toLowerCase()}
              </button>
            </div>
          ) : (
            <ProfileForm
              key={active + "-" + index}
              profile={profile}
              initialProfile={initialProfile}
              schema={schema}
              section={active}
              onChange={onChange}
              disabled={disabled}
              compact
              entryIndex={index}
              hideEntryActions
              hideAdd
              writerAction={writerAction}
            />
          )}
          <footer className="compose-editor-footer">
            <small>
              <Icon name="check" size={14} /> Bạn luôn xem lại đề xuất trước khi
              áp dụng.
            </small>
            <div>
              <button
                disabled={groups.findIndex((g) => g[0] === active) === 0}
                onClick={() =>
                  select(
                    groups[groups.findIndex((g) => g[0] === active) - 1][0],
                  )
                }
              >
                ← Phần trước
              </button>
              {active === "summary" ? (
                <button
                  className="compose-finish"
                  disabled={busy || !ready}
                  onClick={onPreview}
                >
                  {embedded ? "Hoàn tất chỉnh sửa →" : "Chọn mẫu CV →"}
                </button>
              ) : (
                <button
                  onClick={() =>
                    select(
                      groups[groups.findIndex((g) => g[0] === active) + 1][0],
                    )
                  }
                >
                  Phần tiếp theo →
                </button>
              )}
            </div>
          </footer>
          {active === "summary" && !embedded && (
            <label className="compose-refine">
              <input
                type="checkbox"
                checked={refine}
                disabled={busy}
                onChange={(e) => setRefine(e.target.checked)}
              />{" "}
              Biên tập câu chữ khi tạo bản CV
            </label>
          )}
        </section>
        {showPreview && (
          <aside className="compose-preview">
            <div>
              <strong>Bản xem trước nội dung</strong>
              <span>
                {embedded
                  ? "Thiết kế CV hiện tại được giữ nguyên"
                  : "Chọn mẫu ở bước hoàn tất"}
              </span>
            </div>
            <ProfileLivePreview profile={profile} />
          </aside>
        )}
      </div>
    </main>
  );
}
