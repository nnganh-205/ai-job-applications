"""Source-aligned edit contracts for automatic wording suggestions.

Only explicitly enumerated editorial equivalences can be auto-accepted. An
unknown paraphrase is unverified, not evidence of either truth or fabrication.
Ordered semantic tokens preserve action/object and quantity associations.
"""
import re
import unicodedata
from collections import Counter

VERSION = 'source-edit-contract-v2'
# Full phrases, longest first. These change wording, never add an achievement.
_EQUIVALENTS = (
    (r'\b(?:built|developed)\b', 'built'),
    (r'\b(?:sắp xếp|xếp)\b', 'xếp'),
    (r'\b(?:ghi nhận|ghi lại|ghi)\b', 'ghi'),
    (r'\b(?:để thuận tiện tìm kiếm|để tiện tìm lại)\b', 'để tiện tìm lại'),
    (r'\b(?:các tệp|những tệp)\b', 'tệp'),
    (r'\b(?:bằng cách sử dụng|sử dụng|dùng)\b', 'dùng'),
    (r'\b(?:phối hợp|cộng tác)\b', 'phối hợp'),
    (r'\b(?:đã hoàn thành|hoàn thành)\b', 'hoàn thành'),
    (r'\b(?:mã nguồn|source code)\b', 'mã_nguồn'),
    (r'\b(?:mã|identifier|id)\b', 'mã'),
    (r'\b(?:hình ảnh|ảnh)\b', 'ảnh'),
    (r'\b(?:node\.?\s*js)\b', 'nodejs'),
    (r'\b(?:postgres|postgresql)\b', 'postgresql'),
    (r'\b(?:hỗ trợ|assist(?:ed|ing)?|support(?:ed|ing)?)\b', 'hỗ_trợ'),
)

def _instrument_order(text):
    """Normalize an unambiguous method/action frame without a synonym list.

    'dùng TOOL để TASK' and 'TASK bằng TOOL' carry the same task and method.
    Task/tool contents stay ordered and intact; scope clauses stay attached.
    This never treats a goal as an achieved outcome.
    """
    lines=[]
    for line in text.splitlines():
        main,separator,scope=line.partition(';')
        front=re.fullmatch(r'\s*dùng\s+([^;]+?)\s+để\s+(.+?)\s*[.!]?\s*',main)
        back=re.fullmatch(r'\s*(.+?)\s+bằng\s+([^;]+?)\s*[.!]?\s*',main)
        if front:
            tool,task=front.groups()
        elif back:
            task,tool=back.groups()
        else:
            lines.append(line);continue
        # A method must not migrate across coordinated actions. Complex clauses
        # require separate review rather than this simple frame normalization.
        if re.match(r'(?:giảm|tăng|cải thiện|tối ưu|tiết kiệm|nâng cao|hạn chế)\b',task):
            lines.append(line);continue
        if re.search(r'\b(?:và|rồi|sau đó|and|then)\b',task):
            lines.append(line);continue
        lines.append(task.rstrip(' .!')+' cv_method '+tool.rstrip(' .!')+(separator+scope if separator else ''))
    return '\n'.join(lines)


def canonical_tokens(text):
    text = unicodedata.normalize('NFC', text).casefold()
    # Strip chat framing separately for each source line, never inside content.
    text = re.sub(r'(?m)^\s*(?:[•*]\s*|-\s+|\d+[.)]\s+)', '', text)
    text = re.sub(r'(?m)^\s*(?:mình|tôi|em)\s+(?:đã\s+)?', '', text)
    text = re.sub(r'(?m)^\s*có\s+(?=(?:hỗ trợ|tham gia|phối hợp)\b)', '', text)
    # Context-bound verb equivalence: "làm website" may be "phát triển website";
    # "làm" alone is not evidence of coding, leadership or measurable results.
    text = re.sub(r'\b(?:làm|thực hiện|phát triển|xây dựng)\s+(?=(?:giao diện|website|trang web|ứng dụng|chức năng|tính năng|api)\b)', 'xây dựng ', text)
    text = re.sub(r'\blàm\s+', 'thực hiện ', text)
    text = re.sub(r'\b(?:kiểm tra|đối chiếu)\s+(?=(?:mã|id|phiếu)\b)', 'đối chiếu ', text)
    for pattern, replacement in _EQUIVALENTS:
        text = re.sub(pattern, replacement, text)
    text = _instrument_order(text)
    return re.findall(r'[+-]?\d+(?:[.,]\d+)*|[^\W\d_]+(?:_[^\W\d_]+)*', text, re.UNICODE)

def assess_edit(original, proposed):
    before, after = canonical_tokens(original), canonical_tokens(proposed)
    if before == after and before:
        return dict(version=VERSION, status='verified_editorial', reasons=[])
    from ai.agents.cv_clauses import clauses
    left,bounds=clauses(original);right,new_bounds=clauses(proposed)
    if len(left)>1 and len(left)==len(right) and bounds==new_bounds and all(canonical_tokens(a)==canonical_tokens(b) for a,b in zip(left,right)):
        return dict(version=VERSION,status='verified_editorial',reasons=[],structure='clauses')
    reasons = []
    if Counter(before) == Counter(after):
        reasons.append('changed_action_object_or_quantity_order')
    else:
        if Counter(before) - Counter(after): reasons.append('unverified_omission_or_paraphrase')
        if Counter(after) - Counter(before): reasons.append('unverified_addition_or_paraphrase')
    return dict(version=VERSION, status='unverified', reasons=reasons or ['empty_content'])


def professional_wording(text):
    """Render a small set of source-proven operations with formal CV verbs."""
    replacements = (
        (r'^(?:Thực hiện|Làm) (?=(?:giao diện|website|trang web|ứng dụng|chức năng|tính năng|API)\b)', 'Phát triển '),
        (r'^Dùng\b', 'Sử dụng'),
        (r'^Ghi (?:lại )?(?!nhận\b)', 'Ghi nhận '),
        (r'^Xếp\b', 'Sắp xếp'),
    )
    from ai.agents.cv_clauses import clauses
    parts,_=clauses(text)
    selected=[]
    for index,part in enumerate(parts):
        candidate=part
        for pattern,replacement in replacements:
            candidate=re.sub(pattern,replacement,candidate,flags=re.I)
        frame=re.fullmatch(r'(?:dùng|sử dụng)\s+(.+?)\s+để\s+(.+)',candidate,re.I)
        if frame:
            tool,task=frame.groups()
            if not re.match(r'(?:giảm|tăng|cải thiện|tối ưu|tiết kiệm|nâng cao|hạn chế)\b',task,re.I):
                candidate=task[0].upper()+task[1:]+' bằng '+tool
        if index and part[0].islower():candidate=candidate[0].lower()+candidate[1:]
        selected.append(candidate if assess_edit(part,candidate)['status']=='verified_editorial' else part)
    result=[];cursor=0
    for old,new in zip(parts,selected):
        at=text.find(old,cursor)
        result.extend([text[cursor:at],new]);cursor=at+len(old)
    result.append(text[cursor:]);candidate=''.join(result)
    candidate=re.sub(r'\brồi\b','sau đó',candidate,flags=re.I)
    return candidate if assess_edit(text,candidate)['status']=='verified_editorial' else text
