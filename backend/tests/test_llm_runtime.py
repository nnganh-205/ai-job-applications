import json
import os
import unittest
import weakref
import gc
from unittest.mock import patch

import httpx
from pydantic import BaseModel, create_model

from ai.llm import ollama_client as client
from backend.app.core.config import Settings


class Output(BaseModel):
    value: str


class LLMRuntimeTests(unittest.TestCase):
    def test_legacy_exports_cannot_keep_tasks_on_4b(self):
        names = ['LLM_MODEL', 'PROFILE_MODEL', 'JD_MODEL', 'UPDATE_MODEL', 'CV_MODEL',
                 'FORM_CV_MODEL', 'ASSISTANT_MODEL', 'INTERVIEW_MODEL', 'VERIFIER_MODEL']
        with patch.dict(os.environ, {key: 'qwen3:4b' for key in names}, clear=True):
            settings = Settings.from_environment()
        for task in ('default', 'profile', 'jd', 'update', 'cv', 'form', 'assistant', 'interview', 'verifier'):
            self.assertEqual(settings.model_for_task(task), 'qwen3:8b')
        self.assertEqual(settings.model_for_task('writer'), 'kltn-writer-8b-unsloth:latest')

    def test_context_expands_without_modifying_long_input(self):
        short = [{'role': 'user', 'content': 'Compare these facts.'}]
        long = [{'role': 'user', 'content': 'dữ kiện ' * 2500}]
        with patch.object(client, 'CONTEXT_LENGTH', 16384):
            self.assertEqual(client.generation_options(short, 'verifier')['num_ctx'], 8192)
            self.assertEqual(client.generation_options(long, 'verifier')['num_ctx'], 16384)
        self.assertEqual(long[0]['content'], 'dữ kiện ' * 2500)

    def test_shared_transport_routes_tasks_and_preserves_schema_validation(self):
        requests = []
        def respond(request):
            requests.append(json.loads(request.content))
            return httpx.Response(200, json={'message': {'content': '{"value":"ok"}'}, 'done': True})
        with httpx.Client(transport=httpx.MockTransport(respond)) as transport:
            with patch.object(client, '_client', transport):
                for task in ('jd', 'assistant', 'verifier'):
                    self.assertEqual(client.request_structured([{'role': 'user', 'content': 'test'}], Output, task=task).value, 'ok')
        self.assertTrue(all(r['model'] == 'qwen3:8b' for r in requests))
        self.assertTrue(all(r['think'] is False and r['stream'] is False for r in requests))
        self.assertTrue(all(r['format'] == Output.model_json_schema() for r in requests))

    def test_dynamic_schemas_are_not_retained_after_request(self):
        model = create_model('TemporaryOutput', value=(str, ...))
        reference = weakref.ref(model)
        client.response_schema(model)
        del model
        gc.collect()
        self.assertIsNone(reference())

    def test_expired_deadline_does_not_send_request(self):
        with patch.object(client._client, 'post') as post, client.llm_deadline(-1):
            with self.assertRaises(client.OllamaTimeoutError):
                client.request_structured([], Output)
        post.assert_not_called()

    def test_invalid_or_truncated_output_is_never_accepted(self):
        for body in (
            {'message': {'content': '{"value":"ok"}'}, 'done_reason': 'length'},
            {'message': {'content': '{"wrong":true}'}},
            {'message': {'content': 'incomplete'}},
        ):
            with self.subTest(body=body), httpx.Client(transport=httpx.MockTransport(
                lambda request: httpx.Response(200, json=body)
            )) as transport, patch.object(client, '_client', transport):
                with self.assertRaises(client.OllamaResponseError):
                    client.request_structured([], Output)
