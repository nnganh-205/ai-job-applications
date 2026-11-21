"""Durable conversation + bounded intent routing over existing CV/profile/match agents."""
import json
import re
import os
from backend.app.db import database,profile_repository,workflow_repository as records
from backend.app.db.job_posting_repository import get_posting,utc_now
from backend.app.db.profile_revision_repository import current_revision,RevisionConflict
from backend.app.schemas.assistant import AssistantStart,AssistantMessage,IntentDecision
from backend.app.schemas.cv import CVStart
from backend.app.schemas.resume import Presentation
from ai.llm.ollama_client import request_structured,llm_deadline
from ai.prompts.assistant_prompt import CHAT_SYSTEM,PROMPT_VERSION
from backend.app.services.assistant_routing import ChatDecision, StandaloneChatDecision, SourceMismatch, expand_decision, quick_decision, routing_payload
from ai.prompts.cv_prompt import CV_PROMPT_VERSION
from backend.app.core.config import settings
from backend.app.services import tasks
from backend.app.services.ai_progress import report
from backend.app.services.interviews import digest

from backend.app.core.workspace import owner_id, record_kind
KIND='assistant_sessions'
LABELS={'review_cv':'Rà soát CV','tailor_cv':'Điều chỉnh CV theo JD','evaluate':'Xem độ phù hợp','update_profile':'Bổ sung hồ sơ','find_jobs':'Tìm việc phù hợp','clarify':'Làm rõ yêu cầu','advice':'Tư vấn CV','build_cv':'Tạo CV qua trò chuyện','prepare_cv':'Kiểm tra và tạo CV','labor_law':'Hỏi luật lao động'}


def read(key,connection=None):
    tasks.require_database()
    if connection is None:
        with database.connect() as c:return read(key,c)
    row=connection.execute('SELECT payload FROM kltn_app.records WHERE kind=%s AND record_id=%s',(record_kind(KIND),key)).fetchone()
    if row is None or row['payload']['owner_id']!=owner_id():raise LookupError('Không tìm thấy cuộc trò chuyện')
    return row['payload']


def public(session):return {key:value for key,value in session.items() if key not in {'owner_id','events','start_digest','processed_tasks'}}


def recent():
    tasks.require_database()
    with database.connect() as c:
        rows=c.execute("SELECT payload FROM kltn_app.records WHERE kind=%s AND payload->>'owner_id'=%s ORDER BY updated_at DESC LIMIT 50",(record_kind(KIND),owner_id())).fetchall()
    return [{k:s[k] for k in ('session_id','title','context','status','updated_at')} for s in (row['payload'] for row in rows)]


def start(request:AssistantStart):
    tasks.require_database()
    identity='assistant_'+digest([owner_id(),request.event_id])[:32]
    signature=digest(request.model_dump())
    with database.connect() as c,c.transaction():
        c.execute('SELECT pg_advisory_xact_lock(hashtext(%s))',(identity,))
        old=c.execute('SELECT payload FROM kltn_app.records WHERE kind=%s AND record_id=%s',(record_kind(KIND),identity)).fetchone()
        if old:
            if old['payload']['start_digest']!=signature:raise RevisionConflict('Mã tạo phiên đã dùng cho nguồn khác')
            return public(old['payload'])
        context=request.model_dump(exclude={'event_id'})
        if request.profile_id:
            context['profile_id']=current_revision(request.profile_id)
            profile=profile_repository.load_profile_record(context['profile_id'],profile_repository.DEFAULT_STORAGE_DIR)
            if profile is None:raise LookupError('Không tìm thấy hồ sơ đã xác nhận')
            context['source_name']=profile.profile.contact.full_name or 'Hồ sơ đã xác nhận'
        elif request.cv_id:
            cv=records.get('cv_versions',request.cv_id)
            if cv is None:raise LookupError('Không tìm thấy CV đã xác nhận')
            context['source_name']=cv.get('title') or 'CV đã xác nhận'
            context['profile_revision_id']=cv['document']['source_profile_revision_id']
        if request.posting_id:
            job=get_posting(request.posting_id)
            if job is None:raise LookupError('Không tìm thấy công việc')
            context.update(job_hash=job.content_hash,job_title=job.title)
        session=dict(schema_version=1,session_id=identity,owner_id=owner_id(),title='Cuộc trò chuyện mới',
            version=1,status='ready',context=context,start_digest=signature,events={},processed_tasks=[],pending=None,
            messages=[dict(role='assistant',text='Chào bạn! Mình có thể giải đáp cách viết CV, cùng bạn tạo CV mới qua trò chuyện hoặc rà soát CV đã có. Bạn đang muốn chuẩn bị gì?' ,created_at=utc_now())],
            model=settings.assistant_model,prompt_version=PROMPT_VERSION,created_at=utc_now(),updated_at=utc_now())
        database.put_record(KIND,identity,session,connection=c)
        return public(session)


def message(key,request:AssistantMessage):
    tasks.require_database()
    signature=digest(request.model_dump())
    with database.connect() as c,c.transaction():
        c.execute('SELECT pg_advisory_xact_lock(hashtext(%s))',(key,))
        session=read(key,c)
        if request.event_id in session['events']:
            if session['events'][request.event_id]!=signature:raise RevisionConflict('Mã gửi đã dùng cho nội dung khác')
            return public(session)
        if session['version']!=request.expected_version:raise RevisionConflict('Cuộc trò chuyện đã thay đổi. Tải lại trước khi gửi.')
        if session['pending']:raise RevisionConflict('Đang xử lý yêu cầu trước. Chờ kết quả hoặc thử lại tác vụ bị lỗi.')
        if len(session['messages'])>=101:raise ValueError('Cuộc trò chuyện đã dài; tạo phiên mới để tiếp tục.')
        session['version']+=1
        task=tasks.submit('assistant',{'session_id':key,'request_version':session['version']},'assistant-'+key+'-'+str(session['version']),connection=c)
        text=request.text.strip() or LABELS[request.intent]
        session['messages'].append(dict(role='user',text=text,intent=request.intent,created_at=utc_now()))
        session.update(status='processing',pending={'task_id':task['task_id'],'intent':request.intent,'text':text},updated_at=utc_now())
        session['events'][request.event_id]=signature
        if session['title']=='Cuộc trò chuyện mới':session['title']=text[:80]
        database.put_record(KIND,key,session,connection=c)
        return public(session)


def choose_intent(text,context,history=None,intake=None):
    direct = quick_decision(text, intake)
    if direct:
        return direct
    recent, payload = routing_payload(text, context, history, intake)
    report('intent','Đang đọc câu hỏi và thông tin trong cuộc trò chuyện')
    with llm_deadline(120):
        messages = [
            {'role':'system','content':CHAT_SYSTEM}, *recent,
            {'role':'user','content':'Ngữ cảnh:\n'+json.dumps(payload, ensure_ascii=False, separators=(',', ':'))
                +'\nTIN NHẮN HIỆN TẠI:\n'+text},
        ]
        schema = ChatDecision if intake else StandaloneChatDecision
        result = request_structured(messages, schema, task='assistant')
        try:
            decision = expand_decision(result, text)
        except SourceMismatch:
            from backend.app.services.assistant_grounding import recover_sources
            decision = recover_sources(result,text,request_structured)
    from backend.app.services.assistant_intake import validated_signal
    decision.intake_signal = validated_signal(decision.intake_signal, text) if intake else None
    return decision


def require_context(context,intent):
    if intent in {'review_cv','tailor_cv','evaluate','find_jobs'} and not (context.get('profile_id') or context.get('cv_id')):
        return 'Hãy tạo cuộc trò chuyện mới và chọn một hồ sơ hoặc bản CV để mình dùng đúng nội dung của bạn.'
    if intent in {'tailor_cv','evaluate'} and not context.get('posting_id'):
        return 'Bạn muốn đối chiếu với công việc nào? Tạo phiên mới, chọn JD rồi tiếp tục tác vụ này.'
    if intent=='update_profile' and not context.get('profile_id'):
        return 'Để bổ sung sự thật, hãy chọn hồ sơ đã xác nhận trong phiên mới hoặc tạo / chỉnh thông tin trong Thư viện CV. CV đang chọn được giữ nguyên.'
    return None


def dispatch(intent,session,task_id):
    context=session['context']
    report('dispatch',LABELS.get(intent,'Đang xử lý yêu cầu'))
    if intent=='find_jobs':
        from backend.app.services.dashboard_service import dashboard_snapshot
        if context.get('cv_id'):
            from backend.app.schemas.cv import CVDocument
            from backend.app.services.cv_evaluation import displayed_profile
            profile,_=displayed_profile(CVDocument.model_validate(records.get('cv_versions',context['cv_id'])['document']))
        else:profile=profile_repository.load_profile_record(context['profile_id'],profile_repository.DEFAULT_STORAGE_DIR).profile
        terms=list(dict.fromkeys(term.strip().casefold() for group in profile.skills for skill in group.items for term in re.split(r'[,;\n]+',skill) if len(term.strip())>1))
        rows=dashboard_snapshot()['jobs']
        # A transparent keyword shortlist, not a fabricated match percentage.
        ranked=[]
        for row in rows:
            job=get_posting(row['posting_id']);text=(job.title+' '+job.description).casefold()
            from ai.agents.matching_agent import contains_term
            found=[term for term in terms if contains_term(text,term)]
            if found:ranked.append((len(found),row,found))
        ranked.sort(key=lambda item:(-item[0],item[1]['posting_id']))
        return dict(type='jobs',text='Các tin có từ khóa kỹ năng bạn đã khai báo. Đây là gợi ý tìm kiếm, chưa phải đánh giá mức đáp ứng JD.',jobs=[dict(posting_id=r['posting_id'],title=r['title'],company=r.get('company'),terms=found) for _,r,found in ranked[:6]])
    if intent=='evaluate':
        from backend.app.services.dashboard_service import evaluate_job
        result=evaluate_job(context['posting_id'],context.get('profile_id'),cv_id=context.get('cv_id'))
        return dict(type='evaluation',text='Đã đối chiếu nội dung được chọn. Xem từng yêu cầu và bằng chứng bên dưới.' if result.status!='needs_review' else 'JD còn điểm cần kiểm tra; chưa thể kết luận mức đáp ứng. Xem các cảnh báo bên dưới.',evaluation=result.model_dump(mode='json'))
    if intent=='update_profile':
        if not context.get('posting_id'):return dict(type='guidance',text='Mở hồ sơ để bổ sung thông tin thật và xác nhận bản nháp. Nếu muốn hỏi bổ sung theo yêu cầu công việc, chọn thêm JD trong phiên mới.',href='/workspace/resumes')
        from backend.app.services.profile_sessions import start_update
        from backend.app.schemas.profile_update import UpdateStart
        result=start_update(UpdateStart(profile_id=context['profile_id'],posting_id=context['posting_id']),session_id=task_id.removeprefix('task_'))
        return dict(type='profile_update',text='Đã chuẩn bị câu hỏi bổ sung theo yêu cầu còn thiếu. Câu trả lời chỉ tạo đề xuất; bạn phải kiểm tra và duyệt trước khi lưu hồ sơ.',profile_session_id=result.session_id,href='/workspace/profile/conversation/'+result.session_id)
    if intent in {'review_cv','tailor_cv'}:
        from ai.graph.cv_workflow import start as start_cv
        result=start_cv(CVStart(profile_id=context.get('profile_id'),cv_id=context.get('cv_id'),posting_id=context.get('posting_id'),mode='review' if intent=='review_cv' else 'generate',language=context['language']),session_id=task_id.removeprefix('task_'))
        resume_id='resume_'+task_id.removeprefix('task_')
        draft=dict(schema_version=2,resume_id=resume_id,title=('CV theo '+context.get('job_title','công việc'))[:120] if intent=='tailor_cv' else 'CV đang rà soát',version=1,document=result.document.model_dump(mode='json'),baseline=result.document.model_dump(mode='json'),presentation=Presentation().model_dump(),created_at=utc_now(),updated_at=utc_now(),publications={},latest_cv_id=None,review=result.review.model_dump(mode='json'))
        lineage=None
        if context.get('cv_id'):
            from copy import deepcopy
            from backend.app.services.cv_lineage import version_status
            source=records.get('cv_versions',context['cv_id'])
            draft['presentation']=deepcopy(source.get('presentation') or Presentation().model_dump())
            draft.update(source_cv_id=context['cv_id'],source_posting_id=context.get('posting_id'))
            lineage=version_status(context['cv_id'],source)
        return dict(type='cv_draft',cv_version=lineage,agent_model=settings.model_for_task('cv'),agent_prompt_version=CV_PROMPT_VERSION,cv_session_id=result.session_id,text='Đã chuẩn bị bản nháp và nhận xét từ nội dung nguồn. Mở editor để kiểm tra, áp dụng đề xuất và xác nhận bản CV; hồ sơ nguồn chưa thay đổi.',resume_id=resume_id,href='/workspace/resumes/'+resume_id+'/edit',review=result.review.model_dump(mode='json'),_draft=draft)
    return dict(type='clarification',text='Bạn muốn rà soát CV, xem độ phù hợp với JD hay bổ sung hồ sơ?')


def run_message(task_id,payload):
    session=read(payload['session_id'])
    if task_id in session['processed_tasks']:return {'session_id':session['session_id'],'version':session['version']}
    if session['model']!=settings.assistant_model or session['prompt_version'] not in {PROMPT_VERSION,'assistant-conversation-v4','assistant-router-v2'}:raise RevisionConflict('Cấu hình trợ lý đã đổi. Tạo cuộc trò chuyện mới để tiếp tục.')
    pending=session['pending']
    if not pending or pending['task_id']!=task_id or session['version']!=payload['request_version']:raise RevisionConflict('Tác vụ không còn thuộc lượt hiện tại')
    context=session['context']
    if context.get('posting_id'):
        job=get_posting(context['posting_id'])
        if not job or job.content_hash!=context['job_hash']:raise RevisionConflict('JD đã thay đổi. Tạo phiên mới để chọn đúng nội dung cập nhật.')
    if context.get('profile_id') and current_revision(context['profile_id'])!=context['profile_id']:raise RevisionConflict('Hồ sơ đã thay đổi. Tạo phiên mới để dùng thông tin mới nhất.')
    from backend.app.services.assistant_intake import collect, direct_signal, missing_fields
    from backend.app.services.assistant_answers import contextual_answer
    intake=session.get('cv_intake')
    from backend.app.services.assistant_lists import upgrade_lists
    if intake:
        intake = upgrade_lists(intake)
        session['cv_intake'] = intake
    bound=contextual_answer(intake['profile'],(missing_fields(intake) or ['complete'])[0],pending['text']) if intake else None
    from backend.app.services.labor_law_router import is_law_question
    if pending['intent']=='labor_law' or (pending['intent'] is None and is_law_question(pending['text'])):
        decision=IntentDecision(intent='labor_law')
    elif pending['intent']:
        decision=IntentDecision(intent=pending['intent'])
    elif (signal := direct_signal(session.get('cv_intake'), pending['text'], session['messages'][:-1])):
        decision=IntentDecision(intent='build_cv',intake_signal=signal)
    elif bound:
        decision=bound
    else:
        decision=choose_intent(pending['text'],context,session['messages'][:-1],session.get('cv_intake'))
    if session.get('cv_intake') and (decision.updates or decision.intake_signal) and decision.intent in {'advice','clarify'}:
        decision.intent='build_cv'
    missing=require_context(context,decision.intent)
    if decision.intent=='labor_law':
        from ai.rag.labor_law import answer as law_answer
        result=law_answer(pending['text'])
    elif missing:result=dict(type='guidance',text=missing,href='/workspace/resumes')
    elif decision.intent in {'build_cv','prepare_cv'}:
        report('collect','Đang cập nhật bản nháp và kiểm tra phần thông tin còn thiếu')
        result=collect(session,decision,pending['text'],task_id,
            polish_with_model=bool(decision.intake_signal and decision.intake_signal.kind=='write_bullets'))
    elif decision.intent=='advice':
        result=dict(type='advice',text=decision.reply.strip() or 'Mình có thể giúp bạn viết nội dung CV, chọn mẫu hoặc cùng thu thập thông tin để tạo một bản CV mới. Bạn đang cần hỗ trợ phần nào?')
    elif decision.intent=='clarify':result=dict(type='clarification',text=decision.clarification or decision.reply or 'Bạn muốn hỏi cách viết CV hay bắt đầu tạo một bản CV mới?')
    else:result=dispatch(decision.intent,session,task_id)
    draft=result.pop('_draft',None)
    intake=result.pop('_intake',None)
    profile_draft=result.pop('_profile_draft',None)
    with database.connect() as c,c.transaction():
        c.execute('SELECT pg_advisory_xact_lock(hashtext(%s))',(session['session_id'],))
        current=read(session['session_id'],c)
        if task_id in current['processed_tasks']:return {'session_id':current['session_id'],'version':current['version']}
        if current['version']!=session['version'] or not current['pending'] or current['pending']['task_id']!=task_id:raise RevisionConflict('Cuộc trò chuyện đã đổi trong khi xử lý')
        if draft:database.put_record('resume_drafts',draft['resume_id'],draft,immutable=True,connection=c)
        if profile_draft:database.put_record('profile_drafts',profile_draft['draft_id'],profile_draft,immutable=True,connection=c)
        if intake is not None:current['cv_intake']=intake
        current['messages'].append(dict(role='assistant',text=result['text'],intent=decision.intent,result=result,created_at=utc_now(),source_context=context,prompt_version=PROMPT_VERSION,model=settings.assistant_model))
        current['processed_tasks'].append(task_id)
        current.update(version=current['version']+1,status='ready',pending=None,prompt_version=PROMPT_VERSION,updated_at=utc_now())
        database.put_record(KIND,current['session_id'],current,connection=c)
    return {'session_id':current['session_id'],'version':current['version']}
