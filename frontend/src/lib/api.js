export function csrfHeaders(headers = {}) {
  const result = new Headers(headers);
  const cookie = document.cookie.split('; ').find(value => value.startsWith('kltn_csrf='));
  if (cookie) result.set('X-KLTN-CSRF', decodeURIComponent(cookie.slice('kltn_csrf='.length)));
  return result;
}

export async function authenticatedFetch(path, options = {}) {
  const owner = getStorageOwner();
  const response = await fetch(path, {
    ...options,
    credentials: 'same-origin',
    headers: csrfHeaders(options.headers),
  });
  if (response.status === 401 && !path.startsWith('/api/auth/')) {
    window.dispatchEvent(new CustomEvent('kltn:unauthorized', { detail: { owner } }));
  }
  return response;
}

export async function request(path, options = {}) {
  const { timeoutMs = 600000, signal, ...fetchOptions } = options;
  const controller = new AbortController();
  let timedOut = false;
  const abort = () => controller.abort();
  if (signal?.aborted) abort();
  signal?.addEventListener('abort', abort, { once: true });
  const timer = setTimeout(() => { timedOut = true; controller.abort(); }, timeoutMs);
  try {
    const response = await authenticatedFetch(path, { ...fetchOptions, signal: controller.signal });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      const message = typeof data.detail === 'string' ? data.detail : `Yêu cầu thất bại (HTTP ${response.status})`;
      const error = new Error(message);
      error.status = response.status;
      throw error;
    }
    return data;
  } catch (error) {
    if (timedOut) throw new Error('Hết thời gian chờ máy chủ. Bạn có thể chọn lại công việc để kiểm tra kết quả đã lưu.');
    throw error;
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener('abort', abort);
  }
}
import { getStorageOwner } from './accountStorage.js';
