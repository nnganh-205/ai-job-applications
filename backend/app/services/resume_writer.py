"""Versioned AI Writer previews and explicitly approved CV bullet replacements."""
from copy import deepcopy
from uuid import uuid4
from typing import Literal
import re
from collections import Counter
from pydantic import Field
from backend.app.schemas.profile import StrictModel
from backend.app.schemas.cv import CVDocument
from backend.app.services.cv_writer import WriterRequest, write_bullets
from backend.app.services import resumes
from backend.app.services.profile_drafts import locked
from backend.app.db.profile_revision_repository import RevisionConflict
from backend.app.db.job_posting_repository import utc_now

class ResumeWriterRequest(StrictModel):
    expected_version: int = Field(ge=1)
    section: str
    entry_id: str
    style: str = 'professional'
    count: int = Field(default=4,ge=1,le=6)
    issues: list[Literal['action','pronoun','punctuation','length','specific']] = Field(default_factory=list,max_length=5)

class ResumeWriterApply(StrictModel):
    expected_version: int = Field(ge=1)
    proposal_id: str
    selected: list[int] = Field(min_length=1,max_length=6)
    mode: Literal['replace','append'] = 'replace'


def find_entry(document,kind,entry_id):
    return next((entry for section in document['sections'] if section['kind']==kind for entry in section['entries'] if entry['source_entry_id']==entry_id),None)


def preview(key,request):
    data=resumes.read(key)
    if data['version']!=request.expected_version: raise RevisionConflict('CV đã thay đổi. Lưu rồi tạo lại đề xuất.')
    entry=find_entry(data['document'],request.section,request.entry_id)
    if not entry: raise LookupError('Không tìm thấy mục CV')
    tools=[];results=[];work=[]
    for bullet in entry['bullets']:
        refs=' '.join(bullet['source_refs'])
        target=tools if any('/'+field+'/' in refs for field in ('technologies','technologies_used','items')) else results if any('/'+field+'/' in refs for field in ('outcomes','achievements','academic_achievements')) else work
        target.append(bullet['text'])
    result=write_bullets(WriterRequest(section=request.section,entry=dict(role=entry['title'],company=entry.get('subtitle')),text='\n'.join(work),tools='\n'.join(tools),results='\n'.join(results),style=request.style,count=request.count,issues=request.issues))
    with locked(key) as connection:
        current=resumes.read(key,connection)
        if current['version']!=request.expected_version: raise RevisionConflict('CV đã thay đổi trong lúc AI viết. Tạo lại đề xuất.')
        token='writer_'+uuid4().hex
        current['pending_writer']=dict(id=token,version=request.expected_version,section=request.section,entry_id=request.entry_id,original=deepcopy(entry['bullets']),result=result)
        resumes.write(current,connection)
    return {**result,'proposal_id':token}


def apply(key,request):
    with locked(key) as connection:
        data=resumes.read(key,connection);pending=data.get('pending_writer')
        if data['version']!=request.expected_version or not pending or pending['id']!=request.proposal_id or pending.get('version')!=data['version']: raise RevisionConflict('Đề xuất đã hết hiệu lực. Tạo lại theo CV hiện tại.')
        entry=find_entry(data['document'],pending['section'],pending['entry_id'])
        if not entry or entry['bullets']!=pending['original']: raise RevisionConflict('Nội dung đã thay đổi; chưa áp dụng đề xuất cũ.')
        selected=list(dict.fromkeys(request.selected))
        if any(i<0 or i>=len(pending['result']['bullets']) for i in selected): raise ValueError('Lựa chọn bullet không hợp lệ')
        # Each writer fact representing work maps back to the exact input bullet(s).
        original=entry['bullets']
        all_refs=list(dict.fromkeys(ref for b in original for ref in b['source_refs']))
        proposed=[];replaced=set();insertions={}
        for i in selected:
            bullet=pending['result']['bullets'][i]
            normalize=lambda text: re.sub(r'^(?:[•*]\s*|-\s+|\d+[.)]\s+)', '', text.strip())
            quotes=Counter(normalize(q) for q in bullet['sources'])
            matched=[]
            for j,old in enumerate(original):
                text=normalize(old['text'])
                if j not in replaced and quotes[text]:
                    matched.append(j);quotes[text]-=1
            replaced.update(matched)
            refs=list(dict.fromkeys(ref for j in matched for ref in original[j]['source_refs']))
            # Old preview packets may not contain a per-fact quote mapping.
            replacements=[dict(text=text,source_refs=refs or all_refs) for text in (bullet.get('replacement_lines') or [bullet['text']])]
            proposed.extend(replacements)
            insertions.setdefault(min(matched) if matched else None, []).extend(replacements)
        if request.mode=='append':
            proposed=deepcopy(original)+[b for b in proposed if b['text'] not in {old['text'] for old in original}]
        elif replaced:
            # Selecting one rewrite must not delete other bullets or overflow facts.
            proposed=[b for j,old in enumerate(original)
                      for b in (insertions[j] if j in insertions else [] if j in replaced else [deepcopy(old)])] + insertions.get(None, [])
        else:
            # Old packets without exact quote mapping can only add, not erase.
            proposed=deepcopy(original)+[b for b in proposed if b['text'] not in {old['text'] for old in original}]
        # Preserve the original validation source across multiple approved rewrites.
        validation=deepcopy(original)
        for approval in reversed(data.get('writer_approvals',[])):
            if approval['entry_id']==pending['entry_id'] and approval['section']==pending['section'] and approval['proposed']==original:
                validation=deepcopy(approval['original']);break
        data.setdefault('writer_approvals',[]).append(dict(section=pending['section'],entry_id=pending['entry_id'],original=validation,proposed=deepcopy(proposed),approved_at=utc_now()))
        entry['bullets']=proposed
        resumes.validate_document(data,CVDocument.model_validate(data['document']))
        data.pop('pending_writer',None)
        data.update(version=data['version']+1,updated_at=utc_now())
        return resumes.write(data,connection)


def validation_copy(data,document):
    result=document.model_copy(deep=True)
    for section in result.sections:
        for entry in section.entries:
            current=[b.model_dump(mode='json') for b in entry.bullets]
            approval=next((a for a in reversed(data.get('writer_approvals',[])) if a['section']==section.kind and a['entry_id']==entry.source_entry_id and a['proposed']==current),None)
            if approval:
                from backend.app.schemas.cv import CVBullet
                entry.bullets=[CVBullet.model_validate(b) for b in approval['original']]
    return result
