import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from backend.app.services import profile_drafts as drafts
from backend.app.schemas.profile_draft import DraftSave, DraftConfirm
from backend.app.schemas.profile import MasterProfile
from backend.app.db import profile_repository, workflow_repository, profile_revision_repository


class ProfileDraftTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.env = patch.dict(os.environ, {'KLTN_STORAGE': 'json'})
        self.env.start(); self.addCleanup(self.env.stop)
        for module, name, value in [(profile_repository,'DEFAULT_STORAGE_DIR',Path(self.tmp.name)/'profiles'), (workflow_repository,'DEFAULT_WORKFLOW_STORAGE',Path(self.tmp.name)/'workflows')]:
            patcher=patch.object(module,name,value);patcher.start();self.addCleanup(patcher.stop)

    def save(self,draft,name):
        data=MasterProfile.model_validate(draft['profile'])
        data.contact.full_name=name
        return drafts.save(draft['draft_id'],DraftSave(expected_version=draft['version'],profile=data))

    def confirm(self,draft,event='confirm'):
        return drafts.confirm(draft['draft_id'],DraftConfirm(expected_version=draft['version'],event_id=event))

    def test_draft_does_not_publish_and_survives_reload(self):
        draft=self.save(drafts.start(),'Test Candidate')
        self.assertEqual(drafts.read(draft['draft_id']),draft)
        self.assertEqual(profile_repository.list_profile_records(),[])

    def test_publish_is_idempotent_and_immutable(self):
        draft=self.save(drafts.start(),'Original')
        result=self.confirm(draft)
        self.assertEqual(self.confirm(draft),result)
        with self.assertRaises(profile_revision_repository.RevisionConflict):
            self.save(result,'Overwrite')
        record=profile_repository.load_profile_record(result['confirmed_profile_id'],profile_repository.DEFAULT_STORAGE_DIR)
        self.assertEqual(record.profile.contact.full_name,'Original')
        self.assertTrue(all(e.origin=='user_confirmation' for e in record.evidence))

    def test_stale_save_and_confirm_are_rejected(self):
        draft=drafts.start();self.save(draft,'Current')
        with self.assertRaises(profile_revision_repository.RevisionConflict):self.save(draft,'Stale')
        with self.assertRaises(profile_revision_repository.RevisionConflict):self.confirm(draft)

    def test_two_drafts_cannot_overwrite_same_head(self):
        original=self.confirm(self.save(drafts.start(),'Original'))['confirmed_profile_id']
        first=self.save(drafts.start(original),'First')
        stale=self.save(drafts.start(original),'Stale')
        published=self.confirm(first)['confirmed_profile_id']
        with self.assertRaises(profile_revision_repository.RevisionConflict):self.confirm(stale)
        self.assertEqual(profile_revision_repository.current_revision(original),published)
        self.assertEqual(profile_repository.load_profile_record(original,profile_repository.DEFAULT_STORAGE_DIR).profile.contact.full_name,'Original')
        current=profile_repository.load_profile_record(published,profile_repository.DEFAULT_STORAGE_DIR)
        self.assertEqual(current.profile.contact.full_name,'First')
        self.assertFalse(any('Original' in e.quote for e in current.evidence if e.field_path=='contact'))

    def test_no_change_reuses_revision(self):
        original=self.confirm(drafts.start())['confirmed_profile_id']
        result=self.confirm(drafts.start(original))
        self.assertEqual(result['confirmed_profile_id'],original)


if __name__=='__main__':unittest.main()
