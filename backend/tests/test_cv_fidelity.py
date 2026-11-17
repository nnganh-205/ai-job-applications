import unittest
from unittest.mock import patch
from ai.agents.cv_fidelity import assess_edit, professional_wording
from backend.app.services.cv_writer import WriterRequest, WriterPlan, WriterBullet, write_bullets, bullet_issues
from backend.app.services.cv_polish import PolishRequest, PolishOutput, polish
from ai.agents.cv_selection import SelectionPlan, SelectionLink, validate_selection
from backend.app.schemas.cv import CVBullet

class FidelityTests(unittest.TestCase):
    def test_ordered_relations_and_quantity_attribution(self):
        for before,after in [
            ('Đối chiếu mã kiện hàng và ghi số lượng phiếu.','Đối chiếu phiếu và ghi số lượng mã kiện hàng.'),
            ('Xử lý 12 phiếu và ghi nhận 4 hóa đơn.','Xử lý 4 phiếu và ghi nhận 12 hóa đơn.'),
            ('Gửi báo cáo cho An và nhận phiếu từ Bình.','Gửi phiếu cho An và nhận báo cáo từ Bình.'),
            ('Phối hợp chuẩn bị 37 thẻ tên.','Chuẩn bị 37 thẻ tên.'),
            ('Đối chiếu 12 nhãn vận chuyển.','Đối chiếu 12 vận chuyển.'),
            ('Kiểm thử biểu mẫu.','Kiểm thử biểu mẫu và bàn giao cho khách hàng.'),
        ]:
            with self.subTest(after=after):
                self.assertEqual(assess_edit(before,after)['status'],'unverified')
                self.assertTrue(bullet_issues(WriterBullet(text=after,source_ids=['f0']),{'f0':dict(id='f0',kind='work',text=before)}))

    def test_professional_equivalents_without_fact_invention(self):
        for before,after in [
            ('mình làm giao diện bằng React','Phát triển giao diện bằng React.'),
            ('tôi phối hợp ghi lại 12 phiếu','Cộng tác ghi nhận 12 phiếu.'),
            ('em đã dùng Python để xếp các tệp ảnh','Sử dụng Python để sắp xếp tệp ảnh.'),
        ]:
            with self.subTest(after=after):self.assertEqual(assess_edit(before,after)['status'],'verified_editorial')
        self.assertEqual(professional_wording('Thực hiện giao diện bằng React'),'Phát triển giao diện bằng React')

    def test_unknown_synonym_is_not_claimed_verified(self):
        self.assertEqual(assess_edit('Đếm cây trong vườn','Kiểm kê thực vật trong khuôn viên')['status'],'unverified')

    def test_real_writer_rejects_dropped_collaboration_then_repairs(self):
        before='mình phối hợp chuẩn bị 37 thẻ tên'
        bad=WriterPlan(bullets=[WriterBullet(text='Chuẩn bị 37 thẻ tên.',source_ids=['f0'])])
        good=WriterPlan(bullets=[WriterBullet(text='Phối hợp chuẩn bị 37 thẻ tên.',source_ids=['f0'])])
        with patch('backend.app.services.cv_writer.request_structured',side_effect=[bad,good]):result=write_bullets(WriterRequest(text=before))
        self.assertTrue(result['repair_attempted']);self.assertEqual(result['engine'],'model')
        self.assertIn('Phối hợp',result['bullets'][0]['text'])

    def test_fallback_is_useful_and_source_bound(self):
        r=write_bullets(WriterRequest(text='mình làm giao diện bằng React'),use_model=False)
        self.assertEqual(r['bullets'][0]['text'],'Phát triển giao diện bằng React.')
        self.assertEqual(r['bullets'][0]['origin'],'editorial')

    def test_polish_cannot_swap_relations_even_with_identical_bag_of_words(self):
        before='mình đối chiếu mã kiện hàng và ghi số lượng phiếu'
        with patch('backend.app.services.cv_polish.request_structured',return_value=PolishOutput(text='Đối chiếu phiếu và ghi số lượng mã kiện hàng')):
            result=polish(PolishRequest(text=before))
        self.assertEqual(result['engine'],'editorial');self.assertIn('đối chiếu mã kiện hàng',result['proposed'].lower())

class SelectionEvidenceTests(unittest.TestCase):
    def select(self,sources,requirement,reverse=False):
        catalog={str(i):CVBullet(text=s,source_refs=[str(i)]) for i,s in enumerate(sources)}
        links=[SelectionLink(requirement_id='r0',source_ref=ref,quote=b.text) for ref,b in catalog.items()]
        if reverse:links.reverse()
        return validate_selection(SelectionPlan(links=links),catalog,[dict(id='r0',text=requirement)])

    def test_denied_requirement_never_becomes_positive_evidence(self):
        for s in ['Chưa sử dụng Python.','Không có kinh nghiệm với Python.','Đã dùng Excel; chưa sử dụng Python.','Never used Python.']:
            with self.subTest(s=s):self.assertEqual(self.select([s],'Kinh nghiệm lập trình Python')[0],[])
        self.assertEqual(self.select(['Dùng Python xử lý tệp; chưa đo hiệu năng.'],'Kinh nghiệm lập trình Python')[0],['0'])

    def test_irrelevance_and_single_syllable_collisions(self):
        for text in ['Cắt 4 đoạn âm thanh.','Xử lý dữ liệu bằng Python.']:
            self.assertEqual(self.select([text],'Tổ chức danh mục tài liệu')[0],[])
        self.assertEqual(self.select(['Phân loại tài liệu theo mã.'],'Tổ chức danh mục tài liệu')[0],['0'])

    def test_ranking_is_not_first_two_and_is_permutation_invariant(self):
        source=['Dùng Python.','Dùng Docker.','Xây dựng Python API bằng Docker.']
        a=self.select(source,'Python API Docker')[0]
        self.assertIn('2',a);self.assertEqual(a,self.select(source,'Python API Docker',True)[0]);self.assertEqual(len(a),2)

class RetrievalContractTests(unittest.TestCase):
    def test_retrieval_keeps_late_evidence_without_model_call(self):
        from ai.agents.cv_selection import select_for_job
        model=unittest.mock.Mock(side_effect=AssertionError('No model selection'))
        source='Nội dung nền. '*80+'Dùng Python xử lý tệp.'
        catalog={'x':CVBullet(text=source,source_refs=['x'])}
        selected,_=select_for_job(catalog,dict(required_skills=[dict(name='Python')]),model)
        self.assertEqual(selected,['x']);model.assert_not_called()

    def test_negative_quote_cannot_borrow_a_different_positive_clause(self):
        catalog={'x':CVBullet(text='Dùng Python xử lý tệp; chưa có kinh nghiệm quản lý Python.',source_refs=['x'])}
        link=SelectionLink(requirement_id='r0',source_ref='x',quote='chưa có kinh nghiệm quản lý Python')
        self.assertEqual(validate_selection(SelectionPlan(links=[link]),catalog,[dict(id='r0',text='Python')])[0],[])

    def test_review_and_writer_use_the_same_relation_check(self):
        from ai.agents.cv_agent import review_text_valid
        self.assertFalse(review_text_valid('Đối chiếu mã kiện hàng và ghi số lượng phiếu.','Đối chiếu phiếu và ghi số lượng mã kiện hàng.'))
        self.assertFalse(review_text_valid('Phối hợp chuẩn bị 37 thẻ tên.','Chuẩn bị 37 thẻ tên.'))

class MethodFrameTests(unittest.TestCase):
    def test_tool_action_order_changes_without_changing_facts(self):
        for tool,task in [('Excel','theo dõi các đơn hàng'),('Figma','thiết kế giao diện ứng dụng'),('Công cụ Nội Bộ','xử lý phiếu yêu cầu'),('FastAPI','xây dựng API tiếp nhận hồ sơ')]:
            with self.subTest(tool=tool):
                source=f'mình dùng {tool} để {task}'
                rewrite=f'{task.capitalize()} bằng {tool}.'
                self.assertEqual(assess_edit(source,rewrite)['status'],'verified_editorial')
        self.assertEqual(assess_edit('mình dùng Python để xử lý 12 phiếu; chưa kiểm tra kết quả','Xử lý 12 phiếu bằng Python; chưa kiểm tra kết quả.')['status'],'verified_editorial')

    def test_frame_does_not_allow_new_task_or_method_or_results(self):
        source='mình dùng Excel để theo dõi các đơn hàng'
        for rewrite in ['Theo dõi các đơn hàng bằng Python.','Theo dõi hóa đơn bằng Excel.','Theo dõi các đơn hàng bằng Excel, giúp tăng doanh thu.']:
            with self.subTest(rewrite=rewrite):self.assertEqual(assess_edit(source,rewrite)['status'],'unverified')

class ProfessionalClauseRenderingTests(unittest.TestCase):
    def test_source_bound_renderer_leads_with_work_instead_of_generic_tool_use(self):
        source='Sử dụng Excel để cập nhật đơn hàng và gọi điện xác nhận giao hàng'
        text=professional_wording(source)
        self.assertEqual(text,'Cập nhật đơn hàng bằng Excel và gọi điện xác nhận giao hàng')
        self.assertEqual(assess_edit(source,text)['status'],'verified_editorial')
        self.assertEqual(assess_edit(source,'Cập nhật đơn hàng và gọi điện xác nhận giao hàng bằng Excel')['status'],'unverified')

    def test_renderer_retains_numbers_scope_and_original_sequence(self):
        source='Dùng Pandas để tìm 12 dòng thiếu dữ liệu rồi gửi báo cáo; chưa tự điền số liệu'
        text=professional_wording(source)
        self.assertIn('Tìm 12 dòng thiếu dữ liệu bằng Pandas sau đó gửi báo cáo',text)
        self.assertIn('chưa tự điền số liệu',text)
        self.assertEqual(assess_edit(source,text)['status'],'verified_editorial')
