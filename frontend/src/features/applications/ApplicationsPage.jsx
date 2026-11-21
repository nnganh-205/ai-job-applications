import React, { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import { request } from "../../lib/api.js";
import Icon from "../../components/ui/Icon.jsx";
import PageHeading from "../../components/ui/PageHeading.jsx";
import {EmptyState} from "../../components/ui/PageState.jsx";
import { statusNames } from "./ApplicationPanel.jsx";
export default function ApplicationsPage() {
  const [filter,setFilter] = useState("all"),
    [items, setItems] = useState(null),
    [error, setError] = useState("");
  useEffect(() => {
    const c = new AbortController();
    request("/api/applications", { signal: c.signal })
      .then(setItems)
      .catch((e) => {
        if (e.name !== "AbortError") setError(e.message);
      });
    return () => c.abort();
  }, []);
  return (
    <main className="applications-page">
      <PageHeading eyebrow="THEO DÕI HÀNH TRÌNH" title="Theo dõi ứng tuyển" action={<Link className="button-link" to="/jobs"><Icon name="search" size={16}/> Khám phá việc làm</Link>}>Giữ những công việc bạn quan tâm và theo dõi từng bước ứng tuyển. Trạng thái do bạn xác nhận.</PageHeading>
      <div className="application-filters" role="group" aria-label="Lọc trạng thái"><button aria-pressed={filter==='all'} onClick={()=>setFilter('all')}>Tất cả <span>{items?.length||0}</span></button>{Object.entries(statusNames).filter(([key])=>items?.some(a=>a.status===key)).map(([key,name])=><button key={key} aria-pressed={filter===key} onClick={()=>setFilter(key)}>{name} <span>{items.filter(a=>a.status===key).length}</span></button>)}</div>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {!items && !error && <p role="status">Đang tải…</p>}
      {items?.length === 0 && (
        <EmptyState icon="briefcase" title="Cơ hội mới đang chờ bạn" action={<Link className="button-link secondary-button" to="/jobs">Tìm công việc đầu tiên <Icon name="arrow" size={15}/></Link>}>Khi chuẩn bị ứng tuyển một công việc, bạn có thể lưu CV đã chọn, ghi chú và cập nhật trạng thái tại đây.</EmptyState>
      )}
      {items?.filter(a=>filter==='all'||a.status===filter).map((a) => (
        <article className="workspace-row" key={a.application_id}>
          <div>
            <span className={"status-pill "+a.status}>{statusNames[a.status]}</span><h2>{a.title}</h2>
            <p>
              {a.company || "Chưa công bố công ty"} · {statusNames[a.status]} ·{" "}
              {new Date(a.updated_at).toLocaleDateString("vi-VN")}
            </p>
          </div>
          <Link
            to={"/jobs/" + a.posting_id + (a.cv_id ? "?cv=" + a.cv_id : "")}
          >
            Mở công việc →
          </Link>
        </article>
      ))}
    </main>
  );
}
