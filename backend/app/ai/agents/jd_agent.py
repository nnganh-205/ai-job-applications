import re
import unicodedata

from backend.app.ai.llm.ollama_client import OllamaSchemaError, request_structured
from backend.app.ai.prompts.jd_prompt import JD_ANALYSIS_PROMPT, SKILL_EXTRACTION_PROMPT
from backend.app.schemas.job import (
    EducationRequirement,
    ExtractedJobRequirements,
    ExtractedSkills,
    ExperienceRequirement,
    JobRequirements,
    RequirementItem,
)


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", text)).strip()


def normalize_skill(item: RequirementItem) -> RequirementItem:
    original_name = normalize_whitespace(item.name)
    normalized_name = re.sub(
        r"^(?:solid understanding of|basic knowledge of|experience working with|"
        r"basic experience with|understanding of|strong)\s+",
        "",
        original_name,
        flags=re.IGNORECASE,
    )
    normalized_name = re.sub(r"\s+knowledge$", "", normalized_name, flags=re.IGNORECASE)
    aliases = {
        "torch": "PyTorch",
        "nlp": "NLP (Natural Language Processing)",
        "natural language processing": "NLP (Natural Language Processing)",
        "llm": "LLM (Large Language Model)",
        "large language model": "LLM (Large Language Model)",
        "good ml foundation": "Machine Learning fundamentals",
    }
    normalized_name = aliases.get(normalized_name.casefold(), normalized_name)
    if normalized_name == original_name:
        return item.model_copy(update={"name": original_name})
    return item.model_copy(
        update={"name": normalized_name, "original_name": original_name}
    )


def remove_duplicates(items: list) -> list:
    unique_items = []
    seen = set()
    for item in items:
        name = getattr(item, "name", getattr(item, "description", ""))
        key = (normalize_whitespace(name).casefold(), normalize_whitespace(item.evidence).casefold())
        if key not in seen:
            seen.add(key)
            unique_items.append(item)
    return unique_items


def validate_evidence(requirements: JobRequirements) -> list[str]:
    raw_text = normalize_whitespace(requirements.job_description_raw).casefold()
    warnings = []
    fields = (
        "required_skills",
        "preferred_skills",
        "experience_requirements",
        "education_requirements",
        "responsibilities",
        "core_requirements",
    )
    for field in fields:
        for index, item in enumerate(getattr(requirements, field)):
            if normalize_whitespace(item.evidence).casefold() not in raw_text:
                warnings.append(f"{field}[{index}] có evidence không xuất hiện nguyên văn trong JD")
            if field in {"required_skills", "preferred_skills"}:
                skill_name = item.original_name or item.name
                if normalize_whitespace(skill_name).casefold() not in raw_text:
                    warnings.append(
                        f"{field}[{index}] có tên kỹ năng không xuất hiện trong JD; cần review"
                    )
    return warnings


def fill_explicit_experience_years(requirements: JobRequirements) -> None:
    """Lấy minimum_years khi chính evidence có ghi số năm rõ ràng."""
    pattern = r"(\d+(?:[.,]\d+)?)\s*(?:\+|[-–]\s*\d+(?:[.,]\d+)?)?\s*(?:years?|năm)"
    for item in requirements.experience_requirements:
        if item.minimum_years is not None:
            continue
        match = re.search(pattern, item.evidence, re.IGNORECASE)
        if match:
            item.minimum_years = float(match.group(1).replace(",", "."))


def extract_section(
    job_description: str,
    start_headings: tuple[str, ...],
    end_headings: set[str],
) -> str:
    lines = [line.strip() for line in job_description.splitlines() if line.strip()]
    normalized_lines = [normalize_whitespace(line).casefold().rstrip(":") for line in lines]
    start_index = None
    # Heading cụ thể như "Requirements" được ưu tiên hơn heading bao quát.
    for heading in start_headings:
        if heading in normalized_lines:
            start_index = normalized_lines.index(heading)
            break
    if start_index is None:
        return ""

    selected_lines = []
    for line, heading in zip(lines[start_index + 1:], normalized_lines[start_index + 1:]):
        if heading in end_headings:
            break
        selected_lines.append(line)
    return "\n".join(selected_lines)


def extract_requirement_section(job_description: str) -> str:
    return extract_section(
        job_description,
        ("requirements", "yêu cầu ứng viên", "yêu cầu công việc", "qualifications", "your skills and experience"),
        {
            "what we offer", "why you'll love working here", "benefits",
            "quyền lợi", "quyền lợi được hưởng", "about the company",
        },
    )


def extract_responsibility_section(job_description: str) -> str:
    return extract_section(
        job_description,
        ("responsibilities", "công việc chính", "mô tả công việc", "the job"),
        {
            "requirements", "yêu cầu ứng viên", "yêu cầu công việc",
            "qualifications", "your skills and experience", "what we offer",
            "quyền lợi", "quyền lợi được hưởng",
        },
    )


def split_requirement_sentences(requirement_text: str) -> list[str]:
    # Một số website tách thẻ in đậm giữa câu thành nhiều dòng; ghép lại đến dấu câu.
    joined_lines = []
    current_line = ""
    for line in requirement_text.splitlines():
        current_line = f"{current_line} {line.strip()}".strip()
        if re.search(r"[.!?]$", current_line):
            joined_lines.append(current_line)
            current_line = ""
    if current_line:
        joined_lines.append(current_line)

    sentences = []
    for line in joined_lines:
        sentences.extend(
            part.strip()
            for part in re.split(r"(?<=[.!?])\s+", line.strip())
            if part.strip()
        )
    return sentences


def is_preferred_requirement(sentence: str) -> bool:
    text = normalize_whitespace(sentence).casefold()
    markers = (
        "ưu tiên", "điểm cộng", "lợi thế", "preferred", "nice to have",
        "a plus", "is a plus", "advantage", "bonus",
    )
    return any(marker in text for marker in markers)


def is_education_requirement(sentence: str) -> bool:
    text = normalize_whitespace(sentence).casefold()
    markers = ("tốt nghiệp", "bằng cấp", "cử nhân", "đại học", "bachelor", "degree", "graduate")
    return any(marker in text for marker in markers)


def build_skill_items(skill_names: list[str], requirement_text: str) -> tuple[list[RequirementItem], list[str]]:
    """Gắn skill vào đúng câu evidence; bỏ mọi tên không xuất hiện nguyên văn."""
    sentences = split_requirement_sentences(requirement_text)
    items = []
    warnings = []
    vague_names = {"concepts and applications", "similar backend frameworks", "related field"}
    responsibility_verbs = (
        "collaborate ", "develop ", "implement ", "support ",
        "document ", "participate ", "work with ",
    )
    for skill_name in skill_names:
        skill_name = normalize_whitespace(skill_name)
        if skill_name.casefold() in vague_names or skill_name.casefold().startswith(responsibility_verbs):
            continue
        matches = []
        supported_name = skill_name
        for word_index in range(len(skill_name.split())):
            candidate = " ".join(skill_name.split()[word_index:])
            candidate_matches = [
                sentence for sentence in sentences
                if candidate.casefold() in normalize_whitespace(sentence).casefold()
                and not is_education_requirement(sentence)
            ]
            if candidate_matches:
                supported_name = candidate
                matches = candidate_matches
                break
        if not matches:
            appears_only_in_education = any(
                skill_name.casefold() in normalize_whitespace(sentence).casefold()
                and is_education_requirement(sentence)
                for sentence in sentences
            )
            if appears_only_in_education:
                continue
            warnings.append(f"Bỏ skill '{skill_name}' vì không tìm thấy evidence phù hợp trong JD")
            continue
        required_matches = [sentence for sentence in matches if not is_preferred_requirement(sentence)]
        evidence = required_matches[0] if required_matches else matches[0]
        requirement_type = "required" if required_matches else "preferred"
        items.append(RequirementItem(
            name=supported_name,
            requirement_type=requirement_type,
            evidence=evidence,
        ))
    return remove_duplicates(items), warnings


def fill_missing_skills(requirements: JobRequirements) -> list[str]:
    requirement_text = extract_requirement_section(requirements.job_description_raw)
    responsibility_text = extract_responsibility_section(requirements.job_description_raw)
    preferred_requirements = [
        sentence
        for sentence in split_requirement_sentences(requirement_text)
        if is_preferred_requirement(sentence)
    ]
    preferred_responsibilities = [
        sentence
        for sentence in split_requirement_sentences(responsibility_text)
        if is_preferred_requirement(sentence)
    ]
    skill_source = "\n".join([requirement_text, *preferred_responsibilities]).strip()
    if not skill_source:
        return []

    extracted = request_structured(
        [
            {"role": "system", "content": SKILL_EXTRACTION_PROMPT},
            {"role": "user", "content": skill_source},
        ],
        ExtractedSkills,
    )
    skill_names = list(extracted.skills)
    preferred_sentences = preferred_requirements + preferred_responsibilities
    if preferred_sentences:
        preferred = request_structured(
            [
                {
                    "role": "system",
                    "content": SKILL_EXTRACTION_PROMPT + "\nExtract only preferred skills.",
                },
                {"role": "user", "content": "\n".join(preferred_sentences)},
            ],
            ExtractedSkills,
        )
        skill_names.extend(preferred.skills)

    skill_items, warnings = build_skill_items(skill_names, skill_source)
    requirements.required_skills = []
    requirements.preferred_skills = []
    for item in skill_items:
        target = (
            requirements.required_skills
            if item.requirement_type == "required"
            else requirements.preferred_skills
        )
        target.append(item)
    return warnings


def fill_section_fields(requirements: JobRequirements) -> None:
    requirement_sentences = split_requirement_sentences(
        extract_requirement_section(requirements.job_description_raw)
    )
    responsibility_sentences = split_requirement_sentences(
        extract_responsibility_section(requirements.job_description_raw)
    )

    requirements.responsibilities = [
        RequirementItem(
            name=sentence,
            requirement_type="unspecified",
            evidence=sentence,
        )
        for sentence in responsibility_sentences
    ]
    requirements.education_requirements = [
        EducationRequirement(
            description=sentence,
            requirement_type="preferred" if is_preferred_requirement(sentence) else "required",
            evidence=sentence,
        )
        for sentence in requirement_sentences
        if is_education_requirement(sentence)
    ]

    experience_markers = ("experience", "kinh nghiệm", "đã từng", "hands-on")
    requirements.experience_requirements = [
        ExperienceRequirement(
            description=sentence,
            minimum_years=None,
            requirement_type="preferred" if is_preferred_requirement(sentence) else "required",
            evidence=sentence,
        )
        for sentence in requirement_sentences
        if not is_education_requirement(sentence)
        and any(marker in sentence.casefold() for marker in experience_markers)
    ]


def fill_core_requirements(requirements: JobRequirements) -> None:
    if requirements.core_requirements:
        return
    requirements.core_requirements = [
        RequirementItem(
            name=item.name,
            requirement_type=item.requirement_type,
            evidence=item.evidence,
        )
        for item in requirements.required_skills[:5]
    ]


def normalize_requirements(requirements: JobRequirements) -> tuple[JobRequirements, list[str]]:
    warnings = []
    required_skills = []
    for item in requirements.required_skills:
        if item.requirement_type != "required":
            warnings.append(f"Kỹ năng '{item.name}' nằm trong required nhưng model gán nhãn khác")
        required_skills.append(normalize_skill(item.model_copy(update={"requirement_type": "required"})))

    preferred_skills = []
    for item in requirements.preferred_skills:
        if item.requirement_type != "preferred":
            warnings.append(f"Kỹ năng '{item.name}' nằm trong preferred nhưng model gán nhãn khác")
        preferred_skills.append(normalize_skill(item.model_copy(update={"requirement_type": "preferred"})))

    requirements.required_skills = remove_duplicates(required_skills)
    requirements.preferred_skills = remove_duplicates(preferred_skills)
    requirements.experience_requirements = remove_duplicates(requirements.experience_requirements)
    requirements.education_requirements = remove_duplicates(requirements.education_requirements)
    requirements.responsibilities = remove_duplicates(requirements.responsibilities)
    requirements.core_requirements = remove_duplicates([
        normalize_skill(item) for item in requirements.core_requirements
    ])
    fill_explicit_experience_years(requirements)
    warnings.extend(validate_evidence(requirements))
    return requirements, warnings


def analyze_job_description(job_description_raw: str) -> tuple[JobRequirements, list[str]]:
    cleaned_text = normalize_whitespace(job_description_raw)
    if len(cleaned_text) < 30:
        raise ValueError("Nội dung JD quá ngắn để phân tích")

    messages = [
        {"role": "system", "content": JD_ANALYSIS_PROMPT},
        {"role": "user", "content": f"Job description:\n\n{job_description_raw}"},
    ]
    try:
        extracted = request_structured(messages, ExtractedJobRequirements)
    except OllamaSchemaError:
        # Chỉ thử lại một lần và vẫn bắt model tuân theo cùng một schema.
        messages.append({
            "role": "user",
            "content": "The previous response was invalid. Return only JSON matching the schema.",
        })
        extracted = request_structured(messages, ExtractedJobRequirements)
    requirements = JobRequirements(
        **extracted.model_dump(),
        job_description_raw=job_description_raw,
    )
    fill_section_fields(requirements)
    skill_warnings = fill_missing_skills(requirements)
    requirements, warnings = normalize_requirements(requirements)
    fill_core_requirements(requirements)
    return requirements, skill_warnings + warnings

