import unittest
from unittest.mock import patch

from ai.agents.cv_agent import source_document
from ai.agents.cv_form import (
    FormPlan, apply_form_plan, clean_sentence, form_payload, refine_form, validate_form_document,
    form_plan_schema,
    preferred_summary_refs,
)
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

    def test_form_refines_without_inference_and_keeps_source_unchanged(self):
        original = self.document.model_copy(deep=True)
        self.assertEqual(clean_sentence("- 25%"), "- 25%")
        self.assertEqual(clean_sentence("Thực hiện việc công ty giao."), "Thực hiện việc công ty giao.")
        with patch("ai.llm.ollama_client.request_structured", side_effect=AssertionError("Unexpected inference")) as model:
            result, info = refine_form(self.document)
        model.assert_not_called()
        self.assertEqual(self.document, original)
        self.assertEqual(info["status"], "completed")
        self.assertEqual(result.summary.text, "Vai trò: Thực tập sinh. Kỹ năng: SQL, Python.")
        validate_form_document(original, result)

    def test_large_form_keeps_every_fact_and_number_without_inference(self):
        profile = MasterProfile(contact={'full_name':'Giả lập'}, experience=[{
            'job_title':'Trợ lý', 'description':[f'Có hỗ trợ kiểm tra {n} phiếu bằng SQL.' for n in range(1,10)]
        }], project=[], education=[], involvement=[], skills=[])
        doc = source_document(profile, 'batch-fixture', language='vi')
        with patch('ai.llm.ollama_client.request_structured', side_effect=AssertionError('Unexpected inference')):
            result, info = refine_form(doc)
        self.assertEqual((info['applied'], info['rejected']), (9, 0))
        self.assertEqual([b.text for b in result.sections[0].entries[0].bullets],
                         [f'Hỗ trợ kiểm tra {n} phiếu bằng SQL.' for n in range(1, 10)])
        validate_form_document(doc, result)
