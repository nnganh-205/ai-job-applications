import json
import os
import unittest
from dataclasses import replace
from unittest.mock import patch

import httpx
from pydantic import BaseModel

from ai.llm import ollama_client as client
from backend.app.core.config import Settings


class Output(BaseModel):
    value: str


class GroqRuntimeTests(unittest.TestCase):
    def config(self):
        return replace(Settings(), groq_api_key='test-secret-not-real', groq_tasks=('profile','assistant'))

    def test_environment_routes_only_selected_tasks_and_hides_key(self):
        with patch.dict(os.environ, {'GROQ_API_KEY':'test-secret-not-real', 'GROQ_TASKS':'profile, assistant'}, clear=True):
            settings = Settings.from_environment()
        self.assertEqual(settings.provider_for_task('profile'), 'groq')
        self.assertEqual(settings.model_for_task('assistant'), 'openai/gpt-oss-120b')
        self.assertEqual(settings.provider_for_task('writer'), 'ollama')
        self.assertEqual(settings.model_for_task('writer'), 'kltn-writer-8b-unsloth:latest')
        self.assertEqual(settings.provider_for_task('refine'),'ollama')
        self.assertEqual(settings.model_for_task('refine'),'kltn-writer-8b-unsloth:latest')
        self.assertEqual(settings.model_for_task('jd'), 'qwen3:8b')
        self.assertNotIn('test-secret-not-real',repr(settings))

    def test_invalid_configuration_fails_before_sending_data(self):
        for env in [{'GROQ_TASKS':'profile'}, {'GROQ_TASKS':'typo','GROQ_API_KEY':'test'}, {'GROQ_TIMEOUT_SECONDS':'0'}]:
            with self.subTest(env=env), patch.dict(os.environ,env,clear=True), self.assertRaises(ValueError):
                Settings.from_environment()

    def test_refinement_uses_local_finetuned_writer_and_local_limits(self):
        with patch.dict(os.environ,{'GROQ_TASKS':'profile,assistant','GROQ_API_KEY':'test',
                                   'WRITER_MODEL':'custom-finetuned:latest'},clear=True):
            settings=Settings.from_environment()
        self.assertEqual(settings.model_for_task('refine'),'custom-finetuned:latest')
        requests=[]
        def respond(request):
            requests.append(request)
            return httpx.Response(200,json={'done':True,'message':{'content':'{"value":"ok"}'}})
        with httpx.Client(transport=httpx.MockTransport(respond)) as transport, \
             patch.object(client,'_client',transport),patch.object(client,'settings',settings):
            client.request_structured([],Output,task='refine')
            client.request_structured([],Output,task='refine',max_output_tokens=2048)
        self.assertTrue(all(request.url.host=='127.0.0.1' for request in requests))
        for request in requests:
            body=json.loads(request.content)
            self.assertEqual(body['model'],'custom-finetuned:latest')
            self.assertEqual(body['options']['num_predict'],1200)
            self.assertIs(body['think'],False)
            self.assertNotIn('authorization',request.headers)

    def test_explicit_refine_override_is_respected(self):
        with patch.dict(os.environ,{'WRITER_MODEL':'custom-finetuned:latest','REFINE_MODEL':'qwen3:8b'},clear=True):
            settings=Settings.from_environment()
        self.assertEqual(settings.model_for_task('writer'),'custom-finetuned:latest')
        self.assertEqual(settings.model_for_task('refine'),'qwen3:8b')

    def test_per_task_models_and_common_model_fallback(self):
        env={'GROQ_API_KEY':'test', 'GROQ_TASKS':'assistant,profile,jd',
             'GROQ_MODEL':'common-model', 'GROQ_ASSISTANT_MODEL':' openai/gpt-oss-20b ',
             'GROQ_PROFILE_MODEL':'openai/gpt-oss-120b'}
        with patch.dict(os.environ,env,clear=True):
            settings=Settings.from_environment()
        self.assertEqual(settings.model_for_task('assistant'),'openai/gpt-oss-20b')
        self.assertEqual(settings.model_for_task('profile'),'openai/gpt-oss-120b')
        self.assertEqual(settings.model_for_task('jd'),'common-model')
        self.assertEqual(settings.provider_for_task('writer'),'ollama')
        self.assertEqual(settings.model_for_task('writer'),'kltn-writer-8b-unsloth:latest')
        env.update(GROQ_ASSISTANT_MODEL=' ',GROQ_PROFILE_MODEL='')
        with patch.dict(os.environ,env,clear=True):
            settings=Settings.from_environment()
        self.assertEqual(settings.model_for_task('assistant'),'common-model')
        self.assertEqual(settings.model_for_task('profile'),'common-model')

    def test_wire_model_follows_task_override(self):
        seen=[]
        def respond(request):
            seen.append(json.loads(request.content))
            return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':'{"value":"ok"}'}}]})
        settings=replace(self.config(),groq_assistant_model='openai/gpt-oss-20b',groq_profile_model='openai/gpt-oss-120b')
        with httpx.Client(transport=httpx.MockTransport(respond)) as transport, \
             patch.object(client,'_client',transport),patch.object(client,'settings',settings):
            client.request_structured([],Output,task='assistant')
            client.request_structured([],Output,task='profile')
        self.assertEqual([body['model'] for body in seen],['openai/gpt-oss-20b','openai/gpt-oss-120b'])
        self.assertTrue(all(body['reasoning_effort']=='low' for body in seen))

    def test_groq_wire_format_and_local_writer_are_separate(self):
        requests = []
        def respond(request):
            requests.append(request)
            if request.url.host == 'api.groq.com':
                return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':'{"value":"ok"}'}}]})
            return httpx.Response(200,json={'done':True,'message':{'content':'{"value":"local"}'}})
        with httpx.Client(transport=httpx.MockTransport(respond)) as transport, \
             patch.object(client,'_client',transport), patch.object(client,'settings',self.config()):
            self.assertEqual(client.request_structured([],Output,task='profile').value,'ok')
            self.assertEqual(client.request_structured([],Output,task='writer').value,'local')
        cloud = json.loads(requests[0].content)
        self.assertEqual(cloud['model'],'openai/gpt-oss-120b')
        self.assertEqual(cloud['response_format']['json_schema']['schema'],Output.model_json_schema())
        self.assertEqual(cloud['reasoning_effort'],'low')
        self.assertNotIn('keep_alive',cloud)
        self.assertNotIn('think',cloud)
        self.assertEqual(requests[0].headers['authorization'],'Bearer test-secret-not-real')
        self.assertNotIn('authorization',requests[1].headers)

    def test_quota_and_auth_errors_are_safe_without_local_fallback(self):
        for status in [401,403,429,500]:
            seen = []
            def respond(request):
                seen.append(request)
                return httpx.Response(status,json={'error':'private CV text and key'})
            with self.subTest(status=status), httpx.Client(transport=httpx.MockTransport(respond)) as transport, \
                 patch.object(client,'_client',transport), patch.object(client,'settings',self.config()):
                with self.assertRaises(client.OllamaError) as error:
                    client.request_structured([],Output,task='profile')
                self.assertNotIn('private CV',str(error.exception))
                self.assertNotIn('test-secret-not-real',str(error.exception))
                self.assertEqual(len(seen),1)
                self.assertEqual(seen[0].url.host,'api.groq.com')

    def test_partial_refused_and_wrong_schema_results_are_not_accepted(self):
        for choice in [
            {'finish_reason':'length','message':{'content':'{"value":"partial"}'}},
            {'finish_reason':'stop','message':{'refusal':'refused','content':None}},
            {'finish_reason':'stop','message':{'content':'{"wrong":true}'}},
        ]:
            with self.subTest(choice=choice), httpx.Client(transport=httpx.MockTransport(
                    lambda request:httpx.Response(200,json={'choices':[choice]})
                 )) as transport, patch.object(client,'_client',transport), patch.object(client,'settings',self.config()):
                with self.assertRaises(client.OllamaError):client.request_structured([],Output,task='profile')

    def test_deadline_also_limits_cloud_calls(self):
        with patch.object(client,'settings',self.config()), patch.object(client._client,'post') as post, client.llm_deadline(-1):
            with self.assertRaises(client.OllamaTimeoutError):client.request_structured([],Output,task='profile')
        post.assert_not_called()
