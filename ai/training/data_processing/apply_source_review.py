"""Áp dụng quyết định giữ hoặc loại 35 mẫu đã duyệt."""
from copy import deepcopy
import hashlib
import json
import re

from .clean_data import assert_source_only, changed_paths
from .prepare_data import schema_errors


def checksum(record):
    content = json.dumps(record, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(content.encode()).hexdigest()


def normalize_reviewed_cv(cv):
    """Chuẩn hóa giá trị thiếu trong metadata; không sửa câu kinh nghiệm."""
    result = deepcopy(cv)
    for section in ['experience', 'education', 'awards', 'leadership']:
        for item in result[section]:
            for field in ['company', 'institution', 'organization', 'dates', 'degree', 'issuer', 'year']:
                value = item.get(field)
                if not isinstance(value, str):
                    continue
                missing = value.strip().casefold() in {
                    'unknown', 'company not specified', 'institution not specified',
                    'expected in', 'expected in --', 'na', 'n/a',
                }
                # Ngày bị che không đủ để khẳng định năm; bản gốc vẫn ở candidates.
                masked_date = field == 'dates' and bool(re.search('XXX', value, re.I))
                if missing or masked_date:
                    item[field] = None
    # Hai mẫu civil engineering bị đặt tên lĩnh vực vào nhóm ngôn ngữ.
    languages = result['skills']['languages']
    if 'Civil Engineering' in languages:
        result['skills']['languages'] = [
            language
            for language in languages
            if language != 'Civil Engineering'
        ]
        if 'Civil Engineering' not in result['skills']['domain_skills']:
            result['skills']['domain_skills'].append('Civil Engineering')
    return result


def apply_reviews(records, reviews):
    records_by_id = {record['sample_id']: record for record in records}
    decisions_by_id = {review['sample_id']: review for review in reviews}

    if len(records_by_id) != len(records) or len(decisions_by_id) != len(reviews):
        raise ValueError('Duplicate IDs')

    flagged_ids = {
        record['sample_id']
        for record in records
        if record['review_reasons']
    }
    if set(decisions_by_id) != flagged_ids:
        raise ValueError('Review decisions must cover exactly the flagged source records')

    selected_records = []
    excluded_records = []
    review_changes = []

    for record in records:
        decision = decisions_by_id.get(record['sample_id'])
        if decision is None:
            selected_records.append(deepcopy(record))
            continue

        if checksum(record) != decision['record_sha256']:
            raise ValueError(f'Stale review: {record["sample_id"]}')

        action = decision['recommendation']
        if action == 'exclude_until_repaired':
            excluded_records.append({
                'sample_id': record['sample_id'],
                'reason': decision['reason'],
                'category': decision['category'],
                'record_sha256': checksum(record),
            })
            continue
        if action != 'retain_with_constraints':
            raise ValueError(f'Unknown review action: {action}')

        edited = deepcopy(record)
        for field in ['original_cv', 'target_cv']:
            edited[field] = normalize_reviewed_cv(edited[field])
            if schema_errors(edited[field]):
                raise ValueError(f'Invalid edited schema: {record["sample_id"]}')
        assert_source_only(edited['original_cv'], edited['target_cv'])
        edited['source_cv_sha256'] = checksum(edited['original_cv'])
        edited['source_review'] = {
            'decision': action,
            'reason': decision['reason'],
            'scope': 'source_metadata_only',
            'training_ready': False,
        }
        edited['resolved_review_reasons'] = edited['review_reasons']
        edited['review_reasons'] = []
        edited['review_status'] = 'source_reviewed_with_constraints'
        # Duyệt nguồn không đồng nghĩa duyệt đáp án viết lại cho mục tiêu QLoRA.
        edited['requires_manual_review'] = True
        selected_records.append(edited)
        review_changes.append({
            'sample_id': record['sample_id'],
            'original_cv_changed_paths': changed_paths(
                record['original_cv'],
                edited['original_cv'],
                'original_cv',
            ),
            'target_cv_changed_paths': changed_paths(
                record['target_cv'],
                edited['target_cv'],
            ),
            'accepted_constraints': decision['reason'],
            'input_record_sha256': checksum(record),
        })

    return selected_records, excluded_records, review_changes


