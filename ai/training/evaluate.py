"""Offline metrics for real generated CVPlan predictions; no LLM calls or training.

Each JSONL row: {prediction: JSON string, reference: CVPlan dict, catalog: {ref: text}}.
Run on identical held-out inputs for base and adapter. No semantic accuracy claim.
"""

import argparse
import json

from ai.training.prepare_data import load_rows
from backend.app.schemas.cv import CVPlan


def evaluate(rows):
    valid, grounded, scores = 0, 0, []
    if not rows: raise ValueError('No predictions to evaluate')
    for row in rows:
        target = CVPlan.model_validate(row['reference'])
        catalog = row['catalog']
        try: prediction = CVPlan.model_validate_json(row['prediction'])
        except (ValueError, TypeError):
            scores.append(0.0)
            continue
        valid += 1
        refs = set(prediction.selected_refs)
        grounded += bool(refs) and refs <= set(catalog) and all(item.source_ref in catalog and item.original_text == catalog[item.source_ref] for item in prediction.review.items)
        expected = set(target.selected_refs)
        scores.append(2 * len(refs & expected) / (len(refs) + len(expected)) if refs or expected else 1.0)
    return {'samples': len(rows), 'schema_validity': valid / len(rows), 'grounded_selection_rate': grounded / len(rows),
            'mean_selection_f1': sum(scores) / len(scores), 'limitations': 'Source/selection checks only; rewritten factual preservation requires human evaluation.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--predictions', required=True)
    args = parser.parse_args()
    print(json.dumps(evaluate(load_rows(args.predictions))))


if __name__ == '__main__': main()
