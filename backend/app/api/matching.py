from typing import Annotated

from fastapi import APIRouter, HTTPException, Path

from backend.app.ai.agents.matching_agent import match_profile
from backend.app.db.job_repository import load_job_analysis
from backend.app.db.match_repository import load_match, save_match
from backend.app.db.profile_repository import load_profile_record
from backend.app.schemas.matching import MatchRequest, MatchResponse
from backend.app.services.profile_answers import confirmed_denials


router = APIRouter(prefix="/api/matches", tags=["Matching Agent"])


@router.post("", response_model=MatchResponse)
def create_match(request: MatchRequest) -> MatchResponse:
    # Pending drafts cannot pass this boundary: only confirmed storage is read.
    record = load_profile_record(request.profile_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Master Profile chưa xác nhận hoặc không tồn tại")
    job = load_job_analysis(request.job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy JD đã phân tích")
    result = match_profile(record.profile, job.job_requirements, request.profile_id, request.job_id,
                           confirmed_unmet=confirmed_denials(request.profile_id, job.job_requirements))
    result.warnings = list(dict.fromkeys([*result.warnings, *job.warnings, *record.warnings]))
    return save_match(result)


@router.get("/{result_id}", response_model=MatchResponse)
def get_match(result_id: Annotated[str, Path(pattern=r"^match_[a-f0-9]{24}$")]) -> MatchResponse:
    result = load_match(result_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy kết quả Matching")
    return result
