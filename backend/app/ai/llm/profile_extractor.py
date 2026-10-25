import json

from pydantic import BaseModel, ConfigDict

from backend.app.ai.llm.ollama_client import OllamaSchemaError, request_structured
from backend.app.ai.prompts.profile_prompt import PROFILE_EXTRACTION_PROMPT
from backend.app.schemas.profile import MasterProfile


class JobTitleItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    experience_index: int
    job_title: str | None


class JobTitleResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[JobTitleItem]


def request_profile(resume_text: str, correction: str | None = None) -> MasterProfile:
    messages = [
        {"role": "system", "content": PROFILE_EXTRACTION_PROMPT},
        {"role": "user", "content": f"Extract this resume:\n\n{resume_text}"},
    ]
    if correction:
        messages.append({"role": "user", "content": correction})
    return request_structured(messages, MasterProfile, task="profile")


def extract_profile_with_retry(resume_text: str) -> MasterProfile:
    try:
        return request_profile(resume_text)
    except OllamaSchemaError:
        correction = (
            "The previous response did not match the schema. Return only valid JSON "
            "with all seven top-level fields and no extra fields."
        )
        return request_profile(resume_text, correction)


def extract_missing_job_titles(
    resume_text: str,
    missing_experiences: list[dict],
) -> dict[int, str | None]:
    prompt = f"""Extract only the candidate's exact job title for each employment entry.

Copy the job title exactly. It must be the candidate's role at the listed company. Do
not use a section heading, company, degree, project role or desired position. Do not
infer seniority or translate. Return null when no title is explicitly stated.

Employment entries:
{json.dumps(missing_experiences, ensure_ascii=False, indent=2)}

Resume:
{resume_text}"""
    result = request_structured(
        [{"role": "user", "content": prompt}],
        JobTitleResult,
        task="profile",
    )
    return {item.experience_index: item.job_title for item in result.items}

