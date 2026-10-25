import re
import unicodedata
import hashlib
import json
from urllib.parse import urlsplit

from backend.app.schemas.profile import MasterProfile, SkillGroup, SourceEvidence
from backend.app.ai.llm.profile_extractor import (
    extract_missing_job_titles,
    extract_profile_with_retry,
)


def extract_profile(resume_text: str) -> MasterProfile:
    profile = extract_profile_with_retry(resume_text)
    profile = fill_clear_missing_fields(profile, resume_text)
    profile = fill_missing_job_titles(profile, resume_text)
    profile = fill_explicit_skill_section(profile, resume_text)
    return assign_profile_metadata(remove_contact_from_involvement(profile))


def _first_match(pattern: str, text: str) -> str | None:
    match = re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE)
    return match.group(1).strip() if match else None


def _find_full_name(resume_text: str) -> str | None:
    labeled_name = _first_match(
        r"^(?:full\s*name|name|họ\s*(?:và\s*)?tên)\s*[:：-]\s*(.+)$",
        resume_text,
    )
    if labeled_name:
        return labeled_name

    ignored_words = {
        "resume", "curriculum", "vitae", "cv", "developer", "engineer",
        "analyst", "manager", "intern", "student", "profile", "university",
        "education", "summary", "experience", "project", "skills", "contact",
        "đại", "học", "giáo", "dục", "kinh", "nghiệm", "dự", "án",
        "kỹ", "năng", "hoạt", "động", "thông", "tin",
        "research", "assistant", "data", "scientist", "consultant", "engineering",
        "specialist", "professional", "curriculum", "laboratory", "phòng", "lab",
    }
    lines = [line.strip() for line in resume_text.splitlines() if line.strip()]
    # Only a prominent uppercase header adjacent to contact details is eligible.
    # Otherwise leave the missing name for user confirmation instead of guessing.
    header_has_contact = bool(re.search(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "\n".join(lines[1:3])))
    for line in lines[:1] if header_has_contact else []:
        words = line.replace("-", " ").split()
        normalized_words = {word.casefold() for word in words}
        only_letters = all(word.replace(".", "").isalpha() for word in words)
        if line.isupper() and 2 <= len(words) <= 6 and only_letters and not normalized_words & ignored_words:
            return line
    return None


def _find_phone(resume_text: str) -> str | None:
    labeled_phone = _first_match(
        r"^(?:phone|mobile|tel|telephone|điện\s*thoại|số\s*điện\s*thoại)"
        r"\s*[:：-]\s*([+()\d][()\d .-]{7,20})\s*$",
        resume_text,
    )
    if labeled_phone:
        return labeled_phone

    # Chỉ tìm số không có nhãn trong phần đầu CV để tránh nhầm ngày tháng.
    header = "\n".join(resume_text.splitlines()[:15])
    for match in re.finditer(r"(?<!\d)(?:\+?84|0)(?:[ .()-]*\d){8,10}(?!\d)", header):
        phone = match.group(0).strip()
        digit_count = len(re.sub(r"\D", "", phone))
        if 9 <= digit_count <= 11:
            return phone
    return None


def _find_gpas(resume_text: str) -> list[str]:
    pattern = (
        r"(?:GPA|CGPA|CPA|điểm\s*trung\s*bình|ĐTB)\s*[:：-]?\s*"
        r"(\d{1,2}(?:[.,]\d{1,2})?(?:\s*/\s*\d{1,2}(?:[.,]\d)?)?)"
    )
    return [match.group(1).strip() for match in re.finditer(pattern, resume_text, re.I)]


def _contact_text(resume_text: str) -> str:
    """Use the header and explicitly labelled contact sections, not employer data."""
    section = re.compile(
        r"^(?:summary|professional (?:summary|profile)|experience|work experience|"
        r"professional experience|education|projects?|skills|technical skills|"
        r"involvement|certifications|kinh nghiệm(?: làm việc)?|học vấn|dự án|"
        r"kỹ năng|hoạt động|giới thiệu|tóm tắt)\s*[:：]?$", re.I,
    )
    contact_heading = re.compile(
        r"^(?:contact(?: information)?|personal information|thông tin (?:liên hệ|cá nhân)|liên hệ)\s*[:：]?$", re.I,
    )
    lines = []
    active = True
    block_lines = 0
    for line in resume_text.splitlines():
        if contact_heading.fullmatch(line.strip()):
            active = True
            block_lines = 0
        elif section.fullmatch(line.strip()):
            active = False
        if active and block_lines < 20:
            lines.append(line)
            block_lines += 1
    return "\n".join(lines)


def _explicit_contact_fields(text: str) -> dict[str, str]:
    fields = {}
    labels = {
        "location": r"location|address|địa chỉ|nơi ở",
        "country": r"country|quốc gia",
        "city": r"city|thành phố",
        "state_or_province": r"state(?:\s*/\s*province)?|province|tỉnh(?:\s*/\s*thành phố)?",
    }
    for field, label in labels.items():
        value = _first_match(rf"^\s*(?:{label})\s*[:：]\s*([^|\n]+)", text)
        if value:
            fields[field] = value
    for match in re.finditer(r"(?<![\w./-])(?:https?://|www\.|(?:linkedin\.com|github\.com)/)[^\s<>|]+", text, re.I):
        url = match.group(0).rstrip(".,;)")
        try:
            parsed = urlsplit(url if "://" in url else "https://" + url)
            host = (parsed.hostname or "").lower().removeprefix("www.")
        except ValueError:
            continue
        if parsed.username or parsed.password:
            continue
        parts = [part for part in parsed.path.split("/") if part]
        if host == "linkedin.com" and len(parts) == 2 and parts[0] == "in":
            fields.setdefault("linkedin", url)
        elif host == "github.com" and len(parts) == 1 and parts[0].lower() not in {"features", "topics", "explore", "orgs"}:
            fields.setdefault("github", url)
        else:
            line_start = text.rfind("\n", 0, match.start()) + 1
            prefix = text[line_start:match.start()]
            if re.search(r"(?:portfolio|hồ sơ năng lực)\s*[:：→-]?\s*$", prefix, re.I):
                fields.setdefault("portfolio_url", url)
            elif re.search(r"(?:personal website|website|trang web|web)\s*[:：→-]?\s*$", prefix, re.I):
                fields.setdefault("website", url)
    return fields


def fill_clear_missing_fields(profile: MasterProfile, resume_text: str) -> MasterProfile:
    """Bổ sung trường có định dạng rõ, chỉ bằng chuỗi nguyên văn từ CV."""
    source = _normalize(resume_text)
    full_name = _find_full_name(resume_text)
    email = _first_match(
        r"([A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,})",
        resume_text,
    )
    phone = _find_phone(resume_text)

    contact_values = {
        "full_name": full_name,
        "email": email,
        "phone": phone,
        **_explicit_contact_fields(_contact_text(resume_text)),
    }
    for field, source_value in contact_values.items():
        model_value = getattr(profile.contact, field)
        if source_value and (not model_value or _normalize(model_value) not in source):
            setattr(profile.contact, field, source_value)

    institutions = [entry.institution for entry in profile.education if entry.institution]
    for education in profile.education:
        span = _entry_span(resume_text, education.institution, institutions)
        if span is None:
            continue
        block = resume_text[span[0]:span[1]]
        gpas = _find_gpas(block)
        if len(gpas) == 1 and (not education.gpa or _normalize(education.gpa) not in _normalize(block)):
            education.gpa = gpas[0]
    return profile


def fill_missing_job_titles(profile: MasterProfile, resume_text: str) -> MasterProfile:
    """Trích xuất lại riêng job title và chỉ nhận chuỗi nguyên văn trong CV."""
    companies = [entry.company for entry in profile.experience if entry.company]
    source = _normalize(resume_text)
    missing_experiences = []
    for index, experience in enumerate(profile.experience):
        span = _entry_span(resume_text, experience.company, companies, previous_line=True)
        block = resume_text[span[0]:span[1]] if span else None
        title_is_supported = (
            experience.job_title
            and _normalize(experience.job_title) in source
            and (block is None or _normalize(experience.job_title) in _normalize(block))
        )
        if not title_is_supported:
            experience.job_title = None
            missing_experiences.append({
                "experience_index": index,
                "company": experience.company,
                "start_date": experience.start_date,
                "end_date": experience.end_date,
                "description": experience.description,
            })

    if not missing_experiences:
        return profile

    job_titles = extract_missing_job_titles(resume_text, missing_experiences)
    requested_indexes = {item["experience_index"] for item in missing_experiences}
    for index, job_title in job_titles.items():
        if index not in requested_indexes or not 0 <= index < len(profile.experience):
            continue
        span = _entry_span(resume_text, profile.experience[index].company, companies, previous_line=True)
        if (
            span is not None
            and job_title
            and _normalize(job_title) in _normalize(resume_text[span[0]:span[1]])
        ):
            profile.experience[index].job_title = job_title
    return profile


def fill_explicit_skill_section(profile: MasterProfile, resume_text: str) -> MasterProfile:
    """Recover only verbatim list items under a Skills heading, never from projects."""
    active = False
    existing = {_normalize(item) for group in profile.skills for item in group.items}
    missing: dict[str, list[str]] = {}
    end_headings = {"experience", "education", "projects", "involvement", "summary", "contact", "kinh nghiệm", "học vấn", "dự án", "hoạt động", "tóm tắt", "giới thiệu", "chứng chỉ", "certifications", "references"}
    for raw_line in resume_text.splitlines():
        line = raw_line.strip()
        heading = re.fullmatch(r"(?:technical\s+skills|skills|kỹ\s+năng)(?:\s*[:：]\s*(.*))?", line, re.IGNORECASE)
        if heading:
            active = True
            line = (heading.group(1) or "").strip()
        elif active and _normalize(line).rstrip(":") in end_headings:
            break
        if not active or not line:
            continue
        group_name = "Other Skills"
        if ":" in line or "：" in line:
            group_name, line = re.split(r"[:：]", line, maxsplit=1)
            group_name = group_name.strip() or "Other Skills"
        # Commas inside parentheses belong to a skill, e.g. "LLMs (Llama, Qwen)".
        parts = []
        start = depth = 0
        for index, char in enumerate(line):
            if char in "([":
                depth += 1
            elif char in ")]":
                depth = max(0, depth - 1)
            elif char in ",;•" and depth == 0:
                parts.append(line[start:index])
                start = index + 1
        parts.append(line[start:])
        for item in parts:
            item = re.sub(r"^[-*\s]+", "", item).strip()
            # Do not split natural-language claims into inferred skill names.
            if item and len(item) <= 100 and _normalize(item) not in existing:
                missing.setdefault(group_name, []).append(item)
                existing.add(_normalize(item))
    for group_name, items in missing.items():
        profile.skills.append(SkillGroup(group=group_name, items=items))
    return profile


def remove_contact_from_involvement(profile: MasterProfile) -> MasterProfile:
    """Loại entry contact bị model phân loại nhầm thành involvement."""
    contact_headings = {
        "contact", "contact information", "personal information",
        "thông tin liên hệ", "thông tin cá nhân", "liên hệ",
    }
    contact_values = {
        _normalize(value)
        for value in profile.contact.model_dump().values()
        if isinstance(value, str) and value.strip()
    }

    valid_involvement = []
    for item in profile.involvement:
        main_values = [item.organization, item.role, item.activity_name]
        normalized_values = {
            _normalize(value)
            for value in main_values
            if isinstance(value, str) and value.strip()
        }
        combined_text = " ".join(
            value
            for _, value in _string_values(item.model_dump())
        )
        contains_email = bool(re.search(r"[\w.%+-]+@[\w.-]+\.[A-Za-z]{2,}", combined_text))
        contains_phone = bool(re.search(r"(?:\+?84|0)(?:[ .()-]*\d){8,10}", combined_text))

        is_contact = bool(normalized_values & contact_headings)
        is_contact = is_contact or bool(normalized_values & contact_values)
        is_contact = is_contact or (
            not item.organization and (contains_email or contains_phone)
        )
        if not is_contact:
            valid_involvement.append(item)

    profile.involvement = valid_involvement
    return profile


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    return re.sub(r"\s+", " ", text).strip().casefold()


def _source_matches(value: str, text: str) -> list[re.Match]:
    pattern = r"\s+".join(re.escape(part) for part in value.split())
    return list(re.finditer(pattern, text, re.IGNORECASE)) if pattern else []


def _entry_span(text: str, anchor: str | None, anchors: list[str], *, previous_line: bool = False) -> tuple[int, int] | None:
    """Locate a unique entity block. Ambiguous anchors deliberately remain unassigned."""
    if not anchor:
        return None
    matches = _source_matches(anchor, text)
    if len(matches) != 1:
        return None
    lines = text.splitlines(keepends=True)
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))
    target = text[:matches[0].start()].count("\n")
    headings = {"experience", "education", "projects", "skills", "involvement", "summary", "kinh nghiệm", "học vấn", "dự án", "kỹ năng", "hoạt động", "tóm tắt"}
    start = target
    if previous_line and target > 0 and _normalize(lines[target - 1]).rstrip(":") not in headings:
        start -= 1
    end = min(len(lines), target + 12)
    for other in anchors:
        if _normalize(other) == _normalize(anchor):
            continue
        for match in _source_matches(other, text):
            other_line = text[:match.start()].count("\n")
            if other_line > target:
                end = min(end, max(target + 1, other_line - int(previous_line)))
    for index in range(target + 1, end):
        if _normalize(lines[index]).rstrip(":") in headings:
            end = index
            break
    return offsets[start], offsets[end]


def assign_profile_metadata(profile: MasterProfile, *, preserve_ids: bool = False) -> MasterProfile:
    """Derive IDs and normalized skill names in Python, never invent profile facts."""
    assigned = set()
    for section in ("experience", "project", "education", "involvement", "skills"):
        for entry in getattr(profile, section):
            content = json.dumps(entry.model_dump(exclude={"id", "normalized_items"}), ensure_ascii=False, sort_keys=True)
            if not preserve_ids or not entry.id:
                base_id = f"{section}_{hashlib.sha256(content.encode()).hexdigest()[:16]}"
                entry.id = base_id
                occurrence = 2
                while entry.id in assigned:
                    entry.id = f"{base_id}_{occurrence}"
                    occurrence += 1
            if entry.id in assigned:
                raise ValueError("Duplicate profile entry ID")
            assigned.add(entry.id)
            if section == "skills":
                entry.normalized_items = [_normalize(item) for item in entry.items]
    return profile


def _string_values(value, path: str = "") -> list[tuple[str, str]]:
    values = []
    if isinstance(value, str) and value.strip():
        return [(path, value)]
    if isinstance(value, dict):
        for key, child in value.items():
            if key in {"id", "group", "normalized_items"}:
                continue
            child_path = f"{path}.{key}" if path else key
            values.extend(_string_values(child, child_path))
    if isinstance(value, list):
        for index, child in enumerate(value):
            values.extend(_string_values(child, f"{path}[{index}]"))
    return values


def build_source_evidence(profile: MasterProfile, resume_text: str, source_id: str) -> list[SourceEvidence]:
    evidence = []
    for path, value in _string_values(profile.model_dump()):
        matches = _source_matches(value, resume_text)
        # Prefer entity-specific spans to avoid attributing another school's GPA/title.
        entity = re.match(r"(experience|education)\[(\d+)\]", path)
        if entity:
            section, index = entity.group(1), int(entity.group(2))
            entries = getattr(profile, section)
            attribute = "company" if section == "experience" else "institution"
            anchors = [getattr(item, attribute) for item in entries if getattr(item, attribute)]
            span = _entry_span(resume_text, getattr(entries[index], attribute), anchors, previous_line=section == "experience")
            if span:
                matches = [match for match in matches if span[0] <= match.start() < match.end() <= span[1]]
        if matches:
            match = matches[0]
            evidence.append(SourceEvidence(field_path=path, source_id=source_id, quote=match.group(), start=match.start(), end=match.end()))
    return evidence


def confirmation_evidence(profile: MasterProfile, resume_text: str, source_id: str) -> list[SourceEvidence]:
    evidence = build_source_evidence(profile, resume_text, source_id)
    document_paths = {item.field_path for item in evidence}
    for path, value in _string_values(profile.model_dump()):
        if path not in document_paths:
            evidence.append(SourceEvidence(field_path=path, source_id=source_id, origin="user_confirmation", quote=value))
    return evidence


def validate_against_source(profile: MasterProfile, resume_text: str) -> list[str]:
    """Tạo cảnh báo đối chiếu; không coi exact match là xác minh ngữ nghĩa."""
    source = _normalize(resume_text)
    evidence_paths = {item.field_path for item in build_source_evidence(profile, resume_text, "validation")}
    warnings = []
    for path, value in _string_values(profile.model_dump(exclude={"summary"})):
        if _normalize(value) not in source:
            warnings.append(f"Cần kiểm tra {path}: không tìm thấy nguyên văn trong CV")
        elif re.match(r"(?:experience|education)\[\d+\]\.(?:job_title|gpa)$", path) and path not in evidence_paths:
            warnings.append(f"Cần kiểm tra {path}: chưa đối chiếu được với đúng employer/institution")

    if profile.summary and _normalize(profile.summary) not in source:
        warnings.append("Summary không xuất hiện nguyên văn trong CV; cần kiểm tra model có viết mới")

    companies = {_normalize(item.company) for item in profile.experience if item.company}
    for index, project in enumerate(profile.project):
        if project.project_name and _normalize(project.project_name) in companies:
            warnings.append(
                f"Cần kiểm tra project[{index}]: tên dự án trùng tên công ty"
            )
    return warnings

