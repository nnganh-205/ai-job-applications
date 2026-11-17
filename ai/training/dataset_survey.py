"""Revision-pinned, stratified private surveys; never log CV text or label approval."""
import argparse
from collections import Counter, defaultdict
import hashlib
import io
import json
from pathlib import Path
import time
from urllib.parse import quote

from ai.training.review_store import atomic

REPOS={'tailoring':'abhaykanjoor/iteratecv-resume-tailoring','matching_original':'cnamuangtoun/resume-job-description-fit','matching_merged':'med2425/resume-job-fit-merged-v1'}
VERSION='hf-survey-v1'
SEED=42


def digest(value):
    if not isinstance(value,bytes):value=json.dumps(value,ensure_ascii=False,sort_keys=True).encode()
    return hashlib.sha256(value).hexdigest()


def get(url,*,params=None,revision=None):
    import requests
    for attempt in range(4):
        try:response=requests.get(url,params=params,timeout=60)
        except requests.RequestException:
            if attempt==3:raise
            time.sleep(2**attempt);continue
        if response.status_code in (429,500,502,503,504) and attempt<3:
            time.sleep(min(8,2**attempt));continue
        response.raise_for_status()
        if revision and response.headers.get('x-revision')!=revision:raise ValueError('Viewer revision mismatch; sample refused')
        return response


class RangeFile(io.RawIOBase):
    """Read only Parquet footer and selected metadata columns, not resume shards."""
    def __init__(self,url,size):self.url=url;self.size=size;self.pos=0;self.ranges=[]
    def seekable(self):return True
    def readable(self):return True
    def tell(self):return self.pos
    def seek(self,offset,whence=0):
        self.pos=offset if whence==0 else self.pos+offset if whence==1 else self.size+offset
        return self.pos
    def read(self,n=-1):
        import requests
        n=min(n if n>=0 else self.size-self.pos,self.size-self.pos)
        if n<=0:return b''
        start=self.pos
        for attempt in range(4):
            try:response=requests.get(self.url,headers={'Range':f'bytes={start}-{start+n-1}'},timeout=60,stream=True)
            except requests.RequestException:
                if attempt==3:raise
                time.sleep(2**attempt);continue
            if response.status_code in (429,500,502,503,504) and attempt<3:
                response.close();time.sleep(2**attempt);continue
            if response.status_code!=206:
                response.close();raise ValueError('Range unsupported; refusing full shard download')
            try:content=response.content
            except requests.RequestException:
                response.close()
                if attempt==3:raise
                time.sleep(2**attempt);continue
            if len(content)!=n or response.headers.get('Content-Range','').split('/')[0]!=f'bytes {start}-{start+n-1}':raise ValueError('Range response mismatch')
            self.pos+=n;self.ranges.append({'start':start,'length':n,'sha256':digest(content)})
            return content
        raise ValueError('Metadata download failed')


def balanced(rows,count,fields,diversity=None):
    """Deterministic equal stratum coverage, then domain diversity within strata."""
    groups=defaultdict(list)
    for row in rows:groups[tuple(str(row.get(k,'')) for k in fields)].append(row)
    for key,values in groups.items():
        if diversity:
            sub=defaultdict(list)
            for row in values:sub[tuple(str(row.get(k,'')) for k in diversity)].append(row)
            for bucket in sub.values():bucket.sort(key=lambda r:digest([SEED,r]))
            ordered=[]
            while any(sub.values()):
                for category in sorted(sub):
                    if sub[category]:ordered.append(sub[category].pop(0))
            groups[key]=ordered
        else:values.sort(key=lambda r:digest([SEED,r]))
    selected=[]
    while len(selected)<count and any(groups.values()):
        for key in sorted(groups,key=lambda k:digest([SEED,k])):
            if groups[key] and len(selected)<count:selected.append(groups[key].pop(0))
    return selected


def parse_iterate(row):
    raw=row['input'];start=raw.index('{');cv,end=json.JSONDecoder().raw_decode(raw[start:])
    remainder=raw[start+end:];marker='JOB DESCRIPTION:'
    if marker not in remainder:raise ValueError('Missing JD separator')
    jd=remainder.split(marker,1)[1].strip()
    output=json.loads(row['output'])
    if not isinstance(cv,dict) or not isinstance(output,dict) or not jd:raise ValueError('Unexpected tailoring structure')
    return cv,jd,output


def metadata(repo,folder):
    old=folder/'repo.json'
    previous=json.loads(old.read_text()) if old.exists() else None
    endpoint='https://huggingface.co/api/datasets/'+repo
    if previous:
        if previous.get('id')!=repo:raise ValueError('Cached dataset identity mismatch')
        endpoint+='/revision/'+previous['sha']
    info=get(endpoint).json();revision=info['sha']
    if info.get('gated'):raise ValueError('Gated source; no credentials requested')
    if previous and previous['sha']!=revision:raise ValueError('Pinned source revision mismatch')
    atomic(old,info)
    files={f['rfilename'] for f in info['siblings']}
    if 'README.md' in files:
        card=get(f'https://huggingface.co/datasets/{repo}/resolve/{revision}/README.md').text
        (folder/'README.md').write_text(card)
    else:card=None
    return info,card


def survey_tailoring(root,legacy,count):
    folder=root/'abhaykanjoor';folder.mkdir(exist_ok=True);info,card=metadata(REPOS['tailoring'],folder)
    manifest=json.loads((legacy/'manifest.json').read_text())
    if manifest.get('dataset')!=REPOS['tailoring'] or manifest.get('cache_revision')!=info['sha']:raise ValueError('Legacy source/revision cannot be verified; refusing duplicate download')
    pool=[];inputs={};source_checks={}
    for split in ('train','validation','test'):
        path=legacy/(split+'.json');source_checks[str(path)]=digest(path.read_bytes())
        if source_checks[str(path)]!=manifest['splits'][split]['sha256']:raise ValueError('Legacy checksum mismatch')
        rows=json.loads(path.read_text())
        for i,row in enumerate(rows):
            cv,jd,target=parse_iterate(row);inputs[split,i]=row
            length=sum(len(json.dumps(entry)) for entry in cv.get('experience',[]))
            pool.append({'split':split,'index':i,'length_bin':0 if length<1500 else 1 if length<4000 else 2,'entries_bin':min(3,len(cv.get('experience',[])))})
    chosen=[]
    for split,quota in [('train',count*8//10),('validation',count//10),('test',count-count*8//10-count//10)]:
        chosen+=balanced([r for r in pool if r['split']==split],quota,['length_bin','entries_bin'])
    rows=[{'source':REPOS['tailoring'],'revision':info['sha'],'source_split':r['split'],'source_index':r['index'],'stratum':r,'raw':inputs[r['split'],r['index']]} for r in chosen]
    write_rows(folder/'samples.jsonl',rows)
    result={'repo':info['id'],'revision':info['sha'],'license_declared':(info.get('cardData') or {}).get('license'),'license_scope_verified':False,'dataset_card_sha256':digest(card.encode()) if card else None,'repo_metadata_sha256':digest((folder/'repo.json').read_bytes()),'label_origin':'GPT-4o mini parsed source CV and generated tailored output; card declaration','human_approved':False,'pool_rows':len(pool),'selected':len(rows),'downloaded_rows':0,'reused_local_rows':len(rows),'source_checksums':source_checks,'sampling':'40/5/5 published split quotas (for 50); balanced CV length and experience-entry count; seed42 hash order','samples_sha256':digest((folder/'samples.jsonl').read_bytes())}
    atomic(folder/'manifest.json',result);return result


def write_rows(path,rows):
    content=''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows)
    if path.exists():
        if path.read_text()!=content:raise ValueError('Existing sample differs; use a new survey directory')
    else:
        with path.open('x') as f:f.write(content)


def survey_matching(root,name,count):
    import pyarrow.parquet as pq
    repo=REPOS[name];folder=root/repo.split('/')[0];folder.mkdir(exist_ok=True)
    info,card=metadata(repo,folder);revision=info['sha'];meta_path=folder/'sampling-index.json'
    if meta_path.exists():
        saved=json.loads(meta_path.read_text())
        if saved['revision']!=revision:raise ValueError('Metadata revision mismatch')
        index=saved['rows'];files=saved['files']
    else:
        viewer=get('https://datasets-server.huggingface.co/parquet',params={'dataset':repo},revision=revision).json()
        if viewer.get('pending') or viewer.get('failed') or viewer.get('partial'):raise ValueError('Viewer not complete')
        converted=None
        if name=='matching_original':converted=get('https://huggingface.co/api/datasets/'+repo+'/revision/refs%2Fconvert%2Fparquet').json()['sha']
        index=[];files=[];offsets=Counter()
        for file in viewer['parquet_files']:
            if file['config']!='default':continue
            url=file['url']
            # Pin a mutable auto-converted URL to its own exact commit.
            if converted:url=url.replace('refs%2Fconvert%2Fparquet',converted)
            elif '/resolve/'+revision+'/' not in url:
                url=url.replace('/resolve/refs%2Fconvert%2Fparquet/',f'/resolve/{revision}/data/')
                # Original repo paths are known, never infer an unlisted shard.
                original=[f['rfilename'] for f in info['siblings'] if f['rfilename'].endswith('.parquet') and '/'+file['split']+'-' in f['rfilename']]
                original.sort();ordinal=sum(f['split']==file['split'] for f in files)
                url=f'https://huggingface.co/datasets/{repo}/resolve/{revision}/{original[ordinal]}'
            reader=RangeFile(url,file['size']);parquet=pq.ParquetFile(reader)
            columns=[c for c in ('label','source','resume_domain','jd_domain') if c in parquet.schema_arrow.names]
            values=parquet.read(columns=columns).to_pylist()
            for i,row in enumerate(values):index.append({**row,'split':file['split'],'index':offsets[file['split']]+i})
            offsets[file['split']]+=len(values)
            files.append({'split':file['split'],'url':url,'size':file['size'],'metadata_rows':len(values),'metadata_columns':columns,'ranges':reader.ranges,'converted_revision':converted})
        atomic(meta_path,{'revision':revision,'rows':index,'files':files})
    selected=[]
    for split,quota in [('train',count*8//10),('test',count-count*8//10)]:
        selected+=balanced([r for r in index if r['split']==split],quota,['label'],['source','resume_domain','jd_domain'])
    if len(selected)!=count:raise ValueError('Insufficient population for requested strata')
    checkpoint=folder/'checkpoints';checkpoint.mkdir(exist_ok=True);rows=[]
    for selected_row in selected:
        split=selected_row['split'];offset=selected_row['index'];path=checkpoint/f'{split}-{offset}.json'
        if path.exists():record=json.loads(path.read_text())
        else:
            response=get('https://datasets-server.huggingface.co/rows',params={'dataset':repo,'config':'default','split':split,'offset':offset,'length':1,'revision':revision},revision=revision)
            body=response.json()
            if body.get('partial') or len(body.get('rows',[]))!=1 or body['rows'][0]['row_idx']!=offset or body['rows'][0].get('truncated_cells'):raise ValueError('Incomplete source row refused')
            row=body['rows'][0]['row']
            if any(row.get(k)!=selected_row[k] for k in ('label','source','resume_domain','jd_domain') if k in selected_row):raise ValueError('Selected row metadata differs from pinned source')
            record={'source':repo,'revision':revision,'source_split':split,'source_index':offset,'stratum':selected_row,'raw':row,'response_sha256':digest(response.content),'viewer_revision':response.headers['x-revision']};atomic(path,record)
        if record['revision']!=revision:raise ValueError('Checkpoint revision differs')
        rows.append(record)
    write_rows(folder/'samples.jsonl',rows)
    result={'repo':repo,'revision':revision,'license_declared':(info.get('cardData') or {}).get('license'),'license_scope_verified':False,'dataset_card_sha256':digest(card.encode()) if card else None,'repo_metadata_sha256':digest((folder/'repo.json').read_bytes()),'dataset_card_present':card is not None,'label_origin':'Qwen2.5-32B and generated cross-domain pairing (dataset card)' if name=='matching_merged' else 'Not documented in repository; no dataset card','human_approved':False,'pool_rows':len(index),'selected':len(rows),'downloaded_rows':len(rows),'reused_local_rows':0,'sampling':'80/20 published split quotas; equal label coverage; round-robin source/domain diversity; seed42 hash order','metadata_bytes_read':sum(r['length'] for f in files for r in f['ranges']),'full_shards_downloaded':0,'label_counts':dict(Counter(r['raw']['label'] for r in rows)),'samples_sha256':digest((folder/'samples.jsonl').read_bytes())}
    atomic(folder/'manifest.json',result);return result


def survey(root,legacy,tailoring=50,matching=100):
    root.mkdir(parents=True,exist_ok=True);results={};errors={}
    for name in REPOS:
        try:
            results[name]=survey_tailoring(root,legacy,tailoring) if name=='tailoring' else survey_matching(root,name,matching//2 if name=='matching_original' else matching-matching//2)
        except Exception as e:
            # Do not serialize HTTP bodies, CVs or credentials into logs.
            errors[name]={'type':type(e).__name__,'message':'Source survey incomplete; private checkpoints retained for resume.'}
    report={'version':VERSION,'seed':SEED,'sources':results,'errors':errors,'training_started':False};atomic(root/'manifest.json',report);return report


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,default=Path('ai/data/raw/hf-research-survey-v1'));p.add_argument('--legacy',type=Path,default=Path('ai/data/raw'));p.add_argument('--tailoring',type=int,default=50);p.add_argument('--matching',type=int,default=100);args=p.parse_args()
    if min(args.tailoring,args.matching)<1:p.error('Sample sizes must be positive')
    report=survey(args.output,args.legacy,args.tailoring,args.matching)
    if report['errors']:raise SystemExit(1)

if __name__=='__main__':main()
