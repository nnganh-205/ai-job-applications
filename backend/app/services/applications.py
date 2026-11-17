"""Atomic application history tied to an immutable CV version and job snapshot."""
import hashlib
import json
import os
from backend.app.db import database,workflow_repository as records,profile_repository as profiles
from backend.app.db.job_posting_repository import get_posting,utc_now
from backend.app.db.profile_revision_repository import RevisionConflict
from backend.app.services.profile_drafts import locked
from backend.app.schemas.cv import CVDocument

OWNER_ID=os.getenv('WORKSPACE_OWNER_ID','local-demo')
ADVANCED={'applied','interviewing','offer','rejected','withdrawn'}


def identity(posting_id):return 'application_'+hashlib.sha256(f'{OWNER_ID}:{posting_id}'.encode()).hexdigest()[:32]


def _stored(key,connection=None):
    if connection is None:return records.get('applications',key)
    row=connection.execute("SELECT payload FROM kltn_app.records WHERE kind='applications' AND record_id=%s",(key,)).fetchone()
    return row['payload'] if row else None


def read(posting_id):
    job=get_posting(posting_id)
    if job is None:raise LookupError('Không tìm thấy công việc')
    return _stored(identity(posting_id)) or dict(application_id=identity(posting_id),posting_id=posting_id,title=job.title,company=job.company,job_snapshot_hash=job.content_hash,status='untracked',version=0,cv_id=None,profile_revision_id=None,events=[],updated_at=None,owner_id=OWNER_ID)


def update(posting_id,request):
    key=identity(posting_id)
    digest=hashlib.sha256(json.dumps(request.model_dump(mode='json'),sort_keys=True).encode()).hexdigest()
    with locked(key) as connection:
        data=_stored(key,connection) or read(posting_id)
        previous=next((e for e in data['events'] if e['event_id']==request.event_id),None)
        if previous:
            if previous['request_hash']!=digest:raise RevisionConflict('Mã thao tác đã được dùng với nội dung khác')
            return data
        if data['version']!=request.expected_version:raise RevisionConflict('Theo dõi ứng tuyển đã thay đổi. Tải lại trước khi cập nhật.')
        job=get_posting(posting_id)
        if job is None:raise LookupError('Không tìm thấy công việc')
        if job.content_hash!=request.job_content_hash:raise RevisionConflict('Tin tuyển dụng đã cập nhật. Kiểm tra JD mới trước khi tiếp tục.')
        cv_id=request.cv_id if 'cv_id' in request.model_fields_set else data['cv_id']
        profile_id=request.profile_id if 'profile_id' in request.model_fields_set else data['profile_revision_id']
        if cv_id:
            version=records.get('cv_versions',cv_id)
            if version is None:raise LookupError('CV chưa được publish hoặc không tồn tại')
            document=CVDocument.model_validate(version['document'])
            source=document.source_profile_revision_id
            if request.profile_id and request.profile_id!=source:raise RevisionConflict('CV và hồ sơ nguồn không khớp nhau')
            profile_id=source
        if profile_id and profiles.load_profile_record(profile_id,profiles.DEFAULT_STORAGE_DIR) is None:raise LookupError('Hồ sơ nguồn chưa được xác nhận')
        status=request.status
        keep_submission=status=='opened_source' and data['status'] in ADVANCED
        if not keep_submission:
            data.update(cv_id=cv_id,profile_revision_id=profile_id,job_snapshot_hash=job.content_hash,status=status)
        event=dict(event_id=request.event_id,request_hash=digest,action=request.status,status=data['status'],cv_id=cv_id,profile_revision_id=profile_id,job_snapshot_hash=job.content_hash,at=utc_now(),origin='user_link_activation' if request.status=='opened_source' else 'user_report')
        data['events'].append(event)
        data.update(version=data['version']+1,updated_at=event['at'],title=job.title,company=job.company)
        if connection is None:records.put('applications',key,data)
        else:database.put_record('applications',key,data,connection=connection)
        return data


def list_all():
    return sorted((r for r in records.list_kind('applications') if r.get('owner_id')==OWNER_ID),key=lambda r:r['updated_at'],reverse=True)
