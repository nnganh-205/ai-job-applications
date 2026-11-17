import React from "react";
const titles = {
  experience: "Kinh nghiệm",
  project: "Dự án",
  education: "Học vấn",
  involvement: "Hoạt động",
  skills: "Kỹ năng",
};
export default function ProfileLivePreview({ profile }) {
  return (
    <div className="builder-paper" aria-label="Bản xem trước thông tin CV">
      <h1>{profile.contact.full_name || "Họ và tên của bạn"}</h1>
      <p className="builder-paper-contact">
        {[
          profile.contact.email,
          profile.contact.phone,
          profile.contact.location,
        ]
          .filter(Boolean)
          .join(" · ")}
      </p>
      {profile.summary && (
        <section>
          <h2>Giới thiệu</h2>
          <p>{profile.summary}</p>
        </section>
      )}
      {Object.entries(titles).map(
        ([section, title]) =>
          profile[section]?.length > 0 && (
            <section key={section}>
              <h2>{title}</h2>
              {profile[section].map((e, i) => (
                <article key={e.id || i}>
                  <div>
                    <strong>
                      {e.project_name ||
                        e.job_title ||
                        e.institution ||
                        e.activity_name ||
                        e.group}
                    </strong>
                    <small>
                      {[e.start_date, e.end_date].filter(Boolean).join(" – ")}
                    </small>
                  </div>
                  {(e.company || e.role || e.major) && (
                    <p>
                      {[e.company, e.role, e.major].filter(Boolean).join(" · ")}
                    </p>
                  )}
                  <ul>
                    {[
                      ...(e.description || []),
                      ...(e.contributions || []),
                      ...(e.outcomes || []),
                      ...(e.details || []),
                      ...(e.items || []),
                    ]
                      .filter(Boolean)
                      .map((t, j) => (
                        <li key={j}>{t}</li>
                      ))}
                  </ul>
                </article>
              ))}
            </section>
          ),
      )}
    </div>
  );
}
