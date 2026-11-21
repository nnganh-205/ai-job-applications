import React, { createContext, useCallback, useContext, useEffect, useState } from 'react';
import { request } from '../../lib/api.js';
import { accountStorage, getStorageOwner, setStorageOwner } from '../../lib/accountStorage.js';

const AuthContext = createContext(null);
export const useAuth = () => useContext(AuthContext);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState('');
  const [requiresLogin, setRequiresLogin] = useState(false);
  const apply = useCallback(data => {
    setStorageOwner(data.user?.user_id);
    if (data.user?.profile_id && !accountStorage.getItem('kltn.confirmedProfileId')) {
      accountStorage.setItem('kltn.confirmedProfileId', data.user.profile_id);
    }
    setUser(data.user);
    setRequiresLogin(false);
    setError('');
    setReady(true);
  }, []);
  const refresh = useCallback(async signal => {
    try { apply(await request('/api/auth/me', { signal, timeoutMs: 15000 })); }
    catch (failure) {
      if (failure.name !== 'AbortError') { setError('Chưa kết nối được máy chủ. Vui lòng thử lại.'); setReady(true); }
    }
  }, [apply]);
  useEffect(() => {
    const controller = new AbortController();
    refresh(controller.signal);
    const expired = event => {
      if (event.detail?.owner && event.detail.owner !== getStorageOwner()) return;
      setStorageOwner(null); setUser(null); setRequiresLogin(true);
    };
    const changed = event => { if (event.key === 'kltn.auth.changed') { setReady(false); refresh(); } };
    window.addEventListener('kltn:unauthorized', expired);
    window.addEventListener('storage', changed);
    return () => {
      controller.abort();
      window.removeEventListener('kltn:unauthorized', expired);
      window.removeEventListener('storage', changed);
    };
  }, [refresh]);
  function notify() {
    try { localStorage.setItem('kltn.auth.changed', crypto.randomUUID()); } catch {}
  }
  async function authenticate(mode, payload, signal) {
    const data = await request(`/api/auth/${mode}`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload), signal, timeoutMs: 30000,
    });
    apply(data);
    notify();
    return data.user;
  }
  async function logout() {
    await request('/api/auth/logout', { method: 'POST', timeoutMs: 15000 });
    apply({ user: null });
    notify();
  }
  return <AuthContext.Provider value={{ user, ready, error, requiresLogin, authenticate, logout, refresh }}>{children}</AuthContext.Provider>;
}
