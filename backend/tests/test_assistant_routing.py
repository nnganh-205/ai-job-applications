import unittest
from unittest.mock import patch

from ai.llm.ollama_client import OllamaSchemaError
from pydantic import ValidationError
from backend.app.schemas.assistant import IntentDecision
from backend.app.services.assistant import choose_intent
from backend.app.services.assistant_intake import blank_intake, apply_updates
from backend.app.services.assistant_routing import ChatDecision, expand_decision, routing_payload


class AssistantRoutingTests(unittest.TestCase):
    def test_experience_with_dates_at_end_keeps_typos_and_full_clauses(self):
        text = ('Từng làm ở Example Lab, làm AI engieer Intern , làm những việc : '
                'Xây dựng pipeline dữ liệu (Python, Pandas, SQL) cho xử lý ngôn ngữ tự nhiên (NLP) và thị giác máy tính (CV), '
                'Nghiên cứu, fine-tuning mô hình (LLM với LoRA) và phát triển RAG (ChromaDB/Qdrant).'
                'Triển khai microservice (FastAPI, Docker) và tối ưu thời gian suy luận (inference latency). '
                'Bắt đầu 3/2026 - 6/2026\n')
        intake = blank_intake()
        with patch('backend.app.services.assistant.request_structured', side_effect=AssertionError('Unexpected inference')):
            decision = choose_intent(text, {'language':'vi'}, intake=intake)
        result, rejected = apply_updates(intake, decision.updates, text)
        self.assertEqual(rejected,0)
        entry = result['profile']['experience'][0]
        self.assertEqual(entry['company'],'Example Lab')
        self.assertEqual(entry['job_title'],'AI engieer Intern')
        self.assertEqual((entry['start_date'],entry['end_date']),('3/2026','6/2026'))
        self.assertEqual(len(entry['description']),3)
        self.assertIn('(Python, Pandas, SQL)',entry['description'][0])
        self.assertIn('ngôn ngữ tự nhiên (NLP)',entry['description'][0])
        self.assertIn('(inference latency)',entry['description'][2])
        self.assertNotIn('Bắt đầu',entry['description'][2])

    def test_rewritten_model_values_get_one_source_preserving_repair(self):
        from backend.app.services.assistant_grounding import SourceUpdates
        import re
        text = 'Mình đảm nhận vai trò AI engieer và xây dựng luồng xử lý ngôn ngữ tự nhiên (NLP).'
        bad = ChatDecision(intent='build_cv',updates=[dict(path='experience.0.job_title',value='AI engineer')])
        words = list(re.finditer(r'\S+',text))
        start = next(i for i,m in enumerate(words) if m.group()=='AI')
        good = SourceUpdates(updates=[dict(path='experience.0.job_title',spans=[dict(start=start,end=start+2)])])
        with patch('backend.app.services.assistant.request_structured',side_effect=[bad,good]) as model:
            decision = choose_intent(text,{'language':'vi'},intake=blank_intake())
        self.assertEqual(model.call_count,2)
        intake,rejected = apply_updates(None,decision.updates,text)
        self.assertEqual(rejected,0)
        self.assertEqual(intake['profile']['experience'][0]['job_title'],'AI engieer')
        self.assertIn('source_tokens',model.call_args.args[0][-1]['content'])

    def test_failed_source_repair_never_applies_invented_facts(self):
        from backend.app.services.assistant_grounding import SourceUpdates
        text = 'Mình đảm nhận vai trò AI engieer.'
        bad = ChatDecision(intent='build_cv',updates=[dict(path='experience.0.job_title',value='Senior AI Engineer')])
        intake = blank_intake()
        invalid = SourceUpdates(updates=[dict(path='experience.0.job_title',spans=[dict(start=0,end=9999)])])
        with patch('backend.app.services.assistant.request_structured',side_effect=[bad,invalid]) as model:
            with self.assertRaises(OllamaSchemaError):choose_intent(text,{'language':'vi'},intake=intake)
        self.assertEqual(model.call_count,2)
        self.assertEqual(intake['profile']['experience'],[])

    def test_explicit_experience_keeps_all_facts_without_inference(self):
        from backend.app.services.assistant_intake import collect
        text = 'Từng làm Intern ở FPT Telecom, tháng 6/2025 đến 9/2025, làm vị trí AI engineer, cụ thể Xây dựng hệ thống RAG nội bộ, Xây dựng thuật toán XG boost dự đoán xác suất mua hàng'
        intake = blank_intake()
        intake['profile']['contact']['full_name'] = 'An'
        with patch('backend.app.services.assistant.request_structured', side_effect=AssertionError('Unexpected inference')):
            decision = choose_intent(text, {'language': 'vi'}, intake=intake)
        result = collect({'cv_intake': intake}, decision, text, 'task_' + 'a' * 32)
        entry = result['intake']['profile']['experience'][0]
        self.assertEqual(entry['company'], 'FPT Telecom')
        self.assertEqual(entry['job_title'], 'AI engineer')
        self.assertEqual(entry['employment_type'], 'Intern')
        self.assertEqual((entry['start_date'], entry['end_date']), ('6/2025', '9/2025'))
        self.assertEqual(len(entry['description']), 2)
        self.assertIsNone(entry['is_current'])
        self.assertIsNone(decision.intake_signal)
        self.assertIn('email hoặc số điện thoại', result['text'])

    def test_inferred_boolean_and_writer_signal_do_not_discard_facts(self):
        from backend.app.services.assistant_intake import collect, validated_signal
        from backend.app.schemas.assistant import IntakeSignal
        text = 'Từng làm Intern ở FPT Telecom, tháng 6/2025 đến 9/2025'
        result = ChatDecision(intent='build_cv', updates=[
            dict(path='experience.0.company', value='FPT Telecom'),
            dict(path='experience.0.employment_type', value='Intern'),
            dict(path='experience.0.is_current', value=False),
        ])
        decision = expand_decision(result, text)
        signal = IntakeSignal(kind='write_bullets', section='experience', evidence=text)
        self.assertIsNone(validated_signal(signal, text))
        decision.intake_signal = signal
        with patch('backend.app.services.cv_polish.chat_proposals', return_value=[]) as polish:
            intake = collect({'cv_intake': blank_intake()}, decision, text, 'task_' + 'b' * 32, polish_with_model=True)
        self.assertFalse(polish.call_args.kwargs['use_model'])
        self.assertEqual(intake['intake']['profile']['experience'][0]['company'], 'FPT Telecom')
        self.assertFalse(any(p.field == 'is_current' for p in decision.updates))
        self.assertIsNotNone(validated_signal(IntakeSignal(kind='write_bullets', section='experience', evidence='Viết lại mô tả thành bullet'), 'Viết lại mô tả thành bullet'))

    def test_experience_parser_defers_ambiguous_and_hypothetical_changes(self):
        from backend.app.services.assistant_routing import explicit_experience
        intake = blank_intake()
        text = 'Tôi đã làm tại Công ty ABC, từ 1/2024 đến 6/2024, vị trí Developer, công việc: Phát triển API; Kiểm thử ứng dụng'
        decision = explicit_experience(text, intake)
        self.assertIsNotNone(decision)
        changed, rejected = apply_updates(intake, decision.updates, text)
        self.assertEqual(rejected, 0)
        self.assertEqual(len(changed['profile']['experience'][0]['description']), 2)
        self.assertIsNotNone(explicit_experience(text, changed))
        changed['profile']['experience'][0]['job_title'] = 'Tester'
        self.assertIsNone(explicit_experience(text, changed))
        self.assertIsNone(explicit_experience(text + ' nếu có dữ liệu', intake))
        self.assertIsNone(explicit_experience(text + '?', intake))

    def test_contact_request_is_single_explanation_and_instruction(self):
        from backend.app.services.assistant_intake import collect, question
        intake = blank_intake()
        intake['profile']['contact']['full_name'] = 'An'
        decision = IntentDecision(intent='build_cv', reply='Bạn cần cung cấp email hoặc số điện thoại để nhà tuyển dụng liên hệ. Bạn muốn dùng email hay số điện thoại?')
        result = collect({'cv_intake': intake}, decision, 'tiếp tục', 'task_' + 'c' * 32)
        self.assertEqual(result['text'], question('contact.reach', intake))
        self.assertNotIn('?', result['text'])

    def test_short_field_answers_do_not_need_inference_or_rewrite_facts(self):
        intake = blank_intake()
        intake['profile']['contact'] = dict(full_name='An', email='an@example.com')
        with patch('backend.app.services.assistant.request_structured', side_effect=AssertionError('Unexpected inference')):
            decision = choose_intent('Backend Developer', {'language': 'vi'}, intake=intake)
            self.assertEqual(decision.updates[0].section, 'target_role')
            intake['target_role'] = 'Backend Developer'
            intake['profile']['education'] = [dict(institution='NEU')]
            decision = choose_intent('Công nghệ thông tin', {'language': 'vi'}, intake=intake)
            self.assertEqual(decision.updates[0].field, 'major')
            self.assertEqual(decision.updates[0].value, 'Công nghệ thông tin')

    def test_skills_cannot_be_silently_written_only_as_group_labels(self):
        with self.assertRaises(ValidationError):
            ChatDecision(intent='build_cv', updates=[dict(path='skills.0.group', value='Python')])

    def test_no_intake_means_no_intake_signal_in_generation(self):
        from backend.app.services.assistant_routing import StandaloneChatDecision
        with self.assertRaises(ValidationError):
            StandaloneChatDecision(intent='build_cv', intake_signal=dict(kind='skip', section='education', evidence='học CNTT'))

    def test_short_chat_uses_small_context_and_long_input_is_preserved(self):
        from ai.llm.ollama_client import generation_options
        short = [{'role': 'system', 'content': 'CV assistant'}, {'role': 'user', 'content': 'TIN NHẮN HIỆN TẠI:\nXin chào'}]
        self.assertEqual(generation_options(short, 'assistant')['num_ctx'], 4096)
        self.assertEqual(generation_options(short, 'assistant')['num_predict'], 1024)
        long = [{'role': 'user', 'content': 'TIN NHẮN HIỆN TẠI:\n' + 'dữ kiện ' * 2000}]
        self.assertGreater(generation_options(long, 'assistant')['num_ctx'], 4096)
        self.assertEqual(generation_options(long, 'assistant')['num_predict'], 2048)
        self.assertEqual(long[0]['content'].count('dữ kiện '), 2000)

    def test_greeting_create_and_contact_answers_do_not_need_inference(self):
        intake = blank_intake()
        with patch('backend.app.services.assistant.request_structured', side_effect=AssertionError('Unexpected inference')):
            self.assertEqual(choose_intent('Xin chào!', {'language': 'vi'}).intent, 'advice')
            self.assertEqual(choose_intent('Tôi muốn tạo CV', {'language': 'vi'}).intent, 'build_cv')
            decision = choose_intent('Nguyễn Minh An', {'language': 'vi'}, intake=intake)
            intake, rejected = apply_updates(intake, decision.updates, 'Nguyễn Minh An')
            self.assertEqual(rejected, 0)
            decision = choose_intent('an@example.com', {'language': 'vi'}, intake=intake)
            self.assertEqual(decision.updates[0].field, 'email')
            self.assertEqual(decision.updates[0].value, 'an@example.com')

    def test_commands_and_questions_are_not_names(self):
        intake = blank_intake()
        for text in ('Xóa Dự Án', 'Tên Nên Viết Thế Nào?', 'mình dùng Python', 'Ngành Công Nghệ Thông Tin'):
            with self.subTest(text=text), patch('backend.app.services.assistant.request_structured',
                    return_value=IntentDecision(intent='clarify', reply='Bạn muốn sửa phần nào?')) as model:
                result = choose_intent(text, {'language': 'vi'}, intake=intake)
                self.assertFalse(result.updates)
                model.assert_called_once()

    def test_compact_updates_keep_existing_source_validation(self):
        text = 'Tên mình là An, biết Python và React'
        result = ChatDecision(intent='build_cv', updates=[
            dict(path='contact.full_name', value='An'),
            dict(path='skills.0.items', value=['Python', 'React']),
        ])
        decision = expand_decision(result, text)
        intake, rejected = apply_updates(None, decision.updates, text)
        self.assertEqual(rejected, 0)
        self.assertEqual(intake['profile']['contact']['full_name'], 'An')
        self.assertEqual(intake['profile']['skills'][0]['items'], ['Python', 'React'])
        result.updates[1].value = ['Python', 'Kubernetes']
        with self.assertRaises(OllamaSchemaError):
            expand_decision(result, text)

    def test_invalid_paths_and_unrequested_deletion_are_rejected(self):
        for path, operation, text, value in (
            ('project', 'set', 'Python', 'Python'),
            ('project.99.role', 'set', 'Developer', 'Developer'),
            ('contact.full_name.extra', 'set', 'An', 'An'),
            ('project.0', 'remove_entry', 'Dự án Python', None),
        ):
            with self.subTest(path=path), self.assertRaises((OllamaSchemaError, ValidationError)):
                expand_decision(ChatDecision(intent='build_cv', updates=[
                    dict(path=path, operation=operation, value=value)]), text)

    def test_context_preserves_indices_focus_and_named_entries_without_duplicate_history(self):
        intake = blank_intake()
        intake['profile']['contact'] = dict(full_name='An', email='an@example.com')
        intake['target_role'] = 'Developer'
        intake['skipped'] = ['education', 'experience']
        intake['profile']['project'] = [
            dict(project_name='Blog', role='Developer', description=['FIRST PRIVATE DESCRIPTION'] * 100),
            dict(project_name='Shop', role='Developer', description=['SECOND PRIVATE DESCRIPTION']),
        ]
        history = [dict(role='assistant', text='Question ' * 1000), dict(role='user', text='Answer ' * 1000)] * 10
        recent, payload = routing_payload('Sửa dự án Shop', {'language': 'vi', 'document': 'HIDDEN DOCUMENT'}, history, intake)
        self.assertLessEqual(sum(len(m['content']) for m in recent), 1800)
        self.assertLessEqual(len(recent), 4)
        self.assertEqual(len(payload['cv_intake']['profile']['project']), 2)
        self.assertNotIn('description', payload['cv_intake']['profile']['project'][0])
        self.assertEqual(payload['cv_intake']['profile']['project'][1]['description'], ['SECOND PRIVATE DESCRIPTION'])
        self.assertNotIn('document', payload)
        self.assertNotIn('entry', payload.get('expected_answer') or {})

    def test_long_input_uses_actual_local_quote_without_truncating_facts(self):
        value = 'Python'
        text = 'Giới thiệu. ' * 200 + 'Kỹ năng: Python'
        decision = expand_decision(ChatDecision(intent='build_cv', updates=[
            dict(path='skills.0.items', value=[value])]), text)
        self.assertEqual(decision.updates[0].evidence, value)
        self.assertIn(decision.updates[0].evidence, text)
