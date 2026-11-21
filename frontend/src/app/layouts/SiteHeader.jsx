import React, { useEffect, useRef, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import Icon from "../../components/ui/Icon.jsx";
import { useAuth } from "../../features/auth/AuthContext.jsx";

const menus = [
  { id: "jobs", label: "Việc làm", paths: ["/jobs"] },
  { id: "templates", label: "Mẫu CV", paths: ["/templates"] },
  { id: "mine", label: "Trang của tôi", paths: ["/workspace"] },
  { id: "personal", label: "Cá nhân", paths: [] },
];

export default function SiteHeader() {
  const location = useLocation();
  const { user, logout } = useAuth();
  const [accountOpen, setAccountOpen] = useState(false);
  const [signingOut, setSigningOut] = useState(false);
  const [accountError, setAccountError] = useState('');
  const [mobileOpen, setMobileOpen] = useState(false);
  const header = useRef(null);
  function close() { setMobileOpen(false); setAccountOpen(false); }
  async function signOut() {
    setSigningOut(true); setAccountError('');
    try { await logout(); window.location.replace('/'); }
    catch (error) { setAccountError(error.message); }
    finally { setSigningOut(false); }
  }
  useEffect(() => { close(); }, [location.key]);
  useEffect(() => {
    const dismiss = event => { if (!header.current?.contains(event.target)) close(); };
    document.addEventListener("pointerdown", dismiss);
    return () => document.removeEventListener("pointerdown", dismiss);
  }, []);
  function trigger(menu, personal = false) {
    const current = personal ? location.pathname.startsWith("/workspace") : menu.paths.some(path => location.pathname.startsWith(path));
    if (menu.id !== "personal") {
      return <div className="mega-nav-item" key={menu.id}>
        <Link className={`mega-trigger mega-direct-link${current ? " is-current" : ""}`}
          to={menu.id === "mine" ? "/workspace" : `/${menu.id}`} aria-current={current ? "page" : undefined}
          onClick={close}>{menu.label}</Link>
      </div>;
    }
    return <div className="mega-nav-item mega-personal" key={menu.id}>
      {user ? <>
        <button type="button" className={`mega-trigger${accountOpen ? ' is-open' : ''}`} onClick={() => setAccountOpen(value => !value)} aria-expanded={accountOpen} aria-controls="account-menu" aria-label="Mở menu tài khoản">
          <span className="account-avatar">{user.full_name.trim().slice(0, 1).toLocaleUpperCase('vi')}</span>
          <span className="account-short-name">{user.full_name.split(' ').slice(-2).join(' ')}</span>
        </button>
        {accountOpen && <div id="account-menu" className="account-menu">
          <div className="account-identity"><strong>{user.full_name}</strong><span>{user.email}</span></div>
          {user.role === 'admin' && <Link to="/admin" onClick={close}><Icon name="shield" size={16} />Trang quản trị</Link>}
          <Link to="/workspace" onClick={close}><Icon name="user" size={16} />Không gian của tôi</Link>
          <Link to="/workspace/resumes/new" onClick={close}><Icon name="file" size={16} />Hoàn thiện hồ sơ</Link>
          <button type="button" onClick={signOut} disabled={signingOut}><Icon name="arrow" size={16} />{signingOut ? 'Đang đăng xuất…' : 'Đăng xuất'}</button>
          {accountError && <p role="alert">{accountError}</p>}
        </div>}
      </> : <Link to="/register" className="mega-trigger" onClick={close} aria-current={location.pathname === '/register' ? 'page' : undefined}>
        <span className="mega-personal-icon"><Icon name="user" size={17} /></span>Đăng ký
      </Link>}
    </div>;
  }
  return <header className="site-header mega-header" ref={header}
    onKeyDown={event => { if (event.key === "Escape") close(); }}>
    <div className="site-header-inner">
      <Link className="mega-mobile-home" to="/">Trang chủ</Link>
      <button type="button" className="mega-mobile-toggle" aria-label={mobileOpen ? "Đóng menu điều hướng" : "Mở menu điều hướng"} aria-expanded={mobileOpen} aria-controls="main-navigation" onClick={() => setMobileOpen(value => !value)}><Icon name={mobileOpen ? "close" : "menu"} size={22} /></button>
      <nav id="main-navigation" className="mega-navigation" aria-label="Điều hướng chính" data-open={mobileOpen}>
        <div className="mega-nav-item mega-home-item"><Link className={`mega-trigger mega-direct-link${location.pathname === "/" ? " is-current" : ""}`} to="/" aria-current={location.pathname === "/" ? "page" : undefined} onClick={close}>Trang chủ</Link></div>
        {menus.filter(menu => menu.id !== 'personal').map(menu => trigger(menu))}
        {trigger(menus.find(menu => menu.id === 'personal'), true)}
      </nav>
    </div>
  </header>;
}
