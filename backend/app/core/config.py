"""Configuration from process environment; never reads or rewrites .env files."""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit


PROJECT_ROOT = Path(__file__).resolve().parents[3]
LLMTask = Literal["default", "profile", "jd", "update", "cv", "form", "interview", "assistant", "writer", "verifier"]


@dataclass(frozen=True)
class Settings:
    ollama_base_url: str = "http://127.0.0.1:11434"
    default_model: str = "qwen3:4b"
    profile_model: str = "qwen3:4b"
    jd_model: str = "qwen3:4b"
    update_model: str = "qwen3:4b"
    cv_model: str = "qwen3:4b"
    writer_model: str | None = "kltn-writer-8b-unsloth:latest"
    form_model: str = "qwen3:4b"
    interview_model: str = "qwen3:4b"
    assistant_model: str = "qwen3:4b"
    verifier_model: str = "qwen3:8b"
    embedding_model: str = "bge-m3"
    timeout_seconds: float = 600
    context_length: int = 16_384
    profile_storage_dir: Path = PROJECT_ROOT / "backend/storage/master_profiles"

    def model_for_task(self, task: LLMTask) -> str:
        if task not in {"default", "profile", "jd", "update", "cv", "form", "interview", "assistant", "writer", "verifier"}:
            raise ValueError("Unknown LLM task")
        if task == "writer": return self.writer_model or self.cv_model
        return self.default_model if task == "default" else getattr(self, f"{task}_model")

    @classmethod
    def from_environment(cls) -> "Settings":
        base_url = os.getenv("OLLAMA_BASE_URL", cls.ollama_base_url).rstrip("/")
        parsed = urlsplit(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("OLLAMA_BASE_URL must be an HTTP(S) URL without credentials")
        model = os.getenv("LLM_MODEL", cls.default_model)
        timeout = float(os.getenv("LLM_TIMEOUT_SECONDS", "600"))
        context = int(os.getenv("LLM_CONTEXT_LENGTH", "16384"))
        if timeout <= 0 or context < 512:
            raise ValueError("LLM timeout must be positive and context must be at least 512")
        storage = Path(os.getenv("PROFILE_STORAGE_DIR", str(cls.profile_storage_dir)))
        return cls(
            ollama_base_url=base_url,
            default_model=model,
            profile_model=os.getenv("PROFILE_MODEL", model),
            jd_model=os.getenv("JD_MODEL", model),
            update_model=os.getenv("UPDATE_MODEL", model),
            cv_model=os.getenv("CV_MODEL", model),
            writer_model=os.getenv("WRITER_MODEL", cls.writer_model) or None,
            form_model=os.getenv("FORM_CV_MODEL", os.getenv("CV_MODEL", model)),
            interview_model=os.getenv("INTERVIEW_MODEL", model),
            assistant_model=os.getenv("ASSISTANT_MODEL", model),
            verifier_model=os.getenv("VERIFIER_MODEL", cls.verifier_model),
            embedding_model=os.getenv("EMBEDDING_MODEL", cls.embedding_model),
            timeout_seconds=timeout,
            context_length=context,
            profile_storage_dir=storage if storage.is_absolute() else PROJECT_ROOT / storage,
        )


settings = Settings.from_environment()
