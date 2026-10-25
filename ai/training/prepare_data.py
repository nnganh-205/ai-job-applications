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
    if not plan.selected_refs or any(ref not in catalog for ref in plan.selected_refs):
        raise ValueError('Unsupported selected refs')
    if any(item.source_ref not in catalog or item.original_text != catalog[item.source_ref] for item in plan.review.items):
        raise ValueError('Unsupported review source')
    from backend.app.ai.agents.cv_agent import review_text_valid
    if any(not review_text_valid(item.original_text, item.proposed_text) for item in plan.review.items):
        raise ValueError('Review changed numbers/negation')
    group = hashlib.sha256(json.dumps(catalog, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
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
    report['splits'] = {name: sum(record['split'] == name for record in accepted) for name in ('train', 'validation', 'test')}
    return accepted, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True)
    parser.add_argument('--output', help='New JSONL file; omitted means audit only')
    args = parser.parse_args()
    records, report = prepare(load_rows(args.input))
    print(json.dumps(report))
    if args.output:
        if report['incompatible'] or not records:
            raise SystemExit('Export refused: curate schema-compatible grounded examples first. Source dataset was not modified.')
        with Path(args.output).open('x', encoding='utf-8') as stream:
            for record in records: stream.write(json.dumps(record, ensure_ascii=False) + '\n')


if __name__ == '__main__': main()
