"""Versioned sentence-pair audit for existing tailoring packets. No LLM or training."""
import argparse
from collections import Counter,defaultdict
import copy
from difflib import SequenceMatcher
import json
from pathlib import Path
import re

from ai.training.dataset_survey import digest,parse_iterate
from ai.training.dataset_convert import norm
from ai.training.review_pack import load_verified,assert_isolated,POLICY
from ai.training.review_store import atomic
from ai.agents.cv_grounding import GUARD_VERSION,check_rewrite,editorial_rewrite,catalog_context
from ai.prompts.cv_prompt import CV_PROMPT_VERSION
from backend.app.schemas.cv import CVDocument,CVPlan

VERSION='tailor-clean-v3'
ROOT=Path(__file__).resolve().parents[2]
DEFAULT_SOURCE=ROOT/'ai/data/processed/external-research-v1/tailoring'
DEFAULT_RAW=ROOT/'ai/data/raw/hf-research-survey-v1/abhaykanjoor/samples.jsonl'


def pointer(value,path):
    for part in path.strip('/').split('/'):
        part=part.replace('~1','/').replace('~0','~');value=value[int(part)] if isinstance(value,list) else value[part]
    return value


def word_diff(before,after):
    old=re.findall(r'\s+|[^\s]+',before or '');new=re.findall(r'\s+|[^\s]+',after or '');result=[]
    for op,a,b,c,d in SequenceMatcher(None,old,new,autojunk=False).get_opcodes():result.append({'op':op,'original':''.join(old[a:b]),'proposed':''.join(new[c:d])})
    return result


def source_contexts(packet):return catalog_context(CVDocument.model_validate(packet['cv']))


def assess_pair(packet,pair,proposed=None,source_ref=None,reason=None):
    ref=source_ref or pair.get('source_ref');text=pair['proposed_text'] if proposed is None else proposed
    if not isinstance(text,str) or not isinstance(reason if reason is not None else pair.get('reason'),str) or not (reason if reason is not None else pair.get('reason','')).strip():
        return {'version':GUARD_VERSION,'status':'rejected','checks':[{'name':'schema','status':'fail','details':['Nonempty text and reason required']}],'reason_codes':['schema']}
    if not ref:
        candidate=next(iter(pair.get('candidate_refs',[])),None)
        analysis=check_rewrite(packet['catalog'][candidate],text,source_contexts(packet).get(candidate)) if candidate else {'version':GUARD_VERSION,'checks':[],'reason_codes':[]}
        analysis['checks'].insert(0,{'name':'source_alignment','status':'warning','details':['No unique source binding; remaining checks are conditional comparisons only']})
        analysis.update(status='needs_review',reason_codes=['source_alignment']+analysis['reason_codes'],binding_unconfirmed=True)
        return analysis
    if ref not in packet['catalog'] or ref not in pair.get('allowed_source_refs',[]):
        return {'version':GUARD_VERSION,'status':'rejected','checks':[{'name':'source_entry_binding','status':'fail','details':['Source ref outside immutable entry']}],'reason_codes':['source_entry_binding']}
    original=packet['catalog'][ref];checks=check_rewrite(original,text,source_contexts(packet).get(ref))
    checks['checks'].insert(0,{'name':'source_exact','status':'pass' if (pair.get('source_ref')!=ref or pair.get('original_text')==original) else 'fail','details':[]})
    if checks['checks'][0]['status']=='fail':checks.update(status='rejected',reason_codes=['source_exact']+checks['reason_codes'])
    return checks


def make_pair(packet,origin,path,text,allowed,source_ref=None,candidates=None,reason=None):
    context=source_contexts(packet);candidates=candidates or []
    pair={'id':digest([packet['pair_id'],origin,path,text])[:24],'origin':origin,'target_path':path,'source_ref':source_ref,
          'candidate_refs':candidates,'allowed_source_refs':allowed,'original_text':packet['catalog'].get(source_ref),
          'proposed_text':text,'reason':reason or 'Đối chiếu output dataset với câu nguồn; cần reviewer kiểm tra ý nghĩa và mức liên quan JD.',
          'severity':'info','source_context':context.get(source_ref or (candidates[0] if candidates else None)),
          'human_reviewed':False,'model_assessment':None,'comparison_original_text':packet['catalog'].get(source_ref or (candidates[0] if candidates else None))}
    pair['assessment']=assess_pair(packet,pair);pair['status']=pair['assessment']['status'];pair['severity']='error' if pair['status']=='rejected' else 'warning' if pair['status']=='needs_review' else 'info'
    pair['diff']=word_diff(pair['original_text'] or (packet['catalog'].get(candidates[0],'') if candidates else ''),text)
    return pair


def bind_target(packet,path,text,allowed):
    exact=[r for r in allowed if packet['catalog'][r]==text]
    if len(exact)==1:return make_pair(packet,'dataset_target',path,text,allowed,exact[0])
    if exact:return make_pair(packet,'dataset_target',path,text,allowed,candidates=exact)
    scores=sorted(((SequenceMatcher(None,norm(packet['catalog'][r]),norm(text),autojunk=False).ratio(),r) for r in allowed),reverse=True)
    if not scores:return make_pair(packet,'dataset_target',path,text,allowed)
    top,ref=scores[0];margin=top-(scores[1][0] if len(scores)>1 else 0)
    # Similarity proposes a binding only; guards must independently preserve source information.
    if top>=.60 and margin>=.06:
        proposed=make_pair(packet,'dataset_target',path,text,allowed,ref)
        if proposed['status']=='candidate_pass':return proposed
        # A near-identical sentence with a definite fact delta is an auditable rejection.
        if top>=.90 and proposed['status']=='rejected':return proposed
    return make_pair(packet,'dataset_target',path,text,allowed,candidates=[ref] if top>=.25 else [])


def clean_packet(packet,record):
    if packet.get('task')!='tailor_review' or packet.get('original_matching_label') is not None:raise ValueError('Tailoring packets only; matching is excluded')
    if digest(record)!=packet['source_record_sha256']:raise ValueError('Raw row checksum mismatch')
    source,jd,target=parse_iterate(record['raw'])
    if target!=packet['original_target'] or jd!=packet['job']['description']:raise ValueError('Original target/JD changed')
    for ref,text in packet['catalog'].items():
        if pointer(source,ref)!=text:raise ValueError('Catalog text/ref does not match raw CV')
    out=copy.deepcopy(packet);contexts=source_contexts(out);pairs=[];scope=[]
    fields={'experience':('title','company','dates'),'projects':('title','dates'),'education':('degree','institution','dates'),'awards':('title','year','issuer'),'leadership':('role','organization','dates')}
    for field,keys in fields.items():
        originals=source.get(field,[]) or []
        for ti,entry in enumerate(target.get(field,[]) or []):
            root=f'/{field}/{ti}';indexes=[i for i,v in enumerate(originals) if all(v.get(k)==entry.get(k) for k in keys)]
            if len(indexes)!=1:
                scope.append({'path':root,'status':'rejected' if not indexes else 'needs_review','code':'entry_metadata_changed_or_ambiguous'})
                allowed=[]
            else:
                original_root=f'/{field}/{indexes[0]}'
                allowed=[ref for ref,ctx in contexts.items() if ctx['entry_id']==original_root]
            values=[]
            if field in {'projects','awards','leadership'} and isinstance(entry.get('description'),str) and entry['description'].strip():values.append((root+'/description',entry['description']))
            for name in ('bullet_points','tech_stack'):
                bullets=entry.get(name,[]) or []
                if isinstance(bullets,str):bullets=[bullets]
                for bi,text in enumerate(bullets):
                    if not isinstance(text,str):raise ValueError('Invalid target bullet schema')
                    if text.strip():values.append((f'{root}/{name}/{bi}',text))
            for path,text in values:pairs.append(bind_target(out,path,text,allowed))
    if isinstance(target.get('skills'),dict):
        for group,items in target['skills'].items():
            if isinstance(items,str):items=[items]
            # Skills retain their own source group, rather than a global text-only lookup.
            allowed=[r for r in out['catalog'] if r.startswith('/skills/'+group+'/')]
            for i,text in enumerate(items or []):
                if not isinstance(text,str):raise ValueError('Invalid target skills schema')
                if text.strip():pairs.append(bind_target(out,f'/skills/{group}/{i}',text,allowed))
    if source.get('summary')!=target.get('summary'):scope.append({'path':'/summary','status':'needs_review','code':'summary_outside_bullet_contract'})
    if source.get('personal_info')!=target.get('personal_info'):scope.append({'path':'/personal_info','status':'rejected','code':'contact_change_outside_bullet_contract'})
    # Preserve no-op choices; generate an independent, small rule-based alternative where possible.
    covered={p['source_ref'] for p in pairs if p['status']=='candidate_pass' and p['original_text']==p['proposed_text']}
    for ref,text in out['catalog'].items():
        rewritten,kinds=editorial_rewrite(text)
        if rewritten!=text:
            pair=make_pair(out,'rule_generated',ref,rewritten,[r for r,c in contexts.items() if c['entry_id']==contexts[ref]['entry_id']],ref,
                           reason='Đề xuất tự động theo quy tắc '+', '.join(kinds)+'; giữ dữ kiện, chưa được người duyệt.')
            pair['rule_kinds']=kinds;pairs.append(pair)
        elif ref not in covered:pairs.append(make_pair(out,'source_keep',ref,text,[ref],ref,reason='Giữ nguyên câu nguồn; reviewer quyết định có chọn nội dung này theo JD hay không.'))
    out['parent_conversion']=out['conversion'];out['parent_packet_sha256']=digest(packet)
    out['cleaning']={'version':VERSION,'guard_version':GUARD_VERSION,'prompt_version':CV_PROMPT_VERSION,'pairs':pairs,'scope_changes':scope,
                     'scope':'partial_bullet_plan','complete_original_target':False,'selection_status':'unreviewed','models_called':False,
                     'corpus_registry':'external-research-v1','candidate_pass_is_human_approved':False,'status':'needs_review' if scope or any(p['status']!='candidate_pass' for p in pairs) else 'candidate_pass'}
    out['annotation']={'status':'draft','reviewer_ids':[],'source_usage_confirmed':False,'cv_usage_confirmed':False,'conversion_review_confirmed':False,
                       'requirements':[],'requirement_groups':[],'cv_plan':{'selected_refs':[],'review':{'items':[],'warnings':['Partial conversion. Original target and rejected/uncertain proposals remain available for review.']}},
                       'pair_decisions':{},'partial_plan_review_confirmed':False}
    return out


def validate_decision_shape(packet,annotation):
    pairs={p['id']:p for p in packet['cleaning']['pairs']};decisions=annotation.get('pair_decisions',{})
    if not isinstance(decisions,dict) or set(decisions)-set(pairs):raise ValueError('Unknown proposal decision')
    for ident,decision in decisions.items():
        if not isinstance(decision,dict) or set(decision)-{'action','source_ref','proposed_text','reason','semantic_review_confirmed'}:raise ValueError('Invalid proposal decision schema')
        if decision.get('action') not in {'edit','accept','keep','discard'}:raise ValueError('Invalid proposal decision action')
        for field in ('source_ref','proposed_text','reason'):
            if field in decision and (not isinstance(decision[field],str) or len(decision[field])>20000):raise ValueError('Invalid proposal text')
        ref=decision.get('source_ref')
        if ref and (ref not in packet['catalog'] or ref not in pairs[ident]['allowed_source_refs']):raise ValueError('Source ref outside immutable entry')
        if 'semantic_review_confirmed' in decision and type(decision['semantic_review_confirmed']) is not bool:raise ValueError('Invalid semantic review confirmation')


def validate_decisions(packet,annotation):
    """Approval gate only. Pair acceptance never supplies reviewer IDs or permissions."""
    if not packet.get('cleaning'):return
    validate_decision_shape(packet,annotation)
    if packet['cleaning']['guard_version']!=GUARD_VERSION:raise ValueError('Guard version changed; re-audit in a new pack')
    if annotation.get('partial_plan_review_confirmed') is not True:raise ValueError('Cần xác nhận phạm vi plan một phần và kiểm tra lựa chọn theo JD')
    pairs={p['id']:p for p in packet['cleaning']['pairs']};decisions=annotation.get('pair_decisions',{})
    if not isinstance(decisions,dict) or set(decisions)-set(pairs):raise ValueError('Quyết định đề xuất không thuộc gói nguồn')
    plan=CVPlan.model_validate(annotation['cv_plan']);reviews={item.source_ref:item for item in plan.review.items};chosen={}
    for ident,pair in pairs.items():
        decision=decisions.get(ident)
        if decision is None:
            if pair['origin']!='source_keep':raise ValueError('Còn đề xuất chưa có quyết định giữ/sửa/chấp nhận/bỏ')
            continue
        if decision.get('action') not in {'accept','keep','discard'}:raise ValueError('Invalid pair decision')
        if decision['action']=='discard':continue
        ref=decision.get('source_ref') or pair.get('source_ref')
        if not ref or ref not in pair['allowed_source_refs'] or ref not in packet['catalog']:raise ValueError('Đề xuất chưa được gắn đúng entry nguồn')
        if ref in chosen:raise ValueError('Chỉ chọn một phương án cho mỗi bullet nguồn')
        chosen[ref]=ident
        original=packet['catalog'][ref]
        proposed=original if decision['action']=='keep' else decision.get('proposed_text',pair['proposed_text'])
        reason=decision.get('reason','')
        check=assess_pair(packet,pair,proposed,ref,reason)
        if check['status']=='rejected':raise ValueError('Đề xuất được chọn còn lỗi dữ kiện/nguồn: '+','.join(check['reason_codes']))
        if check['status']=='needs_review' and decision.get('semantic_review_confirmed') is not True:raise ValueError('Cần reviewer xác nhận ý nghĩa của câu sửa chưa chắc chắn')
        if ref not in plan.selected_refs:raise ValueError('Đề xuất được chấp nhận chưa thuộc bullet đã chọn')
        if proposed!=original:
            item=reviews.get(ref)
            if item is None or item.original_text!=original or item.proposed_text!=proposed or item.reason!=reason:raise ValueError('CVPlan không khớp quyết định sửa câu')
        elif ref in reviews:raise ValueError('Quyết định giữ nguyên còn chứa bản viết lại')
    # Manual edits in the source-bullet editor are also rechecked; no untracked rewrite bypass.
    for ref,item in reviews.items():
        if ref not in chosen:raise ValueError('Mọi câu sửa cần có quyết định reviewer trong màn hình đối chiếu')


def dedup_audit(packets,source_manifest,source=DEFAULT_SOURCE,exclude=None):
    """Parent/global registry already jointly groups CV/JD. Preserve, never resplit."""
    other=source.parent/'matching';_,matching=load_verified(other) if other.exists() else ({},{})
    _,parents=load_verified(source)
    registry=list(parents.values())+list(matching.values());assert_isolated(registry+packets)
    for row in packets:
        parent=parents[row['pair_id']]
        if any(row[k]!=parent[k] for k in ('split','cv_identity','jd_group','catalog','job','cv')):raise ValueError('Source identity/split/content changed during cleaning')
    known=json.loads((source.parent/'report.json').read_text())['group_audit'] if (source.parent/'report.json').exists() else {}
    overlaps=[]
    keys={(norm(p['source_resume_text']),norm(p['job']['description'])):p['split'] for p in packets}
    for path in sorted(source.parent.parent.rglob('manifest.json')):
        if any(part.startswith('tailor-clean') for part in path.parts) or (exclude is not None and path.resolve().is_relative_to(exclude.resolve())):continue
        matched=0;conflicts=0
        for split in ('train','validation','test'):
            file=path.parent/(split+'.jsonl')
            if not file.exists():continue
            for line in file.read_text().splitlines():
                row=json.loads(line);key=(norm(row.get('source_resume_text','')),norm(row['job']['description']))
                if key in keys:matched+=1;conflicts+=row['split']!=keys[key]
        if matched:overlaps.append({'pack':str(path.parent),'shared_source_pairs':matched,'historical_fold_conflicts':conflicts})
    return {'historical_pack_overlaps':overlaps,'registry_packets':len(registry),'intentional_parent_versions':len(packets),'group_isolation':True,'split_changed':False,
            'legacy_overlap':known,'scope':'Same parent corpus version, not new independent examples. Do not combine legacy/pilot splits by their names.'}


def run(source,raw,output,limit=None):
    source=source.resolve();raw=raw.resolve();output=output.resolve()
    manifest,by_id=load_verified(source)
    rows=sorted(by_id.values(),key=lambda p:digest(['tailor-clean-v1',p['pair_id']]))
    if limit:rows=rows[:limit]
    if not rows or any(p.get('task')!='tailor_review' for p in rows):raise ValueError('Expected tailoring-only source packets')
    records={digest(r):r for r in (json.loads(line) for line in raw.read_text().splitlines() if line.strip())}
    deps={**manifest.get('source_checksums',{}),**manifest.get('legacy_checksums',{}),str(raw):digest(raw.read_bytes()),str(source/'manifest.json'):digest((source/'manifest.json').read_bytes())}
    for split in ('train','validation','test'):deps[str(source/(split+'.jsonl'))]=digest((source/(split+'.jsonl')).read_bytes())
    policy_checks={str(path.relative_to(ROOT)):digest(path.read_bytes()) for path in (Path(__file__).resolve(),ROOT/'ai/agents/cv_grounding.py',ROOT/'ai/prompts/cv_prompt.py')}
    for path in sorted(source.parent.parent.rglob('manifest.json')):
        if any(part.startswith('tailor-clean') for part in path.parts) or path.resolve().is_relative_to(output):continue
        deps[str(path)]=digest(path.read_bytes())
        for split in ('train','validation','test'):
            file=path.parent/(split+'.jsonl')
            if file.exists():deps[str(file)]=digest(file.read_bytes())
    fingerprint=digest([VERSION,GUARD_VERSION,CV_PROMPT_VERSION,policy_checks,deps,limit])
    output.mkdir(parents=True,exist_ok=True);checkpoint=output/'checkpoint.json';work=output/'records';work.mkdir(exist_ok=True)
    state=json.loads(checkpoint.read_text()) if checkpoint.exists() else {'fingerprint':fingerprint,'completed':{},'errors':{}}
    if state['fingerprint']!=fingerprint:raise ValueError('Inputs/policy changed; use a new versioned output')
    packets=[]
    for packet in rows:
        key=packet['pair_id'];path=work/(key+'.json')
        if key in state.get('errors',{}):continue
        if key in state['completed']:
            if digest(path.read_bytes())!=state['completed'][key]:raise ValueError('Checkpoint result checksum differs')
            clean=json.loads(path.read_text())
        else:
            try:clean=clean_packet(packet,records[packet['source_record_sha256']])
            except (ValueError,KeyError,TypeError,IndexError) as error:
                known={'Raw row checksum mismatch','Original target/JD changed','Catalog text/ref does not match raw CV','Invalid target bullet schema','Invalid target skills schema','Tailoring packets only; matching is excluded'}
                message=str(error) if str(error) in known else 'source_schema_or_checksum_failed'
                state.setdefault('errors',{})[key]={'pair_id':key,'status':'rejected','code':message,'type':type(error).__name__};atomic(checkpoint,state);continue
            atomic(path,clean);state['completed'][key]=digest(path.read_bytes());atomic(checkpoint,state)
        packets.append(clean)
    audit=dedup_audit(packets,manifest,source,output);checks={}
    for split in ('train','validation','test'):
        path=output/(split+'.jsonl');content=''.join(json.dumps(p,ensure_ascii=False)+'\n' for p in packets if p['split']==split)
        if path.exists() and path.read_text()!=content:raise ValueError('Refusing overwrite of a different completed pack')
        if not path.exists():path.write_text(content)
        checks[path.name]=digest(path.read_bytes())
    pairs=[pair for p in packets for pair in p['cleaning']['pairs']];target=[p for p in pairs if p['origin']=='dataset_target'];alternatives=[p for p in pairs if p['origin']!='dataset_target']
    status=Counter(p['status'] for p in pairs);rewritten=sum(p['source_ref'] is not None and p['original_text']!=p['proposed_text'] for p in pairs);kept=sum(p['source_ref'] is not None and p['original_text']==p['proposed_text'] for p in pairs)
    report={'input_samples':len(rows),'rejected_samples':len(state.get('errors',{})),'version':VERSION,'guard_version':GUARD_VERSION,'samples':len(packets),'source_bullets':sum(len(p['catalog']) for p in packets),'pairs':len(pairs),'pair_states':dict(status),
            'sample_states':dict(Counter(p['cleaning']['status'] for p in packets)),'target_pairs':len(target),'target_states':dict(Counter(p['status'] for p in target)),
            'source_alternatives':len(alternatives),'rule_rewrites':sum(p['origin']=='rule_generated' for p in alternatives),'kept_pairs':kept,'rewritten_pairs':rewritten,'unbound_pairs':sum(p['source_ref'] is None for p in pairs),
            'candidate_keep':sum(p['status']=='candidate_pass' and p['original_text']==p['proposed_text'] for p in pairs),'candidate_rewrite':sum(p['status']=='candidate_pass' and p['original_text']!=p['proposed_text'] for p in pairs),
            'reason_counts':dict(Counter(c for p in pairs for c in p['assessment']['reason_codes'])),'rewrite_rule_counts':dict(Counter(kind for p in pairs for kind in p.get('rule_kinds',[]))),'scope_changes':dict(Counter(s['code'] for p in packets for s in p['cleaning']['scope_changes'])),
            'splits':dict(Counter(p['split'] for p in packets)),'dedup_audit':audit,'human_approved':0,'source_usage_confirmed':0,'models_called':False,'training_started':False,'adapter_enabled':False,'complete_original_targets':0}
    atomic(output/'manifest.json',{'pack_version':1,'task':'tailor_review','pipeline_version':VERSION,'guard_version':GUARD_VERSION,'prompt_version':CV_PROMPT_VERSION,'split_policy':POLICY,'checksums':checks,'source_checksums':deps,'review_cohort':[p['pair_id'] for p in sorted(packets,key=lambda p:(p['split']!='train',-sum(v['status']=='candidate_pass' and v['origin']=='rule_generated' for v in p['cleaning']['pairs']),p['pair_id']))[:10]],'packets':len(packets),'splits':report['splits'],'training_ready':False,'scope':'partial_bullet_plan','dedup_audit':audit,'policy_checksums':policy_checks})
    atomic(output/'examples-redacted.json',safe_examples(packets))
    atomic(output/'errors.json',list(state.get('errors',{}).values()))
    atomic(output/'report.json',report);atomic(output/'issues.json',[{'pair_id':p['pair_id'],'proposal_id':pair['id'],'status':pair['status'],'reason_codes':pair['assessment']['reason_codes']} for p in packets for pair in p['cleaning']['pairs'] if pair['status']!='candidate_pass'])
    return report


def safe_examples(packets):
    from ai.agents.cv_grounding import TECHNOLOGIES
    allowed=set('a an the and or for to of in on with using by from data used utilized built developed reviewed records monthly daily weekly annually basis revenues commissions expenses ensure they are recorded appropriately work worked collaboratively collaborated api apis rest'.split())|{t.casefold() for t in TECHNOLOGIES}
    def redact(text):
        text=re.sub(r'https?://\S+|[\w.+-]+@[\w.-]+','[CONTACT]',text or '')
        text=re.sub(r'\d+(?:[.,]\d+)?','[NUMBER]',text)
        return re.sub(r'[\w.+#-]+',lambda m:m.group() if m.group().casefold() in allowed or m.group() in {'CONTACT','NUMBER'} else '[REDACTED]',text)
    result=[]
    for packet in packets:
        for pair in packet['cleaning']['pairs']:
            if pair['status']=='candidate_pass' and pair['origin']=='rule_generated' and len(result)<3:
                result.append({'pair_id':packet['pair_id'],'source_ref':pair['source_ref'],'before':redact(pair['original_text']),'after':redact(pair['proposed_text']),'status':'candidate_pass_not_human_approved','rules':pair.get('rule_kinds',[])})
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,default=DEFAULT_SOURCE);p.add_argument('--raw',type=Path,default=DEFAULT_RAW);p.add_argument('--output',type=Path,required=True);p.add_argument('--limit',type=int);a=p.parse_args();run(a.source,a.raw,a.output,a.limit)

if __name__=='__main__':main()
