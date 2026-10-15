from uuid import uuid4

from fastapi import APIRouter, File, HTTPException, UploadFile

from backend.app.ai.graph.profile_workflow import confirm_extraction, start_extraction
from backend.app.ai.llm.ollama_client import OllamaError
from backend.app.schemas.profile import (
    ConfirmationRequest,
    ExtractionResponse,
    SavedProfileResponse,
)
from backend.app.services.document_reader import DocumentReadError
from backend.app.db.profile_repository import load_master_profile


router = APIRouter(prefix="/api/profiles", tags=["Profile Agent"])


@router.post("/extract", response_model=ExtractionResponse)
async def extract_cv(file: UploadFile = File(...)) -> ExtractionResponse:
    thread_id = uuid4().hex
    try:
        state = start_extraction(file.filename or "", await file.read(), thread_id)
    except (DocumentReadError, OllamaError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return ExtractionResponse(
        thread_id=thread_id,
        status="pending_confirmation",
        profile=state["profile"],
        warnings=state.get("warnings", []),
    )


@router.post("/{thread_id}/confirm", response_model=SavedProfileResponse)
def confirm_profile(thread_id: str, request: ConfirmationRequest) -> SavedProfileResponse:
    try:
        state = confirm_extraction(thread_id, request.profile)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    if state.get("status") != "confirmed":
        raise HTTPException(status_code=409, detail="Phiên trích xuất chưa sẵn sàng để xác nhận")
    return SavedProfileResponse(
        thread_id=thread_id,
        status="confirmed",
        profile=state["profile"],
        warnings=state.get("warnings", []),
    )


@router.get("/{thread_id}", response_model=SavedProfileResponse)
def get_master_profile(thread_id: str) -> SavedProfileResponse:
    profile = load_master_profile(thread_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Master Profile chưa được xác nhận hoặc không tồn tại")
    return SavedProfileResponse(
        thread_id=thread_id,
        status="confirmed",
        profile=profile,
        warnings=[],
    )
