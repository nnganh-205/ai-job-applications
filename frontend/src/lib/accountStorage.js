let owner = 'guest';

export function setStorageOwner(userId) {
  owner = userId || 'guest';
}

export function getStorageOwner() { return owner; }

export const accountStorage = {
  getItem(key) {
    try { return localStorage.getItem(`kltn.account.${owner}.${key}`); }
    catch { return null; }
  },
  setItem(key, value) {
    try { localStorage.setItem(`kltn.account.${owner}.${key}`, value); }
    catch { /* Storage may be disabled by the browser. */ }
  },
  removeItem(key) {
    try { localStorage.removeItem(`kltn.account.${owner}.${key}`); }
    catch { /* Storage may be disabled by the browser. */ }
  },
};
