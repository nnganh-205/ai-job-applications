from typing import Annotated,Literal
from uuid import uuid4
from fastapi import APIRouter,Header,Path,Query
from backend.app.schemas.cv import CVStart
from backend.app.schemas.dashboard import EvaluateRequest
from backend.app.api.dashboard import execute
from backend.app.services import tasks

router=APIRouter(prefix='/api/tasks',tags=['Background tasks'])
TaskID=Annotated[str,Path(pattern=r'^task_[a-f0-9]{32}$')]
Key=Annotated[str|None,Header(alias='Idempotency-Key',pattern=r'^[A-Za-z0-9_-]{1,128}$')]


@router.get('')
def list_recent(kind:Literal['cv','evaluate','interview','assistant']|None=None,profile_id:Annotated[str|None,Query(pattern=r'^[A-Za-z0-9_-]{1,128}$')]=None):
    return execute(tasks.list_recent,kind,profile_id)


@router.post('/cv',status_code=202)
def cv(request:CVStart,idempotency_key:Key=None):
    return execute(tasks.submit,'cv',request.model_dump(mode='json'),idempotency_key or uuid4().hex)


@router.post('/evaluate/{posting_id}',status_code=202)
def evaluate(posting_id:Annotated[str,Path(pattern=r'^posting_[a-f0-9]{24}$')],request:EvaluateRequest,idempotency_key:Key=None):
    return execute(tasks.submit,'evaluate',{'posting_id':posting_id,**request.model_dump(mode='json')},idempotency_key or uuid4().hex)


@router.get('/{task_id}')
def read(task_id:TaskID):return execute(tasks.read,task_id)


@router.post('/{task_id}/retry',status_code=202)
def retry(task_id:TaskID):return execute(tasks.retry,task_id)
