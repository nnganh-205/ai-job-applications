from typing import Annotated
from fastapi import APIRouter,Path,Query,HTTPException
from fastapi.responses import HTMLResponse
from backend.app.services import resumes, resume_editing
from backend.app.schemas.resume import ResumeStart,ResumeSave,ResumePublish,ResumeEditStart,ResumeEditComplete
from backend.app.schemas.profile_draft import DraftSave
from backend.app.schemas.cv import CVDocument
from backend.app.services.resume_writer import ResumeWriterRequest,ResumeWriterApply
from backend.app.db.profile_revision_repository import RevisionConflict
from backend.app.api.cv import run
from backend.app.services.cv_renderer import render_html

router=APIRouter(prefix='/api/resumes',tags=['CV Library'])
ResumeID=Annotated[str,Path(pattern=r'^resume_[a-f0-9]{32}$')]


def checked(fn,*args):
    try:return run(fn,*args)
    except RevisionConflict as e:raise HTTPException(409,str(e)) from e


@router.get('')
def library():return resumes.library()


@router.post('')
def start(request:ResumeStart):return checked(resumes.start,request)


@router.get('/published')
def published():
    from backend.app.db import workflow_repository as records
    from backend.app.services.cv_lineage import version_status
    return [{**{k:v.get(k) for k in ('cv_id','title','created_at','resume_id','draft_version')},'cv_version':version_status(v['cv_id'],v)} for v in records.list_kind('cv_versions')]


@router.get('/{key}')
def read(key:ResumeID):return checked(resumes.read,key)


@router.put('/{key}')
def save(key:ResumeID,request:ResumeSave):return checked(resumes.save,key,request)


@router.delete('/{key}')
def delete(key: ResumeID, expected_version: Annotated[int, Query(ge=1)]):
    return checked(resumes.delete, key, expected_version)


@router.post('/{key}/publish')
def publish(key:ResumeID,request:ResumePublish):return checked(resumes.publish,key,request)


@router.post('/{key}/duplicate')
def duplicate(key:ResumeID):return checked(resumes.duplicate,key)


@router.get('/{key}/preview',response_class=HTMLResponse)
def preview(key:ResumeID):
    data=checked(resumes.read,key)
    return HTMLResponse(render_html(CVDocument.model_validate(data['document']),data['presentation']['template'],data['presentation']),headers={'Cache-Control':'no-store'})


@router.post('/{key}/preview', response_class=HTMLResponse)
def preview_changes(key: ResumeID, request: ResumeSave):
    return HTMLResponse(checked(resumes.preview_changes, key, request), headers={'Cache-Control': 'no-store'})


@router.post('/{key}/writer')
def writer(key:ResumeID,request:ResumeWriterRequest):
    from backend.app.services.resume_writer import preview
    return checked(preview,key,request)


@router.post('/{key}/writer/apply')
def writer_apply(key:ResumeID,request:ResumeWriterApply):
    from backend.app.services.resume_writer import apply
    return checked(apply,key,request)


@router.post('/{key}/source-edit')
def begin_edit(key: ResumeID, request: ResumeEditStart):
    return checked(resume_editing.begin, key, request)


@router.get('/{key}/source-edit')
def read_edit(key: ResumeID):
    return checked(resume_editing.read, key)


@router.put('/{key}/source-edit')
def save_edit(key: ResumeID, request: DraftSave):
    return checked(resume_editing.save, key, request)


@router.post('/{key}/source-edit/complete')
def complete_edit(key: ResumeID, request: ResumeEditComplete):
    return checked(resume_editing.complete, key, request)


from backend.app.services import resume_history
from backend.app.schemas.resume import ResumeRestore


@router.get('/{key}/history')
def history(key: ResumeID):
    return checked(resume_history.listing, key)


@router.get('/{key}/history/{version}/preview', response_class=HTMLResponse)
def history_preview(key: ResumeID, version: int):
    value=checked(resume_history.selected,key,version)
    return HTMLResponse(render_html(CVDocument.model_validate(value['document']),value['presentation']['template'],value['presentation']),headers={'Cache-Control':'no-store'})


@router.post('/{key}/history/restore')
def restore_history(key: ResumeID, request: ResumeRestore):
    return checked(resume_history.restore,key,request)


@router.get('/{key}/history/drafts/{draft_id}')
def archived_history_draft(key: ResumeID, draft_id: str):
    return checked(resume_history.archived_draft,key,draft_id)
