import re
import unicodedata

from backend.app.schemas.profile import MasterProfile
from backend.app.ai.llm.profile_extractor import (
    extract_missing_job_titles,
    extract_profile_with_retry,
)


def extract_profile(resume_text: str) -> MasterProfile:
    profile = extract_profile_with_retry(resume_text)
    profile = fill_clear_missing_fields(profile, resume_text)
    profile = fill_missing_job_titles(profile, resume_text)
    return remove_contact_from_involvement(profile)


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
    }
    lines = [line.strip() for line in resume_text.splitlines() if line.strip()]
    for line in lines[:5]:
        words = line.replace("-", " ").split()
        normalized_words = {word.casefold() for word in words}
        only_letters = all(word.replace(".", "").isalpha() for word in words)
        if 2 <= len(words) <= 6 and only_letters and not normalized_words & ignored_words:
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
    }
    for field, source_value in contact_values.items():
        model_value = getattr(profile.contact, field)
        if source_value and (not model_value or _normalize(model_value) not in source):
            setattr(profile.contact, field, source_value)

    for education, gpa in zip(profile.education, _find_gpas(resume_text)):
        if not education.gpa or _normalize(education.gpa) not in source:
            education.gpa = gpa
    return profile


def fill_missing_job_titles(profile: MasterProfile, resume_text: str) -> MasterProfile:
    """Trích xuất lại riêng job title và chỉ nhận chuỗi nguyên văn trong CV."""
    source = _normalize(resume_text)
    missing_experiences = []
    for index, experience in enumerate(profile.experience):
        title_is_supported = (
            experience.job_title
            and _normalize(experience.job_title) in source
        )
        if not title_is_supported:
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
        if (
            index in requested_indexes
            and 0 <= index < len(profile.experience)
            and job_title
            and _normalize(job_title) in source
        ):
            profile.experience[index].job_title = job_title
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


def _string_values(value, path: str = "") -> list[tuple[str, str]]:
    values = []
    if isinstance(value, str) and value.strip():
        return [(path, value)]
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else key
            values.extend(_string_values(child, child_path))
    if isinstance(value, list):
        for index, child in enumerate(value):
            values.extend(_string_values(child, f"{path}[{index}]"))
    return values


def validate_against_source(profile: MasterProfile, resume_text: str) -> list[str]:
    """Tạo cảnh báo đối chiếu; không coi exact match là xác minh ngữ nghĩa."""
    source = _normalize(resume_text)
    warnings = []
    for path, value in _string_values(profile.model_dump(exclude={"summary"})):
        if _normalize(value) not in source:
            warnings.append(f"Cần kiểm tra {path}: không tìm thấy nguyên văn trong CV")

    if profile.summary and _normalize(profile.summary) not in source:
        warnings.append("Summary không xuất hiện nguyên văn trong CV; cần kiểm tra model có viết mới")

    companies = {_normalize(item.company) for item in profile.experience if item.company}
    for index, project in enumerate(profile.project):
        if project.project_name and _normalize(project.project_name) in companies:
            warnings.append(
                f"Cần kiểm tra project[{index}]: tên dự án trùng tên công ty"
            )
    return warnings

