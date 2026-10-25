from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query

from backend.app.ai.llm.ollama_client import OllamaConnectionError, OllamaError, OllamaTimeoutError
from backend.app.db.job_posting_repository import get_posting, set_saved
from backend.app.schemas.dashboard import DashboardEvaluation, EvaluateRequest, JobImportRequest, JobPosting, SavedJobRequest
from backend.app.services.dashboard_service import dashboard_snapshot, evaluate_job
from backend.app.services.job_fetcher import JobContentError, JobFetchError, UnsafeJobUrl
from backend.app.services.job_importer import import_job, refresh_job, sync_jobs
from backend.app.db.profile_revision_repository import RevisionConflict


router = APIRouter(prefix="/api/dashboard", tags=["Recruitment Dashboard"])
PostingID = Annotated[str, Path(pattern=r"^posting_[a-f0-9]{24}$")]


def execute(function, *args, **kwargs):
    try:
        return function(*args, **kwargs)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except UnsafeJobUrl as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except JobContentError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except JobFetchError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    except OllamaConnectionError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except OllamaTimeoutError as error:
        raise HTTPException(status_code=504, detail=str(error)) from error
    except OllamaError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    except RevisionConflict as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail="Không xác thực được dữ liệu JD. Hãy kiểm tra nội dung hoặc nhập JD text ngắn hơn.") from error


@router.get("")
def dashboard(q: str = Query(default="", max_length=200), location: str = "", employment_type: str = "", workplace_type: str = "", saved: bool = False, source_name: str = "", domestic_sources_only: bool = False):
    return execute(dashboard_snapshot, q, location, employment_type, workplace_type, saved, source_name, domestic_sources_only)


@router.post("/jobs", response_model=JobPosting)
def add_job(request: JobImportRequest):
    return execute(import_job, request)


@router.post("/jobs/sync")
def sync():
    return execute(sync_jobs)


@router.get("/jobs/{posting_id}", response_model=JobPosting)
def detail(posting_id: PostingID):
    job = get_posting(posting_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy công việc")
    return job


@router.post("/jobs/{posting_id}/refresh")
def refresh(posting_id: PostingID):
    return execute(refresh_job, posting_id)


@router.post("/jobs/{posting_id}/evaluate", response_model=DashboardEvaluation)
def evaluate(posting_id: PostingID, request: EvaluateRequest):
    return execute(evaluate_job, posting_id, request.profile_id)


@router.patch("/jobs/{posting_id}/saved", response_model=JobPosting)
def save(posting_id: PostingID, request: SavedJobRequest):
    return execute(set_saved, posting_id, request.saved)
