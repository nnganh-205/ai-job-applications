from fastapi import APIRouter
from pydantic import BaseModel,HttpUrl
from backend.app.db import workflow_repository as records, database

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
    if database.enabled():
        values = [row['data'] for row in database.list_records('events', shared=True)]
    else:
        import json
        values = [json.loads(path.read_text()) for path in (records.DEFAULT_WORKFLOW_STORAGE / 'events').glob('*.json')]
    return [CareerEvent.model_validate(event) for event in values if 'title' in event and 'source_url' in event]
