"""Compact chat routing with evidence reconstructed from the current user message."""
import re
from pydantic import Field
from typing import Literal
from backend.app.schemas.profile import StrictModel
from backend.app.schemas.assistant import Intent, IntentDecision, IntakeSignal, ProfilePatch
from backend.app.services.assistant_answers import fold
from ai.llm.ollama_client import OllamaSchemaError


class ChatPatch(StrictModel):
    path: str = Field(min_length=1, max_length=90, pattern=(
        r'^(?:contact\.(?:full_name|email|phone|location|linkedin|github|website|portfolio_url)'
        r'|summary|target_role|education\.\d+\.(?:institution|major|field_of_study|degree|start_date|end_date|gpa|details)'
        r'|experience\.\d+\.(?:company|job_title|role|employment_type|location|start_date|end_date|is_current|description|responsibilities|achievements|technologies_used)'
        r'|project\.\d+\.(?:project_name|project_type|role|start_date|end_date|description|technologies|github_url|demo_url|project_url)'
        r'|involvement\.\d+\.(?:activity_name|organization|role|description)'
        r'|skills\.\d+\.items|(?:education|experience|project|involvement|skills)\.\d+)$'
    ))
    value: str | list[str] | bool | None = None
    operation: Literal['set', 'append', 'remove_entry'] = 'set'


class ChatDecision(StrictModel):
    intent: Intent
    reply: str = Field(default='', max_length=1000)
    intake_signal: IntakeSignal | None = None
    updates: list[ChatPatch] = Field(default_factory=list, max_length=24)


class StandaloneChatDecision(ChatDecision):
    intake_signal: None = None


class SourceMismatch(OllamaSchemaError):
    """A proposed value was rewritten instead of copied from the current message."""


def source_evidence(value, text):
    from backend.app.services.assistant_intake import supported
    if not supported(value, text):
        raise SourceMismatch('Thông tin trích xuất chưa khớp lời bạn cung cấp.')
    if len(text) <= 1500:
        return text
    if isinstance(value, str) or isinstance(value, list):
        values = [value] if isinstance(value, str) else value
        spans = []
        for item in values:
            pattern = r'\s+'.join(re.escape(part) for part in item.split())
            match = re.search(pattern, text, re.I) if pattern else None
            if not match:
                raise SourceMismatch('Thông tin trích xuất chưa khớp lời bạn cung cấp.')
            spans.append(match.span())
        if spans:
            evidence = text[min(s[0] for s in spans):max(s[1] for s in spans)]
            if len(evidence) <= 1500:
                return evidence
    raise OllamaSchemaError('Bạn chia thông tin thành các tin nhắn ngắn hơn để mình ghi nhận chính xác nhé.')


def expand_decision(result, text):
    if isinstance(result, IntentDecision):
        return result
    updates = []
    try:
        for patch in result.updates:
            if patch.path.endswith('.is_current'):
                from backend.app.services.assistant_intake import supported
                if not supported(patch.value, text):
                    continue
            parts = patch.path.split('.')
            section, index, field = parts[0], None, ''
            if section in {'summary', 'target_role'}:
                if len(parts) != 1:
                    raise ValueError('Invalid scalar path')
            elif section == 'contact':
                if len(parts) != 2:
                    raise ValueError('Invalid contact path')
                field = parts[1]
            else:
                if len(parts) not in {2, 3} or not parts[1].isdigit():
                    raise ValueError('Invalid entry path')
                index = int(parts[1])
                field = parts[2] if len(parts) == 3 else ''
                if not field and patch.operation != 'remove_entry':
                    raise ValueError('Missing field')
            updates.append(ProfilePatch(section=section, field=field, index=index,
                value=patch.value, operation=patch.operation, evidence=source_evidence(patch.value, text)))
        return IntentDecision(intent=result.intent, reply=result.reply,
                              clarification=result.reply if result.intent == 'clarify' else '',
                              updates=updates, intake_signal=result.intake_signal)
    except ValueError as error:
        raise OllamaSchemaError('Chưa xác định đúng mục cần cập nhật; bạn nói rõ mục đó giúp mình nhé.') from error


_EXPERIENCE_STATEMENT = re.compile(
    r'\s*(?:(?:Tôi|Mình|Em)\s+)?(?:từng|đã)\s+làm\s+'
    r'(?:(?P<employment>Intern|thực tập(?: sinh)?)\s+)?(?:ở|tại)\s+(?P<company>[^,;\n?]+),\s*'
    r'(?:từ\s+)?(?:tháng\s+)?(?P<start>(?:0?[1-9]|1[0-2])/[12]\d{3})\s*'
    r'(?:đến|tới|-)\s*(?:tháng\s+)?(?P<end>(?:0?[1-9]|1[0-2])/[12]\d{3}),\s*'
    r'(?:làm\s+)?(?:vị trí|vai trò)\s+(?P<role>[^,;\n?]+),\s*'
    r'(?:cụ thể\s*:?|công việc\s*:|nhiệm vụ\s*:)\s*(?P<work>[^?]+)', re.I,
)

_EXPERIENCE_END_DATES = re.compile(
    r'\s*(?:(?:Tôi|Mình|Em)\s+)?(?:từng|đã)\s+làm\s+'
    r'(?:(?P<employment>Intern|thực tập(?: sinh)?)\s+)?(?:ở|tại)\s+(?P<company>[^,;\n?]+),\s*'
    r'(?:làm\s+)?(?:(?:vị trí|vai trò)\s+)?(?P<role>[^,;\n?]+),\s*'
    r'(?:làm\s+)?(?:những\s+)?(?:việc|công việc|nhiệm vụ|cụ thể)\s*:\s*(?P<work>[^?]+?)'
    r'[.\s;]*(?:bắt đầu|thời gian|từ)\s*:?\s*(?:tháng\s+)?(?P<start>(?:0?[1-9]|1[0-2])/[12]\d{3})\s*'
    r'(?:đến|tới|[-–—])\s*(?:tháng\s+)?(?P<end>(?:0?[1-9]|1[0-2])/[12]\d{3})[.\s]*', re.I,
)


def explicit_experience(text, intake):
    match = _EXPERIENCE_STATEMENT.fullmatch(text) or _EXPERIENCE_END_DATES.fullmatch(text)
    if not match:
        return None
    if len(re.findall(r'\b(?:từng|đã)\s+làm\s+(?:ở|tại)\b', text, re.I)) > 1:
        return None
    # Only accept a complete factual statement, never questions or instructions.
    if re.search(r'\b(?:neu|gia su|vi du|khong|chua|xoa|sua|doi|bo qua)\b', fold(text)):
        return None
    entries = intake['profile'].get('experience', [])
    company = match['company'].strip()
    existing = [i for i, entry in enumerate(entries) if fold(entry.get('company') or '') == fold(company)]
    if len(existing) > 1:
        return None
    if existing:
        entry = entries[existing[0]]
        if any(fold(entry.get(field) or '') != fold(value) for field, value in (
            ('job_title', match['role'].strip()), ('start_date', match['start']), ('end_date', match['end'])
        )):
            return None
    index = existing[0] if existing else len(entries)
    if index > 30:
        return None
    fields = {'company': company, 'job_title': match['role'].strip(),
              'start_date': match['start'], 'end_date': match['end']}
    if match['employment']:
        fields['employment_type'] = match['employment']
    fields['description'] = [part.strip() for part in re.split(r'[;\n]+|[,\.]\s*(?=(?:Xây dựng|Phát triển|Thiết kế|Triển khai|Phân tích|Kiểm thử|Nghiên cứu)\b)', match['work'], flags=re.I) if part.strip()]
    updates = [ProfilePatch(section='experience', index=index, field=field, value=value,
                            operation='append' if field == 'description' else 'set',
                            evidence=source_evidence(value, text)) for field, value in fields.items()]
    return IntentDecision(intent='build_cv', updates=updates)


def quick_decision(text, intake=None):
    plain = fold(' '.join(text.split())).strip(' .!?…')
    if plain in {'chao', 'xin chao', 'chao ban', 'hello', 'hi', 'hey'}:
        return IntentDecision(intent='advice', reply='Chào bạn! Bạn muốn tạo CV, chỉnh CV hay chuẩn bị phỏng vấn?')
    if plain in {'cam on', 'cam on ban', 'thanks', 'thank you'}:
        return IntentDecision(intent='advice', reply='Bạn cứ gửi phần tiếp theo muốn hoàn thiện nhé.')
    if plain in {'tao cv', 'tao cv moi', 'viet cv', 'toi muon tao cv', 'minh muon tao cv', 'giup minh tao cv', 'tao cv qua chat'}:
        return IntentDecision(intent='build_cv')
    from backend.app.services.assistant_lists import cv_question_answer
    answer = cv_question_answer(text)
    if answer and not re.search(r'\b(?:minh|toi|em) (?:da |dang |tung )?(?:hoc|lam|phu trach|su dung|biet|tham gia)\b', plain):
        return IntentDecision(intent='advice', reply=answer)
    if not intake:
        return None
    from backend.app.services.assistant_project_facts import explicit_project
    project = explicit_project(text,intake)
    if project: return project
    experience = explicit_experience(text, intake)
    if experience:
        return experience
    from backend.app.services.assistant_intake import missing_fields
    path = (missing_fields(intake) or ['complete'])[0]
    if path in {'skills','skills.languages'}:
        from backend.app.services.assistant_skills import skill_answer
        answer=skill_answer(intake['profile'],path,text)
        if answer:return answer
    stripped = text.strip()
    simple = (len(stripped) <= 120 and bool(stripped) and not re.search(r'[?;:\n,]|\b(?:minh|toi|em|chua|khong|bo qua|them|sua|doi|xoa|tai sao|la sao|nghia la|huong dan|vi du|hay|neu|nen|muon|can|phai|duoc|thi sao)\b', plain))
    if simple and path == 'target_role':
        return IntentDecision(intent='build_cv', updates=[ProfilePatch(section='target_role', value=stripped, evidence=stripped)])
    parts = path.split('.')
    if simple and len(parts) == 3 and parts[1].isdigit() and parts[2] in {'institution','major','degree','company','job_title','project_name','activity_name'}:
        return IntentDecision(intent='build_cv', updates=[ProfilePatch(section=parts[0], index=int(parts[1]), field=parts[2], value=stripped, evidence=stripped)])
    if path == 'contact.full_name' and 2 <= len(stripped.split()) <= 6:
        words = stripped.split()
        command = re.search(r'\b(?:xoa|du an|khong|chua|tao|cv|muon|giup|doi|bo qua|lap trinh|vai tro|chuc danh|nganh|ky nang|developer|engineer|senior|junior)\b', plain)
        if not command and all(word[:1].isupper() and word.replace('-', '').isalpha() for word in words):
            return IntentDecision(intent='build_cv', updates=[ProfilePatch(
                section='contact', field='full_name', value=stripped, evidence=stripped)])
    if path == 'contact.reach':
        if re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', stripped):
            field = 'email'
        elif re.fullmatch(r'[+\d\s().-]+', stripped) and 8 <= len(re.sub(r'\D', '', stripped)) <= 15:
            field = 'phone'
        else:
            return None
        return IntentDecision(intent='build_cv', updates=[ProfilePatch(
            section='contact', field=field, value=stripped, evidence=stripped)])
    return None


def routing_payload(text, context, history=None, intake=None):
    from backend.app.services.assistant_intake import missing_fields
    from backend.app.services.assistant_answers import answer_context
    current = (missing_fields(intake) or ['complete'])[0] if intake else None
    expected = answer_context(intake['profile'], current) if intake else None
    profile = {}
    if intake:
        profile['contact'] = intake['profile']['contact']
        for section in ('education', 'experience', 'project', 'skills', 'involvement'):
            entries = []
            for index, entry in enumerate(intake['profile'][section]):
                names = [entry.get(key) for key in ('project_name', 'company', 'institution', 'activity_name', 'organization') if entry.get(key)]
                focused = bool(expected and expected.get('section') == section and expected.get('index') == index)
                named = any(fold(name) in fold(text) for name in names)
                if focused or named or section == 'skills':
                    entries.append(entry)
                else:
                    entries.append({key: value for key, value in entry.items()
                        if key not in {'id', 'description', 'responsibilities', 'original_bullets',
                                       'details', 'original_description', 'achievements', 'outcomes', 'contributions'}})
            profile[section] = entries
        profile['summary'] = intake['profile'].get('summary')
    def compact(value):
        if isinstance(value, dict):
            return {key: compact(item) for key, item in value.items() if item not in (None, '', [], {})}
        if isinstance(value, list):
            return [compact(item) for item in value]
        return value
    state = None if not intake else dict(profile=compact(profile), current_step=current,
        target_role=intake.get('target_role'), focus_section=intake.get('focus_section'),
        skipped=intake.get('skipped', []), step_history=intake.get('step_history', [])[-4:])
    expected = {key: value for key, value in (expected or {}).items() if key != 'entry'} or None
    recent = []
    remaining = 1800
    for message in reversed(history or []):
        if message.get('role') not in {'user', 'assistant'}:
            continue
        content = message.get('text', '')[:min(600, remaining)]
        if content:
            recent.append(dict(role=message['role'], content=content))
            remaining -= len(content)
        if len(recent) >= 4 or remaining <= 0:
            break
    return list(reversed(recent)), dict(language=context['language'], has_cv=bool(context.get('cv_id')),
        has_profile=bool(context.get('profile_id')), has_job=bool(context.get('posting_id')),
        cv_intake=state, expected_answer=expected)
