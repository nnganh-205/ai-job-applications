import unittest
import os
import io
from pathlib import Path
from PIL import Image
from unittest.mock import patch
from bs4 import BeautifulSoup
from backend.tests import test_profile_drafts
from backend.tests.test_simple_reference_templates import fixture
from backend.app.services import profile_drafts, resumes
from backend.app.api.cv import templates
from backend.app.api.profile_drafts import form_preview
from backend.app.schemas.profile import MasterProfile
from backend.app.schemas.profile_draft import DraftSave, DraftConfirm, DraftPreview
from backend.app.schemas.resume import Presentation, ResumeStart


class TemplateFormFlowTests(unittest.TestCase):
    setUp=test_profile_drafts.ProfileDraftTests.setUp

    def test_selection_and_later_template_change_preserve_all_form_data(self):
        initial=Presentation(template='simple',template_version=3,color='#b54848')
        draft=profile_drafts.start(presentation=initial)
        self.assertEqual(draft['presentation']['template'],'simple')
        profile=fixture()
        from backend.app.services.assets import save_photo
        asset_env=patch.dict(os.environ,{'KLTN_ASSET_STORAGE':str(Path(self.tmp.name)/'assets')})
        asset_env.start();self.addCleanup(asset_env.stop)
        content=io.BytesIO();Image.new('RGB',(64,64),'white').save(content,format='PNG')
        asset=save_photo(content.getvalue())
        changed=Presentation(template='split',template_version=3,color='#e96b9b',photo_asset_id=asset['asset_id'])
        saved=profile_drafts.save(draft['draft_id'],DraftSave(expected_version=1,profile=profile,presentation=changed))
        reopened=profile_drafts.read(draft['draft_id'])
        self.assertEqual(reopened['presentation'],changed.model_dump(mode='json'))
        self.assertEqual(reopened['profile'],profile.model_dump(mode='json'))
        confirmed=profile_drafts.confirm(draft['draft_id'],DraftConfirm(expected_version=saved['version'],event_id='confirm-template-form'))
        with patch('ai.llm.ollama_client.request_structured',side_effect=AssertionError('Form export must not invoke AI')):
            resume=resumes.start(ResumeStart(profile_id=confirmed['confirmed_profile_id'],presentation=changed,refine_form=False))
        self.assertEqual(resume['presentation'],changed.model_dump(mode='json'))
        self.assertEqual(resume['document']['contact']['full_name'],profile.contact.full_name)
        self.assertEqual({s['kind'] for s in resume['document']['sections']},{'education','experience','project','skills','certifications','awards','references'})

    def test_preview_uses_selected_renderer_without_storing_or_calling_ai(self):
        before=profile_drafts.list_editing()
        for template in ('simple','clean','minimal','compact','executive','corporate','consultant','precision','modern','sidebar','metro','split','classic','academic','harvard'):
            with self.subTest(template=template),patch('ai.llm.ollama_client.request_structured',side_effect=AssertionError('Unexpected AI call')):
                result=form_preview(DraftPreview(profile=fixture(),presentation=Presentation(template=template,template_version=3)))
                soup=BeautifulSoup(result['html'],'html.parser')
                text=soup.body.get_text(' ',strip=True)
                self.assertIn(fixture().contact.full_name,text)
                self.assertIn('GPA: 3.4/4.0',text)
                self.assertIn('Chứng chỉ kiểm thử',text)
                self.assertIn('reference@example.com',text)
        self.assertEqual(profile_drafts.list_editing(),before)

    def test_catalog_only_offers_the_fifteen_supplied_layouts_and_valid_fields(self):
        items=templates()
        self.assertEqual(len(items),15)
        self.assertEqual(sum(item['category']=='harvard' for item in items),3)
        schema=MasterProfile.model_json_schema()
        contact=set(schema['$defs']['Contact']['properties'])
        for template in items:
            self.assertTrue(set(template['contact_fields'])<=contact)
            self.assertEqual(template['form_sections'][-1],'summary')
            for kind,fields in template['entry_fields'].items():
                model=schema['properties'][kind]['items']['$ref'].split('/')[-1]
                self.assertTrue(set(fields)<=set(schema['$defs'][model]['properties']))
            self.assertEqual(template['has_photo'],template['category']!='harvard')
