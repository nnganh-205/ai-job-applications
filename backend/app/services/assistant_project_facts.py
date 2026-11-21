"""Keep explicit project metadata alongside the model's other extracted facts."""
import re
from backend.app.schemas.assistant import ProfilePatch
from backend.app.services.assistant_answers import fold


def explicit_project(text, intake):
    from backend.app.services.assistant_intake import missing_fields
    from backend.app.services.assistant_routing import source_evidence
    from backend.app.schemas.assistant import IntentDecision
    path = (missing_fields(intake) or ['complete'])[0]
    if (path != 'project' and not path.startswith('project.')) or re.search(r'[?]|\b(?:neu|gia su|vi du|khong phai|chua lam|khong lam|hay tao|hay viet)\b',fold(text)):
        return None
    match = re.fullmatch(r'\s*(?:Dự án|Project)\s+([^:\n?]{2,240})\s*[:：]\s*(?:với\s+)?(?:công việc|nhiệm vụ|mô tả)\s*:?\s*(.{20,})',text,re.I|re.S)
    if not match or len(re.findall(r'(?:^|[\n.;])\s*(?:Dự án|Project)\s+',text,re.I)) > 1:
        return None
    name, work = match[1].strip(), match[2].strip()
    entries = intake['profile']['project']
    found = [i for i,e in enumerate(entries) if fold(e.get('project_name') or '')==fold(name)]
    if len(found)>1: return None
    index = found[0] if found else len(entries)
    parts = path.split('.')
    if not found and len(parts)==3 and parts[1].isdigit() and int(parts[1])<len(entries):
        index = int(parts[1])
        if entries[index].get('project_name'): return None
    if index>30: return None
    # Sentence boundaries keep decimal commas, percent ranges and parentheses intact.
    sentences = [part.strip() for part in re.split(r'(?<=[.!])\s+(?=[A-ZĐÀ-Ỹ])|,\s*(?=Đạt\b)',work) if part.strip()]
    if len(sentences)>20: return None
    updates = [ProfilePatch(section='project',index=index,field='project_name',value=name,
                            evidence=source_evidence(name,text))]
    updates.extend(ProfilePatch(section='project',index=index,field='description',operation='append',
                                value=[part],evidence=source_evidence(part,text)) for part in sentences)
    return IntentDecision(intent='build_cv',updates=updates)


def enrich_project_updates(profile, path, text, updates):
    result = list(updates)
    if not path.startswith('project'):
        return result
    # Supplement only affirmative first-person statements, never examples or questions.
    plain = fold(text)
    if re.search(r'[?]|\b(?:neu|gia su|vi du|nhung|khong phai|chua lam|khong lam)\b', plain):
        return result
    personal = re.search(r'\bdự án cá nhân\b', text, re.I)
    own = re.search(r'\b(?:mình|tôi|em)\s+(?:trực tiếp\s+)?(?:làm|xây dựng|phát triển|thiết kế|triển khai|lập trình)\s+[^,;\n.!?]+', text, re.I)
    if not personal or not own:
        return result
    # Ambiguous messages about several projects must be resolved by the model.
    indices = {p.index for p in result if p.section == 'project' and p.index is not None}
    parts = path.split('.')
    if len(indices) > 1:
        return result
    index = next(iter(indices), int(parts[1]) if len(parts)==3 and parts[1].isdigit() else len(profile['project']))
    if index > len(profile['project']):
        return result
    entry = profile['project'][index] if index < len(profile['project']) else {}
    from backend.app.services.assistant_intake import supported, normalized
    def valid(p):
        return normalized(p.evidence) in normalized(text) and supported(p.value,p.evidence)
    fields = {p.field for p in result if p.section=='project' and p.index==index and valid(p)}
    additions = [('project_type', personal.group())]
    # A stated activity is a role description, not an inferred full-stack/lead title.
    activity = own.group().strip()
    broad = re.search(r'\b(?:het|toan bo|tat ca|moi thu)\b',fold(activity))
    if not entry and 'project_name' not in fields and not broad:
        label = re.sub(r'^(?:mình|tôi|em)\s+(?:trực tiếp\s+)?(?:làm|xây dựng|phát triển|thiết kế|triển khai|lập trình)\s+', '',activity,flags=re.I)
        additions.insert(0,('project_name',label))
    if not entry and 'project_name' not in fields and not any(k=='project_name' for k,v in additions):
        return result
    if not entry.get('role') and 'role' not in fields:
        additions.append(('role',activity))
    if not broad and not any(entry.get(k) or k in fields for k in ('description','work','contributions','outcomes')):
        additions.append(('description',[activity]))
    for field,value in additions:
        evidence = value[0] if isinstance(value,list) else value
        if field not in fields and not entry.get(field) and len(evidence) <= 1500:
            result = [p for p in result if not (p.section=='project' and p.index==index and p.field==field and not valid(p))]
            result.append(ProfilePatch(section='project',index=index,field=field,value=value,evidence=evidence))
    return result
