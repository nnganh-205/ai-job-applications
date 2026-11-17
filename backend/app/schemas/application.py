"""Self-reported application tracking; link activation is not a submission."""
from typing import Literal
from pydantic import Field
from backend.app.schemas.profile import StrictModel

ApplicationStatus=Literal['saved','opened_source','applied','interviewing','offer','rejected','withdrawn']


class ApplicationUpdate(StrictModel):
    status:ApplicationStatus
    expected_version:int=Field(ge=0)
    event_id:str=Field(pattern=r'^[A-Za-z0-9_-]{1,128}$')
    job_content_hash:str=Field(pattern=r'^[a-f0-9]{64}$')
    cv_id:str|None=Field(default=None,pattern=r'^cv_[a-f0-9]{32}$')
    profile_id:str|None=Field(default=None,pattern=r'^[A-Za-z0-9_-]{1,128}$')
