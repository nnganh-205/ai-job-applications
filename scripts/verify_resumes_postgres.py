"""CV library transaction, immutable version and PDF HTTP checks on a disposable DB."""
import os
from unittest.mock import patch


def main():
    url=os.environ.get('KLTN_TEST_DATABASE_URL')
    if not url:raise SystemExit('Set KLTN_TEST_DATABASE_URL to a restored disposable DB')
    os.environ.update(KLTN_STORAGE='postgres',DATABASE_URL=url)
    from backend.app.db import database,profile_repository as profiles
    from backend.app.services import profile_drafts,resumes
    from backend.app.schemas.profile_draft import DraftSave,DraftConfirm
    from backend.app.schemas.profile import MasterProfile
    from backend.app.schemas.resume import ResumeStart,ResumePublish
    from backend.app.main import app
    from fastapi.testclient import TestClient
    root=None;draft_id=None;resume_id=None;cv_id=None
    try:
        draft=profile_drafts.start();draft_id=draft['draft_id']
        p=MasterProfile(contact={'full_name':'CV Integration Fixture'},experience=[],project=[{'project_name':'Fixture project','description':['Built Python APIs.','Maintained SQL queries.']}],education=[],involvement=[],skills=[])
        draft=profile_drafts.save(draft_id,DraftSave(expected_version=1,profile=p))
        root=profile_drafts.confirm(draft_id,DraftConfirm(expected_version=2,event_id='confirm'))['confirmed_profile_id']
        resume=resumes.start(ResumeStart(profile_id=root));resume_id=resume['resume_id']
        with database.connect() as c:before=c.execute("SELECT count(*) n FROM kltn_app.records WHERE kind='cv_versions'").fetchone()['n']
        with patch.object(resumes,'write',side_effect=RuntimeError('Simulated publish failure')):
            try:resumes.publish(resume_id,ResumePublish(expected_version=1,event_id='rollback'))
            except RuntimeError:pass
            else:raise AssertionError('Expected publish failure')
        with database.connect() as c:assert c.execute("SELECT count(*) n FROM kltn_app.records WHERE kind='cv_versions'").fetchone()['n']==before
        with TestClient(app) as client:
            assert client.get('/api/resumes/'+resume_id).status_code==200
            result=client.post('/api/resumes/'+resume_id+'/publish',json={'expected_version':1,'event_id':'publish'})
            assert result.status_code==200,result.text
            result=result.json();cv_id=result['cv_id']
            assert client.post('/api/resumes/'+resume_id+'/publish',json={'expected_version':1,'event_id':'publish'}).json()==result
            pdf=client.get('/api/cv/versions/'+cv_id+'/pdf');assert pdf.status_code==200,pdf.text
            assert pdf.content.startswith(b'%PDF')
            assert client.get('/api/resumes/published').status_code==200
            preview=client.get('/api/resumes/'+resume_id+'/preview');assert preview.status_code==200
            assert 'CV Integration Fixture' in preview.text
    finally:
        with database.connect() as c,c.transaction():
            for kind,key in [('profile_drafts',draft_id),('resume_drafts',resume_id),('cv_versions',cv_id),('profiles',root)]:
                if key:c.execute('DELETE FROM kltn_app.records WHERE kind=%s AND record_id=%s',(kind,key))
            if resume_id:c.execute("DELETE FROM kltn_app.records WHERE kind='resume_history' AND payload->>'resume_id'=%s",(resume_id,))
            if root:
                c.execute('DELETE FROM kltn_app.profile_heads WHERE root_id=%s',(root,))
                c.execute('DELETE FROM kltn_app.profile_revisions WHERE root_id=%s',(root,))


if __name__=='__main__':main()
