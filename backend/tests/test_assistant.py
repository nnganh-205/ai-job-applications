import unittest
from unittest.mock import patch
from pydantic import ValidationError
from backend.app.schemas.assistant import AssistantStart,AssistantMessage,IntentDecision
from backend.app.schemas.cv import CVDocument,CVStart,CVReview
from backend.app.services.assistant import require_context,choose_intent


class AssistantTests(unittest.TestCase):
    def test_context_cannot_mix_cv_and_profile(self):
        with self.assertRaises(ValidationError):AssistantStart(profile_id='p',cv_id='cv_'+'a'*32,event_id='one')

    def test_empty_input_and_unknown_actions_rejected(self):
        for payload in [dict(text=' '),dict(intent='execute_sql')]:
            with self.assertRaises(ValidationError):AssistantMessage(expected_version=1,event_id='one',**payload)

    def test_missing_sources_request_clarification(self):
        for intent in ('review_cv','tailor_cv','evaluate','find_jobs','update_profile'):
            self.assertIsNotNone(require_context({},intent))
        self.assertIsNotNone(require_context({'cv_id':'cv_x'},'update_profile'))
        self.assertIsNone(require_context({'cv_id':'cv_x','posting_id':'posting_x'},'tailor_cv'))

    def test_classifier_never_receives_attached_document_or_ids(self):
        with patch('backend.app.services.assistant.request_structured',return_value=IntentDecision(intent='evaluate')) as model:
            choose_intent('Xem độ phù hợp',{'language':'vi','cv_id':'private_cv_identifier','posting_id':'private_job','document':'SECRET DOCUMENT'})
            payload=model.call_args.args[0][1]['content']
            self.assertNotIn('SECRET DOCUMENT',payload)
            self.assertNotIn('private_cv_identifier',payload)
            self.assertIn('has_cv',payload)

    def test_cv_review_cannot_read_hidden_profile(self):
        from ai.graph.cv_workflow import generate
        doc=CVDocument(source_profile_revision_id='p',language='en',contact={},sections=[dict(kind='project',heading='Projects',entries=[dict(source_entry_id='one',title='Visible project',bullets=[dict(text='Visible Python work.',source_refs=['/project/0/description/0'])])])])
        with patch('ai.graph.cv_workflow.records.get',return_value={'document':doc.model_dump(mode='json')}),patch('ai.graph.cv_workflow.profile_repository.load_profile_record',side_effect=AssertionError('Hidden profile read')),patch('ai.graph.cv_workflow.plan_cv',side_effect=lambda baseline,*_: (baseline,CVReview(items=[]))) as model:
            result=generate({'request':CVStart(cv_id='cv_'+'a'*32,mode='review').model_dump()})
            self.assertEqual(result['document']['sections'][0]['entries'][0]['bullets'][0]['text'],'Visible Python work.')
            self.assertEqual(len(model.call_args.args[0].sections),1)

    def test_empty_extracted_entries_do_not_become_phantom_cv_sections(self):
        from backend.app.schemas.profile import MasterProfile
        from ai.agents.cv_agent import source_document
        profile=MasterProfile(contact={},experience=[{}],project=[],education=[{}],involvement=[],skills=[{'group':'Empty skills'}])
        self.assertEqual(source_document(profile,'fixture').sections,[])
