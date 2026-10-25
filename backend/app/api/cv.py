"""CV APIs: preview is temporary; only explicit approval persists a CV version."""

from typing import Annotated

from fastapi import APIRouter, Path, HTTPException
from fastapi.responses import HTMLResponse, Response
from pydantic import ValidationError

from backend.app.ai.graph import cv_workflow as workflow
from backend.app.api.dashboard import execute
from backend.app.db import workflow_repository as records
from backend.app.schemas.cv import CVApproval, CVDocument, CVSession, CVStart
from backend.app.services.cv_renderer import TEMPLATES, render_html, render_pdf

router = APIRouter(prefix='/api/cv', tags=['CV Review and Generation'])
SessionID = Annotated[str, Path(pattern=r'^[a-f0-9]{32}$')]
CVID = Annotated[str, Path(pattern=r'^cv_[a-f0-9]{32}$')]


def run(function, *args):
    def checked():
        try:
            return function(*args)
        except ValidationError as error:
            raise HTTPException(status_code=422, detail='Dữ liệu CV không đúng schema; chưa lưu thay đổi.') from error
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
    return execute(checked)


@router.get('/templates')
def templates():
    return TEMPLATES


@router.post('/sessions', response_model=CVSession)
def start(request: CVStart):
    return run(workflow.start, request)


@router.get('/sessions/{session_id}', response_model=CVSession)
def session(session_id: SessionID):
    return run(workflow.view, session_id)


@router.post('/sessions/{session_id}/approve', response_model=CVSession)
def approve(session_id: SessionID, request: CVApproval):
    return run(workflow.confirm, session_id, request)


@router.post('/sessions/{session_id}/preview', response_class=HTMLResponse)
def preview(session_id: SessionID, request: CVApproval):
    current = run(workflow.view, session_id)
    document = request.document or current.document
    from backend.app.ai.agents.cv_agent import validate_edits
    run(validate_edits, current.document, document)
    return HTMLResponse(run(render_html, document, request.template), headers={'Cache-Control': 'no-store'})


@router.get('/versions/{cv_id}')
def version(cv_id: CVID):
    data = records.get('cv_versions', cv_id)
    if data is None:
        raise HTTPException(status_code=404, detail='Không tìm thấy CV đã xác nhận.')
    return data


@router.get('/versions/{cv_id}/pdf')
def pdf(cv_id: CVID):
    data = version(cv_id)
    content = run(render_pdf, CVDocument.model_validate(data['document']), data['template'])
    return Response(content, media_type='application/pdf', headers={'Content-Disposition': f'attachment; filename="{cv_id}.pdf"', 'Cache-Control': 'no-store'})
