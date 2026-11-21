import { request } from './api.js';

export function jobRequest(path, body, method = 'POST', signal) {
  return request(`/api/dashboard${path}`, {
    method, signal, timeoutMs: 360000,
    headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  });
}

export function getDashboard(filters, signal) {
  const query = new URLSearchParams(Object.entries(filters).filter(([, value]) => value !== '' && value !== false));
  return request(`/api/dashboard?${query}`, { signal, timeoutMs: 15000 });
}
