"""Session metadata and confirmed-answer ledger, separate from Master Profile facts."""

import hashlib
import os
import re
from pathlib import Path

from backend.app.core.config import PROJECT_ROOT
from backend.app.db import database
from backend.app.db.job_posting_repository import atomic_json

DEFAULT_WORKFLOW_STORAGE = Path(os.environ.get("WORKFLOW_STORAGE_DIR", PROJECT_ROOT / "backend/storage/workflows"))


def safe_key(key: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_:-]{1,240}", key):
        raise ValueError("ID phiên không hợp lệ")
    return key


def get(kind: str, key: str):
    key = safe_key(key)
    if database.enabled():
        return database.get_record(kind, key)
    path = DEFAULT_WORKFLOW_STORAGE / kind / f"{key}.json"
    if not path.exists():
        return None
    import json
    return json.loads(path.read_text(encoding="utf-8"))


def put(kind: str, key: str, data: dict):
    key = safe_key(key)
    if database.enabled():
        return database.put_record(kind, key, data)
    atomic_json(DEFAULT_WORKFLOW_STORAGE / kind / f"{key}.json", data)
    return data


def signature(target: dict) -> str:
    # Semantic requirement identity, independent of the analysis-generated ID.
    names = target.get("skill_options") or [target["label"]]
    return hashlib.sha256("|".join(sorted(name.strip().casefold() for name in names)).encode()).hexdigest()[:24]


def answer_key(root_id: str, target: dict) -> str:
    return safe_key(root_id) + ":" + signature(target)


def answer_for(root_id: str, target: dict):
    return get("answers", answer_key(root_id, target))
