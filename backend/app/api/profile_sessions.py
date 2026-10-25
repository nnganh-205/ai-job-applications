from typing import Annotated

from fastapi import APIRouter, HTTPException, Path
from pydantic import ValidationError

from backend.app.api.dashboard import execute
from backend.app.db.profile_revision_repository import RevisionConflict, history, current_revision
from backend.app.schemas.profile_update import SessionAction, SessionView, UpdateStart
from backend.app.services import profile_sessions as service

router = APIRouter(prefix="/api/profile-sessions", tags=["Profile Update and Chat"])
SessionID = Annotated[str, Path(pattern=r"^[a-f0-9]{32}$")]


def run(function, *args):
    def checked():
        try:
            return function(*args)
        except RevisionConflict as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except ValidationError as error:
            raise HTTPException(status_code=422, detail="Thông tin hồ sơ/câu trả lời không đúng schema; hồ sơ chưa được cập nhật") from error
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
    return execute(checked)


@router.post("/update", response_model=SessionView)
def start_update(request: UpdateStart):
    return run(service.start_update, request)


@router.post("/build", response_model=SessionView)
def start_build():
    return run(service.start_build)


@router.get("/{session_id}", response_model=SessionView)
def get_session(session_id: SessionID):
    return run(service.view_session, session_id)


@router.post("/{session_id}/actions", response_model=SessionView)
def action(session_id: SessionID, request: SessionAction):
    return run(service.act, session_id, request)


@router.post("/{session_id}/retry", response_model=SessionView)
def retry(session_id: SessionID):
    return run(service.retry, session_id)


@router.get("/profiles/{profile_id}/revisions")
def revisions(profile_id: Annotated[str, Path(pattern=r"^[A-Za-z0-9_-]{1,128}$")]):
    return {"current_profile_id": run(current_revision, profile_id), "revisions": run(history, profile_id)}
