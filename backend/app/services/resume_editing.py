"""Durable, CV-scoped form editing. Never advances the shared profile head."""
from copy import deepcopy
from uuid import uuid4
from backend.app.services import resumes
from backend.app.services.profile_drafts import locked
from backend.app.db import profile_repository as profiles
from backend.app.db.profile_revision_repository import RevisionConflict
from backend.app.db.job_posting_repository import utc_now
from backend.app.schemas.profile import MasterProfile, SourceEvidence
from ai.agents.cv_agent import source_document, validate_edits

KINDS = ('experience', 'project', 'education', 'involvement', 'skills')
TEXT_FIELDS = ('description', 'responsibilities', 'achievements', 'objectives', 'contributions', 'outcomes', 'details', 'academic_achievements', 'relevant_coursework', 'original_bullets')


def editable_profile(data):
    """Use the exact source revision plus the sentences actually visible on this CV.

    Merged bullets go into one editable description, never split into invented facts.
    Original source and CV snapshots remain in the editing packet for provenance.
    """
    document = data['document']
    source = profiles.load_profile_record(document['source_profile_revision_id'], profiles.DEFAULT_STORAGE_DIR)
    if source is None:
        raise LookupError('Không tìm thấy hồ sơ nguồn của CV')
    profile = source.profile.model_dump(mode='json')
    profile['contact'] = deepcopy(document['contact'])
    profile['summary'] = document['summary']['text'] if document.get('summary') else None
    sections = {s['kind']: s for s in document['sections']}
    for kind in KINDS:
        originals = {e.get('id') or f'/{kind}/{i}': e for i, e in enumerate(profile[kind])}
        entries = []
        for current in sections.get(kind, {}).get('entries', []):
            entry = deepcopy(originals.get(current['source_entry_id']))
            if entry is None:
                raise ValueError('Không đối chiếu được mục CV với hồ sơ nguồn; chưa mở bản sửa.')
            entry['id'] = current['source_entry_id']
            if kind != 'skills':
                for field in TEXT_FIELDS:
                    if field in entry:
                        entry[field] = []
                if 'original_description' in entry:
                    entry['original_description'] = None
                fallback = 'details' if kind == 'education' else 'description'
                for bullet in current['bullets']:
                    fields = {ref.split('/')[3] for ref in bullet['source_refs'] if len(ref.split('/')) > 3}
                    field = next(iter(fields)) if len(fields) == 1 else fallback
                    if field not in TEXT_FIELDS or field not in entry:
                        # Scalars/tools/URLs already exist in the source metadata. Keep
                        # an edited or merged sentence too when it differs from that value.
                        values = entry.get(field)
                        if bullet['text'] == values or isinstance(values, list) and bullet['text'] in values:
                            continue
                        field = fallback
                    if bullet['text'] not in entry[field]:
                        entry[field].append(bullet['text'])
            entries.append(entry)
        profile[kind] = entries
    return MasterProfile.model_validate(profile)


def read(key):
    packet = resumes.read(key).get('source_edit')
    if not packet:
        raise LookupError('CV chưa có bản nháp chỉnh sửa')
    return deepcopy(packet)


def begin(key, request):
    with locked(key) as connection:
        data = resumes.read(key, connection)
        if data['version'] != request.expected_version:
            raise RevisionConflict('CV đã thay đổi. Tải lại trước khi chỉnh sửa.')
        packet = data.get('source_edit')
        if packet and packet['status'] == 'editing':
            if packet['resume_version'] != data['version']:
                raise RevisionConflict('Bản nháp sửa thuộc phiên bản CV cũ. Nội dung đã lưu vẫn được giữ; cần đối chiếu trước khi tiếp tục.')
            return deepcopy(packet)
        profile = editable_profile(data).model_dump(mode='json')
        packet = dict(draft_id='draft_' + uuid4().hex, resume_id=key, resume_version=data['version'], version=1,
                      status='editing', profile=profile, initial_profile=deepcopy(profile),
                      source_document=deepcopy(data['document']), updated_at=utc_now())
        data['source_edit'] = packet
        resumes.write(data, connection)
        return deepcopy(packet)


def save(key, request):
    with locked(key) as connection:
        data = resumes.read(key, connection)
        packet = data.get('source_edit')
        if not packet or packet['status'] != 'editing' or packet['version'] != request.expected_version or packet['resume_version'] != data['version']:
            raise RevisionConflict('CV hoặc bản nháp đã thay đổi. Tải lại trước khi lưu.')
        # Existing IDs are stable; new entries get IDs at confirmation.
        packet.update(profile=request.profile.model_dump(mode='json'), version=packet['version'] + 1, updated_at=utc_now())
        resumes.write(data, connection)
        return deepcopy(packet)


def complete(key, request):
    with locked(key) as connection:
        data = resumes.read(key, connection)
        previous = data.get('edit_completions', {}).get(request.event_id)
        if previous:
            if previous['draft_version'] != request.expected_version or previous['draft_id'] != request.draft_id:
                raise RevisionConflict('Yêu cầu hoàn tất đã được dùng cho bản nháp khác.')
            return data
        packet = data.get('source_edit')
        if not packet or packet['draft_id'] != request.draft_id or packet['status'] != 'editing' or packet['version'] != request.expected_version or packet['resume_version'] != data['version']:
            raise RevisionConflict('CV hoặc bản nháp đã thay đổi. Nội dung chưa được ghi đè.')
        profile = MasterProfile.model_validate(packet['profile'])
        for kind in KINDS:
            used = set()
            for entry in getattr(profile, kind):
                if not entry.id:
                    entry.id = kind + '_' + uuid4().hex
                if entry.id in used:
                    raise ValueError('Mục CV có mã bị trùng; chưa lưu thay đổi.')
                used.add(entry.id)
        source_id = 'cvlocal_' + uuid4().hex
        baseline = source_document(profile, source_id, job_id=data['document'].get('job_analysis_id'), language=data['document']['language'])
        # Reuse current, approved wording and headers for untouched entries. New
        # references point at the confirmed CV-local profile, not stale indexes.
        old_entries = {(s['kind'], e['source_entry_id']): e for s in data['document']['sections'] for e in s['entries']}
        initial = { (kind, e['id']): e for kind in KINDS for e in packet['initial_profile'][kind] }
        current = { (kind, e.id): e.model_dump(mode='json') for kind in KINDS for e in getattr(profile, kind) }
        document = baseline.model_copy(deep=True)
        for section in document.sections:
            for entry in section.entries:
                identity = (section.kind, entry.source_entry_id)
                old = old_entries.get(identity)
                if old and initial.get(identity) != current.get(identity):
                    # A metadata edit must not reintroduce source bullets that
                    # this CV deliberately omitted during tailoring.
                    before = initial.get(identity, {})
                    after = current[identity]
                    changed_fields = {field for field in after if after[field] != before.get(field)}
                    visible_texts = {b['text'] for b in old['bullets']}
                    entry.bullets = [b for b in entry.bullets if b.text in visible_texts or any(
                        len(ref.split('/')) > 3 and ref.split('/')[3] in changed_fields for ref in b.source_refs)]
                if old and initial.get(identity) == current.get(identity):
                    by_text = {b.text: b for b in entry.bullets}
                    if any(b['text'] not in by_text for b in old['bullets']):
                        raise ValueError('Có câu CV chưa ánh xạ được nguồn. Bản nháp được giữ để đối chiếu.')
                    entry.bullets = [by_text[b['text']].model_copy(deep=True) for b in old['bullets']]
                    entry.title, entry.subtitle, entry.period = old['title'], old.get('subtitle'), old.get('period')
                    base_entry = next(e for s in baseline.sections if s.kind == section.kind for e in s.entries if e.source_entry_id == entry.source_entry_id)
                    base_entry.title, base_entry.subtitle, base_entry.period = entry.title, entry.subtitle, entry.period
        validate_edits(baseline, document)
        # Validate before any persistent change. PostgreSQL stores source + CV in
        # the same transaction; shared Master Profile revisions stay untouched.
        profiles.save_master_profile(source_id, profile, profiles.DEFAULT_STORAGE_DIR,
            evidence=[SourceEvidence(field_path='cv', source_id=key, origin='user_confirmation', quote=profile.model_dump_json())], connection=connection)
        data.setdefault('edit_history', []).append(dict(version=data['version'], document=deepcopy(data['document']), baseline=deepcopy(data['baseline']), presentation=deepcopy(data['presentation']), title=data['title'], source_edit=deepcopy(packet), created_at=utc_now()))
        data.update(document=document.model_dump(mode='json'), baseline=baseline.model_dump(mode='json'), version=data['version'] + 1, updated_at=utc_now())
        data.pop('pending_writer', None)
        data.pop('form_refinement', None)
        data.pop('summary_options', None)
        data.pop('writer_approvals', None)
        data['source_edit']['status'] = 'completed'
        data.setdefault('edit_completions', {})[request.event_id] = dict(draft_id=request.draft_id, draft_version=request.expected_version)
        return resumes.write(data, connection)
