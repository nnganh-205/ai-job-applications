import { test, expect } from 'bun:test';
import { safeDestination } from './AuthPage.jsx';
import { accountStorage, setStorageOwner } from '../../lib/accountStorage.js';

test('after-login destinations cannot escape the app or loop through authentication', () => {
  for (const value of ['https://example.com', '//example.com', '/\\example.com', '/\n/example.com', '/login', '/register?next=/jobs', null]) {
    expect(safeDestination(value)).toBe('/workspace');
  }
  expect(safeDestination('/workspace/resumes/new?template=classic')).toBe('/workspace/resumes/new?template=classic');
  expect(safeDestination('/jobs?q=python')).toBe('/jobs?q=python');
});

test('switching accounts cannot reuse another candidate profile or pending task', () => {
  const previous = globalThis.localStorage;
  const items = new Map([['kltn.confirmedProfileId', 'legacy-profile']]);
  globalThis.localStorage = {
    getItem: key => items.get(key) ?? null,
    setItem: (key, value) => items.set(key, value),
    removeItem: key => items.delete(key),
  };
  try {
    setStorageOwner('first');
    accountStorage.setItem('kltn.confirmedProfileId', 'profile-first');
    accountStorage.setItem('cv.task', 'task-first');
    setStorageOwner('second');
    expect(accountStorage.getItem('kltn.confirmedProfileId')).toBeNull();
    expect(accountStorage.getItem('cv.task')).toBeNull();
    accountStorage.setItem('kltn.confirmedProfileId', 'profile-second');
    setStorageOwner('first');
    expect(accountStorage.getItem('kltn.confirmedProfileId')).toBe('profile-first');
    setStorageOwner(null);
    expect(accountStorage.getItem('kltn.confirmedProfileId')).toBeNull();
    expect(items.get('kltn.confirmedProfileId')).toBe('legacy-profile');
  } finally {
    globalThis.localStorage = previous;
    setStorageOwner(null);
  }
});
