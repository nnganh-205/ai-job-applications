import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import Icon from "../../components/ui/Icon.jsx";
import { request } from "../../lib/api.js";
import { formatSalary } from "../jobs/formatters.js";
import useLandingMotion from "./useLandingMotion.js";
import { HeroRail, PaperSkeleton, DocumentStage } from "./LandingVisuals.jsx";
import { faqItems, chatExamples } from "./homeContent.js";

const previewTemplates = [
  {
    id: "classic",
    name: "Harvard (Classic)",
    layout: "one-column",
    thumbnail: "/templates/previews/classic.png",
  },
  {
    id: "modern",
    name: "Horizon",
    layout: "two-column",
    thumbnail: "/templates/previews/modern.png",
  },
  {
    id: "ats",
    name: "Essential",
    layout: "one-column",
    thumbnail: "/templates/previews/ats.png",
  },
];
const roles = [
  "Sinh viên",
  "Lập trình viên",
  "Nhà thiết kế",
  "Chuyên viên marketing",
  "Người đang tìm cơ hội mới",
];
const normalize = (text) =>
  text
    .toLocaleLowerCase("vi")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/đ/g, "d");
function Action({
  to = "/workspace/resumes/new",
  children = "Tạo CV của bạn",
  secondary = false,
}) {
  return (
    <Link
      className={secondary ? "zen-button zen-button-quiet" : "zen-button"}
      to={to}
    >
      {children}
      <Icon name="arrow" size={17} />
    </Link>
  );
}

export default function HomePage() {
  const root = useLandingMotion();
  const [jobs, setJobs] = useState([]);
  const [templates, setTemplates] = useState(previewTemplates);
  const [loading, setLoading] = useState(true);
  const [jobError, setJobError] = useState(false);
  const [chat, setChat] = useState(0);
  const [edited, setEdited] = useState(false);
  const [query, setQuery] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    Promise.allSettled([
      request("/api/dashboard", { signal: controller.signal }),
      request("/api/cv/templates", { signal: controller.signal }),
    ]).then(([dashboard, gallery]) => {
      if (controller.signal.aborted) return;
      if (dashboard.status === "fulfilled")
        setJobs(dashboard.value.jobs.slice(0, 3));
      else setJobError(true);
      if (gallery.status === "fulfilled" && gallery.value.length)
        setTemplates(gallery.value);
      setLoading(false);
    });
    return () => controller.abort();
  }, []);
  const example = chatExamples[chat];
  const filteredFaq = faqItems.filter(([question, answer]) =>
    normalize(question + answer).includes(normalize(query.trim())),
  );
  return (
    <main ref={root} className="home-page zen-home">
      <section className="zen-hero" aria-labelledby="zen-hero-title">
        <div className="zen-hero-light" aria-hidden="true" />
        <div className="zen-stars" aria-hidden="true" />
        <div className="zen-container zen-hero-copy">
          <div className="zen-pill">
            <span className="zen-status-dot" /> Từ những gì bạn đã làm, đến cơ
            hội tiếp theo
          </div>
          <h1 id="zen-hero-title">
            Kể câu chuyện của bạn.
            <br />
            <span>Mở lối sự nghiệp.</span>
          </h1>
          <p>
            Biến kinh nghiệm thành một bản CV rõ ràng, chỉn chu.
            <br className="zen-desktop-break" /> Cùng AI hoàn thiện từng câu
            chữ, tự tin cho bước tiếp theo.
          </p>
          <div className="zen-hero-actions">
            <Action />
            <Link className="zen-text-link" to="/templates">
              Khám phá mẫu CV <Icon name="diagonal" size={16} />
            </Link>
          </div>
          <div className="zen-hero-facts">
            <div>
              <strong>01 hồ sơ</strong>
              <span>Nhiều cách thể hiện</span>
            </div>
            <div>
              <strong>06 mẫu CV</strong>
              <span>Chọn phong cách của bạn</span>
            </div>
            <div>
              <Icon name="shield" size={23} />
              <span>Bạn duyệt mọi thay đổi</span>
            </div>
          </div>
        </div>
        <HeroRail />
        <a href="#hanh-trinh" className="zen-scroll-hint">
          <span>Cuộn để khám phá</span>
          <span aria-hidden="true">↓</span>
        </a>
      </section>

      <section
        className="zen-letter-wrap zen-container"
        id="hanh-trinh"
        aria-labelledby="zen-letter-title"
      >
        <article className="zen-letter" data-reveal>
          <div className="zen-window-bar">
            <span className="zen-window-dots">
              <i />
              <i />
              <i />
            </span>
            <span>
              <Icon name="file" size={14} /> Một lời nhắn dành cho bạn
            </span>
            <span>Hộp thư đến</span>
          </div>
          <div className="zen-letter-body">
            <div className="zen-letter-heading">
              <span className="zen-letter-avatar">
                <Icon name="chat" size={22} />
              </span>
              <div>
                <strong>Một lời nhắn dành cho bạn</strong>
                <small>người đang chuẩn bị cho bước tiếp theo</small>
              </div>
              <Icon name="bookmark" size={18} />
            </div>
            <h2 id="zen-letter-title">
              Cơ hội tốt bắt đầu từ
              <br />
              một câu chuyện được kể rõ.
            </h2>
            <p className="zen-letter-statement">
              Bạn đã có kinh nghiệm, kiến thức và những điều đáng tự hào.{" "}
              <span>
                Chúng mình giúp bạn sắp xếp lại, diễn đạt tốt hơn và nhìn rõ
                công việc phù hợp.
              </span>{" "}
              <em>Từng bước một. Theo cách của bạn.</em>
            </p>
            <div className="zen-letter-signature">
              Đồng hành cùng bạn. <Icon name="chat" size={15} />
            </div>
          </div>
        </article>
      </section>

      <section
        className="zen-upload zen-container"
        id="bat-dau"
        aria-labelledby="zen-upload-title"
        data-reveal
      >
        <h2 id="zen-upload-title">
          Một bản CV. <span>Một góc nhìn mới.</span>
        </h2>
        <p className="zen-section-description">
          Tải CV hiện có để chuẩn bị hồ sơ, rà soát nội dung
          <br className="zen-desktop-break" /> và khám phá những điều bạn có thể
          làm tốt hơn.
        </p>
        <div className="zen-upload-card">
          <span className="zen-card-glow" aria-hidden="true" />
          <h3>Mang câu chuyện của bạn vào đây.</h3>
          <Link className="zen-upload-target" to="/workspace/import">
            <div className="zen-file-icons" aria-hidden="true">
              <img
                src="/images/home/file-pdf.svg"
                alt=""
                width="70"
                height="83"
              />
              <img
                src="/images/home/file-doc.svg"
                alt=""
                width="70"
                height="83"
              />
            </div>
            <span>
              <u>Chọn CV của bạn</u> để bắt đầu <Icon name="arrow" size={16} />
            </span>
            <small>
              <Icon name="shield" size={14} /> Kiểm tra và xác nhận thông tin
              trước khi dùng
            </small>
          </Link>
          <div className="zen-upload-meta">
            <span>PDF, DOCX có văn bản · Tối đa 5 MB</span>
            <Link to="/workspace">
              Chưa có CV? Tạo hồ sơ mới <Icon name="arrow" size={14} />
            </Link>
          </div>
        </div>
      </section>

      <section
        className="zen-features zen-container"
        id="tinh-nang"
        aria-label="AI đồng hành cùng bạn"
      >
        <div className="zen-feature-grid">
          <article className="zen-feature zen-chat-feature" data-reveal>
            <div className="zen-feature-heading">
              <h2>
                Trợ lý AI <Icon name="chat" size={26} />
                <span>Hiểu câu chuyện của bạn.</span>
              </h2>
              <p>
                Gỡ rối từng mục trong CV, đối chiếu yêu cầu công việc và chuẩn
                bị cho buổi phỏng vấn tiếp theo.
              </p>
            </div>
            <div className="zen-chat-demo">
              <div className="zen-demo-label">
                <span className="zen-status-dot" /> Minh họa cách sử dụng
              </div>
              <div
                className="zen-chat-tabs"
                role="group"
                aria-label="Chọn tình huống minh họa"
              >
                {chatExamples.map((item, i) => (
                  <button
                    key={item.label}
                    aria-pressed={chat === i}
                    onClick={() => setChat(i)}
                  >
                    {item.label}
                  </button>
                ))}
              </div>
              <div className="zen-conversation" key={chat}>
                <p className="zen-chat-question">{example.question}</p>
                <div className="zen-chat-answer">
                  <Icon name="chat" size={21} />
                  <p>{example.answer}</p>
                </div>
              </div>
              <Link className="zen-chat-input" to="/workspace/assistant">
                <span>Bạn muốn chuẩn bị điều gì hôm nay?</span>
                <span aria-hidden="true">↑</span>
              </Link>
            </div>
          </article>
          <article className="zen-feature zen-edit-feature" data-reveal>
            <div className="zen-feature-heading">
              <h2>
                Câu chữ chỉn chu.<span>Dấu ấn vẫn là của bạn.</span>
              </h2>
              <p>
                Gợi ý ngắn gọn, rõ ý hơn từ thông tin đã nhập. Giữ nguyên vai
                trò, con số và những điều bạn thực sự đã làm.
              </p>
            </div>
            <div className="zen-edit-demo">
              <PaperSkeleton />
              <div className="zen-edit-selection">
                <small>MINH HỌA · KINH NGHIỆM</small>
                <p>{edited ? chatExamples[0].after : chatExamples[0].before}</p>
                <i />
                <i />
                <i />
                <i />
              </div>
              <div className="zen-suggestion">
                <span>
                  <Icon name="chat" size={17} />{" "}
                  {edited
                    ? "Gọn hơn, vẫn đúng thông tin gốc"
                    : "Một câu rõ hơn đang chờ bạn"}
                </span>
                <button onClick={() => setEdited(!edited)}>
                  {edited ? "Xem câu gốc" : "Xem gợi ý chỉnh câu"}
                  <Icon name={edited ? "refresh" : "arrow"} size={16} />
                </button>
              </div>
            </div>
          </article>
        </div>
        <div className="zen-center-action" data-reveal>
          <Action to="/workspace/assistant">Mở trợ lý của bạn</Action>
          <small>Thông tin thật. Quyết định của bạn.</small>
        </div>
      </section>

      <section
        className="zen-templates zen-container"
        aria-labelledby="zen-template-title"
      >
        <div className="zen-section-heading" data-reveal>
          <div>
            <h2 id="zen-template-title">
              Cùng một câu chuyện.
              <br />
              <span>Nhiều cách thể hiện.</span>
            </h2>
          </div>
          <Action to="/templates" secondary>
            Xem tất cả mẫu CV
          </Action>
        </div>
        <div
          className="zen-template-track"
          aria-label="Các mẫu CV có thể chỉnh sửa"
        >
          {templates.map((template, index) => (
            <Link
              className="zen-template"
              key={template.id}
              to={"/workspace/resumes/new?template=" + template.id}
            >
              <div className="zen-template-image">
                <span className="zen-template-number">0{index + 1}</span>
                <img
                  loading="lazy"
                  src={template.thumbnail}
                  width="600"
                  height="849"
                  alt={"Xem mẫu CV " + template.name}
                />
                <span className="zen-template-open">
                  Dùng mẫu này <Icon name="arrow" size={16} />
                </span>
              </div>
              <div className="zen-template-caption">
                <div>
                  <h3>{template.name}</h3>
                  <span>
                    {template.layout === "two-column"
                      ? "Hai cột · Hiện đại"
                      : "Một cột · Gọn gàng"}
                  </span>
                </div>
                <Icon name="diagonal" size={20} />
              </div>
            </Link>
          ))}
        </div>
        <p className="zen-track-note">
          Kéo ngang để khám phá các mẫu. Đổi mẫu bất cứ lúc nào.
        </p>
      </section>

      <section
        className="zen-possibilities"
        aria-labelledby="zen-role-title"
        data-reveal
      >
        <div className="zen-role-orbit" aria-hidden="true">
          {["SQL", "CV", "UI", "AI", "PDF", "</>"].map((text, i) => (
            <span key={text} style={{ "--orbit-index": i }}>
              {text}
            </span>
          ))}
          <Icon name="chat" size={42} />
        </div>
        <h2 id="zen-role-title">
          Dành cho những người
          <br />
          luôn muốn <span>tiến xa hơn.</span>
        </h2>
        <p>
          Bạn mới bắt đầu, đang chuyển hướng hay tìm thử thách mới?
          <br />
          Hãy bắt đầu bằng câu chuyện của chính mình.
        </p>
        <div className="zen-role-marquee">
          <div>
            {[0, 1].map((copy) => (
              <div key={copy} aria-hidden={copy === 1 ? true : undefined}>
                {roles.map((role) => (
                  <span key={role}>
                    <Icon name="chat" size={15} />
                    {role}
                  </span>
                ))}
              </div>
            ))}
          </div>
        </div>
      </section>

      <section
        className="zen-jobs zen-container"
        aria-labelledby="zen-jobs-title"
        data-reveal
      >
        <div className="zen-section-heading">
          <div>
            <h2 id="zen-jobs-title">
              Khám phá cơ hội. <span>Tìm hướng đi.</span>
            </h2>
          </div>
          <Action to="/jobs" secondary>
            Xem việc làm
          </Action>
        </div>
        <div className="zen-job-grid">
          {loading
            ? [0, 1, 2].map((i) => (
                <div key={i} className="zen-job-loading" aria-hidden="true">
                  <i />
                  <i />
                  <i />
                </div>
              ))
            : jobs.map((job) => (
                <Link
                  className="zen-job"
                  key={job.posting_id}
                  to={"/jobs/" + job.posting_id}
                >
                  <div className="zen-job-top">
                    <span>
                      <Icon name="briefcase" size={20} />
                    </span>
                    <small>{job.company || "Công ty chưa công bố"}</small>
                    <Icon name="diagonal" size={17} />
                  </div>
                  <h3>{job.title}</h3>
                  <p>
                    <Icon name="pin" size={14} />
                    {job.location || "Địa điểm chưa công bố"}
                  </p>
                  <div className="zen-job-bottom">
                    <strong>{formatSalary(job)}</strong>
                    <span>Xem chi tiết →</span>
                  </div>
                </Link>
              ))}
        </div>
        {!loading && !jobs.length && (
          <p className="zen-empty" role="status">
            {jobError
              ? "Chưa tải được việc làm. Bạn có thể mở trang việc làm để thử lại."
              : "Chưa có tin tuyển dụng để giới thiệu. Khám phá trang việc làm để cập nhật cơ hội mới."}
          </p>
        )}
      </section>

      <section
        className="zen-faq zen-container"
        id="cau-hoi"
        aria-labelledby="zen-faq-title"
        data-reveal
      >
        <div className="zen-faq-heading">
          <h2 id="zen-faq-title">
            Bắt đầu <span>đơn giản hơn.</span>
          </h2>
          <p>Câu trả lời ngắn gọn để bạn yên tâm chuẩn bị hồ sơ.</p>
        </div>
        <div className="zen-faq-layout">
          <div className="zen-faq-main">
            <label className="zen-faq-search">
              <Icon name="search" size={18} />
              <input
                type="search"
                aria-label="Tìm câu hỏi thường gặp"
                placeholder="Tìm câu hỏi của bạn..."
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
            </label>
            <div className="zen-faq-items">
              {filteredFaq.map(([question, answer]) => (
                <details key={question}>
                  <summary>
                    {question}
                    <span aria-hidden="true">+</span>
                  </summary>
                  <p>{answer}</p>
                </details>
              ))}
              {!filteredFaq.length && (
                <div className="zen-empty" role="status">
                  Chưa tìm thấy câu hỏi phù hợp.
                  <button onClick={() => setQuery("")}>
                    Xem tất cả câu hỏi
                  </button>
                </div>
              )}
            </div>
          </div>
          <aside className="zen-faq-aside">
            <span className="zen-aside-icon">
              <Icon name="chat" size={25} />
            </span>
            <h3>Bạn đã sẵn sàng?</h3>
            <p>
              Một bước nhỏ hôm nay.
              <br />
              Một cơ hội mới ngày mai.
            </p>
            <Action />
            <div className="zen-shortcuts">
              <span>KHÁM PHÁ NHANH</span>
              <Link to="/templates">
                Mẫu CV <Icon name="arrow" size={14} />
              </Link>
              <Link to="/workspace/assistant">
                Trợ lý AI <Icon name="arrow" size={14} />
              </Link>
              <Link to="/workspace/interviews">
                Luyện phỏng vấn <Icon name="arrow" size={14} />
              </Link>
            </div>
          </aside>
        </div>
      </section>

      <section
        className="zen-ending"
        id="laptop-preview"
        aria-labelledby="zen-ending-title"
      >
        <div className="zen-ending-copy zen-container" data-reveal>
          <h2 id="zen-ending-title">
            Chăm chút từng câu chữ.
            <br />
            <span>Tự tin với mỗi lần gửi đi.</span>
          </h2>
          <Action />
        </div>
        <DocumentStage />
      </section>
    </main>
  );
}
