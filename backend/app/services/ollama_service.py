import json

import httpx
from pydantic import ValidationError

from backend.app.schemas.profile import MasterProfile


OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL_NAME = "qwen3:4b"
TIMEOUT_SECONDS = 120

SYSTEM_PROMPT = """You are an information extraction assistant. Extract only factual
information explicitly present in the provided resume. Preserve wording, names, dates,
responsibilities and achievements. Do not optimize, rewrite, summarize, infer,
exaggerate or invent information. Return structured JSON that follows the schema.
Missing information must be null or empty.

Classify employment only as experience, named work or academic products as project,
and clubs, volunteering or student organizations as involvement. Keep an existing
resume summary unchanged; return null when the resume has no summary. Include a skill
only when the resume explicitly states it. Do not infer skills from job titles or
responsibilities. Keep education dates separate from employment dates."""


class OllamaError(RuntimeError):
    """Lỗi kết nối hoặc phản hồi từ Ollama."""


def request_profile(resume_text: str, correction: str | None = None) -> MasterProfile:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Extract this resume:\n\n{resume_text}"},
    ]
    if correction:
        messages.append({"role": "user", "content": correction})

    payload = {
        "model": MODEL_NAME,
        "messages": messages,
        "format": MasterProfile.model_json_schema(),
        "stream": False,
        "think": False,
        "options": {"temperature": 0},
    }
    try:
        response = httpx.post(OLLAMA_URL, json=payload, timeout=TIMEOUT_SECONDS)
        response.raise_for_status()
    except httpx.RequestError as error:
        raise OllamaError(
            "Không kết nối được Ollama. Hãy chạy `ollama serve` và cài qwen3:4b."
        ) from error
    except httpx.HTTPStatusError as error:
        raise OllamaError(f"Ollama trả về lỗi HTTP {error.response.status_code}") from error

    try:
        content = response.json()["message"]["content"]
        return MasterProfile.model_validate(json.loads(content))
    except (KeyError, TypeError, json.JSONDecodeError, ValidationError) as error:
        raise OllamaError(f"Ollama trả về JSON sai schema: {error}") from error


def extract_profile_with_retry(resume_text: str) -> MasterProfile:
    try:
        return request_profile(resume_text)
    except OllamaError as first_error:
        if "JSON sai schema" not in str(first_error):
            raise
        correction = (
            "Your previous response did not match the JSON schema. Return only valid "
            "JSON with all seven top-level fields and no extra fields."
        )
        return request_profile(resume_text, correction)


