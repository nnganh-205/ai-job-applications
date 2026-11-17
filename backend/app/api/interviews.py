from typing import Annotated
from fastapi import APIRouter,HTTPException,Path
from backend.app.api.dashboard import execute
from backend.app.schemas.interview import InterviewStart,InterviewAnswer
from backend.app.services import interviews

router=APIRouter(prefix='/api/interviews',tags=['Text interview practice'])
SessionID=Annotated[str,Path(pattern=r'^interview_[a-f0-9]{32}$')]


def call(function,*args):
    try:return execute(function,*args)
    except HTTPException as error:
        if error.status_code==422:raise HTTPException(422,'Không tạo được lượt phỏng vấn. Kiểm tra CV/JD và câu trả lời.') from error
        raise


@router.get('')
def recent():return call(interviews.recent)


@router.post('',status_code=202)
def start(request:InterviewStart):return call(interviews.start,request)


@router.get('/{session_id}')
def read(session_id:SessionID):return call(lambda:interviews.public(interviews.read(session_id)))


@router.post('/{session_id}/answers',status_code=202)
def answer(session_id:SessionID,request:InterviewAnswer):return call(interviews.answer,session_id,request)
