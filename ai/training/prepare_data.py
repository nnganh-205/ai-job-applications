"""Audit existing datasets, or export reviewed CVPlan examples without changing sources.

Input may contain messages, or legacy prompt/completion messages. Legacy targets
are counted but never silently rewritten to the runtime contract.
"""

import argparse
import hashlib
import json
from pathlib import Path

from backend.app.schemas.cv import CVPlan


def load_rows(path):
    text = Path(path).read_text(encoding='utf-8')
    return json.loads(text) if text.lstrip().startswith('[') else [json.loads(line) for line in text.splitlines() if line.strip()]


def messages_for(row):
    if isinstance(row.get('messages'), list):
        return row['messages']
    if isinstance(row.get('prompt'), list) and isinstance(row.get('completion'), list):
        return row['prompt'] + row['completion']
    if all(isinstance(row.get(key), str) for key in ('instruction', 'input', 'output')):
        return [{'role': 'system', 'content': row['instruction']}, {'role': 'user', 'content': row['input']}, {'role': 'assistant', 'content': row['output']}]
    raise ValueError('Unsupported message structure')


def validate_example(row):
    messages = messages_for(row)
    if [m.get('role') for m in messages] != ['system', 'user', 'assistant'] or not all(isinstance(m.get('content'), str) and m['content'].strip() for m in messages):
        raise ValueError('Expected system/user/assistant messages')
    payload = json.loads(messages[1]['content'])
    catalog = payload['catalog']
    if not isinstance(catalog, dict) or not catalog or not all(isinstance(k, str) and isinstance(v, str) for k, v in catalog.items()):
        raise ValueError('Expected grounded source catalog')
    plan = CVPlan.model_validate_json(messages[-1]['content'])
    if row.get('prompt_version')=='cv-review-v4' and (len(plan.review.items)>5 or set(payload.get('catalog_context',{}))!=set(catalog)):
        raise ValueError('CV prompt v4 requires entry contexts and at most five edits')
    if len(set(plan.selected_refs))!=len(plan.selected_refs):raise ValueError('Duplicate selected refs')
    if not plan.selected_refs or any(ref not in catalog for ref in plan.selected_refs):
        raise ValueError('Unsupported selected refs')
    if len({item.source_ref for item in plan.review.items})!=len(plan.review.items) or any(item.source_ref not in plan.selected_refs or item.original_text != catalog.get(item.source_ref) or not item.reason.strip() for item in plan.review.items):
        raise ValueError('Unsupported review source')
    from ai.agents.cv_grounding import grounded_rewrite as review_text_valid
    if any(not review_text_valid(item.original_text, item.proposed_text) for item in plan.review.items):
        raise ValueError('Review failed source/factual guard')
    group = hashlib.sha256(json.dumps(catalog, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    if row.get('split_policy')=='cv-identity-and-jd-group-v1':
        if row.get('split') not in {'train','validation','test'} or not row.get('cv_identity') or not row.get('jd_group'):
            raise ValueError('Missing grouped split metadata')
        if row.get('review_status')!='approved' or not row.get('reviewer_ids') or row.get('source_usage_confirmed') is not True:
            raise ValueError('Reviewed source approval required')
        return {**{key:row[key] for key in ('split_policy','split','cv_identity','jd_group','review_status','reviewer_ids','source_usage_confirmed')},
                'contract':'cv-plan-v1','group_id':row['cv_identity'],'messages':messages,
                **{k:row[k] for k in ('prompt_version','source_hash','pair_id','synthetic_cv','cv_usage_confirmed','source_record','source_record_sha256','label_provenance','guard_version','cleaning_provenance','corpus_registry') if k in row}}
    bucket = int(group[:8], 16) % 10
    return {'contract': 'cv-plan-v1', 'group_id': group, 'split': 'test' if bucket == 0 else 'validation' if bucket == 1 else 'train', 'messages': messages}


def prepare(rows):
    accepted, seen = [], set()
    report = {'input': len(rows), 'compatible': 0, 'incompatible': 0, 'duplicates': 0}
    for row in rows:
        try:
            record = validate_example(row)
        except (ValueError, TypeError, KeyError, AttributeError):
            report['incompatible'] += 1
            continue
        digest = hashlib.sha256(json.dumps(record['messages'], sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        if digest in seen:
            report['duplicates'] += 1
            continue
        seen.add(digest)
        accepted.append(record)
        report['compatible'] += 1
    grouped=[row for row in accepted if row.get('split_policy')=='cv-identity-and-jd-group-v1']
    if grouped:
        from ai.training.review_pack import assert_isolated
        assert_isolated(grouped)
    report['splits'] = {name: sum(record['split'] == name for record in accepted) for name in ('train', 'validation', 'test')}
    return accepted, report


def audit_review_pack(path):
    """Audit draft contracts without impersonating human approval or granting rights."""
    from collections import Counter
    from ai.training.review_pack import load_verified
    from backend.app.schemas.cv import CVDocument
    from ai.agents.cv_agent import review_text_valid
    manifest,packets=load_verified(path);candidates=0;issues=[]
    for key,packet in packets.items():
        doc=CVDocument.model_validate(packet['cv'])
        visible={b.source_refs[0]:b.text for section in doc.sections for entry in section.entries for b in entry.bullets}
        if packet['catalog']!=visible:raise ValueError('Catalog differs from exact visible source bullets')
        if packet.get('task')=='matching':
            if packet.get('original_matching_label') not in {'Good Fit','Potential Fit','No Fit'}:raise ValueError('Invalid original matching label')
            continue
        try:
            plan=CVPlan.model_validate(packet['annotation']['cv_plan'])
            if not plan.selected_refs or len(set(plan.selected_refs))!=len(plan.selected_refs) or any(ref not in visible for ref in plan.selected_refs):raise ValueError('invalid_selection')
            if any(item.source_ref not in plan.selected_refs or item.original_text!=visible.get(item.source_ref) or not item.reason.strip() or not review_text_valid(item.original_text,item.proposed_text) for item in plan.review.items):raise ValueError('invalid_rewrite')
        except (ValueError,KeyError,TypeError):issues.append({'pair_id':key,'code':'candidate_plan_requires_manual_construction'})
        else:candidates+=1
    clean_pairs=[pair for p in packets.values() for pair in p.get('cleaning',{}).get('pairs',[])]
    return {'cleaning_pair_states':dict(Counter(pair['status'] for pair in clean_pairs)),'samples':len(packets),'task':manifest.get('task','tailor_review'),'schema_source_checked':True,
            'draft_plan_candidates':candidates,'candidate_plan_issues':issues,
            'automatic_states':dict(Counter(p.get('conversion',{}).get('status','pending') for p in packets.values())),
            'human_approved':sum(p['annotation'].get('status')=='approved' for p in packets.values()),
            'splits':dict(Counter(p['split'] for p in packets.values())),
            'training_ready':False,'training_started':False,
            'limitations':'Automatic source/contract checks only; rights, semantic correctness and independent human evaluation remain required.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    inputs=parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument('--input')
    inputs.add_argument('--pack',help='Audit a source-pinned reviewer pack without exporting drafts')
    parser.add_argument('--output', help='New JSONL file; omitted means audit only')
    args = parser.parse_args()
    if args.pack:
        if args.output:parser.error('Use export_reviewed after human approval; pack audit cannot export drafts')
        print(json.dumps(audit_review_pack(args.pack)));return
    records, report = prepare(load_rows(args.input))
    print(json.dumps(report))
    if args.output:
        if report['incompatible'] or not records:
            raise SystemExit('Export refused: curate schema-compatible grounded examples first. Source dataset was not modified.')
        with Path(args.output).open('x', encoding='utf-8') as stream:
            for record in records: stream.write(json.dumps(record, ensure_ascii=False) + '\n')


if __name__ == '__main__': main()
