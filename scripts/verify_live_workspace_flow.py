"""Opt-in actual Qwen flow, exclusively on the isolated restored DB/backend 8014.
Uses a generated synthetic CV; never reads a personal CV for evaluation/training.
"""
import json
import os
import time
from pathlib import Path
from uuid import uuid4


def main():
    if os.getenv('KLTN_LIVE_WORKSPACE')!='1':raise SystemExit('Opt in with KLTN_LIVE_WORKSPACE=1')
    os.environ.update(KLTN_STORAGE='postgres',DATABASE_URL='postgresql://kltn_demo:local-preflight-only@127.0.0.1:55432/kltn_restore_verify',KLTN_WORKER_ENABLED='0')
    import httpx,pymupdf
    from backend.app.db import database,workflow_repository as records
    from backend.app.db.profile_revision_repository import current_revision
    from backend.app.schemas.cv import CVDocument
    from backend.app.schemas.resume import ResumeStart,ResumeSave,ResumePublish,Presentation
    from backend.app.services import resumes,tasks,applications
    from backend.app.schemas.application import ApplicationUpdate
    from backend.app.services.cv_renderer import render_pdf
    from scripts.verify_assistant_postgres import cleanup
    owned={'records':[],'tasks':[],'profiles':[],'threads':[]};job_id=None;analysis_ids=[];match_ids=[]
    manifest={'synthetic_fixture':True,'stages':[]};started=time.monotonic();out=Path('output/evaluation/live-workspace-flow.json')
    out.parent.mkdir(parents=True, exist_ok=True)
    def stage(name,**details):
        manifest['stages'].append({'name':name,'elapsed':round(time.monotonic()-started,2),**details});out.write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
    def checked(r):
        assert r.is_success,(r.status_code,r.text[:500]);return r.json()
    try:
        unique=uuid4().hex
        document=CVDocument(source_profile_revision_id='synthetic-source',language='en',contact={'full_name':'Nguyễn An QA','email':'synthetic.qa@example.com'},sections=[{'kind':'experience','heading':'Experience','entries':[{'source_entry_id':'one','title':'Backend Developer','subtitle':'Synthetic QA Company','period':'2023-01 – 2025-06','bullets':[{'text':'Built Python REST APIs with PostgreSQL and wrote integration tests.','source_refs':['/experience/0/description/0']}]}]},{'kind':'project','heading':'Projects','entries':[{'source_entry_id':'two','title':'Python API Project','bullets':[{'text':'Implemented a Python service with PostgreSQL transactions.','source_refs':['/project/0/description/0']}]}]},{'kind':'skills','heading':'Skills','entries':[{'source_entry_id':'three','title':'Programming','bullets':[{'text':'Python, PostgreSQL, Git','source_refs':['/skills/0/items/0']}]}]}])
        pdf=render_pdf(document,'ats',Presentation().model_dump())
        with httpx.Client(base_url='http://127.0.0.1:8014',timeout=600,trust_env=False) as client:
            extraction=checked(client.post('/api/profiles/extract',files={'file':('synthetic-qa.pdf',pdf,'application/pdf')}));root=extraction['thread_id'];owned['profiles'].append(root);owned['records'].append(['profiles',root]);owned['threads'].append(root)
            assert 'Nguyễn An' in extraction['profile']['contact']['full_name'];assert 'Docker' not in json.dumps(extraction['profile'])
            checked(client.post('/api/profiles/'+root+'/confirm',json={'profile':extraction['profile']}));stage('upload_and_explicit_profile_confirmation',profile_id=root)
            initial=records.get('profiles',root)
            job=checked(client.post('/api/dashboard/jobs',json={'job_description_text':'Synthetic QA job '+unique+'\nJob Title: Backend Developer\nCompany: Synthetic QA Company\nResponsibilities:\nBuild Python APIs and SQL services.\nRequirements:\n- Python is required.\n- PostgreSQL is required.\n- Docker is required.\nBenefits:\nLearning support. This posting is synthetic test data, not a real vacancy.'}));job_id=job['posting_id']
            before=resumes.start(ResumeStart(profile_id=root,title='QA flow baseline'));owned['records'].append(['resume_drafts',before['resume_id']]);before_cv=resumes.publish(before['resume_id'],ResumePublish(expected_version=1,event_id='baseline'))['cv_id'];owned['records'].append(['cv_versions',before_cv])
            evaluated=checked(client.post('/api/dashboard/jobs/'+job_id+'/evaluate',json={'cv_id':before_cv}));analysis_ids.append(evaluated['analysis']['job_id'])
            if evaluated.get('matching'):match_ids.append(evaluated['matching']['result_id'])
            stage('select_job_and_evaluate_exact_cv',status=evaluated['status'],input_type=evaluated['input_type'],evidence_quotes=len(evaluated.get('evidence_quotes',{})))
            update=checked(client.post('/api/profile-sessions/update',json={'profile_id':root,'posting_id':job_id}));sid=update['session_id'];owned['records'].append(['sessions',sid]);owned['threads'].append(sid)
            assert update['status']=='pending_answer',update['status']
            assert 'docker' in json.dumps(update['target']).lower(),update['target']
            answer='I used Docker in the Python API Project to package the Python service and run PostgreSQL containers.'
            proposal=checked(client.post('/api/profile-sessions/'+sid+'/actions',json={'action_id':update['action_id'],'event_id':uuid4().hex,'decision':'yes','message':answer,'target_section':'project','entry_name':'Container packaging practice','confirmed_skills':[s for s in update['target'].get('skill_options',[]) if 'docker' in s.lower()]}))
            assert proposal['status']=='pending_approval',proposal['status'];assert current_revision(root)==root
            approved=checked(client.post('/api/profile-sessions/'+sid+'/actions',json={'action_id':proposal['action_id'],'event_id':uuid4().hex,'decision':'approve'}));revision=approved['profile_id']
            if revision!=root:owned['records'].append(['profiles',revision])
            assert revision!=root and records.get('profiles',root)==initial
            stage('answer_gap_and_approve_profile_update',revision_id=revision)
            session=checked(client.post('/api/assistant',json={'profile_id':revision,'posting_id':job_id,'event_id':uuid4().hex}));key=session['session_id'];owned['records'].append(['assistant_sessions',key])
            queued=checked(client.post('/api/assistant/'+key+'/messages',json={'expected_version':1,'event_id':uuid4().hex,'intent':'tailor_cv'}));task_id=queued['pending']['task_id'];owned['tasks'].append(task_id);owned['threads'].append('cv:'+task_id.removeprefix('task_'));owned['records'].append(['cv_sessions',task_id.removeprefix('task_')])
            with database.connect() as c:
                task=tasks.claim(c);assert task['task_id']==task_id;tasks.perform(c,task)
            done=tasks.read(task_id);assert done['status']=='completed',done['error'];session=checked(client.get('/api/assistant/'+key));result=session['messages'][-1]['result'];rid=result['resume_id'];owned['records'].append(['resume_drafts',rid])
            stage('qwen_tailor_and_resume_chat',session_id=key,resume_id=rid)
            draft=resumes.read(rid);doc=CVDocument.model_validate(draft['document']);saved=resumes.save(rid,ResumeSave(expected_version=1,title='QA · CV đã điều chỉnh',document=doc,presentation=Presentation(template='sidebar',font='serif',font_size=11)))
            assert checked(client.get('/api/resumes/'+rid))['version']==2
            final_cv=resumes.publish(rid,ResumePublish(expected_version=2,event_id='explicit-final-approval'))['cv_id'];owned['records'].append(['cv_versions',final_cv])
            actual=client.get('/api/cv/versions/'+final_cv+'/pdf');assert actual.is_success
            pdfpath=Path('output/evaluation/live-workspace-final.pdf');pdfpath.write_bytes(actual.content)
            with pymupdf.open(stream=actual.content,filetype='pdf') as exported:
                text=' '.join(' '.join(p.get_text() for p in exported).split());assert 'Nguyễn An' in text
                exported[0].get_pixmap(matrix=pymupdf.Matrix(1.3,1.3)).save('output/evaluation/live-workspace-final.png')
            stage('change_template_save_confirm_pdf_reload',cv_id=final_cv)
            evaluated=checked(client.post('/api/dashboard/jobs/'+job_id+'/evaluate',json={'cv_id':final_cv}));assert evaluated['input_id']==final_cv
            if evaluated.get('matching'):match_ids.append(evaluated['matching']['result_id'])
            track=applications.update(job_id,ApplicationUpdate(expected_version=0,event_id='source',status='opened_source',job_content_hash=job['content_hash'],cv_id=final_cv));assert track['status']=='opened_source'
            track=applications.update(job_id,ApplicationUpdate(expected_version=1,event_id='user-sent',status='applied',job_content_hash=job['content_hash'],cv_id=final_cv));assert track['cv_id']==final_cv
            owned['records'].append(['applications',applications.identity(job_id)])
            stage('evaluate_final_cv_and_self_confirm_tracker',status=track['status']);manifest['passed']=True
    finally:
        cleanup(database,owned)
        with database.connect() as c,c.transaction():
            for key in match_ids:c.execute("DELETE FROM kltn_app.records WHERE kind='matches' AND record_id=%s",(key,))
            for key in analysis_ids:
                c.execute("DELETE FROM kltn_app.records WHERE kind='analyses' AND record_id=%s",(key,))
                c.execute("DELETE FROM kltn_app.records WHERE kind='analysis_cache' AND payload->>'job_id'=%s",(key,))
            if job_id:
                c.execute('DELETE FROM kltn_app.job_snapshots WHERE posting_id=%s',(job_id,));c.execute('DELETE FROM kltn_app.job_postings WHERE posting_id=%s',(job_id,))
        manifest['cleaned_up']=True;manifest['seconds']=round(time.monotonic()-started,2);out.write_text(json.dumps(manifest,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
