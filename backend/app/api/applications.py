from typing import Annotated
from fastapi import APIRouter,Path
from backend.app.api.dashboard import execute
from backend.app.schemas.application import ApplicationUpdate
from backend.app.services import applications
router=APIRouter(prefix='/api/applications',tags=['Application tracker'])
PostingID=Annotated[str,Path(pattern=r'^posting_[a-f0-9]{24}$')]


@router.get('')
def list_all():return execute(applications.list_all)


@router.get('/{posting_id}')
def read(posting_id:PostingID):return execute(applications.read,posting_id)


@router.post('/{posting_id}/events')
def update(posting_id:PostingID,request:ApplicationUpdate):return execute(applications.update,posting_id,request)
