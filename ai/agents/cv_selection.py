"""Select quoted CV evidence against job requirements before editorial review.

This produces suggestions for user review. A literal citation proves its origin,
not an employment qualification. Matching scores remain in the existing engine.
"""
import re
from pydantic import Field
from backend.app.schemas.profile import StrictModel
from ai.llm.ollama_client import OllamaSchemaError

VERSION='cv-selection-v3'


class SelectionLink(StrictModel):
    requirement_id: str
    source_ref: str
    quote: str=Field(min_length=6,max_length=700)


class SelectionPlan(StrictModel):
    links: list[SelectionLink]=Field(default_factory=list,max_length=64)


def requirement_catalog(requirements):
    result=[];seen=set()
    groups=requirements.get('requirement_groups') or requirements.get('groups') or []
    grouped={name.casefold().strip() for group in groups for name in group.get('members',[])}
    for group in groups:
        members=group.get('members',[])
        if members:
            text=('Một trong: ' if group.get('operator')=='any' else 'Đồng thời: ')+' / '.join(members)
            result.append(dict(id=f'r{len(result)}',text=text,priority=group.get('requirement_type','required')))
            seen.add(text.casefold())
    for field in ('required_skills','experience_requirements','education_requirements','certifications','languages',
                  'technical_requirements','responsibilities','preferred_skills','unspecified_skills'):
        for item in requirements.get(field,[]):
            text=(item.get('name') or item.get('description') or '').strip()
            if not text or text.casefold() in seen or text.casefold() in grouped:continue
            seen.add(text.casefold())
            result.append(dict(id=f'r{len(result)}',text=text,priority=item.get('requirement_type','unspecified')))
    return result


def _evidence_score(source, quote, requirement):
    """Conservative lexical relevance on positive source clauses, never a fit score.

    A verbatim citation proves origin only. Denied clauses cannot supply keywords;
    rank all candidates before applying the global per-requirement budget.
    """
    from ai.agents.matching_agent import canonical, contains_term
    ignored={'kinh','nghiệm','kinh nghiệm','yêu','cầu','với','trong','của','và','hoặc','một','đồng','thời',
             'tổ','chức','có','khả','năng','sử','dụng','bắt','buộc','ưu','tiên','experience','with','required','skills','in','and','or'}
    # Keep phrases such as "chưa đo ..." out of matching evidence while still
    # permitting positive work in a different clause of the same source bullet.
    positive=[]
    for clause in re.split(r'[.;\n]|\bbut\b|\bnhưng\b',source,flags=re.I):
        negative=re.search(r"\b(?:chưa|không|chẳng|never|not|without|no experience)\b",clause,re.I)
        if negative:clause=clause[:negative.start()]
        if clause.strip():positive.append(clause)
    positive=' '.join(positive)
    quote_positive=[]
    for clause in re.split(r'[.;\n]|\bbut\b|\bnhưng\b',quote,flags=re.I):
        negative=re.search(r'\b(?:chưa|không|chẳng|never|not|without|no experience)\b',clause,re.I)
        if negative:clause=clause[:negative.start()]
        quote_positive.append(clause)
    quote=' '.join(quote_positive)
    words={canonical(t) for t in re.findall(r'[\w+#.]+',requirement.casefold()) if len(t)>1 and t not in ignored}
    ordered=[t for t in re.findall(r'[\w+#]+',requirement.casefold())]
    phrases={' '.join(ordered[i:i+2]) for i in range(len(ordered)-1) if ordered[i] not in ignored and ordered[i+1] not in ignored}
    # Vietnamese syllables alone (e.g. 'liệu' in 'dữ liệu' vs 'tài liệu')
    # do not establish topical relevance. Require a shared phrase instead.
    named={canonical(w) for w in re.findall(r'(?<!\w)[A-Z][A-Za-z0-9+#.]+',requirement)}
    terms=phrases | {w for w in words if w.isascii() and (requirement.isascii() or w in named)}
    hits={word for word in terms if contains_term(positive,word) and contains_term(quote,word)}
    # Bibliographic metadata is related to a document catalogue even when
    # the bullet does not repeat the JD's label. This selects relevant source,
    # it does not certify that the whole requirement is met.
    related={'tài liệu':('năm xuất bản','nhan đề','bibliography'),
             'document':('publication year','bibliography')}
    for term,signals in related.items():
        if contains_term(requirement,term) and any(contains_term(positive,x) and contains_term(quote,x) for x in signals):
            hits.add(term)
    return len(hits) / max(1,len(terms)) if hits else 0


def validate_selection(plan,catalog,requirements):
    allowed={r['id']:r for r in requirements};selected=[];invalid=0;ranked={}
    for link in plan.links:
        if link.requirement_id not in allowed or link.source_ref not in catalog:
            invalid+=1;continue
        source=catalog[link.source_ref].text
        if link.quote not in source:
            invalid+=1;continue
        score=_evidence_score(source,link.quote,allowed[link.requirement_id]['text'])
        if score<=0:
            invalid+=1;continue
        pair=(link.requirement_id,link.source_ref)
        ranked[pair]=max(ranked.get(pair,0),score)
    # Stable ties use source identity, never the order of chunks/model links.
    counts={}
    for (requirement_id,ref),score in sorted(ranked.items(),key=lambda item:(-item[1],item[0])):
        if counts.get(requirement_id,0)>=2:continue
        counts[requirement_id]=counts.get(requirement_id,0)+1
        if ref not in selected:selected.append(ref)
    return selected,invalid


def select_for_job(catalog,requirements,request=None):
    criteria=requirement_catalog(requirements)
    if not criteria:return [],['JD chưa có yêu cầu cụ thể để chọn nội dung; bản CV nguồn được giữ nguyên.']
    if len(criteria)>32:raise OllamaSchemaError('JD có quá nhiều yêu cầu trong một lượt; hãy chọn nhóm yêu cầu cần ưu tiên.')
    # Source retrieval is deterministic. The language model edits the selected
    # facts later; it cannot silently drop all relevant source evidence here.
    # Score the full source as its own exact quotation, then rank globally.
    links=[]
    for r in criteria:
        for ref,bullet in catalog.items():
            # Search the whole source; do not silently cut away late evidence.
            quotes=[bullet.text[i:i+700] for i in range(0,len(bullet.text),350)]
            eligible=[q for q in quotes if len(q)>=6 and _evidence_score(bullet.text,q,r['text'])>0]
            if eligible:
                quote=max(eligible,key=lambda q:_evidence_score(bullet.text,q,r['text']))
                links.append(SelectionLink(requirement_id=r['id'],source_ref=ref,quote=quote))
    combined=SelectionPlan.model_construct(links=links)
    selected,invalid=validate_selection(combined,catalog,criteria)
    warnings=[]
    if invalid:warnings.append('Một số đề xuất chọn nội dung không khớp dẫn chứng đã được loại.')
    if not selected:warnings.append('Chưa tìm được nội dung CV có dẫn chứng phù hợp với JD; giữ nguyên CV nguồn để bạn xem lại.')
    return selected,warnings
