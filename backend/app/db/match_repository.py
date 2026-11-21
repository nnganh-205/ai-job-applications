from backend.app.core.workspace import storage_path
import re
import os
import tempfile
from pathlib import Path

from backend.app.core.config import PROJECT_ROOT
from backend.app.schemas.matching import MatchResponse
from backend.app.db import database


DEFAULT_MATCH_STORAGE = Path(os.environ.get("MATCH_STORAGE_DIR", PROJECT_ROOT / "backend/storage/matches"))


def load_match(result_id: str, storage_dir: Path = DEFAULT_MATCH_STORAGE) -> MatchResponse | None:
    storage_dir = storage_path(storage_dir)
    if not re.fullmatch(r"match_[a-f0-9]{24}", result_id):
        raise ValueError("result_id không hợp lệ")
    if database.enabled():
        data = database.get_record("matches", result_id)
        return MatchResponse.model_validate(data) if data is not None else None
    path = storage_dir / f"{result_id}.json"
    return MatchResponse.model_validate_json(path.read_text(encoding="utf-8")) if path.exists() else None


def save_match(result: MatchResponse, storage_dir: Path = DEFAULT_MATCH_STORAGE) -> MatchResponse:
    storage_dir = storage_path(storage_dir)
    if database.enabled():
        database.put_record("matches", result.result_id, result.model_dump(mode="json"), immutable=True)
        return load_match(result.result_id, storage_dir)
    storage_dir.mkdir(parents=True, exist_ok=True)
    path = storage_dir / f"{result.result_id}.json"
    # Content-addressed result: repeat requests read the existing immutable result.
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=storage_dir, prefix=".match-", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(result.model_dump_json(indent=2))
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)
    except FileExistsError:
        existing = load_match(result.result_id, storage_dir)
        if existing is None:
            raise ValueError("Không đọc được kết quả đã lưu")
        return existing
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return result
