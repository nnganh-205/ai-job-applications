import unittest
from backend.app.schemas.assistant import IntentDecision, ProfilePatch, IntakeSignal
from backend.app.services.assistant_intake import apply_updates, blank_intake, collect, missing_fields, direct_signal


def patch(section, field, value, evidence, index=None, **kwargs):
    return ProfilePatch(section=section,field=field,value=value,evidence=evidence,index=index,**kwargs)


class IntakeTests(unittest.TestCase):
    def test_multiple_turns_and_correction_preserve_other_facts(self):
        first='Tôi là An, email an@example.com'
        draft,rejected=apply_updates(None,[patch('contact','full_name','An',first),patch('contact','email','an@example.com',first)],first)
        self.assertEqual(rejected,0)
        text='Đổi tên thành Bình'
        changed,rejected=apply_updates(draft,[patch('contact','full_name','Bình',text)],text)
        self.assertEqual(changed['profile']['contact']['full_name'],'Bình')
        self.assertEqual(changed['profile']['contact']['email'],'an@example.com')
        self.assertEqual(draft['profile']['contact']['full_name'],'An')

    def test_fabricated_facts_and_assistant_examples_never_enter_profile(self):
        text='Tôi dùng React'
        changed,rejected=apply_updates(None,[patch('skills','items',['React','Python'],text,0),patch('project','description',['Tăng tốc 40%'],text,0),patch('contact','full_name','An','Tên tôi là An')],text)
        self.assertEqual(rejected,3)
        self.assertEqual(changed['profile'],blank_intake()['profile'])

    def test_bad_indices_and_unapproved_removal_do_not_erase_data(self):
        text='Dự án React'
        draft,_=apply_updates(None,[patch('project','project_name','Dự án React',text,0)],text)
        changed,rejected=apply_updates(draft,[patch('project','project_name','React',text,2),patch('project','',None,text,0,operation='remove_entry')],text)
        self.assertEqual(rejected,2)
        self.assertEqual(changed['profile']['project'],draft['profile']['project'])
        changed,rejected=apply_updates(draft,[patch('project','',None,'Xóa dự án',0,operation='remove_entry')],'Xóa dự án')
        self.assertEqual(rejected,0)
        self.assertEqual(changed['profile']['project'],[])

    def test_raw_duplicate_bullets_are_not_accepted(self):
        _, rejected=apply_updates(None,[patch('project','original_bullets',['React'],'React',0)],'React')
        self.assertEqual(rejected,1)

    def test_questions_follow_missing_fields_and_allow_optional_skip(self):
        result=collect({},IntentDecision(intent='build_cv'),'Tạo CV','task_'+'a'*32)
        self.assertIn('họ và tên',result['text'])
        result=collect({'cv_intake':result['_intake']},IntentDecision(intent='build_cv',updates=[patch('contact','full_name','An','An')]),'An','task_'+'b'*32)
        self.assertEqual(result['intake']['missing'][0],'contact.reach')
        result=collect({'cv_intake':result['_intake']},IntentDecision(intent='build_cv'),'chưa có','task_'+'c'*32)
        self.assertEqual(result['intake']['missing'][0],'contact.reach')
        result=collect({'cv_intake':result['_intake']},IntentDecision(intent='build_cv',updates=[patch('contact','email','an@example.com','an@example.com')]),'an@example.com','task_'+'d'*32)
        self.assertEqual(result['intake']['missing'][0],'target_role')
        result=collect({'cv_intake':result['_intake']},IntentDecision(intent='build_cv'),'bỏ qua','task_'+'e'*32)
        self.assertEqual(result['intake']['missing'][0],'education')

    def test_ready_snapshot_is_staged_not_published_and_corrections_make_new_snapshot(self):
        text='An an@example.com Frontend React'
        decision=IntentDecision(intent='prepare_cv',updates=[patch('contact','full_name','An',text),patch('contact','email','an@example.com',text),patch('target_role','','Frontend',text),patch('skills','items',['React'],text,0)])
        intake=blank_intake()
        intake['skipped']=['education','experience','project','involvement','summary','skills.languages']
        result=collect({'cv_intake':intake},decision,text,'task_'+'d'*32)
        self.assertEqual(result['intake']['missing'],[])
        self.assertEqual(result['_profile_draft']['status'],'editing')
        self.assertIsNone(result['_profile_draft']['confirmed_profile_id'])
        self.assertIn('/workspace/resumes/new?draft=draft_',result['href'])
        next_result=collect({'cv_intake':result['_intake']},IntentDecision(intent='build_cv',updates=[patch('contact','full_name','Bình','Bình')]),'Bình','task_'+'e'*32)
        self.assertNotEqual(result['href'],next_result['href'])
        self.assertEqual(result['_profile_draft']['profile']['contact']['full_name'],'An')
        self.assertEqual(next_result['_profile_draft']['profile']['contact']['full_name'],'Bình')

    def test_advice_schema_and_old_actions_remain_compatible(self):
        self.assertEqual(IntentDecision(intent='advice',reply='Một CV ngắn gọn...').updates,[])
        self.assertEqual(IntentDecision(intent='evaluate').reply,'')

    def test_adding_skills_retains_existing_list_and_group_alone_is_not_background(self):
        draft,_=apply_updates(None,[patch('skills','items',['React'],'React',0)],'React')
        changed,rejected=apply_updates(draft,[patch('skills','items',['Python'],'Thêm Python',0,operation='append')],'Thêm Python')
        self.assertEqual(rejected,0)
        self.assertEqual(changed['profile']['skills'][0]['items'],['React','Python'])
        empty,_=apply_updates(None,[patch('skills','group','Kỹ thuật','Kỹ thuật',0)],'Kỹ thuật')
        self.assertIn('skills.0.items',missing_fields(empty))

    def test_full_sequential_flow_partial_fields_and_no_experience(self):
        session={}
        count=0
        def turn(text, updates=()):
            nonlocal count
            count+=1
            result=collect(session,IntentDecision(intent='build_cv',updates=list(updates)),text,'task_'+f'{count:032x}')
            session['cv_intake']=result['_intake']
            return result
        r=turn('Tạo CV')
        self.assertEqual(r['intake']['step'],'contact')
        text='An an@example.com Frontend'
        r=turn(text,[patch('contact','full_name','An',text),patch('contact','email','an@example.com',text),patch('target_role','','Frontend',text)])
        self.assertEqual(r['intake']['missing'][0],'education')
        self.assertNotIn('href',r)
        r=turn('NEU',[patch('education','institution','NEU','NEU',0)])
        self.assertEqual(r['intake']['missing'][0],'education.0.major')
        self.assertIn('ngành học',r['text'])
        r=turn('CNTT',[patch('education','major','CNTT','CNTT',0)])
        self.assertEqual(r['intake']['missing'][0],'education.more')
        r=turn('hết rồi')
        self.assertEqual(r['intake']['step'],'experience')
        r=turn('Mình chưa có kinh nghiệm')
        self.assertEqual(r['intake']['step'],'project')
        self.assertEqual(r['intake']['profile']['experience'],[])
        r=turn('chưa có')
        self.assertEqual(r['intake']['step'],'skills')
        r=turn('React',[patch('skills','items',['React'],'React',0)])
        self.assertEqual(r['intake']['missing'][0],'skills.languages')
        r=turn('chưa có ngoại ngữ')
        self.assertEqual(r['intake']['step'],'involvement')
        r=turn('chưa có')
        self.assertEqual(r['intake']['step'],'summary')
        r=turn('bỏ qua')
        self.assertEqual(r['intake']['missing'],[])
        self.assertIn('href',r)
        self.assertEqual(r['_profile_draft']['profile']['education'][0]['institution'],'NEU')

    def test_invalid_contact_and_skip_of_named_future_section(self):
        intake=blank_intake()
        intake['profile']['contact'].update(full_name='An',email='invalid')
        self.assertEqual(missing_fields(intake)[0],'contact.reach')
        intake['profile']['contact']['phone']='0901234567'
        intake['target_role']='Frontend'
        result=collect({'cv_intake':intake},IntentDecision(intent='build_cv'),'chưa có kinh nghiệm','task_'+'f'*32)
        self.assertEqual(result['intake']['step'],'education')
        self.assertIn('experience',result['_intake']['skipped'])
        self.assertNotIn('education',result['_intake']['skipped'])
        self.assertNotIn('href',result)

    def test_skipping_unknown_detail_preserves_entry_and_corrections_reopen_required_field(self):
        intake=blank_intake()
        intake['profile']['contact'].update(full_name='An',email='an@example.com')
        intake['target_role']='Frontend'
        intake['profile']['education']=[{'institution':'NEU'}]
        result=collect({'cv_intake':intake},IntentDecision(intent='build_cv'),'không nhớ','task_'+'a'*32)
        self.assertEqual(result['intake']['step'],'experience')
        self.assertEqual(result['intake']['profile']['education'][0]['institution'],'NEU')
        result=collect({'cv_intake':result['_intake']},IntentDecision(intent='build_cv',updates=[patch('contact','email',None,'Xóa email')]),'Xóa email','task_'+'b'*32)
        self.assertEqual(result['intake']['missing'][0],'contact.reach')

    def experience_stage(self):
        intake=blank_intake()
        intake['profile']['contact'].update(full_name='An',email='an@example.com')
        intake['target_role']='Frontend'
        intake['profile']['education']=[dict(institution='NEU',major='CNTT')]
        intake['current_step']='experience'
        return intake

    def test_natural_absence_replies_move_on_without_saving_negative_facts(self):
        for text in ['mình chưa từng làm ở đâu','em chưa đi làm bao giờ','từ trước đến giờ mình chưa đi làm','minh chua tung lam o dau','Mình chưa từng làm cho công ty nào cả']:
            with self.subTest(text=text):
                intake=self.experience_stage()
                signal=direct_signal(intake,text)
                self.assertIsNotNone(signal)
                result=collect({'cv_intake':intake},IntentDecision(intent='build_cv'),text,'task_'+'c'*32)
                self.assertEqual(result['intake']['step'],'project')
                self.assertEqual(result['intake']['profile']['experience'],[])
                self.assertEqual(result['intake']['profile']['education'],intake['profile']['education'])

    def test_advice_and_mixed_positive_experience_are_sent_to_semantic_model(self):
        for text in ['Chưa có kinh nghiệm thì viết gì?','mình chưa từng làm ở đâu, nhưng có đồ án React','Chưa làm ở FPT nhưng từng thực tập ở ABC','Mình chưa từng làm ở đâu nên ghi CV thế nào?']:
            self.assertIsNone(direct_signal(self.experience_stage(),text),text)

    def test_semantic_absence_signal_keeps_project_from_same_reply(self):
        text='Em chỉ học thôi, nhưng có đồ án React'
        signal=IntakeSignal(kind='not_available',section='experience',evidence='Em chỉ học thôi')
        result=collect({'cv_intake':self.experience_stage()},IntentDecision(intent='build_cv',intake_signal=signal,updates=[patch('project','project_name','React',text,0)]),text,'task_'+'d'*32)
        self.assertIn('experience',result['_intake']['skipped'])
        self.assertEqual(result['intake']['missing'][0],'project.0.role')
        self.assertEqual(result['intake']['profile']['project'][0]['project_name'],'React')

    def test_unquoted_signal_cannot_skip_and_unknown_only_skips_current_detail(self):
        intake=self.experience_stage()
        signal=IntakeSignal(kind='not_available',section='experience',evidence='Chưa đi làm')
        result=collect({'cv_intake':intake},IntentDecision(intent='build_cv',intake_signal=signal),'Tôi từng thực tập','task_'+'e'*32)
        self.assertEqual(result['intake']['step'],'experience')
        intake['profile']['education']=[dict(institution='NEU')]
        signal=IntakeSignal(kind='unknown',section='education',evidence='không nhớ chính xác')
        result=collect({'cv_intake':intake},IntentDecision(intent='build_cv',intake_signal=signal),'Mình không nhớ chính xác tên ngành','task_'+'f'*32)
        self.assertIn('education.0.major',result['_intake']['skipped'])
        self.assertEqual(result['intake']['step'],'experience')
        self.assertEqual(result['intake']['profile']['education'][0]['institution'],'NEU')

    def test_request_to_explain_never_skips_or_changes_profile(self):
        intake=self.experience_stage()
        intake['skipped']=['experience']
        intake['current_step']='project'
        for text in ['là sao','là sao?','mình chưa hiểu','ý bạn là gì?','dự án là gì','giai thich lai giup minh','mình chưa biết']:
            with self.subTest(text=text):
                signal=direct_signal(intake,text)
                self.assertEqual(signal.kind,'explain')
                decision=IntentDecision(intent='build_cv',intake_signal=IntakeSignal(kind='unknown',section='project',evidence=text),updates=[patch('project','project_name',text,text,0)])
                result=collect({'cv_intake':intake},decision,text,'task_'+'a'*32)
                self.assertEqual(result['intake']['step'],'project')
                self.assertEqual(result['intake']['profile'],intake['profile'])
                self.assertEqual(result['_intake']['skipped'],['experience'])
                self.assertEqual(result['_intake']['revision'],intake['revision'])
                self.assertIn('bài tập',result['text'])
                self.assertIn('Ví dụ',result['text'])
                self.assertNotIn('href',result)

    def test_semantic_explanation_keeps_current_field_and_does_not_store_examples(self):
        intake=self.experience_stage()
        intake['skipped']=['experience']
        intake['profile']['project']=[{'project_name':'Website'}]
        text='Bạn muốn biết chức danh hay phần em phụ trách trong bài đó?'
        decision=IntentDecision(intent='build_cv',intake_signal=IntakeSignal(kind='explain',section='project',evidence=text),reply='Vai trò là phần bạn trực tiếp phụ trách.',updates=[patch('project','role','chức danh',text,0)])
        result=collect({'cv_intake':intake},decision,text,'task_'+'b'*32)
        self.assertEqual(result['intake']['missing'][0],'project.0.role')
        self.assertFalse(result['intake']['profile']['project'][0].get('role'))
        self.assertNotIn('project.0.role',result['_intake']['skipped'])
        self.assertIn('không nhất thiết phải có chức danh',result['text'])

    def skills_stage(self):
        intake=self.experience_stage()
        intake.update(skipped=['experience','project'],current_step='skills',step_history=['contact','target_role','education','experience','project','skills'])
        return intake

    def test_exact_return_request_overrides_wrong_explanation_and_reopens_skipped_project(self):
        intake=self.skills_stage()
        text='quay lại về dự án đi, tôi cần bổ sung'
        wrong=IntakeSignal(kind='explain',section='skills',evidence=text)
        result=collect({'cv_intake':intake},IntentDecision(intent='build_cv',intake_signal=wrong),text,'task_'+'a'*32)
        self.assertEqual(result['intake']['step'],'project')
        self.assertEqual(result['_intake']['focus_section'],'project')
        self.assertNotIn('project',result['_intake']['skipped'])
        self.assertEqual(result['intake']['profile'],intake['profile'])
        self.assertIn('quay lại phần dự án',result['text'])
        self.assertNotIn('Kỹ năng là',result['text'])
        text='Website, mình làm giao diện bằng React'
        result=collect({'cv_intake':result['_intake']},IntentDecision(intent='build_cv',updates=[patch('project','project_name','Website',text,0),patch('project','role','làm giao diện',text,0),patch('project','description',['làm giao diện bằng React'],text,0)]),text,'task_'+'b'*32)
        self.assertEqual(result['intake']['missing'][0],'project.more')
        self.assertEqual(result['_intake']['focus_section'],'project')
        self.assertEqual(result['intake']['profile']['project'][0]['project_name'],'Website')

    def test_previous_section_uses_history_and_legacy_messages(self):
        intake=self.skills_stage()
        signal=direct_signal(intake,'vậy quay lại lúc nãy')
        self.assertEqual(signal.kind,'navigate')
        self.assertEqual(signal.section,'project')
        intake.pop('step_history')
        messages=[dict(role='assistant',result=dict(intake=dict(step=stage))) for stage in ['education','project','skills']]
        signal=direct_signal(intake,'quay lại phần trước nhé',messages)
        self.assertEqual(signal.section,'project')
        self.assertIsNone(direct_signal(intake,'quay lại lúc nãy'))

    def test_completed_section_can_be_reopened_and_resumed_without_erasing_data(self):
        intake=self.skills_stage()
        result=collect({'cv_intake':intake},IntentDecision(intent='build_cv'),'quay lại học vấn','task_'+'c'*32)
        self.assertEqual(result['intake']['missing'][0],'education.review')
        self.assertIn('bổ sung hoặc sửa',result['text'])
        explained=collect({'cv_intake':result['_intake']},IntentDecision(intent='build_cv'),'là sao','task_'+'d'*32)
        self.assertEqual(explained['intake']['missing'][0],'education.review')
        result=collect({'cv_intake':explained['_intake']},IntentDecision(intent='build_cv'),'giữ nguyên','task_'+'e'*32)
        self.assertEqual(result['intake']['step'],'skills')
        self.assertEqual(result['intake']['profile'],intake['profile'])

    def test_mixed_navigation_and_new_facts_are_kept_and_unquoted_navigation_is_ignored(self):
        intake=self.skills_stage()
        text='Cho mình bổ sung đồ án: Website bán hàng'
        self.assertIsNone(direct_signal(intake,text))
        decision=IntentDecision(intent='build_cv',intake_signal=IntakeSignal(kind='navigate',section='project',evidence='Cho mình bổ sung đồ án'),updates=[patch('project','project_name','Website bán hàng',text,0)])
        result=collect({'cv_intake':intake},decision,text,'task_'+'f'*32)
        self.assertEqual(result['intake']['missing'][0],'project.0.role')
        self.assertEqual(result['intake']['profile']['project'][0]['project_name'],'Website bán hàng')
        decision=IntentDecision(intent='build_cv',intake_signal=IntakeSignal(kind='navigate',section='project',evidence='quay lại dự án'))
        result=collect({'cv_intake':intake},decision,'React','task_'+'a'*32)
        self.assertEqual(result['intake']['step'],'skills')
        self.assertNotIn('focus_section',result['_intake'])

    def test_positive_new_facts_cannot_be_skipped_by_a_stale_negative_signal(self):
        intake=self.skills_stage()
        intake['skipped'].remove('project')
        intake['focus_section']='project'
        text='Dự án Website, vai trò lập trình, xây dựng giao diện'
        decision=IntentDecision(intent='build_cv',intake_signal=IntakeSignal(kind='not_available',section='project',evidence=text),updates=[patch('project','project_name','Website',text,0),patch('project','role','lập trình',text,0),patch('project','description',['xây dựng giao diện'],text,0)])
        result=collect({'cv_intake':intake},decision,text,'task_'+'a'*32)
        self.assertEqual(result['intake']['missing'][0],'project.more')
        self.assertEqual(result['intake']['profile']['project'][0]['project_name'],'Website')
        self.assertNotIn('project',result['_intake']['skipped'])

    def test_source_bound_work_and_scalar_description_are_normalized_losslessly(self):
        for field in ['work','description']:
            text='Mình xây dựng trang sản phẩm bằng React.'
            intake=self.skills_stage()
            intake['focus_section']='project'
            intake['skipped'].remove('project')
            intake['profile']['project']=[{'project_name':'Website','role':'lập trình giao diện'}]
            result=collect({'cv_intake':intake},IntentDecision(intent='build_cv',updates=[patch('project',field,text,text,0)]),text,'task_'+'b'*32)
            self.assertEqual(result['intake']['missing'][0],'project.more')
            self.assertEqual(result['intake']['profile']['project'][0]['description'],[text])

    def role_stage(self):
        intake=self.skills_stage()
        intake['skipped'].remove('project')
        intake['focus_section']='project'
        intake['current_step']='project.0.role'
        intake['profile']['project']=[{'project_name':'Website bán hàng'}]
        return intake

    def test_role_answer_from_screenshot_is_bound_to_question_without_inventing_title(self):
        for text in ['mình làm hết mọi thứ','em tự làm từ đầu tới cuối','mình chỉ hỗ trợ phần giao diện','backend','mình phụ trách sửa lỗi giao diện']:
            with self.subTest(text=text):
                intake=self.role_stage()
                result=collect({'cv_intake':intake},IntentDecision(intent='build_cv'),text,'task_'+'c'*32)
                entry=result['intake']['profile']['project'][0]
                self.assertEqual(entry['role'],text)
                self.assertEqual(result['intake']['missing'][0],'project.0.work')
                self.assertEqual(entry['description'],[])
                self.assertEqual(entry['technologies'],[])
                self.assertIn('cụ thể',result['text'])
                self.assertIn('ghi nhận vai trò',result['text'])

    def test_vague_total_ownership_is_not_a_fabricated_list_of_tasks(self):
        intake=self.role_stage()
        intake['profile']['project'][0]['role']='tự thực hiện'
        result=collect({'cv_intake':intake},IntentDecision(intent='build_cv'),'mình làm hết mọi thứ','task_'+'d'*32)
        self.assertEqual(result['intake']['missing'][0],'project.0.work')
        self.assertEqual(result['intake']['profile']['project'][0].get('description',[]),[])
        self.assertIn('không tự đoán',result['text'])

    def test_role_binding_targets_correct_entry_and_existing_work_is_preserved(self):
        intake=self.role_stage()
        intake['profile']['project']=[{'project_name':'Old','role':'thiết kế','description':['Vẽ giao diện']},{'project_name':'New','description':['Xây dựng trang sản phẩm']}]
        result=collect({'cv_intake':intake},IntentDecision(intent='build_cv'),'mình làm hết mọi thứ','task_'+'e'*32)
        self.assertEqual(result['intake']['missing'][0],'project.more')
        self.assertEqual(result['intake']['profile']['project'][0]['role'],'thiết kế')
        self.assertEqual(result['intake']['profile']['project'][1]['role'],'mình làm hết mọi thứ')
        self.assertEqual(result['intake']['profile']['project'][1]['description'],['Xây dựng trang sản phẩm'])

    def test_questions_other_people_and_multiple_facts_are_not_blindly_stored_as_role(self):
        from backend.app.services.assistant_answers import contextual_answer
        intake=self.role_stage()
        for text in ['mình làm hết mọi thứ thì ghi sao?','ví dụ mình phụ trách frontend','nhóm mình làm hết mọi thứ','mình chưa hiểu','mình làm việc ở ABC','mình làm frontend nhưng bạn khác làm backend','quay lại kỹ năng','mình không làm gì']:
            self.assertIsNone(contextual_answer(intake['profile'],'project.0.role',text),text)

    def test_role_question_without_question_mark_explains_named_project_and_keeps_state(self):
        for text in ['vai trò của dự án đó gồm những gì nhỉ','vai trò gồm những gì','ở mục này nên ghi gì','cho mình ví dụ vai trò với','vai tro cua du an do gom nhung gi nhi']:
            with self.subTest(text=text):
                intake=self.role_stage()
                decision=IntentDecision(intent='build_cv',reply='Mình đã nhận vai trò của bạn trong dự án.',updates=[patch('project','role',text,text,0)])
                result=collect({'cv_intake':intake},decision,text,'task_'+'a'*32)
                self.assertEqual(result['intake']['missing'][0],'project.0.role')
                self.assertEqual(result['intake']['profile'],intake['profile'])
                self.assertEqual(result['_intake']['revision'],intake['revision'])
                self.assertIn('Website bán hàng',result['text'])
                self.assertIn('kiểm thử website',result['text'])
                self.assertNotIn('đã nhận vai trò',result['text'])
                self.assertNotIn('còn thiếu vai trò',result['text'])

    def test_explanation_examples_follow_project_type_and_do_not_become_facts(self):
        intake=self.role_stage()
        intake['profile']['project'][0]['project_name']='Phân tích dữ liệu bán hàng'
        result=collect({'cv_intake':intake},IntentDecision(intent='build_cv'),'vai trò gồm những gì','task_'+'b'*32)
        self.assertEqual(result['intake']['profile'],intake['profile'])
        self.assertIn('thu thập và làm sạch dữ liệu',result['text'])
        self.assertNotIn('kiểm thử website',result['text'])

    def test_mixed_fact_and_question_go_to_model_instead_of_discarding_fact(self):
        from backend.app.services.assistant_answers import clarification_request
        self.assertFalse(clarification_request('Mình làm frontend, vai trò nên ghi thế nào?'))

    def test_question_topic_is_explained_without_changing_active_field(self):
        intake=self.role_stage()
        for text, expected in [('kỹ năng của dự án gồm những gì','Kỹ năng là'),('đồ án là gì','bài tập thực tế')]:
            result=collect({'cv_intake':intake},IntentDecision(intent='build_cv'),text,'task_'+'c'*32)
            self.assertIn(expected,result['text'])
            self.assertEqual(result['intake']['missing'][0],'project.0.role')
            self.assertEqual(result['intake']['profile'],intake['profile'])

    def test_personal_project_acknowledgement_and_optional_detail_deferral(self):
        intake=self.role_stage()
        intake['profile']['project'][0]['project_name']='hệ thống tuyển sinh dùng AI hỗ trợ tạo CV và chatbot, RAG'
        text='đây là dự án cá nhân, nên có thể nói mình làm hết'
        result=collect({'cv_intake':intake},IntentDecision(intent='build_cv'),text,'task_'+'a'*32)
        entry=result['intake']['profile']['project'][0]
        self.assertEqual(entry['role'],text)
        self.assertEqual(entry['project_type'],'dự án cá nhân')
        self.assertEqual(entry['description'],[])
        self.assertIn('không cần liệt kê thêm vai trò',result['text'])
        self.assertIn('hệ thống tuyển sinh',result['text'])
        self.assertIn('tùy chọn',result['text'])
        self.assertNotIn('2–3',result['text'])
        for skip in ['để sau','không cần bổ sung','sang phần tiếp theo']:
            next_result=collect({'cv_intake':result['_intake']},IntentDecision(intent='build_cv'),skip,'task_'+'b'*32)
            self.assertEqual(next_result['intake']['missing'][0],'project.more')
            self.assertNotIn('bỏ qua phần dự án',next_result['text'])
            self.assertIn('vẫn được giữ nguyên',next_result['text'])
            self.assertEqual(next_result['intake']['profile']['project'],result['intake']['profile']['project'])

    def test_entry_number_confusion_explains_reference_not_job_details(self):
        intake=self.role_stage()
        intake['profile']['project'][0]['role']='tự làm toàn bộ'
        for text in ['giải thích mình mục 1 là sao, có nhiều mục à','mục là soa','mục 1 là sao','có nhiều mục à','muc 1 la sao']:
            result=collect({'cv_intake':intake},IntentDecision(intent='build_cv',updates=[patch('project','description',[text],text,0)]),text,'task_'+'a'*32)
            self.assertIn('Website bán hàng',result['text'])
            self.assertIn('Hiện chỉ có một',result['text'])
            self.assertNotIn('1–3 việc',result['text'])
            self.assertEqual(result['intake']['profile'],intake['profile'])
            self.assertEqual(result['intake']['missing'][0],'project.0.work')
            self.assertEqual(result['_intake']['revision'],intake['revision'])

    def test_numbered_reference_uses_actual_entries_and_does_not_navigate(self):
        intake=self.role_stage()
        intake['profile']['project'].append({'project_name':'Dashboard dữ liệu'})
        result=collect({'cv_intake':intake},IntentDecision(intent='build_cv'),'mục 2 là gì','task_'+'b'*32)
        self.assertIn('Dashboard dữ liệu',result['text'])
        self.assertIn('2 mục',result['text'])
        self.assertEqual(result['intake']['missing'][0],'project.0.role')
        result=collect({'cv_intake':intake},IntentDecision(intent='build_cv'),'mục 3 là gì','task_'+'c'*32)
        self.assertIn('chưa có mục 3',result['text'])
        self.assertEqual(len(result['intake']['profile']['project']),2)

    def test_followup_questions_use_project_names_instead_of_internal_number(self):
        result=collect({'cv_intake':self.role_stage()},IntentDecision(intent='build_cv'),'Tiếp tục','task_'+'d'*32)
        self.assertIn('Website bán hàng',result['text'])
        self.assertNotIn('mục 1',result['text'])

    def test_role_wording_question_is_advice_not_profile_input(self):
        intake=self.role_stage()
        intake['profile']['project'][0]['role']='mình làm hết'
        text='nếu mà mình làm hết mọi thứ, bởi vì là dự án cá nhân, thì mình sẽ viết vai trò là gì'
        decision=IntentDecision(intent='build_cv',updates=[patch('project','role','trưởng nhóm',text,0)])
        result=collect({'cv_intake':intake},decision,text,'task_'+'a'*32)
        self.assertIn('Tự thực hiện toàn bộ dự án cá nhân',result['text'])
        self.assertIn('chưa áp dụng',result['text'])
        self.assertNotIn('chưa đối chiếu',result['text'])
        self.assertNotIn('còn thiếu',result['text'])
        self.assertEqual(result['intake']['profile'],intake['profile'])
        self.assertEqual(result['_intake']['revision'],intake['revision'])
        self.assertEqual(result['intake']['missing'][0],'project.0.work')
        confirmed=collect({'cv_intake':result['_intake']},IntentDecision(intent='build_cv'),'dùng câu này','task_'+'b'*32)
        entry=confirmed['intake']['profile']['project'][0]
        self.assertEqual(entry['role'],'Tự thực hiện toàn bộ dự án cá nhân')
        self.assertEqual(entry['description'],[])
        self.assertEqual(entry['technologies'],[])
        self.assertNotIn('pending_role_wording',confirmed['_intake'])

    def test_wording_variants_without_question_marks_and_no_unsupported_personal_label(self):
        intake=self.role_stage()
        intake['profile']['project'][0]['role']='tự làm toàn bộ'
        for text in ['mình làm hết thì vai trò nên ghi thế nào','ghi vai trò sao cho chuyên nghiệp','nên ghi vai trò là gì']:
            result=collect({'cv_intake':intake},IntentDecision(intent='build_cv'),text,'task_'+'c'*32)
            self.assertEqual(result['intake']['profile'],intake['profile'])
            self.assertEqual(result['_intake']['pending_role_wording']['value'],'Tự thực hiện toàn bộ dự án')

    def test_stale_wording_does_not_apply_to_changed_project(self):
        intake=self.role_stage()
        intake['profile']['project'][0]['role']='tự làm toàn bộ'
        result=collect({'cv_intake':intake},IntentDecision(intent='build_cv'),'vai trò nên ghi thế nào','task_'+'d'*32)
        changed=result['_intake']
        changed['profile']['project'][0]['project_name']='Dự án khác'
        result=collect({'cv_intake':changed},IntentDecision(intent='build_cv'),'áp dụng','task_'+'e'*32)
        self.assertEqual(result['intake']['profile']['project'][0]['role'],'tự làm toàn bộ')
        self.assertIn('đã thay đổi',result['text'])
        self.assertNotIn('pending_role_wording',result['_intake'])

    def test_model_cannot_apply_wording_without_explicit_user_confirmation(self):
        intake=self.role_stage()
        intake['profile']['project'][0]['role']='tự làm toàn bộ'
        result=collect({'cv_intake':intake},IntentDecision(intent='build_cv'),'vai trò nên ghi thế nào','task_'+'f'*32)
        state=result['_intake']
        text='câu này nghĩa là gì'
        decision=IntentDecision(intent='build_cv',intake_signal=IntakeSignal(kind='accept_wording',section='project',evidence=text))
        result=collect({'cv_intake':state},decision,text,'task_'+'a'*32)
        self.assertEqual(result['intake']['profile']['project'][0]['role'],'tự làm toàn bộ')
        self.assertIn('pending_role_wording',result['_intake'])

    def test_wording_confirmation_variants_are_explicit_not_questions(self):
        from backend.app.services.assistant_wording import suggestion_acceptance
        for text in ['dùng câu này','ghi câu đó vào CV','viết như vậy đi','áp dụng gợi ý này','đúng rồi, dùng câu này nhé']:
            self.assertTrue(suggestion_acceptance(text),text)
        for text in ['dùng câu này được không?','nếu dùng câu này','đừng dùng câu này','câu này nghĩa là gì']:
            self.assertFalse(suggestion_acceptance(text),text)

    def test_wording_advice_for_other_sections_does_not_propose_a_project_role(self):
        intake=self.role_stage()
        text='Kỹ năng nên trình bày thế nào cho gọn?'
        decision=IntentDecision(intent='build_cv',reply='Nhóm các kỹ năng thực tế theo công cụ hoặc chuyên môn.',intake_signal=IntakeSignal(kind='wording',section='skills',evidence=text))
        result=collect({'cv_intake':intake},decision,text,'task_'+'b'*32)
        self.assertEqual(result['intake']['profile'],intake['profile'])
        self.assertNotIn('pending_role_wording',result['_intake'])
        self.assertNotIn('Tự thực hiện',result['text'])


class DialogueFollowupTests(unittest.TestCase):
    def session(self):
        intake = blank_intake()
        intake['profile']['contact'].update(full_name='An', email='an@example.com')
        intake['profile']['project'] = [dict(project_name='Website bán hàng', role='mình tự làm hết')]
        intake.update(target_role='Developer', skipped=['education','experience'], current_step='project.0.work')
        return dict(cv_intake=intake, messages=[dict(role='assistant',text='Bạn muốn bổ sung một việc hoặc kết quả cho Website bán hàng không?')])

    def test_followups_preserve_facts_stage_and_original_referent(self):
        from copy import deepcopy
        session = self.session()
        original = deepcopy(session['cv_intake']['profile'])
        for text in ['nghĩa là thêm dự án khác á', 'ý là sửa cái cũ?', 'có phải thêm dự án mới nữa không?']:
            result = collect(session, IntentDecision(intent='build_cv', updates=[patch('project','project_name',text,text,1)]), text, 'task_'+'f'*32)
            self.assertIn('Website bán hàng', result['text'])
            self.assertIn('Không phải thêm dự án khác', result['text'])
            self.assertEqual(result['_intake']['profile'], original)
            self.assertEqual(result['intake']['missing'][0], 'project.0.work')
            self.assertEqual(result['_intake']['revision'],0)
            session['cv_intake'] = result['_intake']
            session['messages'] += [dict(role='user',text=text),dict(role='assistant',text=result['text'])]

    def test_explicit_add_command_is_not_mistaken_for_question(self):
        from backend.app.services.assistant_dialogue import followup_question
        self.assertFalse(followup_question('Tôi muốn thêm dự án khác tên Blog'))
        self.assertFalse(followup_question('mình muốn thêm dự án khác được không?'))
        self.assertFalse(followup_question('mình có thể thêm dự án mới không?'))

    def test_context_tracks_active_entry_and_previous_turns(self):
        from backend.app.services.assistant_dialogue import dialogue_context, resolve_followup
        session = self.session()
        intake = session['cv_intake']
        intake['profile']['project'].append(dict(project_name='Chatbot tuyển dụng',role='Tự thực hiện'))
        context = dialogue_context(intake,'project.1.work',session['messages'])
        self.assertIn('Chatbot tuyển dụng',context['entity'])
        self.assertEqual(context['action'],'add_optional_detail_to_existing_entry')
        self.assertIn('bổ sung',context['last_assistant_message'])
        answer=resolve_followup(intake,'project.1.work','nghĩa là thêm dự án khác à',session['messages'])
        self.assertIn('Chatbot tuyển dụng',answer)
        self.assertNotIn('Website bán hàng',answer)

    def test_question_about_suggested_wording_does_not_apply_it(self):
        session=self.session()
        session['cv_intake']['pending_role_wording']=dict(index=0,value='Tự thực hiện toàn bộ dự án')
        result=collect(session,IntentDecision(intent='build_cv'),'câu đó ghi ở đâu?','task_'+'e'*32)
        self.assertIn('ô Vai trò',result['text'])
        self.assertIn('chưa được áp dụng',result['text'])
        self.assertEqual(result['_intake']['profile']['project'][0]['role'],'mình tự làm hết')

class ProjectCollectionTests(unittest.TestCase):
    def session(self):
        intake=blank_intake()
        intake['profile']['contact'].update(full_name='An',email='an@example.com')
        intake.update(target_role='Developer',skipped=['education','experience'])
        intake['profile']['project']=[dict(project_name='Website',role='Tự thực hiện')]
        return dict(cv_intake=intake)

    def turn(self, session, text, updates=(), signal=None):
        result=collect(session,IntentDecision(intent='build_cv',updates=list(updates),intake_signal=signal),text,'task_'+'d'*32)
        session['cv_intake']=result['_intake']
        return result

    def test_skip_details_asks_if_more_projects_then_explicit_end_advances(self):
        session=self.session()
        r=self.turn(session,'bỏ qua')
        self.assertEqual(r['intake']['missing'][0],'project.more')
        self.assertIn('còn dự án nào',r['text'])
        self.assertEqual(len(r['intake']['profile']['project']),1)
        r=self.turn(session,'hết rồi')
        self.assertEqual(r['intake']['step'],'skills')
        self.assertEqual(r['intake']['profile']['project'][0]['project_name'],'Website')

    def test_collect_second_project_and_ask_again(self):
        session=self.session();self.turn(session,'để sau')
        r=self.turn(session,'còn')
        self.assertEqual(r['intake']['missing'][0],'project.1.project_name')
        self.assertEqual(len(r['intake']['profile']['project']),1)
        text='Chatbot, mình làm Backend'
        r=self.turn(session,text,[patch('project','project_name','Chatbot',text,1),patch('project','role','Backend',text,1)])
        self.assertEqual(r['intake']['missing'][0],'project.1.work')
        r=self.turn(session,'bỏ qua')
        self.assertEqual(r['intake']['missing'][0],'project.more')
        self.assertEqual([p['project_name'] for p in r['intake']['profile']['project']],['Website','Chatbot'])
        r=self.turn(session,'không thêm nữa')
        self.assertEqual(r['intake']['step'],'skills')

    def test_can_give_new_project_directly_without_yes_turn(self):
        session=self.session();self.turn(session,'bỏ qua')
        text='Dự án thứ hai là Blog, mình viết giao diện'
        r=self.turn(session,text,[patch('project','project_name','Blog',text,1),patch('project','role','viết giao diện',text,1)])
        self.assertEqual(r['intake']['missing'][0],'project.1.work')
        self.assertEqual(r['intake']['profile']['project'][0]['project_name'],'Website')

    def test_explanation_keeps_list_open_and_facts_unchanged(self):
        session=self.session();r=self.turn(session,'bỏ qua');profile=r['intake']['profile']
        r=self.turn(session,'nghĩa là thêm dự án khác á')
        self.assertIn('đã kể hết',r['text'])
        self.assertEqual(r['intake']['missing'][0],'project.more')
        self.assertEqual(r['intake']['profile'],profile)

    def test_cancel_unfilled_next_project_does_not_leave_empty_entry(self):
        session=self.session();self.turn(session,'bỏ qua');self.turn(session,'còn')
        r=self.turn(session,'không thêm nữa')
        self.assertEqual(r['intake']['step'],'skills')
        self.assertEqual(len(r['intake']['profile']['project']),1)

    def test_completion_signal_cannot_skip_unfinished_project(self):
        session=self.session()
        r=self.turn(session,'hết rồi',signal=IntakeSignal(kind='section_complete',section='project',evidence='hết rồi'))
        self.assertEqual(r['intake']['missing'][0],'project.0.work')
        self.assertNotIn('project_confirmed_count',r['_intake'])

class MultiFactProjectTests(unittest.TestCase):
    def test_exact_message_keeps_personal_type_and_activity_together(self):
        intake=blank_intake()
        intake['profile']['contact'].update(full_name='An',email='an@example.com')
        intake.update(target_role='Developer',skipped=['education','experience'],project_next_index=1)
        intake['profile']['project']=[dict(project_name='Dự án cũ',role='Tự làm',description=['Thiết kế'])]
        text='mình làm computer vision ( hand tracking ) cho trò flappy bird, đây cũng là dự án cá nhân'
        name='computer vision ( hand tracking ) cho trò flappy bird'
        result=collect({'cv_intake':intake},IntentDecision(intent='build_cv',updates=[patch('project','project_name',name,text,1)]),text,'task_'+'e'*32)
        entries=result['intake']['profile']['project']
        self.assertEqual(entries[0]['project_name'],'Dự án cũ')
        self.assertEqual(entries[1]['project_type'],'dự án cá nhân')
        self.assertIn('hand tracking',entries[1]['role'])
        self.assertIn(entries[1]['role'],text)
        self.assertTrue(entries[1]['description'])
        self.assertEqual(entries[1]['technologies'],[])
        self.assertEqual(result['intake']['missing'][0],'project.more')
        self.assertIn('loại dự án: dự án cá nhân',result['text'])

    def test_supplement_does_not_discard_model_extracted_fields(self):
        from backend.app.services.assistant_project_facts import enrich_project_updates
        profile=blank_intake()['profile']
        text='mình phát triển website bằng React, đây là dự án cá nhân'
        updates=[patch('project','project_name','website',text,0),patch('project','technologies',['React'],text,0)]
        enriched=enrich_project_updates(profile,'project',text,updates)
        self.assertEqual(enriched[:2],updates)
        self.assertIn('project_type',[p.field for p in enriched])

    def test_personal_type_alone_does_not_invent_role(self):
        intake=blank_intake()
        intake['profile']['project']=[dict(project_name='Blog')]
        from backend.app.services.assistant_project_facts import enrich_project_updates
        self.assertEqual(enrich_project_updates(intake['profile'],'project.0.role','đây là dự án cá nhân',[]),[])

    def test_examples_negation_questions_and_multiple_projects_not_bound(self):
        from backend.app.services.assistant_project_facts import enrich_project_updates
        profile=blank_intake()['profile'];profile['project']=[dict(project_name='Blog')]
        for text in ['ví dụ mình làm website, đây là dự án cá nhân','mình làm website là dự án cá nhân à?', 'mình không làm website, không phải dự án cá nhân']:
            self.assertEqual(enrich_project_updates(profile,'project.0.role',text,[]),[])
        text='mình làm website, dự án cá nhân'
        updates=[patch('project','project_name','website',text,0),patch('project','project_name','website',text,1)]
        self.assertEqual(enrich_project_updates(profile,'project.more',text,updates),updates)

    def test_short_role_answer_with_more_facts_uses_full_extraction(self):
        from backend.app.services.assistant_answers import contextual_answer
        profile=blank_intake()['profile']
        profile['project']=[dict(project_name='Blog')]
        text='mình phụ trách frontend, dùng React'
        self.assertIsNone(contextual_answer(profile,'project.0.role',text))
        intake=blank_intake()
        intake['profile']['contact'].update(full_name='An',email='an@example.com')
        intake.update(target_role='Developer',skipped=['education','experience'])
        intake['profile']['project']=profile['project']
        result=collect({'cv_intake':intake},IntentDecision(intent='build_cv',updates=[patch('project','role','frontend',text,0),patch('project','technologies',['React'],text,0)]),text,'task_'+'b'*32)
        entry=result['intake']['profile']['project'][0]
        self.assertEqual(entry['role'],'frontend')
        self.assertEqual(entry['technologies'],['React'])

class SkillsFollowupTests(unittest.TestCase):
    def test_three_technical_groups_preserve_parentheses_and_explicit_labels(self):
        from unittest.mock import patch as mock_patch
        from backend.app.services.assistant import choose_intent
        from backend.app.services.assistant_skills import group_skills
        text='Ngôn ngữ lập trình: Python, SQL (PostgreSQL, MySQL), Framework & Thư Viện: PyTorch, Hugging Face, Unsloth, LangGraph, Công cụ phát triển: Git, Docker, Google Earth Engine, QGIS'
        s=self.session()
        with mock_patch('backend.app.services.assistant.request_structured',side_effect=AssertionError('Unexpected inference')):
            decision=choose_intent(text,{'language':'vi'},intake=s['cv_intake'])
        r=collect(s,decision,text,'task_'+'d'*32)
        groups={e['group']:e['items'] for e in r['intake']['profile']['skills']}
        self.assertEqual(groups,{
            'Ngôn ngữ lập trình':['Python','SQL (PostgreSQL, MySQL)'],
            'Framework & thư viện':['PyTorch','Hugging Face','Unsloth','LangGraph'],
            'Công cụ phát triển':['Git','Docker','Google Earth Engine','QGIS'],
        })
        entries=[dict(group=label,items=items) for label,items in groups.items()]
        self.assertEqual(group_skills(group_skills(entries)),entries)
        self.assertIn('ngoại ngữ',r['text'])

    def test_legacy_mixed_groups_are_reclassified_without_losing_skills(self):
        from backend.app.services.assistant_skills import group_skills
        entries=[{'group':'Kỹ năng khác','items':['SQL (PostgreSQL, MySQL)','Hugging Face','Unsloth','Google Earth Engine','QGIS']},
                 {'group':'AI & học máy','items':['PyTorch']},
                 {'group':'Framework & công cụ phát triển','items':['LangGraph','Git','Docker']}]
        grouped=group_skills(entries)
        self.assertEqual({e['group'] for e in grouped},{'Ngôn ngữ lập trình','Framework & thư viện','Công cụ phát triển'})
        self.assertEqual(sorted(item for e in entries for item in e['items']),sorted(item for e in grouped for item in e['items']))

    def session(self):
        i=blank_intake();i['profile']['contact'].update(full_name='An',email='an@example.com')
        i.update(target_role='AI Engineer',skipped=['education','experience','project'])
        return dict(cv_intake=i)

    def turn(self,s,text,updates=()):
        r=collect(s,IntentDecision(intent='build_cv',updates=list(updates)),text,'task_'+'c'*32)
        s['cv_intake']=r['_intake'];return r

    def test_exact_list_is_grouped_then_asks_languages(self):
        s=self.session()
        r=self.turn(s,'dùng được python, pytorch, langgraph, tensorflow, numpy, pandas, CNN, TRANSFORMER, RAG, PROMT engineering')
        groups={e['group']:e['items'] for e in r['intake']['profile']['skills']}
        self.assertEqual(groups['Ngôn ngữ lập trình'],['python'])
        self.assertIn('numpy',groups['Framework & thư viện'])
        self.assertIn('pandas',groups['Framework & thư viện'])
        self.assertIn('langgraph',groups['Framework & thư viện'])
        self.assertIn('CNN',groups['AI & học máy'])
        self.assertIn('PROMT engineering',groups['AI & học máy'])
        self.assertEqual(r['intake']['missing'][0],'skills.languages')
        self.assertIn('ngoại ngữ',r['text'])

    def test_language_level_and_no_certificate_preserve_technical_skills(self):
        s=self.session();self.turn(s,'Python')
        r=self.turn(s,'Tiếng Anh')
        self.assertTrue(r['intake']['missing'][0].endswith('.level'))
        r=self.turn(s,'đọc hiểu tài liệu')
        self.assertTrue(r['intake']['missing'][0].endswith('.certificate'))
        r=self.turn(s,'chưa có chứng chỉ')
        self.assertEqual(r['intake']['step'],'involvement')
        items=[x for g in r['intake']['profile']['skills'] for x in g['items']]
        self.assertIn('Python',items);self.assertIn('Tiếng Anh',items);self.assertIn('đọc hiểu tài liệu',items)
        self.assertNotIn('chưa có chứng chỉ',items)
        self.assertNotIn('skills',r['_intake']['skipped'])

    def test_certificate_not_yet_does_not_mean_no_language_or_level(self):
        s=self.session();self.turn(s,'Python')
        r=self.turn(s,'chưa có chứng chỉ')
        self.assertEqual(r['intake']['missing'][0],'skills.languages')
        self.turn(s,'Tiếng Anh')
        r=self.turn(s,'chưa có chứng chỉ')
        self.assertTrue(r['intake']['missing'][0].endswith('.level'))
        r=self.turn(s,'giao tiếp cơ bản')
        self.assertEqual(r['intake']['step'],'involvement')

    def test_all_language_details_in_one_message_avoids_repeating_questions(self):
        s=self.session();self.turn(s,'Python')
        r=self.turn(s,'Tiếng Anh IELTS 6.5, Tiếng Nhật N3')
        # Japanese proficiency N3 is not automatically a passed JLPT certificate.
        self.assertTrue(r['intake']['missing'][0].endswith('.certificate'))
        self.assertIn('Tiếng Nhật',r['text'])
        r=self.turn(s,'JLPT N3')
        self.assertEqual(r['intake']['step'],'involvement')
        self.assertEqual(len(r['intake']['profile']['skills']),3)

    def test_decline_languages_preserves_existing_categories(self):
        s=self.session();self.turn(s,'Python, pandas')
        r=self.turn(s,'chưa có ngoại ngữ')
        self.assertEqual(r['intake']['step'],'involvement')
        self.assertEqual(len(r['intake']['profile']['skills']),2)

    def test_certificate_year_does_not_count_as_proficiency_score(self):
        from backend.app.services.assistant_skills import language_missing
        i=blank_intake();i['profile']['skills']=[dict(group='Ngoại ngữ',items=['Tiếng Anh, IELTS thi năm 2024'])]
        self.assertEqual(language_missing(i),['skills.0.level'])
