"""One synthetic, schema-validated request for one Cloudflare task. No retries."""
import argparse
import json
import sys
import time

from ai.llm.ollama_client import request_structured,OllamaError
from backend.app.core.config import settings

TASKS=('jd','interview','cv','verifier')


def sample(task):
    if task=='jd':
        from ai.agents.jd_extraction import CompactJD,PROMPT
        return [dict(role='system',content=PROMPT),dict(role='user',content='Line 1: Required skill: Python. Return only Python, cited as line 1.')],CompactJD
    if task=='interview':
        from backend.app.services.interviews import response_schema
        return [dict(role='system',content='Trả JSON question: kind technical, một câu hỏi tiếng Việt về dự án, evidence_refs chỉ gồm cv:0.'),
                dict(role='user',content='cv:0: Built a Python API. Hỏi một câu về cách kiểm thử API.')],response_schema({'cv:0':'Built a Python API.'},'technical')
    if task=='cv':
        from backend.app.schemas.cv import CVPlan
        return [dict(role='system',content='Review this synthetic CV source. Preserve the exact source reference. Return JSON selected_refs and review with items and warnings. No edits are needed.'),
                dict(role='user',content='Source /project/0/description/0: Built a Python API. Select this reference, return empty review.items and review.warnings.')],CVPlan
    if task=='verifier':
        from ai.agents.cv_semantics import CompactReview,_COMPACT_PROMPT
        return [dict(role='system',content=_COMPACT_PROMPT),dict(role='user',content=json.dumps(dict(s0='Built a Python API.',t0='Developed a Python API.')))],CompactReview
    raise ValueError('Tác vụ kiểm tra không hợp lệ')


def check(task):
    if settings.provider_for_task(task)!='cloudflare':
        raise ValueError('Điền thông tin Cloudflare và bật tác vụ trong CLOUDFLARE_TASKS trước khi kiểm tra')
    messages,schema=sample(task)
    start=time.monotonic()
    result=request_structured(messages,schema,task=task,max_output_tokens=1024)
    if task=='jd' and (not result.items or any(i.name!='Python' or i.line!=1 for i in result.items)):
        raise ValueError('JD chưa trích đúng kỹ năng hoặc dòng nguồn của mẫu kiểm tra')
    if task=='interview' and (result.question.kind!='technical' or result.question.evidence_refs!=['cv:0']):
        raise ValueError('Câu hỏi chưa bám đúng nguồn kiểm tra')
    if task=='cv' and (result.selected_refs!=['/project/0/description/0'] or result.review.items):
        raise ValueError('Rà soát CV chưa giữ đúng mẫu nguồn kiểm tra')
    if task=='verifier' and not all(v for k,v in result.model_dump().items() if isinstance(v,bool)):
        raise ValueError('Kiểm tra nghĩa chưa xác nhận đúng hai câu tương đương')
    return dict(task=task,provider='cloudflare',model=settings.model_for_task(task),validated=True,
                requests=1,seconds=round(time.monotonic()-start,2))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--task',required=True,choices=TASKS)
    args=parser.parse_args()
    try:
        output=check(args.task);status=0
    except (OllamaError,ValueError) as error:
        output=dict(task=args.task,validated=False,error=str(error));status=1
    sys.stdout.write(json.dumps(output,ensure_ascii=False)+'\n')
    return status


if __name__=='__main__':
    raise SystemExit(main())
