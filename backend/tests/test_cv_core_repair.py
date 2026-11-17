import json
import unittest
from unittest.mock import patch

from ai.agents.cv_grounding import check_rewrite
from ai.agents.cv_selection import SelectionPlan,SelectionLink,requirement_catalog,validate_selection
from ai.agents.cv_agent import plan_cv,source_document,bullet_catalog
from backend.app.schemas.cv import CVPlan,CVReview
from backend.app.schemas.profile import MasterProfile
from backend.app.services.cv_writer import WriterRequest,WriterPlan,WriterBullet,write_bullets


class ContentAnchorTests(unittest.TestCase):
    def test_losing_identifier_is_not_cleared_by_same_number_or_source_id(self):
        result=check_rewrite('Kiểm tra 33 mã kiện hàng bằng bảng tính.','Kiểm tra 33 kiện hàng bằng bảng tính.')
        self.assertEqual(result['status'],'rejected')
        self.assertIn('content_anchors',result['reason_codes'])

    def test_closed_object_equivalents_allow_paraphrasing(self):
        result=check_rewrite('Kiểm tra mã kiện hàng.','Đối chiếu ID kiện hàng.')
        self.assertNotEqual(result['status'],'rejected')
        result=check_rewrite('Chỉnh sửa mã nguồn bằng Python.','Biên tập source code bằng Python.')
        self.assertNotEqual(result['status'],'rejected')

    def test_document_and_material_are_not_interchangeable(self):
        self.assertEqual(check_rewrite('Đối chiếu hóa đơn.','Đối chiếu đơn hàng.')['status'],'rejected')
        self.assertEqual(check_rewrite('Kiểm kê vật tư.','Kiểm kê thiết bị.')['status'],'rejected')

    def test_writer_repairs_missing_object_before_returning_model_output(self):
        bad=WriterPlan(bullets=[WriterBullet(text='Kiểm tra 33 kiện hàng bằng bảng tính.',source_ids=['f0'])])
        fixed=WriterPlan(bullets=[WriterBullet(text='Kiểm tra 33 mã kiện hàng bằng bảng tính.',source_ids=['f0'])])
        with patch('backend.app.services.cv_writer.request_structured',side_effect=[bad,fixed]):
            result=write_bullets(WriterRequest(field='description',text='mình kiểm tra 33 mã kiện hàng bằng bảng tính'))
        self.assertTrue(result['repair_attempted']);self.assertEqual(result['engine'],'model')
        self.assertIn('mã kiện hàng',result['bullets'][0]['text'])


class SourceSelectionTests(unittest.TestCase):
    def document(self):
        profile=MasterProfile(contact={},experience=[],education=[],involvement=[],skills=[],project=[dict(project_name='Bài thực hành',description=[
            'Cắt 4 đoạn âm thanh.',
            'Phân loại 41 bản ghi theo mã tài liệu.',
            'Chuẩn bị 9 số đeo cho hoạt động thể thao.',
            'Đối chiếu 15 mục thiếu năm xuất bản.',
        ])])
        return source_document(profile,'fixture',language='vi')

    def requirements(self):
        return dict(technical_requirements=[dict(name='Tổ chức danh mục tài liệu',requirement_type='required',evidence='Tổ chức danh mục tài liệu')])

    def selection(self,document):
        catalog=bullet_catalog(document)
        return SelectionPlan(links=[SelectionLink(requirement_id='r0',source_ref=ref,quote=catalog[ref].text) for ref in (list(catalog)[1],list(catalog)[3])])

    def test_review_only_sees_selected_evidence_and_source_document_is_immutable(self):
        document=self.document();original=document.model_dump();selection=self.selection(document)
        selected=[link.source_ref for link in selection.links]
        review=CVPlan(selected_refs=selected,review=CVReview(items=[]))
        with patch('ai.agents.cv_agent.request_structured',return_value=review) as model:
            result,_=plan_cv(document,self.requirements())
        self.assertEqual(list(bullet_catalog(result)),selected)
        self.assertEqual(document.model_dump(),original)
        payload=json.loads(model.call_args_list[0].args[0][1]['content'])
        self.assertEqual(list(payload['catalog']),selected)
        self.assertEqual(payload['selected_source_refs'],selected)

    def test_nonexistent_or_misattributed_quotes_never_select_source(self):
        document=self.document();catalog=bullet_catalog(document);ref=next(iter(catalog))
        plan=SelectionPlan(links=[SelectionLink(requirement_id='r0',source_ref=ref,quote='Không có trong nguồn'),
                                  SelectionLink(requirement_id='fake',source_ref=ref,quote=catalog[ref].text)])
        selected,invalid=validate_selection(plan,catalog,requirement_catalog(self.requirements()))
        self.assertEqual(selected,[]);self.assertEqual(invalid,2)

    def test_no_job_match_does_not_create_a_false_tailored_cv(self):
        document=self.document()
        with patch('ai.agents.cv_agent.request_structured',return_value=SelectionPlan(links=[])) as model:
            result,review=plan_cv(document,dict(technical_requirements=[dict(name='Kubernetes',requirement_type='required')]))
        self.assertEqual(model.call_count,0)
        self.assertEqual(result,document)
        self.assertTrue(any('giữ nguyên CV nguồn' in text for text in review.warnings))

    def test_no_jd_or_review_mode_keeps_all_sources(self):
        document=self.document();refs=list(bullet_catalog(document))
        response=CVPlan(selected_refs=refs[:1],review=CVReview(items=[]))
        for requirements,mode in ((None,'generate'),(self.requirements(),'review')):
            with self.subTest(mode=mode),patch('ai.agents.cv_agent.request_structured',return_value=response) as model:
                result,_=plan_cv(document,requirements,mode)
                self.assertEqual(list(bullet_catalog(result)),refs)
                self.assertEqual(model.call_count,1)

    def test_denial_is_not_positive_skill_evidence(self):
        from backend.app.schemas.cv import CVBullet
        catalog={'x':CVBullet(text='Chưa sử dụng Python.',source_refs=['x'])}
        criteria=[dict(id='r0',text='Python')]
        plan=SelectionPlan(links=[SelectionLink(requirement_id='r0',source_ref='x',quote='Python.')])
        self.assertEqual(validate_selection(plan,catalog,criteria)[0],[])

    def test_or_group_does_not_require_both_alternatives(self):
        rows=requirement_catalog(dict(requirement_groups=[dict(operator='any',members=['Python','Java'],requirement_type='required')],
                                      required_skills=[dict(name='Python'),dict(name='Java')]))
        self.assertEqual(len(rows),1)
        self.assertIn('Một trong',rows[0]['text'])

    def test_each_requirement_has_a_global_evidence_limit(self):
        catalog=bullet_catalog(self.document())
        plan=SelectionPlan(links=[SelectionLink(requirement_id='r0',source_ref=ref,quote=bullet.text) for ref,bullet in catalog.items()])
        selected,_=validate_selection(plan,catalog,[dict(id='r0',text='Danh mục tài liệu')])
        self.assertEqual(len(selected),2)


if __name__=='__main__':unittest.main()
