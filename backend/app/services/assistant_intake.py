"""Conversation facts are copied from user evidence, then reviewed in the CV form."""
import re
import unicodedata
from copy import deepcopy
from pydantic import ValidationError
from backend.app.schemas.profile import MasterProfile, Contact, Experience, Project, Education, Involvement, SkillGroup
from backend.app.db.job_posting_repository import utc_now

MODELS = dict(contact=Contact, experience=Experience, project=Project, education=Education, involvement=Involvement, skills=SkillGroup)
FORBIDDEN = {'id', 'original_bullets', 'original_description', 'normalized_items'}
REMOVE = re.compile(r'\b(xóa|xoá|bỏ|remove|delete|không đưa)\b', re.I)


def blank_intake():
    profile = MasterProfile(contact={}, experience=[], project=[], education=[], involvement=[], skills=[])
    return dict(profile=profile.model_dump(mode='json'), target_role=None, skipped=[], active=True, revision=0)


def normalized(value):
    return ' '.join(unicodedata.normalize('NFC', value).casefold().split())


def supported(value, evidence):
    if isinstance(value, str):
        return bool(value.strip()) and normalized(value) in normalized(evidence)
    if isinstance(value, list):
        return bool(value) and all(isinstance(item, str) and supported(item, evidence) for item in value)
    if isinstance(value, bool):
        markers = ('đang', 'hiện tại', 'currently', 'present') if value else ('đã nghỉ', 'không còn', 'kết thúc', 'ended')
        return any(marker in normalized(evidence) for marker in markers)
    return value is None and bool(REMOVE.search(evidence))


def apply_updates(intake, updates, message):
    result = deepcopy(intake or blank_intake())
    rejected = 0
    changed = False
    for patch in updates:
        candidate = deepcopy(result)
        if normalized(patch.evidence) not in normalized(message):
            rejected += 1
            continue
        try:
            if patch.operation == 'remove_entry':
                if patch.section not in MODELS or patch.section == 'contact' or not REMOVE.search(patch.evidence):
                    raise ValueError('Deletion needs an explicit request')
                candidate['profile'][patch.section].pop(patch.index if patch.index is not None else -999)
            else:
                if not supported(patch.value, patch.evidence):
                    raise ValueError('Value not supported by the current user message')
                if patch.section == 'target_role':
                    if patch.value is not None and not isinstance(patch.value, str): raise ValueError('Role must be text')
                    candidate['target_role'] = patch.value
                elif patch.section == 'summary':
                    candidate['profile']['summary'] = patch.value
                else:
                    field = 'description' if patch.field == 'work' and patch.section in {'experience','project','involvement'} else patch.field
                    value = patch.value
                    if field in {'description','responsibilities','technologies','details','items'} and isinstance(value,str): value = [value]
                    if field in FORBIDDEN or field not in MODELS[patch.section].model_fields:
                        raise ValueError('Unsupported field')
                    if patch.section == 'contact':
                        entry = candidate['profile']['contact']
                    else:
                        entries = candidate['profile'][patch.section]
                        if patch.index is None or patch.index > len(entries): raise ValueError('Invalid entry')
                        if patch.index == len(entries): entries.append({})
                        entry = entries[patch.index]
                    if patch.operation == 'append':
                        if not isinstance(value, list) or not isinstance(entry.get(field, []), list):
                            raise ValueError('Only lists can be appended')
                        entry[field] = list(dict.fromkeys(entry.get(field, []) + value))
                    else:
                        entry[field] = value
            if patch.operation != 'remove_entry' and patch.value is not None:
                path = f'{patch.section}.{patch.index}.{patch.field}'
                candidate['skipped'] = [item for item in candidate.get('skipped', []) if item not in {patch.section, path}]
            candidate['profile'] = MasterProfile.model_validate(candidate['profile']).model_dump(mode='json')
        except (ValueError, IndexError, KeyError, TypeError, ValidationError):
            rejected += 1
            continue
        changed = changed or candidate != result
        result = candidate
    if changed:
        result['revision'] = result.get('revision', 0) + 1
        result.pop('draft_id', None)
    return result, rejected


STAGES = ('contact', 'target_role', 'education', 'experience', 'project', 'skills', 'involvement', 'summary')
TITLES = dict(contact='Thông tin cá nhân', target_role='Vị trí mục tiêu', education='Học vấn', experience='Kinh nghiệm', project='Dự án', skills='Kỹ năng', involvement='Hoạt động', summary='Giới thiệu bản thân')
REQUIRED = {
    'education': [('institution', 'tên trường / cơ sở đào tạo'), ('major', 'ngành học hoặc chương trình đào tạo')],
    'experience': [('company', 'tên công ty / nơi làm việc'), ('job_title', 'vị trí công việc'), ('work', 'công việc bạn trực tiếp thực hiện')],
    'project': [('project_name', 'tên dự án / đồ án'), ('role', 'vai trò của bạn trong dự án'), ('work', 'những việc bạn trực tiếp thực hiện trong dự án')],
    'skills': [('items', 'các kỹ năng hoặc công cụ bạn sử dụng được')],
    'involvement': [('activity_name', 'tên hoạt động'), ('role', 'vai trò của bạn'), ('work', 'những việc bạn tham gia thực hiện')],
}
INTRO = {
    'education': 'Tiếp theo là học vấn. Bạn cho mình biết trường / cơ sở đào tạo và ngành học nhé. Có thể thêm thời gian học, bằng cấp, điểm số nếu muốn.',
    'experience': 'Đến phần kinh nghiệm: bạn từng làm ở đâu, vị trí gì và trực tiếp làm những việc nào? Có thể thêm thời gian làm việc. Nếu chưa có kinh nghiệm, cứ nhắn “chưa có”.',
    'project': 'Tiếp theo là dự án / đồ án. Bạn kể tên dự án, vai trò và những việc mình trực tiếp thực hiện nhé. Có thể kèm công nghệ đã dùng và link GitHub của dự án nếu có. Nếu chưa có dự án, nhắn “chưa có”.',
    'skills': 'Đến phần kỹ năng. Bạn dùng được những kỹ năng, công cụ hoặc ngoại ngữ nào? Chỉ cần kể những gì bạn thực sự biết; nếu chưa muốn thêm, nhắn “bỏ qua”.',
    'involvement': 'Bạn có hoạt động ngoại khóa, tình nguyện hay câu lạc bộ nào muốn đưa vào CV không? Nếu có, kể tên hoạt động, vai trò và việc bạn đã làm. Nếu chưa có, nhắn “chưa có”.',
    'summary': 'Cuối cùng, bạn có muốn thêm vài câu giới thiệu bản thân hoặc định hướng nghề nghiệp không? Bạn có thể viết ý thô để tinh chỉnh sau, hoặc nhắn “bỏ qua”.',
}


def remaining_fields(intake):
    profile = intake['profile']
    contact = profile['contact']
    skipped = intake.get('skipped', [])
    fields = []
    if not (contact.get('full_name') or '').strip(): fields.append('contact.full_name')
    email = contact.get('email') or ''
    phone = contact.get('phone') or ''
    valid_email = bool(re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email))
    valid_phone = bool(re.fullmatch(r'[+\d\s().-]+', phone)) and 8 <= len(re.sub(r'\D', '', phone)) <= 15
    if not (valid_email or valid_phone): fields.append('contact.reach')
    if not intake.get('target_role') and 'target_role' not in skipped: fields.append('target_role')
    for section in STAGES[2:-1]:
        if section in skipped: continue
        entries = profile[section]
        if not entries:
            fields.append(section)
            continue
        for index, entry in enumerate(entries):
            for field, _ in REQUIRED[section]:
                path = f'{section}.{index}.{field}'
                if path in skipped: continue
                if field == 'work':
                    present = any(entry.get(key) for key in ('description','responsibilities','technologies'))
                elif section == 'experience' and field == 'job_title': present = entry.get('job_title') or entry.get('role')
                elif section == 'education' and field == 'major': present = entry.get('major') or entry.get('field_of_study') or entry.get('degree')
                elif section == 'involvement' and field == 'activity_name': present = entry.get('activity_name') or entry.get('organization')
                else: present = entry.get(field)
                if not present: fields.append(path)
        from backend.app.services.assistant_lists import LISTS
        if intake.get('list_collection_version', 1) >= 2 and section in LISTS and not any(p.startswith(section + '.') for p in fields):
            if intake.get(section + '_next_index') == len(entries):
                fields.append(f'{section}.{len(entries)}.{LISTS[section][1]}')
            elif intake.get(section + '_confirmed_count', 0) != len(entries):
                fields.append(section + '.more')
        if section == 'skills' and not any(p.startswith('skills.') for p in fields):
            from backend.app.services.assistant_skills import language_missing
            fields.extend(language_missing(intake))
        if section == 'project' and not any(p.startswith('project.') for p in fields):
            if intake.get('project_next_index') == len(entries):
                fields.append(f'project.{len(entries)}.project_name')
            elif intake.get('project_confirmed_count', 0) != len(entries):
                fields.append('project.more')
    if not profile.get('summary') and 'summary' not in skipped: fields.append('summary')
    return fields


def missing_fields(intake):
    fields = remaining_fields(intake)
    focus = intake.get('focus_section')
    if focus in STAGES:
        selected = [path for path in fields if path.split('.')[0] == focus]
        return (selected or [focus + '.review']) + [path for path in fields if path.split('.')[0] != focus]
    return fields


def stage_history(intake, messages=None):
    if intake.get('step_history'): return list(intake['step_history'][-24:])
    stages = []
    for message in messages or []:
        data = (message.get('result') or {}).get('intake') or {}
        stage = data.get('step') or (data.get('missing') or [''])[0].split('.')[0]
        if stage in STAGES and (not stages or stage != stages[-1]): stages.append(stage)
    return stages[-24:]


def navigation_signal(intake, text, messages=None):
    from backend.app.schemas.assistant import IntakeSignal
    if not intake: return None
    plain = ''.join(c for c in unicodedata.normalize('NFD', normalized(text)) if not unicodedata.combining(c)).replace('đ','d').strip(' .!?…')
    plain = re.sub(r'^(?:(?:vay|the|bay gio|gio)\s+)?(?:(?:toi|minh|em) (?:muon|can) |cho (?:toi|minh|em) )?', '', plain)
    names = {'du an':'project','do an':'project','hoc van':'education','kinh nghiem':'experience','ky nang':'skills','hoat dong':'involvement','thong tin ca nhan':'contact','lien he':'contact','vi tri muc tieu':'target_role','tom tat':'summary','gioi thieu':'summary'}
    match = re.fullmatch(r'(?:quay lai|tro lai|ve lai|mo lai|bo sung|chinh sua|sua) (?:ve |phan |muc )*('+'|'.join(names)+r')(?: di)?(?:,? (?:toi|minh|em) (?:can|muon) (?:bo sung|sua|chinh sua)(?: them)?)?(?: nhe| nha| a)?', plain)
    if match: return IntakeSignal(kind='navigate',section=names[match[1]],evidence=text)
    if re.fullmatch(r'(?:quay lai|tro lai|ve lai) (?:luc nay|phan truoc|muc truoc|buoc truoc|cau hoi truoc|phan vua roi)(?: di| nhe| nha| a)?', plain):
        current = (missing_fields(intake) or ['complete'])[0].split('.')[0]
        previous = next((stage for stage in reversed(stage_history(intake,messages)) if stage != current),None)
        if previous: return IntakeSignal(kind='navigate',section=previous,evidence=text)
    if intake.get('focus_section') and plain in {'xong','da xong','tiep tuc','giu nguyen','khong sua nua','lam tiep'}:
        return IntakeSignal(kind='resume',section=intake['focus_section'],evidence=text)
    return None


def skip_answer(text):
    value = normalized(text).strip(' .!?…')
    value = re.sub(r'^(?:mình|tôi|em|hiện tại mình|hiện tại tôi)\s+', '', value)
    value = re.sub(r'\s+(?:ạ|nhé|nha|đâu|gì cả|gì)$', '', value)
    return value in {'chưa có','không có','chưa có kinh nghiệm','không có kinh nghiệm','chưa có kinh nghiệm làm việc','không có kinh nghiệm làm việc','chưa có phần này','bỏ qua phần này','chưa có dự án','chưa có hoạt động','chưa có học vấn','chưa có kỹ năng','chưa tham gia hoạt động','bỏ qua','bo qua','skip','chưa biết','không nhớ','chưa muốn cung cấp','không muốn thêm','để sau','không cần','không cần bổ sung','không bổ sung','không thêm nữa','chuyển phần tiếp theo','sang phần tiếp theo'}


def asks_for_explanation(text):
    from backend.app.services.assistant_answers import clarification_request
    if clarification_request(text): return True
    plain = ''.join(c for c in unicodedata.normalize('NFD', normalized(text)) if not unicodedata.combining(c)).replace('đ','d')
    plain = plain.strip(' .!?…')
    plain = re.sub(r'^(?:(?:minh|toi|em|to)\s+)?', '', plain)
    plain = re.sub(r'(?:\s+(?:a|nhe|nha|vay|nhi|lam))+$', '', plain)
    return bool(re.fullmatch(r'(?:la sao|sao co|nghia la sao|y (?:ban|la) (?:la )?(?:gi|sao)|chua hieu(?: cau hoi| y ban)?|khong hieu(?: cau hoi| y ban)?|chua biet|giai thich(?: lai| them| ro hon)?(?: giup (?:minh|toi|em))?(?: duoc khong)?|ban dang hoi gi|(?:du an|do an|vai tro|ky nang) la gi)', plain))


EXPLANATIONS = {
    'contact': 'Đây là thông tin để nhà tuyển dụng biết bạn là ai và liên hệ với bạn: họ tên, email hoặc số điện thoại. Bạn chỉ cần gửi thông tin muốn hiển thị trên CV, không cần số giấy tờ hay địa chỉ nhà chi tiết.',
    'target_role': 'Vị trí mục tiêu là công việc bạn muốn ứng tuyển, chẳng hạn thực tập Frontend hoặc nhân viên Marketing. Nếu chưa chọn được, bạn có thể nói lĩnh vực mình quan tâm.',
    'education': 'Học vấn là quá trình học của bạn: trường hoặc cơ sở đào tạo và ngành học. Ví dụ minh họa: học Công nghệ thông tin tại một trường đại học. Bạn có thể kể bằng câu bình thường.',
    'experience': 'Kinh nghiệm là những việc bạn đã thực tế làm, kể cả thực tập, việc bán thời gian hoặc freelance. Bạn kể nơi làm, vị trí và công việc mình phụ trách. Nếu chưa từng đi làm, bạn có thể nói đúng điều đó.',
    'project': 'Dự án / đồ án là một sản phẩm hoặc bài tập thực tế bạn từng thực hiện, ở trường, trong nhóm hoặc tự làm; không nhất thiết là dự án đi làm. Ví dụ minh họa: một website bán hàng, bài phân tích dữ liệu hoặc kế hoạch Marketing cho môn học. Mình muốn biết tên / mục tiêu của bài đó, bạn phụ trách việc gì và đã làm được gì. Bạn có thể kể một bài gần đây nhất bằng lời của mình.',
    'skills': 'Kỹ năng là những điều bạn thực sự làm được: công cụ, phần mềm, ngoại ngữ hoặc cách làm việc. Ví dụ minh họa: dùng Excel, lập trình Python hoặc thuyết trình. Chỉ chọn những gì đúng với bạn.',
    'involvement': 'Đây là các hoạt động ngoài học tập / công việc, như câu lạc bộ, tình nguyện hoặc tổ chức sự kiện. Bạn kể hoạt động nào, vai trò và việc mình tham gia làm. Không bắt buộc phải có phần này.',
    'summary': 'Phần giới thiệu là vài câu ngắn về bạn đang học / làm gì, điểm mạnh thực tế và công việc mong muốn. Bạn cứ viết ý thô; câu chữ có thể tinh chỉnh sau.',
}


def explain_entry_reference(intake, path, text):
    from backend.app.services.assistant_answers import fold, entry_reference
    stage = path.split('.')[0]
    entries = intake['profile'].get(stage, [])
    if not isinstance(entries,list):
        return '“Mục” là một phần thông tin trong CV, chẳng hạn học vấn hoặc dự án. Hiện mình đang hỏi phần ' + TITLES[stage].lower() + '; bạn không cần tự tạo thêm mục.'
    count = len(entries)
    if not count: return 'Mình đang hỏi về phần ' + TITLES[stage].lower() + '. Hiện bạn chưa nhập thông tin nào trong phần này; không có yêu cầu phải tạo nhiều mục.'
    parts = path.split('.')
    current = int(parts[1]) if len(parts)==3 and parts[1].isdigit() else 0
    requested = re.search(r'\bmuc\s*(?:thu\s*)?(\d+)\b',fold(text))
    index = int(requested[1])-1 if requested else current
    if not 0 <= index < count:
        return f'Hiện bạn có {count} thông tin trong phần {TITLES[stage].lower()}, chưa có mục {index+1}. Mình đang hỏi về {entry_reference(intake["profile"],stage,current)}. Không cần thêm mục mới trừ khi bạn muốn; dữ liệu hiện tại vẫn được giữ nguyên.'
    reference = entry_reference(intake['profile'],stage,index)
    if count == 1:
        noun = {'project':'dự án','experience':'công việc','education':'quá trình học','involvement':'hoạt động','skills':'nhóm kỹ năng'}.get(stage,'thông tin')
        return f'“Mục 1” trong câu trước chỉ có nghĩa là {reference}, tức thông tin đầu tiên bạn đã kể trong phần này. Hiện chỉ có một {noun} đã nhập; bạn không bắt buộc phải thêm {noun} khác hay tạo thêm mục trong CV. Mình sẽ gọi bằng tên cụ thể để bạn dễ theo dõi; các thông tin đã nhập vẫn được giữ nguyên.'
    listing = '; '.join(f'{n+1}: {entry_reference(intake["profile"],stage,n)}' for n in range(min(count,4)))
    return f'Mỗi mục là một thông tin riêng trong phần {TITLES[stage].lower()}. Bạn hiện có {count} mục: {listing}. “Mục {index+1}” là {reference}. Đây chỉ là cách phân biệt những thông tin đã có, không phải yêu cầu thêm thông tin mới; bước nhập hiện tại vẫn được giữ nguyên.'


def explain_question(intake, text='', messages=None):
    missing = missing_fields(intake)
    if missing and missing[0] in {'education.more','experience.more','involvement.more'}:
        return 'Mình đang kiểm tra bạn đã kể hết các mục trong phần này chưa, không yêu cầu bạn phải có thêm. Bạn có thể kể mục khác hoặc nói “hết rồi” để tiếp tục.\n\n' + question(missing[0],intake)
    if missing and missing[0].startswith('skills'):
        from backend.app.services.assistant_skills import skill_question
        detail = skill_question(missing[0],intake)
        if detail:
            from backend.app.services.assistant_skills import no_certificate
            prefix = 'Mình ghi nhận bạn chưa có chứng chỉ. Bạn vẫn có thể ghi khả năng ngoại ngữ thực tế trên CV. ' if no_certificate(text) else 'Mình đang làm rõ thông tin ngoại ngữ để ghi vào CV. '
            return prefix + detail
    if missing and missing[0] == 'project.more':
        return 'Mình đang hỏi bạn đã kể hết các dự án muốn đưa vào CV chưa, không phải yêu cầu bổ sung chi tiết cho dự án cũ. Nếu còn, kể tên dự án tiếp theo; nếu đã hết hoặc không muốn thêm, nhắn “hết rồi”. Các dự án đã nhập vẫn được giữ nguyên.'
    from backend.app.services.assistant_dialogue import resolve_followup
    followup = resolve_followup(intake,(missing or ['complete'])[0],text,messages)
    if followup: return followup
    if not missing: return 'Bạn đã hoàn tất các phần. Bạn muốn mình giải thích nội dung nào trước khi chọn mẫu CV?'
    path = missing[0]
    stage = path.split('.')[0]
    from backend.app.services.assistant_answers import clarification_topic
    topic = clarification_topic(text)
    if topic == 'entry': return explain_entry_reference(intake,path,text)
    if topic in {'skills','education','project'}: return EXPLANATIONS[topic]
    if topic == 'role' and not path.endswith(('.role','.job_title')):
        if len(path.split('.')) == 3: path = '.'.join(path.split('.')[:2]) + '.role'
        elif len(intake['profile'].get('project', [])) == 1:
            stage = 'project'; path = 'project.0.role'
        else: path = stage + '.role'
    elif topic == 'work': path = stage + '.work'
    elif topic == 'major': path = 'education.0.major'
    if path.endswith('.role') or path.endswith('.job_title'):
        parts = path.split('.')
        entries = intake['profile'].get(stage, [])
        entry = entries[int(parts[1])] if len(parts) == 3 and int(parts[1]) < len(entries) else {}
        name = entry.get('project_name') or entry.get('activity_name') or entry.get('company')
        from backend.app.services.assistant_answers import entry_reference
        context = f'Trong {entry_reference(intake["profile"],stage,int(parts[1]))}, ' if len(parts)==3 and name else ''
        examples = 'thiết kế, lập trình, kiểm thử hoặc chuẩn bị nội dung'
        if stage == 'project':
            topic = normalized(' '.join([str(entry.get('project_name') or ''),*entry.get('description',[]),*entry.get('technologies',[])]))
            if re.search(r'phân tích|dữ liệu|data|trực quan', normalized(str(entry.get('project_name') or ''))):
                examples = 'thu thập và làm sạch dữ liệu, phân tích hoặc trực quan hóa kết quả'
            elif re.search(r'marketing|truyền thông|chiến dịch', normalized(str(entry.get('project_name') or ''))):
                examples = 'nghiên cứu đối tượng, lập kế hoạch hoặc xây dựng nội dung truyền thông'
            elif re.search(r'web|bán hàng|react|frontend|backend',topic):
                examples = 'thiết kế giao diện, lập trình chức năng, xử lý dữ liệu phía máy chủ hoặc kiểm thử website'
            elif re.search(r'dữ liệu|data|phân tích',topic):
                examples = 'thu thập và làm sạch dữ liệu, phân tích hoặc trực quan hóa kết quả'
            elif re.search(r'marketing|truyền thông|chiến dịch',topic):
                examples = 'nghiên cứu đối tượng, lập kế hoạch hoặc xây dựng nội dung truyền thông'
        return context + 'vai trò là phần bạn trực tiếp đảm nhận, không nhất thiết phải có chức danh. Ví dụ minh họa: ' + examples + '. Đây chỉ là các khả năng để bạn dễ hình dung, chưa được đưa vào CV. Nếu tự làm toàn bộ, bạn có thể nói “mình tự thực hiện toàn bộ dự án”; nếu làm nhóm, chỉ kể phần của bạn. Bạn đã trực tiếp đảm nhận phần nào?'

    if path.endswith('.work'):
        return 'Mình muốn biết cụ thể bạn đã tự làm những việc nào trong mục vừa kể. Có thể mô tả 1–3 việc bằng câu đơn giản; chỉ thêm kết quả hoặc số liệu nếu bạn có thông tin thật.'
    if path.endswith('.major'):
        return 'Ngành học là tên ngành / chương trình bạn theo học tại trường vừa kể, chẳng hạn Kế toán hoặc Công nghệ thông tin. Đây chỉ là ví dụ, bạn dùng tên ngành thật của mình nhé.'
    return EXPLANATIONS[stage]


def direct_signal(intake, text, messages=None):
    """Fast, unambiguous replies; mixed statements and questions go to the model."""
    from backend.app.schemas.assistant import IntakeSignal
    if not intake: return None
    from backend.app.services.assistant_projects import project_list_signal
    project_signal = project_list_signal(intake,(missing_fields(intake) or ['complete'])[0],text)
    if project_signal: return project_signal
    from backend.app.services.assistant_lists import list_signal, personal_facts
    extra_signal = list_signal(intake,(missing_fields(intake) or ['complete'])[0],text)
    if extra_signal: return extra_signal
    from backend.app.services.assistant_skills import skill_signal
    skills_signal = skill_signal((missing_fields(intake) or ['complete'])[0],text)
    if skills_signal: return skills_signal
    if intake.get('pending_polish') and normalized(text).strip(' .!') in {'áp dụng cách viết','áp dụng câu gợi ý','dùng bản tinh chỉnh'}:
        return IntakeSignal(kind='accept_polish',section=(missing_fields(intake) or ['summary'])[0].split('.')[0],evidence=text)
    navigation = navigation_signal(intake, text, messages)
    if navigation: return navigation
    missing = missing_fields(intake)
    if re.fullmatch(r'(?:(?:giúp mình|giúp tôi|hãy|bạn) )?(?:viết (?:lại )?bullet|tạo bullet|ai writer|chỉnh bullet)(?: (?:cho |phần )?(?:dự án|kinh nghiệm|hoạt động|học vấn)(?: này| vừa nhập)?)?(?: nhé| đi)?[.!]?',normalized(text)):
        current=(missing or ['project'])[0].split('.')[0]
        section=next((target for name,target in [('dự án','project'),('kinh nghiệm','experience'),('hoạt động','involvement'),('học vấn','education')] if name in normalized(text)),current)
        if section not in {'project','experience','involvement','education'}: section='project'
        return IntakeSignal(kind='write_bullets',section=section,evidence=text)
    from backend.app.services.assistant_wording import wording_request, suggestion_acceptance
    if intake.get('pending_role_wording') and suggestion_acceptance(text):
        return IntakeSignal(kind='accept_wording',section='project',evidence=text)
    if wording_request(text,(missing or ['complete'])[0]):
        return IntakeSignal(kind='wording',section='project',evidence=text)
    if not missing: return None
    from backend.app.services.assistant_dialogue import followup_question
    if (followup_question(text) or asks_for_explanation(text)) and not personal_facts(text):
        return IntakeSignal(kind='explain',section=missing[0].split('.')[0],evidence=text)
    if skip_answer(text):
        section = missing[0].split('.')[0]
        for term, target in [('kinh nghiệm','experience'),('dự án','project'),('hoạt động','involvement'),('học vấn','education'),('kỹ năng','skills')]:
            if term in normalized(text): section = target; break
        kind = 'not_available' if section != missing[0].split('.')[0] else 'skip'
        return IntakeSignal(kind=kind,section=section,evidence=text)
    plain = ''.join(c for c in unicodedata.normalize('NFD', normalized(text)) if not unicodedata.combining(c)).replace('đ','d')
    if '?' in plain or re.search(r'\b(nhung|tuy nhien|nen|lam sao|the nao|viet gi|ghi gi)\b', plain): return None
    plain = plain.strip(' .!…')
    plain = re.sub(r'^(?:(?:hien tai|tu truoc den gio|truoc gio|den gio|that ra|thuc ra)\s+)?(?:(?:minh|toi|em|to)\s+)?', '', plain)
    plain = re.sub(r'\s+(?:a|nhe|nha)$', '', plain)
    patterns = {
        'experience': r'(?:chua(?: tung)?|khong(?: he)?) (?:lam o dau|lam viec o dau|lam tai dau|di lam(?: bao gio)?|lam viec(?: bao gio)?|thuc tap(?: bao gio)?|lam cho cong ty nao(?: ca)?|co kinh nghiem(?: gi)?(?: ca)?)',
        'project': r'(?:chua(?: tung)?|khong) (?:lam du an(?: nao)?(?: ca)?|lam do an(?: nao)?(?: ca)?|co du an(?: nao)?(?: ca)?)',
        'involvement': r'(?:chua(?: tung)?|khong) tham gia (?:cau lac bo|clb|hoat dong|tinh nguyen)(?: nao)?(?: ca)?',
    }
    for section, pattern in patterns.items():
        if re.fullmatch(pattern, plain):
            return IntakeSignal(kind='not_available',section=section,evidence=text)
    return None


def validated_signal(signal, text):
    if not signal or normalized(signal.evidence) not in normalized(text): return None
    plain = ''.join(c for c in unicodedata.normalize('NFD', normalized(text)) if not unicodedata.combining(c)).replace('đ','d')
    absence = bool(re.search(r'\b(?:chua|khong)(?: tung| he)? (?:co|lam|di|tham gia|thuc hien|buoc chan|tung)\b|\bchi (?:di )?hoc\b', plain))
    memory = bool(re.search(r'\b(?:khong nho|chua biet|chua xac dinh|khong chac)\b', plain))
    if signal.kind == 'accept_polish' and normalized(text).strip(' .!') not in {'áp dụng cách viết','áp dụng câu gợi ý','dùng bản tinh chỉnh'}: return None
    if signal.kind == 'accept_wording':
        from backend.app.services.assistant_wording import suggestion_acceptance
        if not suggestion_acceptance(text): return None
    if signal.kind == 'not_available' and not absence: return None
    if signal.kind == 'skip' and not (absence or memory or re.search(r'\b(?:bo qua|skip|khong muon|chua muon|khong them|de sau|khong can|khong bo sung|chuyen phan tiep|sang phan tiep)\b',plain)): return None
    if signal.kind == 'unknown' and not memory: return None
    if signal.kind == 'write_bullets' and not re.search(r'\b(?:viet|tao|tinh chinh|chinh sua|viet lai|toi uu)\b.{0,45}\b(?:bullet|cau|mo ta|noi dung|y)\b|\bai writer\b', plain): return None
    return signal


def accepted_signal(intake, signal, text):
    signal = validated_signal(signal, text)
    if not signal: return None
    missing = missing_fields(intake)
    if not missing: return None
    current = missing[0]
    stage = current.split('.')[0]
    if signal.kind in {'explain','navigate','resume','wording','accept_wording','more_entries','section_complete','accept_polish','write_bullets'} or asks_for_explanation(text): return None
    if signal.section == 'contact': return None
    # Unknown details are scoped to the exact current question, never another section.
    if signal.kind == 'unknown':
        return current if signal.section == stage else None
    if signal.section != stage:
        # A named future section can be declined without skipping the current one.
        return signal.section if signal.section in STAGES and signal.kind == 'not_available' else None
    if stage == 'skills' and (current == 'skills.languages' or current.endswith(('.level','.certificate'))): return current
    if signal.kind == 'not_available': return stage
    return current


def question(path, intake):
    from backend.app.services.assistant_lists import LISTS
    section = path.split('.')[0]
    if section in LISTS and path == section + '.more':
        names = {'education':'trường hoặc chương trình đào tạo', 'experience':'công việc, nơi thực tập hoặc việc freelance', 'involvement':'hoạt động hoặc câu lạc bộ'}
        return f'Bạn còn {names[section]} nào muốn đưa vào CV không? Nếu có, kể tiếp nhé; nếu đã đủ, nhắn “hết rồi”. Những mục đã nhập vẫn được giữ nguyên.'

    stage = path.split('.')[0]
    if path == 'contact.full_name': return 'Bắt đầu với thông tin cá nhân nhé. Bạn muốn ghi họ và tên nào trên CV? Bạn có thể gửi kèm email hoặc số điện thoại liên hệ.'
    if path == 'contact.reach': return 'Nhà tuyển dụng cần thông tin liên hệ. Bạn nhập email hoặc số điện thoại hợp lệ nhé.'
    from backend.app.services.assistant_skills import skill_question
    detail = skill_question(path,intake)
    if detail: return detail
    if path == 'target_role': return 'Bạn muốn ứng tuyển vị trí hoặc lĩnh vực nào? Nếu chưa xác định, bạn có thể nhắn “bỏ qua”.'
    if path == 'project.more':
        names = ', '.join(e.get('project_name') or 'dự án chưa đặt tên' for e in intake['profile']['project'])
        return f'Mình đã ghi nhận {len(intake["profile"]["project"])} dự án: {names}. Bạn còn dự án nào muốn đưa vào CV không? Nếu còn, hãy kể tên dự án tiếp theo; nếu đã nhập hết hoặc không muốn thêm, nhắn “hết rồi” hoặc “không thêm nữa” để sang phần kỹ năng.'
    if path.endswith('.review'):
        return f'Bạn muốn bổ sung hoặc sửa điều gì ở phần {TITLES[stage].lower()}? Bạn cứ kể thông tin mới; nếu giữ nguyên, nhắn “xong” để tiếp tục.'
    if path == stage: return INTRO[stage]
    _, index, field = path.split('.')
    if stage == 'project' and int(index) == len(intake['profile']['project']):
        return 'Bạn kể tên dự án tiếp theo muốn đưa vào CV nhé. Có thể gửi kèm vai trò và việc bạn đã thực hiện; các dự án trước vẫn được giữ nguyên.'
    if field == 'work':
        entry = intake['profile'][stage][int(index)]
        name = entry.get('project_name') or entry.get('company') or entry.get('activity_name')
        from backend.app.services.assistant_answers import entry_reference
        context = f'Với {entry_reference(intake["profile"],stage,int(index))}, ' if name else ''
        next_step = 'để chuyển sang câu hỏi về các dự án khác bạn muốn thêm.' if stage == 'project' else 'để sang phần tiếp theo.'
        return context + 'bạn kể những việc trực tiếp thực hiện, công cụ/cách làm và đầu ra hoặc kết quả nếu có nhé. Bạn có thể kể ý thô; AI Writer sẽ giúp viết thành bullet. Một ý cụ thể là đủ, không cần số liệu nếu chưa đo lường. Đây là phần tùy chọn: nếu chưa muốn thêm, nhắn “để sau” hoặc “bỏ qua” ' + next_step
    label = dict(REQUIRED[stage])[field]
    from backend.app.services.assistant_answers import entry_reference
    reference=entry_reference(intake['profile'],stage,int(index))
    return f'Với {reference}, mình còn thiếu {label}. Bạn bổ sung giúp mình nhé. Nếu chưa biết hoặc chưa muốn thêm chi tiết này, bạn có thể nhắn “bỏ qua”.'


def collect(session, decision, text, task_id, polish_with_model=False):
    previous = session.get('cv_intake')
    before = missing_fields(previous or blank_intake())
    fast_signal = direct_signal(previous, text, session.get('messages'))
    from backend.app.services.assistant_answers import contextual_answer
    bound=contextual_answer((previous or blank_intake())['profile'],(before or ['complete'])[0],text) if not fast_signal else None
    if bound and not decision.updates: decision=bound
    signal = validated_signal(fast_signal or decision.intake_signal, text)
    polish_with_model = bool(polish_with_model and signal and signal.kind == 'write_bullets')
    explaining = bool(signal and signal.kind == 'explain' and normalized(signal.evidence) in normalized(text))
    wording = bool(signal and signal.kind=='wording')
    accepting = bool(signal and signal.kind=='accept_wording')
    if signal and signal.kind in {'more_entries','section_complete'}:
        from backend.app.services.assistant_lists import LISTS
        section = signal.section
        count = len((previous or blank_intake())['profile'].get(section, []))
        first_field = 'project_name' if section == 'project' else LISTS.get(section, ('',''))[1]
        awaiting = before and before[0] == f'{section}.{count}.{first_field}' and (previous or {}).get(section + '_next_index') == count
        if not before or (before[0] != section + '.more' and not awaiting): signal = None
    from backend.app.services.assistant_lists import personal_facts
    mixed_explanation = explaining and bool(decision.updates) and not fast_signal and personal_facts(text)
    updates = [] if (signal and signal.kind=='write_bullets') or fast_signal or (explaining and not mixed_explanation) or wording or accepting or (signal and signal.kind in {'more_entries','section_complete'}) else decision.updates
    if mixed_explanation:
        from backend.app.services.assistant_lists import factual_clauses
        statements = factual_clauses(text)
        updates = [patch for patch in updates if any(supported(patch.value, clause) for clause in statements)]
    if signal and signal.kind == 'not_available' and normalized(signal.evidence) in normalized(text):
        updates = [patch for patch in updates if patch.section != signal.section]
    if not signal and decision.intent in {'build_cv','prepare_cv'}:
        from backend.app.services.assistant_project_facts import enrich_project_updates
        updates = enrich_project_updates((previous or blank_intake())['profile'],(before or ['complete'])[0],text,updates)
    intake, rejected = apply_updates(previous, updates, text)
    if previous is None: intake['list_collection_version'] = 2
    polish_applied = 0
    if signal and signal.kind == 'accept_polish':
        for proposal in intake.pop('pending_polish',[]):
            if proposal['section']!='summary' and (proposal['index'] is None or proposal['index'] >= len(intake['profile'][proposal['section']])): continue
            entry = intake['profile'] if proposal['section']=='summary' else intake['profile'][proposal['section']][proposal['index']]
            if entry.get(proposal['field']) == proposal['original']:
                entry[proposal['field']] = proposal['proposed'];polish_applied += 1
        if polish_applied:
            intake['revision'] = intake.get('revision',0)+1
            intake.pop('draft_id',None)
    from backend.app.services.assistant_skills import group_skills
    if any(p.section == 'skills' for p in updates):
        intake['profile']['skills'] = group_skills(intake['profile']['skills'])
    from backend.app.services.assistant_skills import no_certificate
    if before and before[0].startswith('skills.') and before[0].endswith('.level') and no_certificate(text):
        certificate_path = before[0].rsplit('.',1)[0] + '.certificate'
        if certificate_path not in intake['skipped']: intake['skipped'].append(certificate_path)
    if signal and signal.section in {'project','education','experience','involvement'} and signal.kind in {'more_entries','section_complete'}:
        section = signal.section
        if signal.kind == 'more_entries':
            intake[section + '_next_index'] = len(intake['profile'][section])
        elif signal.kind == 'section_complete':
            intake[section + '_confirmed_count'] = len(intake['profile'][section])
            intake.pop(section + '_next_index',None)
            if intake.get('focus_section') == section: intake.pop('focus_section',None)
    wording_reply = None
    accepted_wording = False
    if wording:
        from backend.app.services.assistant_wording import propose_role
        from backend.app.services.assistant_answers import clarification_topic
        if signal.section=='project' and clarification_topic(text) in {None,'role'}:
            wording_reply, proposal = propose_role(intake,text,(before or ['complete'])[0])
        else:
            proposal = None
            wording_reply = decision.reply.strip() or explain_question(intake,text)
        if proposal: intake['pending_role_wording'] = proposal
        else:
            intake.pop('pending_role_wording',None)
            if signal.section=='project' and clarification_topic(text) in {None,'role'} and before and before[0].startswith('project.') and before[0].endswith('.role'):
                wording_reply = explain_question(intake,text)
    elif accepting:
        from backend.app.services.assistant_wording import confirm_role
        intake, wording_reply, accepted_wording = confirm_role(intake,text)
    navigating = bool(signal and signal.kind == 'navigate' and normalized(signal.evidence) in normalized(text))
    resuming = bool(signal and signal.kind == 'resume' and normalized(signal.evidence) in normalized(text))
    if navigating:
        intake['focus_section'] = signal.section
        intake['skipped'] = [path for path in intake.get('skipped',[]) if path.split('.')[0] != signal.section]
        intake['revision'] = intake.get('revision',0) + 1
        intake.pop('draft_id',None)
    focus = intake.get('focus_section')
    if focus and not navigating and (resuming or accepted_wording or any(patch.section == focus for patch in updates)):
        if not any(path.split('.')[0] == focus for path in remaining_fields(intake)):
            intake.pop('focus_section',None)
    missing = missing_fields(intake)
    skipped_now = False
    path = accepted_signal(previous or blank_intake(), signal, text)
    if path and before:
        intake.setdefault('skipped', [])
        if path not in intake['skipped']: intake['skipped'].append(path)
        intake['revision'] = intake.get('revision', 0) + 1
        intake.pop('draft_id', None)
        skipped_now = True
        if intake.get('focus_section') == path.split('.')[0]: intake.pop('focus_section',None)
        missing = missing_fields(intake)
    history = stage_history(previous or blank_intake(),session.get('messages'))
    for stage in [(before or [''])[0].split('.')[0], (missing or [''])[0].split('.')[0]]:
        if stage in STAGES and (not history or history[-1] != stage): history.append(stage)
    intake['step_history'] = history[-24:]
    intake['current_step'] = missing[0] if missing else 'complete'
    # The intake owns follow-up requests; the model only answers actual questions.
    model_reply = decision.reply.strip() if bound or decision.intent in {'advice', 'clarify'} or '?' in text or asks_for_explanation(text) else ''
    reply = model_reply or 'Mình đã nhận thông tin bạn vừa chia sẻ.'
    if wording_reply:
        reply = wording_reply
    elif navigating:
        reply = f'Mình đã quay lại phần {TITLES[signal.section].lower()}. Những thông tin đã nhập vẫn được giữ nguyên.'
    elif resuming:
        reply = 'Mình sẽ tiếp tục từ thông tin bạn đã cung cấp.'
    elif explaining:
        reply = decision.reply.strip() if mixed_explanation and decision.reply.strip() else explain_question(previous or blank_intake(), text, session.get('messages'))
    elif signal and signal.kind == 'more_entries':
        reply = f'Được nhé, mình sẽ thêm thông tin {TITLES[signal.section].lower()} mới và giữ nguyên các mục đã nhập.'
    elif signal and signal.kind == 'section_complete':
        reply = f'Đã ghi nhận bạn đã kể hết phần {TITLES[signal.section].lower()}. Mình giữ nguyên danh sách hiện tại và chuyển sang phần tiếp theo.'
    elif signal and signal.kind == 'accept_polish':
        reply = f'Đã áp dụng {polish_applied} phần tinh chỉnh bạn vừa duyệt.' if polish_applied else 'Nội dung đã thay đổi, nên mình chưa áp dụng gợi ý cũ. Bạn có thể yêu cầu tinh chỉnh lại.'
    elif not previous: reply = 'Mình sẽ cùng bạn hoàn thiện CV từng phần. Phần nào chưa có, bạn cứ nói “chưa có”; mình sẽ chuyển sang phần tiếp theo.'
    elif skipped_now:
        title = TITLES[path.split('.')[0]].lower()
        if len(path.split('.')) == 3:
            field = path.split('.')[-1]
            detail = 'mô tả công việc/kết quả chi tiết' if field == 'work' else dict(REQUIRED[path.split('.')[0]]).get(field, 'chi tiết này')
            reply = f'Được nhé, mình sẽ chưa thêm {detail}. Các thông tin {title} đã nhập vẫn được giữ nguyên.'
        else:
            reply = f'Mình hiểu rồi, mình sẽ bỏ qua phần {title} và giữ lại những thông tin bạn đã cung cấp.'
    elif updates and any(p.section == 'skills' for p in updates):
        grouped = intake['profile']['skills']
        reply = 'Mình đã ghi nhận và phân nhóm kỹ năng của bạn:\n' + '\n'.join(f'• {e["group"]}: {", ".join(e["items"])}' for e in grouped)
    elif rejected: reply = 'Có chi tiết chưa đối chiếu được với lời bạn kể nên mình chưa đưa vào bản nháp.'
    elif updates and any(p.section == 'project' and p.field == 'project_type' for p in updates):
        project_index = next(p.index for p in updates if p.section == 'project' and p.field == 'project_type')
        entry = intake['profile']['project'][project_index]
        from backend.app.services.assistant_answers import entry_reference
        reply = f'Mình đã ghi nhận {entry_reference(intake["profile"],"project",project_index)}; loại dự án: {entry.get("project_type")}. ' + (f'Phần bạn trực tiếp làm: {entry["role"]}. Mình đã có mô tả phần bạn đảm nhận, không cần liệt kê thêm vai trò.' if entry.get('role') else 'Mình sẽ hỏi thêm phần bạn trực tiếp đảm nhận nếu chưa có thông tin.')
    if len(updates) > 1 and not rejected and not wording:
        labels = {'full_name':'họ tên','email':'email','phone':'điện thoại','institution':'trường','major':'ngành học','project_name':'tên dự án','project_type':'loại dự án','job_title':'vị trí','company':'nơi làm việc','description':'công việc','technologies':'công nghệ','github_url':'GitHub','demo_url':'link demo','project_url':'link dự án','items':'kỹ năng'}
        details = []
        for patch in updates:
            value = ', '.join(patch.value) if isinstance(patch.value,list) else patch.value
            if isinstance(value,str): details.append(f'{labels.get(patch.field,patch.field or TITLES[patch.section])}: {value}')
        if details: reply = 'Mình đã ghi nhận:\n' + '\n'.join('• ' + detail for detail in details) + '\n\n' + reply
    from backend.app.services.assistant_lists import cv_question_answer
    side_answer = cv_question_answer(text)
    if side_answer and not wording and (not explaining or mixed_explanation):
        reply += '\n\n' + side_answer
    if missing:
        if not (explaining or wording or (accepting and not accepted_wording)):
            if missing[0] == 'contact.reach' and not updates and not model_reply and not side_answer:
                reply = question(missing[0], intake)
            else:
                reply += '\n\n' + question(missing[0], intake)
    elif not (wording or (accepting and not accepted_wording)):
        reply += '\n\nMình đã đi qua tất cả các phần của CV. Bạn có thể yêu cầu sửa thêm, hoặc mở form kiểm tra thông tin rồi chọn mẫu CV.'
    stage = missing[0].split('.')[0] if missing else None
    from backend.app.services.assistant_dialogue import dialogue_context
    frame=dialogue_context(intake,(missing or ['complete'])[0],session.get('messages'))
    if not (explaining or wording):
        intake['dialogue_focus'] = {k:frame[k] for k in ('section','index','field','action','entity','known_role')}
    from backend.app.services.cv_polish import chat_proposals
    suggestions = chat_proposals(previous,intake,updates,use_model=polish_with_model) if updates and not (explaining or wording) else []
    result = dict(type='cv_intake', text=reply, intake=dict(profile=intake['profile'],target_role=intake.get('target_role'),missing=missing,revision=intake.get('revision',0),step=stage,step_title=TITLES.get(stage,'Hoàn tất'),step_number=STAGES.index(stage)+1 if stage else len(STAGES),total_steps=len(STAGES)), _intake=intake)
    if signal and signal.kind=='write_bullets':
        from backend.app.services.cv_writer import WriterRequest,write_bullets,preserve_unedited_lines
        entries=intake['profile'][signal.section]
        if entries:
            frame=intake.get('dialogue_focus') or {}
            index=frame.get('index') if frame.get('section')==signal.section and frame.get('index') is not None else len(entries)-1
            index=min(index,len(entries)-1)
            entry=entries[index]
            field='details' if signal.section=='education' else 'description'
            original=entry.get(field) or []
            generated=write_bullets(WriterRequest(section=signal.section,field=field,entry=entry,text='\n'.join(original)),use_model=polish_with_model)
            if generated['bullets']:
                merged=preserve_unedited_lines(original,generated['bullets'])
                suggestions=[dict(section=signal.section,index=index,field=field,original=entry.get(field,[]),proposed=[b['text'] for b in merged],bullet_sources=[b['sources'] for b in merged],questions=generated['questions'])]
                result['text']='Mình đã viết lại các ý bạn cung cấp thành bullet. Bạn kiểm tra câu đề xuất và thông tin nguồn rồi chọn áp dụng; dữ kiện gốc vẫn được giữ nguyên.'
            else:
                result['text']='Để viết bullet đúng với bạn, mình cần biết việc bạn trực tiếp thực hiện. '+ ' '.join(generated['questions'])
        else:
            result['text']='Bạn muốn viết bullet cho mục nào? Kể tên công việc/dự án và những việc bạn trực tiếp thực hiện; mình sẽ viết từ các thông tin đó.'
    if suggestions: intake['pending_polish'] = suggestions
    if suggestions: result['wording_suggestions'] = suggestions
    if not missing:
        draft_id = 'draft_' + task_id.removeprefix('task_')
        intake['draft_id'] = draft_id
        result.update(href=f'/workspace/resumes/new?draft={draft_id}',
            _profile_draft=dict(draft_id=draft_id,base_profile_id=None,version=1,status='editing',profile=intake['profile'],updated_at=utc_now(),confirmed_profile_id=None,confirmation_event_id=None))
    return result
