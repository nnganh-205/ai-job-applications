import unittest
from unittest.mock import patch

from ai.llm.ollama_client import OllamaTimeoutError
from backend.app.services.cv_writer import WriterRequest,write_bullets
from backend.app.services.cv_refinement import Rewrite,RewritePlan,Review,Reviews,wording_issues,format_line,candidate_issues


SOURCE=('Built a dashboard using Python to display temperature measurements from test equipment '
        'for review by the research team during scheduled checks, and recorded the timestamps '
        'of incoming readings in PostgreSQL to preserve the original sequence of the collected observations.')
SPLIT=[SOURCE.split(', and ')[0]+'.',SOURCE.split(', and ')[1].capitalize().replace('postgresql','PostgreSQL')]


def verdict(accepted=True):
    return Reviews(reviews=[Review(source_id='f0',same_actions_and_objects=accepted,
        same_tools_and_methods=True,same_actor_and_scope=True,same_numbers_and_results=True,
        same_goals_negations_and_conditions=True,all_facts_retained=True,no_added_claims=True,
        each_line_is_complete=True,goals_and_scope_stay_attached=True,omitted_facts=[],added_claims=[])])


class RefinementTests(unittest.TestCase):
    def run_plan(self,lines,review=True,**kwargs):
        request=WriterRequest(field='description',text=SOURCE,issues=['length'],**kwargs)
        plan=RewritePlan(rewrites=[Rewrite(source_id='f0',lines=lines)])
        with patch('backend.app.services.cv_refinement.request_structured',side_effect=lambda messages,schema,**kw:plan if schema is RewritePlan else verdict(review)) as call:
            result=write_bullets(request)
        return result,call

    def test_diagnostics_match_word_limit_and_punctuation(self):
        self.assertIn('length',wording_issues(SOURCE))
        self.assertNotIn('length',wording_issues(' '.join(['word']*38)+'.'))
        self.assertIn('length',wording_issues(' '.join(['word']*39)+'.'))
        self.assertEqual(wording_issues('mình hỗ trợ kiểm thử'),{'pronoun','punctuation'})
        self.assertEqual(format_line('Built a dashboard,.'),'Built a dashboard.')

    def test_vietnamese_limit_is_sixty_whitespace_units(self):
        self.assertNotIn('length',wording_issues('Triển '+' '.join(['khai']*59)+'.'))
        self.assertIn('length',wording_issues('Triển '+' '.join(['khai']*60)+'.'))

    def test_equivalent_scope_wording_reaches_semantic_review(self):
        source='Implemented continuous monitoring and version control for approved documents (audit history).'
        lines=['Implemented ongoing monitoring with document versioning for approved documents, retaining audit history.']
        errors=candidate_issues(source,lines,['length'],semantic_review=True)
        self.assertFalse(any(e.startswith('preserve_source_detail:') for e in errors))
        self.assertIn('requested_issue_not_fixed',errors)
        # Actual numbers and tools cannot be delegated to a permissive review.
        errors=candidate_issues('Built 20 Python tools.', ['Built 30 Java tools.'], ['length'],semantic_review=True)
        self.assertIn('numbers',errors)
        self.assertIn('technologies',errors)

    def test_split_is_a_single_atomic_proposal_with_all_source_facts(self):
        result,call=self.run_plan(SPLIT)
        self.assertEqual(result['status'],'review_required')
        self.assertEqual(result['unresolved'],[])
        self.assertEqual(result['bullets'][0]['replacement_lines'],SPLIT)
        self.assertEqual(result['bullets'][0]['sources'],[SOURCE])
        self.assertTrue(all(len(t.split())<=38 for t in SPLIT))
        self.assertTrue(all(c.kwargs['task']=='refine' for c in call.call_args_list))

    def test_echo_and_still_long_rewrite_are_not_improvements(self):
        for lines in [[SOURCE],[SOURCE.replace('Built','Developed',1)]]:
            result,call=self.run_plan(lines)
            self.assertEqual(result['status'],'no_safe_improvement')
            self.assertEqual(result['bullets'],[])
            self.assertEqual(result['unresolved'][0]['issues'],['length'])
            self.assertEqual(call.call_count,2)

    def test_shorter_text_cannot_drop_tools_or_invent_measurements(self):
        for lines in [['Built a dashboard.'],['Built a Python dashboard with 99% accuracy.']]:
            result,_=self.run_plan(lines)
            self.assertEqual(result['bullets'],[])
            self.assertGreater(result['rejected'],0)

    def test_unverified_paraphrase_is_not_returned_as_a_success(self):
        # A compact paraphrase outside the literal edit contract needs a separate review.
        rewrite=['Created a Python dashboard displaying temperature measurements from test equipment for research team review during scheduled checks.',
                 'Recorded incoming reading timestamps in PostgreSQL, preserving the original collected observation sequence.']
        result,_=self.run_plan(rewrite,review=False)
        self.assertEqual(result['bullets'],[])

    def test_timeout_has_explicit_status_and_no_unchanged_suggestions(self):
        with patch('backend.app.services.cv_refinement.request_structured',side_effect=OllamaTimeoutError('test')):
            result=write_bullets(WriterRequest(text=SOURCE,field='description',issues=['length']))
        self.assertEqual(result['status'],'unavailable')
        self.assertEqual(result['bullets'],[])
        self.assertEqual(result['error_message'],'test')

    def test_partial_success_survives_a_later_api_error(self):
        plan=RewritePlan(rewrites=[Rewrite(source_id='f0',lines=SPLIT),Rewrite(source_id='f1',lines=[SOURCE+' Extra laboratory context.'])])
        with patch('backend.app.services.cv_refinement.request_structured',side_effect=[plan,verdict(),OllamaTimeoutError('API unavailable')]):
            result=write_bullets(WriterRequest(text=SOURCE+'\n'+SOURCE+' Extra laboratory context.',field='description',issues=['length']))
        self.assertEqual(result['status'],'review_required')
        self.assertEqual(len(result['bullets']),1)
        self.assertEqual(result['bullets'][0]['sources'],[SOURCE])
        self.assertEqual(result['unresolved'][0]['source_id'],'f1')
        self.assertEqual(result['error_message'],'API unavailable')

    def test_concise_can_edit_a_bullet_that_already_meets_length_limit(self):
        source='Built a dashboard using Python and PostgreSQL for the purpose of displaying temperature measurements.'
        shorter='Built a Python and PostgreSQL dashboard displaying temperature measurements.'
        echo=RewritePlan(rewrites=[Rewrite(source_id='f0',lines=[source])])
        plan=RewritePlan(rewrites=[Rewrite(source_id='f0',lines=[shorter])])
        with patch('backend.app.services.cv_refinement.request_structured',side_effect=[echo,plan,verdict()]) as model:
            result=write_bullets(WriterRequest(text=source,field='description',style='concise'))
        self.assertEqual(model.call_count,3)
        self.assertEqual(result['status'],'review_required')
        self.assertEqual(result['bullets'][0]['replacement_lines'],[shorter])
        self.assertEqual(result['unresolved'],[])

    def test_punctuation_is_fixed_without_calling_model(self):
        with patch('backend.app.services.cv_refinement.request_structured') as model:
            result=write_bullets(WriterRequest(text='kiểm thử biểu mẫu',field='description',issues=['punctuation']))
        model.assert_not_called()
        self.assertEqual(result['bullets'][0]['replacement_lines'],['Kiểm thử biểu mẫu.'])

    def test_unknown_or_duplicate_source_id_cannot_replace_work(self):
        for rewrites in [[Rewrite(source_id='unknown',lines=SPLIT)],
                         [Rewrite(source_id='f0',lines=SPLIT),Rewrite(source_id='f0',lines=SPLIT)]]:
            with patch('backend.app.services.cv_refinement.request_structured',return_value=RewritePlan(rewrites=rewrites)):
                result=write_bullets(WriterRequest(text=SOURCE,field='description',issues=['length']))
            self.assertEqual(result['bullets'],[])

    def test_word_cut_cannot_pass_as_a_fact_preserving_split(self):
        words=SOURCE.split()
        result,call=self.run_plan([' '.join(words[:38])+'.',' '.join(words[38:])])
        self.assertEqual(result['bullets'],[])
        self.assertEqual(call.call_count,2)

    def test_literal_split_still_requires_sentence_and_scope_review(self):
        plan=RewritePlan(rewrites=[Rewrite(source_id='f0',lines=SPLIT)])
        bad=verdict();bad.reviews[0].each_line_is_complete=False
        with patch('backend.app.services.cv_refinement.request_structured',side_effect=[plan,bad,plan,bad]) as call:
            result=write_bullets(WriterRequest(text=SOURCE,field='description',issues=['length']))
        self.assertEqual(call.call_count,4)
        self.assertEqual(result['bullets'],[])

    def test_conciseness_cannot_remove_qualifiers_or_version_control(self):
        source='Implemented continuous monitoring and version control for approved documents (audit history).'
        errors=candidate_issues(source,['Implemented monitoring for documents.'],['length'])
        self.assertIn('preserve_source_detail:continuous',errors)
        self.assertIn('preserve_source_detail:version control',errors)
        self.assertIn('preserve_source_detail:approved',errors)
        self.assertIn('preserve_source_detail:audit history',errors)

    def test_all_true_flags_cannot_override_reported_omitted_fact(self):
        plan=RewritePlan(rewrites=[Rewrite(source_id='f0',lines=SPLIT)])
        bad=verdict();bad.reviews[0].omitted_facts=['A source fact is missing.']
        with patch('backend.app.services.cv_refinement.request_structured',side_effect=[plan,bad,plan,bad]):
            result=write_bullets(WriterRequest(text=SOURCE,field='description',issues=['length']))
        self.assertEqual(result['bullets'],[])

    def test_only_requested_issue_and_count_are_targeted(self):
        with patch('backend.app.services.cv_refinement.request_structured') as model:
            result=write_bullets(WriterRequest(text=SOURCE,field='description',issues=['pronoun']))
        model.assert_not_called()
        self.assertEqual(result['status'],'unchanged')


class SplitPersistenceTests(unittest.TestCase):
    from backend.tests.test_profile_drafts import ProfileDraftTests
    setUp=ProfileDraftTests.setUp

    def test_split_applies_and_saves_with_original_source_refs(self):
        from backend.app.db import profile_repository as profiles
        from backend.app.schemas.profile import MasterProfile
        from backend.app.schemas.resume import ResumeStart,ResumeSave,Presentation
        from backend.app.services import resumes,resume_writer
        profile=MasterProfile(contact={},experience=[],education=[],involvement=[],skills=[],project=[dict(id='p1',project_name='Synthetic laboratory dashboard',description=[SOURCE,'Wrote test documentation.'])])
        profiles.save_master_profile('splitfixture',profile,profiles.DEFAULT_STORAGE_DIR)
        draft=resumes.start(ResumeStart(profile_id='splitfixture'))
        entry=draft['document']['sections'][0]['entries'][0]
        generated=dict(bullets=[dict(text='\n'.join(SPLIT),replacement_lines=SPLIT,sources=[SOURCE],source_ids=['f0'])])
        with patch('backend.app.services.resume_writer.write_bullets',return_value=generated):
            proposal=resume_writer.preview(draft['resume_id'],resume_writer.ResumeWriterRequest(expected_version=1,section='project',entry_id=entry['source_entry_id'],issues=['length']))
        updated=resume_writer.apply(draft['resume_id'],resume_writer.ResumeWriterApply(expected_version=1,proposal_id=proposal['proposal_id'],selected=[0]))
        bullets=updated['document']['sections'][0]['entries'][0]['bullets']
        self.assertEqual([b['text'] for b in bullets],SPLIT+['Wrote test documentation.'])
        self.assertEqual(bullets[0]['source_refs'],entry['bullets'][0]['source_refs'])
        self.assertEqual(bullets[1]['source_refs'],entry['bullets'][0]['source_refs'])
        saved=resumes.save(draft['resume_id'],ResumeSave(expected_version=2,title='Synthetic edited',document=updated['document'],presentation=Presentation()))
        self.assertEqual(saved['document'],updated['document'])
