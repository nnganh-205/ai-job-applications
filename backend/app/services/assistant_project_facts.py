"""Keep explicit project metadata alongside the model's other extracted facts."""
import re
from backend.app.schemas.assistant import ProfilePatch
from backend.app.services.assistant_answers import fold


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
