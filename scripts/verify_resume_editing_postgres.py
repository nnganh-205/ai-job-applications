"""CV editing transaction/API verification on the disposable restore database."""
import os
from uuid import uuid4
from copy import deepcopy
from unittest.mock import patch


def main():
    url = os.environ.get('KLTN_TEST_DATABASE_URL', '')
    if url.rsplit('/', 1)[-1] != 'kltn_restore_verify':
        raise SystemExit('Use disposable kltn_restore_verify only')
    os.environ.update(KLTN_STORAGE='postgres', DATABASE_URL=url, KLTN_WORKER_ENABLED='0')
    from backend.app.db import database, profile_repository as profiles
    from backend.app.schemas.profile import MasterProfile
    from backend.app.schemas.resume import ResumeStart, ResumeEditComplete
    from backend.app.services import resumes, resume_editing as editing
    from backend.app.main import app
    from fastapi.testclient import TestClient
    root = 'edit_fixture_' + uuid4().hex
    key = None
    try:
        profiles.save_master_profile(root, MasterProfile(contact={'full_name':'Lifecycle Fixture'}, experience=[], project=[{'id':'proj_fixture','project_name':'Fixture project','description':['Built Python APIs.']}], education=[], involvement=[], skills=[]), profiles.DEFAULT_STORAGE_DIR)
        cv = resumes.start(ResumeStart(profile_id=root)); key = cv['resume_id']
        with TestClient(app) as client:
            endpoint = '/api/resumes/' + key + '/source-edit'
            first = client.post(endpoint, json={'expected_version':1}); assert first.status_code == 200, first.text
            draft = first.json(); profile = deepcopy(draft['profile']); profile['contact']['phone']='0900000000'
            saved = client.put(endpoint, json={'expected_version':1,'profile':profile}); assert saved.status_code == 200, saved.text
            draft = saved.json()
            assert client.post(endpoint,json={'expected_version':1}).json() == draft
            assert client.get(endpoint).json() == draft
            req = ResumeEditComplete(draft_id=draft['draft_id'],expected_version=draft['version'],event_id='complete')
            before = resumes.read(key)
            with database.connect() as c:
                count = c.execute("SELECT count(*) n FROM kltn_app.records WHERE kind='profiles'").fetchone()['n']
            with patch.object(resumes,'write',side_effect=RuntimeError('simulate final write failure')):
                try: editing.complete(key,req)
                except RuntimeError: pass
                else: raise AssertionError('Expected rollback')
            assert resumes.read(key) == before
            with database.connect() as c:
                assert c.execute("SELECT count(*) n FROM kltn_app.records WHERE kind='profiles'").fetchone()['n'] == count
            response = client.post(endpoint+'/complete',json=req.model_dump()); assert response.status_code == 200, response.text
            result = response.json(); assert result['resume_id']==key and result['version']==2
            assert result['document']['contact']['phone']=='0900000000'
            assert client.post(endpoint+'/complete',json=req.model_dump()).json()['version']==2
            assert client.put(endpoint,json={'expected_version':1,'profile':profile}).status_code==409
            assert client.get('/api/resumes/'+key+'/preview').status_code==200
    finally:
        with database.connect() as c,c.transaction():
            sources = c.execute("SELECT record_id FROM kltn_app.records WHERE kind='profiles' AND (record_id=%s OR payload->'evidence' @> %s::jsonb)", (root, __import__('json').dumps([{'source_id':key or 'none'}]))).fetchall()
            for row in sources:
                source = row['record_id']
                if source != root and not source.startswith('cvlocal_'): continue
                c.execute('DELETE FROM kltn_app.profile_heads WHERE root_id=%s',(source,))
                c.execute('DELETE FROM kltn_app.profile_revisions WHERE root_id=%s',(source,))
                c.execute("DELETE FROM kltn_app.records WHERE kind='profiles' AND record_id=%s",(source,))
            if key:
                c.execute("DELETE FROM kltn_app.records WHERE kind='resume_history' AND payload->>'resume_id'=%s",(key,))
                c.execute("DELETE FROM kltn_app.records WHERE kind='resume_drafts' AND record_id=%s",(key,))


if __name__ == '__main__': main()
