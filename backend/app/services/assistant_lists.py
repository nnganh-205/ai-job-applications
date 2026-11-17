"""Explicit list completion across CV sections, without guessing a user's history."""
import re
from backend.app.services.assistant_answers import fold
from backend.app.schemas.assistant import IntakeSignal

LISTS = {'education': ('học vấn', 'institution'), 'experience': ('kinh nghiệm', 'company'), 'involvement': ('hoạt động', 'activity_name')}


def list_signal(intake, path, text):
    section = path.split('.')[0]
    if section not in LISTS: return None
    count = len(intake['profile'][section])
    awaiting = path == f'{section}.{count}.{LISTS[section][1]}' and intake.get(section + '_next_index') == count
    if path != section + '.more' and not awaiting: return None
    plain = fold(' '.join(text.split())).strip(' .!…')
    plain = re.sub(r'^(?:minh|toi|em) ', '', plain)
    plain = re.sub(r' (?:nhe|nha|a)$', '', plain)
    if plain in {'khong','khong con','het roi','het','da het','da nhap het','xong','da xong','chi co vay','khong them nua','bo qua','de sau','chua co','khong co them'} or re.fullmatch(r'(?:khong con|khong co) (?:kinh nghiem|cong viec|hoat dong|chuong trinh|truong)(?: nao)?(?: khac| nua)?',plain):
        return IntakeSignal(kind='section_complete', section=section, evidence=text)
    if plain in {'co','con','van con','con nua','co them','chua het','con mot cai nua','them nua'} or re.fullmatch(r'(?:con|co them|muon them) (?:kinh nghiem|cong viec|hoat dong|chuong trinh|truong)(?: khac| nua)?',plain):
        return IntakeSignal(kind='more_entries', section=section, evidence=text)
    return None


def personal_facts(text):
    """Mixed fact + question must reach extraction, not the explain-only shortcut."""
    clauses = re.split(r'[,;.!?\n]|\bnhung\b', fold(text))
    return any(re.match(r'\s*(?:minh|toi|em|to) (?:da |dang |tung |chi )?(?:hoc|lam|phu trach|su dung|biet|tham gia|tot nghiep|thuc tap|co du an)\b', clause) and not re.search(r'\b(?:vi du|gia su|hay|la sao|la gi|nen|phai khong)\b',clause) for clause in clauses)


def factual_clauses(text):
    return [clause.strip() for clause in re.split(r'[,;.!?\n]',text) if clause.strip() and not re.search(r'\b(?:vi du|gia su|la sao|la gi|nen ghi|phai viet|thi sao)\b|^\s*(?:neu|ban muon|co phai)\b', fold(clause))]


def upgrade_lists(intake):
    """Resume old sessions without re-asking completed earlier sections."""
    from copy import deepcopy
    if not intake or intake.get('list_collection_version',1)>=2: return intake
    from backend.app.services.assistant_intake import STAGES, missing_fields
    result=deepcopy(intake)
    current=(missing_fields(intake) or ['summary'])[0].split('.')[0]
    position=STAGES.index(current) if current in STAGES else len(STAGES)
    for section in LISTS:
        if STAGES.index(section)<position:
            result[section+'_confirmed_count']=len(result['profile'][section])
    result['list_collection_version']=2
    return result


def cv_question_answer(text):
    plain=fold(text)
    if not re.search(r'[?]|\b(?:bat buoc|can khong|duoc khong|phai co|thi sao|nen ghi gi)\b',plain): return None
    if re.search(r'\b(?:ket qua|so lieu|thanh tich)\b',plain):
        return 'Không bắt buộc có số liệu hoặc thành tích định lượng. Bạn có thể nêu đầu ra thực tế như tính năng đã hoàn thành, sản phẩm hoặc việc đã bàn giao; nếu chưa có thì để trống. Mình sẽ không tự đặt số liệu hoặc kết quả cho bạn.'
    if re.search(r'\b(?:chung chi|ielts|toeic)\b',plain):
        return 'Không bắt buộc có chứng chỉ để ghi ngoại ngữ. Bạn có thể nêu ngôn ngữ và khả năng sử dụng thực tế; chỉ ghi tên chứng chỉ hoặc điểm khi bạn đã có kết quả thật.'
    if re.search(r'\b(?:gpa|diem trung binh)\b',plain):
        return 'GPA là phần tùy chọn. Bạn có thể để trống; nếu ghi thì dùng điểm thực tế và thang điểm của trường.'
    return None
