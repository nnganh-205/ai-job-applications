import React, { useEffect, useRef, useState } from 'react';
import { Link, Navigate, useNavigate, useSearchParams } from 'react-router-dom';
import Icon from '../../components/ui/Icon.jsx';
import { useAuth } from './AuthContext.jsx';

export function safeDestination(value) {
  if (!value?.startsWith('/') || value.startsWith('//') || value.includes('\\') || /[\u0000-\u0020\u007f]/.test(value) || /^\/(login|register)(\/|\?|$)/.test(value)) return '/workspace';
  return value;
}

function Eye({ visible }) {
  return <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true">
    <path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z" /><circle cx="12" cy="12" r="3" />
    {!visible && <path d="m3 3 18 18" />}
  </svg>;
}

export default function AuthPage({ mode }) {
  const { user, ready, authenticate } = useAuth();
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const registering = mode === 'register';
  const destination = safeDestination(params.get('next') || (user?.role === 'admin' ? '/admin' : '/workspace'));
  const next = params.get('next') ? `?next=${encodeURIComponent(destination)}` : '';
  const [values, setValues] = useState({ full_name: '', email: '', password: '', confirmation: '' });
  const [showPassword, setShowPassword] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const pending = useRef(null);
  useEffect(() => {
    setError(''); setBusy(false); setShowPassword(false);
    setValues(current => ({ ...current, password: '', confirmation: '' }));
    return () => pending.current?.abort();
  }, [mode]);
  useEffect(() => { document.title = `${registering ? 'Đăng ký' : 'Đăng nhập'} · Career Workspace`; }, [registering]);
  if (ready && user) return <Navigate replace to={destination} />;
  function change(event) { setValues({ ...values, [event.target.name]: event.target.value }); setError(''); }
  async function submit(event) {
    event.preventDefault();
    if (busy) return;
    if (registering && values.password !== values.confirmation) { setError('Mật khẩu xác nhận chưa khớp.'); return; }
    setBusy(true); setError('');
    pending.current = new AbortController();
    try {
      const account = await authenticate(mode, {
        ...(registering ? { full_name: values.full_name.trim() } : {}),
        email: values.email.trim(), password: values.password,
      }, pending.current.signal);
      navigate(params.get('next') ? destination : account.role === 'admin' ? '/admin' : '/workspace', { replace: true });
    } catch (failure) {
      if (failure.name !== 'AbortError') setError(failure.message);
    } finally { setBusy(false); }
  }
  return <main className="auth-page">
    <div className="auth-orbit auth-orbit-one" aria-hidden="true" /><div className="auth-orbit auth-orbit-two" aria-hidden="true" />
    <div className="auth-page-heading"><Link to="/" className="auth-back"><span aria-hidden="true">←</span> Về trang chủ</Link></div>
    <section className={`auth-card${registering ? '' : ' is-login'}`} aria-label={registering ? 'Đăng ký tài khoản' : 'Đăng nhập tài khoản'}>
      <aside className="auth-story">
        <h1>Xây dựng hồ sơ cá nhân</h1>
        <div className="auth-story-visual" aria-hidden="true"><div className="auth-mini-cv"><span className="auth-mini-avatar"><Icon name="user" size={20} /></span><div className="auth-mini-lines"><i /><i /><i /></div><div className="auth-mini-divider" /><i /><i /><i /><span className="auth-mini-stamp"><Icon name="check" size={18} /></span></div></div>
        <div className="auth-story-switch"><p>{registering ? 'Bạn đã có tài khoản?' : 'Lần đầu bạn ghé thăm?'}</p><Link to={`${registering ? '/login' : '/register'}${next}`} tabIndex={busy ? -1 : undefined}>{registering ? 'Đăng nhập' : 'Tạo tài khoản'} <Icon name="arrow" size={16} /></Link></div>
      </aside>
      <div className="auth-form-wrap">
        <div className="auth-form-content" key={mode}>
          <h2>{registering ? 'Tạo tài khoản' : 'Đăng nhập'}</h2>
          <form onSubmit={submit} className="auth-form" aria-busy={busy}>
            {registering && <label htmlFor="auth-name">Họ và tên<div className="auth-input"><Icon name="user" size={18} /><input id="auth-name" name="full_name" autoComplete="name" placeholder="Tên của bạn" value={values.full_name} onChange={change} required minLength={2} maxLength={100} disabled={busy} /></div></label>}
            <label htmlFor="auth-email">Email<div className="auth-input"><span className="auth-at" aria-hidden="true">@</span><input id="auth-email" name="email" type="email" autoComplete="username" autoCapitalize="none" spellCheck={false} placeholder="ban@email.com" value={values.email} onChange={change} required maxLength={254} disabled={busy} /></div></label>
            <label htmlFor="auth-password">Mật khẩu<div className="auth-input"><Icon name="shield" size={18} /><input id="auth-password" name="password" type={showPassword ? 'text' : 'password'} autoComplete={registering ? 'new-password' : 'current-password'} placeholder={registering ? 'Ít nhất 8 ký tự' : 'Nhập mật khẩu của bạn'} value={values.password} onChange={change} required minLength={registering ? 8 : 1} maxLength={128} disabled={busy} /><button type="button" className="auth-password-toggle" aria-label={showPassword ? 'Ẩn mật khẩu' : 'Hiện mật khẩu'} aria-pressed={showPassword} onClick={() => setShowPassword(value => !value)}><Eye visible={showPassword} /></button></div></label>
            {registering && <label htmlFor="auth-confirm">Xác nhận mật khẩu<div className="auth-input"><Icon name="shield" size={18} /><input id="auth-confirm" name="confirmation" type={showPassword ? 'text' : 'password'} autoComplete="new-password" placeholder="Nhập lại mật khẩu" value={values.confirmation} onChange={change} required minLength={8} maxLength={128} disabled={busy} /></div></label>}
            {error && <p className="auth-error" role="alert">{error}</p>}
            <button className="auth-submit" type="submit" disabled={busy}>{busy ? 'Đang xử lý…' : registering ? 'Tạo tài khoản' : 'Đăng nhập'}{!busy && <Icon name="arrow" size={18} />}</button>
          </form>
          <p className="auth-form-switch">{registering ? 'Đã có tài khoản?' : 'Chưa có tài khoản?'} <Link to={`${registering ? '/login' : '/register'}${next}`}>{registering ? 'Đăng nhập' : 'Đăng ký ngay'}</Link></p>
        </div>
      </div>
    </section>
  </main>;
}
