import json
import math
import re
import unicodedata
from collections import Counter
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field

from ai.llm.ollama_client import request_structured, llm_deadline

ROOT = Path(__file__).resolve().parent
INDEX = ROOT / 'index.json'
SOURCES = {
    '45.signed.pdf': ('Bộ luật Lao động 45/2019/QH14', 'https://vanban.chinhphu.vn/?docid=198540&lang=vi&pageid=27160', '2021-01-01'),
    '145.signed.pdf': ('Nghị định 145/2020/NĐ-CP', 'https://vanban.chinhphu.vn/?classid=1&docid=201967&pageid=27160', '2021-02-01'),
    '74qh15.signed.pdf': ('Luật Việc làm 74/2025/QH15', 'https://vanban.chinhphu.vn/?classid=1&docid=214560&orggroupid=1&pageid=27160', '2026-01-01'),
    '41-2024-qh15.pdf': ('Luật Bảo hiểm xã hội 41/2024/QH15', 'https://vanban.chinhphu.vn/?docid=211199&pageid=27160', '2025-07-01'),
    '293-cp.signed.pdf': ('Nghị định 293/2025/NĐ-CP', 'https://vanban.chinhphu.vn/?docid=215832&pageid=27160', '2026-01-01'),
}
ARTICLE = re.compile(r'(?im)^\s*Điều\s+(\d+[a-z]?)\s*[.:]\s*([^\n]{0,110})')
STOP = {'va','la','cua','co','cho','toi','minh','em','anh','chi','theo','duoc','nhu','thi','khi','neu','ve','mot','nhung','trong','voi','bao','nhieu','nao','gi','sao','phai','can','hay','luat','quy','dinh','nguoi','lao','dong'}


def tokens(text):
    text = ''.join(c for c in unicodedata.normalize('NFD', text.casefold()) if not unicodedata.combining(c)).replace('đ', 'd')
    return [x for x in re.findall(r'[a-z0-9]+', text) if len(x) > 1 and x not in STOP]


def dense(text):
    return ''.join(c for c in unicodedata.normalize('NFD', text.casefold()) if not unicodedata.combining(c)).replace('đ','d').replace(' ', '').replace('\n','')


def preferred_files(query):
    q = dense(query)
    if any(x in q for x in ('nghiphep','nghihangnam','thuviec','lamthemgio','tangca','sathai','chamduthopdong')):
        return {'45.signed.pdf','145.signed.pdf'}
    if 'luongtoithieu' in q:
        return {'293-cp.signed.pdf','45.signed.pdf'}
    if 'baohiemxahoi' in q:
        return {'41-2024-qh15.pdf'}
    if 'baohiemthatnghiep' in q or 'luatvieclam' in q:
        return {'74qh15.signed.pdf'}
    return None


def build_index():
    import pymupdf
    rows = []
    for filename, (title, url, effective) in SOURCES.items():
        path = ROOT / filename
        if not path.is_file():
            raise FileNotFoundError(path)
        doc = pymupdf.open(path)
        current = None
        count = 0
        for page_no, page in enumerate(doc, 1):
            text = page.get_text(sort=True)
            if len(text.strip()) < 100:
                text = page.get_text(textpage=page.get_textpage_ocr(language='vie', dpi=150, full=True), sort=True)
            text = re.sub(r'[ \t]+', ' ', text).strip()
            if len(text) < 100:
                continue
            matches = list(ARTICLE.finditer(text))
            sections = []
            if matches:
                if matches[0].start() > 100:
                    sections.append((current, text[:matches[0].start()]))
                for i, match in enumerate(matches):
                    current = 'Điều ' + match.group(1)
                    sections.append((current, text[match.start():matches[i+1].start() if i+1 < len(matches) else len(text)]))
            else:
                sections.append((current, text))
            for article, section in sections:
                section = section.strip()
                if len(section) < 80:
                    continue
                for start in range(0, len(section), 1200):
                    chunk = section[start:start+1350]
                    if len(chunk) < 80:
                        continue
                    count += 1
                    rows.append(dict(id=f'{filename}:{page_no}:{count}', title=title, url=url, effective=effective,
                                     file=filename, page=page_no, article=article, text=chunk))
    INDEX.write_text(json.dumps(rows, ensure_ascii=False), encoding='utf-8')
    load_index.cache_clear()
    return len(rows)


@lru_cache(maxsize=1)
def load_index():
    if not INDEX.is_file():
        return []
    return json.loads(INDEX.read_text(encoding='utf-8'))


def retrieve(query, limit=5):
    from backend.app.services.knowledge import retrieval_rows
    rows = retrieval_rows(load_index())
    q = set(tokens(query))
    preferred = preferred_files(query)
    if 'nghiphep' in dense(query): q.update(('nghi','hang','nam'))
    if not q or not rows:
        return []
    df = Counter(t for row in rows for t in set(tokens(row['text'] + ' ' + row['title'])))
    ranked = []
    for row in rows:
        if preferred and row['file'] in SOURCES and row['file'] not in preferred:
            continue
        terms = Counter(tokens(row['text']))
        compact = dense(row['text'])
        matched = {t for t in q if t in terms or t in compact}
        if len(matched) < min(2, len(q)):
            continue
        score = sum((1 + math.log1p(terms[t])) * math.log1p(len(rows)/(1+df[t])) for t in matched)
        score += sum(2 for t in q & set(tokens(row['title'])))
        heading = row['text'][:160]
        score += sum(5 for t in q if t in dense(heading))
        if 'nghiphep' in dense(query) and 'nghihangnam' in dense(heading): score += 18
        if 'nghiphep' in dense(query) and row['file']=='45.signed.pdf' and row['article']=='Điều 113': score += 35
        if 'thuviec' in dense(query) and 'thuviec' in dense(heading): score += 18
        if 'luongtoithieu' in dense(query) and row['file']=='293-cp.signed.pdf': score += 10
        ranked.append((score, row))
    ranked.sort(key=lambda item: item[0], reverse=True)
    chosen = []
    for _, row in ranked:
        if any(r['file'] == row['file'] and r['page'] is not None and row['page'] is not None and abs(r['page'] - row['page']) <= 1 for r in chosen):
            continue
        chosen.append(row)
        if len(chosen) == limit:
            break
    return chosen


class LawAnswer(BaseModel):
    answer: str = Field(max_length=1800)
    source_ids: list[str] = Field(max_length=5)
    insufficient: bool = False


def answer(query):
    if not query.strip() or query.strip().casefold() in {'hỏi luật lao động', 'hỏi về luật lao động việt nam'}:
        return dict(type='labor_law', text='Bạn muốn hỏi về hợp đồng, thời giờ làm việc, nghỉ phép, lương hay bảo hiểm xã hội? Hãy nêu tình huống cụ thể để mình tìm đúng điều luật.', sources=[])
    hits = retrieve(query)
    if not hits:
        return dict(type='labor_law', text='Mình chưa tìm thấy căn cứ đủ rõ trong các tài liệu đang được sử dụng. Bạn có thể nêu rõ hơn tình huống hoặc điều luật muốn tra cứu.', sources=[])
    vacation = next((r for r in hits if r['file']=='45.signed.pdf' and r['article']=='Điều 113'), None)
    if vacation and any(x in dense(query) for x in ('nghiphep','nghihangnam')) and all(x in dense(vacation['text']) for x in ('12ngay','14ngay','16')):
        return dict(type='labor_law', text='Theo Điều 113, nếu làm đủ 12 tháng cho một người sử dụng lao động: nghỉ 12 ngày làm việc trong điều kiện bình thường; 14 ngày nếu là lao động chưa thành niên, người khuyết tật hoặc làm công việc nặng nhọc, độc hại, nguy hiểm; 16 ngày nếu làm công việc đặc biệt nặng nhọc, độc hại, nguy hiểm. Nếu làm chưa đủ 12 tháng, số ngày nghỉ được tính theo tỷ lệ thời gian làm việc.', sources=[dict(title=vacation['title'], article=vacation['article'], page=vacation['page'], url=vacation['url'], effective=vacation['effective'])])
    excerpts = [dict(id=r['id'], title=r['title'], article=r['article'], page=r['page'], text=r['text'][:1200]) for r in hits]
    prompt = 'Chỉ dùng các trích đoạn JSON sau để trả lời câu hỏi pháp luật lao động. Không suy diễn quy định không có trong nguồn. Nếu mức hưởng hoặc thời hạn thay đổi theo loại công việc/đối tượng, phải nêu đủ các trường hợp trong nguồn; không trả lời một con số chung. Nếu OCR mờ hoặc chưa đủ căn cứ, insufficient=true. source_ids chỉ chứa id được cung cấp, tối đa 3 nguồn. Trả lời tiếng Việt ngắn gọn, không tự bịa số điều hay mức tiền.\nNguồn: '+json.dumps(excerpts, ensure_ascii=False)+'\nCâu hỏi: '+query
    with llm_deadline(90):
        result = request_structured([{'role':'system','content':'Bạn là công cụ tra cứu văn bản pháp luật. Chỉ trả JSON đúng schema và chỉ sử dụng nguồn được cung cấp.'},{'role':'user','content':prompt}], LawAnswer, task='assistant')
    by_id = {r['id']: r for r in hits}
    cited = [by_id[x] for x in result.source_ids if x in by_id][:3]
    if result.insufficient or not cited:
        return dict(type='labor_law', text='Các trích đoạn tìm được chưa đủ để kết luận. Bạn hãy nêu rõ hơn tình huống; mình sẽ tra lại văn bản.', sources=[])
    cited_text = dense(' '.join(r['text'] for r in cited))
    numbers = re.findall(r'\b\d+(?:[.,]\d+)*\b', result.answer)
    if any(dense(number) not in cited_text for number in numbers):
        return dict(type='labor_law', text='Mình chưa thể kiểm chứng đầy đủ các số liệu trong bản trích. Hãy mở văn bản gốc ở nguồn chính thức để đối chiếu.', sources=[dict(title=r['title'], article=r['article'], page=r['page'], url=r['url'], effective=r['effective']) for r in cited])
    sources = [dict(title=r['title'], article=r['article'], page=r['page'], url=r['url'], effective=r['effective']) for r in cited]
    return dict(type='labor_law', text=result.answer.strip(), sources=sources)


if __name__ == '__main__':
    print(build_index())
