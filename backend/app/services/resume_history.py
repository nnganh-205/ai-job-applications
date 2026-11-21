"""Immutable CV snapshots; restoring always creates a later version."""
from copy import deepcopy
from backend.app.core.workspace import record_kind
from backend.app.db import database, workflow_repository as records
from backend.app.db.profile_revision_repository import RevisionConflict
from backend.app.db.job_posting_repository import utc_now
from backend.app.schemas.cv import CVDocument
from backend.app.schemas.resume import Presentation

FIELDS = ('resume_id','version','title','document','baseline','presentation','updated_at','created_at','writer_approvals','form_refinement','summary_options','review')
KIND = 'resume_history'


def snapshot(data, connection=None):
    key = f"{data['resume_id']}:{data['version']}"
    value = deepcopy({k:data[k] for k in FIELDS if k in data})
    if connection is not None:
        database.put_record(KIND,key,value,immutable=True,connection=connection)
    elif records.get(KIND,key) is None:
        records.put(KIND,key,value)


def versions(key):
    from backend.app.services import resumes
    data = resumes.read(key)
    # Older projects have only the snapshots recorded at form completion.
    found = {h['version']:h for h in data.get('edit_history',[]) if 'document' in h and 'baseline' in h}
    if database.enabled():
        with database.connect() as c:
            rows=c.execute("SELECT payload FROM kltn_app.records WHERE kind=%s AND payload->>'resume_id'=%s",(record_kind(KIND),key)).fetchall()
        found.update({r['payload']['version']:r['payload'] for r in rows})
    else:
        found.update({h['version']:h for h in records.list_kind(KIND) if h.get('resume_id')==key})
    found[data['version']] = {k:data[k] for k in FIELDS if k in data}
    return data, found


def is_restorable(value):
    from backend.app.services import resumes
    try:
        Presentation.model_validate(value['presentation'])
        resumes.validate_document(value,CVDocument.model_validate(value['document']))
        return True
    except (ValueError,KeyError): return False


def listing(key):
    data, found=versions(key)
    return dict(archived_drafts=[{k:d.get(k) for k in ('draft_id','version','updated_at')} for d in data.get('archived_source_edits',[])], current_version=data['version'], editing_draft=(dict(draft_id=data['source_edit']['draft_id'],version=data['source_edit']['version'],updated_at=data['source_edit']['updated_at']) if data.get('source_edit',{}).get('status')=='editing' else None), versions=[dict(version=n,title=h['title'],created_at=h.get('updated_at') or h.get('created_at'),current=n==data['version'],restorable=is_restorable(h)) for n,h in sorted(found.items(),reverse=True)])


def selected(key, version):
    _, found=versions(key)
    if version not in found: raise LookupError('Không có phiên bản CV này trong lịch sử đã lưu.')
    return deepcopy(found[version])


def restore(key, request):
    from backend.app.services import resumes
    from backend.app.services.profile_drafts import locked
    target=selected(key,request.target_version)
    if not is_restorable(target): raise ValueError('Bản cũ thiếu dữ liệu kiểm chứng nguồn. Bạn vẫn có thể xem lại, nhưng chưa thể khôi phục an toàn.')
    with locked(key) as c:
        data=resumes.read(key,c)
        event=data.get('restore_events',{}).get(request.event_id)
        if event:
            if event['target_version']!=request.target_version or event['expected_version']!=request.expected_version: raise RevisionConflict('Yêu cầu khôi phục đã được dùng cho phiên bản khác.')
            return data
        if data['version']!=request.expected_version: raise RevisionConflict('CV đã thay đổi. Tải lại lịch sử trước khi khôi phục.')
        if request.target_version==data['version']: raise ValueError('Đây đã là phiên bản hiện tại.')
        draft=data.get('source_edit')
        if draft and draft['status']=='editing':
            if request.editing_draft_version!=draft['version']: raise RevisionConflict('Có bản nháp chỉnh sửa đang mở hoặc vừa thay đổi. Xác nhận lưu lại bản nháp trước khi khôi phục.')
            data.setdefault('archived_source_edits',[]).append(deepcopy(draft))
        # Keep publications, completed edits and prior history. Restore only the
        # validated content and its matching source-validation metadata.
        for name in FIELDS:
            if name in {'resume_id','version','updated_at','created_at'}: continue
            if name in target: data[name]=deepcopy(target[name])
            else: data.pop(name,None)
        data.pop('source_edit',None);data.pop('pending_writer',None)
        data['version']+=1;data['updated_at']=utc_now()
        data.setdefault('restore_events',{})[request.event_id]=dict(target_version=request.target_version,expected_version=request.expected_version,result_version=data['version'])
        return resumes.write(data,c)


def archived_draft(key, draft_id):
    from backend.app.services import resumes
    data=resumes.read(key)
    found=next((d for d in data.get('archived_source_edits',[]) if d['draft_id']==draft_id),None)
    if found is None: raise LookupError('Không tìm thấy bản nháp lưu giữ của CV này.')
    return deepcopy(found)
