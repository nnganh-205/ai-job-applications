"""Safety checks use a disposable fixture pack, never real reviewer approval."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from fastapi import FastAPI
from ai.training.review_pack import build
from ai.training.review_store import ReviewStore
from ai.training.export_reviewed import approved_example
from backend.tests.test_review_pack import jobs
from backend.app.api.data_review import router

class DataReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.pack=self.root/'pack';self.pack.mkdir()
        rows,manifest=build(jobs());checks={}
        for split in ('train','validation','test'):
            data=''.join(json.dumps(r)+'\n' for r in rows if r['split']==split).encode();name=split+'.jsonl'
            (self.pack/name).write_bytes(data);checks[name]=hashlib.sha256(data).hexdigest()
        manifest['checksums']=checks;(self.pack/'manifest.json').write_text(json.dumps(manifest))
        self.store=ReviewStore(self.pack,self.root/'reviews');self.key=self.store.cohort['pair_ids'][0]
        self.before={p.name:p.read_bytes() for p in self.pack.iterdir()}

    def annotation(self):
        p=self.store.packets[self.key];ref=next(iter(p['catalog']))
        return {'requirements':[{'name':'Fixture skill','field':'unspecified_skills','requirement_type':'unspecified','status':'unknown','job_evidence':p['job']['description'],'evidence_refs':[]}],'requirement_groups':[],'source_usage_confirmed':False,'cv_usage_confirmed':False,'cv_plan':{'selected_refs':[ref],'review':{'items':[],'warnings':[]}}}

    def test_ten_train_frozen_and_drafts_do_not_export(self):
        self.assertEqual(len(self.store.cohort['pair_ids']),10)
        self.assertTrue(all(self.store.packets[k]['split']=='train' for k in self.store.cohort['pair_ids']))
        self.store.save(self.key,0,self.annotation())
        with self.assertRaisesRegex(ValueError,'Human approval'):self.store.export([self.key])
        self.assertFalse((self.store.root/'exports').exists())
        self.assertEqual(self.before,{p.name:p.read_bytes() for p in self.pack.iterdir()})

    def test_human_content_approval_does_not_grant_source_rights(self):
        self.store.save(self.key,0,self.annotation(),'approve','fixture reviewer',True)
        self.assertEqual(self.store.progress(self.key)['annotation']['status'],'approved')
        self.assertEqual(self.store.validation(self.key)['content_errors'],[])
        self.assertFalse(self.store.validation(self.key)['exportable'])
        with self.assertRaisesRegex(ValueError,'Source usage'):self.store.export([self.key])

    def test_approved_subset_exports_without_changing_split(self):
        a=self.annotation();a['source_usage_confirmed']=True # fixture permission only
        self.store.save(self.key,0,a,'approve','fixture reviewer',True)
        result=self.store.export([self.key]);folder=self.store.root/'exports'/result['export_id']
        rows=[json.loads(x) for x in (folder/'reviewed.jsonl').read_text().splitlines()]
        self.assertEqual(len(rows),1);self.assertEqual(rows[0]['split'],'train')
        self.assertEqual(rows[0]['cv_identity'],self.store.packets[self.key]['cv_identity'])
        self.assertEqual(self.before,{p.name:p.read_bytes() for p in self.pack.iterdir()})
        self.assertEqual(len(json.loads((folder/'annotations.json').read_text())[0]['annotation']['requirements']),1)

    def test_cas_and_explicit_confirmation_and_edits_reset_approval(self):
        a=self.annotation()
        with self.assertRaises(ValueError):self.store.save(self.key,0,a,'approve','reviewer',False)
        self.store.save(self.key,0,a,'approve','reviewer',True)
        with self.assertRaisesRegex(ValueError,'Tiến độ'):self.store.save(self.key,0,a)
        self.store.save(self.key,1,a)
        self.assertEqual(self.store.progress(self.key)['annotation']['status'],'draft')
        self.assertEqual(self.store.progress(self.key)['annotation']['reviewer_ids'],[])

    def test_source_tampering_and_ungrounded_labels_rejected(self):
        a=self.annotation();a['requirements'][0]['job_evidence']='invented quote'
        with self.assertRaisesRegex(ValueError,'verbatim'):self.store.save(self.key,0,a,'approve','reviewer',True)
        a=self.annotation();a['requirements'][0].update(status='met',evidence_refs=['/nonexistent'])
        with self.assertRaisesRegex(ValueError,'visible'):self.store.save(self.key,0,a,'approve','reviewer',True)
        p=self.pack/'train.jsonl';p.write_text(p.read_text()+'\n')
        with self.assertRaisesRegex(ValueError,'checksum'):ReviewStore(self.pack,self.store.root)

    def test_rewrite_reason_and_factual_guard(self):
        a=self.annotation();ref=a['cv_plan']['selected_refs'][0]
        a['cv_plan']['review']['items']=[{'source_ref':ref,'original_text':self.store.packets[self.key]['catalog'][ref],'proposed_text':'Led Kubernetes production team with 99 engineers.','reason':'invented','severity':'info'}]
        with self.assertRaisesRegex(ValueError,'dữ kiện'):self.store.save(self.key,0,a,'approve','reviewer',True)

    def test_api_mock_ai_prelabel_is_draft_and_never_grants_rights(self):
        from backend.app.schemas.job import JobRequirements
        from backend.app.schemas.cv import CVDocument,CVReview
        app=FastAPI();app.include_router(router);client=TestClient(app)
        packet=self.store.packets[self.key]
        req=JobRequirements(job_description_raw=packet['job']['description'],unspecified_skills=[{'name':'Python','requirement_type':'unspecified','evidence':packet['job']['description']}])
        with patch('backend.app.api.data_review.ReviewStore',return_value=self.store),patch('ai.agents.jd_agent.analyze_job_description',return_value=(req,[])),patch('ai.agents.cv_agent.plan_cv',return_value=(CVDocument.model_validate(packet['cv']),CVReview(items=[],warnings=[]))):
            response=client.post('/api/data-review/samples/'+self.key+'/prelabel',json={'version':0})
            self.assertEqual(response.status_code,200,response.text)
            a=response.json()['progress']['annotation'];self.assertEqual(a['status'],'draft');self.assertFalse(a['source_usage_confirmed']);self.assertEqual(a['reviewer_ids'],[])
            self.assertEqual(a['requirements'][0]['status'],'unknown')
