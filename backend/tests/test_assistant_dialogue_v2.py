import unittest
from backend.app.services.assistant_intake import blank_intake, collect, missing_fields, direct_signal
from backend.app.schemas.assistant import IntentDecision, ProfilePatch, IntakeSignal

class DialogueV2Tests(unittest.TestCase):
    def state(self):
        i=blank_intake();i['list_collection_version']=2
        i['profile']['contact']={'full_name':'An','email':'an@example.com'}
        i['target_role']='Developer';i['profile']['education']=[{'institution':'NEU','major':'CNTT'}]
        return i

    def turn(self,i,text,updates=(),signal=None,reply=''):
        return collect({'cv_intake':i},IntentDecision(intent='build_cv',updates=list(updates),intake_signal=signal,reply=reply),text,'task_'+'a'*32)

    def test_education_list_asks_and_explains_without_skipping(self):
        i=self.state();self.assertEqual(missing_fields(i)[0],'education.more')
        result=self.turn(i,'là sao')
        self.assertEqual(result['intake']['profile'],i['profile'])
        self.assertEqual(result['intake']['missing'][0],'education.more')
        result=self.turn(result['_intake'],'hết rồi')
        self.assertEqual(result['intake']['missing'][0],'experience')

    def test_add_second_education_preserves_first_and_checks_missing_major(self):
        i=self.state();r=self.turn(i,'còn');i=r['_intake']
        self.assertEqual(missing_fields(i)[0],'education.1.institution')
        r=self.turn(i,'HUST',[ProfilePatch(section='education',index=1,field='institution',value='HUST',evidence='HUST')])
        self.assertEqual(r['intake']['profile']['education'][0]['institution'],'NEU')
        self.assertEqual(r['intake']['missing'][0],'education.1.major')

    def test_experience_list_completion_and_absence_have_different_scopes(self):
        i=self.state();i['education_confirmed_count']=1
        i['profile']['experience']=[{'company':'ABC','job_title':'Intern','description':['Kiểm thử giao diện']}]
        self.assertEqual(missing_fields(i)[0],'experience.more')
        r=self.turn(i,'không còn công việc nào khác')
        self.assertEqual(r['intake']['missing'][0],'project')
        self.assertEqual(len(r['intake']['profile']['experience']),1)

    def test_mixed_question_records_two_facts_and_still_answers_question(self):
        i=self.state();text='mình học NEU ngành CNTT, kinh nghiệm là gì?'
        self.assertIsNone(direct_signal(i,text))
        patches=[ProfilePatch(section='education',index=0,field=f,value=v,evidence=text) for f,v in [('institution','NEU'),('major','CNTT')]]
        r=self.turn(i,text,patches,IntakeSignal(kind='explain',section='experience',evidence=text),reply='Kinh nghiệm gồm việc làm và thực tập thực tế.')
        self.assertEqual(r['intake']['profile']['education'][0]['major'],'CNTT')
        self.assertIn('Kinh nghiệm gồm',r['text'])
        self.assertIn('trường: NEU',r['text'])
        self.assertNotIn('experience',r['_intake']['skipped'])

    def test_hypothetical_question_is_never_recorded_as_role(self):
        i=self.state();i['education_confirmed_count']=1;i['skipped']=['experience']
        i['profile']['project']=[{'project_name':'Blog'}]
        text='ví dụ mình làm trưởng nhóm thì sao?'
        r=self.turn(i,text,[ProfilePatch(section='project',index=0,field='role',value='trưởng nhóm',evidence=text)],IntakeSignal(kind='explain',section='project',evidence=text))
        self.assertFalse(r['intake']['profile']['project'][0].get('role'))

    def test_mixed_real_fact_and_hypothetical_role_only_records_real_fact(self):
        i=self.state();i['education_confirmed_count']=1;i['skipped']=['experience'];i['profile']['project']=[{'project_name':'Blog'}]
        text='mình làm giao diện, ví dụ mình làm trưởng nhóm thì sao?'
        patches=[ProfilePatch(section='project',index=0,field=f,value=v,evidence=text) for f,v in [('description',['giao diện']),('role','trưởng nhóm')]]
        r=self.turn(i,text,patches,IntakeSignal(kind='explain',section='project',evidence=text))
        self.assertEqual(r['intake']['profile']['project'][0]['description'],['giao diện'])
        self.assertFalse(r['intake']['profile']['project'][0].get('role'))

    def test_old_session_does_not_reask_previous_education(self):
        from backend.app.services.assistant_lists import upgrade_lists
        i=self.state();i.pop('list_collection_version')
        self.assertEqual(missing_fields(i)[0],'experience')
        upgraded=upgrade_lists(i)
        self.assertEqual(missing_fields(upgraded)[0],'experience')
        self.assertEqual(upgraded['education_confirmed_count'],1)
        self.assertNotIn('list_collection_version',i)

    def test_question_is_answered_even_when_model_only_acknowledges_facts(self):
        i=self.state();i['education_confirmed_count']=1
        text='Mình từng thực tập tại ABC, vị trí Tester, công việc là kiểm thử giao diện. Mình chưa có số liệu kết quả, phần kết quả có bắt buộc không?'
        patches=[ProfilePatch(section='experience',index=0,field=f,value=v,evidence=text) for f,v in [('company','ABC'),('role','Tester'),('description',['kiểm thử giao diện'])]]
        r=self.turn(i,text,patches,reply='Mình đã nhận mô tả công việc của bạn.')
        self.assertIn('Không bắt buộc có số liệu',r['text'])
        self.assertIn('không tự đặt số liệu',r['text'])
        self.assertEqual(r['intake']['missing'][0],'experience.more')
        self.assertEqual(r['intake']['profile']['experience'][0]['company'],'ABC')
