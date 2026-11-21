import json
import re
import unittest
from unittest.mock import patch

from backend.app.services.assistant_grounding import SourceUpdates, recover_sources
from backend.app.services.assistant_routing import ChatDecision, SourceMismatch
from backend.app.services.assistant_intake import blank_intake,apply_updates
from backend.app.services.assistant import choose_intent


class AssistantGroundingTests(unittest.TestCase):
    def test_explicit_project_keeps_percent_ranges_awards_and_all_source_clauses(self):
        text = ('Dự án Phân tích lớp phủ đô thị : với công việc Xử lý ảnh qua 5 mốc (1986–2025), '
                'trích xuất 12 đặc trưng.   Huấn luyện Random Forest phân loại 6 loại với độ chính xác '
                '91,49% – 97,88%, đồng thời phân tích bằng ma trận chuyển đổi. '
                'Phát triển trên Google Earth Engine, truy vấn điểm ảnh (pixel-level) , '
                'Đạt Giải Nhì cấp Trường và Giải Nhất cấp Khoa=')
        intake = blank_intake()
        intake['profile']['contact'].update(full_name='Test',email='test@example.com')
        intake['target_role']='Developer';intake['skipped']=['education','experience']
        with patch('backend.app.services.assistant.request_structured',side_effect=AssertionError('Unexpected inference')):
            decision=choose_intent(text,{'language':'vi'},intake=intake)
        result,rejected=apply_updates(intake,decision.updates,text)
        self.assertEqual(rejected,0)
        entry=result['profile']['project'][0]
        self.assertEqual(entry['project_name'],'Phân tích lớp phủ đô thị')
        self.assertEqual(len(entry['description']),4)
        for value in ['5 mốc (1986–2025)','12 đặc trưng','6 loại','91,49% – 97,88%','pixel-level','Giải Nhì','Giải Nhất']:
            self.assertIn(value,' '.join(entry['description']))
        self.assertIsNone(entry['start_date'])
        self.assertIsNone(entry['end_date'])
        self.assertIsNone(entry['role'])
        self.assertEqual(entry['technologies'],[])

    def test_hypothetical_project_is_not_taken_as_a_fact(self):
        from backend.app.services.assistant_project_facts import explicit_project
        intake=blank_intake();intake['skipped']=['contact','target_role','education','experience']
        self.assertIsNone(explicit_project('Dự án Demo: với công việc ví dụ xây dựng ứng dụng thì sao?',intake))

    def test_recovery_uses_original_ranges_and_keeps_valid_fields(self):
        text='Dự án Demo: mô hình đạt 91,49% – 97,88% với Random Forest (pixel-level).'
        tokens=list(re.finditer(r'\S+',text))
        bad=ChatDecision(intent='build_cv',updates=[
            dict(path='project.0.project_name',value='Demo'),
            dict(path='project.0.description',value=['Đạt 97.88%']),
            dict(path='project.0.technologies',value=['Random Forest','Python']),
        ])
        rf=next(i for i,m in enumerate(tokens) if m.group()=='Random')
        selection=SourceUpdates(updates=[
            dict(path='project.0.description',spans=[dict(start=3,end=len(tokens))]),
            dict(path='project.0.technologies',spans=[dict(start=rf,end=rf+2)]),
        ])
        with patch('backend.app.services.assistant.request_structured',return_value=selection) as request:
            result=recover_sources(bad,text,request)
        values={p.field:p.value for p in result.updates}
        self.assertEqual(values['project_name'],'Demo')
        self.assertEqual(values['description'],[text[tokens[3].start():]])
        self.assertEqual(values['technologies'],['Random Forest'])
        self.assertNotIn('Python',request.call_args.args[0][-1]['content'])
        payload=json.loads(request.call_args.args[0][-1]['content'])
        self.assertEqual(payload['token_count'],len(tokens))

    def test_out_of_bounds_overlap_or_unrequested_fields_are_rejected(self):
        bad=ChatDecision(intent='build_cv',updates=[dict(path='project.0.description',value=['invented'])])
        for values in [
            [dict(path='project.0.description',spans=[dict(start=0,end=99)])],
            [dict(path='project.0.description',spans=[dict(start=0,end=2),dict(start=1,end=3)])],
            [dict(path='contact.full_name',spans=[dict(start=0,end=1)])],
            [dict(path='project.0.description',spans=[])],
        ]:
            with self.subTest(values=values),self.assertRaises(SourceMismatch):
                recover_sources(bad,'Original source words',lambda *a,**kw:SourceUpdates(updates=values))

    def test_repair_preserves_set_then_append_order(self):
        text='Built Python API. Deployed Docker.'
        bad=ChatDecision(intent='build_cv',updates=[
            dict(path='project.0.description',value=['Developed Python service'],operation='set'),
            dict(path='project.0.description',value=['Deployed Docker.'],operation='append'),
        ])
        selected=SourceUpdates(updates=[dict(path='project.0.description',spans=[dict(start=0,end=3)])])
        decision=recover_sources(bad,text,lambda *a,**kw:selected)
        result,rejected=apply_updates(blank_intake(),decision.updates,text)
        self.assertEqual(rejected,0)
        self.assertEqual(result['profile']['project'][0]['description'],['Built Python API.','Deployed Docker.'])
