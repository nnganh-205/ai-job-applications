import re
import unicodedata
import hashlib
from backend.app.ai.agents.jd_choices import ONE_OF, choice_for_item, choice_type, one_of_blocks

from backend.app.ai.llm.ollama_client import OllamaSchemaError, request_structured
from backend.app.ai.prompts.jd_prompt import JD_ANALYSIS_PROMPT, SKILL_EXTRACTION_PROMPT
from backend.app.schemas.job import (
    EducationRequirement,
    ExtractedJobRequirements,
    ExtractedSkills,
    ExperienceRequirement,
    JobRequirements,
    RequirementItem,
    RequirementGroup,
)


GENERIC_SKILL_NAMES = {
    "dots", "programming languages", "client sites", "data", "distributed",
    "deploying", "operating", "production", "reliable", "motivated",
    "software systems", "technical requirements", "different audiences",
    "practical engineering problems",
}


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", text)).strip()


def normalize_skill(item: RequirementItem) -> RequirementItem:
    original_name = normalize_whitespace(item.name)
    normalized_name = re.sub(
        r"^(?:solid understanding of|strong knowledge of|basic knowledge of|experience working with|"
        r"basic experience with|hands-on experience with|experience with|familiarity with|"
        r"proficiency in|knowledge of|understanding of|strong)\s+",
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
        "collaboration": "Collaboration", "collaborating": "Collaboration",
        "collaborate": "Collaboration", "communicate": "Communication",
        "communicating": "Communication", "communication": "Communication",
    }
    normalized_name = aliases.get(normalized_name.casefold(), normalized_name)
    if normalized_name == original_name:
        return item.model_copy(update={"name": original_name})
    return item.model_copy(
        update={"name": normalized_name, "original_name": item.original_name or original_name}
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
        "unspecified_skills",
        "experience_requirements",
        "education_requirements",
        "responsibilities",
        "core_requirements",
        "certifications", "languages", "technical_requirements",
    )
    for field in fields:
        for index, item in enumerate(getattr(requirements, field)):
            if normalize_whitespace(item.evidence).casefold() not in raw_text:
                warnings.append(f"{field}[{index}] có evidence không xuất hiện nguyên văn trong JD")
            if field in {"required_skills", "preferred_skills", "unspecified_skills"}:
                skill_name = item.original_name or item.name
                if normalize_whitespace(skill_name).casefold() not in normalize_whitespace(item.evidence).casefold():
                    warnings.append(
                        f"{field}[{index}] có tên kỹ năng không xuất hiện trong JD; cần review"
                    )
    return warnings


def fill_explicit_experience_years(requirements: JobRequirements) -> None:
    """Lấy minimum_years khi chính evidence có ghi số năm rõ ràng."""
    pattern = r"(\d+(?:[.,]\d+)?)\s*(?:\+|(?:[-–—]|to|đến|tới)\s*\d+(?:[.,]\d+)?\s*\+?)?\s*(?:years?|năm)"
    for item in requirements.experience_requirements:
        values = {float(match.group(1).replace(",", ".")) for match in re.finditer(pattern, item.evidence, re.IGNORECASE)}
        # Never keep model-invented years. Multiple different minima need review.
        is_maximum = re.search(r"up to|at most|tối đa|không quá", item.evidence, re.I)
        item.minimum_years = next(iter(values)) if len(values) == 1 and not is_maximum else None


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
        ("requirements", "yêu cầu ứng viên", "yêu cầu công việc", "qualifications", "your skills and experience",
         "who you are", "what we look for", "what we're looking for", "what you bring", "what we require"),
        {
            "what we offer", "why you'll love working here", "benefits",
            "quyền lợi", "quyền lợi được hưởng", "about the company",
            "responsibilities", "mô tả công việc", "công việc chính",
            "what you'll do", "where you'll be", "where you will work", "our benefits",
        },
    )


def extract_responsibility_section(job_description: str) -> str:
    return extract_section(
        job_description,
        ("responsibilities", "công việc chính", "mô tả công việc", "the job", "what you'll do", "what you will do"),
        {
            "requirements", "yêu cầu ứng viên", "yêu cầu công việc",
            "qualifications", "your skills and experience", "what we offer",
            "quyền lợi", "quyền lợi được hưởng",
            "who you are", "what we look for", "what we're looking for", "what you bring", "what we require",
        },
    )


def split_requirement_sentences(requirement_text: str) -> list[str]:
    # Keep independent bullets separate even without punctuation. Join only clear
    # inline continuations from legacy HTML ("knowledge of" / "NLP" / "and" ...).
    joined_lines = []
    current_line = ""
    for line in requirement_text.splitlines():
        line = line.strip()
        if not line:
            continue
        continuation = re.search(r"\b(?:of|with|and|or|và|hoặc)$", current_line, re.I) or re.match(r"^(?:(?:and|or|và|hoặc)\b|is (?:a|an) (?:plus|advantage))", line, re.I)
        if current_line and not continuation:
            joined_lines.append(current_line)
            current_line = ""
        current_line = f"{current_line} {line}".strip()
        if re.search(r"[.!?]$", current_line):
            joined_lines.append(current_line)
            current_line = ""
    if current_line:
        joined_lines.append(current_line)

    sentences = []
    for line in joined_lines:
        sentences.extend(
            part.strip()
            for part in re.split(r"(?<=[.!?;])\s+", line.strip())
            if part.strip()
        )
    return sentences


def is_preferred_requirement(sentence: str) -> bool:
    text = normalize_whitespace(sentence).casefold()
    markers = (
        "ưu tiên", "điểm cộng", "lợi thế", "preferred", "preferably", "nice to have", "nice-to-have",
        "a plus", "is a plus", "advantage", "bonus",
    )
    return any(marker in text for marker in markers)


def is_education_requirement(sentence: str) -> bool:
    text = normalize_whitespace(sentence).casefold()
    markers = ("tốt nghiệp", "bằng cấp", "cử nhân", "đại học", "bachelor", "degree", "graduate", "preferred fields", "educational background", "academic background")
    return any(marker in text for marker in markers)


def build_skill_items(skill_names: list[str], requirement_text: str) -> tuple[list[RequirementItem], list[str]]:
    """Gắn skill vào đúng câu evidence; bỏ mọi tên không xuất hiện nguyên văn."""
    sentences = split_requirement_sentences(requirement_text)
    items = []
    warnings = []
    vague_names = {"concepts and applications", "similar backend frameworks", "related field", "work", "experience", "skills", "knowledge", "unit", "independent work", "dots", "programming languages", "client sites"}
    responsibility_verbs = (
        "collaborate ", "develop ", "implement ", "support ",
        "document ", "participate ", "work with ",
    )
    for skill_name in skill_names:
        skill_name = normalize_whitespace(skill_name)
        if skill_name.casefold() in vague_names | GENERIC_SKILL_NAMES or skill_name.casefold().startswith(responsibility_verbs):
            continue
        matches = []
        supported_name = skill_name
        for word_index in range(len(skill_name.split())):
            candidate = " ".join(skill_name.split()[word_index:])
            if candidate.casefold() in vague_names:
                continue
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
    preferred_section = extract_section(
        requirements.job_description_raw,
        ("nice to have", "nice-to-have", "preferred skills", "preferred qualifications", "ưu tiên", "điểm cộng"),
        {"responsibilities", "mô tả công việc", "about the company", "benefits", "quyền lợi", "contact info"},
    )
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
        task="jd",
    )
    skill_names = list(extracted.skills)
    preferred_sentences = preferred_requirements + preferred_responsibilities
    if preferred_sentences or preferred_section:
        preferred = request_structured(
            [
                {
                    "role": "system",
                    "content": SKILL_EXTRACTION_PROMPT + "\nExtract only preferred skills.",
                },
                {"role": "user", "content": preferred_section or "\n".join(preferred_sentences)},
            ],
            ExtractedSkills,
            task="jd",
        )
        skill_names.extend(preferred.skills)

    skill_items, warnings = build_skill_items(skill_names, skill_source)
    for item in skill_items:
        target = (
            requirements.required_skills
            if item.requirement_type == "required"
            else requirements.preferred_skills
        )
        if not any(normalize_whitespace(existing.name).casefold() == normalize_whitespace(item.name).casefold() for existing in target):
            target.append(item)
    return warnings


def fill_section_fields(requirements: JobRequirements) -> None:
    requirement_sentences = split_requirement_sentences(
        extract_requirement_section(requirements.job_description_raw)
    )
    responsibility_sentences = split_requirement_sentences(
        extract_responsibility_section(requirements.job_description_raw)
    )
    # Some short feed JDs have no headings at all. Recover only sentences that
    # explicitly address the candidate, never facts about the hiring company.
    source_sentences = split_requirement_sentences(requirements.job_description_raw)
    if not requirement_sentences:
        requirement_sentences = [sentence for sentence in source_sentences if re.match(
            r"^(?:we(?:'re| are) (?:looking for|seeking)|you (?:must|should|have)\b|"
            r"candidates? (?:must|should|have)\b|ứng viên (?:cần|phải)|bạn (?:cần|phải))",
            sentence, re.I,
        )]
    if not responsibility_sentences:
        responsibility_sentences = [sentence for sentence in source_sentences if re.match(
            r"^(?:you(?:'ll| will)\b|you (?:build|develop|design|create|turn|write|test)\b|bạn sẽ\b)",
            sentence, re.I,
        )]

    responsibilities = [
        RequirementItem(
            name=sentence,
            requirement_type="unspecified",
            evidence=sentence,
        )
        for sentence in responsibility_sentences
    ]
    education_requirements = [
        EducationRequirement(
            description=sentence,
            requirement_type="preferred" if is_preferred_requirement(sentence) else "required",
            evidence=sentence,
        )
        for sentence in requirement_sentences
        if is_education_requirement(sentence)
    ]

    experience_markers = ("experience", "kinh nghiệm", "đã từng", "hands-on")
    experience_requirements = [
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
    for field, recovered in (("responsibilities", responsibilities), ("education_requirements", education_requirements), ("experience_requirements", experience_requirements)):
        existing = getattr(requirements, field)
        for item in recovered:
            if not any(normalize_whitespace(item.evidence).casefold() in normalize_whitespace(old.evidence).casefold() or normalize_whitespace(old.evidence).casefold() in normalize_whitespace(item.evidence).casefold() for old in existing):
                existing.append(item)


def fill_core_requirements(requirements: JobRequirements) -> None:
    if requirements.core_requirements:
        return
    requirements.core_requirements = [
        RequirementItem(
            name=item.name,
            requirement_type=item.requirement_type,
            evidence=item.evidence,
        )
        for item in requirements.required_skills if item.priority == "high"
    ]


def source_skill_classification(name: str, raw_text: str, evidence: str | None = None) -> tuple[str, str] | None:
    """Use explicit section and local clause scope, not a whole-page preference."""
    mode = None
    candidates = []
    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    for index, line in enumerate(lines):
        heading = normalize_whitespace(line).casefold().rstrip(":")
        if heading in {"requirements", "qualifications", "required skills", "minimum qualifications", "yêu cầu công việc", "yêu cầu ứng viên", "your skills and experience", "who you are", "what we look for", "what we're looking for", "what you bring", "what we require"}:
            mode = "required"
            continue
        if heading in {"nice to have", "nice-to-have", "preferred", "preferred skills", "preferred qualifications", "ưu tiên", "điểm cộng"}:
            mode = "preferred"
            continue
        if heading in {"responsibilities", "mô tả công việc", "công việc chính", "benefits", "quyền lợi", "what we offer", "about the company", "contact info", "what you'll do", "what you will do", "where you'll be", "where you will work", "our benefits"}:
            mode = None
            continue
        if mode is None or not re.search(r"(?<!\w)" + re.escape(name) + r"(?!\w)", line, re.I):
            continue
        block = line
        # Legacy scraped inline bold text may occupy separate lines.
        following = lines[index + 1:index + 5]
        if following and (re.fullmatch(r"and|or|và|hoặc", following[0], re.I) or re.match(r"is (?:a|an) (?:plus|advantage)", following[0], re.I)):
            block = " ".join([line, *following[:next((i + 1 for i, value in enumerate(following) if re.search(r"[.!?]$", value)), len(following))]])
        clauses = re.split(r";|(?<=[.!?])\s+(?=[A-ZĐ])|\bbut\b|\bwhereas\b|\bnhưng\b", block, flags=re.I)
        clause = next((part.strip() for part in clauses if name.casefold() in part.casefold()), block)
        kind = "preferred" if is_preferred_requirement(clause) else "required" if re.search(r"\b(?:must|required|mandatory)\b|bắt buộc", clause, re.I) else mode
        candidates.append((kind, clause))
    if evidence:
        exact = next((candidate for candidate in candidates if normalize_whitespace(candidate[1]).casefold().rstrip(".;") == normalize_whitespace(evidence).casefold().rstrip(".;")), None)
        if exact:
            return exact
    return next((candidate for candidate in candidates if candidate[0] == "required"), candidates[0] if candidates else None)


def normalize_requirements(requirements: JobRequirements) -> tuple[JobRequirements, list[str]]:
    warnings = []
    required_skills = []
    preferred_skills = []
    unspecified_skills = []
    choices = one_of_blocks(requirements.job_description_raw)
    expanded = []
    for item in [*requirements.required_skills, *requirements.preferred_skills, *requirements.unspecified_skills]:
        # Some models return one item named "SQL or MongoDB" despite the schema.
        # Split short explicit names only, never split inside parentheses or R&D.
        parts = re.split(r"\s+(?:and/or|or|hoặc)\s+", item.name, flags=re.I)
        if len(parts) == 1:
            and_parts = re.split(r"\s+(?:and|và)\s+", item.name, flags=re.I)
            if len(and_parts) > 1 and all(all(word[0].isupper() for word in part.split()) for part in and_parts):
                parts = and_parts
        if len(parts) > 1 and all(1 <= len(part.split()) <= 4 for part in parts) and not re.search(r"[()]|research and development|written and verbal", item.name, re.I):
            expanded.extend(item.model_copy(update={"name": part.strip(), "original_name": None}) for part in parts)
        else:
            expanded.append(item)
    for item in expanded:
        if item.name.casefold() in GENERIC_SKILL_NAMES:
            continue
        # Recover only explicit surface forms, never semantic inventions. For example,
        # a model's "Collaboration" may quote "collaborating"; retain that exact quote.
        surface_forms = {"collaboration": ("collaborating", "collaborate"), "communication": ("communicate", "communicating")}
        if not re.search(re.escape(item.original_name or item.name), item.evidence, re.I):
            for form in surface_forms.get(item.name.casefold(), ()):
                match = re.search(r"\b" + re.escape(form) + r"\b", item.evidence, re.I)
                if match:
                    item = item.model_copy(update={"original_name": match.group()})
                    break
            parenthetical = re.fullmatch(r"(.+?)\s*\(([^()]+)\)", item.name)
            if parenthetical:
                match = re.search(re.escape(parenthetical[1].strip()) + r"\s+(?:such as|like)\s+(" + re.escape(parenthetical[2].strip()) + r")\b", item.evidence, re.I)
                if match:
                    item = item.model_copy(update={"name": match[1], "original_name": None})
        original_choice = choice_for_item(item.original_name or item.name, item.evidence, choices)
        source_classification = source_skill_classification(item.original_name or item.name, requirements.job_description_raw, item.evidence)
        if source_classification:
            item = item.model_copy(update={"requirement_type": source_classification[0], "evidence": source_classification[1]})
        if is_education_requirement(item.evidence):
            # Degrees/preferred academic fields belong to education, not mandatory skills.
            continue
        boundary = r";|\bbut\b|\bwhereas\b|\bnhưng\b"
        if is_preferred_requirement(item.evidence) and re.search(r"\b(?:required|must|mandatory)\b|bắt buộc", item.evidence, re.I):
            boundary += r"|,|\band\b|\bvà\b"
        clauses = re.split(boundary, item.evidence, flags=re.I)
        name = item.original_name or item.name
        clause = next((part for part in clauses if normalize_whitespace(name).casefold() in normalize_whitespace(part).casefold()), item.evidence)
        requirement_type = item.requirement_type
        if is_preferred_requirement(clause):
            requirement_type = "preferred"
        elif re.search(r"\b(?:required|must|mandatory)\b|bắt buộc", clause, re.I):
            requirement_type = "required"
        choice = original_choice or choice_for_item(item.original_name or item.name, item.evidence, choices)
        if choice:
            requirement_type = choice_type(choice, requirements.job_description_raw)
            item = item.model_copy(update={"evidence": choice})
        normalized = normalize_skill(item.model_copy(update={"requirement_type": requirement_type}))
        target = {"required": required_skills, "preferred": preferred_skills, "unspecified": unspecified_skills}[requirement_type]
        target.append(normalized)

    requirements.required_skills = remove_duplicates(required_skills)
    requirements.preferred_skills = remove_duplicates(preferred_skills)
    requirements.unspecified_skills = remove_duplicates(unspecified_skills)
    # A paraphrased skill label is not evidence. If its full source passage is
    # already retained as a validated typed requirement, discard only that
    # redundant label. Otherwise leave it flagged for human review.
    raw_source = normalize_whitespace(requirements.job_description_raw).casefold()
    typed_requirements = requirements.experience_requirements + requirements.education_requirements + requirements.technical_requirements
    for field in ("required_skills", "preferred_skills", "unspecified_skills"):
        retained = []
        for item in getattr(requirements, field):
            evidence = normalize_whitespace(re.sub(r"^[-+•*]\s*", "", item.evidence)).casefold()
            literal_name = normalize_whitespace(item.original_name or item.name).casefold()
            covered = any(other.requirement_type == item.requirement_type
                          and evidence in normalize_whitespace(other.evidence).casefold()
                          and normalize_whitespace(other.evidence).casefold() in raw_source
                          for other in typed_requirements)
            if literal_name not in normalize_whitespace(item.evidence).casefold() and evidence in raw_source and covered:
                warnings.append("Loại nhãn kỹ năng diễn đạt lại; toàn bộ evidence được giữ trong yêu cầu kinh nghiệm/học vấn/kỹ thuật tương ứng.")
            else:
                retained.append(item)
        setattr(requirements, field, retained)
    # Keep the concrete constituents rather than also scoring the model's combined
    # "system design, data structures, and algorithms" item for the same clause.
    for field in ("required_skills", "preferred_skills", "unspecified_skills"):
        items = getattr(requirements, field)
        def constituent_count(item):
            return sum(other is not item and len(other.name) < len(item.name)
                       and re.search(r"(?<!\w)" + re.escape(other.name) + r"(?!\w)", item.name, re.I) is not None
                       and normalize_whitespace(other.evidence).casefold() == normalize_whitespace(item.evidence).casefold()
                       for other in items)
        setattr(requirements, field, [item for item in items if constituent_count(item) < 2])
    for field in ("technical_requirements", "experience_requirements", "education_requirements", "certifications", "languages", "core_requirements"):
        for item in getattr(requirements, field):
            choice = choice_for_item(getattr(item, "original_name", None) or getattr(item, "name", getattr(item, "description", "")), item.evidence, choices)
            if choice:
                item.requirement_type = choice_type(choice, requirements.job_description_raw)
                item.evidence = choice
    requirements.experience_requirements = remove_duplicates(requirements.experience_requirements)
    requirements.education_requirements = remove_duplicates(requirements.education_requirements)
    requirements.responsibilities = remove_duplicates(requirements.responsibilities)
    requirements.core_requirements = remove_duplicates([
        normalize_skill(item) for item in requirements.core_requirements
    ])
    fill_explicit_experience_years(requirements)
    emphasized = r"\b(?:core|essential|critical|mandatory|must)\b|bắt buộc|cốt lõi"
    for item in requirements.required_skills + requirements.preferred_skills:
        if item.priority == "high" and not re.search(emphasized, item.evidence, re.I):
            item.priority = None
    requirements.core_requirements = [item for item in requirements.core_requirements if item.requirement_type == "required" and re.search(emphasized, item.evidence, re.I)]
    raw = normalize_whitespace(requirements.job_description_raw).casefold()
    if requirements.employment_type and not any(marker in raw for marker in {
        "full-time": ["full-time", "full time", "toàn thời gian"],
        "part-time": ["part-time", "part time", "bán thời gian"],
        "internship": ["intern", "thực tập"], "contract": ["contract", "hợp đồng"],
    }[requirements.employment_type]):
        warnings.append("Bỏ employment_type vì JD không ghi rõ loại hợp đồng")
        requirements.employment_type = None
    for field in ("job_title", "company", "location", "salary", "job_summary"):
        value = getattr(requirements, field)
        if value is not None and (not value.strip() or normalize_whitespace(value).casefold() not in raw):
            if value.strip():
                warnings.append(f"{field} chưa có bằng chứng nguyên văn; để null")
            setattr(requirements, field, None)
    warnings.extend(validate_evidence(requirements))
    return requirements, warnings


def assign_requirement_ids(requirements: JobRequirements) -> None:
    for field in ("required_skills", "preferred_skills", "unspecified_skills", "experience_requirements", "education_requirements", "responsibilities", "core_requirements", "certifications", "languages", "technical_requirements"):
        for item in getattr(requirements, field):
            name = getattr(item, "name", getattr(item, "description", ""))
            key = normalize_whitespace(f"{field}|{name}|{item.evidence}|{item.requirement_type}").casefold()
            item.id = "req_" + hashlib.sha256(key.encode()).hexdigest()[:16]


def build_requirement_groups(requirements: JobRequirements) -> list[str]:
    """Validate alternatives against source connectors; preserve flat skill API."""
    warnings = []
    skills = requirements.required_skills + requirements.preferred_skills + requirements.unspecified_skills
    candidates = list(requirements.requirement_groups)
    for block in one_of_blocks(requirements.job_description_raw):
        members = [item for item in skills if item.evidence == block]
        if len(members) >= 2:
            candidates.insert(0, RequirementGroup(operator="any", members=[item.name for item in members], requirement_type=choice_type(block, requirements.job_description_raw), evidence=block))
    def alternative_separator(part):
        # Examples refine an alternative: "Iceberg or frameworks like Spark,
        # Beam or Flink". Never cross an AND clause or an independent sentence.
        return bool(
            re.fullmatch(r"[\s(),]*(?:and/or|or|hoặc|hay)[\s(),]*", part, re.I)
            or re.fullmatch(r"[\s()]*,[\s(),]*", part)
            or re.fullmatch(r"\s+(?:such as|like)\s+", part, re.I)
            or re.fullmatch(r"[\s,]*(?:or|hoặc|hay)\s+(?:a|an|the)\s+", part, re.I)
            or (not re.search(r"\b(?:and|và|must|required)\b|[.;\n]", part, re.I)
                and re.fullmatch(r"[\s,]*(?:or|hoặc|hay)\s+[\w ,()-]{1,100}?\s+(?:such as|like)\s+", part, re.I))
        )

    def alternatives(separators, tail=""):
        valid = all(alternative_separator(part) for part in separators)
        explicit = any(re.search(r"\b(?:or|hoặc|hay)\b", part, re.I) for part in separators) or re.match(r"[\s,]*(?:or|hoặc|hay)\s+(?:similar|equivalent|tương đương)\b", tail, re.I)
        return bool(separators and valid and explicit)

    # Recover comma/OR lists too: "Python, Java, C++ or similar" is one unit.
    by_evidence: dict[tuple[str, str], list[RequirementItem]] = {}
    for item in skills:
        by_evidence.setdefault((item.evidence, item.requirement_type), []).append(item)
    for (evidence, kind), items in by_evidence.items():
        positions = []
        for item in items:
            match = re.search(re.escape(item.original_name or item.name), evidence, re.I)
            if match:
                positions.append((match.start(), match.end(), item))
        positions.sort(key=lambda entry: entry[0])
        chain = []
        recovered = []
        def finish_chain():
            if len(chain) >= 2 and alternatives([evidence[left[1]:right[0]] for left, right in zip(chain, chain[1:])], evidence[chain[-1][1]:]):
                candidates.append(RequirementGroup(operator="any", members=[entry[2].name for entry in chain], requirement_type=kind, evidence=evidence))
                recovered.append(list(chain))
        for position in positions:
            if chain:
                separator = evidence[chain[-1][1]:position[0]]
                if not alternative_separator(separator):
                    finish_chain()
                    chain = []
            chain.append(position)
        finish_chain()
        for nested in re.finditer(r"\bor\s+(?:with\s+)?(?:a\s+)?[^.;\n]+?\b(?:such as|like)\b", evidence, re.I):
            left = [position for position in positions if position[1] <= nested.start()]
            right = [position for position in positions if position[0] >= nested.end()]
            if left and right and not any(left[-1] in entries and right[0] in entries for entries in recovered):
                warnings.append("Quan hệ AND/OR có các nhóm ví dụ lồng nhau; cần kiểm tra JD trước khi tính điểm")
    valid = []
    used = set()
    # A recovered outer OR supersedes its redundant example-only subgroups.
    for group in sorted(candidates, key=lambda group: -len(group.members)):
        if normalize_whitespace(group.evidence).casefold() not in normalize_whitespace(requirements.job_description_raw).casefold():
            warnings.append("Nhóm AND/OR không có evidence trong JD; bỏ nhóm, cần review")
            continue
        members = []
        for name in group.members:
            matches = [item for item in skills if normalize_whitespace(name).casefold() in {normalize_whitespace(item.name).casefold(), normalize_whitespace(item.original_name or item.name).casefold()} and item.requirement_type == group.requirement_type]
            if len(matches) == 1:
                members.append(matches[0])
        ids = list(dict.fromkeys(item.id for item in members))
        connector = r"\b(?:and/or|or|hoặc|hay)\b" if group.operator == "any" else r"\b(?:and|và)\b"
        is_choice = group.operator == "any" and ONE_OF.search(group.evidence)
        if len(ids) != len(group.members) or len(ids) < 2 or not (is_choice or re.search(connector, group.evidence, re.I)):
            warnings.append("Nhóm AND/OR chưa rõ hoặc thiếu thành viên; cần review")
            continue
        # Every adjacent member must be connected by the group's own operator.
        positions = sorted((re.search(re.escape(item.original_name or item.name), group.evidence, re.I) for item in members), key=lambda match: match.start() if match else -1)
        connected = False
        if all(match is not None for match in positions):
            separators = [group.evidence[left.end():right.start()] for left, right in zip(positions, positions[1:])]
            connected = alternatives(separators, group.evidence[positions[-1].end():]) if group.operator == "any" else all(re.fullmatch(r"[\s(),]*(?:and|và)[\s(),]*", part, re.I) for part in separators)
        if any(match is None for match in positions) or (not is_choice and not connected):
            warnings.append("Quan hệ AND/OR mơ hồ; cần kiểm tra JD")
            continue
        key = tuple(sorted(ids))
        if key in used:
            continue
        if group.operator == "any" and any(set(ids) <= set(old.requirement_ids) and old.evidence == group.evidence for old in valid if old.operator == "any"):
            continue
        if group.operator == "any" and any(set(ids) & set(old.requirement_ids) for old in valid if old.operator == "any"):
            warnings.append("Các nhóm OR chồng lấn; cần review")
            continue
        group.requirement_ids = ids
        group.id = "group_" + hashlib.sha256((group.operator + "|" + "|".join(sorted(ids))).encode()).hexdigest()[:16]
        valid.append(group)
        used.add(key)
    requirements.requirement_groups = valid
    return warnings


def analyze_job_description(job_description_raw: str) -> tuple[JobRequirements, list[str]]:
    cleaned_text = normalize_whitespace(job_description_raw)
    if len(cleaned_text) < 30:
        raise ValueError("Nội dung JD quá ngắn để phân tích")
    if len(job_description_raw) > 60000:
        raise ValueError("JD vượt giới hạn 60000 ký tự; hãy dán phần mô tả công việc")

    messages = [
        {"role": "system", "content": JD_ANALYSIS_PROMPT},
        {"role": "user", "content": f"Job description:\n\n{job_description_raw}"},
    ]
    try:
        extracted = request_structured(messages, ExtractedJobRequirements, task="jd")
    except OllamaSchemaError:
        # Chỉ thử lại một lần và vẫn bắt model tuân theo cùng một schema.
        messages.append({
            "role": "user",
            "content": "The previous response was invalid. Return only JSON matching the schema.",
        })
        extracted = request_structured(messages, ExtractedJobRequirements, task="jd")
    requirements = JobRequirements(
        **extracted.model_dump(),
        job_description_raw=job_description_raw,
    )
    fill_section_fields(requirements)
    # A nonempty first response can still omit entire preferred/required sections.
    # The existing focused extractor now merges instead of replacing those lists.
    skill_warnings = fill_missing_skills(requirements)
    requirements, warnings = normalize_requirements(requirements)
    fill_core_requirements(requirements)
    assign_requirement_ids(requirements)
    warnings.extend(build_requirement_groups(requirements))
    return requirements, skill_warnings + warnings

