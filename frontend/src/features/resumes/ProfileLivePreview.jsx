import React from "react";
const titles = {
  education: "Học vấn",
  experience: "Kinh nghiệm",
  project: "Dự án",
  involvement: "Hoạt động",
  skills: "Kỹ năng",
  certifications: "Chứng chỉ",
  awards: "Danh hiệu và giải thưởng",
  references: "Người giới thiệu",
};
const projectLink=(value)=>{
  try {
    const url=new URL(/^github\.com\//i.test(value || '')?'https://'+value:value);
    return ['https:','http:'].includes(url.protocol) && !url.username && !url.password?url.href:null;
  } catch {return null;}
};
export default function ProfileLivePreview({ profile }) {
  return (
    <div className="builder-paper" aria-label="Bản xem trước thông tin CV">
      <h1>{profile.contact.full_name || "Họ và tên của bạn"}</h1>
      {profile.contact.headline && <p>{profile.contact.headline}</p>}
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
              {profile[section].map((e, i) => section === "skills" ? (
                <p className="builder-skills-inline" key={e.id || i}><strong>{e.group}:</strong> {(e.items || []).filter(Boolean).join(", ")}</p>
              ) : (
                <article key={e.id || i}>
                  <div>
                    <strong style={{minWidth:0,overflowWrap:'anywhere',whiteSpace:'normal'}}>
                      {e.project_name || e.job_title || e.institution || e.activity_name || e.group || e.name || e.title || e.full_name}
                      {section==='project' && e.technologies?.filter(Boolean).length>0 && <span style={{fontWeight:400,fontStyle:'italic'}}> | {e.technologies.filter(Boolean).join(', ')}</span>}
                      {section==='project' && e.github_url && <span style={{fontWeight:400}}> | {projectLink(e.github_url)?<a href={projectLink(e.github_url)} target="_blank" rel="noopener noreferrer">GitHub</a>:e.github_url}</span>}
                    </strong>
                    <small>
                      {[e.start_date, e.end_date].filter(Boolean).join(" – ")}
                    </small>
                  </div>
                  {(e.company || (section === "involvement" && e.role) || e.major) && (
                    <p>
                      {[
                        e.company,
                        section === "involvement" ? e.role : null,
                        e.major,
                      ]
                        .filter(Boolean)
                        .join(" · ")}
                    </p>
                  )}
                  <ul>
                    {[
                      ...(e.description || []),
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
