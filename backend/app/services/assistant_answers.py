"""Bind clear short answers to the field being asked, without inventing CV facts."""
import re
import unicodedata
from backend.app.schemas.assistant import IntentDecision, ProfilePatch


def fold(text):
    return ''.join(c for c in unicodedata.normalize('NFD', text.casefold()) if not unicodedata.combining(c)).replace('đ', 'd')


def clarification_topic(text):
    plain = fold(text)
    if re.search(r'\bmuc\s*(?:thu\s*)?\d+\b|\bmuc (?:la (?:gi|sao|soa)|nghia la)|\b(?:co nhieu|bao nhieu) muc\b',plain): return 'entry'
    for pattern, topic in [(r'\b(vai tro|chuc danh|trach nhiem)\b','role'),(r'\b(ky nang|cong cu)\b','skills'),(r'\b(nganh hoc|chuyen nganh)\b','major'),(r'\b(hoc van)\b','education'),(r'\b(cong viec|nhiem vu)\b','work'),(r'\b(du an|do an)\b','project')]:
        if re.search(pattern,plain): return topic
    return None


def clarification_request(text):
    """Recognize questions about how to answer, even without a question mark."""
    plain = fold(' '.join(text.split()))
    # A message containing a personal fact plus a question needs semantic extraction.
    if re.search(r'\b(?:minh|toi|em|to) (?:da |dang |se |chi )?(?:lam|phu trach|dam nhan|xay dung|thiet ke|hoc|biet|su dung)\b',plain):
        return False
    query = bool(re.search(r'\b(?:nhung gi|la gi|la sao|la soa|co nhieu muc|bao nhieu muc|gom gi|nghia la|nhu the nao|ra sao|can ghi gi|nen ghi gi|phai viet gi|viet the nao|ghi the nao|giai thich|cho (?:minh |em |toi )?vi du)\b',plain))
    subject = bool(re.search(r'\b(?:vai tro|trach nhiem|cong viec|du an|do an|ky nang|hoc van|nganh hoc|muc(?:\s*(?:thu\s*)?\d+)?|muc nay|muc do|phan nay|phan do|cau hoi)\b',plain))
    return query and (subject or bool(re.search(r'\b(?:giai thich|vi du|can ghi gi|nen ghi gi|phai viet gi)\b',plain)))


def answer_context(profile, path):
    parts = path.split('.')
    if path in {'education.more','experience.more','involvement.more'}:
        section=path.split('.')[0]
        return dict(section=section,index=len(profile[section]),asked_field='more',instruction='Hỏi còn mục nào muốn thêm hay đã hết. Kể ngay mục tiếp theo thì ghi vào index này, không sửa mục cũ. Chỉ section_complete khi người dùng xác nhận đã hết; câu hỏi thì explain.')
    if path == 'project.more':
        return dict(section='project',index=len(profile['project']),asked_field='more',instruction='Hỏi còn dự án nào muốn thêm hay đã hết. Nếu kể dự án tiếp theo, thêm tại index này; không ghi đè dự án cũ. Nếu chưa hiểu thì explain, nếu đã hết thì section_complete, nếu còn nhưng chưa kể thì more_entries. Chỉ hoàn tất danh sách khi người dùng xác nhận.')
    if len(parts) != 3 or not parts[1].isdigit(): return None
    section, index, field = parts[0], int(parts[1]), parts[2]
    entries = profile.get(section, [])
    if index >= len(entries): return None
    return dict(section=section,index=index,asked_field=field,
                data_field='description' if field == 'work' else field,
                entry=entries[index],
                instruction='Hiểu câu ngắn theo đúng mục này. Chép nguyên văn dữ kiện; vai trò không bắt buộc là chức danh. Nếu mơ hồ, hỏi cụ thể điều chưa rõ, không lặp lại câu hỏi đã được trả lời.')


def entry_reference(profile, section, index):
    labels = {'project':'dự án','education':'học vấn','experience':'kinh nghiệm','involvement':'hoạt động','skills':'nhóm kỹ năng'}
    entries = profile.get(section, [])
    entry = entries[index] if isinstance(entries,list) and index < len(entries) else {}
    name = next((entry.get(key) for key in ('project_name','institution','company','activity_name','organization','group') if entry.get(key)),None)
    label = labels.get(section,'thông tin')
    if name: return f'{label} “{name}”'
    return label + (f' thứ {index+1}' if len(entries)>1 else ' của bạn')


def contextual_answer(profile, path, text):
    from backend.app.services.assistant_wording import wording_request
    if wording_request(text,path): return None
    if clarification_request(text): return None
    if path == 'project' or path == 'project.more' or re.fullmatch(r'project\.\d+\.project_name',path):
        from backend.app.services.assistant_project_facts import enrich_project_updates
        extracted = enrich_project_updates(profile,path,text,[])
        if {'project_name','project_type','role','description'} <= {p.field for p in extracted}:
            return IntentDecision(intent='build_cv',updates=extracted)
    if path.startswith('skills'):
        from backend.app.services.assistant_skills import skill_answer
        return skill_answer(profile,path,text)
    context = answer_context(profile, path)
    if not context or path == 'project.more' or context['section'] not in {'project','experience','involvement'}: return None
    plain = fold(' '.join(text.split())).strip(' .!…')
    field = context['asked_field']
    personal = re.search(r'dự án cá nhân|du an ca nhan',text,re.I)
    owns_all = bool(re.search(r'\b(?:minh|toi|em|to) (?:tu )?(?:lam het|lam toan bo|thuc hien toan bo|tu lam)\b',plain))
    if context['section']=='project' and personal and owns_all and field in {'role','work'} and not re.search(r'\b(?:bang|su dung|cong nghe|cong cu)\b',plain) and not re.search(r'[?]|\b(?:vi du|gia su|neu|nhung|khong|chua)\b',plain):
        updates=[]
        if not context['entry'].get('project_type'):
            updates.append(ProfilePatch(section='project',index=context['index'],field='project_type',value=personal.group(),evidence=text))
        if field=='role':
            updates.append(ProfilePatch(section='project',index=context['index'],field='role',value=text.strip(),evidence=text))
        return IntentDecision(intent='build_cv',reply='Mình hiểu đây là dự án cá nhân và bạn tự thực hiện toàn bộ, nên không cần liệt kê thêm vai trò. Mô tả công việc hoặc kết quả bên dưới là phần bổ sung tùy chọn.',updates=updates)
    if len(text) > 180 or re.search(r'\b(?:bang|su dung|dong thoi|kiem)\b', plain) or re.search(r'[,?;:\n]|\b(nhung|vi du|la sao|chua|khong|nen|hay la|duoc ko|duoc khong|the nao|lam sao|quay lai|bo qua)\b', plain): return None
    # Only direct self-attribution; a teammate's or the group's work is not the user's role.
    statement = bool(re.fullmatch(
        r'(?:(?:minh|toi|em|to) (?:chi )?)?(?:'
        r'lam (?:het|tat ca|toan bo|ca|chinh|phan|giao dien|backend|frontend|thiet ke|lap trinh)\b.*|'
        r'(?:tu lam|tu thuc hien|tu trien khai|phu trach|dam nhan|ho tro|chiu trach nhiem)\b.*)', plain))
    role_label = plain in {'frontend','backend','fullstack','full-stack','thanh vien','truong nhom','lap trinh vien','thiet ke giao dien'}
    if not (statement or role_label): return None
    field = context['asked_field']
    if field == 'work' and re.search(r'\b(het|tat ca|toan bo|moi thu|tu lam)\b', plain):
        return IntentDecision(intent='build_cv',reply='Mình hiểu bạn phụ trách toàn bộ. Để đưa vào CV rõ ràng, mình cần vài việc cụ thể bạn đã thực hiện; mình sẽ không tự đoán các công việc đó.')
    if field not in {'role','job_title'}: return None
    return IntentDecision(intent='build_cv',
        reply=f'Mình đã ghi nhận vai trò bạn vừa mô tả: “{text.strip()}”.',
        updates=[ProfilePatch(section=context['section'],index=context['index'],field='role',value=text.strip(),evidence=text)])
