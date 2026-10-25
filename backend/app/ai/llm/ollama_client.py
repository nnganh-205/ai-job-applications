import json
import logging
import time
from contextlib import contextmanager
from contextvars import ContextVar
from typing import TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from backend.app.core.config import LLMTask, settings


OLLAMA_URL = f"{settings.ollama_base_url}/api/chat"
MODEL_NAME = settings.default_model
TIMEOUT_SECONDS = settings.timeout_seconds
CONTEXT_LENGTH = settings.context_length
logger = logging.getLogger(__name__)
ResponseModel = TypeVar("ResponseModel", bound=BaseModel)
_deadline = ContextVar("llm_deadline", default=None)


@contextmanager
def llm_deadline(seconds: float):
    """A shared budget for a selected-job analysis, without changing Profile calls."""
    token = _deadline.set(time.monotonic() + seconds)
    try:
        yield
    finally:
        _deadline.reset(token)


class OllamaError(RuntimeError):
    """Lỗi chung khi gọi Ollama."""


class OllamaConnectionError(OllamaError):
    pass


class OllamaTimeoutError(OllamaError):
    pass


class OllamaResponseError(OllamaError):
    pass


class OllamaSchemaError(OllamaResponseError):
    pass


def clean_null_strings(value):
    """Đổi chuỗi null do model sinh sai thành giá trị JSON null."""
    if isinstance(value, str) and value.strip().casefold() in {"null", "none", "n/a"}:
        return None
    if isinstance(value, list):
        return [clean_null_strings(item) for item in value]
    if isinstance(value, dict):
        return {key: clean_null_strings(item) for key, item in value.items()}
    return value


def request_structured(
    messages: list[dict[str, str]],
    response_model: type[ResponseModel],
    *,
    task: LLMTask = "default",
) -> ResponseModel:
    model_name = MODEL_NAME if task == "default" else settings.model_for_task(task)
    payload = {
        "model": model_name,
        "messages": messages,
        "format": response_model.model_json_schema(),
        "stream": False,
        "think": False,
        "keep_alive": "10m",
        "options": {"temperature": 0, "num_ctx": CONTEXT_LENGTH},
    }
    started = time.perf_counter()
    deadline = _deadline.get()
    timeout = min(TIMEOUT_SECONDS, deadline - time.monotonic()) if deadline else TIMEOUT_SECONDS
    if timeout <= 0:
        raise OllamaTimeoutError("Hết thời gian phân tích JD; vui lòng thử lại.")
    try:
        response = httpx.post(OLLAMA_URL, json=payload, timeout=timeout, trust_env=False)
        response.raise_for_status()
    except httpx.ConnectError as error:
        raise OllamaConnectionError(
            "Không kết nối được Ollama. Hãy kiểm tra `ollama serve` và model đã cấu hình."
        ) from error
    except httpx.TimeoutException as error:
        raise OllamaTimeoutError(
            f"Ollama đã kết nối nhưng xử lý quá {timeout:g} giây."
        ) from error
    except httpx.HTTPStatusError as error:
        raise OllamaResponseError(
            f"Ollama trả về lỗi HTTP {error.response.status_code}."
        ) from error
    except httpx.RequestError as error:
        raise OllamaConnectionError("Lỗi khi gọi Ollama") from error
    finally:
        logger.info("llm_request task=%s model=%s seconds=%.3f", task, model_name, time.perf_counter() - started)

    try:
        content = response.json()["message"]["content"]
        parsed_content = clean_null_strings(json.loads(content))
        return response_model.model_validate(parsed_content)
    except (KeyError, TypeError, json.JSONDecodeError, ValidationError) as error:
        # ValidationError can contain source CV/PII; do not expose it via API/logs.
        raise OllamaSchemaError("Ollama trả về JSON sai schema; vui lòng thử lại hoặc kiểm tra model.") from error

