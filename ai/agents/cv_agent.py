"""Agent 5: grounded selection and review. Rendering and persistence stay outside AI."""

import json
import re
from typing import Literal
from pydantic import Field,create_model

from ai.llm.ollama_client import OllamaSchemaError, request_structured
from backend.app.schemas.cv import CVBullet, CVDocument, CVEntry, CVPlan, CVSection,CVReview
from backend.app.schemas.profile import MasterProfile


HEADINGS = {
    'en': ['Experience', 'Projects', 'Education', 'Activities', 'Skills'],
    'vi': ['Kinh nghiệm', 'Dự án', 'Học vấn', 'Hoạt động', 'Kỹ năng'],
}
HIDDEN_SOURCE_FIELDS = {
    'experience': {'technologies_used'},
    'project': set(),
}
TITLE_FIELDS = {
    'certifications': ('name',),
    'awards': ('title',),
    'references': ('full_name',),
    'experience': ('job_title',),
    'project': ('project_name',),
    'education': ('institution',),
    'involvement': ('role', 'activity_name'),
}


def source_document(profile: MasterProfile, profile_id: str, job_id=None, language='en') -> CVDocument:
    sections = []
    headings = dict(zip(('experience', 'project', 'education', 'involvement', 'skills'), HEADINGS[language]))
    headings.update(dict(certifications='Chứng chỉ',awards='Danh hiệu và giải thưởng',references='Người giới thiệu') if language=='vi' else dict(certifications='Certifications',awards='Honors and awards',references='References'))
    for kind in ('education', 'experience', 'project', 'involvement', 'skills', 'certifications', 'awards', 'references'):
        heading = headings[kind]
        entries = []
        for index, entry in enumerate(getattr(profile, kind)):
            data = entry.model_dump()
            # Extraction can leave an all-null optional entry. A section label
            # alone is not candidate content and must not become a phantom CV fact.
            meaningful=lambda value: bool(value.strip()) if isinstance(value,str) else any(isinstance(item,str) and item.strip() for item in value) if isinstance(value,list) else False
            hidden_fields = HIDDEN_SOURCE_FIELDS.get(kind, set())
            if not any(meaningful(value) for key,value in data.items() if key != 'id' and key not in hidden_fields):
                continue
            if kind=='skills' and not any(item.strip() for item in entry.items):
                continue
            root = f'/{kind}/{index}'
            if kind == 'skills':
                title, subtitle = entry.group or heading, None
                bullets = [CVBullet(text=', '.join(entry.items), source_refs=[f'{root}/items/{n}' for n in range(len(entry.items))])] if entry.items else []
            else:
                title = next((data.get(key) for key in TITLE_FIELDS[kind] if data.get(key)), heading)
                subtitle_keys = ('company', 'degree', 'field_of_study', 'major', 'position', 'organization', 'issuer', 'location') + (('role',) if kind == 'project' else ())
                subtitle = ' · '.join(dict.fromkeys(data[key] for key in subtitle_keys if data.get(key))) or None
                bullets, seen = [], set()
                for key in ('description', 'responsibilities', 'achievements', 'objectives', 'contributions', 'outcomes', 'details', 'academic_achievements', 'relevant_coursework', 'technologies', 'technologies_used', 'original_bullets', 'original_description', 'gpa', 'github_url', 'demo_url', 'project_url', 'email', 'phone', 'relationship'):
                    if key in hidden_fields:
                        continue
                    value = data.get(key)
                    if key == 'technologies' and isinstance(value, list):
                        remaining = [(n, text) for n, text in enumerate(value) if text and text.strip()]
                        if remaining:
                            bullets.append(CVBullet(text=', '.join(text for _, text in remaining), source_refs=[f'{root}/{key}/{n}' for n, _ in remaining]))
                        continue
                    values = list(enumerate(value)) if isinstance(value, list) else [(None, value)]
                    for n, text in values:
                        if isinstance(text, str) and text.strip() and text not in seen:
                            seen.add(text)
                            bullets.append(CVBullet(text=text, source_refs=[f'{root}/{key}' + (f'/{n}' if n is not None else '')]))
            period = ' – '.join(str(value) for value in (data.get('start_date'), data.get('end_date') or data.get('graduation_date') or ('Present' if data.get('is_current') else None)) if value) or None
            period = period or data.get('date') or data.get('period')
            entries.append(CVEntry(source_entry_id=entry.id or root, title=title, subtitle=subtitle, period=period, bullets=bullets))
        if entries:
            sections.append(CVSection(kind=kind, heading=heading, entries=entries))
    return CVDocument(source_profile_revision_id=profile_id, job_analysis_id=job_id, language=language,
                      contact=profile.contact, summary=CVBullet(text=profile.summary, source_refs=['/summary']) if profile.summary else None, sections=sections)


def bullet_catalog(document):
    return {bullet.source_refs[0]: bullet for section in document.sections for entry in section.entries for bullet in entry.bullets}


def review_text_valid(original: str, proposed: str) -> bool:
    from ai.agents.cv_grounding import grounded_rewrite
    return grounded_rewrite(original,proposed)


def plan_cv(document: CVDocument, requirements=None, mode='generate'):
    catalog = bullet_catalog(document)
    if not catalog:
        raise ValueError('Hồ sơ chưa có nội dung chuyên môn để tạo CV.')
    from ai.prompts.cv_prompt import CV_REVIEW_PROMPT
    from ai.agents.cv_grounding import job_brief,catalog_context
    from backend.app.services.ai_progress import report
    report('cv_review','Đang chọn nội dung và rà soát CV')
    selected=list(catalog)
    selection_warnings=[]
    tailored=mode=='generate' and requirements is not None
    if tailored:
        from ai.agents.cv_selection import select_for_job
        report('cv_select','Đang đối chiếu nội dung CV với từng yêu cầu công việc')
        selected,selection_warnings=select_for_job(catalog,requirements,request_structured)
        if not selected:
            return document.model_copy(deep=True),CVReview(items=[],warnings=selection_warnings)
    active_catalog={ref:catalog[ref] for ref in selected}
    prompt = CV_REVIEW_PROMPT
    payload={'mode': mode, 'catalog': {key: value.text for key, value in active_catalog.items()},
             'catalog_context':{key:value for key,value in catalog_context(document).items() if key in active_catalog},
             'job_requirements':job_brief(requirements), 'review_language':document.language}
    schema=CVPlan
    if tailored:
        # Preserve CVPlan v1 wire shape while preventing the review stage from
        # selecting a different source set or adding unrelated original bullets.
        payload['selected_source_refs']=selected
        schema=create_model('SelectedSourceCVPlan',__base__=CVPlan,
                            selected_refs=(list[Literal[tuple(selected)]],Field(min_length=len(selected),max_length=len(selected),json_schema_extra={'const':selected})))
    plan = request_structured([
        {'role': 'system', 'content': prompt},
        {'role': 'user', 'content': json.dumps(payload, ensure_ascii=False)},
    ], schema, task='cv')
    report('cv_validate','Đang kiểm tra nguồn và các đề xuất viết lại')
    if len(plan.review.items)>5:raise OllamaSchemaError('AI trả quá nhiều câu sửa; bản nguồn được giữ nguyên, hãy thử lại.')
    if not plan.selected_refs or any(ref not in active_catalog for ref in plan.selected_refs) or (tailored and plan.selected_refs!=selected):
        raise OllamaSchemaError('Qwen chọn nguồn không tồn tại. CV chưa được lưu; vui lòng thử lại.')
    valid_reviews = []
    for item in plan.review.items:
        source = active_catalog.get(item.source_ref)
        if source is None or source.text != item.original_text or not review_text_valid(item.original_text, item.proposed_text):
            plan.review.warnings.append('Đã loại đề xuất không khớp nguồn hoặc có nguy cơ thêm dữ kiện, thay đổi số liệu, phủ định hay mức độ kinh nghiệm.')
            continue
        valid_reviews.append(item)
    plan.review.items = valid_reviews
    # Generation is extractive: rewrites remain unverified suggestions until a user applies them.
    plan.review.warnings.extend(selection_warnings)
    rank = {ref: index for index, ref in enumerate(selected)}
    result = document.model_copy(deep=True)
    for section in result.sections:
        for entry in section.entries:
            entry.bullets = sorted((bullet for bullet in entry.bullets if bullet.source_refs[0] in rank), key=lambda bullet: rank[bullet.source_refs[0]])
        section.entries = [entry for entry in section.entries if entry.bullets or section.kind in {'education','certifications','awards','references'}]
    result.sections = [section for section in result.sections if section.entries]
    plan.review.warnings.extend([
        'CV tự động chỉ chọn/sắp xếp nội dung nguồn; đề xuất viết lại cần bạn đối chiếu và duyệt.',
        'Kiểm tra ATS ở mức bố cục và khả năng đọc văn bản, không bảo đảm kết quả của mọi ATS.',
    ])
    return result, plan.review


def validate_edits(original: CVDocument, edited: CVDocument):
    """Edits affect this CV version only; no invented source links or metadata."""
    if original.model_dump(exclude={'sections', 'summary'}) != edited.model_dump(exclude={'sections', 'summary'}):
        raise ValueError('Không sửa thông tin liên hệ/nguồn trong CV; hãy cập nhật Master Profile trước.')
    if edited.summary != original.summary:
        raise ValueError('Summary giữ nguyên nguồn; cập nhật Master Profile nếu cần thay đổi.')
    originals = {entry.source_entry_id: (section.kind, entry) for section in original.sections for entry in section.entries}
    seen = set()
    for section in edited.sections:
        for entry in section.entries:
            if entry.source_entry_id not in originals or entry.source_entry_id in seen:
                raise ValueError('Mục CV không thuộc bản nháp nguồn hoặc bị trùng.')
            seen.add(entry.source_entry_id)
            kind, source = originals[entry.source_entry_id]
            if section.kind != kind or (entry.title, entry.subtitle, entry.period) != (source.title, source.subtitle, source.period):
                raise ValueError('Không thay đổi chức danh, công ty hoặc ngày tháng ngoài hồ sơ đã xác nhận.')
            allowed = {tuple(b.source_refs): b.text for b in source.bullets}
            refs_seen = set()
            for bullet in entry.bullets:
                refs = tuple(bullet.source_refs)
                if refs not in allowed or refs in refs_seen or not review_text_valid(allowed[refs], bullet.text):
                    raise ValueError('Bullet thiếu nguồn, bị trùng hoặc thay đổi số liệu/phủ định. Hãy cập nhật hồ sơ trước.')
                refs_seen.add(refs)
    if not any(entry.bullets for section in edited.sections for entry in section.entries):
        raise ValueError('CV cần có ít nhất một nội dung chuyên môn.')
    if len(edited.model_dump_json()) > 120000:
        raise ValueError('CV quá dài; hãy giảm nội dung.')
