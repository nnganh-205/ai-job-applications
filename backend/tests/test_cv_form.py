import unittest
from unittest.mock import patch

from ai.agents.cv_agent import source_document
from ai.agents.cv_form import (
    FormPlan, apply_form_plan, clean_sentence, form_payload, refine_form, validate_form_document,
    form_plan_schema,
    preferred_summary_refs,
)
from ai.llm.ollama_client import OllamaConnectionError
from backend.app.schemas.profile import MasterProfile


class FormRefinementTests(unittest.TestCase):
    def test_summary_policy_reuses_existing_and_limits_role_project_skills(self):
        from pydantic import ValidationError
        options = {'/entry/project/0':'Dự án: Mẫu', '/skills/0/items/0':'Kỹ năng: SQL',
                   '/entry/experience/0':'Vai trò: Trợ lý'}
        expected = ['/entry/experience/0','/skills/0/items/0']
        self.assertEqual(preferred_summary_refs(options),expected)
        schema = form_plan_schema({'candidates':[], 'summary_options':options})
        self.assertEqual(schema.model_json_schema()['properties']['summary_refs']['const'],expected)
        with self.assertRaises(ValidationError):
            schema.model_validate({'edits':[],'summary_refs':list(options)})
        self.assertEqual(preferred_summary_refs({**options,'/summary':'Nội dung đã nhập.'}),['/summary'])

    def test_generation_schema_is_bound_to_allowed_refs_including_empty_input(self):
        from pydantic import ValidationError
        schema = form_plan_schema({'candidates':[
            {'source_ref':'allowed','proposed_text':'Fact'},
            {'source_ref':'other','proposed_text':'Other fact'}], 'summary_options':{'known':'Fact'}})
        schema.model_validate({'edits':[{'source_ref':'allowed','proposed_text':'Fact'}],'summary_refs':['known']})
        for bad in [
            {'edits':[{'source_ref':'invented','proposed_text':'Fact'}],'summary_refs':[]},
            {'edits':[],'summary_refs':['invented']},
            {'edits':[{'source_ref':'allowed','proposed_text':'Invented fact'}],'summary_refs':[]},
            {'edits':[{'source_ref':'allowed','proposed_text':'Other fact'}],'summary_refs':[]},
        ]:
            with self.assertRaises(ValidationError): schema.model_validate(bad)
        empty = form_plan_schema({'candidates':[], 'summary_options':{}})
        with self.assertRaises(ValidationError):
            empty.model_validate({'edits':[{'source_ref':'x','proposed_text':'X'}],'summary_refs':[]})
        skipped = form_plan_schema({'candidates':[
            {'source_ref':'missing', 'original_text':'Already clear.'},
            {'source_ref':'unchanged', 'original_text':'No change.', 'proposed_text':'No change.'}],
            'summary_options':{}})
        self.assertEqual(skipped.model_json_schema()['properties']['edits']['maxItems'],0)
    def test_form_model_can_be_selected_without_changing_tailoring_model(self):
        from backend.app.core.config import Settings
        with patch.dict('os.environ', {'LLM_MODEL':'base', 'CV_MODEL':'tailor', 'FORM_CV_MODEL':'form-adapter'}):
            settings = Settings.from_environment()
        self.assertEqual(settings.model_for_task('form'),'form-adapter')
        self.assertEqual(settings.model_for_task('cv'),'tailor')
        self.assertEqual(settings.model_for_task('jd'),'base')
    def setUp(self):
        profile = MasterProfile(
            contact={"full_name": "Hồ sơ giả lập"},
            experience=[{"job_title": "Thực tập sinh", "description": ["Có hỗ trợ kiểm tra 25 bản ghi bằng SQL."]}],
            project=[{"project_name": "Bảng tồn kho", "description": ["Thực hiện việc tổng hợp tồn kho bằng Python."]}],
            education=[], involvement=[], skills=[{"items": ["SQL", "Python"]}],
        )
        self.document = source_document(profile, "synthetic-form", language="vi")

    def test_refinement_keeps_invalid_edits_and_composes_only_source_facts(self):
        payload = form_payload(self.document)
        plan = FormPlan(
            edits=[
                {"source_ref": "/experience/0/description/0", "proposed_text": "Dẫn dắt kiểm tra 50 bản ghi bằng SQL."},
                {"source_ref": "/project/0/description/0", "proposed_text": "Tổng hợp tồn kho bằng Python."},
            ],
            summary_refs=["/entry/experience/0", "/skills/0/items/0"],
        )
        refined, applied, rejected = apply_form_plan(self.document, payload, plan)
        self.assertEqual((applied, rejected), (1, 1))
        self.assertEqual(refined.sections[0], self.document.sections[0])
        self.assertEqual(refined.sections[-1], self.document.sections[-1])
        self.assertEqual(refined.summary.text, "Vai trò: Thực tập sinh. Kỹ năng: SQL, Python.")
        validate_form_document(self.document, refined)
        refined.summary.text += " Thành thạo Docker."
        with self.assertRaises(ValueError):
            validate_form_document(self.document, refined)

    def test_ambiguous_prefix_and_model_failure_leave_source_intact(self):
        self.assertEqual(clean_sentence("- 25%"), "- 25%")
        self.assertEqual(clean_sentence("Thực hiện việc công ty giao."), "Thực hiện việc công ty giao.")
        with patch("ai.agents.cv_form.request_structured", side_effect=OllamaConnectionError()):
            result, info = refine_form(self.document)
        self.assertEqual(result, self.document)
        self.assertEqual(info["status"], "fallback")

    def test_large_form_batches_reject_cross_batch_refs_and_keep_failure_atomic(self):
        from ai.llm.ollama_client import llm_deadline
        profile = MasterProfile(contact={'full_name':'Giả lập'}, experience=[{
            'job_title':'Trợ lý', 'description':[f'Có hỗ trợ kiểm tra {n} phiếu bằng SQL.' for n in range(1,10)]
        }], project=[], education=[], involvement=[], skills=[])
        doc = source_document(profile, 'batch-fixture', language='vi')
        seen = []
        def response(messages, schema, **kwargs):
            payload = __import__('json').loads(messages[1]['content']); seen.append(payload)
            edits = [{'source_ref':c['source_ref'], 'proposed_text':c['proposed_text']} for c in payload['candidates']]
            if len(seen)==1:
                edits.append({'source_ref':'/experience/0/description/8', 'proposed_text':'Hỗ trợ kiểm tra 9 phiếu bằng SQL.'})
            return FormPlan(edits=edits, summary_refs=[])
        with patch('ai.agents.cv_form.request_structured', side_effect=response), patch(
                'ai.agents.cv_form.llm_deadline', wraps=llm_deadline) as deadline:
            result, info = refine_form(doc)
        deadline.assert_called_once_with(270)
        self.assertEqual([len(p['candidates']) for p in seen], [4,4,1])
        self.assertTrue(all(not p['summary_options'] for p in seen[1:]))
        self.assertEqual((info['applied'],info['rejected']), (9,1))
        validate_form_document(doc,result)
        with patch('ai.agents.cv_form.request_structured', side_effect=[FormPlan(edits=[],summary_refs=[]), OllamaConnectionError()]):
            result, info = refine_form(doc)
        self.assertEqual(result,doc)
        self.assertEqual(info['status'],'fallback')
