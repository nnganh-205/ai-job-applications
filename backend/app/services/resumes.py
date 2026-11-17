"""Source-bound CV library. Draft publish and immutable version share a transaction."""
from uuid import uuid4
from backend.app.db import database,workflow_repository as records,profile_repository as profiles
from backend.app.db.profile_revision_repository import current_revision,RevisionConflict
from backend.app.services.profile_drafts import locked
from ai.agents.cv_agent import source_document,validate_edits
from backend.app.schemas.cv import CVDocument
from ai.agents.cv_form import get_summary_options, refine_form, validate_form_document
from backend.app.db.job_posting_repository import utc_now


def read(key,connection=None):
    if connection is None:data=records.get('resume_drafts',key)
    else:
        row=connection.execute("SELECT payload FROM kltn_app.records WHERE kind='resume_drafts' AND record_id=%s",(key,)).fetchone()
        data=row['payload'] if row else None
    if data is None:raise LookupError('Không tìm thấy CV')
    return data


def write(data,connection=None):
    from backend.app.services.resume_history import snapshot
    # Captures legacy current state before its first mutation as well as the
    # new version; snapshots omit pending proposals and editable form drafts.
    try: previous=read(data['resume_id'],connection)
    except LookupError: previous=None
    if previous: snapshot(previous,connection)
    snapshot(data,connection)
    if connection is None:return records.put('resume_drafts',data['resume_id'],data)
    return database.put_record('resume_drafts',data['resume_id'],data,connection=connection)


def start(request):
    review=None
    refinement = None
    summary_options = None
    if request.session_id:
        from ai.graph.cv_workflow import view
        session=view(request.session_id)
        if session.status=='cancelled':raise ValueError('Phiên CV đã hủy')
        document=session.document
        baseline=document
        review=session.review.model_dump(mode='json')
    else:
        profile_id = request.profile_id if request.refine_form else current_revision(request.profile_id)
        record=profiles.load_profile_record(profile_id,profiles.DEFAULT_STORAGE_DIR)
        if record is None:
            raise LookupError("Không tìm thấy hồ sơ nguồn")
        document=source_document(record.profile,profile_id,language=request.language)
        baseline=document
        if request.refine_form:
            validate_edits(baseline, baseline)
            summary_options = get_summary_options(baseline)
            document, refinement = refine_form(baseline)
    if request.presentation.photo_asset_id:
        from backend.app.services.assets import read_photo
        read_photo(request.presentation.photo_asset_id)
    (validate_form_document if refinement else validate_edits)(baseline, document)
    data=dict(schema_version=2,resume_id='resume_'+uuid4().hex,title=request.title,version=1,document=document.model_dump(mode='json'),baseline=baseline.model_dump(mode='json'),presentation=request.presentation.model_dump(),created_at=utc_now(),updated_at=utc_now(),publications={},latest_cv_id=None,review=review)
    if refinement:
        data.update(form_refinement=refinement, summary_options=summary_options)
    with locked(data['resume_id']) as connection:return write(data,connection)


def validate_document(data, document):
    baseline = CVDocument.model_validate(data['baseline'])
    validator = validate_form_document if data.get('form_refinement') else validate_edits
    from backend.app.services.resume_writer import validation_copy
    validator(baseline, validation_copy(data,document))


def preview_changes(key, request):
    data = read(key)
    if data['version'] != request.expected_version:
        raise RevisionConflict('CV đã thay đổi. Tải lại trước khi xem.')
    validate_document(data, request.document)
    from backend.app.services.cv_renderer import render_html
    return render_html(request.document, request.presentation.template, request.presentation.model_dump())


def save(key,request):
    with locked(key) as connection:
        data=read(key,connection)
        if data['version']!=request.expected_version:raise RevisionConflict('CV đã thay đổi ở phiên khác. Tải lại trước khi lưu.')
        if request.presentation.photo_asset_id:
            from backend.app.services.assets import read_photo
            read_photo(request.presentation.photo_asset_id)
        validate_document(data, request.document)
        data.update(title=request.title,document=request.document.model_dump(mode='json'),presentation=request.presentation.model_dump(),version=data['version']+1,updated_at=utc_now())
        return write(data,connection)


def publish(key,request):
    with locked(key) as connection:
        data=read(key,connection)
        if request.event_id in data['publications']:
            previous=data['publications'][request.event_id]
            if previous['draft_version']!=request.expected_version:raise RevisionConflict('Event đã dùng cho phiên bản khác')
            return previous
        if data['version']!=request.expected_version:raise RevisionConflict('CV đã thay đổi. Lưu và kiểm tra lại trước khi xuất bản.')
        document=CVDocument.model_validate(data['document'])
        validate_document(data, document)
        from backend.app.schemas.resume import Presentation
        data['presentation']=Presentation.model_validate(data['presentation']).model_dump()
        cv_id='cv_'+uuid4().hex
        version=dict(schema_version=2,cv_id=cv_id,resume_id=key,title=data['title'],document=data['document'],template=data['presentation']['template'],presentation=data['presentation'],created_at=utc_now(),draft_version=data['version'],provider='user_confirmed',source_profile_revision_id=document.source_profile_revision_id)
        if connection is not None:database.put_record('cv_versions',cv_id,version,immutable=True,connection=connection)
        else:records.put('cv_versions',cv_id,version)
        result={'cv_id':cv_id,'draft_version':data['version']}
        data['publications'][request.event_id]=result;data['latest_cv_id']=cv_id
        write(data,connection)
        return result


def duplicate(key):
    data=read(key)
    data.pop('source_edit', None)
    data.pop('edit_history', None)
    data.pop('restore_events', None)
    data.pop('archived_source_edits', None)
    data.pop('edit_completions', None)
    data.pop('pending_writer', None)
    data.update(resume_id='resume_'+uuid4().hex,title=(data['title']+' — bản sao')[:120],version=1,created_at=utc_now(),updated_at=utc_now(),publications={},latest_cv_id=None)
    with locked(data['resume_id']) as connection:return write(data,connection)


def library():
    return [{**{k:d[k] for k in ('resume_id','title','version','updated_at','latest_cv_id','presentation')}, 'has_editing_draft':d.get('source_edit',{}).get('status')=='editing', 'published_version':next((p['draft_version'] for p in d.get('publications',{}).values() if p.get('cv_id')==d.get('latest_cv_id')),None)} for d in sorted(records.list_kind('resume_drafts'),key=lambda d:d['updated_at'],reverse=True)]
