"""Freshness is metadata around immutable CV inputs, never a replacement input."""
import hashlib
import json
from backend.app.db import workflow_repository as records


def content_hash(document):
    visible={k:v for k,v in document.items() if k not in {'source_profile_revision_id','job_analysis_id'}}
    return hashlib.sha256(json.dumps(visible,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()


def version_status(cv_id, version=None):
    version=version or records.get('cv_versions',cv_id)
    if version is None: raise LookupError('Không tìm thấy phiên bản CV.')
    key=version.get('resume_id')
    current=records.get('resume_drafts',key) if key else None
    published_version=version.get('draft_version')
    latest=None
    if current:
        latest_id=current.get('latest_cv_id')
        if latest_id:
            latest_record=records.get('cv_versions',latest_id)
            if latest_record and latest_record.get('draft_version')==current['version']: latest=latest_id
    return dict(cv_id=cv_id,resume_id=key,source_version=published_version,title=version.get('title'),
                current_version=current['version'] if current else None,
                version_changed=bool(current and published_version!=current['version']),
                content_stale=bool(current and content_hash(version['document'])!=content_hash(current['document'])),
                has_editing_draft=bool(current and current.get('source_edit',{}).get('status')=='editing'),
                latest_published_cv_id=latest, content_hash=content_hash(version['document']))
