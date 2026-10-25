import json
import re
import os
import tempfile
from collections.abc import Sequence
from pathlib import Path

from backend.app.core.config import settings
from backend.app.db import database
from backend.app.schemas.profile import MasterProfile, SourceEvidence, StoredProfile


DEFAULT_STORAGE_DIR = settings.profile_storage_dir


def _safe_thread_id(thread_id: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_-]+", thread_id):
        raise ValueError("thread_id không hợp lệ")
    return thread_id


def save_master_profile(
    thread_id: str,
    profile: MasterProfile,
    storage_dir: Path = DEFAULT_STORAGE_DIR,
    *,
    evidence: Sequence[dict | SourceEvidence] = (),
    warnings: Sequence[str] = (),
    source_text: str | None = None,
    source_filename: str | None = None,
    root_profile_id: str | None = None,
    parent_profile_id: str | None = None,
) -> None:
    safe_id = _safe_thread_id(thread_id)
    record = StoredProfile(profile=profile, evidence=list(evidence), warnings=list(warnings), source_text=source_text, source_filename=source_filename,
                           root_profile_id=root_profile_id, parent_profile_id=parent_profile_id)
    if database.enabled():
        with database.connect() as connection, connection.transaction():
            connection.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (safe_id,))
            if connection.execute("SELECT 1 FROM kltn_app.records WHERE kind='profiles' AND record_id=%s", (safe_id,)).fetchone():
                raise ValueError("Profile đã tồn tại; không ghi đè hồ sơ đã xác nhận")
            database.put_record("profiles", safe_id, record.model_dump(mode="json"), immutable=True, connection=connection)
            connection.execute("INSERT INTO kltn_app.profile_heads(root_id,revision_id) VALUES (%s,%s) ON CONFLICT DO NOTHING", (root_profile_id or safe_id, safe_id))
            connection.execute("INSERT INTO kltn_app.profile_revisions(revision_id,root_id,parent_id) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING", (safe_id, root_profile_id or safe_id, parent_profile_id))
        return
    storage_dir.mkdir(parents=True, exist_ok=True)
    path = storage_dir / f"{safe_id}.json"
    content = record.model_dump_json(indent=2)
    # Atomic publication with no overwrite, even if another confirmation races.
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=storage_dir, prefix=".profile-", delete=False) as stream:
            temporary_path = Path(stream.name)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary_path, path)
    except FileExistsError as error:
        raise ValueError("Profile đã tồn tại; không ghi đè hồ sơ đã xác nhận") from error
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def load_profile_record(thread_id: str, storage_dir: Path = DEFAULT_STORAGE_DIR) -> StoredProfile | None:
    if database.enabled():
        data = database.get_record("profiles", _safe_thread_id(thread_id))
        if data is not None:
            return StoredProfile.model_validate(data)
    path = storage_dir / f"{_safe_thread_id(thread_id)}.json"
    if not path.exists():
        return None
    record = json.loads(path.read_text(encoding="utf-8"))
    if "profile" not in record:
        # Legacy seven-group JSON files stay untouched on disk.
        return StoredProfile(profile=MasterProfile.model_validate(record))
    return StoredProfile.model_validate(record)


def list_profile_records() -> list[tuple[str, StoredProfile]]:
    records = {}
    for path in sorted(DEFAULT_STORAGE_DIR.glob("*.json"), key=lambda item: item.stat().st_mtime):
        try:
            record = load_profile_record(path.stem, DEFAULT_STORAGE_DIR)
            if record:
                records[path.stem] = record
        except (ValueError, OSError, KeyError):
            continue
    if database.enabled():
        for item in reversed(database.list_records("profiles")):
            records[item["id"]] = StoredProfile.model_validate(item["data"])
    return list(reversed(list(records.items())))


def load_master_profile(
    thread_id: str,
    storage_dir: Path = DEFAULT_STORAGE_DIR,
) -> MasterProfile | None:
    record = load_profile_record(thread_id, storage_dir)
    return record.profile if record else None

