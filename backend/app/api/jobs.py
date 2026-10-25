from typing import Annotated

from fastapi import APIRouter, HTTPException, Path

from backend.app.ai.graph.jd_workflow import run_jd_analysis
from backend.app.ai.llm.ollama_client import (
    OllamaConnectionError,
    OllamaResponseError,
    OllamaTimeoutError,
)
from backend.app.schemas.job import JobAnalysisRequest, JobAnalysisResponse, JobRequirements
from backend.app.services.job_fetcher import JobContentError, JobFetchError, UnsafeJobUrl
from backend.app.db.job_repository import load_job_analysis, save_job_analysis


router = APIRouter(prefix="/api/jobs", tags=["JD Analysis Agent"])


@router.get("/{job_id}", response_model=JobAnalysisResponse)
def get_job(job_id: Annotated[str, Path(pattern=r"^[A-Za-z0-9_-]{1,128}$")]) -> JobAnalysisResponse:
    job = load_job_analysis(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy JD đã lưu")
    return job


@router.post("/analyze", response_model=JobAnalysisResponse)
def analyze_job(request: JobAnalysisRequest) -> JobAnalysisResponse:
    if request.saved_job_id:
        saved_job = load_job_analysis(request.saved_job_id)
        if saved_job is None:
            raise HTTPException(status_code=404, detail="Không tìm thấy JD đã lưu")
        return saved_job

    try:
        state = run_jd_analysis(request.source_url, request.job_description_text)
        requirements = JobRequirements.model_validate(state["job_requirements"])
        return save_job_analysis(
            requirements,
            state.get("warnings", []),
            state.get("final_url") or request.source_url,
        )
    except UnsafeJobUrl as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except JobFetchError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    except JobContentError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except OllamaConnectionError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except OllamaTimeoutError as error:
        raise HTTPException(status_code=504, detail=str(error)) from error
    except OllamaResponseError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
