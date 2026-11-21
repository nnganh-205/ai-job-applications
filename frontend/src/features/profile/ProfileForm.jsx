import React, { useLayoutEffect, useRef } from "react";
import FieldPolish from "./FieldPolish.jsx";
import AIWriter from "./AIWriter.jsx";
import { resumeFieldHint } from "../resumes/resumeFieldHints.js";

const labels = {
  contact: "Thông tin cá nhân",
  headline: "Vị trí ứng tuyển",
  date_of_birth: "Ngày sinh",
  gender: "Giới tính",
  interests: "Sở thích",
  additional_info: "Thông tin thêm",
  certifications: "Chứng chỉ",
  awards: "Danh hiệu và giải thưởng",
  references: "Người giới thiệu",
  name: "Tên chứng chỉ",
  issuer: "Đơn vị cấp",
  date: "Thời gian",
  title: "Danh hiệu / giải thưởng",
  position: "Chức vụ",
  relationship: "Mối quan hệ",
  experience: "Kinh nghiệm",
  project: "Dự án",
  education: "Học vấn",
  involvement: "Hoạt động",
  skills: "Kỹ năng",
  summary: "Tóm tắt",
  full_name: "Họ và tên",
  email: "Email",
  phone: "Điện thoại",
  location: "Địa điểm",
  job_title: "Chức danh",
  role: "Vai trò",
  technologies: "Công nghệ sử dụng",
  company: "Công ty",
  employment_type: "Hình thức",
  start_date: "Ngày bắt đầu",
  end_date: "Ngày kết thúc",
  is_current: "Đang làm việc",
  description: "Mô tả",
  responsibilities: "Trách nhiệm",
  original_bullets: "Nội dung gốc",
  project_name: "Tên dự án",
  project_type: "Loại dự án",
  objectives: "Mục tiêu",
  github_url: "URL GitHub",
  demo_url: "URL demo",
  project_url: "URL dự án",
  institution: "Trường / cơ sở đào tạo",
  degree: "Bằng cấp",
  field_of_study: "Lĩnh vực học",
  major: "Chuyên ngành",
  graduation_date: "Ngày tốt nghiệp",
  gpa: "Điểm trung bình",
  gpa_scale: "Thang điểm",
  details: "Chi tiết",
  academic_achievements: "Thành tích học tập",
  relevant_coursework: "Môn học liên quan",
  original_description: "Mô tả gốc",
  organization: "Tổ chức",
  activity_name: "Tên hoạt động",
  activity_type: "Loại hoạt động",
  period: "Thời gian",
  group: "Nhóm kỹ năng",
  items: "Kỹ năng",
  normalized_items: "Tên kỹ năng chuẩn hóa",
  country: "Quốc gia",
  city: "Thành phố",
  state_or_province: "Tỉnh / bang",
  portfolio_url: "URL portfolio",
  website: "Website",
  linkedin: "LinkedIn",
  github: "GitHub",
};
export const sections = [
  "contact",
  "experience",
  "project",
  "education",
  "involvement",
  "skills",
  "certifications",
  "awards",
  "references",
  "summary",
];
export const label = (key) => labels[key] || key;
const visibleFields = {
  contact: [
    "full_name",
    "headline",
    "date_of_birth",
    "gender",
    "interests",
    "additional_info",
    "email",
    "phone",
    "location",
    "linkedin",
    "github",
    "website",
    "portfolio_url",
  ],
  education: [
    "institution",
    "degree",
    "major",
    "start_date",
    "end_date",
    "gpa",
    "details",
  ],
  experience: [
    "job_title",
    "company",
    "location",
    "start_date",
    "end_date",
    "is_current",
    "description",
  ],
  project: [
    "project_name",
    "role",
    "technologies",
    "github_url",
    "start_date",
    "end_date",
    "description",
    "project_url",
  ],
  skills: ["group", "items"],
  certifications: ["name", "issuer", "date", "description"],
  awards: ["title", "organization", "date", "description"],
  references: ["full_name", "position", "organization", "email", "phone", "relationship", "description"],
  involvement: [
    "activity_name",
    "organization",
    "role",
    "period",
    "description",
  ],
};
const resolve = (s, root) =>
  s.$ref
    ? root.$defs[s.$ref.split("/").at(-1)]
    : s.anyOf
      ? resolve(
          s.anyOf.find((x) => x.type !== "null"),
          root,
        )
      : s;

function GrowingTextarea(props) {
  const ref=useRef(null);
  useLayoutEffect(()=>{
    const element=ref.current;
    if (!element)return;
    const resize=()=>{element.style.height='auto';const style=getComputedStyle(element);element.style.height=(element.scrollHeight+parseFloat(style.borderTopWidth||0)+parseFloat(style.borderBottomWidth||0))+'px';};
    resize();
    const observer=new ResizeObserver(resize);
    observer.observe(element);
    return ()=>observer.disconnect();
  },[props.value]);
  return <textarea {...props} ref={ref} rows={2} wrap="soft" style={{overflow:'hidden',resize:'vertical',overflowWrap:'anywhere',whiteSpace:'pre-wrap'}} />;
}

export default function ProfileForm({
  profile,
  initialProfile,
  schema,
  section,
  onChange,
  disabled = false,
  compact = false,
  review = false,
  entryIndex = null,
  hideEntryActions = false,
  hideAdd = false,
  writerAction = null,
  allowedFields = null,
}) {
  function field(key, spec, value, change, entry = null) {
    const type = resolve(spec, schema).type;
    const [, placeholder] = compact ? resumeFieldHint(section, key) : ["", ""];
    const fieldLabel =
      review && key === "original_bullets"
        ? "Nội dung AI trích xuất bổ sung"
        : label(key);
    if (key === "id") return null;
    if (allowedFields && !allowedFields.includes(key)) return null;
    if (
      compact &&
      !visibleFields[section]?.includes(key) &&
      section !== "summary" &&
      !(
        review &&
        (Array.isArray(value)
          ? value.some(Boolean)
          : value != null && value !== "")
      )
    )
      return null;
    if (type === "boolean")
      return (
        <label key={key}>
          <input
            type="checkbox"
            checked={value === true}
            disabled={disabled}
            onChange={(e) => change(e.target.checked)}
          />
          {fieldLabel}
        </label>
      );
    if (type === "array")
      return (
        <div key={key} className="profile-writer-field">
          {fieldLabel}
          {!(entry && ["description", "responsibilities", "contributions", "details"].includes(key)
            && ["experience", "project", "involvement", "education"].includes(section)) && (
            <GrowingTextarea disabled={disabled} aria-label={fieldLabel} placeholder={placeholder}
              value={(value || []).join("\n")} onChange={(e) => change(e.target.value.split("\n"))} />
          )}
          {entry &&
            [
              "description",
              "responsibilities",
              "contributions",
              "details",
            ].includes(key) &&
            ["experience", "project", "involvement", "education"].includes(
              section,
            ) && (
              <AIWriter
                key={`${section}-${entry.id || entryIndex}-${key}`}
                field={key}
                initialValue={
                  initialProfile?.[section]?.find(
                    (item) => item.id && item.id === entry.id,
                  )?.[key] ||
                  (entry.id
                    ? []
                    : initialProfile?.[section]?.[entryIndex]?.[key]) ||
                  []
                }
                section={section}
                entry={entry}
                value={value || []}
                disabled={disabled}
                onApply={change}
                renderSource={(suggestions, hasPreview) => hasPreview ? (
                  <div className="writer-source-list">
                    {(value || []).map((line, index) => <div className="writer-source-line" key={index}>
                      <textarea aria-label={`${fieldLabel}, câu ${index + 1}`} rows={Math.min(5, Math.max(2, Math.ceil(line.length / 70)))}
                        value={line} disabled={disabled} onChange={(event) => {
                          const next = [...(value || [])]; next[index] = event.target.value;
                          change(next.flatMap((text) => text.split("\n")));
                        }} />
                      {suggestions(index)}
                    </div>)}
                  </div>
                ) : <textarea disabled={disabled} aria-label={fieldLabel} placeholder={placeholder}
                  value={(value || []).join("\n")} onChange={(event) => change(event.target.value.split("\n"))} />}
                action={writerAction}
              />
            )}
          {["outcomes", "achievements"].includes(key) && (
            <FieldPolish
              value={(value || []).join("\n")}
              field={key}
              disabled={disabled}
              onApply={(next) => change(next.split("\n"))}
            />
          )}
        </div>
      );
    const props = {
      disabled,
      "aria-label": fieldLabel,
      placeholder: placeholder || undefined,
      value: value ?? "",
      onChange: (e) => change(e.target.value || null),
    };
    return (
      <label key={key}>
        {fieldLabel}
        {section==='project' && ['project_name','github_url','project_url'].includes(key) ? (
          <GrowingTextarea {...props} />
        ) : ["summary", "original_description"].includes(key) ? (
          <textarea {...props} rows={5} />
        ) : (
          <input
            {...props}
            type={key === "email" ? "email" : "text"}
            placeholder={
              placeholder ||
              (key === "date_of_birth" ? "Ví dụ: 15/08/2004" : key.includes("date") ? "Ví dụ: 09/2024" : undefined)
            }
          />
        )}
        {["summary", "role"].includes(key) && (
          <FieldPolish
            value={value || ""}
            field={key}
            disabled={disabled}
            onApply={change}
          />
        )}
      </label>
    );
  }
  const spec = resolve(schema.properties[section], schema);
  if (section === "summary")
    return field(section, spec, profile.summary, (value) =>
      onChange({ ...profile, summary: value }),
    );
  if (section === "contact")
    return (
      <div className="form-grid">
        {(allowedFields ? allowedFields.filter((key) => spec.properties[key]).map((key) => [key, spec.properties[key]]) : Object.entries(spec.properties)).map(([key, s]) =>
          field(key, s, profile.contact[key], (value) =>
            onChange({
              ...profile,
              contact: { ...profile.contact, [key]: value },
            }),
          ),
        )}
      </div>
    );
  const entrySpec = resolve(spec.items, schema);
  return (
    <div>
      {compact && !(profile[section] || []).length && (
        <p className="cv-form-empty">
          Chưa có {label(section).toLowerCase()}. Thêm một mục bên dưới hoặc bỏ
          qua nếu không phù hợp.
        </p>
      )}
      {(profile[section] || []).map((entry, index) =>
        entryIndex !== null && entryIndex !== index ? null : (
          <fieldset key={entry.id || index} disabled={disabled}>
            <legend>
              {label(section)} {index + 1}
            </legend>
            <div className="form-grid">
              {(allowedFields ? allowedFields.filter((key) => entrySpec.properties[key]).map((key) => [key, entrySpec.properties[key]]) : Object.entries(entrySpec.properties)).map(([key, s]) =>
                field(
                  key,
                  s,
                  entry[key],
                  (value) =>
                    onChange({
                      ...profile,
                      [section]: (profile[section] || []).map((x, i) =>
                        i === index ? { ...x, [key]: value } : x,
                      ),
                    }),
                  entry,
                ),
              )}
            </div>
            {!hideEntryActions && (
              <button
                type="button"
                className="secondary-button"
                onClick={() =>
                  onChange({
                    ...profile,
                    [section]: (profile[section] || []).filter((_, i) => i !== index),
                  })
                }
              >
                Xóa mục
              </button>
            )}
          </fieldset>
        ),
      )}
      {!hideAdd && (
        <button
          type="button"
          disabled={disabled}
          onClick={() =>
            onChange({ ...profile, [section]: [...(profile[section] || []), {}] })
          }
        >
          Thêm {label(section).toLowerCase()}
        </button>
      )}
    </div>
  );
}
