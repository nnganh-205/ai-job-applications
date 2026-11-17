"""Reproducible local CV writing checks. Never changes user CVs or trains models."""
import argparse,os,sys,json,time,re,hashlib
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
p=argparse.ArgumentParser();p.add_argument('--writer',required=True);p.add_argument('--verifier',required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--context',type=int,default=8192);p.add_argument('--only',default='');args=p.parse_args()
os.environ.update(WRITER_MODEL=args.writer,VERIFIER_MODEL=args.verifier,LLM_CONTEXT_LENGTH=str(args.context))
from backend.app.services import cv_writer,cv_polish
from ai.agents import cv_semantics
from ai.llm.ollama_client import request_structured
from backend.app.core.config import settings
import httpx
cases=json.loads((ROOT/'backend/tests/fixtures/cv_writing_cases.json').read_text());cases=[c for c in cases if not args.only or c['id'] in args.only.split(',')];out=args.output;out.mkdir(parents=True,exist_ok=True)
files=['ai/agents/cv_clauses.py','ai/agents/cv_fidelity.py','ai/agents/cv_semantics.py','backend/app/services/cv_writer.py','backend/app/services/cv_polish.py','ai/agents/cv_grounding.py','ai/agents/cv_style.py','ai/llm/ollama_client.py','backend/app/core/config.py','scripts/evaluate_cv_writing.py']
with httpx.Client(base_url=settings.ollama_base_url,trust_env=False,timeout=30) as client:
 tags=client.get('/api/tags').json();needed={args.writer,args.verifier}
 assert needed<={m['name'] for m in tags['models']}
 manifest=dict(writer=args.writer,verifier=args.verifier,models={m['name']:m['digest'] for m in tags['models'] if m['name'] in needed},sources={f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in files},cases_sha256=hashlib.sha256((ROOT/'backend/tests/fixtures/cv_writing_cases.json').read_bytes()).hexdigest(),labels='Developer-authored diagnostic references, not expert labels',selected_cases=[c['id'] for c in cases],options=dict(writer_context=args.context,verifier_context=4096,temperature=0))
 identity=out/'manifest.json'
 if identity.exists() and json.loads(identity.read_text())!=manifest:raise ValueError('Model, source or cases changed; choose a fresh output directory.')
 identity.write_text(json.dumps(manifest,indent=2))
rows=[]
for track in ('writer','polish'):
 for case in cases:
  if track=='polish' and case['id'] not in {'sales','hr','retail','design'}:continue
  path=out/(case['id']+'-'+track+'.json')
  if path.exists():
   cached=json.loads(path.read_text())
   if (cached.get('id'),cached.get('track'),cached.get('source'))!=(case['id'],track,case['text']):raise ValueError('Cached result does not match the scheduled case.')
   rows.append(cached);continue
  raw=[]
  def call(messages,schema,**kwargs):
   start=time.monotonic();v=request_structured(messages,schema,**kwargs);raw.append(dict(task=kwargs.get('task'),result=v.model_dump(),seconds=time.monotonic()-start));return v
  start=time.monotonic();row=dict(id=case['id'],cohort=case['cohort'],track=track,source=case['text'])
  try:
   with patch.object(cv_writer,'request_structured',side_effect=call),patch.object(cv_polish,'request_structured',side_effect=call),patch.object(cv_semantics,'request_structured',side_effect=call):
    result=cv_writer.write_bullets(cv_writer.WriterRequest(text=case['text'],field='description',count=2)) if track=='writer' else cv_polish.polish(cv_polish.PolishRequest(text=case['text']))
   text='\n'.join(b['text'] for b in result['bullets']) if track=='writer' else result['proposed']
   missing=[pattern for pattern in case['units'] if not re.search(pattern,text,re.I)]
   row.update(result=result,text=text,missing_reference_units=missing,reference_complete=not missing,pronoun_free=not bool(re.search(r'\b(?:mình|tôi|em)\b',text,re.I)))
  except Exception as e:row.update(error=type(e).__name__+': '+str(e))
  row.update(seconds=time.monotonic()-start,calls=raw);rows.append(row);path.write_text(json.dumps(row,ensure_ascii=False,indent=2));(out/'results.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2));print(track,case['id'],row.get('result',{}).get('engine'),row.get('reference_complete'),round(row['seconds'],1),flush=True)
assert all(hashlib.sha256((ROOT/f).read_bytes()).hexdigest()==h for f,h in manifest['sources'].items()),'Source changed during evaluation'
from collections import Counter
summary=dict(total=len(rows),complete=sum(r.get('reference_complete',False) for r in rows),pronoun_free=sum(r.get('pronoun_free',False) for r in rows),origins=dict(Counter(r.get('result',{}).get('engine') for r in rows)),errors=[r['id'] for r in rows if 'error' in r])
(out/'summary.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary),flush=True)
