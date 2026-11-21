import unittest
from unittest.mock import patch
from bs4 import BeautifulSoup
from backend.tests.test_simple_reference_templates import fixture
from ai.agents.cv_agent import source_document
from backend.app.schemas.resume import Presentation
from backend.app.services.cv_templates import TEMPLATES, example_document, REFERENCES
from backend.app.services.cv_renderer import render_html


class SuppliedTemplatePreviewTests(unittest.TestCase):
    def test_all_preview_templates_use_fictional_identity_and_education(self):
        document=example_document()
        self.assertEqual(document.contact.email,'minhan@example.com')
        self.assertEqual(document.contact.full_name,'Nguyễn Minh An')
        education=next(s for s in document.sections if s.kind=='education')
        self.assertEqual(education.entries[0].title,'Đại học Minh Họa')
        self.assertEqual(education.entries[0].period,'2023 – 2027')
        self.assertTrue(any(b.text=='3.6/4.0' for b in education.entries[0].bullets))
        self.assertEqual(len(next(s for s in document.sections if s.kind=='experience').entries),3)
        for template in TEMPLATES:
            with self.subTest(template=template['id']):
                soup=BeautifulSoup(render_html(document,template['id']),'html.parser')
                text=' '.join(soup.body.get_text(' ',strip=True).split())
                self.assertIn('Nguyễn Minh An',text)
                self.assertIn('Đại học Minh Họa',text)
                self.assertIn('3.6/4.0',text)
                self.assertNotIn('3.4/4.0',text)
                self.assertNotIn('Đại học Quốc gia Hà Nội',text)

    def test_twelve_supplied_layouts_preserve_all_fields_and_uploaded_photo(self):
        document=source_document(fixture(),'fixture',language='vi')
        self.assertEqual(len(REFERENCES),15)
        for template in REFERENCES:
            with self.subTest(template=template), patch('backend.app.services.assets.photo_data',return_value='data:image/png;base64,fixture'):
                soup=BeautifulSoup(render_html(document,template,Presentation(template=template,photo_asset_id='asset_'+'a'*64).model_dump()),'html.parser')
                text=' '.join(soup.body.get_text(' ',strip=True).split())
                for section in document.sections:
                    for entry in section.entries:
                        for value in [entry.title,entry.subtitle]+[b.text for b in entry.bullets]:
                            if value:self.assertTrue(' '.join(value.split()) in text,template+': missing source field '+value)
                expected_photo = 0 if template in {'classic','academic','harvard'} else 1
                self.assertEqual(len(soup.select('img[src="data:image/png;base64,fixture"]')),expected_photo)
                self.assertEqual(soup.select('.section-skills li'),[])
                self.assertEqual(soup.select('script'),[])
