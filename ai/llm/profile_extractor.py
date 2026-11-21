import json
import hashlib
import time
from collections import OrderedDict
from concurrent.futures import Future
from copy import deepcopy
from threading import Lock

from pydantic import BaseModel, ConfigDict, Field, create_model

from ai.llm.ollama_client import OllamaSchemaError, request_structured
from ai.prompts.profile_prompt import PROFILE_EXTRACTION_PROMPT
from backend.app.schemas.profile import MasterProfile
from backend.app.core.config import settings


def _extraction_entry(name, omitted):
    model = MasterProfile.model_fields[name].annotation.__args__[0]
    return create_model('Extract' + model.__name__, __config__=ConfigDict(extra='forbid'), **{
        key: (field.annotation, deepcopy(field))
        for key, field in model.model_fields.items() if key not in omitted
    })


_OMITTED = {
    'experience': {'id', 'original_bullets', 'responsibilities', 'achievements'},
    'project': {'id', 'original_bullets', 'objectives', 'responsibilities', 'contributions', 'outcomes'},
    'education': {'id', 'original_description'},
    'involvement': {'id', 'responsibilities', 'achievements'},
    'skills': {'id', 'normalized_items'},
    'certifications': {'id'}, 'awards': {'id'}, 'references': {'id'},
}
ExtractionProfile = create_model('ExtractionProfile', __config__=ConfigDict(extra='forbid'), **{
    key: ((list[_extraction_entry(key, _OMITTED[key])],
           Field(default_factory=list) if not field.is_required() else ...)
          if key in _OMITTED else (field.annotation, deepcopy(field)))
    for key, field in MasterProfile.model_fields.items()
})
_cache = OrderedDict()
_pending = {}
_cache_lock = Lock()
_CACHE_TTL = 600
_CACHE_ENTRIES = 8


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
    extracted = request_structured(messages, ExtractionProfile, task="profile")
    return MasterProfile.model_validate(extracted.model_dump())


def _extract_profile_with_retry(resume_text: str) -> MasterProfile:
    try:
        return request_profile(resume_text)
    except OllamaSchemaError:
        correction = (
            "The previous response did not match the schema. Return only valid JSON "
            "matching the supplied schema and no extra fields. Omit empty optional fields."
        )
        return request_profile(resume_text, correction)


def extract_profile_with_retry(resume_text: str) -> MasterProfile:
    key = (settings.provider_for_task('profile'), settings.model_for_task('profile'), hashlib.sha256(resume_text.encode()).digest())
    with _cache_lock:
        cached = _cache.get(key)
        if cached and time.monotonic() - cached[0] < _CACHE_TTL:
            _cache.move_to_end(key)
            return MasterProfile.model_validate_json(cached[1])
        pending = _pending.get(key)
        owner = pending is None
        if owner:
            pending = _pending[key] = Future()
    if not owner:
        return MasterProfile.model_validate_json(pending.result())
    try:
        profile = _extract_profile_with_retry(resume_text)
        serialized = profile.model_dump_json()
        with _cache_lock:
            _cache[key] = (time.monotonic(), serialized)
            _cache.move_to_end(key)
            while len(_cache) > _CACHE_ENTRIES:
                _cache.popitem(last=False)
        pending.set_result(serialized)
        return profile
    except BaseException as error:
        pending.set_exception(error)
        raise
    finally:
        with _cache_lock:
            _pending.pop(key, None)


def extract_missing_job_titles(
    resume_text: str,
    missing_experiences: list[dict],
) -> dict[int, str | None]:
    prompt = f"""Extract only the candidate's exact job title for each employment entry.

Copy the job title exactly. It must be the candidate's role at the listed company. Do
not use a section heading, company, degree, project role or desired position. Do not
infer seniority or translate. Return null when no title is explicitly stated.

Employment entries:
{json.dumps(missing_experiences, ensure_ascii=False, separators=(',', ':'))}

Each entry includes its own source excerpt; do not use text from another entry."""
    result = request_structured(
        [{"role": "user", "content": prompt}],
        JobTitleResult,
        task="profile",
        max_output_tokens=768,
    )
    return {item.experience_index: item.job_title for item in result.items}

