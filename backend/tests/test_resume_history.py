import unittest
from copy import deepcopy
from unittest.mock import patch
from backend.tests.test_resumes import ResumeTests as Fixture
from backend.app.services import resumes, resume_history as history
from backend.app.schemas.resume import ResumeRestore, ResumeSave, Presentation, ResumePublish, ResumeEditStart
from backend.app.services import resume_editing
from backend.app.db import workflow_repository as records
from backend.app.db.profile_revision_repository import RevisionConflict

class HistoryTests(unittest.TestCase):
    setUp=Fixture.setUp
    create=Fixture.create
    def change(self,cv,color='#123456'):
        return resumes.save(cv['resume_id'],ResumeSave(expected_version=cv['version'],title='Changed',document=cv['document'],presentation=Presentation(color=color)))
    def restore(self,cv,version=1,**extra):
        return history.restore(cv['resume_id'],ResumeRestore(expected_version=cv['version'],target_version=version,event_id='restore',**extra))
    def test_all_saved_versions_have_immutable_content_and_design(self):
        cv=self.create();key=cv['resume_id'];initial=history.selected(key,1)
        cv=self.change(cv);cv=self.change(cv,'#abcdef')
        self.assertEqual([v['version'] for v in history.listing(key)['versions']],[3,2,1])
        self.assertEqual(history.selected(key,1),initial)
        self.assertEqual(history.selected(key,2)['presentation']['color'],'#123456')
    def test_restore_new_version_keeps_old_versions_and_published_pdf(self):
        cv=self.create();key=cv['resume_id'];published=resumes.publish(key,ResumePublish(expected_version=1,event_id='pdf'))
        pdf=deepcopy(records.get('cv_versions',published['cv_id']))
        changed=self.change(cv);restored=self.restore(changed)
        self.assertEqual(restored['version'],3);self.assertEqual(restored['resume_id'],key)
        self.assertEqual(restored['document'],cv['document']);self.assertEqual(restored['presentation'],cv['presentation'])
        self.assertEqual(history.selected(key,2)['title'],'Changed')
        self.assertEqual(records.get('cv_versions',published['cv_id']),pdf)
        self.assertEqual(self.restore(changed)['version'],3)
        self.assertEqual(len(resumes.library()),1)
    def test_stale_and_foreign_version_cannot_restore(self):
        cv=self.create();changed=self.change(cv)
        with self.assertRaises(RevisionConflict): self.restore(cv)
        with self.assertRaises(LookupError): self.restore(changed,999)
    def test_pending_draft_requires_explicit_version_and_is_preserved(self):
        cv=self.change(self.create());key=cv['resume_id']
        packet=resume_editing.begin(key,ResumeEditStart(expected_version=2))
        with self.assertRaises(RevisionConflict): self.restore(cv)
        result=self.restore(cv,editing_draft_version=packet['version'])
        self.assertEqual(result['archived_source_edits'][0],packet)
        self.assertEqual(history.archived_draft(key,packet['draft_id']),packet)
        with self.assertRaises(LookupError): history.archived_draft(key,'draft_missing')
        self.assertIsNone(history.listing(key)['editing_draft'])
    def test_failed_restore_keeps_current_and_draft(self):
        cv=self.change(self.create());before=resumes.read(cv['resume_id'])
        with patch.object(resumes,'write',side_effect=RuntimeError('failure')):
            with self.assertRaises(RuntimeError):self.restore(cv)
        self.assertEqual(resumes.read(cv['resume_id']),before)
    def test_legacy_missing_versions_are_not_fabricated(self):
        cv=self.create();key=cv['resume_id']
        # Simulate a legacy project with no saved history before current v5.
        cv['version']=5;records.put('resume_drafts',key,cv)
        self.assertEqual([v['version'] for v in history.listing(key)['versions']],[5,1])
        with self.assertRaises(LookupError):history.selected(key,3)

    def test_approved_ai_wording_can_be_restored_with_its_validation_metadata(self):
        from backend.tests.test_cv_writer import EditorWriterTests
        from backend.app.services import resume_writer
        from backend.app.schemas.cv import CVDocument
        cv=self.create();proposal=EditorWriterTests.proposal(self,cv)
        approved=resume_writer.apply(cv['resume_id'],resume_writer.ResumeWriterApply(expected_version=1,proposal_id=proposal['proposal_id'],selected=[0]))
        changed=self.change(approved)
        restored=self.restore(changed,version=2)
        self.assertEqual(restored['document'],approved['document'])
        self.assertEqual(restored['writer_approvals'],approved['writer_approvals'])
        resumes.validate_document(restored,CVDocument.model_validate(restored['document']))

del Fixture
