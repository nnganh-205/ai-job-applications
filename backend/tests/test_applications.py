import unittest
from unittest.mock import patch
from backend.tests import test_profile_drafts
from backend.app.services import applications
from backend.app.schemas.application import ApplicationUpdate
from backend.app.schemas.dashboard import JobPosting
from backend.app.schemas.profile import MasterProfile
from ai.agents.cv_agent import source_document
from backend.app.db import profile_repository as profiles,workflow_repository as records
from backend.app.db.profile_revision_repository import RevisionConflict


class ApplicationTests(unittest.TestCase):
    setUp=test_profile_drafts.ProfileDraftTests.setUp

    def setup_job(self):
        self.job=JobPosting(posting_id='posting_'+'a'*24,title='Fixture job',description='Python engineer role',source_name='fixture',external_id='fixture',imported_at='2026-11-09T00:00:00Z',content_hash='b'*64)
        patcher=patch.object(applications,'get_posting',return_value=self.job);patcher.start();self.addCleanup(patcher.stop)
        profile=MasterProfile(contact={},experience=[],project=[{'project_name':'Fixture','description':['Built Python services.']}],education=[],involvement=[],skills=[])
        profiles.save_master_profile('fixture_profile',profile,profiles.DEFAULT_STORAGE_DIR)
        self.cv='cv_'+'c'*32
        records.put('cv_versions',self.cv,{'document':source_document(profile,'fixture_profile').model_dump(mode='json')})

    def update(self,status,version=0,event='event',**extra):
        return applications.update(self.job.posting_id,ApplicationUpdate(status=status,expected_version=version,event_id=event,job_content_hash=self.job.content_hash,**extra))

    def test_open_source_is_not_a_submission(self):
        self.setup_job();data=self.update('opened_source',cv_id=self.cv)
        self.assertEqual(data['status'],'opened_source')
        self.assertEqual(data['profile_revision_id'],'fixture_profile')
        self.assertEqual(data['events'][0]['origin'],'user_link_activation')
        self.assertEqual(applications.read(self.job.posting_id),data)

    def test_reopening_does_not_downgrade_or_replace_submitted_cv(self):
        self.setup_job();self.update('applied',cv_id=self.cv)
        data=self.update('opened_source',version=1,event='reopen',cv_id=None)
        self.assertEqual(data['status'],'applied')
        self.assertEqual(data['cv_id'],self.cv)
        self.assertEqual(len(data['events']),2)

    def test_stale_and_reused_events_are_rejected(self):
        self.setup_job();first=self.update('saved')
        self.assertEqual(self.update('saved'),first)
        with self.assertRaises(RevisionConflict):self.update('applied')
        with self.assertRaises(RevisionConflict):self.update('applied',event='other')

    def test_changed_snapshot_and_missing_cv_are_rejected(self):
        self.setup_job()
        req=ApplicationUpdate(status='saved',expected_version=0,event_id='old',job_content_hash='d'*64)
        with self.assertRaises(RevisionConflict):applications.update(self.job.posting_id,req)
        with self.assertRaises(LookupError):self.update('applied',cv_id='cv_'+'f'*32)
        self.assertEqual(applications.read(self.job.posting_id)['version'],0)

    def test_cv_profile_mismatch_is_rejected(self):
        self.setup_job()
        with self.assertRaises(RevisionConflict):self.update('applied',cv_id=self.cv,profile_id='other_profile')
