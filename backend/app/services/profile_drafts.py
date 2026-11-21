"""Durable form drafts with compare-and-set and atomic confirmation in PostgreSQL."""
from contextlib import contextmanager
from threading import RLock
from uuid import uuid4
from backend.app.db import database, profile_repository as profiles, profile_revision_repository as revisions, workflow_repository as records
from backend.app.db.job_posting_repository import utc_now
from backend.app.schemas.profile import MasterProfile, SourceEvidence
from ai.agents.profile_agent import assign_profile_metadata

_lock = RLock()


@contextmanager
def locked(draft_id):
    records.safe_key(draft_id)
    if database.enabled():
        with database.connect() as connection, connection.transaction():
            connection.execute('SELECT pg_advisory_xact_lock(hashtext(%s))', ('profile_draft:' + draft_id,))
            yield connection
    else:
        with _lock:
            yield None


def read(draft_id, connection=None):
    if connection is not None:
        draft = database.get_record('profile_drafts', draft_id, connection=connection)
    else:
        draft = records.get('profile_drafts', draft_id)
    if draft is None:
        raise LookupError('Không tìm thấy bản nháp hồ sơ')
    return draft


def write(draft, connection=None):
    if connection is not None:
        database.put_record('profile_drafts', draft['draft_id'], draft, connection=connection)
    else:
        records.put('profile_drafts', draft['draft_id'], draft)
    return draft


def start(base_id=None, presentation=None):
    if base_id:
        base_id = revisions.current_revision(base_id)
        profile = profiles.load_profile_record(base_id, profiles.DEFAULT_STORAGE_DIR).profile
    else:
        from backend.app.core.workspace import owner_id
        seed = profiles.load_profile_record('account_' + owner_id(), profiles.DEFAULT_STORAGE_DIR)
        contact = {field: getattr(seed.profile.contact, field) for field in ('full_name', 'email')} if seed else {}
        profile = MasterProfile(contact=contact, experience=[], project=[], education=[], involvement=[], skills=[])
    draft = dict(draft_id='draft_' + uuid4().hex, base_profile_id=base_id, version=1, status='editing', profile=profile.model_dump(mode='json'), updated_at=utc_now(), confirmed_profile_id=None, confirmation_event_id=None)
    if presentation is not None:draft['presentation']=presentation.model_dump(mode='json')
    with locked(draft['draft_id']) as connection:
        return write(draft, connection)


def from_extraction(thread_id, state):
    """Open an editable form without confirming the imported CV's facts."""
    from uuid import NAMESPACE_URL, uuid5
    if not state or state.get('status') != 'pending_confirmation':
        raise LookupError('Không tìm thấy kết quả trích xuất đang chờ kiểm tra')
    profile = MasterProfile.model_validate(state['profile'])
    draft_id = 'draft_' + uuid5(NAMESPACE_URL, 'kltn:cv-import:' + thread_id).hex
    with locked(draft_id) as connection:
        try:
            return read(draft_id, connection)
        except LookupError:
            pass
        draft = dict(
            draft_id=draft_id, base_profile_id=None, version=1, status='editing',
            profile=profile.model_dump(mode='json'), updated_at=utc_now(),
            confirmed_profile_id=None, confirmation_event_id=None,
            import_thread_id=thread_id, source_text=state.get('resume_text'),
            source_filename=state.get('filename'),
            warnings=state.get('warnings', []), evidence=state.get('evidence', []),
        )
        return write(draft, connection)


def save(draft_id, request):
    with locked(draft_id) as connection:
        draft = read(draft_id, connection)
        if draft['status'] != 'editing' or draft['version'] != request.expected_version:
            raise revisions.RevisionConflict('Bản nháp đã thay đổi hoặc đã xác nhận. Tải lại trước khi sửa.')
        draft.update(profile=request.profile.model_dump(mode='json'), version=draft['version'] + 1, updated_at=utc_now())
        if request.presentation is not None:draft['presentation']=request.presentation.model_dump(mode='json')
        return write(draft, connection)


def confirm(draft_id, request):
    with locked(draft_id) as connection:
        draft = read(draft_id, connection)
        if draft['status'] == 'confirmed' and draft['confirmation_event_id'] == request.event_id:
            return draft
        if draft['status'] != 'editing' or draft['version'] != request.expected_version:
            raise revisions.RevisionConflict('Bản nháp đã thay đổi hoặc đã xác nhận. Tải lại trước khi duyệt.')
        profile = assign_profile_metadata(MasterProfile.model_validate(draft['profile']), preserve_ids=True)
        base_id = draft['base_profile_id']
        before = profiles.load_profile_record(base_id, profiles.DEFAULT_STORAGE_DIR).profile.model_dump(mode='json') if base_id else {}
        after = profile.model_dump(mode='json')
        changed = [key for key, value in after.items() if before.get(key) != value]
        quote = profile.model_dump_json()
        if base_id and not changed:
            confirmed_id = base_id
        elif base_id:
            confirmed_id = revisions.commit_revision(base_id, profile, session_id=draft_id, action_id=request.event_id, changed_paths=changed, quote=quote, connection=connection)
        else:
            confirmed_id = 'profile_' + draft_id.removeprefix('draft_')
            metadata = {}
            evidence = [SourceEvidence(field_path=key, source_id=draft_id, origin='user_confirmation', quote=quote) for key in changed]
            if draft.get('import_thread_id'):
                from ai.agents.profile_agent import confirmation_evidence, validate_against_source
                source_text = draft.get('source_text') or ''
                evidence = confirmation_evidence(profile, source_text, draft['import_thread_id'])
                metadata = dict(source_text=source_text, source_filename=draft.get('source_filename'),
                                warnings=validate_against_source(profile, source_text))
            profiles.save_master_profile(confirmed_id, profile, profiles.DEFAULT_STORAGE_DIR, evidence=evidence, connection=connection, **metadata)
        draft.update(profile=after, status='confirmed', confirmed_profile_id=confirmed_id, confirmation_event_id=request.event_id, version=draft['version'] + 1, updated_at=utc_now())
        return write(draft, connection)


def list_editing():
    if database.enabled():
        items = [row["data"] for row in database.list_records("profile_drafts")]
    else:
        items = records.list_kind('profile_drafts')
    return [{"draft_id": item["draft_id"], "full_name": item["profile"]["contact"].get("full_name"), "updated_at": item["updated_at"]} for item in items if item["status"] == "editing"]
