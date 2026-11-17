"""Interview CAS, atomic queue, pinned source snapshots and resume. Disposable DB only.
Set KLTN_LIVE_INTERVIEW=1 for an actual two-question Qwen practice run.
"""
import json
import os
import time
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4


def main():
    url=os.getenv('KLTN_TEST_DATABASE_URL')
    if not url:raise SystemExit('Set disposable KLTN_TEST_DATABASE_URL')
    os.environ.update(KLTN_STORAGE='postgres',DATABASE_URL=url,KLTN_WORKER_ENABLED='0')
    from backend.app.db import database
    from backend.app.db.job_posting_repository import posting_id,upsert_posting,utc_now
    from backend.app.schemas.dashboard import JobPosting
    from backend.app.schemas.cv import CVDocument
    from backend.app.schemas.interview import InitialTurn,NextTurn,FinalTurn
    from backend.app.services import interviews,tasks
    from backend.app.main import app
    from fastapi.testclient import TestClient
    from backend.tests.test_interviews import feedback,question
    database.migrate()
    live=os.getenv('KLTN_LIVE_INTERVIEW')=='1'
    unique=uuid4().hex;cv_id='cv_'+unique;session_id=None;job=None;task_ids=[]
    started=time.monotonic()
    try:
        document=CVDocument(source_profile_revision_id='fixture_'+unique,language='en',contact={'full_name':'Interview Fixture','email':'private@example.com'},sections=[{'kind':'project','heading':'Projects','entries':[{'source_entry_id':'fixture','title':'Python API project','bullets':[{'text':'Built a Python API with PostgreSQL and wrote integration tests.','source_refs':['/project/0/description/0']}]}]}])
        database.put_record('cv_versions',cv_id,dict(cv_id=cv_id,title='Interview fixture',created_at=utc_now(),document=document.model_dump(mode='json')),immutable=True)
        job=JobPosting(posting_id=posting_id('interview-fixture','',unique),title='Backend Engineer',company='Fixture',description='Build Python APIs with PostgreSQL. Explain API testing, SQL transactions and teamwork. This is synthetic integration data.',source_name='interview-fixture',external_id=unique,imported_at=utc_now())
        job,_=upsert_posting(job)
        with TestClient(app) as client:
            payload=dict(cv_id=cv_id,posting_id=job.posting_id,language='vi' if live else 'en',question_count=2,event_id=unique)
            r=client.post('/api/interviews',json=payload);assert r.status_code==202,r.text
            s=r.json();session_id=s['session_id'];task_ids.append(s['pending']['task_id'])
            assert 'source' not in s and 'owner_id' not in s
            assert client.post('/api/interviews',json=payload).json()==s
            wrong={**payload,'question_count':3};assert client.post('/api/interviews',json=wrong).status_code==409
            stored=interviews.read(session_id);assert 'private@example.com' not in json.dumps(stored['source'])
            # Modifying the latest posting must not alter a practice snapshot.
            job.description='Changed source, not the pinned session.';upsert_posting(job)
            assert interviews.read(session_id)['source']==stored['source']
            def perform(result=None):
                with database.connect() as c:
                    task=tasks.claim(c);assert task and task['task_id']==task_ids[-1], 'Use an idle disposable database'
                    context=nullcontext() if live else patch('backend.app.services.interviews.request_structured',return_value=result)
                    with context as model:
                        tasks.perform(c,task)
                        if not live:
                            inputs=[json.loads(call.args[0][1]['content']) for call in model.call_args_list]
                            for entry in inputs:
                                if entry['operation']=='feedback':
                                    assert 'current_question' in entry and 'answer' in entry
                                    assert 'next_question_goal' not in entry and 'previous_questions' not in entry
                                else:
                                    assert 'answer' not in entry and 'current_question' not in entry
                current=tasks.read(task_ids[-1]);assert current['status']=='completed',current['error']
                return client.get('/api/interviews/'+session_id).json()
            s=perform(InitialTurn(question={**{k:v for k,v in question().items() if k!='evidence'},'evidence_refs':['cv:2']}))
            assert s['status']=='awaiting_answer' and s['version']==2
            # Worker retry after session commit is safe and must not invoke Qwen.
            with patch('backend.app.services.interviews.request_structured',side_effect=AssertionError('duplicate model call')):
                interviews.run_turn(task_ids[-1],{'session_id':session_id,'request_version':1})
            answer='I built a Python API with PostgreSQL. I used transactions to keep writes atomic and integration tests to check rollback on failure. I reviewed the API with a teammate.'
            for index in range(2):
                a=dict(expected_version=s['version'],event_id=uuid4().hex,answer=answer)
                path='/api/interviews/'+session_id+'/answers'
                if index==0:
                    before=s['version']
                    with patch('backend.app.services.interviews.database.put_record',side_effect=RuntimeError('simulated commit failure')):
                        try:interviews.answer(session_id,__import__('backend.app.schemas.interview',fromlist=['InterviewAnswer']).InterviewAnswer(**a))
                        except RuntimeError:pass
                        else:raise AssertionError('Expected failure')
                    assert interviews.read(session_id)['version']==before
                    with database.connect() as c:
                        assert c.execute("SELECT count(*) AS n FROM kltn_app.tasks WHERE kind='interview' AND payload->>'session_id'=%s",(session_id,)).fetchone()['n']==1
                r=client.post(path,json=a);assert r.status_code==202,r.text;s=r.json();task_ids.append(s['pending']['task_id'])
                assert client.post(path,json=a).json()==s
                assert client.post(path,json={**a,'event_id':uuid4().hex}).status_code==409
                q=question('behavioral');q['text']='Describe how you worked with a teammate on the Python API.'
                s=perform(NextTurn(question={**{k:v for k,v in q.items() if k!='evidence'},'evidence_refs':['cv:2']},feedback=feedback()) if index==0 else FinalTurn(feedback=feedback()))
            assert s['status']=='completed' and s['report']['answered']==2
            assert len(s['turns'])==2 and all(t['answer']==answer for t in s['turns'])
            assert client.get('/api/interviews/'+session_id).json()==s
            assert any(row['session_id']==session_id for row in client.get('/api/interviews').json())
            if live:
                import re
                vietnamese=re.compile(r'[ăâđêôơưàáạảãầấậẩẫằắặẳẵèéẹẻẽềếệểễìíịỉĩòóọỏõồốộổỗờớợởỡùúụủũừứựửữỳýỵỷỹ]',re.I)
                assert all(vietnamese.search(t['question']['text']) for t in s['turns']), 'Vietnamese questions required'
                assert all(vietnamese.search(t['feedback']['suggested_approach']) for t in s['turns']), 'Vietnamese feedback required'
                assert [t['question']['kind'] for t in s['turns']]==['technical','behavioral']
                output=Path('output/evaluation/live-interview-result.json');output.parent.mkdir(parents=True,exist_ok=True)
                output.write_text(json.dumps(dict(seconds=round(time.monotonic()-started,2),model=s['model'],prompt_version=s['prompt_version'],synthetic_fixture=True,session=s),ensure_ascii=False,indent=2))
    finally:
        with database.connect() as c,c.transaction():
            if session_id:
                c.execute("DELETE FROM kltn_app.tasks WHERE kind='interview' AND payload->>'session_id'=%s",(session_id,))
                c.execute('DELETE FROM kltn_app.records WHERE kind=%s AND record_id=%s',('interviews',session_id))
            c.execute('DELETE FROM kltn_app.records WHERE kind=%s AND record_id=%s',('cv_versions',cv_id))
            if job:
                c.execute('DELETE FROM kltn_app.job_snapshots WHERE posting_id=%s',(job.posting_id,))
                c.execute('DELETE FROM kltn_app.job_postings WHERE posting_id=%s',(job.posting_id,))


if __name__=='__main__':main()
