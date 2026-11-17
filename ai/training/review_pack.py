"""Build an annotation-only pack from audited public JDs and explicitly synthetic CVs.
No runtime DB, personal CV, model call, label inference or training occurs here.
"""
import argparse
import hashlib
import json
import random
import re
from pathlib import Path
from backend.app.schemas.cv import CVDocument
from backend.app.schemas.profile import MasterProfile
from backend.app.schemas.dashboard import JobPosting

POLICY='cv-identity-and-jd-group-v1'
SPLITS=('train','validation','test')
FACTS={
 'train':[
  ('Backend API practice',['Python','PostgreSQL','Git'],['Built a Python REST API for inventory records.','Used PostgreSQL transactions to keep inventory writes consistent.']),
  ('Web component practice',['React','TypeScript','CSS'],['Built reusable React components for a course catalog.','Typed form inputs with TypeScript and styled responsive pages with CSS.']),
  ('Manual QA practice',['Manual Testing','SQL','API Testing'],['Wrote manual test cases for a registration workflow.','Checked API responses and verified persisted records with SQL.'])],
 'validation':[
  ('Data import practice',['Python','SQL','Pandas'],['Implemented a Python CSV import with validation errors.','Cleaned tabular data with Pandas before loading SQL tables.']),
  ('Accessibility practice',['JavaScript','React','HTML'],['Developed a keyboard accessible React menu.','Used semantic HTML and visible focus states on navigation controls.']),
  ('Regression QA practice',['Selenium','Python','Test Design'],['Automated browser regression checks with Selenium and Python.','Documented edge cases for a shopping cart workflow.'])],
 'test':[
  ('Service observability practice',['Python','FastAPI','Docker'],['Packaged a FastAPI service in a Docker container.','Recorded structured request logs for troubleshooting failed requests.']),
  ('Dashboard practice',['Vue','TypeScript','REST API'],['Created a Vue dashboard consuming paginated REST API data.','Handled empty states and retries with typed TypeScript state.']),
  ('Integration QA practice',['PostgreSQL','Integration Testing','Git'],['Tested PostgreSQL rollback behavior during failed writes.','Tracked reproducible integration failures in a Git repository.'])]}


def signature(job):
    text=re.sub(r'\W+',' ',job.description.casefold()).split()
    return set(zip(text,text[1:],text[2:]))


def jd_groups(jobs,threshold=.82):
    parents=list(range(len(jobs)));sets=[signature(job) for job in jobs]
    def root(i):
        while parents[i]!=i:parents[i]=parents[parents[i]];i=parents[i]
        return i
    for i in range(len(jobs)):
        for j in range(i):
            union=sets[i]|sets[j]
            if jobs[i].content_hash==jobs[j].content_hash or (union and len(sets[i]&sets[j])/len(union)>=threshold):parents[root(i)]=root(j)
    groups={}
    for i,job in enumerate(jobs):groups.setdefault(root(i),[]).append(job.posting_id)
    return {key:'jdg_'+hashlib.sha256('|'.join(sorted(members)).encode()).hexdigest()[:16] for members in groups.values() for key in members}


def assert_isolated(rows):
    cleaned=[r for r in rows if r.get('cleaning_provenance')]
    if cleaned:
        registries={r.get('corpus_registry') for r in cleaned}
        if len(registries)!=1 or None in registries or any(r.get('corpus_registry') not in registries for r in rows):
            raise ValueError('Cleaned data must share one audited corpus registry; do not mix legacy/pilot splits')
    seen={name:{} for name in ('cv_identity','jd_group')}
    for row in rows:
        if row['split'] not in SPLITS:raise ValueError('Unknown split')
        for name in seen:
            previous=seen[name].setdefault(row[name],row['split'])
            if previous!=row['split']:raise ValueError(f'{name} crosses split boundary')
    return {name:len(values) for name,values in seen.items()}


def build(jobs,seed=42):
    from ai.agents.cv_agent import source_document,bullet_catalog
    groups=jd_groups(jobs);keys=sorted(set(groups.values()));random.Random(seed).shuffle(keys)
    if len(keys)<10:raise ValueError('Need at least 10 independent JD groups for a three-way review pack')
    n=len(keys);train_end=int(n*.8);validation_end=max(train_end+1,int(n*.9))
    assignment={group:'train' if i<train_end else 'validation' if i<validation_end else 'test' for i,group in enumerate(keys)}
    rows=[]
    for job in jobs:
        split=assignment[groups[job.posting_id]]
        for index,(name,skills,facts) in enumerate(FACTS[split]):
            identity=f'synthetic-{split}-{index}'
            profile=MasterProfile(contact={'full_name':'Ứng viên tổng hợp '+identity},experience=[],project=[{'project_name':name,'description':facts}],education=[],involvement=[],skills=[{'group':'Declared skills','items':skills}])
            original=source_document(profile,identity,language='en')
            for variant in ('base','omitted','explicit_denial'):
                document=original.model_copy(deep=True)
                if variant=='omitted':document.sections[0].entries[0].bullets.pop()
                if variant=='explicit_denial':
                    from backend.app.schemas.cv import CVBullet
                    document.sections[0].entries[0].bullets.append(CVBullet(text='I have no experience with Kubernetes.',source_refs=['/synthetic/explicit_denial']))
                pair_id=hashlib.sha256(f'{identity}|{variant}|{job.posting_id}'.encode()).hexdigest()[:24]
                rows.append(dict(pack_version=1,split_policy=POLICY,pair_id=pair_id,split=split,cv_identity=identity,cv_variant=variant,jd_group=groups[job.posting_id],synthetic_cv=True,
                    job={'posting_id':job.posting_id,'content_hash':job.content_hash,'source_url':job.source_url,'fetched_at':job.fetched_at,'title':job.title,'description':job.description,'expiry_conflict':job.expiry_conflict},
                    cv=document.model_dump(mode='json'),catalog={key:bullet.text for key,bullet in bullet_catalog(document).items()},
                    annotation={'status':'pending','reviewer_ids':[],'requirements':[],'cv_plan':None,'source_usage_confirmed':False},
                    rubric={'statuses':['met','partially_met','unknown','not_met'],'rule':'Use displayed CV evidence only. Missing evidence is unknown; explicit denial may support not_met. Numeric/negation/entity preservation must be checked.'}))
    counts=assert_isolated(rows)
    return rows,dict(seed=seed,split_policy=POLICY,source_jobs=len(jobs),jd_groups=len(keys),cv_identities=counts['cv_identity'],packets=len(rows),splits={name:sum(r['split']==name for r in rows) for name in SPLITS},labels_reviewed=0,training_ready=False,blockers=['Human requirement and CVPlan labels pending','Public JD reuse/training rights unverified','CUDA training environment and held-out baseline evaluation required'],limitations=['Synthetic CVs are a small preparation sample, not a representative Vietnamese evaluation set','No expert labels or model-generated labels are asserted'])


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--jobs',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--seed',type=int,default=42);args=p.parse_args()
    if args.output.exists():raise SystemExit('Use a new output directory; reviewer work must not be overwritten')
    raw=args.jobs.read_bytes();jobs=[JobPosting.model_validate_json(line) for line in raw.decode().splitlines() if line.strip()]
    unique={j.posting_id:j for j in jobs}
    rows,manifest=build(list(unique.values()),args.seed);manifest['job_file_sha256']=hashlib.sha256(raw).hexdigest();args.output.mkdir(parents=True)
    for split in SPLITS:
        content=''.join(json.dumps(row,ensure_ascii=False)+'\n' for row in rows if row['split']==split)
        (args.output/(split+'.jsonl')).write_text(content)
    manifest['checksums']={path.name:hashlib.sha256(path.read_bytes()).hexdigest() for path in args.output.glob('*.jsonl')}
    (args.output/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))


if __name__=='__main__':main()


def load_verified(pack):
    """Read a pack and its provenance chain without creating reviewer progress."""
    pack=Path(pack);manifest=json.loads((pack/'manifest.json').read_text())
    if manifest.get('split_policy')!=POLICY:raise ValueError('Invalid grouped split policy')
    root=Path(__file__).resolve().parents[2]
    for source,expected in {**manifest.get('source_checksums',{}),**manifest.get('legacy_checksums',{}),**manifest.get('policy_checksums',{})}.items():
        path=Path(source) if Path(source).is_absolute() else root/source
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
            raise ValueError('Referenced source/legacy checksum changed; rebuild audit in a new pack')
    packets={}
    for split in SPLITS:
        name=split+'.jsonl';data=(pack/name).read_bytes()
        if hashlib.sha256(data).hexdigest()!=manifest['checksums'][name]:raise ValueError('Gói nguồn đã thay đổi checksum; dừng duyệt/export')
        for line in data.decode().splitlines():
            if not line.strip():continue
            row=json.loads(line)
            if manifest.get('task') and row.get('task')!=manifest['task']:raise ValueError('Mixed task contracts are not permitted in one reviewer pack')
            if row['split']!=split or row['pair_id'] in packets:raise ValueError('Split hoặc pair_id nguồn không hợp lệ')
            packets[row['pair_id']]=row
    assert_isolated(list(packets.values()))
    return manifest,packets
