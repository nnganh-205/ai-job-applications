"""Build provenance-bound 8B research data; no personal workspace CVs are read."""
import json,re,hashlib,random,zipfile
from pathlib import Path
from collections import Counter,defaultdict

ROOT=Path(__file__).resolve().parents[2]
RAW=ROOT/'ai/data/raw/cv8b-sources'
OUT=ROOT/'ai/data/processed/cv8b-v1'
SEED=42

def digest(x):return hashlib.sha256((x if isinstance(x,bytes) else str(x).encode())).hexdigest()
def norm(x):return re.sub(r'\d+(?:[.,]\d+)*','<n>',' '.join(x.casefold().split())).rstrip('.')
def split(group):
 n=int(digest(group)[:8],16)%100
 return 'test' if n<10 else 'validation' if n<20 else 'train'

def safe(a,b):
 from ai.agents.cv_grounding import check_rewrite
 from backend.app.services.cv_writer import unsupported_claims
 from backend.app.services.cv_wording_constraints import missing_scope_clauses
 if not (20<=len(a)<=650 and 15<=len(b)<=700):return False
 if re.search(r'https?://|\S+@\S+|\b\d{9,}\b',a+' '+b):return False
 if a.casefold()==b.casefold():return False
 return check_rewrite(a,b)['status']!='rejected' and not unsupported_claims(a,b) and not missing_scope_clauses(a,b)

def messages(a,b,task,lang='vi'):
 if task=='cv_writer':
  system=f'Write professional CV bullets in {lang}. Use only supplied facts. Preserve work, role, methods, quantities, negation, conditions and goals. Never invent achievements. Each fact stays in one bullet; cite its id. Return JSON with bullets: [{{text,source_ids}}].'
  user=dict(facts=[dict(id='f0',kind='work',text=a)],max_bullets=1,style='professional')
  answer=dict(bullets=[dict(text=b,source_ids=['f0'])])
 else:
  system=f'Edit the supplied text in {lang}. Preserve its complete meaning, names, facts, numbers, roles, negation and conditions. Do not add achievements or claims. Return JSON with only text.'
  if task=='cv_polish':system+=' Use clear professional CV language without first-person chat filler.'
  user=dict(source_text=a,field='description');answer=dict(text=b)
 return [dict(role='system',content=system),dict(role='user',content=json.dumps(user,ensure_ascii=False)),dict(role='assistant',content=json.dumps(answer,ensure_ascii=False))]

def build(translations=None):
 OUT.mkdir(exist_ok=True,parents=True);rows=[];rejected=Counter();seen=set()
 def add(a,b,source,group,task='aux_edit',lang='vi',meta=None,assigned=None):
  key=(norm(a),norm(b),task)
  if key in seen:return
  seen.add(key)
  if not safe(a,b):rejected[source]+=1;return
  rows.append(dict(id=digest(str(key)+source)[:24],source=source,group=group,split=assigned or split(group),task=task,language=lang,label_quality='authored_or_source_labels_rule_screened_not_expert',messages=messages(a,b,task,lang),metadata=meta or {}))
 # Keep official validation/test out of training, then deduplicate by connected text families below.
 for part in ['train','validation']:
  path=RAW/'grammarly--coedit'/f'{part}.jsonl';groups=defaultdict(list)
  for line in path.read_text().splitlines():
   r=json.loads(line);groups[r['task']].append(r)
  for task,items in groups.items():
   random.Random(SEED).shuffle(items)
   for r in items[:600 if part=='train' else 60]:
    a=r['src'].split(': ',1)[-1];add(a,r['tgt'],'coedit','coedit:'+norm(a),'aux_edit','en',{'editing_task':task},part)
 with zipfile.ZipFile(RAW/'ngwgsang--ViSP/json_format.zip') as z:
  for original_split,file in [('train','train'),('validation','val'),('test','test')]:
   corpus=json.loads(z.read('json_format/visp_'+file+'.json'));buckets=defaultdict(list)
   for r in corpus:buckets[r['topic']].append(r)
   for topic,items in buckets.items():
    random.Random(SEED).shuffle(items)
    for r in items[:300 if original_split=='train' else 30]:
     if r['paraphrases']:add(r['original'],r['paraphrases'][0]['text'],'visp','visp:'+norm(r['original']),'aux_edit','vi',{'topic':topic,'research_only':True},original_split)
 # Occupational statements are task descriptions, never assertions about a real candidate.
 tasks=json.loads((RAW/'onet-31/task_statements.json').read_text())['row'];buckets=defaultdict(list)
 for r in tasks:
  if 25<len(r['task'])<330:buckets[r['onetsoc_code']].append(r)
 selected=[]
 for occupation,items in sorted(buckets.items()):
  random.Random(SEED).shuffle(items);selected.extend(items[:3])
 for r in selected:
  target=r['task'].strip();group='onet:'+r['onetsoc_code']
  add('My tasks included: '+target,target,'onet',group,'cv_writer','en',{'occupation':r['title'],'task_id':r['task_id'],'fictional_cv':True})
 # Translations come from a pinned MT model, not asserted to be expert CV labels.
 if translations:
  data=json.loads(Path(translations).read_text())
  for r in data:
   # Language detection and factual regex checks do not establish translation quality.
   # The Colab audit found repetition and mistranslations in the OPUS-MT outputs.
   if r.get('cv_quality_verified') is not True:
    rejected['onet-translated-unverified']+=1;continue
   t=r['translation'].strip();group='onet:'+r['onetsoc_code']
   if not re.search(r'[à-ỹ]',t,re.I):continue
   target=t[0].upper()+t[1:]
   for task,prefix in [('cv_writer','mình đã '),('cv_polish','em có làm công việc này: ')]:
    add(prefix+target[0].lower()+target[1:],target,'onet-translated',group,task,'vi',{'occupation':r['title'],'task_id':r['task_id'],'fictional_cv':True,'machine_translated':True})
 # Carry only the original training portion of V6; its holdouts remain untouched.
 with zipfile.ZipFile(ROOT/'output/colab/kltn-cv-writer-v6-720.zip') as z:
  for line in z.read('data/train.jsonl').decode().splitlines():
   r=json.loads(line);r.update(source='v6-authored',group='v6:'+r['source_families'][0],split='train',id=r['sample_id'],task='cv_'+r['track'],language='vi',label_quality='fictional_authored_not_expert');rows.append(r)
 # Union normalized source/target across task variants, preventing sentence leakage.
 parent={}
 def find(x):
  parent.setdefault(x,x)
  if parent[x]!=x:parent[x]=find(parent[x])
  return parent[x]
 def union(a,b):parent[find(a)]=find(b)
 for row in rows:
  payload=json.loads(row['messages'][1]['content']);source=payload.get('source_text') or '\n'.join(f['text'] for f in payload.get('facts',[]) if f['kind']=='work');answer=json.loads(row['messages'][-1]['content']);target=answer.get('text') or '\n'.join(b['text'] for b in answer.get('bullets',[]))
  row['_source']=norm(source);row['_target']=norm(target);union(row['group'],'s:'+row['_source']);union(row['group'],'s:'+row['_target'])
 assignment={};priority={'train':0,'validation':1,'test':2}
 for row in rows:
  g=find(row['group']);previous=assignment.get(g,'train');assignment[g]=max([previous,row['split']],key=priority.get)
 by_split=defaultdict(list)
 for row in rows:
  row['family']=digest(find(row['group']))[:20];row['split']=assignment[find(row['group'])];row.pop('_source');row.pop('_target');by_split[row['split']].append(row)
 for key,items in by_split.items():
  random.Random(SEED).shuffle(items);(OUT/(key+'.jsonl')).write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in items))
 (OUT/'onet-to-translate.json').write_text(json.dumps(selected,ensure_ascii=False))
 manifests=[json.loads(p.read_text()) for p in RAW.rglob('source.json')]
 report=dict(version='cv8b-v1',model='Qwen/Qwen3-8B',sources=manifests,counts={k:len(v) for k,v in by_split.items()},families={k:len({r['family'] for r in v}) for k,v in by_split.items()},tasks=dict(Counter(r['task'] for r in rows)),languages=dict(Counter(r['language'] for r in rows)),source_counts=dict(Counter(r['source'] for r in rows)),rejected=dict(rejected),research_only=True,training_started=False,expert_reviewed=False,translations_added=any(r['source']=='onet-translated' for r in rows),checksums={p.name:digest(p.read_bytes()) for p in OUT.glob('*.jsonl')})
 (OUT/'manifest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps({k:v for k,v in report.items() if k!='sources'},ensure_ascii=False,indent=2))
 return report

if __name__=='__main__':
 import argparse
 p=argparse.ArgumentParser();p.add_argument('--translations');a=p.parse_args();build(a.translations)
