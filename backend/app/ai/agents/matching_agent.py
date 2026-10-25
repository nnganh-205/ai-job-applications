"""Deterministic evidence-based matching. No LLM or embedding calls."""

import hashlib
import json
import re
import unicodedata
from datetime import date

from backend.app.ai.agents.jd_agent import assign_requirement_ids, build_requirement_groups, normalize_requirements
from backend.app.schemas.job import JobRequirements
from backend.app.schemas.matching import MatchResponse
from backend.app.schemas.profile import MasterProfile
from backend.app.schemas.workflow import RequirementAssessment


ALGORITHM_VERSION = "evidence-v5"
WEIGHTS = {"role": .20, "required_skills": .35, "preferred_skills": .05,
           "experience": .15, "practical_evidence": .10, "education": .10, "other": .05}
ALIASES = {
    "collaborating": "collaboration", "collaborate": "collaboration",
    "communicate": "communication", "communicating": "communication",
    "ml": "machine learning", "machine learning fundamentals": "machine learning",
    "machine learning basics": "machine learning", "ml fundamentals": "machine learning",
    "good ml foundation": "machine learning", "torch": "pytorch",
    "nlp (natural language processing)": "natural language processing", "nlp": "natural language processing",
    "llm (large language model)": "large language model", "llms": "large language model",
    "llm": "large language model", "large language models": "large language model",
    "reactjs": "react", "react.js": "react", "nodejs": "node.js", "postgres": "postgresql",
    "rest apis": "rest api", "restful api": "rest api", "cv (computer vision)": "computer vision",
}
DOMAIN_SKILLS = {
    "ai": {"machine learning", "deep learning", "natural language processing", "computer vision", "large language model"},
    "backend": {"backend", "api design", "rest api", "database design"},
    "data": {"data analysis", "statistics", "data engineering"},
}


def normalized(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", text)).strip().casefold()


def canonical(text: str) -> str:
    value = normalized(text)
    return ALIASES.get(value, value)


def contains_term(text: str, term: str) -> bool:
    target = canonical(term)
    forms = {target, normalized(term), *(key for key, value in ALIASES.items() if value == target)}
    return any(re.search(r"(?<![\w+#])" + re.escape(form) + r"(?![\w+#])", normalized(text)) for form in forms)


def content_hash(model) -> str:
    return hashlib.sha256(json.dumps(model.model_dump(mode="json"), sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def profile_facts(profile: MasterProfile) -> list[tuple[str, str, float]]:
    facts = []
    # Contact is deliberately excluded; an email/domain must never prove a skill.
    for section in ("skills", "experience", "project", "education", "involvement"):
        for index, entry in enumerate(getattr(profile, section)):
            for field, value in entry.model_dump().items():
                if field in {"id", "group", "normalized_items", "company", "institution", "organization", "project_name", "location", "start_date", "end_date", "graduation_date", "github_url", "demo_url", "project_url"}:
                    continue
                values = enumerate(value) if isinstance(value, list) else [(None, value)]
                for item_index, item in values:
                    if isinstance(item, str) and item.strip():
                        path = f"/{section}/{index}/{field}" + (f"/{item_index}" if item_index is not None else "")
                        depth = .65 if section == "skills" else (.35 if section == "education" else 1.0)
                        facts.append((path, item, depth))
    return facts


def assess_term(item, facts) -> RequirementAssessment:
    matches, denied = [], []
    for path, text, depth in facts:
        if not contains_term(text, item.name):
            continue
        negative = re.search(r"(?:no experience (?:with|in)|never used|never worked with|chưa từng sử dụng|chưa sử dụng|không biết|không có kinh nghiệm với)\s+([^.;\n]+)", text, re.I)
        if negative and contains_term(re.split(r"\bbut\b|nhưng", negative.group(1), flags=re.I)[0], item.name):
            denied.append(path)
        else:
            matches.append((path, depth))
    value = max((depth for _, depth in matches), default=0)
    if denied and not matches:
        return RequirementAssessment(requirement_id=item.id, status="not_met", evidence_refs=denied, contribution=0,
                                     explanation=f"{item.name}: hồ sơ ghi rõ chưa có kinh nghiệm/kỹ năng này")
    return RequirementAssessment(
        requirement_id=item.id, status="met" if value == 1 else "partially_met" if value else "unknown",
        evidence_refs=[path for path, _ in matches], contribution=value,
        explanation=(f"{item.name}: có bằng chứng thực hành" if value == 1 else
                     f"{item.name}: có khai báo/khoá học, chưa có bằng chứng thực hành" if value else
                     f"{item.name}: chưa có bằng chứng trong hồ sơ; không kết luận ứng viên không có kỹ năng"),
    )


def month_index(value: str | None) -> int | None:
    if not value:
        return None
    value = normalized(value)
    match = re.fullmatch(r"(\d{4})[-/](\d{1,2})(?:[-/]\d{1,2})?", value)
    if match:
        year, month = map(int, match.groups())
    else:
        match = re.fullmatch(r"(?:tháng\s*)?(\d{1,2})[/-](\d{4})", value)
        if match:
            month, year = map(int, match.groups())
        else:
            months = {name: i for i, names in enumerate([
                ("jan", "january"), ("feb", "february"), ("mar", "march"), ("apr", "april"),
                ("may",), ("jun", "june"), ("jul", "july"), ("aug", "august"),
                ("sep", "sept", "september"), ("oct", "october"), ("nov", "november"), ("dec", "december")], 1) for name in names}
            match = re.fullmatch(r"([a-z]+)\.?\s+(\d{4})", value)
            if not match or match.group(1) not in months:
                return None
            month, year = months[match.group(1)], int(match.group(2))
    return year * 12 + month - 1 if 1 <= month <= 12 and 1900 <= year <= 2200 else None


def assess_experience(item, profile, facts, as_of: date) -> RequirementAssessment:
    # Only count dated experience that explicitly shares a domain/skill with the JD.
    vocabulary = {"backend", "frontend", "machine learning", "data analysis", "research", "software engineering", "devops"}
    vocabulary.update(text for group in profile.skills for text in group.items)
    terms = {term for term in vocabulary if contains_term(item.evidence, term)}
    months, refs = set(), []
    complete = bool(profile.experience) and bool(terms)
    relevant = False
    now = as_of.year * 12 + as_of.month - 1
    for index, entry in enumerate(profile.experience):
        texts = [text for path, text, _ in facts if path.startswith(f"/experience/{index}/")]
        if not terms or not any(contains_term(text, term) for text in texts for term in terms):
            complete = False
            continue
        relevant = True
        refs.extend(path for path, text, _ in facts if path.startswith(f"/experience/{index}/") and any(contains_term(text, term) for term in terms))
        start = month_index(entry.start_date)
        end = now if entry.is_current is True or normalized(entry.end_date or "") in {"present", "current", "hiện tại", "nay"} else month_index(entry.end_date)
        if start is None or end is None or end < start or start > now:
            complete = False
            continue
        months.update(range(start, min(end, now) + 1))
        refs.extend([f"/experience/{index}/start_date", f"/experience/{index}/end_date"])
    if item.minimum_years is None:
        value = 1.0 if relevant else 0.0
        status = "met" if relevant else "unknown"
        explanation = "Có kinh nghiệm cùng lĩnh vực được ghi rõ" if relevant else "Chưa đủ bằng chứng xác định kinh nghiệm cùng lĩnh vực"
    else:
        required_months = item.minimum_years * 12
        value = min(1.0, len(months) / required_months) if required_months else float(relevant)
        status = "met" if value == 1 else "not_met" if complete else "partially_met" if months else "unknown"
        explanation = f"Đếm hợp nhất {len(months)} tháng liên quan có ngày rõ; yêu cầu {required_months:g} tháng. Không cộng trùng thời gian; ngày thiếu không được tự điền."
    return RequirementAssessment(requirement_id=item.id, status=status, evidence_refs=refs, contribution=value, explanation=explanation)


def degree_level(text: str) -> int | None:
    for level, pattern in [(3, r"\bph\.?d\b|\bdoctorate\b|tiến sĩ"), (2, r"\bmaster\b|\bm\.?s\.?\b|thạc sĩ"), (1, r"\bbachelor\b|\bb\.?s\.?\b|cử nhân|đại học")]:
        if re.search(pattern, normalized(text)):
            return level
    return None


def assess_education(item, profile) -> RequirementAssessment:
    target = degree_level(item.evidence)
    major_aliases = {"computer science": ["computer science", "khoa học máy tính"], "information technology": ["information technology", "công nghệ thông tin"], "engineering": ["engineering", "kỹ thuật"], "business": ["business", "kinh doanh"]}
    majors = [aliases for aliases in major_aliases.values() if any(contains_term(item.evidence, alias) for alias in aliases)]
    best, refs, known = 0.0, [], []
    for index, entry in enumerate(profile.education):
        text = " ".join(filter(None, [entry.degree, entry.field_of_study, entry.major]))
        level = degree_level(text)
        if level is None or target is None:
            continue
        known.append(level)
        major_ok = not majors or any(contains_term(text, alias) for aliases in majors for alias in aliases)
        value = 1.0 if level >= target and major_ok else .5 if level >= target else 0.0
        if value > best:
            best, refs = value, [f"/education/{index}/degree", f"/education/{index}/major", f"/education/{index}/field_of_study"]
    status = "met" if best == 1 else "partially_met" if best else "unknown"
    if known and target and max(known) < target and not re.search(r"\bor\b|hoặc|equivalent|tương đương", item.evidence, re.I):
        status = "not_met"
    return RequirementAssessment(requirement_id=item.id, status=status, evidence_refs=refs, contribution=best, explanation="Đối chiếu bậc học và ngành ghi rõ; ngành chưa xác định/tương đương cần review, không suy đoán từ tên trường.")


def match_profile(profile: MasterProfile, job: JobRequirements, profile_id: str, job_id: str, *, as_of: date | None = None, confirmed_unmet: dict[str, str] | None = None) -> MatchResponse:
    as_of = as_of or date.today()
    profile_hash, job_hash = content_hash(profile), content_hash(job)
    job, warnings = normalize_requirements(job.model_copy(deep=True))
    assign_requirement_ids(job)
    warnings.extend(build_requirement_groups(job))
    unresolved_relationships = any("AND/OR" in warning or "OR chồng lấn" in warning for warning in warnings)
    if job.unspecified_skills:
        warnings.append("Các kỹ năng chưa nêu rõ bắt buộc/ưu tiên không bị coi là yêu cầu bắt buộc và không tham gia tính điểm.")
    facts = profile_facts(profile)
    assessments, fields, by_id, items_by_id = [], {}, {}, {}
    for field in ("required_skills", "preferred_skills", "experience_requirements", "education_requirements", "certifications", "languages", "technical_requirements"):
        fields[field] = []
        for item in getattr(job, field):
            if item.requirement_type == "unspecified" and field not in {"required_skills", "preferred_skills"}:
                continue
            name = getattr(item, "original_name", None) or getattr(item, "name", None)
            if field == "technical_requirements" and any(canonical(item.name) == canonical(skill.name) for skill in job.required_skills + job.preferred_skills):
                continue
            if normalized(item.evidence) not in normalized(job.job_description_raw) or (name and not contains_term(item.evidence, name)):
                warnings.append(f"Bỏ {item.id} khỏi tính điểm vì evidence JD chưa hợp lệ")
                continue
            result = assess_experience(item, profile, facts, as_of) if field == "experience_requirements" else assess_education(item, profile) if field == "education_requirements" else assess_term(item, facts)
            result.label = getattr(item, "name", None) or item.description
            result.source_field = field
            result.dimension = "preferred_skills" if item.requirement_type == "preferred" else {
                "experience_requirements": "experience", "education_requirements": "education",
                "required_skills": "required_skills",
            }.get(field, "other")
            assessments.append(result)
            by_id[item.id] = result
            items_by_id[item.id] = item
            fields[field].append(result)
    # An OR group contributes once using its best supported member, never once per alternative.
    for group in job.requirement_groups:
        if group.operator != "any" or not all(key in by_id for key in group.requirement_ids):
            continue
        members = [by_id[key] for key in group.requirement_ids]
        best = max(members, key=lambda member: member.contribution)
        combined = best.model_copy(update={"requirement_id": group.id, "label": "Một trong: " + " / ".join(group.members), "member_ids": group.requirement_ids, "explanation": f"Một trong {' / '.join(group.members)}: {best.explanation}"})
        assessments.append(combined)
        by_id[group.id] = combined
        for field in ("required_skills", "preferred_skills"):
            if any(member.requirement_id in group.requirement_ids for member in fields[field]):
                fields[field] = [member for member in fields[field] if member.requirement_id not in group.requirement_ids] + [combined]

    for assessment in assessments:
        if assessment.status == "unknown" and assessment.requirement_id in (confirmed_unmet or {}):
            assessment.status = "not_met"
            assessment.explanation = confirmed_unmet[assessment.requirement_id]
            assessment.evidence_refs = [f"user_confirmation:{assessment.requirement_id}"]

    def average(results):
        return sum(item.contribution for item in results) / len(results) if results else None

    preferred = list(fields["preferred_skills"])
    mandatory = {}
    for field in ("experience_requirements", "education_requirements", "certifications", "languages", "technical_requirements"):
        mandatory[field] = []
        for assessment in fields[field]:
            if items_by_id[assessment.requirement_id].requirement_type == "preferred":
                preferred.append(assessment)
            else:
                mandatory[field].append(assessment)
    dimensions = {"required_skills": average(fields["required_skills"]), "preferred_skills": average(preferred), "experience": average(mandatory["experience_requirements"]), "education": average(mandatory["education_requirements"]), "other": average(mandatory["certifications"] + mandatory["languages"] + mandatory["technical_requirements"])}
    core = set()
    title = normalized(job.job_title or "")
    domain = DOMAIN_SKILLS["ai"] if re.search(r"\bai\b|machine learning|artificial intelligence", title) else DOMAIN_SKILLS["backend"] if "backend" in title else DOMAIN_SKILLS["data"] if "data" in title else set()
    for item in job.required_skills:
        if item.id in by_id and (canonical(item.name) in domain or item.priority == "high" or any(canonical(core_item.name) == canonical(item.name) and normalized(core_item.evidence) in normalized(job.job_description_raw) for core_item in job.core_requirements if core_item.requirement_type == "required")):
            core.add(item.id)
    for group in job.requirement_groups:
        if group.operator == "any" and group.id in by_id and core.intersection(group.requirement_ids):
            core.difference_update(group.requirement_ids)
            core.add(group.id)
    core_coverage = average([by_id[key] for key in sorted(core)])
    dimensions["role"] = core_coverage if core else dimensions["required_skills"]
    required = fields["required_skills"]
    dimensions["practical_evidence"] = sum(float(item.contribution > 0 and any(ref.startswith(("/project/", "/experience/")) for ref in item.evidence_refs)) for item in required) / len(required) if required else None
    active = {key: value for key, value in dimensions.items() if value is not None}
    weight_sum = sum(WEIGHTS[key] for key in active)
    weights = {key: WEIGHTS[key] / weight_sum for key in active} if weight_sum else {}
    score = 100 * sum(active[key] * weights[key] for key in active) if active else None
    if unresolved_relationships:
        score = None
    if score is not None and core_coverage is not None:
        score = min(score, 50 + 50 * core_coverage)
    units = [item for field in fields.values() for item in field]
    counted_ids = {item.requirement_id for item in units}
    for assessment in assessments:
        assessment.counted_in_score = assessment.requirement_id in counted_ids
        assessment.is_core = assessment.requirement_id in core
    coverage = sum(item.status != "unknown" for item in units) / len(units) if units else 0
    warnings.append("Điểm dựa trên bằng chứng trong hồ sơ, không phải xác suất tuyển dụng. Trọng số v1 chưa được hiệu chỉnh bằng đánh giá chuyên gia.")
    if not active:
        warnings.append("Không có yêu cầu có evidence hợp lệ để tính điểm")
    return MatchResponse(
        result_id="match_" + hashlib.sha256(f"{profile_id}|{job_id}|{profile_hash}|{job_hash}|{ALGORITHM_VERSION}|{as_of}|{sorted((confirmed_unmet or {}).items())}".encode()).hexdigest()[:24],
        profile_revision_id=profile_id, job_analysis_id=job_id, profile_content_hash=profile_hash, job_content_hash=job_hash,
        algorithm_version=ALGORITHM_VERSION, score=round(score, 2) if score is not None else None,
        dimension_scores={key: round(value * 100, 2) for key, value in active.items()}, assessments=assessments,
        strengths=[item.explanation for item in units if item.status in {"met", "partially_met"}],
        gaps=[item.explanation for item in units if item.status in {"unknown", "not_met"}],
        warnings=list(dict.fromkeys(warnings)), evidence_coverage=coverage, core_coverage=core_coverage,
        applied_weights=weights, as_of=as_of.isoformat(),
    )
