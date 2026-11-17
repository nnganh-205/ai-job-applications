"""Conservative checks, not a claim of complete semantic factual verification."""
import re
from ai.agents.matching_agent import canonical,contains_term

TECHNOLOGIES={'Python','Java','JavaScript','TypeScript','C++','C#','.NET','Go','Golang',
    'Rust','Ruby','PHP','Swift','Kotlin','Scala','SQL','NoSQL','PostgreSQL','MySQL',
    'MongoDB','Redis','Elasticsearch','Docker','Kubernetes','AWS','Azure','GCP',
    'React','Angular','Vue','Node.js','FastAPI','Django','Flask','Spring','Laravel',
    'TensorFlow','PyTorch','Pandas','NumPy','Spark','Kafka','Airflow','Terraform',
    'Jenkins','GitHub','GitLab','Linux','LLM','NLP','API','REST API'}
_STOP={'I','A','An','The','And','In','For','With','During','At','On','By','Using',
       'This','That','We','It','My','Our','To','As','Of','Built','Developed','Designed',
       'Implemented','Created','Supported','Worked','Collaborated','Maintained',
       'Improved','Used','Wrote','Delivered','Analyzed','Optimized','Assisted','Engineered',
       'Refactored','Tested','Debugged','Automated','Configured','Integrated','Deployed',
       'Led','Managed','Xây','Thiết','Tối','Tham','Phát','Triển','Hỗ','Đã','Làm','Cải',
       'Tạo','Sử','Viết','Quản','Xử','Kết','Chuẩn','Tích','Bảo','Đảm','Đưa','Tự','Từng',
       'Chủ','Góp','Giúp','Duy','Vận','Nghiên','Hoàn'}
_NEGATIVE=r"\b(?:never|not|no|without|haven't|hasn't|didn't|cannot|can't)\b|chưa|không|chẳng"
_SCOPE=[r'\b(?:led|lead|managed|owned|architected)\b|dẫn dắt|quản lý|chịu trách nhiệm chính',
        r'\b(?:expert|advanced|proficient|mastered)\b|chuyên gia|thành thạo',
        r'\b(?:production|enterprise|certified)\b|chứng chỉ|chứng nhận']

def entities(text):
    found=set()
    for match in re.finditer(r'(?<!\w)[A-ZÀ-Ỹ][\w.+#-]*',text):
        word=match.group().rstrip('.')
        if word in _STOP:continue
        found.add(canonical(word))
    return found

def _legacy_grounded_rewrite(original,proposed):
    if not proposed.strip():return False
    numbers=lambda t:set(re.findall(r'\d+(?:[.,]\d+)?%?',t))
    if numbers(original)!=numbers(proposed):return False
    if bool(re.search(_NEGATIVE,original,re.I))!=bool(re.search(_NEGATIVE,proposed,re.I)):return False
    if any(re.search(pattern,proposed,re.I) and not re.search(pattern,original,re.I) for pattern in _SCOPE):return False
    if any(contains_term(proposed,term) and not contains_term(original,term) for term in TECHNOLOGIES):return False
    if not entities(proposed)<=entities(original):return False
    links=lambda t:set(re.findall(r'https?://\S+|[\w.+-]+@[\w.-]+',t))
    return links(original)==links(proposed)


def job_brief(requirements):
    """Remove duplicate/raw JD and runtime fields before CV review; keep evidence."""
    if requirements is None:return None
    fields=('required_skills','preferred_skills','unspecified_skills','experience_requirements',
            'education_requirements','technical_requirements','certifications','languages')
    brief={}
    for field in fields:
        values=requirements.get(field,[])
        if values:brief[field]=[{k:v for k,v in row.items() if k in {'name','description','requirement_type','evidence'}} for row in values]
    if requirements.get('requirement_groups'):
        brief['groups']=[{k:v for k,v in g.items() if k in {'operator','members','requirement_type','evidence'}} for g in requirements['requirement_groups']]
    return brief


GUARD_VERSION='cv-grounding-v2.6'
# Closed spelling/grammar equivalences, not a semantic synonym dictionary.
_ALIAS_RULES=[(r'\bpostgres\b','PostgreSQL'),(r'\bmy\s+sql\b','MySQL'),(r'\bpostgre\s+sql\b','PostgreSQL'),(r'\bnode\s*\.?\s+js\b','Node.js')]
_EDIT_RULES=[
    (r'\bin order to\b','to','conciseness'),
    (r'\bon a monthly basis\b','monthly','conciseness'),
    (r'\bon a daily basis\b','daily','conciseness'),
    (r'\bon a weekly basis\b','weekly','conciseness'),
    (r'\bon an annual basis\b','annually','conciseness'),
    (r'\butilized\b','used','wording'),(r'\butilize\b','use','wording'),
    (r'\butilizing\b','using','wording'),
    (r'\bworked collaboratively with\b','collaborated with','wording'),
    (r"\bdidn't\b",'did not','grammar'),(r"\bcan't\b",'cannot','grammar'),
    (r'\brecieved\b','received','spelling'),(r'\bsuccesfully\b','successfully','spelling'),
    (r'\bresponsibilites\b','responsibilities','spelling'),(r'\bcommuncation\b','communication','spelling'),
]
_FUNCTION_WORDS={'a','an','the'}
_PROFICIENCY=r'\b(?:basic|basics|beginner|intermediate|advanced|expert|proficient|familiar|limited|fluent|certified)\b|cơ bản|thành thạo|chuyên gia|sơ cấp'
_CONTRIBUTION=r'\b(?:assist(?:ed|ing)?|support(?:ed|ing)?|help(?:ed|ing)?|participat(?:e|ed|ing)|contribut(?:e|ed|ing)|collaborat(?:e|ed|ing)|led|lead(?:ing)?|manag(?:e|ed|ing)|own(?:ed|ing)?|architect(?:ed|ing)?|supervis(?:e|ed|ing))\b|hỗ trợ|tham gia|phối hợp|cộng tác|dẫn dắt|chủ trì|quản lý'
_CONDITIONS=r'[<>]=?|[≤≥≈]|(?<=\d)\+|\b(?:only|if|unless|when|without|under supervision|at least|at most|up to|more than|less than|approximately|about|over|under)\b|\bchỉ\b(?!\s+(?:số|tiêu|ra|dẫn|định|thị|mục)\b)|nếu|trừ khi|tối thiểu|tối đa|dưới sự giám sát'
_SUBJECTS=r'\b(?:i|we|our|they|their|he|she|his|her|team|teams|client|clients|customer|customers)\b|chúng tôi|nhóm|khách hàng'
_UNITS=r'[%$€£₫¥°]|\b(?:daily|weekly|monthly|quarterly|annually|yearly)\b|\b(?:percent|percentage|usd|vnd|eur|gbp|dollars?|hours?|days?|weeks?|months?|years?|seconds?|milliseconds?|ms|kb|mb|gb|tb|kg|km|thousand|million|billion|kpi)\b|phần trăm|giờ|ngày|tuần|tháng|năm|triệu|tỷ'
_MONTHS=r'\b(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\b'
_NEGATIONS=r"\b(?:never|not|no|without|haven't|hasn't|didn't|cannot|can't|isn't|wasn't)\b|chưa|không|chẳng"


def normalize_technology_spelling(text):
    for pattern,value in _ALIAS_RULES:text=re.sub(pattern,value,text,flags=re.I)
    return text


def editorial_rewrite(text):
    """Deterministic suggestions; caller must retain original and label as automatic."""
    changed=[];result=normalize_technology_spelling(text)
    if result!=text:changed.append('technology_spelling_equivalent')
    def replace(match,value):return value[0].upper()+value[1:] if match.group()[0].isupper() else value
    for pattern,value,kind in _EDIT_RULES:
        updated=re.sub(pattern,lambda m:replace(m,value),result,flags=re.I)
        if updated!=result:changed.append(kind);result=updated
    # Collapse accidental extra whitespace without changing line content.
    updated=re.sub(r'[ \t]{2,}',' ',result)
    if updated!=result:changed.append('spacing');result=updated
    return result,list(dict.fromkeys(changed))


def _comparison_text(text):return editorial_rewrite(text)[0].casefold()


def check_rewrite(original,proposed,context=None):
    """Explain deterministic failures and uncertainty separately; not semantic proof.

    Context is immutable entry metadata. Unknown semantic changes remain warnings.
    No model verdict is used to clear a failed source/fact check.
    """
    from collections import Counter
    context=context or {};checks=[]
    def add(name,state,details=None):checks.append({'name':name,'status':state,'details':details or []})
    if not isinstance(original,str) or not isinstance(proposed,str) or not original.strip() or not proposed.strip():
        return {'version':GUARD_VERSION,'status':'rejected','checks':[{'name':'nonempty_text','status':'fail','details':['Missing original or proposed text']}],'reason_codes':['nonempty_text']}
    before=normalize_technology_spelling(original);after=normalize_technology_spelling(proposed)
    same=original==proposed
    add('nonempty_text','pass')
    from ai.agents.cv_content import missing_content_anchors
    missing_anchors=missing_content_anchors(original,proposed)
    add('content_anchors','fail' if missing_anchors else 'pass',missing_anchors)
    nums=lambda text:Counter(re.findall(r'(?<!\w)[+-]?(?:\d+(?:[.,]\d+)?|[.,]\d+)',text))
    # Ordered occurrence checks retain number-to-clause association as a warning below.
    add('numbers','pass' if nums(before)==nums(after) else 'fail')
    add('number_attribution','pass' if re.findall(r'(?<!\w)[+-]?(?:\d+(?:[.,]\d+)?|[.,]\d+)',before)==re.findall(r'(?<!\w)[+-]?(?:\d+(?:[.,]\d+)?|[.,]\d+)',after) else 'warning')
    byte_units=lambda t:Counter(re.findall(r'(?<!\w)[kKMGT]?[bB](?:ps)?(?!\w)',t))
    add('case_sensitive_units','pass' if byte_units(before)==byte_units(after) else 'fail')
    degrees=r"\b(?:bachelor|master|doctorate|phd|pmp|cpa|cfa|ielts|toefl|cử nhân|thạc sĩ|tiến sĩ)\b"
    qualifications=lambda t:Counter(re.findall(degrees,t.casefold()))
    add('degrees_certifications','pass' if qualifications(before)==qualifications(after) else 'fail')
    states=[(r'\b(?:sinh viên|đang học|đang theo học)\b','studying'),(r'\b(?:tốt nghiệp|graduated)\b','graduated'),(r'\b(?:thực tập sinh|thực tập|internship|intern)\b','intern'),(r'\b(?:bán thời gian|part-time)\b','part_time'),(r'\b(?:toàn thời gian|full-time)\b','full_time'),(r'\bjunior\b','junior'),(r'\bsenior\b','senior'),(r'\b(?:mong muốn|muốn|dự định|dự kiến|định hướng)\b','planned'),(r'\bđang(?=\s+(?:triển khai|phát triển|xây dựng|thực hiện|kiểm thử|nghiên cứu))','ongoing'),(r'\b(?:nhằm|để (?=(?:giảm|tăng|cải thiện|tối ưu|tiết kiệm|nâng cao|hạn chế)\b))','purpose')]
    state_counts=lambda text:Counter(tag for pattern,tag in states for _ in re.finditer(pattern,text,re.I))
    add('qualification_state','pass' if state_counts(before)==state_counts(after) else 'fail')
    counts=lambda pattern,text:Counter(m.group().casefold() for m in re.finditer(pattern,text,re.I))
    compare_before=_comparison_text(before);compare_after=_comparison_text(after)
    for name,pattern in [('units',_UNITS),('dates',_MONTHS),('negation',_NEGATIONS),('proficiency',_PROFICIENCY),('contribution',_CONTRIBUTION),('conditions',_CONDITIONS),('subject',_SUBJECTS)]:
        # Editorial substitutions retain monthly/weekly frequency and contribution scope.
        left=counts(pattern,compare_before);right=counts(pattern,compare_after)
        if name=='dates':
            left=Counter({}) if not left else Counter(m.group().casefold()[:3] for m in re.finditer(pattern,compare_before,re.I))
            right=Counter({}) if not right else Counter(m.group().casefold()[:3] for m in re.finditer(pattern,compare_after,re.I))
        if name=='units':
            aliases={'years':'year','months':'month','weeks':'week','days':'day','hours':'hour','seconds':'second','milliseconds':'ms','dollars':'dollar','percent':'%','percentage':'%'}
            aliases.update({'yearly':'annually'})
            left=Counter({}) if not left else Counter(aliases.get(m.group().casefold(),m.group().casefold()) for m in re.finditer(pattern,compare_before,re.I))
            right=Counter({}) if not right else Counter(aliases.get(m.group().casefold(),m.group().casefold()) for m in re.finditer(pattern,compare_after,re.I))
        equivalences={'conditions':{'about':'approximately'},'proficiency':{'basics':'basic','beginner':'basic','cơ bản':'basic'},'contribution':{'assisted':'helped','assisting':'helping','assist':'help','cộng tác':'phối hợp'},'subject':{'my':'i','me':'i','our':'we','us':'we','their':'they','her':'she','his':'he'}}.get(name,{})
        left=Counter({k:v for k,v in left.items()}) if not equivalences else Counter(equivalences.get(m.group().casefold(),m.group().casefold()) for m in re.finditer(pattern,compare_before,re.I))
        right=Counter({k:v for k,v in right.items()}) if not equivalences else Counter(equivalences.get(m.group().casefold(),m.group().casefold()) for m in re.finditer(pattern,compare_after,re.I))
        add(name,'pass' if left==right else 'fail')
    tech=lambda text:{term for term in TECHNOLOGIES if contains_term(text,term)}
    added=sorted(tech(after)-tech(before));lost=sorted(tech(before)-tech(after))
    add('technologies','fail' if added or lost else 'pass',{'added':added,'lost':lost})
    links=lambda text:Counter(re.findall(r'https?://\S+|[\w.+-]+@[\w.-]+',text))
    add('links','pass' if links(before)==links(after) else 'fail')
    metadata=[]
    for field in ('title','company','subtitle','period','degree','institution'):
        value=context.get(field)
        if isinstance(value,str) and value.strip() and value.casefold() in before.casefold() and value.casefold() not in after.casefold():metadata.append(field)
    add('entry_entities','fail' if metadata else 'pass',metadata)
    # Suppress capitalization of known editorial words; unfamiliar entity changes need review.
    editorial_words={word for pattern,value,kind in _EDIT_RULES for word in re.findall(r'[a-z]+',value)}|_STOP
    ent_before=entities(editorial_rewrite(before)[0])-{canonical(w) for w in editorial_words};ent_after=entities(editorial_rewrite(after)[0])-{canonical(w) for w in editorial_words}
    add('other_entities','warning' if ent_before!=ent_after else 'pass',{'added':sorted(ent_after-ent_before),'lost':sorted(ent_before-ent_after)})
    tokens=lambda text:[t for t in re.findall(r'\w+(?:[.+#-]\w+)*',text) if t not in _FUNCTION_WORDS]
    old=tokens(compare_before);new=tokens(compare_after)
    extra=Counter(new)-Counter(old);missing=Counter(old)-Counter(new)
    add('information_added','warning' if extra else 'pass',dict(extra))
    add('information_lost','warning' if missing else 'pass',dict(missing))
    # Bag equality cannot establish unchanged relationships or actor/quantity attribution.
    add('fact_order','pass' if old==new else 'warning')
    if re.search(_NEGATIONS,before,re.I) or re.search(_CONDITIONS,before,re.I):
        add('clause_scope','pass' if re.findall(r'[.;:!?]',before)==re.findall(r'[.;:!?]',after) else 'warning')
    if before!=original or after!=proposed:add('technology_spelling_equivalent','pass')
    state='rejected' if any(c['status']=='fail' for c in checks) else 'needs_review' if any(c['status']=='warning' for c in checks) else 'candidate_pass'
    return {'version':GUARD_VERSION,'status':state,'checks':checks,'reason_codes':[c['name'] for c in checks if c['status']!='pass'],'change_kind':'keep' if same else 'equivalent_spelling' if before==after else 'editorial' if old==new else 'substantive_unverified'}


def catalog_context(document):
    """Same source entry context in runtime prompts, reviewer checks and SFT export."""
    return {b.source_refs[0]:{'entry_id':entry.source_entry_id,'kind':section.kind,'title':entry.title,'subtitle':entry.subtitle,'period':entry.period}
            for section in document.sections for entry in section.entries for b in entry.bullets}


def grounded_rewrite(original,proposed):
    before=editorial_rewrite(original)[0];after=editorial_rewrite(proposed)[0]
    from ai.agents.cv_fidelity import assess_edit
    return (_legacy_grounded_rewrite(before,after)
            and check_rewrite(original,proposed)['status']!='rejected'
            and assess_edit(original,proposed)['status']=='verified_editorial')
