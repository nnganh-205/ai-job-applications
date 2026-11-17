import unittest
from backend.app.schemas.interview import PracticeTurn
from backend.app.services.interviews import validate_turn,report,cv_text
from ai.llm.ollama_client import OllamaSchemaError
from backend.app.schemas.cv import CVDocument


def feedback():
    return dict(rubric=[dict(dimension=d,score=3,reason='Clear example') for d in ('relevance','clarity','specificity','technical_accuracy')],strengths=['Specific example'],improvements=['Explain tradeoffs'],answer_quotes=['Python'],suggested_approach='Explain the decision and its tradeoffs.')


def question(kind='technical'):
    return dict(kind=kind,text='How did you use Python in the service?',evidence=[dict(source='cv',quote='Python')])


class InterviewGuardTests(unittest.TestCase):
    def session(self,kind='technical'):
        return dict(source={'cv':'Built Python services','jd':'Requires SQL'},question_count=2,turns=[dict(question=question(kind))])

    def test_question_cannot_cite_hidden_profile_content(self):
        value=question();value['evidence'][0]['quote']='Hidden Kubernetes achievement'
        with self.assertRaises(OllamaSchemaError):validate_turn(PracticeTurn(question=value,feedback=None),dict(source={'cv':'Python','jd':'SQL'},turns=[],question_count=2),{'answer':None})

    def test_feedback_must_quote_actual_answer(self):
        value=feedback();value['answer_quotes']=['Invented promotion']
        with self.assertRaises(OllamaSchemaError):validate_turn(PracticeTurn(question=question('behavioral'),feedback=value),self.session(),{'answer':'I used Python.'})

    def test_duplicate_rubric_dimension_rejected(self):
        value=feedback();value['rubric'][0]['dimension']='clarity'
        with self.assertRaises(OllamaSchemaError):validate_turn(PracticeTurn(question=question('behavioral'),feedback=value),self.session(),{'answer':'Python'})

    def test_repeated_question_rejected(self):
        with self.assertRaises(OllamaSchemaError):validate_turn(PracticeTurn(question=question(),feedback=feedback()),self.session(),{'answer':'Python'})

    def test_behavioral_technical_grade_is_not_counted(self):
        session=self.session('behavioral');session['turns'].append(dict(question=question('behavioral')))
        value=PracticeTurn(question=None,feedback=feedback())
        validate_turn(value,session,{'answer':'I used Python.'})
        technical=next(r for r in value.feedback.rubric if r.dimension=='technical_accuracy')
        self.assertIsNone(technical.score)
        result=report([dict(feedback=value.feedback.model_dump())])
        self.assertIsNone(result['rubric']['technical_accuracy']['average'])
        self.assertEqual(result['rubric']['relevance']['average'],3)

    def test_last_answer_must_not_generate_another_question(self):
        session=self.session();session['turns']*=2
        with self.assertRaises(OllamaSchemaError):validate_turn(PracticeTurn(question=question('behavioral'),feedback=feedback()),session,{'answer':'Python'})

    def test_contact_details_do_not_go_to_model(self):
        document=CVDocument(source_profile_revision_id='fixture',language='en',contact={'full_name':'Private Name','email':'private@example.com'},sections=[])
        text=cv_text(document)
        self.assertNotIn('private@example.com',text)
        self.assertNotIn('Private Name',text)

    def test_model_schema_limits_evidence_ids_and_question_kind(self):
        from pydantic import ValidationError
        from backend.app.services.interviews import response_schema
        schema=response_schema({'cv:0':'Python'},'technical')
        schema.model_validate({'question':{'kind':'technical','text':'How do you test Python APIs?','evidence_refs':['cv:0']}})
        for changes in ({'evidence_refs':['jd:999']},{'kind':'behavioral'}):
            with self.assertRaises(ValidationError):
                schema.model_validate({'question':{'kind':'technical','text':'How do you test Python APIs?','evidence_refs':['cv:0'],**changes}})

    def test_segment_quotes_are_exact_and_bounded(self):
        from backend.app.services.interviews import evidence_segments
        source={'cv':'Python. '+('A'*1300),'jd':'SQL transactions'}
        segments=evidence_segments(source)
        self.assertTrue(all(quote in source[key.split(':')[0]] and len(quote)<=600 for key,quote in segments.items()))

    def test_vietnamese_session_does_not_accept_english_question(self):
        session=dict(source={'cv':'Python','jd':'SQL'},turns=[],question_count=2,language='vi')
        with self.assertRaises(OllamaSchemaError):
            validate_turn(PracticeTurn(question=question(),feedback=None),session,{'answer':None})
