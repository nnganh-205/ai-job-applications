"""Load project .env defaults without overriding exported process variables."""

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, get_args
from urllib.parse import urlsplit
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(Path(os.environ.get('KLTN_ENV_FILE', str(PROJECT_ROOT / '.env'))), override=False)
LLMTask = Literal["default", "profile", "jd", "update", "cv", "form", "interview", "assistant", "writer", "verifier", "refine"]

LEGACY_MODELS = {
    "qwen3:4b", "kltn-writer-v6:candidate", "kltn-editor-qwen3-v3:candidate",
    "kltn-form-qwen3-v2:latest", "kltn-form-qwen3-v2:candidate",
}


def generation_model(value: str) -> str:
    return "qwen3:8b" if value in LEGACY_MODELS else value


@dataclass(frozen=True)
class Settings:
    ollama_base_url: str = "http://127.0.0.1:11434"
    default_model: str = "qwen3:8b"
    profile_model: str = "qwen3:8b"
    jd_model: str = "qwen3:8b"
    update_model: str = "qwen3:8b"
    cv_model: str = "qwen3:8b"
    writer_model: str | None = "kltn-writer-8b-unsloth:latest"
    form_model: str = "qwen3:8b"
    interview_model: str = "qwen3:8b"
    assistant_model: str = "qwen3:8b"
    verifier_model: str = "qwen3:8b"
    refine_model: str | None = None
    embedding_model: str = "bge-m3"
    timeout_seconds: float = 600
    context_length: int = 16_384
    profile_storage_dir: Path = PROJECT_ROOT / "backend/storage/master_profiles"
    groq_api_key: str | None = field(default=None, repr=False)
    groq_model: str = 'openai/gpt-oss-120b'
    groq_assistant_model: str | None = None
    groq_profile_model: str | None = None
    groq_update_model: str | None = None
    groq_tasks: tuple[str, ...] = ()
    groq_timeout_seconds: float = 120
    cloudflare_account_id: str | None = field(default=None, repr=False)
    cloudflare_api_token: str | None = field(default=None, repr=False)
    cloudflare_model: str = '@cf/openai/gpt-oss-20b'
    cloudflare_cv_model: str | None = None
    cloudflare_tasks: tuple[str, ...] = ()
    cloudflare_timeout_seconds: float = 120
    cloudflare_max_output_tokens: int = 2048

    def provider_for_task(self, task: LLMTask) -> str:
        if task not in get_args(LLMTask): raise ValueError('Unknown LLM task')
        if task in self.cloudflare_tasks:return 'cloudflare'
        return 'groq' if task in self.groq_tasks else 'ollama'

    def model_for_task(self, task: LLMTask) -> str:
        if self.provider_for_task(task) == 'groq':
            if task == 'assistant': return self.groq_assistant_model or self.groq_model
            if task == 'profile': return self.groq_profile_model or self.groq_model
            if task == 'update': return self.groq_update_model or self.groq_assistant_model or self.groq_model
            return self.groq_model
        if self.provider_for_task(task) == 'cloudflare':
            return (self.cloudflare_cv_model or self.cloudflare_model) if task == 'cv' else self.cloudflare_model
        if task not in get_args(LLMTask):
            raise ValueError("Unknown LLM task")
        if task == "writer": return generation_model(self.writer_model or self.cv_model)
        if task == "refine": return generation_model(self.refine_model or self.writer_model or self.cv_model)
        return generation_model(self.default_model if task == "default" else getattr(self, f"{task}_model"))

    def identity_for_task(self, task: LLMTask) -> str:
        return self.provider_for_task(task)+':'+self.model_for_task(task)

    @classmethod
    def from_environment(cls) -> "Settings":
        base_url = os.getenv("OLLAMA_BASE_URL", cls.ollama_base_url).rstrip("/")
        parsed = urlsplit(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("OLLAMA_BASE_URL must be an HTTP(S) URL without credentials")
        model = generation_model(os.getenv("LLM_MODEL", cls.default_model))
        timeout = float(os.getenv("LLM_TIMEOUT_SECONDS", "600"))
        context = int(os.getenv("LLM_CONTEXT_LENGTH", "16384"))
        if timeout <= 0 or context < 512:
            raise ValueError("LLM timeout must be positive and context must be at least 512")
        storage = Path(os.getenv("PROFILE_STORAGE_DIR", str(cls.profile_storage_dir)))
        groq_tasks = tuple(dict.fromkeys(value.strip() for value in os.getenv('GROQ_TASKS', '').split(',') if value.strip()))
        if set(groq_tasks) - set(get_args(LLMTask)):
            raise ValueError('GROQ_TASKS chứa tác vụ không hợp lệ')
        groq_key = os.getenv('GROQ_API_KEY', '').strip() or None
        if groq_tasks and not groq_key:
            raise ValueError('Cần cấu hình GROQ_API_KEY khi bật GROQ_TASKS')
        groq_model = os.getenv('GROQ_MODEL', cls.groq_model).strip()
        groq_timeout = float(os.getenv('GROQ_TIMEOUT_SECONDS', '120'))
        if not groq_model or groq_timeout <= 0:
            raise ValueError('GROQ_MODEL phải có tên model và GROQ_TIMEOUT_SECONDS phải dương')
        cf_tasks=tuple(dict.fromkeys(v.strip() for v in os.getenv('CLOUDFLARE_TASKS','').split(',') if v.strip()))
        if set(cf_tasks)-set(get_args(LLMTask)):raise ValueError('CLOUDFLARE_TASKS chứa tác vụ không hợp lệ')
        if set(cf_tasks)&set(groq_tasks):raise ValueError('Một tác vụ không thể được cấu hình đồng thời ở GROQ_TASKS và CLOUDFLARE_TASKS')
        if set(cf_tasks)&{'writer','refine'}:raise ValueError('Giữ writer và refine trên model Qwen8B fine-tune, không đưa vào CLOUDFLARE_TASKS')
        cf_account=os.getenv('CLOUDFLARE_ACCOUNT_ID','').strip() or None
        cf_token=os.getenv('CLOUDFLARE_API_TOKEN','').strip() or None
        if cf_tasks and (not cf_account or not cf_token):raise ValueError('Cần CLOUDFLARE_ACCOUNT_ID và CLOUDFLARE_API_TOKEN khi bật CLOUDFLARE_TASKS')
        if cf_account and not re.fullmatch(r'[a-fA-F0-9]{32}',cf_account):raise ValueError('CLOUDFLARE_ACCOUNT_ID phải là Account ID gồm 32 ký tự hex')
        cf_model=os.getenv('CLOUDFLARE_MODEL',cls.cloudflare_model).strip()
        cf_cv_model=os.getenv('CLOUDFLARE_CV_MODEL','').strip() or None
        for value in [cf_model]+([cf_cv_model] if cf_cv_model else []):
            if not re.fullmatch(r'@(?:cf|hf)/[\w.-]+/[\w.:-]+',value):raise ValueError('Tên model Cloudflare phải có dạng @cf/nhà-cung-cấp/tên-model')
        cf_timeout=float(os.getenv('CLOUDFLARE_TIMEOUT_SECONDS','120'))
        cf_max_output=int(os.getenv('CLOUDFLARE_MAX_OUTPUT_TOKENS','2048'))
        if cf_timeout<=0 or not 128<=cf_max_output<=8192:raise ValueError('Cloudflare cần timeout dương và giới hạn đầu ra từ 128 đến 8192 token')
        return cls(
            ollama_base_url=base_url,
            default_model=model,
            profile_model=generation_model(os.getenv("PROFILE_MODEL", model)),
            jd_model=generation_model(os.getenv("JD_MODEL", model)),
            update_model=generation_model(os.getenv("UPDATE_MODEL", model)),
            cv_model=generation_model(os.getenv("CV_MODEL", model)),
            writer_model=generation_model(os.getenv("WRITER_MODEL", cls.writer_model)) or None,
            form_model=generation_model(os.getenv("FORM_CV_MODEL", os.getenv("CV_MODEL", model))),
            interview_model=generation_model(os.getenv("INTERVIEW_MODEL", model)),
            assistant_model=generation_model(os.getenv("ASSISTANT_MODEL", model)),
            verifier_model=generation_model(os.getenv("VERIFIER_MODEL", cls.verifier_model)),
            refine_model=os.getenv("REFINE_MODEL", '').strip() or None,
            embedding_model=os.getenv("EMBEDDING_MODEL", cls.embedding_model),
            timeout_seconds=timeout,
            context_length=context,
            profile_storage_dir=storage if storage.is_absolute() else PROJECT_ROOT / storage,
            groq_api_key=groq_key, groq_model=groq_model, groq_tasks=groq_tasks,
            groq_assistant_model=os.getenv('GROQ_ASSISTANT_MODEL', '').strip() or None,
            groq_profile_model=os.getenv('GROQ_PROFILE_MODEL', '').strip() or None,
            groq_update_model=os.getenv('GROQ_UPDATE_MODEL', '').strip() or None,
            groq_timeout_seconds=groq_timeout,
            cloudflare_account_id=cf_account,cloudflare_api_token=cf_token,
            cloudflare_model=cf_model,cloudflare_cv_model=cf_cv_model,cloudflare_tasks=cf_tasks,
            cloudflare_timeout_seconds=cf_timeout,cloudflare_max_output_tokens=cf_max_output,
        )


settings = Settings.from_environment()
