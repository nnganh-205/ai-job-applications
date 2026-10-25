from uuid import uuid4
from typing import Annotated

from fastapi import APIRouter, File, HTTPException, Path, UploadFile
from starlette.concurrency import run_in_threadpool

from backend.app.ai.graph.profile_workflow import confirm_extraction, profile_graph, start_extraction
from backend.app.ai.llm.ollama_client import OllamaConnectionError, OllamaError, OllamaTimeoutError
from backend.app.schemas.profile import (
    ConfirmationRequest,
    ExtractionResponse,
    SavedProfileResponse,
)
from backend.app.services.document_reader import DocumentReadError, MAX_FILE_SIZE
from backend.app.db.profile_repository import load_profile_record


router = APIRouter(prefix="/api/profiles", tags=["Profile Agent"])
ThreadID = Annotated[str, Path(pattern=r"^[A-Za-z0-9_-]{1,128}$")]


@router.post("/extract", response_model=ExtractionResponse)
async def extract_cv(file: UploadFile = File(...)) -> ExtractionResponse:
    thread_id = uuid4().hex
    try:
        content = await file.read(MAX_FILE_SIZE + 1)
        if len(content) > MAX_FILE_SIZE:
            raise HTTPException(status_code=413, detail="File CV vượt quá giới hạn 5 MB")
        state = await run_in_threadpool(start_extraction, file.filename or "", content, thread_id)
    except DocumentReadError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except OllamaConnectionError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except OllamaTimeoutError as error:
        raise HTTPException(status_code=504, detail=str(error)) from error
    except OllamaError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    finally:
        await file.close()
    return ExtractionResponse(
        thread_id=thread_id,
        status="pending_confirmation",
        profile=state["profile"],
        warnings=state.get("warnings", []),
        evidence=state.get("evidence", []),
    )


@router.post("/{thread_id}/confirm", response_model=SavedProfileResponse)
def confirm_profile(thread_id: ThreadID, request: ConfirmationRequest) -> SavedProfileResponse:
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
        evidence=state.get("evidence", []),
    )


@router.get("/{thread_id}", response_model=SavedProfileResponse)
def get_master_profile(thread_id: ThreadID) -> SavedProfileResponse:
    record = load_profile_record(thread_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Master Profile chưa được xác nhận hoặc không tồn tại")
    return SavedProfileResponse(
        thread_id=thread_id,
        status="confirmed",
        profile=record.profile,
        warnings=record.warnings,
        evidence=record.evidence,
    )


@router.get("/{thread_id}/draft", response_model=ExtractionResponse)
def get_profile_draft(thread_id: ThreadID) -> ExtractionResponse:
    state = profile_graph.get_state({"configurable": {"thread_id": thread_id}}).values
    if not state or state.get("status") != "pending_confirmation":
        raise HTTPException(status_code=404, detail="Không tìm thấy bản nháp đang chờ xác nhận")
    return ExtractionResponse(thread_id=thread_id, status="pending_confirmation", profile=state["profile"], warnings=state.get("warnings", []), evidence=state.get("evidence", []))
