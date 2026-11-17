import unittest
from backend.tests import test_profile_drafts
from backend.app.services import resumes
from backend.app.schemas.resume import ResumeStart,ResumeSave,ResumePublish,Presentation
from backend.app.schemas.cv import CVDocument
from backend.app.schemas.profile import MasterProfile
from backend.app.db import profile_repository as profiles,workflow_repository as records
from backend.app.db.profile_revision_repository import RevisionConflict


class ResumeTests(unittest.TestCase):
    setUp=test_profile_drafts.ProfileDraftTests.setUp

    def create(self):
        profile=MasterProfile(contact={'full_name':'Fixture Candidate'},experience=[],project=[{'id':'proj1','project_name':'Backend','description':['Built Python API with 20 endpoints.','Maintained PostgreSQL database.']}],education=[],involvement=[],skills=[])
        profiles.save_master_profile('fixture',profile,profiles.DEFAULT_STORAGE_DIR)
        return resumes.start(ResumeStart(profile_id='fixture'))

    def test_draft_does_not_publish(self):
        draft=self.create()
        self.assertEqual(records.list_kind('cv_versions'),[])
        self.assertEqual(resumes.read(draft['resume_id']),draft)

    def test_publish_retry_and_immutability(self):
        draft=self.create();req=ResumePublish(expected_version=1,event_id='publish1')
        result=resumes.publish(draft['resume_id'],req)
        self.assertEqual(resumes.publish(draft['resume_id'],req),result)
        stored=records.get('cv_versions',result['cv_id'])
        doc=CVDocument.model_validate(draft['document']);doc.sections[0].entries[0].bullets.pop()
        resumes.save(draft['resume_id'],ResumeSave(expected_version=1,title='Edited',document=doc,presentation=Presentation(color='#123456')))
        self.assertEqual(records.get('cv_versions',result['cv_id']),stored)
        with self.assertRaises(RevisionConflict):resumes.publish(draft['resume_id'],ResumePublish(expected_version=1,event_id='stale'))

    def test_numbers_and_fake_refs_rejected(self):
        draft=self.create();doc=CVDocument.model_validate(draft['document']);doc.sections[0].entries[0].bullets[0].text='Built Python API with 200 endpoints.'
        with self.assertRaises(ValueError):resumes.save(draft['resume_id'],ResumeSave(expected_version=1,title='Bad',document=doc,presentation=Presentation()))
        doc=CVDocument.model_validate(draft['document']);doc.sections[0].entries[0].bullets[0].source_refs=['/fake']
        with self.assertRaises(ValueError):resumes.save(draft['resume_id'],ResumeSave(expected_version=1,title='Bad',document=doc,presentation=Presentation()))

    def test_duplicate_keeps_original_and_clears_publications(self):
        draft=self.create();resumes.publish(draft['resume_id'],ResumePublish(expected_version=1,event_id='publish'))
        original=resumes.read(draft['resume_id']);copy=resumes.duplicate(draft['resume_id'])
        self.assertEqual(original,resumes.read(draft['resume_id']))
        self.assertNotEqual(copy['resume_id'],draft['resume_id'])
        self.assertEqual(copy['publications'],{})
        self.assertIsNone(copy['latest_cv_id'])

    def test_presentation_is_separate_from_content(self):
        draft=self.create();changed=resumes.save(draft['resume_id'],ResumeSave(expected_version=1,title=draft['title'],document=draft['document'],presentation=Presentation(template='classic',font='serif',font_size=11)))
        self.assertEqual(draft['document'],changed['document'])
        with self.assertRaises(RevisionConflict):resumes.save(draft['resume_id'],ResumeSave(expected_version=1,title='Stale',document=draft['document'],presentation=Presentation()))

    def test_pdf_preserves_vietnamese_and_last_bullet_across_pages(self):
        import pymupdf
        from backend.app.services.cv_renderer import render_pdf
        doc=CVDocument.model_validate(self.create()['document'])
        doc.contact.full_name='Nguyễn Văn Kiểm Thử'
        bullet=doc.sections[0].entries[0].bullets[0]
        doc.sections[0].entries[0].bullets=[bullet.model_copy(update={'text':f'Mục {i}: Kiểm thử dữ liệu tiếng Việt với Python và PostgreSQL.'}) for i in range(1,90)]
        for template,font in [('ats','sans'),('classic','serif')]:
            with self.subTest(template=template):
                content=render_pdf(doc,template,Presentation(template=template,font=font,font_size=11).model_dump())
                with pymupdf.open(stream=content,filetype='pdf') as pdf:
                    text=' '.join(' '.join(p.get_text() for p in pdf).split())
                    self.assertGreater(len(pdf),1)
                    self.assertIn('Nguyễn Văn Kiểm Thử',text)
                    self.assertIn('Mục 89',text)
