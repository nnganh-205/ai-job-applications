"""Isolated form-draft integration checks. Never uses the production DATABASE_URL."""
import os
from unittest.mock import patch


def main():
    url=os.environ.get('KLTN_TEST_DATABASE_URL')
    if not url:
        raise SystemExit('Set KLTN_TEST_DATABASE_URL to a restored disposable database')
    os.environ.update(KLTN_STORAGE='postgres',DATABASE_URL=url)
    from backend.app.db import database, profile_revision_repository as revisions, profile_repository as profiles
    from backend.app.services import profile_drafts as drafts
    from backend.app.schemas.profile_draft import DraftSave,DraftConfirm
    from backend.app.schemas.profile import MasterProfile
    from fastapi.testclient import TestClient
    from backend.app.main import app
    ids=[];roots=[]
    try:
        with TestClient(app) as client:
            d=client.post('/api/profile-drafts',json={}).json();ids.append(d['draft_id'])
            p=MasterProfile.model_validate(d['profile']);p.contact.full_name='Integration fixture'
            response=client.put('/api/profile-drafts/'+d['draft_id'],json={'expected_version':1,'profile':p.model_dump(mode='json')})
            assert response.status_code==200,response.text
            d=response.json()
            assert client.put('/api/profile-drafts/'+d['draft_id'],json={'expected_version':1,'profile':p.model_dump(mode='json')}).status_code==409
            approval={'expected_version':d['version'],'event_id':'integration-confirm'}
            response=client.post('/api/profile-drafts/'+d['draft_id']+'/confirm',json=approval)
            assert response.status_code==200,response.text
            result=response.json();root=result['confirmed_profile_id'];roots.append(root)
            assert client.post('/api/profile-drafts/'+d['draft_id']+'/confirm',json=approval).json()==result
            edit=drafts.start(root);ids.append(edit['draft_id'])
            p.contact.full_name='Changed fixture'
            edit=drafts.save(edit['draft_id'],DraftSave(expected_version=1,profile=p))
            original_write=drafts.write
            with patch.object(drafts,'write',side_effect=RuntimeError('Simulated draft write failure')):
                try:
                    drafts.confirm(edit['draft_id'],DraftConfirm(expected_version=edit['version'],event_id='rollback'))
                except RuntimeError:pass
                else:raise AssertionError('Expected failure')
            assert revisions.current_revision(root)==root,'Revision must rollback with draft'
            assert drafts.read(edit['draft_id'])['status']=='editing'
            confirmed=drafts.confirm(edit['draft_id'],DraftConfirm(expected_version=edit['version'],event_id='publish'))
            assert revisions.current_revision(root)==confirmed['confirmed_profile_id']
            assert profiles.load_profile_record(root).profile.contact.full_name=='Integration fixture'
            for path in ['/workspace/profile','/workspace/profile/'+edit['draft_id']+'/contact']:
                assert client.get(path).status_code==200
            assert client.get('/api/does-not-exist').status_code==404
            assert client.get('/assets/missing.js').status_code==404
    finally:
        with database.connect() as c,c.transaction():
            for root in roots:
                rows=c.execute('SELECT revision_id FROM kltn_app.profile_revisions WHERE root_id=%s',(root,)).fetchall()
                c.execute('DELETE FROM kltn_app.profile_revisions WHERE root_id=%s',(root,))
                c.execute('DELETE FROM kltn_app.profile_heads WHERE root_id=%s',(root,))
                for row in rows:c.execute("DELETE FROM kltn_app.records WHERE kind='profiles' AND record_id=%s",(row['revision_id'],))
            for key in ids:c.execute("DELETE FROM kltn_app.records WHERE kind='profile_drafts' AND record_id=%s",(key,))


if __name__=='__main__':main()
