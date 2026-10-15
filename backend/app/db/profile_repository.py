import json
import re
from pathlib import Path

from backend.app.schemas.profile import MasterProfile


DEFAULT_STORAGE_DIR = Path("backend/storage/master_profiles")


def _safe_thread_id(thread_id: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_-]+", thread_id):
        raise ValueError("thread_id không hợp lệ")
    return thread_id


def save_master_profile(
    thread_id: str,
    profile: MasterProfile,
    storage_dir: Path = DEFAULT_STORAGE_DIR,
) -> None:
    safe_id = _safe_thread_id(thread_id)
    storage_dir.mkdir(parents=True, exist_ok=True)
    path = storage_dir / f"{safe_id}.json"
    path.write_text(profile.model_dump_json(indent=2), encoding="utf-8")


def load_master_profile(
    thread_id: str,
    storage_dir: Path = DEFAULT_STORAGE_DIR,
) -> MasterProfile | None:
    safe_id = _safe_thread_id(thread_id)
    path = storage_dir / f"{safe_id}.json"
    if not path.exists():
        return None
    return MasterProfile.model_validate(json.loads(path.read_text(encoding="utf-8")))

