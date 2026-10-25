"""Opt-in, idempotent JSON -> PostgreSQL import. Files are never altered or removed."""

import hashlib
import json

from backend.app.db import database, profile_repository, job_repository, match_repository
from backend.app.db.job_posting_repository import storage_root
from backend.app.schemas.profile import MasterProfile, StoredProfile
from backend.app.schemas.dashboard import JobPosting
from backend.app.schemas.matching import MatchResponse


def import_legacy():
    if not database.enabled():
        raise ValueError("Set KLTN_STORAGE=postgres explicitly before importing")
    sources = []
    for kind, root, pattern in (("profiles", profile_repository.DEFAULT_STORAGE_DIR, "*.json"),
                                 ("analyses", job_repository.DEFAULT_JOB_STORAGE, "*.json"),
                                 ("matches", match_repository.DEFAULT_MATCH_STORAGE, "match_*.json"),
                                 ("postings", storage_root(), "posting_*.json"),
                                 ("analysis_cache", storage_root() / "analyses", "*.json")):
        sources.extend((kind, path.stem, path) for path in root.glob(pattern))
    if (storage_root() / "sync.json").exists():
        sources.append(("feed_state", "current", storage_root() / "sync.json"))
    counts = {"inserted": 0, "existing": 0, "invalid": 0}
    for kind, key, path in sources:
        original = path.read_bytes()
        digest = hashlib.sha256(original).digest()
        try:
            data = json.loads(original)
            if kind == "profiles":
                record = StoredProfile.model_validate(data) if "profile" in data else StoredProfile(profile=MasterProfile.model_validate(data))
                data = record.model_dump(mode="json")
            elif kind == "postings":
                JobPosting.model_validate(data)
            elif kind == "matches":
                MatchResponse.model_validate(data)
            elif kind == "analyses":
                if not isinstance(data.get("job_requirements"), dict) or not data.get("job_description_raw"):
                    raise ValueError("Invalid legacy analysis")
            elif kind == "analysis_cache":
                if not isinstance(data.get("job_id"), str):
                    raise ValueError("Invalid analysis cache")
        except (ValueError, TypeError, KeyError):
            counts["invalid"] += 1
            continue
        with database.connect() as connection, connection.transaction():
            existing = connection.execute("SELECT 1 FROM kltn_app.records WHERE kind=%s AND record_id=%s", (kind, key)).fetchone()
            database.put_record(kind, key, data, immutable=True, connection=connection)
            counts["existing" if existing else "inserted"] += 1
            if kind == "profiles":
                root = record.root_profile_id or key
                connection.execute("INSERT INTO kltn_app.profile_revisions(revision_id,root_id,parent_id) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING", (key, root, record.parent_profile_id))
                connection.execute("INSERT INTO kltn_app.profile_heads(root_id,revision_id) VALUES (%s,%s) ON CONFLICT DO NOTHING", (root, root))
        if hashlib.sha256(path.read_bytes()).digest() != digest:
            raise RuntimeError("Legacy file changed concurrently; import stopped without overwriting it")
    return counts


if __name__ == "__main__":
    print(json.dumps(import_legacy()))
