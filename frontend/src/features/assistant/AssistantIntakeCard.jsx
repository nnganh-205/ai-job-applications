import React from "react";
import { Link } from "react-router-dom";
import Icon from "../../components/ui/Icon.jsx";
const groups = [
  ["education", "Học vấn"],
  ["experience", "Kinh nghiệm"],
  ["project", "Dự án"],
  ["skills", "Nhóm kỹ năng"],
  ["involvement", "Hoạt động"],
];
export default function AssistantIntakeCard({ result }) {
  const { profile, target_role, missing, revision } = result.intake;
  if (missing.length && result.intake.step_title) {
    return (
      <div className="assistant-intake-step" aria-label="Tiến độ tạo CV">
        <Icon name="file" size={15} />
        <span>
          Phần {result.intake.step_number}/{result.intake.total_steps} ·{" "}
          {result.intake.step_title}
        </span>
      </div>
    );
  }
  return (
    <section
      className="assistant-intake-card"
      aria-label="Thông tin CV đang thu thập"
    >
      <header>
        <span>
          <Icon name="file" size={18} />
          Bản nháp CV của bạn
        </span>
        <small>Lượt cập nhật {revision}</small>
      </header>
      {result.intake.step_title && (
        <p className="assistant-intake-progress">
          {missing.length
            ? `Phần ${result.intake.step_number}/${result.intake.total_steps} · ${result.intake.step_title}`
            : "Đã hoàn tất các phần"}
        </p>
      )}
      <h3>{profile.contact.full_name || "Chưa có tên trên CV"}</h3>
      {target_role && <p className="assistant-intake-role">{target_role}</p>}
      <p className="assistant-intake-contact">
        {[
          profile.contact.email,
          profile.contact.phone,
          profile.contact.location,
        ]
          .filter(Boolean)
          .join(" · ") || "Chưa thêm thông tin liên hệ"}
      </p>
      <div className="assistant-intake-groups">
        {groups.map(([key, label]) => (
          <span key={key}>
            {label}
            <b>{profile[key].length}</b>
          </span>
        ))}
      </div>
      <small className="assistant-intake-note">
        Bạn có thể nhắn “đổi…”, “thêm…” hoặc “bỏ…” để điều chỉnh thông tin. Bản
        nháp chưa được xác nhận.
      </small>
      {!missing.length && result.href && (
        <Link className="button-link" to={result.href}>
          Kiểm tra thông tin & tạo CV
          <Icon name="arrow" size={16} />
        </Link>
      )}
      <Link className="assistant-intake-form-link" to="/workspace/resumes/new">
        Hoặc mở form nhập mới
      </Link>
    </section>
  );
}
