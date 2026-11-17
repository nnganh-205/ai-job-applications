"""History restore API and transaction rollback on disposable PostgreSQL only."""
import os
from uuid import uuid4
from unittest.mock import patch


def main():
    url=os.environ.get('KLTN_TEST_DATABASE_URL','')
    if url.rsplit('/',1)[-1]!='kltn_restore_verify': raise SystemExit('Use kltn_restore_verify only')
    os.environ.update(KLTN_STORAGE='postgres',DATABASE_URL=url,KLTN_WORKER_ENABLED='0')
    from backend.app.db import database,profile_repository as profiles
    from backend.app.schemas.profile import MasterProfile
    from backend.app.schemas.resume import ResumeStart,ResumeSave,Presentation,ResumeRestore
    from backend.app.services import resumes,resume_history as history
    from backend.app.main import app
    from fastapi.testclient import TestClient
    root='history_fixture_'+uuid4().hex;key=None
    try:
        profiles.save_master_profile(root,MasterProfile(contact={'full_name':'History Fixture'},experience=[],project=[{'project_name':'Demo','description':['Built Python APIs.']}],education=[],involvement=[],skills=[]),profiles.DEFAULT_STORAGE_DIR)
        cv=resumes.start(ResumeStart(profile_id=root));key=cv['resume_id']
        cv=resumes.save(key,ResumeSave(expected_version=1,title='Second',document=cv['document'],presentation=Presentation(color='#123456')))
        with TestClient(app) as client:
            endpoint='/api/resumes/'+key+'/history'
            assert [v['version'] for v in client.get(endpoint).json()['versions']]==[2,1]
            assert client.get(endpoint+'/1/preview').status_code==200
            original=resumes.read(key)
            real_write=resumes.write
            def fail_after_write(*args,**kwargs):
                real_write(*args,**kwargs)
                raise RuntimeError('simulate transaction failure')
            with patch.object(resumes,'write',side_effect=fail_after_write):
                try:history.restore(key,ResumeRestore(expected_version=2,target_version=1,event_id='rollback'))
                except RuntimeError:pass
                else:raise AssertionError('Expected rollback')
            assert resumes.read(key)==original
            assert [v['version'] for v in history.listing(key)['versions']]==[2,1]
            payload={'expected_version':2,'target_version':1,'event_id':'restore'}
            response=client.post(endpoint+'/restore',json=payload);assert response.status_code==200,response.text
            assert response.json()['version']==3
            assert client.post(endpoint+'/restore',json=payload).json()['version']==3
            assert len(client.get(endpoint).json()['versions'])==3
            assert client.post(endpoint+'/restore',json={**payload,'event_id':'stale'}).status_code==409
    finally:
        with database.connect() as c,c.transaction():
            if key:
                c.execute("DELETE FROM kltn_app.records WHERE kind='resume_history' AND payload->>'resume_id'=%s",(key,))
                c.execute("DELETE FROM kltn_app.records WHERE kind='resume_drafts' AND record_id=%s",(key,))
            c.execute('DELETE FROM kltn_app.profile_heads WHERE root_id=%s',(root,))
            c.execute('DELETE FROM kltn_app.profile_revisions WHERE root_id=%s',(root,))
            c.execute("DELETE FROM kltn_app.records WHERE kind='profiles' AND record_id=%s",(root,))


if __name__=='__main__':main()
