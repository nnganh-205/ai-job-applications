"""Group stated skills and ask optional language follow-ups without inventing levels."""
import re
from backend.app.services.assistant_answers import fold
from backend.app.schemas.assistant import IntentDecision, ProfilePatch, IntakeSignal

LANGUAGE = re.compile(r'\b(tieng anh|english|tieng nhat|japanese|tieng han|korean|tieng trung|chinese|tieng phap|french|tieng duc|german)\b')
LANGUAGE_LABELS = dict(zip(['tieng anh','english','tieng nhat','japanese','tieng han','korean','tieng trung','chinese','tieng phap','french','tieng duc','german'],['Tiếng Anh','Tiếng Anh','Tiếng Nhật','Tiếng Nhật','Tiếng Hàn','Tiếng Hàn','Tiếng Trung','Tiếng Trung','Tiếng Pháp','Tiếng Pháp','Tiếng Đức','Tiếng Đức']))
CERT = re.compile(r'\b(ielts|toeic|toefl|jlpt|topik|hsk|delf|dalf|goethe|cambridge)\b')
LEVEL = re.compile(r'\b(a[12]|b[12]|c[12]|n[1-5]|co ban|giao tiep|doc hieu|thanh thao|trung cap|so cap|cao cap|luu loat|nghe|noi|doc|viet)\b')
GROUPS = {
    'Ngôn ngữ lập trình': {'python','pyton','javascript','typescript','java','c++','c#','sql','go','rust'},
    'Framework & thư viện': {'pytorch','tensorflow','numpy','pandas','scikit-learn','sklearn','hugging face','huggingface','unsloth','langgraph','langchain','react','fastapi','django','flask','node.js','transformers'},
    'Công cụ phát triển': {'git','docker','google earth engine','gee','qgis','jupyter','jupyter notebook','vs code','visual studio code','google colab','colab','mlflow','cuda','excel','power bi','tableau'},
    'AI & học máy': {'cnn','transformer','rag','prompt engineering','promt engineering','computer vision','machine learning','deep learning'},
    'Kỹ năng làm việc': {'giao tiep','lam viec nhom','thuyet trinh','quan ly thoi gian','giai quyet van de'},
}


def language_key(entry):
    for item in entry.get('items',[]):
        match=LANGUAGE.search(fold(item))
        if match: return match.group()
    return None


def category(item, fallback=None):
    plain=fold(item).strip()
    if LANGUAGE.search(plain): return 'Ngoại ngữ · '+LANGUAGE_LABELS[LANGUAGE.search(plain).group()]
    base = plain.split('(',1)[0].strip()
    for label,words in GROUPS.items():
        if plain in words or base in words: return label
    aliases={'ngon ngu lap trinh':'Ngôn ngữ lập trình','framework & thu vien':'Framework & thư viện',
             'framework & libraries':'Framework & thư viện','cong cu phat trien':'Công cụ phát triển'}
    return aliases.get(fold(fallback or '').strip(),fallback) or 'Kỹ năng khác'


def group_skills(entries):
    grouped={}
    for entry in entries:
        for item in entry.get('items',[]):
            label=category(item,entry.get('group'))
            # Language details appended to an existing language group stay with it.
            if (entry.get('group') or '').startswith('Ngoại ngữ') and not LANGUAGE.search(fold(item)):
                label=entry['group']
            if label not in grouped: grouped[label]=dict(group=label,items=[])
            if item not in grouped[label]['items']: grouped[label]['items'].append(item)
    return list(grouped.values())


def language_missing(intake):
    entries=intake['profile']['skills']; skipped=intake.get('skipped',[])
    languages=[(i,e) for i,e in enumerate(entries) if language_key(e)]
    if not languages:
        return [] if 'skills.languages' in skipped else ['skills.languages']
    fields=[]
    checks=intake.get('skill_language_checks',{})
    for i,entry in languages:
        value=' '.join(fold(x) for x in entry['items'])
        state=checks.get(language_key(entry),{})
        has_cert=bool(CERT.search(value))
        scores = re.findall(r'\b(ielts|toeic|toefl)\s*(?:(?:overall|band|dat|duoc|:)\s*)?(\d+(?:[.,]\d+)?)\b',value)
        has_score = any(0 <= float(score.replace(',','.')) <= {'ielts':9,'toeic':990,'toefl':120}[exam] for exam,score in scores)
        has_level=bool(LEVEL.search(value)) or has_score
        if not has_level and not state.get('level') and f'skills.{i}.level' not in skipped: fields.append(f'skills.{i}.level')
        if not has_cert and not state.get('certificate') and f'skills.{i}.certificate' not in skipped: fields.append(f'skills.{i}.certificate')
    return fields


def skill_question(path,intake):
    if path=='skills.languages':
        return 'Phần ngoại ngữ chưa có thông tin. Bạn sử dụng được ngoại ngữ nào và ở mức nào (ví dụ giao tiếp hoặc đọc hiểu tài liệu)? Nếu có chứng chỉ, kể tên, điểm/cấp độ và thời điểm thi nếu nhớ. Nếu chưa có ngoại ngữ muốn đưa vào CV, nhắn “chưa có ngoại ngữ” hoặc “bỏ qua”.'
    parts=path.split('.')
    if len(parts)==3 and parts[0]=='skills' and parts[2] in {'level','certificate'}:
        entry=intake['profile']['skills'][int(parts[1])]
        name=next((x for x in entry['items'] if LANGUAGE.search(fold(x))), 'ngoại ngữ này')
        if parts[2]=='level': return f'Với {name}, bạn đang sử dụng ở mức nào hoặc làm được việc gì: giao tiếp, đọc tài liệu, viết email…? Chỉ mô tả đúng khả năng; chưa rõ thì nhắn “bỏ qua”.'
        return f'Với {name}, bạn đã có chứng chỉ nào chưa? Nếu có, kể tên và điểm/cấp độ; có thể thêm thời điểm thi. Nếu chưa có, nhắn “chưa có chứng chỉ”; phần ngoại ngữ và mức sử dụng vẫn được giữ nguyên.'
    return None


def no_certificate(text):
    return bool(re.fullmatch(r'(?:(?:minh|toi|em) )?(?:chua|khong)(?: co)? chung chi(?: nao)?(?: ca)?(?: ngoai ngu)?(?: nhe| a)?',fold(' '.join(text.split())).strip(' .!…')))


def skill_signal(path,text):
    plain=fold(' '.join(text.split())).strip(' .!…')
    if (path=='skills.languages' or (path.startswith('skills.') and path.endswith('.level'))) and no_certificate(text):
        return IntakeSignal(kind='explain',section='skills',evidence=text)
    if path=='skills.languages' and re.fullmatch(r'(?:(?:minh|toi|em) )?(?:chua co ngoai ngu|khong co ngoai ngu|khong them ngoai ngu|chua co|khong co|bo qua|de sau)',plain):
        return IntakeSignal(kind='skip',section='skills',evidence=text)
    if path.endswith('.certificate') and path.startswith('skills.') and re.fullmatch(r'(?:(?:minh|toi|em) )?(?:chua|khong)(?: co)?(?: chung chi(?: nao)?(?: ca)?)?(?: ngoai ngu)?(?: nhe| a)?',plain):
        return IntakeSignal(kind='skip',section='skills',evidence=text)
    return None


def skill_answer(profile,path,text):
    plain=fold(text)
    if re.search(r'[?]|\b(?:la sao|vi du|gia su|chua|khong|bo qua|de sau|het roi)\b',plain): return None
    parts=path.split('.')
    if len(parts)==3 and parts[0]=='skills' and parts[2] in {'level','certificate'}:
        if parts[2]=='level' and not (LEVEL.search(plain) or CERT.search(plain)): return None
        if parts[2]=='certificate' and not CERT.search(plain): return None
        return IntentDecision(intent='build_cv',reply='Mình đã ghi nhận thông tin ngoại ngữ bạn vừa cung cấp.',updates=[ProfilePatch(section='skills',index=int(parts[1]),field='items',operation='append',value=[text.strip()],evidence=text)])
    if path in {'skills','skills.languages'}:
        labelled = labelled_skills(text)
        if labelled:
            updates=[]
            for offset,(label,items) in enumerate(labelled):
                index=len(profile['skills'])+offset
                updates.extend([
                    ProfilePatch(section='skills',index=index,field='group',value=label,evidence=text),
                    ProfilePatch(section='skills',index=index,field='items',value=items,evidence=text),
                ])
            return IntentDecision(intent='build_cv',updates=updates)
        # Clear skill lists use only verbatim items. Unknown or mixed statements go to the model.
        raw=re.sub(r'^(?:(?:mình|tôi|em)\s+)?(?:dùng được|sử dụng được|biết|dùng)\s+', '',text.strip(),flags=re.I)
        items=skill_items(raw)
        known=set().union(*GROUPS.values())
        if not items or not all(fold(x).split('(',1)[0].strip() in known or LANGUAGE.search(fold(x)) for x in items): return None
        start=len(profile['skills'])
        return IntentDecision(intent='build_cv',updates=[ProfilePatch(section='skills',index=start,field='items',value=items,evidence=text)])
    return None


def labelled_skills(text):
    headers=list(re.finditer(r'(Ngôn ngữ lập trình|Framework\s*&\s*(?:thư viện|libraries)|Công cụ phát triển)\s*:',text,re.I))
    if not headers or text[:headers[0].start()].strip(' ,;\n'):
        return None
    groups=[]
    for i,header in enumerate(headers):
        content=text[header.end():headers[i+1].start() if i+1<len(headers) else len(text)].strip(' ,;\n')
        items=skill_items(content)
        if not items:return None
        groups.append((header[1].strip(),items))
    return groups if len(groups)<=10 else None


def skill_items(content):
    items=[];start=depth=0
    for i,char in enumerate(content):
        if char in '([':depth+=1
        elif char in ')]':depth=max(0,depth-1)
        elif char in ',;\n' and depth==0:
            value=content[start:i].strip()
            if value:items.append(value)
            start=i+1
    value=content[start:].strip()
    if value:items.append(value)
    return items
