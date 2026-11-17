import unittest
from copy import deepcopy
from backend.tests.test_resumes import ResumeTests as Fixture
from backend.app.services import resumes
from backend.app.services.cv_lineage import version_status,content_hash
from backend.app.schemas.resume import ResumePublish,ResumeSave,Presentation
from backend.app.schemas.cv import CVDocument
from backend.app.db import workflow_repository as records

class LineageTests(unittest.TestCase):
    setUp=Fixture.setUp
    create=Fixture.create
    def publish(self,cv):return resumes.publish(cv['resume_id'],ResumePublish(expected_version=cv['version'],event_id='publish'+str(cv['version'])))['cv_id']
    def test_design_change_does_not_mark_matching_content_stale(self):
        cv=self.create();published=self.publish(cv)
        resumes.save(cv['resume_id'],ResumeSave(expected_version=1,title=cv['title'],document=cv['document'],presentation=Presentation(color='#123456')))
        state=version_status(published)
        self.assertTrue(state['version_changed']);self.assertFalse(state['content_stale'])
        self.assertEqual(state['source_version'],1);self.assertEqual(state['current_version'],2)
    def test_content_change_is_stale_and_old_input_is_immutable(self):
        cv=self.create();published=self.publish(cv);original=deepcopy(records.get('cv_versions',published))
        document=CVDocument.model_validate(cv['document']);document.sections[0].entries[0].bullets.pop()
        cv=resumes.save(cv['resume_id'],ResumeSave(expected_version=1,title='Changed',document=document,presentation=Presentation()))
        self.assertTrue(version_status(published)['content_stale'])
        latest=self.publish(cv)
        self.assertEqual(version_status(published)['latest_published_cv_id'],latest)
        self.assertFalse(version_status(latest)['content_stale'])
        self.assertEqual(records.get('cv_versions',published),original)
        self.assertNotEqual(content_hash(cv['document']),content_hash(original['document']))
    def test_source_revision_and_jd_ids_do_not_change_visible_content_hash(self):
        cv=self.create();document=deepcopy(cv['document'])
        document['source_profile_revision_id']='other';document['job_analysis_id']='other'
        self.assertEqual(content_hash(document),content_hash(cv['document']))
    def test_pending_form_is_not_matching_input(self):
        from backend.app.services import resume_editing
        from backend.app.schemas.resume import ResumeEditStart
        cv=self.create();published=self.publish(cv)
        resume_editing.begin(cv['resume_id'],ResumeEditStart(expected_version=1))
        self.assertTrue(version_status(published)['has_editing_draft'])
        self.assertFalse(version_status(published)['content_stale'])
    def test_legacy_cv_without_library_is_still_pinned(self):
        cv=self.create();records.put('cv_versions','cv_legacy',{'document':cv['document']})
        state=version_status('cv_legacy')
        self.assertIsNone(state['current_version']);self.assertFalse(state['content_stale'])

del Fixture

class TailorLineageTests(unittest.TestCase):
    setUp=LineageTests.setUp
    create=LineageTests.create
    def test_tailor_draft_keeps_selected_cv_design_and_source(self):
        from unittest.mock import patch
        from types import SimpleNamespace
        from backend.app.services.assistant import dispatch
        from backend.app.schemas.cv import CVDocument,CVReview
        cv=self.create()
        cv=resumes.save(cv['resume_id'],ResumeSave(expected_version=1,title='Designed',document=cv['document'],presentation=Presentation(template='classic',color='#123456',font='serif',font_size=12,line_height=1.7)))
        published=resumes.publish(cv['resume_id'],ResumePublish(expected_version=2,event_id='source'))['cv_id']
        review=CVReview(items=[])
        result=SimpleNamespace(document=CVDocument.model_validate(cv['document']),review=review,session_id='a'*32)
        with patch('ai.graph.cv_workflow.start',return_value=result) as start:
            response=dispatch('tailor_cv',{'context':{'cv_id':published,'posting_id':'posting_'+'a'*24,'language':'vi'}},'task_'+'c'*32)
        self.assertEqual(start.call_args.args[0].cv_id,published)
        self.assertEqual(response['_draft']['presentation'],cv['presentation'])
        self.assertEqual(response['_draft']['source_cv_id'],published)
        self.assertEqual(response['cv_version']['source_version'],2)
        self.assertEqual(response['_draft']['document'],cv['document'])
