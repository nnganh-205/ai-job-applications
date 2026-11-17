import unittest
from unittest.mock import patch
from backend.app.services.cv_polish import polish, PolishRequest, PolishOutput
from backend.app.services.assistant_intake import blank_intake,collect
from backend.app.schemas.assistant import IntentDecision, ProfilePatch

class PolishTests(unittest.TestCase):
    def test_model_cannot_echo_input_labels_or_leave_chat_pronouns(self):
        before='mình làm giao diện bằng React'
        with patch('backend.app.services.cv_polish.request_structured',return_value=PolishOutput(text='Trường: description; nội dung gốc: '+before)):
            result=polish(PolishRequest(text=before))
        self.assertEqual(result['engine'],'editorial')
        self.assertNotIn('Trường:',result['proposed'])
        with patch('backend.app.services.cv_polish.request_structured',return_value=PolishOutput(text=before)):
            result=polish(PolishRequest(text=before))
        self.assertFalse(result['proposed'].startswith('mình'))
        self.assertTrue(result['changed'])

    def test_repair_recovers_scope_on_second_model_attempt(self):
        before='mình hỗ trợ kiểm thử giao diện; không phụ trách backend'
        with patch('backend.app.services.cv_polish.request_structured',side_effect=[PolishOutput(text='Hỗ trợ kiểm thử giao diện'),PolishOutput(text='Hỗ trợ kiểm thử giao diện; không phụ trách backend')]) as model:
            result=polish(PolishRequest(text=before))
        self.assertEqual(model.call_count,2)
        self.assertEqual(result['engine'],'model')
        self.assertTrue(result['repair_attempted'])
        self.assertIn('không phụ trách backend',result['proposed'])

    def test_editorial_removes_chat_pronoun_without_new_facts(self):
        r=polish(PolishRequest(text='mình làm computer vision ( hand tracking ) cho trò flappy bird'),use_model=False)
        self.assertEqual(r['proposed'],'Thực hiện computer vision (hand tracking) cho trò flappy bird')
        self.assertEqual(r['status'],'review_required')

    def test_model_cannot_add_numbers_or_technology(self):
        with patch('backend.app.services.cv_polish.request_structured',return_value=PolishOutput(text='Phát triển bằng Python, tăng hiệu suất 50%')):
            r=polish(PolishRequest(text='mình làm website bằng React'))
        self.assertNotIn('Python',r['proposed']);self.assertNotIn('50',r['proposed'])
        self.assertIn('React',r['proposed'])

    def test_model_can_rephrase_but_requires_review(self):
        with patch('backend.app.services.cv_polish.request_structured',return_value=PolishOutput(text='Phát triển giao diện bằng React')):
            r=polish(PolishRequest(text='mình làm giao diện bằng React'))
        self.assertEqual(r['proposed'],'Phát triển giao diện bằng React')
        self.assertEqual(r['engine'],'model')
        self.assertEqual(r['original'],'mình làm giao diện bằng React')

    def test_chat_proposal_does_not_mutate_facts_until_explicit_acceptance(self):
        i=blank_intake();i['profile']['contact'].update(full_name='An',email='an@example.com')
        i.update(target_role='Developer',skipped=['education','experience'])
        i['profile']['project']=[dict(project_name='Blog')]
        text='mình làm giao diện bằng React'
        decision=IntentDecision(intent='build_cv',updates=[ProfilePatch(section='project',index=0,field='role',value=text,evidence=text)])
        r=collect({'cv_intake':i},decision,text,'task_'+'e'*32)
        self.assertEqual(r['intake']['profile']['project'][0]['role'],text)
        self.assertTrue(r['wording_suggestions'])
        accepted=collect({'cv_intake':r['_intake']},IntentDecision(intent='build_cv'),'áp dụng cách viết','task_'+'d'*32)
        self.assertEqual(accepted['intake']['profile']['project'][0]['role'],'Thực hiện giao diện bằng React')
        self.assertNotIn('pending_polish',accepted['_intake'])

    def test_stale_chat_proposal_does_not_replace_new_content(self):
        i=blank_intake();i['profile']['project']=[dict(project_name='Blog',role='Nội dung mới')]
        i['pending_polish']=[dict(section='project',index=0,field='role',original='mình làm giao diện',proposed='Thực hiện giao diện')]
        r=collect({'cv_intake':i},IntentDecision(intent='build_cv'),'áp dụng cách viết','task_'+'c'*32)
        self.assertEqual(r['intake']['profile']['project'][0]['role'],'Nội dung mới')
        self.assertIn('chưa áp dụng',r['text'])

    def test_summary_and_work_alias_are_included_in_suggestions(self):
        from backend.app.services.cv_polish import chat_proposals
        i=blank_intake();i['profile']['summary']='mình làm giao diện'
        i['profile']['project']=[dict(project_name='Blog',description=['mình làm giao diện'])]
        updates=[ProfilePatch(section='summary',field='',value='mình làm giao diện',evidence='mình làm giao diện'),ProfilePatch(section='project',index=0,field='work',value=['mình làm giao diện'],evidence='mình làm giao diện')]
        proposals=chat_proposals(None,i,updates)
        self.assertEqual({p['field'] for p in proposals},{'summary','description'})

class FieldScopeTests(unittest.TestCase):
    def test_chat_polish_keeps_overflow_and_excludes_sibling_fields(self):
        from backend.app.services.cv_polish import chat_proposals
        intake=blank_intake()
        lines=['mình làm giao diện bằng React','mình kiểm thử biểu mẫu','mình viết tài liệu','mình sửa lỗi hiển thị','mình ghi phản hồi']
        intake['profile']['project']=[dict(project_name='Demo',description=lines,contributions=['Không thuộc trường đang chỉnh'])]
        update=ProfilePatch(section='project',index=0,field='work',value=lines,evidence='; '.join(lines))
        response=dict(bullets=[dict(text='Phát triển giao diện bằng React.',sources=[lines[0]])],questions=[])
        with patch('backend.app.services.cv_writer.write_bullets',return_value=response) as writer:
            result=chat_proposals(None,intake,[update],use_model=True)
        self.assertEqual(writer.call_args.args[0].field,'description')
        self.assertEqual(result[0]['proposed'][1:],lines[1:])
        self.assertNotIn('Không thuộc trường đang chỉnh',result[0]['proposed'])

    def test_scope_clauses_stay_attached_to_their_original_work(self):
        before='mình viết tài liệu; không viết kiểm thử; chưa đo hiệu năng'
        with patch('backend.app.services.cv_polish.request_structured',return_value=PolishOutput(text='Viết tài liệu; không đo hiệu năng; chưa viết kiểm thử')):
            result=polish(PolishRequest(text=before))
        self.assertEqual(result['engine'],'editorial')
        self.assertIn('không viết kiểm thử',result['proposed'])

    def test_chi_ra_and_chi_so_are_not_scope_limitations(self):
        from backend.app.services.cv_wording_constraints import scope_clauses
        self.assertEqual(scope_clauses('chỉ ra các kỹ năng còn thiếu; ghi chỉ số điện'),[])
        self.assertEqual(scope_clauses('chỉ phụ trách tài liệu'),['chỉ phụ trách tài liệu'])

    def test_multiline_model_cannot_drop_or_merge_source_lines(self):
        from unittest.mock import patch
        from backend.app.services.cv_polish import PolishRequest, PolishOutput, polish
        with patch('backend.app.services.cv_polish.request_structured',return_value=PolishOutput(text='Thực hiện giao diện.')):
            result=polish(PolishRequest(text='mình làm giao diện\nmình hỗ trợ kiểm thử'))
        self.assertEqual(result['engine'],'editorial')
        self.assertIn('kiểm thử',result['proposed'])

    def test_polish_rejects_new_unmeasured_achievement(self):
        from unittest.mock import patch
        from backend.app.services.cv_polish import PolishRequest, PolishOutput, polish
        with patch('backend.app.services.cv_polish.request_structured',return_value=PolishOutput(text='Tối ưu hiệu suất giao diện.')):
            result=polish(PolishRequest(text='mình kiểm thử giao diện'))
        self.assertEqual(result['engine'],'editorial')
        self.assertNotIn('hiệu suất',result['proposed'])
