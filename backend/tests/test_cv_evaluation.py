import unittest
from unittest.mock import patch
from backend.app.schemas.profile import MasterProfile
from backend.app.schemas.job import JobRequirements
from ai.agents.cv_agent import source_document
from ai.agents.matching_agent import match_profile
from backend.app.services.cv_evaluation import displayed_profile,visible_evidence


class CVEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.profile=MasterProfile(contact={},experience=[],project=[{'id':'p','project_name':'Demo','description':['Built Python services.','Maintained SQL queries.']}],education=[],involvement=[],skills=[])
        self.job=JobRequirements(job_description_raw='Required: Python.',required_skills=[{'name':'Python','evidence':'Required: Python.','requirement_type':'required'}])

    def test_hidden_bullet_is_not_profile_evidence(self):
        full=match_profile(self.profile,self.job,'profile','jd')
        doc=source_document(self.profile,'profile')
        doc.sections[0].entries[0].bullets.pop(0)
        projected,refs=displayed_profile(doc)
        result=visible_evidence(match_profile(projected,self.job,'cv','jd'),refs)
        self.assertEqual(full.assessments[0].status,'met')
        self.assertEqual(result.assessments[0].status,'unknown')
        self.assertEqual(result.assessments[0].evidence_refs,[])

    def test_cv_evidence_points_to_visible_text(self):
        doc=source_document(self.profile,'profile');projected,refs=displayed_profile(doc)
        result=visible_evidence(match_profile(projected,self.job,'cv','jd'),refs)
        self.assertEqual(result.assessments[0].evidence_refs,['/document/sections/0/entries/0/bullets/0/text'])

    def test_presentation_does_not_enter_projection(self):
        doc=source_document(self.profile,'profile')
        a,_=displayed_profile(doc);b,_=displayed_profile(doc.model_copy(deep=True))
        self.assertEqual(match_profile(a,self.job,'cv','jd').score,match_profile(b,self.job,'cv','jd').score)

    def test_service_never_loads_hidden_profile_or_answer_ledger(self):
        from backend.app.services.dashboard_service import evaluate_job
        from backend.app.schemas.dashboard import JobPosting
        from backend.app.schemas.job import JobAnalysisResponse
        document=source_document(self.profile,'source_revision')
        version={'document':document.model_dump(mode='json')}
        job=JobPosting(posting_id='posting_'+'a'*24,title='Python Engineer',description='Required: Python.',source_name='fixture',external_id='fixture',imported_at='2026-01-01T00:00:00Z')
        analysis=JobAnalysisResponse(job_id='analysis',status='completed',job_requirements=self.job,warnings=[],job_description_raw=self.job.job_description_raw)
        with patch('backend.app.services.dashboard_service.get_posting',return_value=job), patch('backend.app.services.dashboard_service.profile_repository.load_profile_record',side_effect=AssertionError('Must not read source profile')), patch('backend.app.services.dashboard_service.confirmed_profiles',side_effect=AssertionError('Must not default to a profile')), patch('backend.app.db.workflow_repository.get',return_value=version), patch('backend.app.services.dashboard_service.analyze_selected_job',return_value=(analysis,True)), patch('backend.app.services.dashboard_service.confirmed_denials',side_effect=AssertionError('Must not use profile answers')), patch('backend.app.services.dashboard_service.match_repository.load_match',return_value=None), patch('backend.app.services.dashboard_service.match_repository.save_match',side_effect=lambda result,_:result):
            result=evaluate_job(job.posting_id,None,cv_id='cv_'+'b'*32)
        self.assertEqual(result.input_type,'cv')
        self.assertEqual(result.matching.input_id,'cv_'+'b'*32)
        self.assertEqual(result.matching.profile_revision_id,'source_revision')
        self.assertEqual(result.matching.assessments[0].status,'met')
