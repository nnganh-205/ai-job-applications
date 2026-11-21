import { request } from "./api.js";

export async function extractCVToForm(file) {
  if (!/\.(pdf|docx)$/i.test(file.name) || file.size > 5 * 1024 * 1024) {
    throw new Error("Vui lòng chọn tệp PDF hoặc DOCX, tối đa 5 MB.");
  }
  const body = new FormData();
  body.append("file", file);
  const extraction = await request("/api/profiles/extract", { method: "POST", body });
  return request(`/api/profiles/${extraction.thread_id}/form-draft`, { method: "POST" });
}
