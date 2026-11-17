"""Local review overlays. Original packets, identities and split are immutable."""
import copy
import fcntl
import hashlib
import json
import os
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from ai.training.review_pack import assert_isolated,load_verified
from ai.training.export_reviewed import approved_packet, validate_content

ROOT=Path(__file__).resolve().parents[2]
DEFAULT_PACK=ROOT/'ai/data/processed/topcv-tech-review-v1'
DEFAULT_REVIEWS=Path(os.environ.get('KLTN_REVIEW_DIR',str(ROOT/'ai/data/reviews/topcv-tech-review-v1')))


def atomic(path,value):
    temp=path.with_name(path.name+'.'+uuid4().hex+'.tmp')
    try:
        with temp.open('x',encoding='utf-8') as f:
            json.dump(value,f,ensure_ascii=False,indent=2);f.flush();os.fsync(f.fileno())
        os.replace(temp,path)
    finally:temp.unlink(missing_ok=True)


class ReviewStore:
    def __init__(self,pack=DEFAULT_PACK,reviews=DEFAULT_REVIEWS):
        self.root=Path(reviews);self.root.mkdir(parents=True,exist_ok=True)
        manifest,self.packets=load_verified(pack);self.manifest=manifest;checksums=manifest['checksums']
        with self.lock():
            path=self.root/'cohort.json'
            if path.exists():self.cohort=json.loads(path.read_text())
            else:
                train=[r for r in self.packets.values() if r['split']=='train'];groups=list(dict.fromkeys(r['jd_group'] for r in train));chosen=[]
                for i,g in enumerate(groups[:10]):
                    candidates=[r for r in train if r['jd_group']==g];chosen.append(candidates[i%len(candidates)]['pair_id'])
                if manifest.get('review_cohort') is not None:chosen=manifest['review_cohort']
                self.cohort={'version':1,'pair_ids':chosen,'checksums':checksums,'split_policy':manifest['split_policy']};atomic(path,self.cohort)
            if self.cohort['checksums']!=checksums or len(self.cohort['pair_ids'])!=len(manifest.get('review_cohort',list(range(10)))) or len(set(self.cohort['pair_ids']))!=len(self.cohort['pair_ids']) or any(k not in self.packets or (not manifest.get('task') and self.packets[k]['split']!='train') for k in self.cohort['pair_ids']):raise ValueError('Cohort không khớp nguồn hoặc không đủ 10 mẫu train')

    @contextmanager
    def lock(self):
        with (self.root/'.lock').open('a') as f:
            fcntl.flock(f,fcntl.LOCK_EX)
            try:yield
            finally:fcntl.flock(f,fcntl.LOCK_UN)

    def all_review_keys(self):
        initial=self.cohort['pair_ids']
        if not self.manifest.get('task'):return list(initial)
        return initial+[p['pair_id'] for p in sorted(self.packets.values(),key=lambda p:(p['split']!='train',p['pair_id'])) if p['pair_id'] not in initial]

    def path(self,key):
        if key not in self.all_review_keys():raise ValueError('Mẫu không thuộc cohort')
        return self.root/(key+'.json')

    def progress(self,key):
        path=self.path(key)
        if path.exists():return json.loads(path.read_text())
        initial={'version':0,'annotation':{'status':'draft','reviewer_ids':[],'requirements':[],'requirement_groups':[],'source_usage_confirmed':False,'cv_usage_confirmed':False,'cv_plan':{'selected_refs':[],'review':{'items':[],'warnings':[]}}},'history':[]}
        source=self.packets[key].get('annotation',{})
        for field in ('requirements','requirement_groups','cv_plan','conversion_review_confirmed','matching_overall_label','matching_rationale','pair_decisions','partial_plan_review_confirmed'):
            if source.get(field) is not None:initial['annotation'][field]=copy.deepcopy(source[field])
        return initial

    def packet(self,key):
        row=copy.deepcopy(self.packets[key]);progress=self.progress(key);row['annotation']=progress['annotation']
        if progress.get('model_annotations') is not None:row['model_annotations']=progress['model_annotations']
        return row

    def save(self,key,version,annotation,action='draft',reviewer='',confirmed=False,*,origin='human',model_metadata=None):
        with self.lock():
            old=self.progress(key)
            if old['version']!=version:raise ValueError('Tiến độ đã thay đổi. Tải lại mẫu trước khi lưu (không ghi đè).')
            allowed={'requirements','requirement_groups','cv_plan','source_usage_confirmed','cv_usage_confirmed','conversion_review_confirmed','matching_overall_label','matching_rationale','pair_decisions','partial_plan_review_confirmed'}
            if set(annotation)-allowed:raise ValueError('Không được sửa trạng thái duyệt hoặc nguồn qua bản nháp')
            data=copy.deepcopy(annotation)
            for flag in ('source_usage_confirmed','cv_usage_confirmed'):
                if type(data.get(flag,False)) is not bool:raise ValueError('Xác nhận quyền phải là boolean')
            if self.packets[key].get('cleaning'):
                from ai.training.tailor_clean import validate_decision_shape
                validate_decision_shape(self.packets[key],data)
            data.update(status='skipped' if action=='skip' else 'draft',reviewer_ids=[])
            packet=copy.deepcopy(self.packets[key]);packet['annotation']=data
            if action=='approve':
                if not confirmed or not reviewer.strip():raise ValueError('Cần tên reviewer và xác nhận đã kiểm tra nội dung')
                validate_content(packet);data.update(status='approved',reviewer_ids=[reviewer.strip()])
            now=datetime.now(timezone.utc).isoformat()
            progress={'version':version+1,'annotation':data,'model_annotations':model_metadata if model_metadata is not None else old.get('model_annotations'),'updated_at':now,'history':old['history']+[{'action':action,'origin':origin,'at':now,'reviewer':reviewer.strip(),'source_usage_confirmed':data.get('source_usage_confirmed',False),'cv_usage_confirmed':data.get('cv_usage_confirmed',False)}]}
            atomic(self.path(key),progress);return progress

    def validation(self,key):
        packet=self.packet(key);content=[];export=[]
        try:validate_content(packet)
        except (ValueError,KeyError,TypeError) as e:content.append(str(e))
        try:approved_packet(packet)
        except (ValueError,KeyError,TypeError) as e:export.append(str(e))
        return {'pair_id':key,'content_errors':content,'export_errors':export,'exportable':not export}

    def summary(self,keys=None):
        return [{'pair_id':key,'title':self.packets[key]['job']['title'],'variant':self.packets[key]['cv_variant'],'status':self.progress(key)['annotation']['status'],'version':self.progress(key)['version'],**self.validation(key)} for key in (self.cohort['pair_ids'] if keys is None else keys)]

    def export(self,keys):
        with self.lock():
            if not keys or len(set(keys))!=len(keys):raise ValueError('Chọn các mẫu đã duyệt để export')
            for key in keys:self.path(key)
            packets=[self.packet(key) for key in keys];rows=[approved_packet(p) for p in packets];assert_isolated(packets)
            ident=uuid4().hex;folder=self.root/'exports'/ident;folder.mkdir(parents=True)
            content=''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows)
            (folder/'reviewed.jsonl').write_text(content)
            atomic(folder/'annotations.json',packets)
            atomic(folder/'manifest.json',{'pair_ids':keys,'versions':{k:self.progress(k)['version'] for k in keys},'checksums':self.cohort['checksums'],'sha256':hashlib.sha256(content.encode()).hexdigest(),'splits':{s:sum(r['split']==s for r in rows) for s in ('train','validation','test')},'training_started':False})
            return {'export_id':ident,'count':len(rows),'download_url':f'/api/data-review/exports/{ident}'}
