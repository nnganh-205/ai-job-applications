import json

import httpx
from pydantic import BaseModel, ValidationError


OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL_NAME = "qwen3:4b"
TIMEOUT_SECONDS = 600
CONTEXT_LENGTH = 16_384


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
    response_model: type[BaseModel],
) -> BaseModel:
    payload = {
        "model": MODEL_NAME,
        "messages": messages,
        "format": response_model.model_json_schema(),
        "stream": False,
        "think": False,
        "keep_alive": "10m",
        "options": {"temperature": 0, "num_ctx": CONTEXT_LENGTH},
    }
    try:
        response = httpx.post(OLLAMA_URL, json=payload, timeout=TIMEOUT_SECONDS)
        response.raise_for_status()
    except httpx.ConnectError as error:
        raise OllamaConnectionError(
            "Không kết nối được Ollama. Hãy chạy `ollama serve` và cài qwen3:4b."
        ) from error
    except httpx.TimeoutException as error:
        raise OllamaTimeoutError(
            "Ollama đã kết nối nhưng xử lý quá 600 giây."
        ) from error
    except httpx.HTTPStatusError as error:
        raise OllamaResponseError(
            f"Ollama trả về lỗi HTTP {error.response.status_code}."
        ) from error
    except httpx.RequestError as error:
        raise OllamaConnectionError(f"Lỗi khi gọi Ollama: {error}") from error

    try:
        content = response.json()["message"]["content"]
        parsed_content = clean_null_strings(json.loads(content))
        return response_model.model_validate(parsed_content)
    except (KeyError, TypeError, json.JSONDecodeError, ValidationError) as error:
        raise OllamaSchemaError(f"Ollama trả về JSON sai schema: {error}") from error

