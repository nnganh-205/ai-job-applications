from copy import deepcopy
from unittest.mock import patch
from backend.tests.test_resumes import ResumeTests as _ResumeTests
from backend.app.services import resumes, resume_editing as editing
from backend.app.schemas.resume import ResumeEditStart, ResumeEditComplete, ResumePublish, ResumeSave, Presentation
from backend.app.schemas.profile_draft import DraftSave
from backend.app.schemas.cv import CVDocument
from backend.app.schemas.profile import MasterProfile
from backend.app.db import profile_repository as profiles, workflow_repository as records
from backend.app.db.profile_revision_repository import RevisionConflict
import unittest


class ResumeEditingTests(unittest.TestCase):
    setUp = _ResumeTests.setUp
    create = _ResumeTests.create

    def begin(self, cv):
        return editing.begin(cv['resume_id'], ResumeEditStart(expected_version=cv['version']))

    def save(self, cv, draft, **contact):
        profile = MasterProfile.model_validate(draft['profile'])
        for key, value in contact.items():
            setattr(profile.contact, key, value)
        return editing.save(cv['resume_id'], DraftSave(expected_version=draft['version'], profile=profile))

    def finish(self, cv, draft, event='complete'):
        return editing.complete(cv['resume_id'], ResumeEditComplete(draft_id=draft['draft_id'], expected_version=draft['version'], event_id=event))

    def test_project_stack_and_repository_do_not_become_work_bullets_on_reopen(self):
        from backend.tests.test_project_metadata import project_profile
        from backend.app.schemas.resume import ResumeStart
        profile=project_profile()
        profiles.save_master_profile('metadata_fixture',profile,profiles.DEFAULT_STORAGE_DIR)
        cv=resumes.start(ResumeStart(profile_id='metadata_fixture'))
        draft=self.begin(cv)
        entry=draft['profile']['project'][0]
        self.assertEqual(entry['description'],profile.project[0].description)
        self.assertEqual(entry['technologies'],profile.project[0].technologies)
        self.assertEqual(entry['github_url'],profile.project[0].github_url)

    def test_legacy_standalone_tool_bullets_do_not_block_contact_edit(self):
        from ai.agents.cv_agent import HIDDEN_SOURCE_FIELDS
        from backend.app.schemas.resume import ResumeStart
        profile = MasterProfile(contact={'full_name':'Fixture'}, experience=[{
            'id':'job', 'job_title':'Developer', 'company':'ABC',
            'description':['Built APIs with Python.'], 'technologies_used':['Python', 'Docker']}],
            project=[], education=[], involvement=[], skills=[])
        profiles.save_master_profile('fixture',profile,profiles.DEFAULT_STORAGE_DIR)
        with patch.dict(HIDDEN_SOURCE_FIELDS, {'experience':set()}):
            cv = resumes.start(ResumeStart(profile_id='fixture'))
        self.assertEqual(len(cv['document']['sections'][0]['entries'][0]['bullets']),3)
        draft = self.save(cv,self.begin(cv),full_name='Edited')
        result = self.finish(cv,draft)
        self.assertEqual([b['text'] for b in result['document']['sections'][0]['entries'][0]['bullets']],['Built APIs with Python.'])

    def test_legacy_project_tools_reopen_as_one_grounded_line(self):
        cv = self.create()
        source = profiles.load_profile_record('fixture', profiles.DEFAULT_STORAGE_DIR)
        source.profile.project[0].technologies = ['Docker','Git']
        profiles.save_master_profile('legacy_fixture', source.profile, profiles.DEFAULT_STORAGE_DIR)
        for key in ['document','baseline']:
            cv[key]['source_profile_revision_id'] = 'legacy_fixture'
            cv[key]['sections'][0]['entries'][0]['bullets'] += [
                {'text':name,'source_refs':[f'/project/0/technologies/{index}']}
                for index,name in enumerate(['Docker','Git'])]
        resumes.write(cv)
        result = self.finish(cv,self.save(cv,self.begin(cv),full_name='Edited'))
        texts = [b['text'] for b in result['document']['sections'][0]['entries'][0]['bullets']]
        self.assertEqual(texts[-1],'Docker, Git')
        self.assertNotIn('Docker',texts)

    def test_reopen_reuses_saved_draft_even_after_reload(self):
        cv = self.create(); first = self.begin(cv)
        saved = self.save(cv, first, phone='0900000000')
        self.assertEqual(self.begin(cv), saved)
        self.assertEqual(editing.read(cv['resume_id']), saved)
        self.assertEqual(resumes.read(cv['resume_id'])['version'], 1)

    def test_complete_keeps_identity_design_publications_and_shared_profile(self):
        cv = self.create()
        cv = resumes.save(cv['resume_id'], ResumeSave(expected_version=1, title='My existing CV', document=cv['document'], presentation=Presentation(template='classic', font='serif', color='#123456', font_size=12, line_height=1.7)))
        publication = resumes.publish(cv['resume_id'], ResumePublish(expected_version=cv['version'], event_id='publish'))
        published = deepcopy(records.get('cv_versions', publication['cv_id']))
        original = profiles.load_profile_record('fixture', profiles.DEFAULT_STORAGE_DIR).model_dump()
        draft = self.save(cv, self.begin(cv), full_name='Edited Candidate')
        result = self.finish(cv, draft)
        self.assertEqual(result['resume_id'], cv['resume_id'])
        self.assertEqual(result['version'], cv['version'] + 1)
        self.assertEqual(result['presentation'], cv['presentation'])
        self.assertEqual(result['title'], cv['title'])
        self.assertEqual(result['document']['contact']['full_name'], 'Edited Candidate')
        self.assertEqual(len(resumes.library()), 1)
        self.assertEqual(records.get('cv_versions', publication['cv_id']), published)
        self.assertEqual(profiles.load_profile_record('fixture', profiles.DEFAULT_STORAGE_DIR).model_dump(), original)
        self.assertEqual(self.finish(cv, draft)['version'], result['version'])
        resumes.validate_document(result, CVDocument.model_validate(result['document']))

    def test_current_approved_merged_bullet_survives_open_and_contact_edit(self):
        cv = self.create(); old = deepcopy(cv['document'])
        merged = dict(text='Built Python API with 20 endpoints and maintained PostgreSQL database.', source_refs=[ref for b in old['sections'][0]['entries'][0]['bullets'] for ref in b['source_refs']])
        originals = deepcopy(old['sections'][0]['entries'][0]['bullets'])
        cv['document']['sections'][0]['entries'][0]['bullets'] = [merged]
        cv['writer_approvals'] = [dict(section='project', entry_id='proj1', original=originals, proposed=[merged])]
        resumes.write(cv)
        draft = self.begin(cv)
        self.assertEqual(draft['profile']['project'][0]['description'], [merged['text']])
        draft = self.save(cv, draft, full_name='Contact changed only')
        result = self.finish(cv, draft)
        self.assertEqual([b['text'] for b in result['document']['sections'][0]['entries'][0]['bullets']], [merged['text']])
        self.assertEqual(result['edit_history'][0]['document'], cv['document'])

    def test_stale_save_and_complete_cannot_overwrite(self):
        cv = self.create(); first = self.begin(cv); saved = self.save(cv, first, phone='1')
        with self.assertRaises(RevisionConflict): self.save(cv, first, phone='2')
        with self.assertRaises(RevisionConflict): self.finish(cv, first)
        resumes.save(cv['resume_id'], ResumeSave(expected_version=1, title='Other tab', document=cv['document'], presentation=Presentation()))
        with self.assertRaises(RevisionConflict): self.finish(cv, saved)
        self.assertEqual(editing.read(cv['resume_id'])['profile']['contact']['phone'], '1')

    def test_failed_complete_keeps_cv_and_saved_draft(self):
        cv = self.create(); draft = self.save(cv, self.begin(cv), phone='3')
        before = deepcopy(resumes.read(cv['resume_id']))
        with patch.object(profiles, 'save_master_profile', side_effect=RuntimeError('storage unavailable')):
            with self.assertRaises(RuntimeError): self.finish(cv, draft)
        self.assertEqual(resumes.read(cv['resume_id']), before)
        result = self.finish(cv, draft)
        self.assertEqual(result['document']['contact']['phone'], '3')

    def test_new_entries_receive_stable_ids_and_old_cv_can_reopen(self):
        cv = self.create(); draft = self.begin(cv)
        profile = MasterProfile.model_validate(draft['profile'])
        from backend.app.schemas.profile import Project
        profile.project.append(Project(project_name='New project', description=['Built a web page.']))
        draft = editing.save(cv['resume_id'], DraftSave(expected_version=draft['version'], profile=profile))
        result = self.finish(cv, draft)
        new_draft = self.begin(result)
        self.assertEqual(len(new_draft['profile']['project']), 2)
        self.assertTrue(new_draft['profile']['project'][1]['id'])
        self.assertNotEqual(new_draft['draft_id'], draft['draft_id'])

    def test_duplicate_does_not_share_pending_edit(self):
        cv = self.create(); self.begin(cv)
        copy = resumes.duplicate(cv['resume_id'])
        self.assertNotIn('source_edit', copy)
        self.assertNotEqual(self.begin(cv)['draft_id'], self.begin(copy)['draft_id'])

    def test_metadata_edit_does_not_reintroduce_omitted_source_bullets(self):
        cv = self.create()
        source = profiles.load_profile_record('fixture', profiles.DEFAULT_STORAGE_DIR)
        # Tools are valid source context, but intentionally omitted on this CV.
        source.profile.project[0].technologies = ['Python']
        with patch.object(profiles, 'load_profile_record', return_value=source):
            draft = self.begin(cv)
        profile = MasterProfile.model_validate(draft['profile'])
        profile.project[0].project_name = 'Renamed project'
        draft = editing.save(cv['resume_id'], DraftSave(expected_version=draft['version'], profile=profile))
        result = self.finish(cv, draft)
        bullets = result['document']['sections'][0]['entries'][0]['bullets']
        self.assertEqual([b['text'] for b in bullets], [b['text'] for b in cv['document']['sections'][0]['entries'][0]['bullets']])

# Only the lifecycle cases in this module; the legacy suite runs separately.
del _ResumeTests
