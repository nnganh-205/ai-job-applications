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


class CloudflareRuntimeTests(unittest.TestCase):
    def config(self):
        return replace(Settings(),cloudflare_account_id='a'*32,cloudflare_api_token='test-cloudflare-secret',
            cloudflare_tasks=('jd','cv','interview','verifier'),cloudflare_cv_model='@cf/qwen/qwen3.8-27b',
            groq_api_key='test-groq-secret',groq_tasks=('profile','assistant','update'),groq_assistant_model='openai/gpt-oss-20b')

    def test_task_routing_and_finetuned_model_are_separate(self):
        settings=self.config()
        self.assertEqual(settings.model_for_task('cv'),'@cf/qwen/qwen3.8-27b')
        for task in ('jd','interview','verifier'):
            self.assertEqual(settings.provider_for_task(task),'cloudflare')
            self.assertEqual(settings.model_for_task(task),'@cf/openai/gpt-oss-20b')
        self.assertEqual(settings.provider_for_task('update'),'groq')
        self.assertEqual(settings.model_for_task('update'),'openai/gpt-oss-20b')
        for task in ('writer','refine'):
            self.assertEqual(settings.provider_for_task(task),'ollama')
            self.assertEqual(settings.model_for_task(task),'kltn-writer-8b-unsloth:latest')
        self.assertNotIn('test-cloudflare-secret',repr(settings))
        self.assertNotIn('test-groq-secret',repr(settings))

    def test_env_loads_credentials_and_per_task_model(self):
        with patch.dict(os.environ,{'CLOUDFLARE_ACCOUNT_ID':'b'*32,'CLOUDFLARE_API_TOKEN':'test-secret',
                'CLOUDFLARE_MODEL':'@cf/openai/gpt-oss-20b','CLOUDFLARE_CV_MODEL':'@cf/qwen/qwen3.8-27b',
                'CLOUDFLARE_TASKS':'jd, interview,jd,cv,verifier','CLOUDFLARE_MAX_OUTPUT_TOKENS':'1536'},clear=True):
            settings=Settings.from_environment()
        self.assertEqual(settings.cloudflare_tasks,('jd','interview','cv','verifier'))
        self.assertEqual(settings.cloudflare_max_output_tokens,1536)
        self.assertEqual(settings.model_for_task('cv'),'@cf/qwen/qwen3.8-27b')
        self.assertNotIn('test-secret',repr(settings))

    def test_invalid_or_ambiguous_config_is_rejected_without_credentials_in_error(self):
        base={'CLOUDFLARE_ACCOUNT_ID':'a'*32,'CLOUDFLARE_API_TOKEN':'secret-not-for-output','CLOUDFLARE_TASKS':'jd'}
        for change in [
            {'CLOUDFLARE_ACCOUNT_ID':''},{'CLOUDFLARE_API_TOKEN':''},
            {'CLOUDFLARE_ACCOUNT_ID':'../bad-path'},{'CLOUDFLARE_TASKS':'typo'},
            {'CLOUDFLARE_TASKS':'writer'},{'CLOUDFLARE_TASKS':'refine'},
            {'GROQ_TASKS':'jd','GROQ_API_KEY':'secret'},
            {'CLOUDFLARE_TIMEOUT_SECONDS':'0'},{'CLOUDFLARE_MAX_OUTPUT_TOKENS':'0'},
            {'CLOUDFLARE_MAX_OUTPUT_TOKENS':'9000'},{'CLOUDFLARE_MODEL':'https://invalid/model'},
        ]:
            with self.subTest(change=change),patch.dict(os.environ,{**base,**change},clear=True):
                with self.assertRaises(ValueError) as error:Settings.from_environment()
                self.assertNotIn('secret-not-for-output',str(error.exception))

    def test_blank_tasks_are_inactive_and_blank_cv_override_inherits_default(self):
        with patch.dict(os.environ,{'CLOUDFLARE_TASKS':''},clear=True):settings=Settings.from_environment()
        self.assertEqual(settings.provider_for_task('jd'),'ollama')
        self.assertEqual(replace(self.config(),cloudflare_cv_model=None).model_for_task('cv'),'@cf/openai/gpt-oss-20b')

    def test_wire_payload_is_account_scoped_bounded_and_not_ollama(self):
        seen=[]
        def respond(request):
            seen.append(request)
            return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':'{"value":"ok"}'}}]})
        with httpx.Client(transport=httpx.MockTransport(respond)) as transport, \
             patch.object(client,'_client',transport),patch.object(client,'settings',self.config()):
            self.assertEqual(client.request_structured([{'role':'user','content':'test'}],Output,task='jd').value,'ok')
            self.assertEqual(client.request_structured([],Output,task='cv',max_output_tokens=128).value,'ok')
        self.assertEqual(len(seen),2)
        self.assertEqual(str(seen[0].url),'https://api.cloudflare.com/client/v4/accounts/'+'a'*32+'/ai/v1/chat/completions')
        for request,model,limit in zip(seen,['@cf/openai/gpt-oss-20b','@cf/qwen/qwen3.8-27b'],[2048,128]):
            body=json.loads(request.content)
            self.assertEqual(body['model'],model)
            self.assertEqual(body['max_completion_tokens'],limit)
            self.assertEqual(body['reasoning_effort'],'low')
            self.assertFalse(body['store']);self.assertFalse(body['stream'])
            self.assertNotIn('options',body);self.assertNotIn('think',body)
            self.assertEqual(body['response_format']['json_schema'],Output.model_json_schema())
            self.assertIn('JSON Schema',body['messages'][0]['content'])
            self.assertIn('"value"',body['messages'][0]['content'])
            self.assertEqual(request.headers['authorization'],'Bearer test-cloudflare-secret')

    def test_errors_have_one_request_no_retry_or_other_provider_fallback(self):
        for status in [400,401,403,410,429,503]:
            seen=[]
            def respond(request):
                seen.append(request)
                return httpx.Response(status,json={'errors':[{'message':'private source text test-cloudflare-secret'}]})
            with self.subTest(status=status),httpx.Client(transport=httpx.MockTransport(respond)) as transport, \
                 patch.object(client,'_client',transport),patch.object(client,'settings',self.config()):
                with self.assertRaises(client.OllamaError) as error:client.request_structured([],Output,task='jd')
                self.assertEqual(len(seen),1)
                self.assertEqual(seen[0].url.host,'api.cloudflare.com')
                self.assertNotIn('private source',str(error.exception))
                self.assertNotIn('test-cloudflare-secret',str(error.exception))
                self.assertIn('Cloudflare',str(error.exception))

    def test_invalid_and_partial_outputs_are_never_accepted(self):
        for body in [
            {'choices':[{'finish_reason':'length','message':{'content':'{"value":"partial"}'}}]},
            {'choices':[{'finish_reason':'stop','message':{'content':'{"other":1}'}}]},
            {'choices':[{'finish_reason':'stop','message':{'content':'bad JSON'}}]},
            {'choices':[{'finish_reason':'stop','message':{'content':None,'refusal':'no'}}]},
            {'success':False,'errors':[{'message':'private text'}]},
        ]:
            with self.subTest(body=body),httpx.Client(transport=httpx.MockTransport(lambda request:httpx.Response(200,json=body))) as transport, \
                 patch.object(client,'_client',transport),patch.object(client,'settings',self.config()):
                with self.assertRaises(client.OllamaError):client.request_structured([],Output,task='jd')

    def test_wrapped_result_and_structured_content_are_supported(self):
        body={'success':True,'result':{'choices':[{'finish_reason':'stop','message':{'content':{'value':'ok'}}}]}}
        with httpx.Client(transport=httpx.MockTransport(lambda request:httpx.Response(200,json=body))) as transport, \
             patch.object(client,'_client',transport),patch.object(client,'settings',self.config()):
            self.assertEqual(client.request_structured([],Output,task='jd').value,'ok')

    def test_schema_instruction_does_not_mutate_conversation(self):
        messages=[{'role':'system','content':'Original instruction.'},{'role':'user','content':'Source.'}]
        body={'choices':[{'finish_reason':'stop','message':{'content':'{"value":"ok"}'}}]}
        with httpx.Client(transport=httpx.MockTransport(lambda request:httpx.Response(200,json=body))) as transport, \
             patch.object(client,'_client',transport),patch.object(client,'settings',self.config()):
            client.request_structured(messages,Output,task='interview')
        self.assertEqual(messages,[{'role':'system','content':'Original instruction.'},{'role':'user','content':'Source.'}])

    def test_flattened_interview_result_is_not_accepted_as_nested_schema(self):
        from backend.app.schemas.interview import InitialTurn
        flat={'kind':'technical','question':'Bạn kiểm thử API như thế nào?','evidence_refs':['cv:0']}
        body={'choices':[{'finish_reason':'stop','message':{'content':json.dumps(flat)}}]}
        with httpx.Client(transport=httpx.MockTransport(lambda request:httpx.Response(200,json=body))) as transport, \
             patch.object(client,'_client',transport),patch.object(client,'settings',self.config()):
            with self.assertRaises(client.OllamaSchemaError):client.request_structured([],InitialTurn,task='interview')

    def test_missing_credentials_and_expired_deadline_do_not_send(self):
        for settings in [replace(self.config(),cloudflare_api_token=None),replace(self.config(),cloudflare_account_id='bad')]:
            with patch.object(client,'settings',settings),patch.object(client._client,'post') as post:
                with self.assertRaises(client.OllamaConnectionError):client.request_structured([],Output,task='jd')
                post.assert_not_called()
        with patch.object(client,'settings',self.config()),patch.object(client._client,'post') as post,client.llm_deadline(-1):
            with self.assertRaises(client.OllamaTimeoutError):client.request_structured([],Output,task='jd')
            post.assert_not_called()

    def test_cache_identity_changes_when_provider_or_model_changes(self):
        cloud=self.config()
        local=replace(cloud,cloudflare_tasks=(),jd_model=cloud.cloudflare_model)
        self.assertNotEqual(cloud.identity_for_task('jd'),local.identity_for_task('jd'))
        self.assertNotEqual(cloud.identity_for_task('jd'),replace(cloud,cloudflare_model='@cf/qwen/qwen3.8-27b').identity_for_task('jd'))

    def test_probe_uses_one_call_per_task_and_validates_real_schemas(self):
        from scripts import check_cloudflare as probe
        samples={
            'jd':{'items':[{'name':'Python','line':1}]},
            'interview':{'question':{'kind':'technical','text':'Bạn kiểm thử API Python như thế nào?','evidence_refs':['cv:0']}},
            'cv':{'selected_refs':['/project/0/description/0'],'review':{'items':[],'warnings':[]}},
            'verifier':{'source_ref':'s0','rewrite_ref':'t0','same_action':True,'same_object':True,'same_actor_and_scope':True,'same_methods':True,'same_quantity_and_result':True,'same_conditions':True,'no_added_claims':True},
        }
        for task,payload in samples.items():
            _,schema=probe.sample(task)
            with self.subTest(task=task),patch.object(probe,'settings',self.config()),patch.object(probe,'request_structured',return_value=schema.model_validate(payload)) as call:
                result=probe.check(task)
                self.assertTrue(result['validated'])
                self.assertEqual(result['requests'],1)
                call.assert_called_once()
                self.assertEqual(call.call_args.kwargs['task'],task)

    def test_probe_never_retries_failures_or_calls_another_provider(self):
        from scripts import check_cloudflare as probe
        with patch.object(probe,'settings',self.config()),patch.object(probe,'request_structured',side_effect=client.OllamaResponseError('quota')) as call:
            with self.assertRaises(client.OllamaResponseError):probe.check('jd')
            call.assert_called_once()
        with patch.object(probe,'settings',Settings()),patch.object(probe,'request_structured') as call:
            with self.assertRaises(ValueError):probe.check('jd')
            call.assert_not_called()
