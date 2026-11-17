"""Photo -> CV publish -> tracker integration, only in a disposable PostgreSQL database."""
import io
import os
import tempfile
from uuid import uuid4
from unittest.mock import patch


def main():
    url=os.getenv('KLTN_TEST_DATABASE_URL')
    if not url:raise SystemExit('Set disposable KLTN_TEST_DATABASE_URL')
    os.environ.update(KLTN_STORAGE='postgres',DATABASE_URL=url,KLTN_WORKER_ENABLED='0')
    from PIL import Image
    import pymupdf
    from fastapi.testclient import TestClient
    from backend.app.main import app
    from backend.app.db import database
    from backend.app.db.job_posting_repository import posting_id,upsert_posting,utc_now
    from backend.app.schemas.dashboard import JobPosting
    from backend.app.services import profile_drafts,resumes,applications
    from backend.app.schemas.profile_draft import DraftSave,DraftConfirm
    from backend.app.schemas.profile import MasterProfile
    from backend.app.schemas.resume import ResumeStart
    root=None;draft_id=None;resume_id=None;cv_id=None;asset_id=None;job=None
    try:
        with tempfile.TemporaryDirectory(prefix='kltn-workspace-qa-') as directory:
            os.environ['KLTN_ASSET_STORAGE']=directory
            draft=profile_drafts.start();draft_id=draft['draft_id']
            profile=MasterProfile(contact={'full_name':'Workspace Integration Fixture'},experience=[],project=[{'project_name':'Fixture','description':['Built Python services.','Tested PostgreSQL.']}],education=[],involvement=[],skills=[{'group':'Languages','items':['Python']}])
            draft=profile_drafts.save(draft_id,DraftSave(expected_version=1,profile=profile));root=profile_drafts.confirm(draft_id,DraftConfirm(expected_version=2,event_id='confirm'))['confirmed_profile_id']
            resume=resumes.start(ResumeStart(profile_id=root));resume_id=resume['resume_id']
            image=io.BytesIO();Image.new('RGB',(300,400),'#a8c0dd').save(image,format='PNG')
            with TestClient(app) as client:
                response=client.post('/api/assets/photos',files={'file':('fixture.png',image.getvalue(),'image/png')});assert response.status_code==200,response.text
                asset_id=response.json()['asset_id'];assert client.get('/api/assets/'+asset_id).status_code==200
                request={'expected_version':1,'title':resume['title'],'document':resume['document'],'presentation':{'template':'modern','template_version':2,'photo_asset_id':asset_id}}
                response=client.put('/api/resumes/'+resume_id,json=request);assert response.status_code==200,response.text
                response=client.post('/api/resumes/'+resume_id+'/publish',json={'expected_version':2,'event_id':'publish'});assert response.status_code==200,response.text
                cv_id=response.json()['cv_id'];pdf=client.get('/api/cv/versions/'+cv_id+'/pdf');assert pdf.status_code==200,pdf.text
                with pymupdf.open(stream=pdf.content,filetype='pdf') as doc:
                    assert any(page.get_images() for page in doc)
                    assert 'Workspace Integration Fixture' in ' '.join(' '.join(p.get_text() for p in doc).split())
                unique=uuid4().hex
                job=JobPosting(posting_id=posting_id('fixture','',unique),title='Workspace integration job',description='Fixture only: Python services and SQL.',source_name='fixture',external_id=unique,imported_at=utc_now())
                job,_=upsert_posting(job)
                path='/api/applications/'+job.posting_id
                payload={'expected_version':0,'event_id':'open','status':'opened_source','job_content_hash':job.content_hash,'cv_id':cv_id}
                response=client.post(path+'/events',json=payload);assert response.status_code==200,response.text
                assert response.json()['status']=='opened_source'
                assert client.post(path+'/events',json=payload).json()==response.json()
                payload.update(expected_version=1,event_id='apply',status='applied')
                with patch('backend.app.services.applications.database.put_record',side_effect=RuntimeError('Simulated transaction failure')):
                    try:applications.update(job.posting_id,__import__('backend.app.schemas.application',fromlist=['ApplicationUpdate']).ApplicationUpdate(**payload))
                    except RuntimeError:pass
                    else:raise AssertionError('Expected rollback')
                assert client.get(path).json()['version']==1
                response=client.post(path+'/events',json=payload);assert response.status_code==200,response.text
                assert response.json()['status']=='applied' and response.json()['cv_id']==cv_id
                assert client.get(path).json()['profile_revision_id']==root
                assert client.get('/workspace/applications').status_code==200
    finally:
        with database.connect() as c,c.transaction():
            for kind,key in [('profile_drafts',draft_id),('profiles',root),('resume_drafts',resume_id),('cv_versions',cv_id),('assets',asset_id),('applications',applications.identity(job.posting_id) if job else None)]:
                if key:c.execute('DELETE FROM kltn_app.records WHERE kind=%s AND record_id=%s',(kind,key))
            if root:
                c.execute('DELETE FROM kltn_app.profile_heads WHERE root_id=%s',(root,));c.execute('DELETE FROM kltn_app.profile_revisions WHERE root_id=%s',(root,))
            if job:
                c.execute('DELETE FROM kltn_app.job_snapshots WHERE posting_id=%s',(job.posting_id,));c.execute('DELETE FROM kltn_app.job_postings WHERE posting_id=%s',(job.posting_id,))


if __name__=='__main__':main()
