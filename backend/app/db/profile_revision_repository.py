"""Immutable confirmed revisions with compare-and-set of the current root head."""

import hashlib
from threading import RLock

from backend.app.db import database, profile_repository, workflow_repository as records
from backend.app.db.job_posting_repository import utc_now
from backend.app.schemas.profile import MasterProfile, SourceEvidence, StoredProfile

_revision_lock = RLock()


class RevisionConflict(ValueError):
    pass


def root_id(profile_id: str) -> str:
    record = profile_repository.load_profile_record(profile_id, profile_repository.DEFAULT_STORAGE_DIR)
    if record is None:
        raise LookupError("Master Profile chưa xác nhận hoặc không tồn tại")
    return record.root_profile_id or profile_id


def current_revision(profile_id: str) -> str:
    root = root_id(profile_id)
    if database.enabled():
        with database.connect() as connection:
            row = connection.execute("SELECT revision_id FROM kltn_app.profile_heads WHERE root_id=%s", (root,)).fetchone()
        return row["revision_id"] if row else root
    return (records.get("heads", root) or {}).get("revision_id", root)


def commit_revision(base_id: str, profile: MasterProfile, *, session_id: str, action_id: str,
                    changed_paths: list[str], quote: str) -> str:
    base = profile_repository.load_profile_record(base_id, profile_repository.DEFAULT_STORAGE_DIR)
    if base is None:
        raise LookupError("Hồ sơ gốc không tồn tại")
    root = base.root_profile_id or base_id
    revision = "rev_" + hashlib.sha256(f"{session_id}|{action_id}|{profile.model_dump_json()}".encode()).hexdigest()[:24]
    evidence = list(base.evidence)
    evidence.extend(SourceEvidence(field_path=path, source_id=session_id, origin="user_confirmation", quote=quote) for path in changed_paths)
    record = StoredProfile(profile=profile, evidence=evidence, warnings=base.warnings,
                           source_text=base.source_text, source_filename=base.source_filename,
                           root_profile_id=root, parent_profile_id=base_id)
    metadata = dict(profile_id=revision, root_profile_id=root, parent_profile_id=base_id,
                    session_id=session_id, created_at=utc_now(), changed_paths=changed_paths)
    if database.enabled():
        from psycopg.types.json import Jsonb
        with database.connect() as connection, connection.transaction():
            connection.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (root,))
            existing = connection.execute("SELECT 1 FROM kltn_app.profile_revisions WHERE revision_id=%s", (revision,)).fetchone()
            if existing:
                return revision
            connection.execute("INSERT INTO kltn_app.profile_heads(root_id,revision_id) VALUES (%s,%s) ON CONFLICT DO NOTHING", (root, root))
            head = connection.execute("SELECT revision_id FROM kltn_app.profile_heads WHERE root_id=%s FOR UPDATE", (root,)).fetchone()
            if head["revision_id"] != base_id:
                raise RevisionConflict("Hồ sơ đã được cập nhật ở phiên khác. Tải revision mới trước khi tiếp tục.")
            database.put_record("profiles", revision, record.model_dump(mode="json"), immutable=True, connection=connection)
            connection.execute("INSERT INTO kltn_app.profile_revisions(revision_id,root_id,parent_id,session_id,changed_paths) VALUES (%s,%s,%s,%s,%s)",
                               (revision, root, base_id, session_id, Jsonb(changed_paths)))
            connection.execute("UPDATE kltn_app.profile_heads SET revision_id=%s WHERE root_id=%s", (revision, root))
        return revision
    with _revision_lock:
        existing = records.get("revisions", revision)
        if existing:
            return revision
        if current_revision(base_id) != base_id:
            raise RevisionConflict("Hồ sơ đã có revision mới; tải lại trước khi cập nhật")
        profile_repository.save_master_profile(revision, profile, profile_repository.DEFAULT_STORAGE_DIR,
                                               evidence=evidence, warnings=base.warnings,
                                               source_text=base.source_text, source_filename=base.source_filename,
                                               root_profile_id=root, parent_profile_id=base_id)
        records.put("revisions", revision, metadata)
        records.put("heads", root, {"revision_id": revision})
    return revision


def history(profile_id: str) -> list[dict]:
    root = root_id(profile_id)
    if database.enabled():
        with database.connect() as connection:
            rows = connection.execute("SELECT revision_id AS profile_id,root_id AS root_profile_id,parent_id AS parent_profile_id,session_id,created_at,changed_paths FROM kltn_app.profile_revisions WHERE root_id=%s ORDER BY created_at", (root,)).fetchall()
        return [{**row, "created_at": row["created_at"].isoformat()} for row in rows]
    import json
    rows = [json.loads(path.read_text()) for path in (records.DEFAULT_WORKFLOW_STORAGE / "revisions").glob("*.json")]
    return sorted([row for row in rows if row["root_profile_id"] == root], key=lambda row: row["created_at"])
