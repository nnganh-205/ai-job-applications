import unittest
from unittest.mock import patch
from backend.app.services.cv_writer import WriterRequest,WriterPlan,WriterBullet,write_bullets
from backend.app.services.assistant_intake import blank_intake,collect
from backend.app.schemas.assistant import IntentDecision
from backend.tests.test_resumes import ResumeTests
from backend.app.services import resumes,resume_writer
from backend.app.schemas.cv import CVDocument
from backend.app.schemas.resume import ResumeSave,Presentation
from backend.app.db.profile_revision_repository import RevisionConflict

class WriterTests(unittest.TestCase):
    def test_context_matching_work_text_does_not_hide_actual_work(self):
        from backend.app.services.cv_writer import facts_for
        request = WriterRequest(entry={'project_name': 'Kiểm thử giao diện'}, text='Kiểm thử giao diện', field='description')
        self.assertEqual([f['kind'] for f in facts_for(request)], ['context', 'work'])
        self.assertNotEqual(write_bullets(request, use_model=False)['status'], 'needs_input')

    def test_output_schema_only_allows_provided_evidence_and_requested_count(self):
        from backend.app.services.cv_writer import facts_for, writer_plan_schema
        from pydantic import ValidationError
        facts = facts_for(WriterRequest(entry={'project_name': 'Blog'}, text='Built a Python API.', field='description'))
        schema = writer_plan_schema(facts, 1)
        valid = {'text': 'Developed a Python API.', 'source_ids': ['f1']}
        schema.model_validate({'bullets': [valid]})
        for bullets in ([{**valid, 'source_ids': ['invented']}], [{**valid, 'source_ids': ['f0']}], [valid, valid]):
            with self.subTest(bullets=bullets), self.assertRaises(ValidationError):
                schema.model_validate({'bullets': bullets})
    def test_title_alone_needs_tasks_not_stereotypical_bullets(self):
        r=write_bullets(WriterRequest(entry={'job_title':'AI Engineer','company':'Demo'}),use_model=False)
        self.assertEqual(r['status'],'needs_input');self.assertEqual(r['bullets'],[])
        self.assertIn('trực tiếp',r['questions'][0])

    def test_fallback_keeps_source_and_does_not_invent_metrics(self):
        r=write_bullets(WriterRequest(tasks='mình hỗ trợ xây dựng giao diện bằng React',count=6),use_model=False)
        self.assertEqual(len(r['bullets']),1)
        self.assertIn('hỗ trợ',r['bullets'][0]['text'].lower())
        self.assertEqual(r['bullets'][0]['sources'],['mình hỗ trợ xây dựng giao diện bằng React'])
        self.assertNotIn('%',r['bullets'][0]['text'])

    def test_invalid_refs_and_added_metrics_are_rejected(self):
        plan=WriterPlan(bullets=[WriterBullet(text='Tăng hiệu suất 50% bằng Python',source_ids=['f0']),WriterBullet(text='Triển khai hệ thống',source_ids=['invented'])])
        with patch('backend.app.services.cv_writer.request_structured',return_value=plan):
            r=write_bullets(WriterRequest(tasks='mình làm giao diện bằng React'))
        self.assertEqual(r['rejected'],2);self.assertEqual(r['engine'],'editorial')
        self.assertNotIn('50%',r['bullets'][0]['text'])

    def test_valid_generation_has_per_bullet_sources(self):
        plan=WriterPlan(bullets=[WriterBullet(text='Phát triển giao diện bằng React.',source_ids=['f0'])])
        with patch('backend.app.services.cv_writer.request_structured',return_value=plan):
            r=write_bullets(WriterRequest(tasks='mình làm giao diện bằng React'))
        self.assertEqual(r['engine'],'model');self.assertEqual(len(r['bullets']),1)
        self.assertEqual(r['bullets'][0]['sources'],['mình làm giao diện bằng React'])

    def test_chat_writer_keeps_facts_until_approval(self):
        i=blank_intake();i['profile']['project']=[dict(project_name='Blog',description=['mình làm giao diện bằng React'])]
        r=collect({'cv_intake':i},IntentDecision(intent='build_cv'),'viết bullet cho dự án','task_'+'b'*32)
        self.assertEqual(r['intake']['profile'],i['profile'])
        self.assertTrue(r['wording_suggestions'][0]['bullet_sources'])
        accepted=collect({'cv_intake':r['_intake']},IntentDecision(intent='build_cv'),'áp dụng cách viết','task_'+'a'*32)
        self.assertNotEqual(accepted['intake']['profile']['project'][0]['description'],i['profile']['project'][0]['description'])

    def test_chat_writer_requests_work_when_only_project_name(self):
        i=blank_intake();i['profile']['project']=[dict(project_name='Blog')]
        r=collect({'cv_intake':i},IntentDecision(intent='build_cv'),'viết bullet cho dự án','task_'+'c'*32)
        self.assertNotIn('wording_suggestions',r)
        self.assertIn('trực tiếp',r['text'])

class EditorWriterTests(unittest.TestCase):
    setUp=ResumeTests.setUp
    create=ResumeTests.create

    def test_non_adjacent_suggestions_keep_original_order_even_if_selected_backwards(self):
        from backend.app.db import profile_repository as profiles
        from backend.app.schemas.profile import MasterProfile
        from backend.app.schemas.resume import ResumeStart
        lines = ['Built Python API with 20 endpoints.', 'Maintained PostgreSQL database.', 'Built a Python API.']
        profile = MasterProfile(contact={}, experience=[], education=[], involvement=[], skills=[],
                                project=[dict(id='p1', project_name='Fixture', description=lines)])
        profiles.save_master_profile('orderfixture', profile, profiles.DEFAULT_STORAGE_DIR)
        draft = resumes.start(ResumeStart(profile_id='orderfixture'))
        entry = draft['document']['sections'][0]['entries'][0]
        bullets = [dict(text='Developed Python API with 20 endpoints.', sources=[lines[0]], source_ids=['f0']),
                   dict(text='Developed a Python API.', sources=[lines[2]], source_ids=['f2'])]
        with patch('backend.app.services.resume_writer.write_bullets', return_value=dict(bullets=bullets)):
            proposal = resume_writer.preview(draft['resume_id'], resume_writer.ResumeWriterRequest(
                expected_version=1, section='project', entry_id=entry['source_entry_id']))
        updated = resume_writer.apply(draft['resume_id'], resume_writer.ResumeWriterApply(
            expected_version=1, proposal_id=proposal['proposal_id'], selected=[1, 0]))
        actual = updated['document']['sections'][0]['entries'][0]['bullets']
        self.assertEqual([b['text'] for b in actual], [bullets[0]['text'], lines[1], bullets[1]['text']])
        self.assertEqual(actual[1], entry['bullets'][1])

    def proposal(self,d):
        e=d['document']['sections'][0]['entries'][0]
        result=dict(status='review_required',engine='model',questions=[],facts=[],rejected=0,bullets=[dict(text='Developed Python API with 20 endpoints.',source_ids=['f0'],sources=[e['bullets'][0]['text']],review_required=True)])
        with patch('backend.app.services.resume_writer.write_bullets',return_value=result):
            r=resume_writer.preview(d['resume_id'],resume_writer.ResumeWriterRequest(expected_version=d['version'],section='project',entry_id=e['source_entry_id']))
        return r

    def test_approved_writer_persists_and_can_be_saved_and_rendered(self):
        d=self.create();p=self.proposal(d)
        self.assertEqual(resumes.read(d['resume_id'])['document'],d['document'])
        updated=resume_writer.apply(d['resume_id'],resume_writer.ResumeWriterApply(expected_version=1,proposal_id=p['proposal_id'],selected=[0]))
        self.assertIn('Developed',updated['document']['sections'][0]['entries'][0]['bullets'][0]['text'])
        self.assertEqual(updated['baseline'],d['baseline'])
        saved=resumes.save(d['resume_id'],ResumeSave(expected_version=2,title='Edited',document=updated['document'],presentation=Presentation()))
        self.assertEqual(saved['version'],3)
        changed=CVDocument.model_validate(saved['document']);changed.sections[0].entries[0].bullets[0].text='Invented 999 endpoints'
        with self.assertRaises(ValueError):resumes.validate_document(saved,changed)

    def test_replace_selected_rewrite_keeps_unselected_originals(self):
        d=self.create();original=d['document']['sections'][0]['entries'][0]['bullets']
        p=self.proposal(d)
        updated=resume_writer.apply(d['resume_id'],resume_writer.ResumeWriterApply(expected_version=1,proposal_id=p['proposal_id'],selected=[0]))
        bullets=updated['document']['sections'][0]['entries'][0]['bullets']
        self.assertEqual(len(bullets),2)
        self.assertEqual(bullets[1],original[1])
        self.assertIn('Developed',bullets[0]['text'])

    def test_stale_proposal_cannot_override_saved_edits(self):
        d=self.create();p=self.proposal(d)
        resumes.save(d['resume_id'],ResumeSave(expected_version=1,title='New title',document=d['document'],presentation=Presentation()))
        with self.assertRaises(RevisionConflict):resume_writer.apply(d['resume_id'],resume_writer.ResumeWriterApply(expected_version=1,proposal_id=p['proposal_id'],selected=[0]))

    def test_proposal_from_before_save_is_stale_even_with_new_version(self):
        d=self.create();p=self.proposal(d)
        resumes.save(d['resume_id'],ResumeSave(expected_version=1,title='New title',document=d['document'],presentation=Presentation()))
        with self.assertRaises(RevisionConflict):resume_writer.apply(d['resume_id'],resume_writer.ResumeWriterApply(expected_version=2,proposal_id=p['proposal_id'],selected=[0]))

    def test_append_keeps_existing_bullets_and_adds_only_selected_proposal(self):
        d=self.create();p=self.proposal(d)
        before=d['document']['sections'][0]['entries'][0]['bullets']
        updated=resume_writer.apply(d['resume_id'],resume_writer.ResumeWriterApply(expected_version=1,proposal_id=p['proposal_id'],selected=[0],mode='append'))
        after=updated['document']['sections'][0]['entries'][0]['bullets']
        self.assertEqual(after[:len(before)],before)
        self.assertEqual(len(after),len(before)+1)
        resumes.validate_document(updated,CVDocument.model_validate(updated['document']))

class WriterCompletenessTests(unittest.TestCase):
    def test_oversized_source_is_not_silently_cut_before_editing(self):
        with patch('backend.app.services.cv_writer.request_structured') as model:
            result=write_bullets(WriterRequest(text='\n'.join(f'Việc số {i}' for i in range(41))))
        model.assert_not_called()
        self.assertEqual(result['status'],'needs_input')
        self.assertEqual(result['bullets'],[])

    def test_signed_number_is_not_treated_as_a_bullet_marker(self):
        from backend.app.services.cv_writer import facts_for
        request=WriterRequest(text='-3 °C là nhiệt độ mẫu khi ghi nhận')
        self.assertTrue(facts_for(request)[0]['text'].startswith('-3'))

    def test_explicit_chat_writer_keeps_unedited_lines(self):
        intake=blank_intake()
        lines=['mình làm giao diện bằng React','mình kiểm thử biểu mẫu','mình viết tài liệu','mình sửa lỗi hiển thị','mình ghi phản hồi']
        intake['profile']['project']=[dict(project_name='Blog',description=lines)]
        generated=dict(bullets=[dict(text='Phát triển giao diện bằng React.',sources=[lines[0]])],questions=[])
        with patch('backend.app.services.cv_writer.write_bullets',return_value=generated):
            result=collect({'cv_intake':intake},IntentDecision(intent='build_cv'),'viết bullet cho dự án','task_'+'f'*32)
        self.assertEqual(result['wording_suggestions'][0]['proposed'][1:],lines[1:])
        accepted=collect({'cv_intake':result['_intake']},IntentDecision(intent='build_cv'),'áp dụng cách viết','task_'+'1'*32)
        self.assertEqual(accepted['intake']['profile']['project'][0]['description'][1:],lines[1:])

    def test_repair_preserves_missing_limit_without_fallback(self):
        before='mình hỗ trợ kiểm thử giao diện; không phụ trách backend'
        bad=WriterPlan(bullets=[WriterBullet(text='Hỗ trợ kiểm thử giao diện.',source_ids=['f0'])])
        fixed=WriterPlan(bullets=[WriterBullet(text='Hỗ trợ kiểm thử giao diện; không phụ trách backend.',source_ids=['f0'])])
        with patch('backend.app.services.cv_writer.request_structured',side_effect=[bad,fixed]) as call:
            result=write_bullets(WriterRequest(text=before,field='description'))
        self.assertEqual(call.call_count,2)
        self.assertTrue(result['repair_attempted'])
        self.assertEqual(result['engine'],'model')
        self.assertTrue(result['complete'])
        self.assertIn('không phụ trách backend',result['bullets'][0]['text'])

    def test_limit_cannot_be_reattributed_to_another_task(self):
        before='mình viết báo cáo; không viết kiểm thử; chưa đo hiệu năng'
        swapped='Viết báo cáo; không đo hiệu năng; chưa viết kiểm thử.'
        plan=WriterPlan(bullets=[WriterBullet(text=swapped,source_ids=['f0'])])
        with patch('backend.app.services.cv_writer.request_structured',return_value=plan):
            result=write_bullets(WriterRequest(text=before,field='description'))
        self.assertEqual(result['engine'],'editorial')
        self.assertIn('không viết kiểm thử',result['bullets'][0]['text'])
        self.assertIn('chưa đo hiệu năng',result['bullets'][0]['text'])

    def test_overflow_is_explicit_and_mixed_origin_is_not_model_only(self):
        plan=WriterPlan(bullets=[WriterBullet(text='Phát triển giao diện bằng React.',source_ids=['f0'])])
        request=WriterRequest(text='mình làm giao diện bằng React\nmình hỗ trợ kiểm thử\nmình viết tài liệu',field='description',count=2)
        with patch('backend.app.services.cv_writer.request_structured',return_value=plan):result=write_bullets(request)
        self.assertEqual(result['engine'],'mixed')
        self.assertFalse(result['complete'])
        self.assertEqual([f['text'] for f in result['remaining_facts']],['mình viết tài liệu'])

    def test_broad_ownership_still_asks_for_actual_work(self):
        r=write_bullets(WriterRequest(tasks='mình làm hết mọi thứ'),use_model=False)
        self.assertEqual(r['status'],'needs_input')
        self.assertIn('trực tiếp',r['questions'][0])

    def test_partial_model_rejection_keeps_uncovered_source_when_room(self):
        plan=WriterPlan(bullets=[WriterBullet(text='Thực hiện giao diện.',source_ids=['f1'])])
        with patch('backend.app.services.cv_writer.request_structured',return_value=plan):
            r=write_bullets(WriterRequest(tasks='mình hỗ trợ kiểm thử\nmình làm giao diện',count=2))
        self.assertEqual(len(r['bullets']),2)
        self.assertTrue(any('hỗ trợ' in b['text'].lower() for b in r['bullets']))

    def test_do_not_ask_tools_already_stated_in_work(self):
        r=write_bullets(WriterRequest(tasks='mình làm giao diện bằng React'),use_model=False)
        self.assertFalse(any('công cụ' in q for q in r['questions']))

class ScopedWriterTests(unittest.TestCase):
    def test_scoped_field_cannot_pull_work_tools_or_results_from_siblings(self):
        request=WriterRequest(field='contributions',text='mình hỗ trợ kiểm thử giao diện',entry={'description':['Built Python backend'], 'technologies':['Python'], 'outcomes':['Increased revenue 90%']})
        result=write_bullets(request,use_model=False)
        self.assertEqual(len(result['bullets']),1)
        self.assertNotIn('Python',str(result['facts']))
        self.assertNotIn('90%',str(result['facts']))
        self.assertIn('hỗ trợ',result['bullets'][0]['text'].lower())

    def test_invented_ownership_and_unmeasured_achievement_are_rejected(self):
        for text in ('Chủ trì kiểm thử giao diện.', 'Tối ưu hiệu suất giao diện.'):
            with self.subTest(text=text), patch('backend.app.services.cv_writer.request_structured',return_value=WriterPlan(bullets=[WriterBullet(text=text,source_ids=['f0'])])):
                result=write_bullets(WriterRequest(field='description',text='mình kiểm thử giao diện'))
                self.assertEqual(result['rejected'],1)
                self.assertEqual(result['engine'],'editorial')

    def test_scoped_selected_text_rejects_sibling_claim_even_when_model_returns_it(self):
        plan=WriterPlan(bullets=[WriterBullet(text='Phát triển Python API tăng doanh thu 90%.',source_ids=['f0'])])
        with patch('backend.app.services.cv_writer.request_structured',return_value=plan):
            result=write_bullets(WriterRequest(field='description',text='mình hỗ trợ giao diện bằng React',entry={'achievements':['Tăng doanh thu 90% bằng Python API']}))
        self.assertEqual(result['rejected'],1)
        self.assertNotIn('90%',result['bullets'][0]['text'])
