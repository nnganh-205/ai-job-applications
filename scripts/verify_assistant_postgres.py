"""Assistant transactions, source isolation, graph reuse and PDF in an idle test DB.
KLTN_LIVE_ASSISTANT=1 uses Qwen for intent routing and CV review.
KLTN_KEEP_ASSISTANT_FIXTURE=1 retains only generated test records for browser QA;
run --cleanup later using the exact recorded IDs. Never point this at user data.
"""
import json
import os
import sys
import time
from pathlib import Path
from unittest.mock import patch
from contextlib import ExitStack
from uuid import uuid4

MANIFEST=Path('output/evaluation/assistant-fixture.json')


def cleanup(database,items):
    with database.connect() as c,c.transaction():
        for kind,key in items.get('records',[]):c.execute('DELETE FROM kltn_app.records WHERE kind=%s AND record_id=%s',(kind,key))
        for root in items.get('profiles',[]):
            c.execute('DELETE FROM kltn_app.profile_heads WHERE root_id=%s',(root,));c.execute('DELETE FROM kltn_app.profile_revisions WHERE root_id=%s',(root,))
        for key in items.get('tasks',[]):c.execute('DELETE FROM kltn_app.tasks WHERE task_id=%s',(key,))
    from backend.app.db.checkpoints import get_checkpointer
    for thread in items.get('threads',[]):get_checkpointer().delete_thread(thread)


def main():
    url=os.getenv('KLTN_TEST_DATABASE_URL')
    if not url or url.rsplit('/',1)[-1]!='kltn_restore_verify':raise SystemExit('Use idle kltn_restore_verify KLTN_TEST_DATABASE_URL')
    os.environ.update(KLTN_STORAGE='postgres',DATABASE_URL=url,KLTN_WORKER_ENABLED='0')
    from backend.app.db import database,profile_repository,workflow_repository as records
    from backend.app.services import profile_drafts,resumes,tasks,assistant
    from backend.app.schemas.profile_draft import DraftSave,DraftConfirm
    from backend.app.schemas.profile import MasterProfile
    from backend.app.schemas.resume import ResumeStart,ResumeSave,ResumePublish,Presentation
    from backend.app.schemas.cv import CVDocument,CVPlan,CVReview
    from backend.app.schemas.assistant import IntentDecision
    from ai.agents.cv_agent import bullet_catalog
    from backend.app.db.profile_revision_repository import current_revision
    from backend.app.main import app
    from fastapi.testclient import TestClient
    database.migrate()
    if '--cleanup' in sys.argv:
        data=json.loads(MANIFEST.read_text());cleanup(database,data);data['cleaned_up']=True;MANIFEST.write_text(json.dumps(data,indent=2));return
    live=os.getenv('KLTN_LIVE_ASSISTANT')=='1';keep=os.getenv('KLTN_KEEP_ASSISTANT_FIXTURE')=='1'
    owned={'records':[],'tasks':[],'profiles':[],'threads':[],'synthetic_fixture':True}
    started=time.monotonic()
    try:
        d=profile_drafts.start();owned['records'].append(['profile_drafts',d['draft_id']])
        profile=MasterProfile(contact={'full_name':'Nguyễn An — QA tổng hợp'},experience=[],project=[{'project_name':'Python API QA','description':['Built Python APIs with PostgreSQL and integration tests.','Hidden COBOL achievement must stay outside the selected CV.']}],education=[],involvement=[],skills=[{'group':'Programming','items':['Python','PostgreSQL']}])
        d=profile_drafts.save(d['draft_id'],DraftSave(expected_version=1,profile=profile));root=profile_drafts.confirm(d['draft_id'],DraftConfirm(expected_version=2,event_id=uuid4().hex))['confirmed_profile_id'];owned['profiles'].append(root);owned['records'].append(['profiles',root])
        original=resumes.start(ResumeStart(profile_id=root,title='QA · CV nguồn (tổng hợp)'));owned['records'].append(['resume_drafts',original['resume_id']])
        doc=CVDocument.model_validate(original['document']);doc.sections[0].entries[0].bullets.pop()
        original=resumes.save(original['resume_id'],ResumeSave(expected_version=1,title=original['title'],document=doc,presentation=Presentation()))
        cv_id=resumes.publish(original['resume_id'],ResumePublish(expected_version=2,event_id='publish'))['cv_id'];owned['records'].append(['cv_versions',cv_id]);immutable=records.get('cv_versions',cv_id)
        with TestClient(app) as client:
            start=dict(cv_id=cv_id,event_id=uuid4().hex)
            r=client.post('/api/assistant',json=start);assert r.status_code==201,r.text;s=r.json();key=s['session_id'];owned['records'].append(['assistant_sessions',key])
            assert client.post('/api/assistant',json=start).json()==s
            assert client.post('/api/assistant',json={**start,'language':'en'}).status_code==409
            message=dict(expected_version=1,event_id=uuid4().hex,text='Rà soát nội dung bản CV này giúp tôi.',intent=None if live else 'review_cv')
            r=client.post('/api/assistant/'+key+'/messages',json=message);assert r.status_code==202,r.text;s=r.json();task_id=s['pending']['task_id'];owned['tasks'].append(task_id);owned['threads'].append('cv:'+task_id.removeprefix('task_'));owned['records'].append(['cv_sessions',task_id.removeprefix('task_')])
            assert client.post('/api/assistant/'+key+'/messages',json=message).json()==s
            assert client.post('/api/assistant/'+key+'/messages',json={**message,'event_id':uuid4().hex}).status_code==409
            def perform(fail_commit=False):
                with database.connect() as c:
                    claimed=tasks.claim(c);assert claimed and claimed['task_id']==task_id,'Test DB must be idle'
                    with ExitStack() as stack:
                        if not live:
                            stack.enter_context(patch('backend.app.services.assistant.choose_intent',return_value=IntentDecision(intent='review_cv')))
                            stack.enter_context(patch('ai.agents.cv_agent.request_structured',return_value=CVPlan(selected_refs=list(bullet_catalog(doc)),review=CVReview(items=[]))))
                        stack.enter_context(patch('ai.graph.cv_workflow.profile_repository.load_profile_record',side_effect=AssertionError('Must not access hidden profile')))
                        if fail_commit:
                            real_write=database.put_record
                            def fail(kind,*args,**kwargs):
                                if kind=='assistant_sessions':raise RuntimeError('Simulated response commit failure')
                                return real_write(kind,*args,**kwargs)
                            stack.enter_context(patch('backend.app.services.assistant.database.put_record',side_effect=fail))
                        tasks.perform(c,claimed)
            if not live:
                perform(fail_commit=True);assert tasks.read(task_id)['status']=='failed'
                assert records.get('resume_drafts','resume_'+task_id.removeprefix('task_')) is None
                assert assistant.read(key)['version']==2
                tasks.retry(task_id)
                with patch('ai.graph.cv_workflow.plan_cv',side_effect=AssertionError('Graph result must resume without rerunning model')):perform()
            else:perform()
            task=tasks.read(task_id);assert task['status']=='completed',task['error']
            s=client.get('/api/assistant/'+key).json();assert s['status']=='ready' and s['version']==3
            result=s['messages'][-1]['result'];assert result['type']=='cv_draft'
            new_id=result['resume_id'];owned['records'].append(['resume_drafts',new_id]);draft=resumes.read(new_id)
            assert 'COBOL' not in json.dumps(draft['document'])
            assert records.get('cv_versions',cv_id)==immutable and current_revision(root)==root
            with patch('backend.app.services.assistant.dispatch',side_effect=AssertionError('Committed task cannot run twice')):assistant.run_message(task_id,{'session_id':key,'request_version':2})
            draft=resumes.save(new_id,ResumeSave(expected_version=1,title='QA · CV đã rà soát (tổng hợp)',document=draft['document'],presentation=Presentation(template='modern')))
            new_cv=resumes.publish(new_id,ResumePublish(expected_version=2,event_id='explicit-test-approval'))['cv_id'];owned['records'].append(['cv_versions',new_cv])
            pdf=client.get('/api/cv/versions/'+new_cv+'/pdf');assert pdf.status_code==200,pdf.text
            import pymupdf
            with pymupdf.open(stream=pdf.content,filetype='pdf') as document:
                text=' '.join(' '.join(p.get_text() for p in document).split());assert 'Nguyễn An' in text and 'COBOL' not in text
            assert client.get('/workspace/assistant/'+key).status_code==200
            assert any(x['session_id']==key for x in client.get('/api/assistant').json())
            owned.update(session_id=key,resume_id=new_id,cv_id=new_cv,source_cv_id=cv_id,profile_id=root,seconds=round(time.monotonic()-started,2),live_qwen=live)
            if live:
                Path('output/evaluation/live-assistant-result.json').write_text(json.dumps({'seconds':owned['seconds'],'session':s,'synthetic_fixture':True},ensure_ascii=False,indent=2))
    finally:
        if keep:MANIFEST.write_text(json.dumps(owned,ensure_ascii=False,indent=2))
        else:cleanup(database,owned)


if __name__=='__main__':main()
