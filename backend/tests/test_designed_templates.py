"""New layouts preserve the AI data contract through form, publication and PDF."""
from copy import deepcopy
import unittest
from unittest.mock import patch
from bs4 import BeautifulSoup
from backend.tests import test_admin as admin_fixtures
from backend.app.schemas.template_design import SECTION_KEYS
from backend.app.services import template_catalog, profile_drafts, resumes
from backend.app.services.cv_templates import metadata, synthetic_document
from backend.app.services.cv_renderer import render_html, render_pdf
from backend.app.schemas.resume import Presentation, ResumeStart, ResumePublish
from backend.app.schemas.profile_draft import DraftSave, DraftConfirm
from backend.tests.test_simple_reference_templates import fixture
from backend.app.core.workspace import workspace


class DesignedTemplateTests(unittest.TestCase):
    setUp = admin_fixtures.AdministrationTests.setUp
    register = admin_fixtures.AdministrationTests.register

    def payload(self, **changes):
        return {**dict(name='Bố cục mới độc lập', category='modern', color='#713e95', font='serif', enabled=True,
                      design=dict(layout='two-column', sidebar_position='right', sidebar_width=30,
                                  main_sections=['summary', 'experience', 'project', 'education', 'involvement'],
                                  sidebar_sections=['skills', 'certifications', 'awards', 'references'],
                                  heading_style='filled', header_align='center', show_photo=False)), **changes}

    def create(self, **changes):
        response = self.a.post('/api/admin/templates', json=self.payload(**changes))
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def test_new_layout_has_no_base_and_preview_is_not_persisted(self):
        before = self.a.get('/api/admin/templates').json()
        preview = self.a.post('/api/admin/templates/preview', json=self.payload())
        self.assertEqual(preview.status_code, 200, preview.text)
        self.assertIn('designed-columns', preview.json()['html'])
        self.assertEqual(self.a.get('/api/admin/templates').json(), before)
        item = self.create()
        self.assertIsNone(item['base_template'])
        self.assertEqual(item['renderer'], 'designed')
        self.assertFalse(item['has_photo'])
        self.assertEqual(item['form_sections'][0], 'contact')
        self.assertEqual(set(item['form_sections'][1:]), set(SECTION_KEYS))
        self.assertEqual(metadata(item['id'])['design'], item['design'])
        self.assertTrue(any(t['id']==item['id'] for t in self.b.get('/api/cv/templates').json()))
        thumb = self.b.get(item['thumbnail'])
        self.assertEqual(thumb.status_code, 200)
        self.assertIn('image/svg+xml', thumb.headers['content-type'])
        self.assertIn('#713e95', thumb.text)

    def test_schema_rejects_missing_duplicate_unknown_sections_and_css_injection(self):
        for changes in [dict(main_sections=['education']),
                        dict(main_sections=['summary','experience','project','education','skills']),
                        dict(main_sections=['summary','experience','project','education','fake']),
                        dict(sidebar_width=80), dict(margin_mm=0), dict(layout='one-column'),
                        dict(heading_style='</style><script>1</script>'), dict(extra_css='bad')]:
            data=self.payload(); data['design'].update(changes)
            self.assertEqual(self.a.post('/api/admin/templates', json=data).status_code, 422, changes)
        data=self.payload(base_template='simple')
        self.assertEqual(self.a.post('/api/admin/templates', json=data).status_code, 422)
        member=self.register(self.b)
        self.assertEqual(self.b.post('/api/admin/templates/preview', json=self.payload()).status_code, 403)
        self.a.headers.pop('X-KLTN-CSRF')
        self.assertEqual(self.a.post('/api/admin/templates/preview', json=self.payload()).status_code, 403)

    def test_rendering_keeps_facts_refs_and_contact_fields_without_executing_markup(self):
        item=self.create()
        doc=synthetic_document(); doc.contact.city='Hà Nội'; doc.contact.country='Việt Nam'
        doc.contact.interests='<script>unsafe</script>'; doc.contact.additional_info='Thông tin thêm'
        initial=doc.model_dump()
        html=render_html(doc,item['id']); soup=BeautifulSoup(html,'html.parser')
        self.assertEqual(soup.select('script'), [])
        self.assertIn('<script>unsafe</script>',soup.get_text())
        self.assertIn('Hà Nội',soup.get_text());self.assertIn('Thông tin thêm',soup.get_text())
        for section in doc.sections:
            for entry in section.entries:
                for value in [entry.title, entry.subtitle, entry.period]+[b.text for b in entry.bullets]:
                    if value:self.assertIn(value,soup.get_text(' ',strip=True))
        self.assertEqual(doc.model_dump(),initial)
        self.assertTrue(all(b.source_refs for s in doc.sections for e in s.entries for b in e.bullets))
        self.assertEqual([node['class'][-1] for node in soup.select('.designed-main>.designed-section')],
                         ['section-summary','section-experience','section-project','section-education','section-involvement'])
        self.assertEqual(soup.select('.designed-photo'),[])
        update=self.payload(expected_revision=1)
        update['design'].update(layout='one-column', main_sections=list(SECTION_KEYS), sidebar_sections=[], show_photo=True)
        result=self.a.put('/api/admin/templates/'+item['id'],json=update)
        self.assertEqual(result.status_code,200,result.text)
        soup=BeautifulSoup(render_html(doc,item['id']),'html.parser')
        self.assertEqual(len(soup.select('.designed-photo')),1)
        self.assertFalse(soup.select('.designed-sidebar'))

    def test_form_ai_input_publication_and_export_stay_renderer_independent(self):
        item=self.create()
        member=self.register(self.b)
        with workspace(member['user_id']):
            opts=Presentation(template=item['id'],template_version=3,color=item['color'],font=item['font'])
            draft=profile_drafts.start(presentation=opts)
            profile=fixture()
            saved=profile_drafts.save(draft['draft_id'],DraftSave(expected_version=1,profile=profile,presentation=opts))
            confirmed=profile_drafts.confirm(draft['draft_id'],DraftConfirm(expected_version=saved['version'],event_id='designed-confirm'))
            with patch('ai.llm.ollama_client.request_structured',side_effect=AssertionError('No AI required for layout')):
                resume=resumes.start(ResumeStart(profile_id=confirmed['confirmed_profile_id'],presentation=opts,refine_form=False))
            before=deepcopy(resume['document'])
            self.assertTrue(all(b['source_refs'] for s in before['sections'] for e in s['entries'] for b in e['bullets']))
            published=resumes.publish(resume['resume_id'],ResumePublish(expected_version=resume['version'],event_id='designed-publish'))
            from backend.app.db import workflow_repository
            stored=workflow_repository.get('cv_versions',published['cv_id'])
            self.assertEqual(before,stored['document'])
            from backend.app.schemas.cv import CVDocument
            doc=CVDocument.model_validate(stored['document'])
            template_catalog.delete(self.admin_id,item['id'],1)
            import pymupdf
            with pymupdf.open(stream=render_pdf(doc,item['id'],opts.model_dump()),filetype='pdf') as pdf:
                text=' '.join(' '.join(p.get_text() for p in pdf).split())
                self.assertIn(profile.contact.full_name,text)
                self.assertIn('GPA: 3.4/4.0',text)
                self.assertIn('Chứng chỉ kiểm thử',text)
            self.assertEqual(resumes.read(resume['resume_id'])['document'],before)

    def test_long_new_layout_exports_last_bullet_in_both_column_modes(self):
        import pymupdf
        document=synthetic_document()
        section=next(s for s in document.sections if s.kind=='experience')
        bullet=section.entries[0].bullets[0]
        section.entries=section.entries[:1]
        section.entries[0].bullets=[bullet.model_copy(update={'text':f'Mục {i}: Kinh nghiệm xử lý dữ liệu tiếng Việt và Python.'}) for i in range(1,71)]
        for mode in ['one-column','two-column']:
            with self.subTest(mode=mode):
                payload=self.payload()
                if mode=='one-column':
                    payload['design'].update(layout=mode,main_sections=list(SECTION_KEYS),sidebar_sections=[])
                item=template_catalog.save(self.admin_id,payload)
                with pymupdf.open(stream=render_pdf(document,item['id']),filetype='pdf') as pdf:
                    text=' '.join(' '.join(p.get_text() for p in pdf).split())
                    self.assertGreater(len(pdf),1)
                    self.assertIn('Mục 70:',text)
                    self.assertIn('Nguyễn Minh An',text)


if __name__=='__main__':unittest.main()
