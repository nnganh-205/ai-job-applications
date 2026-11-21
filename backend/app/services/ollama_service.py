"""Compatibility exports for the shared profile extraction client."""
from ai.llm.ollama_client import OllamaError, OLLAMA_URL, MODEL_NAME, TIMEOUT_SECONDS
from ai.llm.profile_extractor import request_profile, extract_profile_with_retry
from ai.prompts.profile_prompt import PROFILE_EXTRACTION_PROMPT as SYSTEM_PROMPT

__all__ = [
    "OllamaError", "OLLAMA_URL", "MODEL_NAME", "TIMEOUT_SECONDS", "SYSTEM_PROMPT",
    "request_profile", "extract_profile_with_retry",
]
