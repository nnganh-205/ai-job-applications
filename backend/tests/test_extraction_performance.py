import unittest
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from unittest.mock import patch

from ai.llm import profile_extractor as extractor
from ai.llm.ollama_client import OllamaSchemaError, generation_options
from ai.graph import profile_workflow
from backend.app.schemas.profile import MasterProfile


def profile():
    return MasterProfile(contact={'full_name': 'Test Candidate'}, experience=[],
                         project=[], education=[], involvement=[], skills=[])


class ExtractionPerformanceTests(unittest.TestCase):
    def setUp(self):
        with extractor._cache_lock:
            extractor._cache.clear()

    def test_compact_response_preserves_form_fields_and_original_prose(self):
        value = extractor.ExtractionProfile.model_validate({
            'contact': {'full_name': 'Nguyễn An', 'date_of_birth': '15/08/2004'},
            'experience': [{'company': 'ABC', 'job_title': 'Developer',
                            'description': ['Xây dựng 20 API bằng Python.']}],
            'project': [{'project_name': 'Demo', 'technologies': ['Python']}],
            'education': [{'institution': 'NEU', 'gpa': '3.6/4.0'}],
            'involvement': [], 'skills': [{'group': 'Code', 'items': ['Python']}],
            'certifications': [{'name': 'AWS', 'date': '2024'}],
            'awards': [{'title': 'Giải nhất'}],
            'references': [{'full_name': 'Reviewer', 'phone': '0901234567'}],
        })
        with patch.object(extractor, 'request_structured', return_value=value):
            result = extractor.request_profile('source')
        self.assertEqual(result.experience[0].description, ['Xây dựng 20 API bằng Python.'])
        self.assertEqual(result.contact.date_of_birth, '15/08/2004')
        self.assertEqual(result.education[0].gpa, '3.6/4.0')
        self.assertEqual(result.certifications[0].name, 'AWS')
        self.assertEqual(result.references[0].phone, '0901234567')

    def test_repeat_upload_reuses_result_without_sharing_mutable_profile(self):
        with patch.object(extractor, 'request_profile', return_value=profile()) as request:
            first = extractor.extract_profile_with_retry('same CV')
            first.contact.full_name = 'Edited by user'
            second = extractor.extract_profile_with_retry('same CV')
        self.assertEqual(second.contact.full_name, 'Test Candidate')
        self.assertEqual(request.call_count, 1)

    def test_distinct_documents_and_expired_results_are_reextracted(self):
        with patch.object(extractor, 'request_profile', side_effect=lambda _: profile()) as request:
            extractor.extract_profile_with_retry('CV one')
            extractor.extract_profile_with_retry('CV two')
            with patch.object(extractor, '_CACHE_TTL', -1):
                extractor.extract_profile_with_retry('CV one')
        self.assertEqual(request.call_count, 3)

    def test_concurrent_repeat_uploads_share_one_inference(self):
        started, release = Event(), Event()
        def infer(_):
            started.set()
            if not release.wait(5): raise TimeoutError('test inference not released')
            return profile()
        with patch.object(extractor, 'request_profile', side_effect=infer) as request:
            with ThreadPoolExecutor(max_workers=2) as pool:
                first = pool.submit(extractor.extract_profile_with_retry, 'concurrent CV')
                self.assertTrue(started.wait(5))
                second = pool.submit(extractor.extract_profile_with_retry, 'concurrent CV')
                release.set()
                self.assertEqual(first.result().model_dump(), second.result().model_dump())
        self.assertEqual(request.call_count, 1)

    def test_failed_inference_is_not_cached_and_retry_remains_available(self):
        with patch.object(extractor, 'request_profile', side_effect=OllamaSchemaError('invalid')) as request:
            with self.assertRaises(OllamaSchemaError): extractor.extract_profile_with_retry('bad CV')
            self.assertEqual(request.call_count, 2)
        with patch.object(extractor, 'request_profile', return_value=profile()) as request:
            extractor.extract_profile_with_retry('bad CV')
            request.assert_called_once()

    def test_start_does_not_checkpoint_uploaded_binary(self):
        with patch.object(profile_workflow, 'read_cv', return_value='CV text'), \
             patch.object(profile_workflow, 'profile_graph') as graph:
            profile_workflow.start_extraction('resume.pdf', b'large uploaded file', 'thread')
        state = graph.invoke.call_args.args[0]
        self.assertNotIn('file_bytes', state)
        self.assertEqual(state['resume_text'], 'CV text')

    def test_short_cv_context_has_room_without_using_16k(self):
        messages = [{'role': 'system', 'content': 'extract facts ' * 150},
                    {'role': 'user', 'content': 'CV source ' * 100}]
        options = generation_options(messages, 'profile')
        self.assertEqual(options['num_ctx'], 8192)
        self.assertGreaterEqual(options['num_predict'], 3072)

    def test_title_repair_sends_only_entry_sources(self):
        value = extractor.JobTitleResult(items=[{'experience_index': 0, 'job_title': 'Developer'}])
        with patch.object(extractor, 'request_structured', return_value=value) as request:
            result = extractor.extract_missing_job_titles('unrelated private section', [
                {'experience_index': 0, 'company': 'ABC', 'source_excerpt': 'Developer | ABC'},
            ])
        self.assertEqual(result[0], 'Developer')
        self.assertNotIn('unrelated private section', request.call_args.args[0][0]['content'])
        self.assertIn('Developer | ABC', request.call_args.args[0][0]['content'])
