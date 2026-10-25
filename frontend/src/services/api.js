export async function request(path, options = {}) {
  const { timeoutMs = 600000, signal, ...fetchOptions } = options;
  const controller = new AbortController();
  let timedOut = false;
  const abort = () => controller.abort();
  if (signal?.aborted) abort();
  signal?.addEventListener('abort', abort, { once: true });
  const timer = setTimeout(() => { timedOut = true; controller.abort(); }, timeoutMs);
  try {
    const response = await fetch(path, { ...fetchOptions, signal: controller.signal });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      const message = typeof data.detail === 'string' ? data.detail : `Yêu cầu thất bại (HTTP ${response.status})`;
      throw new Error(message);
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
