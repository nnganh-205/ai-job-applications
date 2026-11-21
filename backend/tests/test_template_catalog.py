import hashlib
import json
import unittest
from collections import Counter
from typing import get_args
from bs4 import BeautifulSoup
from backend.app.schemas.templates import BuiltinTemplateID
from backend.app.services.cv_templates import TEMPLATES, REFERENCES, synthetic_document as example_document
from backend.app.services.cv_renderer import render_html
from backend.app.services.topcv_renderer import ROOT


class TemplateCatalogTests(unittest.TestCase):
    def test_catalog_preserves_24_ids_and_required_sources(self):
        self.assertEqual(len(TEMPLATES),24)
        self.assertEqual({t['id'] for t in TEMPLATES},set(get_args(BuiltinTemplateID)))
        self.assertEqual(Counter(t['category'] for t in TEMPLATES),
                         dict.fromkeys(['basic','professional','modern','impressive','harvard','ats'],4))
        sources={s['id']:s for s in json.loads((ROOT/'sources.json').read_text())}
        for template in TEMPLATES:
            item=sources[template['id']]
            if template['id'] in REFERENCES:
                self.assertEqual(template['source'],'user_pdf')
                self.assertEqual(template['version'],3)
                self.assertFalse((ROOT/(template['id']+'.html')).exists())
                self.assertFalse((ROOT/(template['id']+'.css')).exists())
            else:
                self.assertEqual(template['name'],item['name'])
                self.assertEqual(template['source'],'topcv')
                self.assertEqual(template['source_url'],item['source_url'])
                self.assertEqual(hashlib.sha256((ROOT/(template['id']+'.html')).read_bytes()).hexdigest(),item['html_sha256'])
                self.assertEqual(hashlib.sha256((ROOT/(template['id']+'.css')).read_bytes()).hexdigest(),item['css_sha256'])

    def test_every_template_preserves_facts_without_sample_content(self):
        document=example_document()
        for template in TEMPLATES:
            with self.subTest(template=template['id']):
                soup=BeautifulSoup(render_html(document,template['id']),'html.parser')
                text=' '.join(soup.body.get_text(' ',strip=True).split())
                for section in document.sections:
                    for entry in section.entries:
                        for value in [entry.title,entry.subtitle]+[b.text for b in entry.bullets]:
                            if value:self.assertTrue(' '.join(value.split()) in text,'Missing source field: '+value)
                for sample in ['Nguyễn Hoàng Anh','hotro@topcv.vn','26/05/1996','SVT Finance']:
                    self.assertNotIn(sample,text)
                sections=[s['class'][-1] for s in soup.select('section.cv-section, section.reference-section:not(.reference-summary),section.harvard-section:not(.harvard-summary)')]
                if template['category'] not in {'professional','modern'} and template['id']!='academic':
                    self.assertLess(sections.index('section-education'),sections.index('section-experience'))
                self.assertEqual(len(soup.select('.section-skills li')),0)
                self.assertEqual(len(soup.select('.skills-line')),2)
                self.assertTrue('Python, PostgreSQL, React, FastAPI, Git' in text)
                self.assertEqual(soup.select('script'),[])
                self.assertEqual(soup.select('img[src^="http"]'),[])

    def test_empty_sections_and_untrusted_text(self):
        document=example_document()
        document.contact.full_name='<script>alert(1)</script>'
        document.sections=[s for s in document.sections if s.kind=='skills']
        document.summary=None
        for template in TEMPLATES:
            with self.subTest(template=template['id']):
                html=render_html(document,template['id'])
                soup=BeautifulSoup(html,'html.parser')
                self.assertEqual(soup.select('script'),[])
                self.assertEqual(len(soup.select('.section-skills')),1)
                self.assertEqual(soup.select('.section-education'),[])
                self.assertEqual(soup.select('.section-experience'),[])
                self.assertIn('<script>alert(1)</script>',soup.get_text())

    def test_new_source_document_starts_with_education(self):
        self.assertEqual(example_document().sections[0].kind,'education')
