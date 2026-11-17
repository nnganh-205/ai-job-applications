"""Ordered source clauses and explicit method bindings, without inferred facts."""
import re
from ai.agents.cv_fidelity import canonical_tokens

_BOUNDARY = re.compile(r'[;\n]+|\b(?:và|rồi|sau đó|and|then)\b|,\s*(?=(?:viết|lưu|ghi|gửi|nhận|gọi|kiểm|hỗ trợ|phối hợp|cập nhật|đối chiếu|phân loại|tạo|thiết kế|xử lý|chuyển|theo dõi|báo cáo|write|store|record|send|test|update)\b)',re.I)

def clauses(text):
    parts=[];boundaries=[];start=0
    for match in _BOUNDARY.finditer(text):
        if text[:match.start()].count('(')>text[:match.start()].count(')'):continue
        part=text[start:match.start()].strip(' .')
        if part:
            parts.append(part)
            boundaries.append('sequence' if match.group().casefold() in {'rồi','sau đó','then'} else 'list')
        start=match.end()
    tail=text[start:].strip(' .')
    if tail:parts.append(tail)
    return parts,boundaries[:max(0,len(parts)-1)]

def methods(text):
    result=[]
    front=re.search(r'\b(?:dùng|sử dụng|using)\s+(.+?)\s+(?:để|to)\s+',text,re.I)
    if front:result.append(front.group(1).strip())
    tail=re.search(r'\b(?:bằng|with)\s+(.+?)\s*[.!]?$',text,re.I)
    if tail:result.append(tail.group(1).strip(' .!'))
    return result

def _contains(source,phrase):
    # Exact ordered terms including conservative spelling aliases.
    wanted=canonical_tokens(phrase);tokens=canonical_tokens(source)
    return bool(wanted) and any(tokens[i:i+len(wanted)]==wanted for i in range(len(tokens)-len(wanted)+1))

def method_issues(source,rewrite):
    issues=[]
    for tool in methods(source):
        if not _contains(rewrite,tool):issues.append('lost_method:'+tool)
    for tool in methods(rewrite):
        if not _contains(source,tool):issues.append('new_method:'+tool)
    return issues

def source_clauses(text):
    parts,_=clauses(text)
    return [dict(index=i,text=p,methods=methods(p)) for i,p in enumerate(parts)]

def recover_clauses(source,rewrite,validator,editorial):
    """Keep verified edits and restore only unsafe clauses from immutable source."""
    before,bounds=clauses(source);after,new_bounds=clauses(rewrite)
    if len(before)<2 or len(before)!=len(after):return None
    selected=[];kept=0;restored=int(bounds!=new_bounds)
    for index,(old,new) in enumerate(zip(before,after)):
        proof=validator(old,new) if not method_issues(old,new) else {'accepted':False}
        if proof['accepted']:
            selected.append(new);kept+=1
        else:
            fallback=editorial(old)
            if index and old[0].islower() and fallback:fallback=fallback[0].lower()+fallback[1:]
            selected.append(fallback);restored+=1
    if not kept or not restored:return None
    # Retain the exact original connective/sequence/scope layout.
    pieces=[];cursor=0
    for old,new in zip(before,selected):
        at=source.find(old,cursor)
        if at<0:return None
        pieces.extend([source[cursor:at],new]);cursor=at+len(old)
    pieces.append(source[cursor:])
    result=editorial(''.join(pieces))
    return result if validator(source,result)['accepted'] else None
