from fastapi import APIRouter
from pydantic import BaseModel,HttpUrl
from backend.app.db import workflow_repository as records

router=APIRouter(prefix='/api/events',tags=['Career events'])


class CareerEvent(BaseModel):
    id:str
    title:str
    description:str
    starts_at:str
    location:str|None=None
    format:str|None=None
    source_url:HttpUrl
    registration_url:HttpUrl|None=None


@router.get('',response_model=list[CareerEvent])
def events():
    return [CareerEvent.model_validate(event) for event in records.list_kind('events')]
