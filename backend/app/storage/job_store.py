import json
import re
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from backend.app.schemas.job import JobAnalysisResponse, JobRequirements


DEFAULT_JOB_STORAGE = Path("backend/storage/jobs")


def _safe_job_id(job_id: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_-]+", job_id):
        raise ValueError("job_id không hợp lệ")
    return job_id


def save_job_analysis(
    requirements: JobRequirements,
    warnings: list[str],
    source_url: str | None,
    storage_dir: Path = DEFAULT_JOB_STORAGE,
) -> JobAnalysisResponse:
    job_id = uuid4().hex
    response = JobAnalysisResponse(
        job_id=job_id,
        status="review" if warnings else "completed",
        job_requirements=requirements,
        warnings=warnings,
        source_url=source_url,
        job_description_raw=requirements.job_description_raw,
    )
    record = response.model_dump(mode="json")
    record["analyzed_at"] = datetime.now(timezone.utc).isoformat()
    storage_dir.mkdir(parents=True, exist_ok=True)
    (storage_dir / f"{job_id}.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return response


def load_job_analysis(
    job_id: str,
    storage_dir: Path = DEFAULT_JOB_STORAGE,
) -> JobAnalysisResponse | None:
    path = storage_dir / f"{_safe_job_id(job_id)}.json"
    if not path.exists():
        return None
    record = json.loads(path.read_text(encoding="utf-8"))
    record.pop("analyzed_at", None)
    return JobAnalysisResponse.model_validate(record)

