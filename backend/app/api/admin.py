from typing import Literal
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel, ConfigDict, Field, model_validator
from backend.app.schemas.template_design import TemplateDesign
from backend.app.services import administration as admin, knowledge, template_catalog


def require_admin(request: Request):
    session = getattr(request.state, 'auth', None)
    if not session: raise HTTPException(401, 'Vui lòng đăng nhập.')
    if session['user']['role'] != 'admin': raise HTTPException(403, 'Chỉ quản trị viên được sử dụng chức năng này.')
    return session['user']['user_id']


router = APIRouter(prefix='/api/admin', tags=['Administration'], dependencies=[Depends(require_admin)])
State = Literal['draft', 'published', 'archived']


class UserUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    role: Literal['user', 'admin'] | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=12, max_length=128, repr=False)


class Document(BaseModel):
    model_config = ConfigDict(extra='forbid')
    title: str = Field(min_length=3, max_length=200)
    text: str = Field(min_length=80, max_length=500000)
    url: str = Field(default='', max_length=2000)
    effective: str = Field(default='', max_length=10)
    status: State = 'draft'
    expected_version: int | None = Field(default=None, ge=1)


class StatusChange(BaseModel):
    model_config = ConfigDict(extra='forbid')
    status: State
    expected_version: int = Field(ge=1)


class Query(BaseModel):
    query: str = Field(min_length=2, max_length=500)


class Template(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=3, max_length=100)
    description: str = Field(default='', max_length=500)
    base_template: str | None = Field(default=None, min_length=1, max_length=100)
    design: TemplateDesign | None = None
    category: Literal['basic', 'professional', 'modern', 'impressive', 'harvard', 'ats']
    color: str = Field(pattern=r'^#[a-fA-F0-9]{6}$')
    font: Literal['sans', 'serif']
    enabled: bool = True
    expected_revision: int | None = Field(default=None, ge=0)

    @model_validator(mode='after')
    def design_or_base(self):
        if bool(self.design) == bool(self.base_template):
            raise ValueError('Chọn cấu hình thiết kế mới hoặc bố cục có sẵn.')
        return self


class DeleteTemplate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_revision: int = Field(ge=0)


def execute(fn, *args, **kwargs):
    try: return fn(*args, **kwargs)
    except LookupError as error: raise HTTPException(404, str(error)) from error
    except admin.AdminConflict as error: raise HTTPException(409, str(error)) from error
    except ValueError as error: raise HTTPException(422, str(error)) from error


@router.get('/overview')
def overview(): return admin.overview()


@router.get('/templates')
def templates(): return template_catalog.list_templates(admin=True)


@router.get('/templates/bases')
def template_bases(): return template_catalog.base_templates()


@router.post('/templates/preview')
def preview_template(payload: Template):
    return execute(template_catalog.preview, payload.model_dump())


@router.post('/templates', status_code=201)
def create_template(payload: Template, actor: str = Depends(require_admin)):
    return execute(template_catalog.save, actor, payload.model_dump())


@router.put('/templates/{template_id}')
def update_template(template_id: str, payload: Template, actor: str = Depends(require_admin)):
    return execute(template_catalog.save, actor, payload.model_dump(), template_id)


@router.delete('/templates/{template_id}')
def delete_template(template_id: str, payload: DeleteTemplate, actor: str = Depends(require_admin)):
    return execute(template_catalog.delete, actor, template_id, payload.expected_revision)


@router.get('/users')
def users(): return admin.users()


@router.patch('/users/{user_id}')
def update_user(user_id: str, payload: UserUpdate, actor: str = Depends(require_admin)):
    return execute(admin.update_user, actor, user_id, payload.model_dump(exclude_none=True))


@router.get('/activity')
def activity(): return admin.activity()


@router.get('/tasks')
def tasks(): return admin.task_list()


@router.post('/tasks/{task_id}/retry')
def retry(task_id: str, actor: str = Depends(require_admin)):
    return execute(admin.retry_task, actor, task_id)


@router.get('/knowledge')
def documents(): return knowledge.list_documents()


@router.post('/knowledge', status_code=201)
def create(payload: Document, actor: str = Depends(require_admin)):
    return execute(knowledge.save, actor, payload.model_dump())


@router.post('/knowledge/upload', status_code=201)
def upload(file: UploadFile = File(...), title: str = Form(..., min_length=3, max_length=200),
           url: str = Form('', max_length=2000), effective: str = Form('', max_length=10),
           actor: str = Depends(require_admin)):
    content = file.file.read(10*1024*1024 + 1)
    if len(content) > 10*1024*1024: raise HTTPException(413, 'PDF tối đa 10 MB.')
    return execute(knowledge.upload_pdf, actor, content, dict(title=title, url=url, effective=effective, status='draft'))


@router.post('/knowledge/search')
def search(payload: Query):
    from ai.rag.labor_law import retrieve
    return {'hits': retrieve(payload.query.strip(), limit=5)}


@router.get('/knowledge/{document_id}')
def document(document_id: str): return execute(knowledge.detail, document_id)


@router.put('/knowledge/{document_id}')
def update(document_id: str, payload: Document, actor: str = Depends(require_admin)):
    if payload.expected_version is None: raise HTTPException(422, 'Cần phiên bản tài liệu để cập nhật.')
    return execute(knowledge.save, actor, payload.model_dump(), document_id)


@router.patch('/knowledge/{document_id}/status')
def status(document_id: str, payload: StatusChange, actor: str = Depends(require_admin)):
    return execute(knowledge.change_status, actor, document_id, payload.status, payload.expected_version)
