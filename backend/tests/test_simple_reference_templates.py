import unittest
from unittest.mock import patch
from bs4 import BeautifulSoup
from backend.app.schemas.profile import MasterProfile
from backend.app.schemas.resume import Presentation
from backend.app.services.cv_renderer import render_html
from ai.agents.cv_agent import source_document, validate_edits


def fixture():
    return MasterProfile(contact=dict(full_name='Ứng viên kiểm thử',headline='AI ENGINEER',email='fixture@example.com',phone='0900000000',date_of_birth='01/01/2000',gender='Nam',location='Hà Nội'),summary='Nghiên cứu hệ thống học máy từ dữ liệu đã cung cấp.',education=[dict(id='edu',institution='Đại học minh họa',degree='Cử nhân',major='Khoa học máy tính',start_date='2018',end_date='2022',details=['GPA: 3.4/4.0'])],experience=[dict(id='exp',job_title='AI Engineer',company='Công ty minh họa',start_date='2022',end_date='2025',description=['Xây dựng API bằng Python.'])],project=[dict(id='proj',project_name='Dự án kiểm thử',description=['Phân tích dữ liệu bằng Python.'])],skills=[dict(id='skills',group='Chuyên môn',items=['Python','PyTorch','SQL'])],involvement=[],certifications=[dict(id='cert',name='Chứng chỉ kiểm thử',issuer='Đơn vị cấp',date='2024')],awards=[dict(id='award',title='Giải thưởng kiểm thử',organization='Tổ chức minh họa',date='2023')],references=[dict(id='ref',full_name='Người tham chiếu',position='Trưởng nhóm',organization='Công ty minh họa',email='reference@example.com',phone='0911111111',relationship='Quản lý trực tiếp')])


class SimpleReferenceTemplateTests(unittest.TestCase):
    def test_all_pdf_fields_survive_source_conversion_and_rendering(self):
        document=source_document(fixture(),'fixture',language='vi')
        self.assertEqual(document.sections[0].kind,'education')
        for template in ('simple','clean','minimal','compact'):
            with self.subTest(template=template):
                soup=BeautifulSoup(render_html(document,template),'html.parser')
                text=soup.body.get_text(' ',strip=True)
                for value in ['Ứng viên kiểm thử','AI ENGINEER','01/01/2000','Nam','fixture@example.com','Đại học minh họa','GPA: 3.4/4.0','Chứng chỉ kiểm thử','Giải thưởng kiểm thử','Người tham chiếu','reference@example.com','0911111111','Quản lý trực tiếp','Dự án kiểm thử']:
                    self.assertIn(value,text)
                self.assertEqual(len(soup.select('img.reference-avatar')),1)
                self.assertTrue(soup.select_one('.reference-avatar')['src'].startswith('data:image/svg+xml;base64,'))
                self.assertEqual(len(soup.select('.section-skills li')),0)
                self.assertIn('Python, PyTorch, SQL',soup.select_one('.section-skills').get_text())
                self.assertLess(str(soup).index('section-education'),str(soup).index('section-experience'))
                self.assertEqual(len(soup.select('.reference-trio')),1 if template=='clean' else 0)

    def test_uploaded_avatar_uses_the_same_layout_slot_and_never_a_remote_url(self):
        document=source_document(fixture(),'fixture',language='vi')
        with patch('backend.app.services.assets.photo_data',return_value='data:image/png;base64,fixture') as photo:
            for template in ('simple','clean','minimal','compact'):
                html=render_html(document,template,Presentation(template=template,photo_asset_id='asset_'+'a'*64).model_dump())
                soup=BeautifulSoup(html,'html.parser')
                self.assertEqual(soup.select_one('header .reference-avatar')['src'],'data:image/png;base64,fixture')
        self.assertEqual(photo.call_count,4)

    def test_added_sections_keep_the_original_grounding_contract(self):
        document=source_document(fixture(),'fixture',language='vi')
        validate_edits(document,document.model_copy(deep=True))
        edited=document.model_copy(deep=True)
        section=next(s for s in edited.sections if s.kind=='references')
        section.entries[0].bullets[0].source_refs=['/references/99/email']
        with self.assertRaises(ValueError):validate_edits(document,edited)
