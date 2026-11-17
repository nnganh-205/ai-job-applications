import unittest
from unittest.mock import Mock, patch
from ai.agents.cv_semantics import Alignment,SemanticReview,semantic_edit
from backend.app.services.cv_polish import PolishRequest,PolishOutput,polish
from backend.app.services.cv_writer import WriterRequest,WriterPlan,WriterBullet,write_bullets


def verdict(source,rewrite,**flags):
    values=dict(equivalent=True,all_source_facts_retained=True,no_added_claims=True,
                alignments=[Alignment(source_quote=source,rewrite_quote=rewrite,same_action=True,same_object=True,same_actor_and_scope=True,same_quantity_and_result=True)])
    values.update(flags);return SemanticReview(**values)

class SemanticTests(unittest.TestCase):
    def test_new_paraphrase_requires_independent_verifier(self):
        a='mình ghi chép thông tin đơn hàng trong Excel';b='Ghi nhận thông tin đơn hàng trong Excel.'
        judge=Mock(return_value=verdict(a,b));r=semantic_edit(a,b,judge)
        self.assertTrue(r['accepted']);self.assertEqual(r['method'],'semantic_model_review')
        self.assertEqual(judge.call_args.kwargs['task'],'verifier')

    def test_reviewer_cannot_override_hard_failures(self):
        judge=Mock(side_effect=AssertionError('must not call'))
        for a,b in [('Hỗ trợ kiểm thử.','Chủ trì kiểm thử.'),('Phối hợp chuẩn bị 37 thẻ tên.','Chuẩn bị 37 thẻ tên.'),('Ghi 12 phiếu.','Ghi 21 phiếu.'),('Đối chiếu mã kiện hàng và ghi số lượng phiếu.','Đối chiếu phiếu và ghi số lượng mã kiện hàng.')]:
            with self.subTest(b=b):self.assertFalse(semantic_edit(a,b,judge)['accepted'])
        judge.assert_not_called()

    def test_invented_or_partial_evidence_cannot_clear_rewrite(self):
        a='ghi chép thông tin đơn hàng trong Excel';b='Ghi nhận thông tin đơn hàng trong Excel.'
        for review in [verdict('not in source',b),verdict('Excel','Excel'),verdict(a,b,no_added_claims=False),verdict(a,b,all_source_facts_retained=False)]:
            with self.subTest(review=review):self.assertFalse(semantic_edit(a,b,Mock(return_value=review))['accepted'])

    def test_writer_can_use_verified_restructured_sentence(self):
        a='mình ghi chép thông tin đơn hàng trong Excel';b='Ghi nhận thông tin đơn hàng trong Excel.'
        with patch('backend.app.services.cv_writer.request_structured',return_value=WriterPlan(bullets=[WriterBullet(text=b,source_ids=['f0'])])),patch('ai.agents.cv_semantics.request_structured',return_value=verdict(a,b)) as judge:
            r=write_bullets(WriterRequest(text=a,field='description'))
        self.assertEqual(r['engine'],'model');self.assertEqual(r['bullets'][0]['text'],b)
        self.assertEqual(r['bullets'][0]['verification'],'semantic_model_review');self.assertEqual(judge.call_count,1)

    def test_polish_can_use_verified_restructured_sentence(self):
        a='mình ghi chép thông tin đơn hàng trong Excel';b='Ghi nhận thông tin đơn hàng trong Excel.'
        with patch('backend.app.services.cv_polish.request_structured',return_value=PolishOutput(text=b)),patch('ai.agents.cv_semantics.request_structured',return_value=verdict(a,b)):
            r=polish(PolishRequest(text=a))
        self.assertEqual(r['engine'],'model');self.assertEqual(r['verification'],'semantic_model_review')
        self.assertEqual(r['original'],a)

class ProfessionalInputTests(unittest.TestCase):
    def test_no_redundant_method_question_for_nontechnical_tools(self):
        for text in ['mình dùng bảng tính để ghi lịch phỏng vấn','mình thiết kế giao diện bằng Figma','mình dùng Excel theo dõi đơn hàng']:
            with self.subTest(text=text):
                r=write_bullets(WriterRequest(text=text),use_model=False)
                self.assertFalse(any('công cụ' in q for q in r['questions']))

    def test_do_not_request_results_already_declared_unmeasured(self):
        r=write_bullets(WriterRequest(text='mình viết nội dung sản phẩm; chưa đo tỷ lệ chuyển đổi'),use_model=False)
        self.assertFalse(any('kết quả thực tế' in q for q in r['questions']))

class MethodScopeTests(unittest.TestCase):
    def test_phone_method_must_not_be_dropped_even_if_reviewer_agrees(self):
        a='mình dùng Excel để cập nhật đơn hàng và gọi điện xác nhận thông tin giao hàng'
        b='Cập nhật đơn hàng và xác nhận thông tin giao hàng bằng Excel.'
        judge=Mock(side_effect=AssertionError('Hard source failure'))
        r=semantic_edit(a,b,judge);self.assertFalse(r['accepted']);judge.assert_not_called()

    def test_small_reviewer_cannot_clear_tool_moving_across_actions(self):
        a='mình dùng bảng tính để ghi lịch phỏng vấn và gửi email nhắc lịch'
        b='Ghi lịch phỏng vấn và gửi email nhắc lịch bằng bảng tính.'
        judge=Mock(side_effect=AssertionError('Ambiguous tool scope'))
        r=semantic_edit(a,b,judge);self.assertFalse(r['accepted']);self.assertEqual(r['method'],'compound_scope_guard');judge.assert_not_called()

from backend.tests import test_resumes as resume_fixtures

class SemanticApprovalTests(unittest.TestCase):
    setUp=resume_fixtures.ResumeTests.setUp
    create=resume_fixtures.ResumeTests.create

    def test_verified_paraphrase_can_be_approved_and_saved_without_losing_other_work(self):
        import json
        from backend.app.services import resume_writer,resumes
        from backend.app.schemas.resume import ResumeSave,Presentation
        from backend.app.schemas.cv import CVDocument
        draft=self.create();entry=draft['document']['sections'][0]['entries'][0]
        def generate(messages,schema,**kwargs):
            payload=json.loads(messages[1]['content'])
            return WriterPlan(bullets=[WriterBullet(text=f['text'].replace('Built','Implemented'),source_ids=[f['id']]) for f in payload['facts'] if f['kind']=='work'])
        source=entry['bullets'][0]['text'];rewrite=source.replace('Built','Implemented')
        with patch('backend.app.services.cv_writer.request_structured',side_effect=generate),patch('ai.agents.cv_semantics.request_structured',return_value=verdict(source,rewrite)):
            preview=resume_writer.preview(draft['resume_id'],resume_writer.ResumeWriterRequest(expected_version=1,section='project',entry_id=entry['source_entry_id']))
        self.assertEqual(resumes.read(draft['resume_id'])['document'],draft['document'])
        self.assertEqual(preview['bullets'][0]['verification'],'semantic_model_review')
        applied=resume_writer.apply(draft['resume_id'],resume_writer.ResumeWriterApply(expected_version=1,proposal_id=preview['proposal_id'],selected=[0]))
        bullets=applied['document']['sections'][0]['entries'][0]['bullets']
        self.assertEqual(bullets[0]['text'],rewrite);self.assertEqual(bullets[1],entry['bullets'][1])
        saved=resumes.save(draft['resume_id'],ResumeSave(expected_version=applied['version'],title='Semantic edit',document=CVDocument.model_validate(applied['document']),presentation=Presentation()))
        self.assertEqual(saved['baseline'],draft['baseline'])

class ClauseAlignmentTests(unittest.TestCase):
    def test_compound_sentence_can_restructure_each_action_without_moving_tools(self):
        a='mình dùng bảng tính để ghi lịch phỏng vấn và gửi email nhắc lịch'
        b='Ghi lịch phỏng vấn bằng bảng tính; gửi email nhắc lịch.'
        judge=Mock(side_effect=AssertionError('No model needed for identical facts'))
        result=semantic_edit(a,b,judge)
        self.assertTrue(result['accepted']);self.assertEqual(result['method'],'clause_aligned_review');judge.assert_not_called()

    def test_sequence_cannot_be_changed_into_unordered_list(self):
        a='mình ghi nhận yêu cầu rồi gửi email phản hồi'
        b='Ghi nhận yêu cầu và gửi email phản hồi.'
        self.assertFalse(semantic_edit(a,b,Mock(side_effect=AssertionError()))['accepted'])

    def test_partial_recovery_preserves_a_good_rewrite_and_restores_phone_method(self):
        from ai.agents.cv_clauses import recover_clauses
        from backend.app.services.cv_polish import clean_cv_sentence
        a='mình dùng Excel để theo dõi đơn hàng và gọi điện xác nhận giao hàng'
        b='Theo dõi đơn hàng bằng Excel; xác nhận giao hàng.'
        cache={}
        validate=lambda x,y:semantic_edit(x,y,Mock(side_effect=AssertionError('closed structural proof')),cache=cache)
        restored=recover_clauses(a,b,validate,clean_cv_sentence)
        self.assertIsNotNone(restored);self.assertIn('Theo dõi đơn hàng bằng Excel',restored)
        self.assertIn('gọi điện',restored.lower());self.assertTrue(validate(a,restored)['accepted'])

class PartialModelRecoveryTests(unittest.TestCase):
    def test_writer_keeps_good_clause_instead_of_discarding_whole_candidate(self):
        source='mình dùng Excel để ghi chép thông tin đơn hàng và gọi điện xác nhận giao hàng'
        candidate='Ghi nhận thông tin đơn hàng bằng Excel; xác nhận giao hàng.'
        plan=WriterPlan(bullets=[WriterBullet(text=candidate,source_ids=['f0'])])
        with patch('backend.app.services.cv_writer.request_structured',return_value=plan) as model,patch('ai.agents.cv_semantics.request_structured',side_effect=lambda messages,schema,**kwargs:verdict(__import__('json').loads(messages[-1]['content'])['s0'],__import__('json').loads(messages[-1]['content'])['t0'])):
            result=write_bullets(WriterRequest(text=source,field='description'))
        self.assertEqual(model.call_count,1);self.assertEqual(result['engine'],'mixed')
        self.assertEqual(result['bullets'][0]['origin'],'mixed');self.assertIn('Ghi nhận thông tin đơn hàng bằng Excel',result['bullets'][0]['text'])
        self.assertIn('gọi điện',result['bullets'][0]['text']);self.assertTrue(result['complete'])

    def test_polish_can_preserve_a_verified_edit_while_restoring_omitted_method(self):
        source='mình dùng Excel để ghi chép thông tin đơn hàng và gọi điện xác nhận giao hàng'
        with patch('backend.app.services.cv_polish.request_structured',return_value=PolishOutput(text='Ghi nhận thông tin đơn hàng bằng Excel; xác nhận giao hàng.')) as model,patch('ai.agents.cv_semantics.request_structured',side_effect=lambda messages,schema,**kwargs:verdict(__import__('json').loads(messages[-1]['content'])['s0'],__import__('json').loads(messages[-1]['content'])['t0'])):
            result=polish(PolishRequest(text=source))
        self.assertEqual(model.call_count,1);self.assertEqual(result['engine'],'mixed')
        self.assertIn('Ghi nhận thông tin đơn hàng bằng Excel',result['proposed']);self.assertIn('gọi điện',result['proposed'])

class ActionCommaTests(unittest.TestCase):
    def test_action_commas_can_align_without_splitting_a_tool_list(self):
        from ai.agents.cv_clauses import clauses
        self.assertEqual(len(clauses('Dùng Python, Pandas để đọc dữ liệu')[0]),1)
        self.assertEqual(len(clauses('Viết API bằng FastAPI, lưu dữ liệu vào PostgreSQL')[0]),2)
        a='mình dùng FastAPI để viết API và lưu dữ liệu vào PostgreSQL'
        b='Viết API bằng FastAPI, lưu dữ liệu vào PostgreSQL.'
        self.assertTrue(semantic_edit(a,b,Mock(side_effect=AssertionError('Structural equivalence')))['accepted'])

class CompactReviewTests(unittest.TestCase):
    def test_every_fact_aspect_must_be_confirmed(self):
        from ai.agents.cv_semantics import CompactReview
        a='mình ghi chép phản hồi của khách hàng';b='Ghi lại phản hồi của khách hàng.'
        fields=('same_action','same_object','same_actor_and_scope','same_methods','same_quantity_and_result','same_conditions','no_added_claims')
        for field in fields:
            flags={f:True for f in fields};flags[field]=False
            review=CompactReview(source_ref='s0',rewrite_ref='t0',**flags)
            with self.subTest(field=field):self.assertFalse(semantic_edit(a,b,Mock(return_value=review))['accepted'])

    def test_review_cache_is_request_local(self):
        from ai.agents.cv_semantics import CompactReview
        a='mình ghi chép phản hồi của khách hàng';b='Ghi lại phản hồi của khách hàng.'
        flags=dict(same_action=True,same_object=True,same_actor_and_scope=True,same_methods=True,same_quantity_and_result=True,same_conditions=True,no_added_claims=True)
        judge=Mock(return_value=CompactReview(source_ref='s0',rewrite_ref='t0',**flags));cache={}
        semantic_edit(a,b,judge,cache=cache);semantic_edit(a,b,judge,cache=cache)
        self.assertEqual(judge.call_count,1)
        semantic_edit(a,b,judge,cache={});self.assertEqual(judge.call_count,2)

class CompoundApprovalTests(unittest.TestCase):
    setUp=resume_fixtures.ResumeTests.setUp

    def test_new_compound_wording_can_be_approved_without_changing_master_profile(self):
        import json
        from backend.app.services import resumes,resume_writer
        from backend.app.db import profile_repository as profiles
        from backend.app.schemas.profile import MasterProfile
        from backend.app.schemas.resume import ResumeStart,ResumeSave,Presentation
        from backend.app.schemas.cv import CVDocument
        text='mình dùng Excel để theo dõi đơn hàng và gọi điện xác nhận giao hàng'
        original=MasterProfile(contact={'full_name':'Fictional Fixture'},experience=[],education=[],involvement=[],skills=[],project=[dict(id='p1',project_name='Sales fixture',description=[text])])
        profiles.save_master_profile('compoundfixture',original,profiles.DEFAULT_STORAGE_DIR)
        draft=resumes.start(ResumeStart(profile_id='compoundfixture'));entry=draft['document']['sections'][0]['entries'][0]
        def model(messages,schema,**kwargs):
            facts=json.loads(messages[1]['content'])['facts'];work=next(f for f in facts if f['kind']=='work')
            return WriterPlan(bullets=[WriterBullet(text='Theo dõi đơn hàng bằng Excel; gọi điện xác nhận giao hàng.',source_ids=[work['id']])])
        with patch('backend.app.services.cv_writer.request_structured',side_effect=model):
            proposal=resume_writer.preview(draft['resume_id'],resume_writer.ResumeWriterRequest(expected_version=1,section='project',entry_id=entry['source_entry_id']))
        self.assertEqual(resumes.read(draft['resume_id'])['document'],draft['document'])
        applied=resume_writer.apply(draft['resume_id'],resume_writer.ResumeWriterApply(expected_version=1,proposal_id=proposal['proposal_id'],selected=[0]))
        saved=resumes.save(draft['resume_id'],ResumeSave(expected_version=2,title='Approved compound',document=CVDocument.model_validate(applied['document']),presentation=Presentation()))
        self.assertEqual(saved['baseline'],draft['baseline'])
        self.assertIn('gọi điện',saved['document']['sections'][0]['entries'][0]['bullets'][0]['text'])
        self.assertEqual(profiles.load_master_profile('compoundfixture',profiles.DEFAULT_STORAGE_DIR),original)

class QualificationGuardTests(unittest.TestCase):
    def test_model_cannot_invent_graduation_degree_or_seniority(self):
        judge=Mock(side_effect=AssertionError('Must be deterministic rejection'))
        for source,rewrite in [('mình đang học công nghệ thông tin','Cử nhân công nghệ thông tin.'),('mình là sinh viên công nghệ thông tin','Đã tốt nghiệp công nghệ thông tin.'),('Thực tập sinh phân tích dữ liệu.','Chuyên viên phân tích dữ liệu.'),('Junior Python developer.','Senior Python developer.')]:
            with self.subTest(source=source):self.assertFalse(semantic_edit(source,rewrite,judge)['accepted'])
        judge.assert_not_called()

    def test_whitespace_is_not_a_polishable_description(self):
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):PolishRequest(text='   ')

    def test_recovery_restores_a_sequence_connector_instead_of_discarding_correct_edits(self):
        from ai.agents.cv_clauses import recover_clauses
        from ai.agents.cv_fidelity import professional_wording
        from backend.app.services.cv_polish import clean_cv_sentence
        source='mình dùng Excel để đánh dấu sản phẩm sắp hết hàng rồi gửi danh sách cho người phụ trách'
        rewrite='Đánh dấu sản phẩm sắp hết hàng bằng Excel; gửi danh sách cho người phụ trách.'
        validate=lambda a,b:semantic_edit(a,b,Mock(side_effect=AssertionError('No model needed')))
        text=recover_clauses(source,rewrite,validate,lambda x:professional_wording(clean_cv_sentence(x)))
        self.assertIsNotNone(text);self.assertIn('sau đó gửi danh sách',text)
        self.assertTrue(validate(source,text)['accepted'])

class ProgressAndGoalTests(unittest.TestCase):
    def test_planned_or_ongoing_work_cannot_become_completed_work(self):
        judge=Mock(side_effect=AssertionError('No model can clear this change'))
        for source,rewrite in [('mình dự định phát triển trang web','Phát triển trang web.'),('mình đang triển khai ứng dụng','Đã triển khai ứng dụng.'),('mình dùng Excel để giảm sai sót','Giảm sai sót bằng Excel.')]:
            with self.subTest(source=source):self.assertFalse(semantic_edit(source,rewrite,judge)['accepted'])
        judge.assert_not_called()

    def test_editorial_renderer_does_not_turn_a_goal_into_a_result(self):
        from ai.agents.cv_fidelity import professional_wording
        source='Sử dụng Excel để giảm sai sót'
        self.assertEqual(professional_wording(source),source)

class ContactMethodTests(unittest.TestCase):
    def test_contact_channels_count_as_stated_methods(self):
        for text in ['mình tiếp nhận phản ánh qua điện thoại','mình gọi điện xác nhận đơn hàng','mình gửi email nhắc lịch phỏng vấn']:
            with self.subTest(text=text):
                result=write_bullets(WriterRequest(text=text),use_model=False)
                self.assertFalse(any('công cụ' in q for q in result['questions']))
