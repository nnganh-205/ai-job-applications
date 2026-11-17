"""Durable text practice sessions pinned to a published CV and a JD snapshot."""
import hashlib
import json
import os
import re
from typing import Literal
from pydantic import create_model,Field
from datetime import datetime,timezone
from backend.app.db import database
from backend.app.db.profile_revision_repository import RevisionConflict
from backend.app.db.job_posting_repository import get_posting
from backend.app.schemas.cv import CVDocument
from backend.app.schemas.interview import InterviewStart,InterviewAnswer,PracticeTurn,PracticeQuestion,QuestionPlan,InitialTurn,FinalTurn
from backend.app.services import tasks
from ai.prompts.interview_prompt import PROMPT_VERSION,SYSTEM
from ai.llm.ollama_client import request_structured,llm_deadline,OllamaSchemaError
from backend.app.core.config import settings

OWNER_ID=os.getenv('WORKSPACE_OWNER_ID','local-demo')
KIND='interviews'


def now():return datetime.now(timezone.utc).isoformat()
def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def read(session_id,*,connection=None):
    if connection is None:
        tasks.require_database()
        with database.connect() as c:return read(session_id,connection=c)
    row=connection.execute('SELECT payload FROM kltn_app.records WHERE kind=%s AND record_id=%s',(KIND,session_id)).fetchone()
    if row is None or row['payload']['owner_id']!=OWNER_ID:raise LookupError('Không tìm thấy phiên phỏng vấn')
    return row['payload']


def public(session):
    return {key:value for key,value in session.items() if key not in {'owner_id','source','start_digest','events','processed_tasks'}}


def recent():
    tasks.require_database()
    with database.connect() as c:
        rows=c.execute("SELECT payload FROM kltn_app.records WHERE kind=%s AND payload->>'owner_id'=%s ORDER BY updated_at DESC LIMIT 50",(KIND,OWNER_ID)).fetchall()
    return [dict(session_id=s['session_id'],status=s['status'],version=s['version'],cv_id=s['cv_id'],posting_id=s['posting_id'],job_title=s['job_title'],language=s['language'],answered=sum(t.get('answer') is not None for t in s['turns']),question_count=s['question_count'],updated_at=s['updated_at']) for s in (row['payload'] for row in rows)]


def cv_text(document):
    # Contact details are not needed by an interviewer. Only published visible
    # content is available; never load hidden Master Profile facts or answers.
    lines=[]
    if document.summary:lines.append(document.summary.text)
    for section in document.sections:
        lines.append(section.heading)
        for entry in section.entries:
            lines.extend(filter(None,[entry.title,entry.subtitle,entry.period]))
            lines.extend(bullet.text for bullet in entry.bullets)
    return '\n'.join(lines)


def enqueue(session,operation,answer,c):
    task=tasks.submit('interview',{'session_id':session['session_id'],'request_version':session['version']},
        'interview-'+session['session_id']+'-'+str(session['version']),connection=c)
    session.update(status='processing',pending={'task_id':task['task_id'],'operation':operation,'answer':answer},updated_at=now())
    database.put_record(KIND,session['session_id'],session,connection=c)
    return public(session)


def start(request:InterviewStart):
    tasks.require_database()
    identity='interview_'+digest([OWNER_ID,request.event_id])[:32]
    request_hash=digest(request.model_dump())
    with database.connect() as c,c.transaction():
        c.execute('SELECT pg_advisory_xact_lock(hashtext(%s))',(identity,))
        previous=c.execute('SELECT payload FROM kltn_app.records WHERE kind=%s AND record_id=%s',(KIND,identity)).fetchone()
        if previous:
            if previous['payload']['start_digest']!=request_hash:raise RevisionConflict('Mã tạo phiên đã dùng với lựa chọn khác')
            return public(previous['payload'])
        version=database.get_record('cv_versions',request.cv_id)
        if version is None:raise LookupError('Chọn CV version đã xuất bản')
        job=get_posting(request.posting_id)
        if job is None:raise LookupError('Không tìm thấy JD')
        document=CVDocument.model_validate(version['document'])
        text=cv_text(document)
        if not text.strip():raise ValueError('CV chưa có nội dung để luyện tập')
        warnings=[]
        if len(text)>14000 or len(job.description)>14000:warnings.append('CV/JD dài: câu hỏi chỉ dùng 14.000 ký tự đầu mỗi tài liệu.')
        session=dict(schema_version=1,session_id=identity,owner_id=OWNER_ID,cv_id=request.cv_id,
            profile_revision_id=document.source_profile_revision_id,posting_id=request.posting_id,
            job_content_hash=job.content_hash,job_title=job.title,language=request.language,
            question_count=request.question_count,version=1,status='processing',turns=[],pending=None,
            source={'cv':text[:14000],'jd':job.description[:14000]},start_digest=request_hash,events={},processed_tasks=[],
            prompt_version=PROMPT_VERSION,model=settings.interview_model,warnings=warnings,report=None,created_at=now(),updated_at=now())
        return enqueue(session,'question',None,c)


def answer(session_id,request:InterviewAnswer):
    tasks.require_database()
    if not request.answer.strip():raise ValueError('Câu trả lời không được để trống')
    payload_digest=digest(request.model_dump())
    with database.connect() as c,c.transaction():
        c.execute('SELECT pg_advisory_xact_lock(hashtext(%s))',(session_id,))
        session=read(session_id,connection=c)
        event=session['events'].get(request.event_id)
        if event:
            if event!=payload_digest:raise RevisionConflict('Mã trả lời đã dùng với nội dung khác')
            return public(session)
        if session['version']!=request.expected_version:raise RevisionConflict('Phiên đã thay đổi. Tải lại trước khi gửi câu trả lời.')
        if session['status']!='awaiting_answer':raise RevisionConflict('Phiên chưa chờ câu trả lời')
        session['version']+=1
        session['events'][request.event_id]=payload_digest
        return enqueue(session,'answer',request.answer,c)


def validate_turn(result,session,pending):
    answer=pending['answer']
    last=answer is not None and len(session['turns'])>=session['question_count']
    if (result.question is None)!=last:raise OllamaSchemaError('Câu hỏi chưa đúng lượt; bạn có thể thử lại.')
    if result.question:
        for evidence in result.question.evidence:
            if evidence.quote not in session['source'][evidence.source]:raise OllamaSchemaError('Câu hỏi có trích dẫn ngoài CV/JD; vui lòng thử lại.')
        if any(t['question']['text'].strip().casefold()==result.question.text.strip().casefold() for t in session['turns']):raise OllamaSchemaError('Câu hỏi bị lặp; vui lòng thử lại.')
    if (result.feedback is not None)!=(answer is not None):raise OllamaSchemaError('Nhận xét chưa đúng lượt; vui lòng thử lại.')
    vi=r'[ăâđêôơưàáạảãầấậẩẫằắặẳẵèéẹẻẽềếệểễìíịỉĩòóọỏõồốộổỗờớợởỡùúụủũừứựửữỳýỵỷỹ]'
    if session.get('language')=='vi':
        texts=([result.question.text] if result.question else [])+([result.feedback.suggested_approach] if result.feedback else [])
        if any(not re.search(vi,text,re.I) for text in texts):raise OllamaSchemaError('AI chưa trả lời đúng tiếng Việt; vui lòng thử lại.')
    if result.feedback:
        if {item.dimension for item in result.feedback.rubric}!={'relevance','clarity','specificity','technical_accuracy'}:raise OllamaSchemaError('Rubric chưa đủ tiêu chí; vui lòng thử lại.')
        if any(not quote.strip() or quote not in answer for quote in result.feedback.answer_quotes):raise OllamaSchemaError('Nhận xét trích sai câu trả lời; vui lòng thử lại.')
        if session['turns'][-1]['question']['kind']=='behavioral':
            for item in result.feedback.rubric:
                if item.dimension=='technical_accuracy':item.score=None


def report(turns):
    feedbacks=[t['feedback'] for t in turns if t.get('feedback')]
    dimensions={}
    for name in ('relevance','clarity','specificity','technical_accuracy'):
        scores=[r['score'] for f in feedbacks for r in f['rubric'] if r['dimension']==name and r['score'] is not None]
        dimensions[name]={'average':round(sum(scores)/len(scores),2) if scores else None,'rated_answers':len(scores)}
    return dict(answered=len(feedbacks),rubric=dimensions,
        strengths=list(dict.fromkeys(x for f in feedbacks for x in f['strengths'])),
        improvements=list(dict.fromkeys(x for f in feedbacks for x in f['improvements'])),
        notice='Nhận xét AI phục vụ luyện tập, có thể sai; không phải kết quả tuyển dụng hay xác suất trúng tuyển.')


def evidence_segments(source):
    result={}
    for kind,text in source.items():
        chunks=[part.strip() for part in re.split(r'\n+|(?<=[.!?])\s+',text) if part.strip()]
        index=0
        for chunk in chunks:
            for offset in range(0,len(chunk),600):
                result[f'{kind}:{index}']=chunk[offset:offset+600]
                index+=1
    return result


def response_schema(refs,question_kind):
    grounded_question=create_model('GroundedQuestion',__base__=QuestionPlan,
        evidence_refs=(list[Literal[tuple(refs)]],Field(min_length=1,max_length=3)),
        kind=(Literal[question_kind],...))
    return create_model('InitialGroundedTurn',__base__=InitialTurn,question=(grounded_question,...))


def run_turn(task_id,payload):
    from backend.app.services.ai_progress import report as progress
    session=read(payload['session_id'])
    if task_id in session['processed_tasks']:return {'session_id':session['session_id'],'version':session['version']}
    if session['model']!=settings.interview_model or session['prompt_version']!=PROMPT_VERSION:raise RevisionConflict('Cấu hình AI đã thay đổi; tạo phiên mới để giữ nhất quán.')
    pending=session['pending']
    if not pending or pending['task_id']!=task_id or session['version']!=payload['request_version']:raise RevisionConflict('Tác vụ không còn thuộc lượt hiện tại')
    segments=evidence_segments(session['source'])
    question_kind='technical' if len(session['turns'])%2==0 else 'behavioral'
    question_input=dict(operation='question',language=session['language'],source_segments=segments,
        next_question_kind=question_kind,
        next_question_goal='Ask about a concrete past teamwork, feedback or prioritization situation in the project.' if question_kind=='behavioral' else 'Ask one technical reasoning question about a skill in the CV/JD.',
        previous_questions=[t['question']['text'] for t in session['turns']])
    last=pending['answer'] is not None and len(session['turns'])>=session['question_count']
    language_instruction='BẮT BUỘC: Viết câu hỏi, nhận xét, lý do, điểm tốt, góp ý bằng TIẾNG VIỆT có dấu. Chỉ trích dẫn câu trả lời giữ nguyên ngôn ngữ gốc. Không trả lời bằng tiếng Anh.' if session['language']=='vi' else 'Write all questions and feedback in English, preserving answer quotes exactly.'
    system=language_instruction+'\n'+SYSTEM+'\n'+language_instruction
    generated=None;graded=None
    with llm_deadline(300):
        if pending['answer'] is not None:
            # Never show the forthcoming question to the grader. Combining both
            # tasks caused Qwen to grade an answer against the next question.
            grade_input=dict(operation='feedback',language=session['language'],
                current_question=session['turns'][-1]['question'],answer=pending['answer'])
            progress('interview_feedback','Đang nhận xét câu trả lời vừa gửi')
            graded=request_structured([{'role':'system','content':system},{'role':'user','content':json.dumps(grade_input,ensure_ascii=False)}],FinalTurn,task='interview')
        if not last:
            progress('interview_question','Đang chuẩn bị câu hỏi tiếp theo')
            generated=request_structured([{'role':'system','content':system},{'role':'user','content':json.dumps(question_input,ensure_ascii=False)}],response_schema(segments,question_kind),task='interview')
    planned=getattr(generated,'question',None)
    question=None
    if planned:
        if any(ref not in segments for ref in planned.evidence_refs):raise OllamaSchemaError('Câu hỏi chọn đoạn nguồn không tồn tại; vui lòng thử lại.')
        question=PracticeQuestion(kind=planned.kind,text=planned.text,evidence=[{'source':ref.split(':')[0],'quote':segments[ref]} for ref in planned.evidence_refs])
    result=PracticeTurn(question=question,feedback=getattr(graded,'feedback',None))
    validate_turn(result,session,pending)
    with database.connect() as c,c.transaction():
        c.execute('SELECT pg_advisory_xact_lock(hashtext(%s))',(session['session_id'],))
        current=read(session['session_id'],connection=c)
        if task_id in current['processed_tasks']:return {'session_id':current['session_id'],'version':current['version']}
        if current['version']!=session['version'] or current['pending']['task_id']!=task_id:raise RevisionConflict('Phiên đã đổi trong khi xử lý')
        if result.feedback:
            current['turns'][-1].update(answer=pending['answer'],feedback=result.feedback.model_dump(),answered_at=now())
        if result.question:current['turns'].append(dict(question=result.question.model_dump(),answer=None,feedback=None))
        current.update(version=current['version']+1,pending=None,status='awaiting_answer' if result.question else 'completed',updated_at=now())
        current['processed_tasks'].append(task_id)
        if current['status']=='completed':current['report']=report(current['turns'])
        database.put_record(KIND,current['session_id'],current,connection=c)
    return {'session_id':current['session_id'],'version':current['version']}
