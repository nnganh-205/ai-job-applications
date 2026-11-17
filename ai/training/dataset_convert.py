"""Source-grounded external-data conversion and joint split audit; no model/trainer."""
import argparse
from collections import Counter, defaultdict
from difflib import SequenceMatcher
import hashlib
import json
from pathlib import Path
import re
import unicodedata

from ai.training.dataset_survey import digest, parse_iterate
from ai.training.review_pack import POLICY, assert_isolated
from ai.training.review_store import atomic
from ai.agents.cv_grounding import TECHNOLOGIES, entities, grounded_rewrite
from ai.agents.matching_agent import contains_term
from backend.app.schemas.cv import CVDocument, CVPlan

VERSION='external-convert-v1'
LABELS={'Good Fit','Potential Fit','No Fit'}


def norm(text):return ' '.join(re.findall(r'\w+',unicodedata.normalize('NFKC',str(text)).casefold()))
def identity(text):return digest(norm(text).encode())

def strings(value):
    if isinstance(value,str):return [value]
    if isinstance(value,list):return [text for item in value for text in strings(item)]
    if isinstance(value,dict):return [text for key,item in value.items() if key not in {'personal_info','contact'} for text in strings(item)]
    return []


def cv_text(cv):return '\n'.join(strings(cv)) if isinstance(cv,dict) else str(cv)

def issue(code,path=''):return {'code':code,'target_path':path}


def rewrite_issues(original,proposed):
    """Fail closed. Automatic checks never establish human or semantic approval."""
    result=[]
    numbers=lambda text:Counter(re.findall(r'\d+(?:[.,]\d+)?%?',text))
    if numbers(original)!=numbers(proposed):result.append('number_or_time_changed')
    neg=lambda text:Counter(re.findall(r"\b(?:never|not|no|without|cannot|can't|haven't|didn't)\b|chưa|không",text.casefold()))
    if neg(original)!=neg(proposed):result.append('negation_changed')
    tech=lambda text:{term for term in TECHNOLOGIES if contains_term(text,term)}
    if tech(original)!=tech(proposed):result.append('technology_added_or_removed')
    if entities(original)!=entities(proposed):result.append('entity_company_or_title_changed')
    if not grounded_rewrite(original,proposed):result.append('runtime_factual_guard_failed')
    support=r'\b(?:assisted|supported|helped|contributed|participated)\b'
    if re.search(support,original,re.I) and not re.search(support,proposed,re.I):result.append('contribution_scope_changed')
    # Unchecked novel content words need human review even if named-entity guards pass.
    editorial={'a','an','the','and','or','for','to','of','in','on','with','using','by','that','which','was','were','is','are','built','developed','created','implemented'}
    if set(norm(proposed).split())-set(norm(original).split())-editorial:result.append('semantic_change_unverified')
    return list(dict.fromkeys(result))


def structured_document(cv,source_id):
    sections=[];catalog={};contexts={}
    def section(kind,heading):
        value={'kind':kind,'heading':heading,'entries':[]};sections.append(value);return value
    def add_entry(group,path,title,subtitle=None,period=None):
        entry={'source_entry_id':path,'title':title or 'Source entry','subtitle':subtitle,'period':period,'bullets':[]};group['entries'].append(entry);return entry
    def bullet(entry,path,text,context):
        if not isinstance(text,str) or not text.strip():return
        catalog[path]=text;contexts[path]=context;entry['bullets'].append({'text':text,'source_refs':[path]})
    for field,kind,heading in [('experience','experience','Experience'),('projects','project','Projects')]:
        group=section(kind,heading)
        for i,item in enumerate(cv.get(field,[]) or []):
            path=f'/{field}/{i}';entry=add_entry(group,path,item.get('title'),item.get('company'),item.get('dates'))
            if field=='projects' and isinstance(item.get('description'),str):bullet(entry,path+'/description',item['description'],path)
            for key in ('bullet_points','tech_stack'):
                values=item.get(key,[]) or []
                if isinstance(values,str):values=[values]
                for j,text in enumerate(values):bullet(entry,f'{path}/{key}/{j}',text,path)
    skills=cv.get('skills') or {};group=section('skills','Skills')
    if isinstance(skills,dict):
        for category,values in skills.items():
            entry=add_entry(group,'/skills/'+category,category)
            if isinstance(values,str):values=[values]
            for i,text in enumerate(values or []):bullet(entry,f'/skills/{category}/{i}',text,'/skills/'+category)
    group=section('education','Education')
    for i,item in enumerate(cv.get('education',[]) or []):add_entry(group,f'/education/{i}',item.get('degree'),item.get('institution'),item.get('dates'))
    for field in ('awards','leadership'):
        group=section('involvement',field.title())
        for i,item in enumerate(cv.get(field,[]) or []):
            entry=add_entry(group,f'/{field}/{i}',item.get('title') or item.get('role'),item.get('issuer') or item.get('organization'),item.get('dates') or str(item.get('year') or '') or None)
            if item.get('description'):bullet(entry,f'/{field}/{i}/description',item['description'],f'/{field}/{i}')
    summary=cv.get('summary')
    document=CVDocument.model_validate({'source_profile_revision_id':'external-'+source_id,'language':'en','contact':{},'summary':{'text':summary,'source_refs':['/summary']} if summary else None,'sections':[s for s in sections if s['entries']]})
    return document.model_dump(mode='json'),catalog,contexts


def tailor_conversion(raw):
    source,jd,target=parse_iterate(raw);doc,catalog,contexts=structured_document(source,digest(raw)[:24]);errors=[];alignment=[];selected=[];reviews=[]
    if source.get('summary')!=target.get('summary'):errors.append(issue('summary_change_outside_bullet_contract','/summary'))
    if source.get('personal_info')!=target.get('personal_info'):errors.append(issue('personal_metadata_changed','/personal_info'))
    # Entry metadata is immutable; removing an entry is allowed, inventing/relabeling it is not.
    for field,keys in [('experience',('title','company','dates')),('projects',('title',)),('education',('degree','institution','dates')),('awards',('title','year','issuer')),('leadership',('role','organization','dates'))]:
        source_entries=source.get(field,[]) or []
        for ti,item in enumerate(target.get(field,[]) or []):
            candidates=[i for i,s in enumerate(source_entries) if all(s.get(k)==item.get(k) for k in keys)]
            target_root=f'/{field}/{ti}'
            if len(candidates)!=1:
                errors.append(issue('entry_company_title_or_time_not_uniquely_grounded',target_root));continue
            si=candidates[0];root=f'/{field}/{si}'
            if field=='projects' and source_entries[si].get('dates')!=item.get('dates'):errors.append(issue('project_time_changed',target_root))
            proposed=[]
            if field in {'projects','awards','leadership'} and isinstance(item.get('description'),str) and item['description'].strip():proposed.append((target_root+'/description',item['description']))
            for key in ('bullet_points','tech_stack'):
                values=item.get(key,[]) or []
                if isinstance(values,str):values=[values]
                proposed.extend((f'{target_root}/{key}/{j}',value) for j,value in enumerate(values) if isinstance(value,str) and value.strip())
            for path,text in proposed:align(path,text,[ref for ref,context in contexts.items() if context==root],catalog,selected,reviews,alignment,errors)
    if isinstance(target.get('skills'),dict):
        for group,values in target['skills'].items():
            if isinstance(values,str):values=[values]
            for i,text in enumerate(values or []):
                if isinstance(text,str) and text.strip():align(f'/skills/{group}/{i}',text,[ref for ref in catalog if ref.startswith('/skills/')],catalog,selected,reviews,alignment,errors)
    elif target.get('skills')!=source.get('skills'):errors.append(issue('unsupported_target_skills','/skills'))
    if not selected:errors.append(issue('no_grounded_selected_bullets'))
    plan={'selected_refs':selected,'review':{'items':reviews,'warnings':['External model-generated draft; human review required.']+[e['code']+' '+e['target_path'] for e in errors]}}
    CVPlan.model_validate(plan)
    return {'cv':doc,'catalog':catalog,'jd':jd,'source_cv':source,'original_target':target,'plan':plan,'alignment':alignment,'errors':errors,'status':'needs_review' if errors else 'automatically_checked'}


def align(path,text,refs,catalog,selected,reviews,alignment,errors):
    available=[ref for ref in refs if ref not in selected]
    exact=[ref for ref in available if catalog[ref]==text]
    candidate=None
    if len(exact)==1:candidate=exact[0]
    elif len(exact)>1:errors.append(issue('ambiguous_source_bullet',path))
    else:
        scores=sorted(((SequenceMatcher(None,norm(catalog[ref]),norm(text),autojunk=False).ratio(),ref) for ref in available),reverse=True)
        if scores and scores[0][0]>=.82 and (len(scores)==1 or scores[0][0]-scores[1][0]>=.08):candidate=scores[0][1]
        else:errors.append(issue('unaligned_target_bullet',path))
    if candidate:
        checks=rewrite_issues(catalog[candidate],text) if catalog[candidate]!=text else []
        if checks:
            errors.extend(issue(code,path) for code in checks)
            alignment.append({'target_path':path,'status':'needs_review','candidate_refs':[candidate],'issues':checks})
            return # Never promote an unsafe similarity match to a grounded source_ref.
        selected.append(candidate)
        if catalog[candidate]!=text:reviews.append({'source_ref':candidate,'original_text':catalog[candidate],'proposed_text':text,'reason':'Automatic source alignment of external model output; wording requires human review.','severity':'info'})
        alignment.append({'target_path':path,'source_ref':candidate,'status':'exact' if catalog[candidate]==text else 'automatically_checked'})
    else:alignment.append({'target_path':path,'status':'needs_review','candidate_refs':[]})


def raw_document(text,source_id):
    # Exact character spans; generic section does not assert any inferred role/company.
    pieces=[]
    for match in re.finditer(r'[^\n]+',text):
        start,end=match.span()
        while start<end:
            stop=min(end,start+1000)
            if stop<end:
                boundary=text.rfind(' ',start+200,stop)
                if boundary>start:stop=boundary
            pieces.append((start,stop));start=stop
    catalog={f'/raw_resume/spans/{start}:{end}':text[start:end] for start,end in pieces if text[start:end].strip()}
    doc=CVDocument.model_validate({'source_profile_revision_id':'external-'+source_id,'language':'en','contact':{},'sections':[{'kind':'experience','heading':'CV source text · unclassified','entries':[{'source_entry_id':'/raw_resume','title':'Original source text','bullets':[{'text':v,'source_refs':[k]} for k,v in catalog.items()]}]}]})
    return doc.model_dump(mode='json'),catalog


def normalize_record(record):
    raw=record['raw'];tailoring='iteratecv-resume-tailoring' in record['source'];ident=digest([record['source'],record['revision'],record['source_split'],record['source_index']])[:24]
    if tailoring:
        result=tailor_conversion(raw);cv,jd,catalog=result['cv'],result['jd'],result['catalog'];source_text=cv_text(result['source_cv'])
        annotation={'status':'draft','reviewer_ids':[],'source_usage_confirmed':False,'cv_usage_confirmed':False,'requirements':[],'requirement_groups':[],'cv_plan':result['plan'],'conversion_review_confirmed':False}
        conversion={k:result[k] for k in ('status','errors','alignment')};target=result['original_target'];label=None
    else:
        source_text=raw.get('resume_text',raw.get('resume'));jd=raw.get('job_description_text',raw.get('jd'));label=raw.get('label')
        if not isinstance(source_text,str) or not source_text.strip() or not isinstance(jd,str) or not jd.strip() or label not in LABELS:raise ValueError('invalid_matching_input')
        cv,catalog=raw_document(source_text,ident);target=None;conversion={'status':'automatically_checked','errors':[],'alignment':[]}
        annotation={'status':'draft','reviewer_ids':[],'source_usage_confirmed':False,'cv_usage_confirmed':False,'requirements':[],'requirement_groups':[],'cv_plan':{'selected_refs':[],'review':{'items':[],'warnings':[]}},'matching_overall_label':'','matching_rationale':'','conversion_review_confirmed':False}
    if not catalog:raise ValueError('empty_source_catalog')
    return {'pack_version':1,'split_policy':POLICY,'pair_id':ident,'split':'train','cv_identity':'pending','cv_variant':'external','jd_group':'pending','synthetic_cv':False,'task':'tailor_review' if tailoring else 'matching','job':{'posting_id':'external_'+ident,'content_hash':identity(jd),'source_url':f"https://huggingface.co/datasets/{record['source']}/tree/{record['revision']}",'fetched_at':None,'title':'IterateCV · tailoring' if tailoring else record['source'].split('/')[0]+' · matching','description':jd,'expiry_conflict':False},'cv':cv,'catalog':catalog,'annotation':annotation,'conversion':conversion,'original_target':target,'original_matching_label':label,'source_resume_text':source_text,'source_record':{k:record[k] for k in ('source','revision','source_split','source_index')},'source_record_sha256':digest(record),'label_provenance':{'kind':'model_generated' if tailoring or record['source'].startswith('med2425/') else 'undocumented','producer':'GPT-4o mini' if tailoring else 'Qwen2.5-32B' if record['source'].startswith('med2425/') else None,'prompt_version':None,'model_revision':None,'human_reviewed':False,'original_label':label},'model_annotations':None}


class Union:
    def __init__(self,n):self.parent=list(range(n))
    def root(self,i):
        while self.parent[i]!=i:self.parent[i]=self.parent[self.parent[i]];i=self.parent[i]
        return i
    def join(self,a,b):
        a,b=self.root(a),self.root(b)
        if a!=b:self.parent[max(a,b)]=min(a,b)


def shingles(text):
    words=norm(text).split();return {tuple(words[i:i+5]) for i in range(max(0,len(words)-4))}


def clustered(texts,threshold):
    """Exact hashes plus high-overlap 5-gram candidates; no short-skill identity joins."""
    union=Union(len(texts));exact={};unique=[];near=[];inverted=defaultdict(set)
    for i,text in enumerate(texts):
        key=identity(text)
        if key in exact:union.join(i,exact[key]);continue
        exact[key]=i;grams=shingles(text)
        if len(grams)<20:unique.append((i,grams));continue
        # Full inverted index makes high Jaccard candidates discoverable, unlike random signatures.
        hits=Counter(j for gram in grams for j in inverted.get(gram,()))
        for j,intersection in hits.items():
            other=unique[j][1]
            if intersection/(len(grams)+len(other)-intersection)>=threshold:
                union.join(i,unique[j][0]);near.append([i,unique[j][0]])
        position=len(unique);unique.append((i,grams))
        for gram in grams:inverted[gram].add(position)
    grouped=defaultdict(list)
    for i in range(len(texts)):grouped[union.root(i)].append(identity(texts[i]))
    keys={root:digest(sorted(set(values)))[:24] for root,values in grouped.items()}
    return [keys[union.root(i)] for i in range(len(texts))],near


def legacy_anchors(legacy):
    anchors=[];checks={}
    for split in ('train','validation','test'):
        path=legacy/(split+'.json')
        if not path.exists():continue
        checks[str(path)]=digest(path.read_bytes())
        for index,row in enumerate(json.loads(path.read_text())):
            try:cv,jd,_=parse_iterate(row)
            except (ValueError,KeyError,TypeError):continue
            anchors.append({'cv':cv_text(cv),'jd':jd,'origin':'legacy_raw','published_split':split,'index':index})
    prepared=legacy.parent/'splits'
    for split in ('train','validation','test'):
        path=prepared/(split+'.json')
        if not path.exists():continue
        checks[str(path)]=digest(path.read_bytes())
        for index,row in enumerate(json.loads(path.read_text())):
            try:
                user=next(m['content'] for m in row.get('messages',row.get('prompt',[])) if m['role']=='user');payload=json.loads(user)
                anchors.append({'cv':cv_text(payload['original_cv']),'jd':payload['job_description'],'origin':'legacy_prepared','published_split':split,'index':index})
            except (ValueError,KeyError,TypeError,StopIteration):continue
    # Existing TopCV packets are immutable comparison anchors, never research training inputs.
    pack=legacy.parent/'processed/topcv-tech-review-v1'
    for split in ('train','validation','test'):
        path=pack/(split+'.jsonl')
        if not path.exists():continue
        checks[str(path)]=digest(path.read_bytes())
        for index,line in enumerate(path.read_text().splitlines()):
            row=json.loads(line);anchors.append({'cv':cv_text(row['cv']),'jd':row['job']['description'],'origin':'topcv_existing','published_split':split,'index':index})
    return anchors,checks


def assign_groups(packets,anchors):
    cvs=[p['source_resume_text'] for p in packets]+[a['cv'] for a in anchors];jds=[p['job']['description'] for p in packets]+[a['jd'] for a in anchors]
    cvgroups,cvnear=clustered(cvs,.90);jdgroups,jdnear=clustered(jds,.85)
    union=Union(len(cvs));seen={}
    for i,(cv,jd) in enumerate(zip(cvgroups,jdgroups)):
        for key in ('cv:'+cv,'jd:'+jd):
            if key in seen:union.join(i,seen[key])
            else:seen[key]=i
    components=defaultdict(list)
    for i in range(len(cvs)):components[union.root(i)].append(i)
    component_ids={root:digest(sorted({cvgroups[i]+':'+jdgroups[i] for i in members})) for root,members in components.items()}
    assignments={}
    # Assign whole connected components. Balance by size; do not split a giant component to fake held-out data.
    counts=Counter();total=len(packets)
    for root,members in sorted(components.items(),key=lambda item:(-sum(i<len(packets) for i in item[1]),component_ids[item[0]])):
        weight=sum(i<len(packets) for i in members)
        if not weight:continue
        fold=min(('train','validation','test'),key=lambda s:counts[s]/({'train':.8,'validation':.1,'test':.1}[s]*max(total,1)))
        assignments[root]=fold;counts[fold]+=weight
    for i,p in enumerate(packets):p.update(cv_identity='cvg_'+cvgroups[i],jd_group='jdg_'+jdgroups[i],split=assignments[union.root(i)],research_component=component_ids[union.root(i)][:24])
    old_folds=defaultdict(set);origin_folds=defaultdict(set)
    for i,a in enumerate(anchors,len(packets)):
        old_folds[union.root(i)].add(a['published_split']);origin_folds[union.root(i),a['origin']].add(a['published_split'])
    anchor_pairs={(cvgroups[i],jdgroups[i]) for i in range(len(packets),len(cvs))}
    cross_cv=defaultdict(set);cross_jd=defaultdict(set)
    for i,p in enumerate(packets):
        cross_cv[cvgroups[i]].add(p['source_record']['source']);cross_jd[jdgroups[i]].add(p['source_record']['source'])
    return {'comparison_anchor_rows':len(anchors),'legacy_pair_reused':sum((cvgroups[i],jdgroups[i]) in anchor_pairs for i in range(len(packets))),
            'cross_source_cv_groups':sum(len(v)>1 for v in cross_cv.values()),'cross_source_jd_groups':sum(len(v)>1 for v in cross_jd.values()),'cv_near_duplicate_links':len(cvnear),'jd_near_duplicate_links':len(jdnear),'connected_components':len(assignments),'component_sizes':sorted([sum(i<len(packets) for i in components[r]) for r in assignments],reverse=True),'splits':dict(counts),'legacy_components_cross_published_splits':sum(len(v)>1 for (root,origin),v in origin_folds.items() if origin=='legacy_raw'),'legacy_prepared_cross_split_components':sum(len(v)>1 for (root,origin),v in origin_folds.items() if origin=='legacy_prepared'),'legacy_cross_version_fold_conflicts':sum(len(v)>1 for v in old_folds.values()),'coverage':'Selected survey rows plus local anchors only; full upstream corpora and unobserved aliases are not certified leak-free','new_rows_linked_to_legacy':sum(any(i>=len(packets) for i in components[union.root(j)]) for j in range(len(packets))),'cv_identity_limitations':'Content identity and high-overlap 5-grams; unobserved aliases/semantic paraphrases are not guaranteed. No person identity is asserted.'}


def redacted_examples(packets):
    """Only allow generic vocabulary/technology names; never export unknown name tokens."""
    generic=set('a an the and or for to of in on with using by from into both back sources applying transformations data large scale pipelines applications tooling like production setting revenues commissions expenses ensure they are recorded appropriately monthly basis analyzed analyze record recorded built developed used experience worked knowledge skills reports reporting financial accounts transactions managing managed assisted supported implemented created'.split())
    allowed=generic|{term.casefold() for term in TECHNOLOGIES}|{'api','apis','rest','my'}
    def redact(text):
        text=re.sub(r'https?://\S+|[\w.+-]+@[\w.-]+','[CONTACT]',text)
        text=re.sub(r'\d+(?:[.,]\d+)?','[NUMBER]',text)
        return re.sub(r'[\w.+#-]+',lambda m:m.group() if m.group().casefold() in allowed or m.group() in {'CONTACT','NUMBER'} else '[REDACTED]',text)
    examples=[];seen=set()
    for packet in packets:
        for item in packet['annotation']['cv_plan']['review']['items']:
            pair=(redact(item['original_text']),redact(item['proposed_text']))
            if pair in seen or len(pair[0])>300:continue
            seen.add(pair);examples.append({'pair_id':packet['pair_id'],'source_ref':item['source_ref'],'original_redacted':pair[0],'proposed_redacted':pair[1],'state':'automatically_checked_draft_not_human_approved'})
            if len(examples)==2:break
        if len(examples)==2:break
    for packet in packets:
        for a in packet['conversion']['alignment']:
            if 'technology_added_or_removed' not in a.get('issues',[]) or not a.get('candidate_refs'):continue
            target=packet['original_target']
            for part in a['target_path'].strip('/').split('/'):target=target[int(part)] if isinstance(target,list) else target[part]
            ref=a['candidate_refs'][0]
            examples.append({'pair_id':packet['pair_id'],'candidate_ref_not_approved':ref,'original_redacted':redact(packet['catalog'][ref]),'proposed_redacted':redact(target),'state':'rejected_alignment_requires_human_review','issues':a['issues']})
            return examples
    return examples


def convert(survey,output,legacy,limit=None):
    if output.exists() and not (output/'checkpoint.json').exists():raise ValueError('Output exists without matching checkpoint; use a new output')
    output.mkdir(parents=True,exist_ok=True);records=[];source_checks={}
    for path in sorted(survey.glob('*/samples.jsonl')):
        manifest=json.loads((path.parent/'manifest.json').read_text())
        if digest(path.read_bytes())!=manifest['samples_sha256']:raise ValueError('Survey checksum mismatch')
        source_checks[str(path)]=digest(path.read_bytes());records.extend(json.loads(line) for line in path.read_text().splitlines() if line.strip())
    # Pilot traverses both branches, not the first N tailoring records.
    records=sorted(records,key=lambda r:digest([r['source'],r['source_split'],r['source_index']]))
    if limit:records=records[:limit]
    anchors,legacy_checks=legacy_anchors(legacy)
    fingerprint=digest([VERSION,source_checks,legacy_checks,limit]);checkpoint_path=output/'checkpoint.json'
    checkpoint=json.loads(checkpoint_path.read_text()) if checkpoint_path.exists() else {'version':VERSION,'fingerprint':fingerprint,'results':{},'errors':{}}
    if checkpoint['fingerprint']!=fingerprint:raise ValueError('Conversion inputs changed; use a new output')
    for record in records:
        key=digest(record)
        if key in checkpoint['results'] or key in checkpoint['errors']:continue
        try:checkpoint['results'][key]=normalize_record(record)
        except (ValueError,TypeError,KeyError,IndexError):checkpoint['errors'][key]={'source':record['source'],'source_split':record['source_split'],'source_index':record['source_index'],'code':'source_schema_or_grounding_conversion_failed'}
        atomic(checkpoint_path,checkpoint)
    packets=list(checkpoint['results'].values());group_report=assign_groups(packets,anchors)
    # Duplicate pairs from different sources retain both original labels in a provenance ledger.
    unique={};duplicates=[]
    for packet in packets:
        key=(packet['task'],packet['cv_identity'],packet['jd_group'])
        if key in unique:
            kept=unique[key];duplicates.append({'removed_pair_id':packet['pair_id'],'kept_pair_id':kept['pair_id'],'source_record':packet['source_record'],'original_matching_label':packet['original_matching_label']})
            kept.setdefault('duplicate_sources',[]).append({'source_record':packet['source_record'],'original_matching_label':packet['original_matching_label'],'source_record_sha256':packet['source_record_sha256']})
            if packet['original_matching_label']!=kept['original_matching_label']:kept['conversion']['errors'].append(issue('conflicting_duplicate_labels'));kept['conversion']['status']='needs_review'
        else:unique[key]=packet
    packets=list(unique.values());assert_isolated(packets)
    errors=Counter(e['code'] for p in packets for e in p['conversion']['errors'])
    branches={}
    for task,folder_name in [('tailor_review','tailoring'),('matching','matching')]:
        branch=output/folder_name;branch.mkdir(exist_ok=True);selected=[p for p in packets if p['task']==task];checks={}
        for split in ('train','validation','test'):
            data=''.join(json.dumps(p,ensure_ascii=False)+'\n' for p in selected if p['split']==split)
            path=branch/(split+'.jsonl')
            if path.exists() and path.read_text()!=data:raise ValueError('Completed packet file differs; refusing overwrite')
            if not path.exists():path.write_text(data)
            checks[path.name]=digest(data.encode())
        cohort=[p['pair_id'] for p in sorted(selected,key=lambda p:(p['split']!='train',p['pair_id']))[:10]]
        atomic(branch/'manifest.json',{'pack_version':1,'task':task,'pipeline_version':VERSION,'split_policy':POLICY,'checksums':checks,'review_cohort':cohort,'packets':len(selected),'splits':dict(Counter(p['split'] for p in selected)),'source_checksums':source_checks,'legacy_checksums':legacy_checks,'training_ready':False,'blockers':['Independent human review missing','Source reuse/training rights and real-CV consent unverified','Not an independent human-labeled evaluation set'],'provenance':'External dataset labels; automatic checks are not human approval.'})
        branches[task]={'pack':str(branch),'samples':len(selected),'automatically_checked':sum(p['conversion']['status']=='automatically_checked' for p in selected),'needs_review':sum(p['conversion']['status']=='needs_review' for p in selected),'all_require_human_review':True,'draft_plan_candidates':sum(bool(p['annotation']['cv_plan']['selected_refs']) for p in selected) if task=='tailor_review' else 0,'automatic_checks_scope':'bullet alignment and conservative source guards' if task=='tailor_review' else 'schema and original-label preservation only; label correctness not validated','splits':dict(Counter(p['split'] for p in selected)),'original_labels':dict(Counter(p['original_matching_label'] for p in selected if p['original_matching_label']))}
    report={'pipeline_version':VERSION,'input_samples':len(records),'converted':len(checkpoint['results']),'duplicates_removed':len(duplicates),'rejected':len(checkpoint['errors']),'branches':branches,'issue_counts':dict(errors),'alignment_counts':dict(Counter(a['status'] for p in packets for a in p['conversion']['alignment'])),'group_audit':group_report,'training_started':False,'adapter_enabled':False,'approved':0,'source_usage_confirmed':0,'source_checksums':source_checks,'legacy_checksums':legacy_checks}
    atomic(output/'examples-redacted.json',redacted_examples(packets))
    atomic(output/'duplicates.json',duplicates);atomic(output/'errors.json',list(checkpoint['errors'].values()));atomic(output/'report.json',report)
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--survey',type=Path,default=Path('ai/data/raw/hf-research-survey-v1'));p.add_argument('--output',type=Path,required=True);p.add_argument('--legacy',type=Path,default=Path('ai/data/raw'));p.add_argument('--limit',type=int);args=p.parse_args();convert(args.survey,args.output,args.legacy,args.limit)

if __name__=='__main__':main()
