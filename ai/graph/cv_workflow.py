"""Agent 5 graph: confirmed profile -> Qwen -> user approval -> immutable CV version."""

from datetime import datetime, timezone
from threading import RLock
from typing import TypedDict
from uuid import uuid4

from langgraph.graph import StateGraph, START, END
from langgraph.types import Command, interrupt

from ai.agents.cv_agent import source_document, plan_cv, validate_edits
from backend.app.db import database, profile_repository, workflow_repository as records
from backend.app.db.checkpoints import get_checkpointer
from backend.app.db.profile_revision_repository import current_revision, RevisionConflict
from backend.app.schemas.cv import CVStart, CVApproval, CVDocument, CVSession
from backend.app.services.dashboard_service import evaluate_job
from backend.app.core.config import settings
from ai.prompts.cv_prompt import CV_PROMPT_VERSION


class CVState(TypedDict, total=False):
    request: dict
    document: dict
    review: dict
    warnings: list[str]
    session_id: str
    status: str
    template: str
    prompt_version: str
    cv_id: str


def generate(state):
    request = CVStart.model_validate(state['request'])
    if request.cv_id:
        version=records.get('cv_versions',request.cv_id)
        if version is None:raise LookupError('Không tìm thấy CV đã xác nhận')
        baseline=CVDocument.model_validate(version['document']).model_copy(deep=True)
        baseline.language=request.language
    else:
        record=profile_repository.load_profile_record(request.profile_id,profile_repository.DEFAULT_STORAGE_DIR)
        if record is None:raise LookupError('Cần hồ sơ đã xác nhận để tạo CV.')
        if current_revision(request.profile_id)!=request.profile_id:raise RevisionConflict('Hồ sơ đã thay đổi. Chọn phiên bản mới nhất trước khi tạo CV.')
        baseline=source_document(record.profile,request.profile_id,language=request.language)
    requirements,job_id,warnings=None,None,[]
    if request.posting_id:
        evaluated=evaluate_job(request.posting_id,request.profile_id,cv_id=request.cv_id)
        requirements=evaluated.analysis.job_requirements.model_dump(mode='json')
        baseline.job_analysis_id=evaluated.analysis.job_id
        warnings=evaluated.warnings
        if evaluated.status=='needs_review' and request.mode=='generate':raise ValueError('JD cần kiểm tra trước khi tối ưu CV. Bạn vẫn có thể review CV không gắn JD.')
    document, review = plan_cv(baseline, requirements, request.mode)
    return {'document': document.model_dump(mode='json'), 'review': review.model_dump(mode='json'),
            'warnings': list(dict.fromkeys(warnings + review.warnings)), 'status': 'pending_approval', 'template': 'ats', 'prompt_version': CV_PROMPT_VERSION}


def approval(state):
    answer = CVApproval.model_validate(interrupt({'status': 'pending_approval', 'document': state['document']}))
    if answer.decision == 'reject':
        return {'status': 'cancelled'}
    document = answer.document or CVDocument.model_validate(state['document'])
    validate_edits(CVDocument.model_validate(state['document']), document)
    return {'status': 'confirmed', 'document': document.model_dump(mode='json'), 'template': answer.template}


def save(state):
    cv_id = 'cv_' + state['session_id']
    from backend.app.services.cv_templates import metadata
    meta=metadata(state['template'])
    data = {'presentation':{'template':state['template'],'template_version':meta['version'],'font':meta['font'],'color':meta['color']}, 'cv_id': cv_id, 'document': state['document'], 'template': state['template'], 'review': state['review'],
            'created_at': datetime.now(timezone.utc).isoformat(), 'prompt_version':state.get('prompt_version'), 'model': settings.cv_model, 'provider': 'ollama',
            'warnings': state['warnings'] + ['Chỉnh sửa thủ công chỉ được xác nhận cho phiên bản CV này, không cập nhật Master Profile.']}
    data['source_cv_id']=state['request'].get('cv_id')
    data['source_posting_id']=state['request'].get('posting_id')
    if database.enabled():
        database.put_record('cv_versions', cv_id, data, immutable=True)
    elif records.get('cv_versions', cv_id) is None:
        records.put('cv_versions', cv_id, data)
    return {'cv_id': cv_id}


def build_cv_graph(checkpointer=None):
    graph = StateGraph(CVState)
    graph.add_node('generate', generate)
    graph.add_node('approval', approval)
    graph.add_node('save', save)
    graph.add_edge(START, 'generate')
    graph.add_edge('generate', 'approval')
    graph.add_conditional_edges('approval', lambda state: 'save' if state['status'] == 'confirmed' else END)
    graph.add_edge('save', END)
    return graph.compile(checkpointer=checkpointer or get_checkpointer())


cv_graph = build_cv_graph()
_lock = RLock()


def view(session_id):
    if records.get('cv_sessions', session_id) is None:
        raise LookupError('Không tìm thấy phiên CV.')
    state = cv_graph.get_state({'configurable': {'thread_id': 'cv:' + session_id}}).values
    if not state or 'document' not in state:
        raise ValueError('Phiên tạo CV chưa có kết quả; vui lòng tạo lại.')
    return CVSession(session_id=session_id, status=state['status'], document=state['document'], review=state['review'],
                     warnings=state['warnings'], prompt_version=state.get('prompt_version'), cv_id=state.get('cv_id'), template=state.get('template', 'ats'))


def start(request,session_id=None):
    session_id=session_id or uuid4().hex
    previous=records.get('cv_sessions',session_id)
    if previous:
        if previous.get('request')!=request.model_dump(mode='json'):raise RevisionConflict('Phiên CV thuộc đầu vào khác')
        state=cv_graph.get_state({'configurable':{'thread_id':'cv:'+session_id}}).values
        if state and state.get('document'):return view(session_id)
    else:records.put('cv_sessions',session_id,{'mode':request.mode,'request':request.model_dump(mode='json')})
    cv_graph.invoke({'session_id':session_id,'request':request.model_dump(mode='json')},{'configurable':{'thread_id':'cv:'+session_id}})
    return view(session_id)


def confirm(session_id, answer):
    with _lock:
        current = view(session_id)
        if current.status != 'pending_approval':
            if current.status == 'confirmed' and answer.decision == 'approve':
                stored_document = answer.document or current.document
                if stored_document != current.document or answer.template != current.template:
                    raise RevisionConflict('CV đã lưu là bất biến. Tạo phiên mới để chỉnh sửa tiếp.')
            return current
        if answer.decision == 'approve':
            validate_edits(current.document, answer.document or current.document)
        cv_graph.invoke(Command(resume=answer.model_dump(mode='json')), {'configurable': {'thread_id': 'cv:' + session_id}})
        return view(session_id)
