"""Source-bound scope clauses shared by writing, polishing and evaluation.

Literal checks deliberately prefer review/fallback to silently losing a limit.
They are not a general semantic entailment judge.
"""
import re
from ai.agents.cv_grounding import normalize_technology_spelling


def scope_clauses(text):
    clauses=[]
    for clause in re.split(r'[;\n]|\.(?=\s|$)',text):
        match=re.search(r"\b(?:không|chưa|chẳng|chỉ(?!\s+(?:số|tiêu|ra|dẫn|định|thị|mục)\b)|dưới sự giám sát|not|never|without|only|under supervision|haven't|hasn't|didn't|cannot|can't)\b.*",clause,re.I)
        if match:clauses.append(match.group().strip())
    return clauses


def missing_scope_clauses(original,proposed):
    def normalize(text):
        return re.sub(r'[^\w]+',' ',normalize_technology_spelling(text).casefold()).strip()
    text=' '+normalize(proposed)+' '
    return [clause for clause in scope_clauses(original) if ' '+normalize(clause)+' ' not in text]
