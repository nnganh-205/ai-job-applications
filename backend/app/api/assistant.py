from typing import Annotated
from fastapi import APIRouter,Path,HTTPException
from backend.app.api.dashboard import execute
from backend.app.schemas.assistant import AssistantStart,AssistantMessage
from backend.app.services import assistant

router=APIRouter(prefix='/api/assistant',tags=['Career assistant'])
SessionID=Annotated[str,Path(pattern=r'^assistant_[a-f0-9]{32}$')]


def call(function,*args):
    try:return execute(function,*args)
    except HTTPException as error:
        if error.status_code==422:raise HTTPException(422,'Không xử lý được yêu cầu trợ lý. Kiểm tra nội dung và nguồn đã chọn.') from error
        raise


@router.get('')
def recent():return call(assistant.recent)


@router.post('',status_code=201)
def start(request:AssistantStart):return call(assistant.start,request)


@router.get('/{session_id}')
def read(session_id:SessionID):return call(lambda:assistant.public(assistant.read(session_id)))


@router.post('/{session_id}/messages',status_code=202)
def message(session_id:SessionID,request:AssistantMessage):return call(assistant.message,session_id,request)
