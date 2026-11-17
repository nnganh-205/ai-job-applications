import { request } from "./api.js";

export function createTask(path, payload, key, signal) {
  return request("/api/tasks" + path, {
    method: "POST",
    headers: { "Content-Type": "application/json", "Idempotency-Key": key },
    body: JSON.stringify(payload),
    signal,
    timeoutMs: 15000,
  });
}
export function getTask(id, signal) {
  return request("/api/tasks/" + id, { signal, timeoutMs: 15000 });
}
export async function waitTask(id, { signal, onProgress } = {}) {
  while (true) {
    const task = await getTask(id, signal);
    if (signal?.aborted) throw new DOMException("Aborted", "AbortError");
    onProgress?.(task);
    if (task.status === "completed") return task.result;
    if (task.status === "failed") {
      const error = new Error(task.error || "Tác vụ thất bại.");
      error.task = task;
      throw error;
    }
    await new Promise((resolve, reject) => {
      const abort = () => {
        clearTimeout(timer);
        reject(new DOMException("Aborted", "AbortError"));
      };
      const timer = setTimeout(() => {
        signal?.removeEventListener("abort", abort);
        resolve();
      }, 1500);
      if (signal?.aborted) abort();
      else signal?.addEventListener("abort", abort, { once: true });
    });
  }
}
export async function retryTask(id, signal) {
  return request("/api/tasks/" + id + "/retry", {
    method: "POST",
    signal,
    timeoutMs: 15000,
  });
}
export function taskLabel(task) {
  return task?.status === "queued"
    ? "Đang chờ AI xử lý"
    : task?.status === "running"
      ? (task.progress?.message || "AI đang xử lý nội dung") + (task.progress?.total ? ` (${task.progress.completed}/${task.progress.total})` : "")
      : task?.status === "failed"
        ? "Tác vụ thất bại"
        : task?.status === "completed"
          ? "Đã có kết quả"
          : "";
}
