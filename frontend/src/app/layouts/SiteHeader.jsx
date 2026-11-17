import React, { useEffect, useRef, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import Icon from "../../components/ui/Icon.jsx";

const menus = [
  {
    id: "jobs", label: "Việc làm", paths: ["/jobs"],
    columns: [
      { title: "Khám phá cơ hội", links: [
        ["/jobs", "Tìm việc làm", "Tìm kiếm và lọc cơ hội phù hợp với bạn.", "search"],
        ["/workspace/applications", "Theo dõi ứng tuyển", "Quản lý những công việc bạn quan tâm.", "briefcase"],
      ] },
      { title: "Sẵn sàng ứng tuyển", links: [
        ["/workspace/resumes", "CV của bạn", "Chọn bản CV cho cơ hội tiếp theo.", "file"],
        ["/workspace/interviews", "Luyện phỏng vấn", "Chuẩn bị câu trả lời cùng AI.", "chat"],
      ] },
    ],
    feature: { tag: "BƯỚC TIẾP THEO", title: "Cơ hội mới, khởi đầu mới.", text: "Tìm một công việc phù hợp với những điều bạn đã làm.", to: "/jobs", cta: "Khám phá việc làm", art: "opportunity" },
  },
  {
    id: "templates", label: "Mẫu CV", paths: ["/templates", "/workspace/resumes", "/workspace/import"],
    columns: [
      { title: "Bắt đầu CV của bạn", links: [
        ["/workspace/resumes/new", "Tạo CV bằng form", "Điền thông tin, xem trước và chỉnh sửa.", "edit"],
        ["/workspace/resumes/chat", "Tạo CV qua chat", "Kể về bạn, cùng AI hoàn thiện nội dung.", "chat"],
        ["/workspace/import", "Tải CV có sẵn", "Tiếp tục từ hồ sơ bạn đang sử dụng.", "download"],
      ] },
      { title: "Chọn một phong cách", links: [
        ["/templates?category=basic", "Đơn giản & rõ ràng", "Bố cục gọn gàng, tập trung vào nội dung.", "file"],
        ["/templates?category=modern", "Hiện đại", "Điểm nhấn tinh tế cho hồ sơ của bạn.", "grid"],
        ["/templates?category=creative", "Sáng tạo", "Thể hiện cá tính qua cách trình bày.", "spark"],
        ["/templates?category=academic", "Học thuật", "Trình bày học vấn và nghiên cứu.", "bookmark"],
      ] },
    ],
    feature: { tag: "THƯ VIỆN MẪU CV", title: "Một diện mạo đúng với bạn.", text: "Chọn mẫu yêu thích và bắt đầu với câu chuyện của chính mình.", to: "/templates", cta: "Xem tất cả mẫu", art: "resume" },
  },
  {
    id: "events", label: "Sự kiện", paths: ["/events"],
    columns: [
      { title: "Kết nối & phát triển", links: [
        ["/events", "Sự kiện nghề nghiệp", "Khám phá các hoạt động và cơ hội kết nối.", "briefcase"],
        ["/jobs", "Cơ hội tuyển dụng", "Tiếp tục khám phá những vị trí mới.", "diagonal"],
      ] },
      { title: "Chuẩn bị trước khi tham gia", links: [
        ["/workspace/resumes", "Hoàn thiện CV", "Mang theo một hồ sơ chỉn chu.", "file"],
        ["/workspace/assistant", "Trao đổi cùng AI", "Gỡ rối các câu hỏi về CV và ứng tuyển.", "spark"],
      ] },
    ],
    feature: { tag: "MỞ RỘNG KẾT NỐI", title: "Gặp gỡ. Học hỏi. Tiến xa.", text: "Thêm những trải nghiệm mới cho hành trình nghề nghiệp.", to: "/events", cta: "Khám phá sự kiện", art: "opportunity" },
  },
  { id: "mine", label: "Trang của tôi", paths: ["/workspace"] },
  {
    id: "personal", label: "Cá nhân", paths: ["/workspace"],
    columns: [
      { title: "Không gian của bạn", links: [
        ["/workspace", "Tổng quan", "Theo dõi hành trình chuẩn bị của bạn.", "grid"],
        ["/workspace/resumes", "Thư viện CV", "Tất cả bản CV trong một không gian.", "file"],
        ["/workspace/applications", "Theo dõi ứng tuyển", "Tiếp tục những cơ hội đang theo đuổi.", "briefcase"],
      ] },
      { title: "Tiếp tục chuẩn bị", links: [
        ["/workspace/assistant", "Trợ lý AI", "Tiếp tục cuộc trò chuyện của bạn.", "spark"],
        ["/workspace/interviews", "Luyện phỏng vấn", "Tự tin hơn cho buổi gặp tiếp theo.", "chat"],
      ] },
    ],
    feature: { tag: "KHÔNG GIAN CÁ NHÂN", title: "Từng bước nhỏ. Thêm nhiều tự tin.", text: "CV, việc làm và sự chuẩn bị của bạn ở cùng một nơi.", to: "/workspace", cta: "Mở tổng quan", art: "resume" },
  },
];

function Chevron() {
  return <svg className="mega-chevron" width="13" height="13" viewBox="0 0 16 16" fill="none" aria-hidden="true"><path d="m4 6 4 4 4-4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" /></svg>;
}

function MenuPanel({ menu, open, close }) {
  const feature = menu.feature;
  return (
    <div className="mega-panel" id={`nav-panel-${menu.id}`} aria-labelledby={`nav-trigger-${menu.id}`} hidden={!open}>
      <div className="mega-panel-content">
        {menu.columns.map(column => <section className="mega-column" key={column.title}>
          <h2>{column.title}</h2>
          {column.links.map(([to, title, text, icon]) => <Link className="mega-link" to={to} key={to} onClick={close}>
            <span className="mega-link-icon"><Icon name={icon} size={19} /></span>
            <span><strong>{title}</strong><small>{text}</small></span>
            <Icon className="mega-link-arrow" name="diagonal" size={14} />
          </Link>)}
        </section>)}
        <Link className={`mega-feature mega-feature-${feature.art}`} to={feature.to} onClick={close}>
          <div className="mega-feature-art" aria-hidden="true">
            {feature.art === "resume" ? <><span className="mega-paper mega-paper-back" /><span className="mega-paper mega-paper-front"><i /><i /><i /><i /></span></> : <><span className="mega-art-tile"><Icon name={feature.art === "spark" ? "spark" : "briefcase"} size={36} /></span><span className="mega-art-orb" /><span className="mega-art-dot" /></>}
          </div>
          <span className="mega-feature-tag">{feature.tag}</span>
          <strong>{feature.title}</strong>
          <p>{feature.text}</p>
          <span className="mega-feature-cta">{feature.cta}<Icon name="arrow" size={15} /></span>
        </Link>
      </div>
      <div className="mega-panel-footer"><Link to={menu.id === "personal" ? "/workspace" : `/${menu.id}`} onClick={close}>Khám phá tất cả <Icon name="arrow" size={14} /></Link></div>
    </div>
  );
}

export default function SiteHeader() {
  const location = useLocation();
  const [open, setOpen] = useState(null);
  const [mobileOpen, setMobileOpen] = useState(false);
  const header = useRef(null), leaveTimer = useRef(null), triggers = useRef({});
  function cancelClose() { clearTimeout(leaveTimer.current); }
  function close() { cancelClose(); setOpen(null); }
  function canHover(event) {
    return (event.pointerType === "mouse" || event.pointerType === "pen") &&
      window.matchMedia("(min-width: 781px) and (hover: hover)").matches;
  }
  function hover(id, event) {
    if (!canHover(event)) return;
    cancelClose(); setOpen(id);
  }
  useEffect(() => { setOpen(null); setMobileOpen(false); }, [location.key]);
  useEffect(() => {
    const dismiss = event => { if (!header.current?.contains(event.target)) { setOpen(null); setMobileOpen(false); } };
    document.addEventListener("pointerdown", dismiss);
    return () => { document.removeEventListener("pointerdown", dismiss); clearTimeout(leaveTimer.current); };
  }, []);
  function trigger(menu, personal = false) {
    const current = personal ? location.pathname.startsWith("/workspace") : menu.paths.some(path => location.pathname.startsWith(path));
    if (menu.id !== "personal") {
      return <div className="mega-nav-item" key={menu.id}>
        <Link className={`mega-trigger mega-direct-link${current ? " is-current" : ""}`}
          to={menu.id === "mine" ? "/workspace" : `/${menu.id}`} aria-current={current ? "page" : undefined}
          onPointerEnter={close} onFocus={close}>{menu.label}</Link>
      </div>;
    }
    return <div className={`mega-nav-item${personal ? " mega-personal" : ""}`} key={menu.id}>
      <button type="button" className={`mega-trigger${open === menu.id ? " is-open" : ""}${current ? " is-current" : ""}`}
        id={`nav-trigger-${menu.id}`} ref={node => { triggers.current[menu.id] = node; }}
        aria-expanded={open === menu.id} aria-controls={`nav-panel-${menu.id}`}
        onPointerEnter={event => hover(menu.id, event)}
        onClick={event => {
          cancelClose();
          // A mouse click must not immediately undo the preceding hover-open.
          if (event.detail > 0 && canHover({ pointerType: event.nativeEvent.pointerType || "mouse" })) setOpen(menu.id);
          else setOpen(value => value === menu.id ? null : menu.id);
        }}
        onKeyDown={event => {
          if (event.key === "ArrowDown") {
            event.preventDefault(); cancelClose(); setOpen(menu.id);
            requestAnimationFrame(() => document.getElementById(`nav-panel-${menu.id}`)?.querySelector("a")?.focus());
          }
        }}>
        {personal && <span className="mega-personal-icon"><Icon name="user" size={17} /></span>}
        {menu.label}<Chevron />
      </button>
      <MenuPanel menu={menu} open={open === menu.id} close={close} />
    </div>;
  }
  return <header className="site-header mega-header" ref={header}
    onPointerEnter={cancelClose}
    onPointerLeave={event => { if (!canHover(event)) return; cancelClose(); leaveTimer.current = setTimeout(() => { if (!header.current?.querySelector(":focus-visible")) setOpen(null); }, 180); }}
    onBlur={event => { if (!event.currentTarget.contains(event.relatedTarget)) close(); }}
    onKeyDown={event => { if (event.key === "Escape") { event.preventDefault(); if (open) { triggers.current[open]?.focus(); close(); } else setMobileOpen(false); } }}>
    <div className="site-header-inner">
      <Link className="mega-mobile-home" to="/" onPointerEnter={close}>Trang chủ</Link>
      <button type="button" className="mega-mobile-toggle" aria-label={mobileOpen ? "Đóng menu điều hướng" : "Mở menu điều hướng"} aria-expanded={mobileOpen} aria-controls="main-navigation" onClick={() => { setMobileOpen(value => !value); close(); }}><Icon name={mobileOpen ? "close" : "menu"} size={22} /></button>
      <nav id="main-navigation" className="mega-navigation" aria-label="Điều hướng chính" data-open={mobileOpen}>
        <div className="mega-nav-item mega-home-item"><Link className={`mega-trigger mega-direct-link${location.pathname === "/" ? " is-current" : ""}`} to="/" aria-current={location.pathname === "/" ? "page" : undefined} onPointerEnter={close} onFocus={close}>Trang chủ</Link></div>
        {menus.slice(0, 4).map(menu => trigger(menu))}
        {trigger(menus[4], true)}
      </nav>
    </div>
  </header>;
}
