from pydantic import Field

from backend.app.schemas.profile import StrictModel
from backend.app.schemas.workflow import MatchResult


class MatchRequest(StrictModel):
    profile_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,128}$")
    job_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,128}$")


class MatchResponse(MatchResult):
    result_id: str
    profile_content_hash: str
    job_content_hash: str
    evidence_coverage: float = Field(ge=0, le=1)
    core_coverage: float | None = Field(default=None, ge=0, le=1)
    applied_weights: dict[str, float]
    as_of: str
