import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {EmptyState} from "../../components/ui/PageState.jsx";
import { request } from "../../lib/api.js";
export default function EventsPage() {
  const [items, setItems] = useState(null),
    [error, setError] = useState("");
  useEffect(() => {
    const c = new AbortController();
    request("/api/events", { signal: c.signal })
      .then(setItems)
      .catch((e) => {
        if (e.name !== "AbortError") setError(e.message);
      });
    return () => c.abort();
  }, []);
  return (
    <main className="events-page">
      <p className="eyebrow">Kết nối và phát triển</p>
      <h1>Sự kiện nghề nghiệp</h1>
      <p>Các sự kiện có nguồn rõ ràng để bạn tìm hiểu và tự đăng ký.</p>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {!items && !error && <p role="status">Đang tải sự kiện…</p>}
      {items?.length === 0 && (
        <EmptyState icon="briefcase" title="Chưa có sự kiện trong kho" action={<Link className="button-link" to="/jobs">Khám phá việc làm →</Link>}>Khi có sự kiện có nguồn rõ ràng, thông tin và đường dẫn đăng ký sẽ xuất hiện tại đây.</EmptyState>
      )}
      {items?.map((e) => (
        <article key={e.id}>
          <h2>{e.title}</h2>
          <p>{e.description}</p>
          <p>
            {new Date(e.starts_at).toLocaleString("vi-VN")} ·{" "}
            {e.location || e.format}
          </p>
          <div className="form-actions">
            <a href={e.source_url} target="_blank" rel="noreferrer">
              Xem nguồn ↗
            </a>
            {e.registration_url && (
              <a href={e.registration_url} target="_blank" rel="noreferrer">
                Mở trang đăng ký ↗
              </a>
            )}
          </div>
        </article>
      ))}
    </main>
  );
}
