import json
import unittest
from unittest.mock import patch
from ai.agents.jd_extraction import CompactJD,SourceItem,expand,source_chunks,extract_compact
from ai.agents.cv_grounding import grounded_rewrite,job_brief
from ai.llm.ollama_client import OllamaSchemaError,OllamaResponseError,request_structured

class AIGroundingTests(unittest.TestCase):
    def test_invalid_citation_and_unsupported_skill_never_expand(self):
        for item in (SourceItem(name='Python',line=9),SourceItem(name='Kubernetes',line=1)):
            with self.assertRaises(OllamaSchemaError):expand(CompactJD(items=[item]),{1:'Python is required.'})

    def test_chunks_keep_preferred_scope_and_do_not_score_benefits(self):
        raw='Requirements\nPython required.\nPreferred skills\nDocker preferred.\nBenefits\nFree Java training.\nRequirements\nSQL required.'
        lines,chunks=source_chunks(raw,35)
        self.assertNotIn('Free Java training.', '\n'.join(v for c in chunks for v in c.values()))
        docker=next(c for c in chunks if 'Docker preferred.' in c.values())
        self.assertIn('Preferred skills',docker.values())
        self.assertEqual(expand(CompactJD(items=[SourceItem(name='SQL',line=8)]),lines).required_skills[0].evidence,'SQL required.')

    def test_partial_cache_reuses_completed_source_part_after_failure(self):
        raw='Requirements\nPython required.\nPreferred skills\nDocker preferred.'
        saved={}
        def chunker(_):return {},[{1:'Requirements',2:'Python required.'},{3:'Preferred skills',4:'Docker preferred.'}]
        first=CompactJD(items=[SourceItem(name='Python',line=2)])
        second=CompactJD(items=[SourceItem(name='Docker',line=4)])
        with patch('ai.agents.jd_extraction.source_chunks',side_effect=chunker),patch('ai.agents.jd_extraction.database.enabled',return_value=True),patch('ai.agents.jd_extraction.database.get_record',side_effect=lambda kind,key:saved.get(key)),patch('ai.agents.jd_extraction.database.put_record',side_effect=lambda kind,key,data,**_:saved.setdefault(key,data)):
            with patch('ai.agents.jd_agent.request_structured',side_effect=[first,RuntimeError('temporary failure')]) as model:
                with self.assertRaises(RuntimeError):extract_compact(raw,model)
            with patch('ai.agents.jd_agent.request_structured',return_value=second) as model:
                result=extract_compact(raw,model)
                self.assertEqual(model.call_count,1)
                self.assertEqual([s.name for s in result.required_skills],['Python'])
                self.assertEqual([s.name for s in result.preferred_skills],['Docker'])

    def test_rewrite_keeps_denial_entities_scope_and_numbers(self):
        cases=[('Built Python APIs.','Built Python APIs with Kubernetes.'),('Supported a team.','Led a team.'),('No experience with Docker.','Experience with Docker.'),('Built 2 APIs.','Built 20 APIs.'),('Built a Python API.','Amazon built a Python API.')]
        for original,proposed in cases:self.assertFalse(grounded_rewrite(original,proposed))
        self.assertTrue(grounded_rewrite('Built a Python API with PostgreSQL.','Developed a Python API with Postgres.'))

    def test_cv_prompt_excludes_raw_jd_and_runtime_metadata(self):
        brief=job_brief({'job_description_raw':'PRIVATE RAW JD','required_skills':[{'id':'r1','name':'Python','requirement_type':'required','evidence':'Python required.'}],'requirement_groups':[{'id':'g1','operator':'any','members':['SQL','MongoDB'],'evidence':'SQL or MongoDB','requirement_type':'required'}]})
        self.assertNotIn('PRIVATE RAW JD',json.dumps(brief))
        self.assertNotIn('r1',json.dumps(brief))
        self.assertEqual(brief['groups'][0]['operator'],'any')

    def test_token_limit_is_rejected_even_if_json_looks_valid(self):
        class Response:
            def raise_for_status(self):pass
            def json(self):return {'message':{'content':'{}'},'done':True,'done_reason':'length'}
        with patch('ai.llm.ollama_client.httpx.post',return_value=Response()):
            with self.assertRaises(OllamaResponseError):request_structured([],CompactJD,task='jd')

    def test_preferred_clause_does_not_relabel_mandatory_experience(self):
        from ai.agents.jd_agent import analyze_job_description
        wire=CompactJD(items=[SourceItem(name='Python',line=2)])
        with patch('ai.agents.jd_agent.request_structured',return_value=wire):
            result,_=analyze_job_description('Requirements\nPython required.\nCó từ 1–3 năm kinh nghiệm Backend, ưu tiên đã triển khai sản phẩm thực tế.')
        years=next(r for r in result.experience_requirements if r.minimum_years==1)
        self.assertEqual(years.requirement_type,'required')
        self.assertNotIn('ưu tiên',years.evidence)
