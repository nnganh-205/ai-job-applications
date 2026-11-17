from typing import Annotated
from fastapi import APIRouter, HTTPException, Path
from backend.app.services import profile_drafts as service
from backend.app.schemas.profile import MasterProfile
from backend.app.services.cv_polish import PolishRequest
from backend.app.services.cv_writer import WriterRequest
from backend.app.schemas.profile_draft import DraftStart, DraftSave, DraftConfirm
from backend.app.db.profile_revision_repository import RevisionConflict
from backend.app.db.profile_repository import list_profile_records

router = APIRouter(prefix='/api/profile-drafts', tags=['Profile forms'])
DraftID = Annotated[str, Path(pattern=r'^draft_[a-f0-9]{32}$')]


def run(fn, *args):
    try:
        return fn(*args)
    except RevisionConflict as error:
        raise HTTPException(409, str(error)) from error
    except LookupError as error:
        raise HTTPException(404, str(error)) from error


@router.get('/schema')
def schema():
    return MasterProfile.model_json_schema()


@router.get('/profiles')
def profiles():
    return [{'profile_id': key, 'full_name': record.profile.contact.full_name, 'parent_profile_id': record.parent_profile_id} for key, record in list_profile_records() if not key.startswith("cvlocal_")]


@router.get('')
def drafts():
    return service.list_editing()


@router.post('')
def start(request: DraftStart):
    return run(service.start, request.base_profile_id)


@router.post('/writer')
def writer(request: WriterRequest):
    from backend.app.services.cv_writer import write_bullets
    return write_bullets(request)


@router.post('/polish')
def polish_text(request: PolishRequest):
    from backend.app.services.cv_polish import polish
    return polish(request)


@router.get('/{draft_id}')
def read(draft_id: DraftID):
    return run(service.read, draft_id)


@router.put('/{draft_id}')
def save(draft_id: DraftID, request: DraftSave):
    return run(service.save, draft_id, request)


@router.post('/{draft_id}/confirm')
def confirm(draft_id: DraftID, request: DraftConfirm):
    return run(service.confirm, draft_id, request)
