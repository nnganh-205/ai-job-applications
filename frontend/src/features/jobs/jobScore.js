const groups = [
  ["Ngôn ngữ & Framework", /\b(python|java|javascript|typescript|c\+\+|c#|go|golang|rust|php|kotlin|swift|react|angular|vue|next\.?js|node\.?js|django|flask|fastapi|spring|laravel|tensorflow|pytorch|langchain|langgraph)\b/i],
  ["Cơ sở dữ liệu", /\b(sql|postgres|mysql|mongodb|redis|oracle|database|dbms|co so du lieu|data warehouse|elasticsearch)\b/i],
  ["API & bảo mật", /\b(api|rest|graphql|grpc|oauth|jwt|authentication|authorization|bao mat|security|xac thuc|phan quyen)\b/i],
  ["Kiến trúc & thiết kế", /\b(oop|solid|architecture|kien truc|design pattern|thiet ke phan mem|microservice|clean code|domain.driven)\b/i],
  ["Tư duy hệ thống & vận hành", /\b(cloud|aws|azure|gcp|devops|docker|kubernetes|ci\/cd|monitoring|van hanh|xu ly su co|troubleshoot|scalab|hieu nang|distributed system)\b/i],
];

export function jobScore(evaluation) {
  const match = evaluation?.matching;
  if (match?.score == null) return null;
  const requirements = evaluation?.analysis?.job_requirements || {};
  const requirementTypes = new Map();
  for (const field of ["required_skills", "preferred_skills", "technical_requirements", "certifications", "languages", "experience_requirements", "education_requirements"]) {
    for (const item of requirements[field] || []) requirementTypes.set(item.id, item.requirement_type);
  }
  const buckets = { mandatory: [], preferred: [], context: [] };
  const categories = new Map();
  for (const item of match.assessments || []) {
    if (!item.counted_in_score) continue;
    const type = requirementTypes.get(item.requirement_id)
      || (item.dimension === "preferred_skills" ? "preferred" : "required");
    if (type === "unspecified") continue;
    const bucket = ["experience_requirements", "education_requirements"].includes(item.source_field)
      ? "context" : type === "preferred" ? "preferred" : "mandatory";
    buckets[bucket].push(item);
    if (bucket === "context") continue;
    const plainLabel = item.label.normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/đ/g, "d").replace(/Đ/g, "D");
    const category = groups.find(([, pattern]) => pattern.test(plainLabel))?.[0] || "Kỹ thuật chuyên môn khác";
    if (!categories.has(category)) categories.set(category, []);
    categories.get(category).push(item);
  }
  const weights = { mandatory: 70, preferred: 25, context: 5 };
  const active = Object.keys(buckets).filter((key) => buckets[key].length);
  const totalWeight = active.reduce((sum, key) => sum + weights[key], 0);
  if (!totalWeight) return null;
  const weighted = active.reduce((sum, key) =>
    sum + weights[key] * buckets[key].reduce((n, item) => n + item.contribution, 0) / buckets[key].length, 0) / totalWeight;
  const score = match.core_coverage == null ? weighted * 100
    : Math.min(weighted * 100, 50 + 50 * match.core_coverage);
  const met = [...buckets.mandatory, ...buckets.preferred].filter((item) => item.status === "met" || item.status === "partially_met");
  const gaps = [...buckets.mandatory, ...buckets.preferred].filter((item) => item.status === "not_met" || item.status === "unknown");
  const names = (items) => items.slice(0, 2).map((item) => item.label).join(", ");
  const summary = [met.length && `Bạn có bằng chứng phù hợp về ${names(met)}.`, gaps.length && `Nên bổ sung thông tin về ${names(gaps)}.`].filter(Boolean).join(" ")
    || "Chưa đủ bằng chứng chuyên môn để kết luận rõ hơn.";
  return { score: Math.round(score), buckets, categories: [...categories], summary };
}
