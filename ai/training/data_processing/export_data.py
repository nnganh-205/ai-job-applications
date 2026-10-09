"""Gom nhóm CV, chia tập và xuất prompt/completion cho Qwen."""

from collections import defaultdict
import hashlib
from itertools import combinations
import json
import random
import re

from .clean_data import assert_source_only
from .data_io import write_json
from .prepare_data import schema_errors
from .rewrite_data import METHOD, validate_rewritten_record

SYSTEM = (
    'Tailor the resume to the job description using only facts in original_cv and user_info. '
    'Prioritize relevant skills and bullet points. Do not invent skills, responsibilities, '
    'achievements, numbers, employers, job titles, dates or qualifications. '
    'Keep missing facts null and preserve incomplete education status. '
    'Return only valid JSON using the original CV schema.'
)


def calculate_fingerprint(value):
    """Tạo mã cố định để so sánh hai nội dung JSON."""
    content = json.dumps(value, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(content.encode()).hexdigest()


def normalize_group_value(value):
    """Chuẩn hóa tên công ty, trường và chức danh trước khi gom nhóm."""
    return re.sub(r'[^\w]+', ' ', value.casefold()).strip() if isinstance(value, str) else ''


def grouping_keys(cv):
    """Gom bản giống nhau và biến thể có ít nhất hai dấu mốc chung."""
    invalid_companies = {'', 'unknown', 'na', 'company not specified'}
    job_anchors = set()
    for experience in cv['experience']:
        company = normalize_group_value(experience['company'])
        title = normalize_group_value(experience['title'])
        if company not in invalid_companies:
            job_anchors.add((company, title))

    yield ('exact', calculate_fingerprint(cv))
    for pair in combinations(sorted(job_anchors), 2):
        yield ('two_jobs', pair)

    invalid_schools = {'', 'unknown', 'institution not specified'}
    schools = set()
    for education in cv['education']:
        school = normalize_group_value(education['institution'])
        if school not in invalid_schools:
            schools.add(school)

    # Hai trường và cùng một chức danh giúp nhận ra biến thể đổi tên công ty.
    roles = {
        normalize_group_value(experience['title'])
        for experience in cv['experience']
        if normalize_group_value(experience['title'])
    }
    for school_pair in combinations(sorted(schools), 2):
        for role in roles:
            yield ('two_schools_role', school_pair, role)


def assign_groups(records):
    # Mỗi bản ghi ban đầu là một nhóm riêng. Nếu có cùng dấu mốc, hai nhóm được nối lại.
    parent_indexes = list(range(len(records)))

    def find_group(index):
        while parent_indexes[index] != index:
            parent_indexes[index] = parent_indexes[parent_indexes[index]]
            index = parent_indexes[index]
        return index

    first_index_by_key = {}
    for index, record in enumerate(records):
        for group_key in grouping_keys(record['original_cv']):
            if group_key in first_index_by_key:
                current_group = find_group(index)
                existing_group = find_group(first_index_by_key[group_key])
                parent_indexes[current_group] = existing_group
            else:
                first_index_by_key[group_key] = index

    records_by_group = defaultdict(list)
    for index, record in enumerate(records):
        group_index = find_group(index)
        records_by_group[group_index].append(record)

    groups = {}
    for group_records in records_by_group.values():
        sample_ids = sorted(record['sample_id'] for record in group_records)
        group_id = calculate_fingerprint(sample_ids)[:16]
        groups[group_id] = group_records
    return groups


def split_records(records, seed=42):
    groups = assign_groups(records)
    group_items = sorted(groups.items())
    random.Random(seed).shuffle(group_items)
    # Đưa nhóm lớn trước để giới hạn lệch tỉ lệ; tie giữ thứ tự theo seed.
    group_items.sort(key=lambda item: len(item[1]), reverse=True)

    ratios = {'train': 0.8, 'validation': 0.1, 'test': 0.1}
    splits = {name: [] for name in ratios}
    assignments = []

    for group_id, group_records in group_items:
        selected_split = min(
            ratios,
            key=lambda name: len(splits[name]) / (ratios[name] * len(records)),
        )
        splits[selected_split].extend(group_records)
        for record in group_records:
            assignments.append({
                'sample_id': record['sample_id'],
                'group_id': group_id,
                'split': selected_split,
                'source_split': record['source_split'],
            })
    return splits, assignments


def to_training_row(record):
    user_content = {
        'user_info': {},
        'original_cv': record['original_cv'],
        'job_description': record['job_description'],
    }
    return {
        'prompt': [
            {'role': 'system', 'content': SYSTEM},
            {'role': 'user', 'content': json.dumps(user_content, ensure_ascii=False)},
        ],
        'completion': [{
            'role': 'assistant',
            'content': json.dumps(record['target_cv'], ensure_ascii=False),
        }],
    }


def export(records, output_dir, seed=42):
    sample_ids = {record['sample_id'] for record in records}
    if not records or len(sample_ids) != len(records):
        raise ValueError('Empty dataset or duplicate sample IDs')

    for record in records:
        for field in ['original_cv', 'target_cv']:
            if schema_errors(record[field]):
                raise ValueError(f'Invalid schema: {record["sample_id"]}')
        if not isinstance(record['job_description'], str) or not record['job_description'].strip():
            raise ValueError('Missing JD')
        if record.get('cleaning_method') == METHOD:
            validate_rewritten_record(record)
        else:
            assert_source_only(record['original_cv'], record['target_cv'])
    # Cùng CV+JD chỉ giữ một mẫu nếu đáp án giống nhau; khác nhau phải duyệt.
    first_record_by_pair = {}
    unique_records = []
    duplicate_pairs = []
    for record in records:
        pair_fingerprint = calculate_fingerprint([
            record['original_cv'],
            record['job_description'],
        ])
        if pair_fingerprint in first_record_by_pair:
            first_record = first_record_by_pair[pair_fingerprint]
            if first_record['target_cv'] != record['target_cv']:
                raise ValueError(
                    f'Conflicting pair: {first_record["sample_id"]}/{record["sample_id"]}'
                )
            duplicate_pairs.append({
                'removed_id': record['sample_id'],
                'retained_id': first_record['sample_id'],
            })
        else:
            first_record_by_pair[pair_fingerprint] = record
            unique_records.append(record)

    splits, assignments = split_records(unique_records, seed)
    output_dir.mkdir(parents=True, exist_ok=True)
    checksums = {}
    for name, rows in splits.items():
        training_rows = [to_training_row(record) for record in rows]
        checksums[name] = write_json(output_dir / f'{name}.json', training_rows)
    write_json(output_dir / 'assignments.json', assignments)
    duplicate_path = output_dir / 'duplicate_pairs.json'
    if duplicate_pairs:
        write_json(duplicate_path, duplicate_pairs)
    elif duplicate_path.exists():
        duplicate_path.unlink()
    group_splits = defaultdict(set)
    for item in assignments:
        group_splits[item['group_id']].add(item['split'])
    if any(len(names)>1 for names in group_splits.values()):
        raise ValueError('Group leakage')
    all_rewritten = all(record.get('cleaning_method') == METHOD for record in records)
    purpose = 'Grounded editorial rewriting' if all_rewritten else 'Source-only reordering baseline'
    report = {
        'input_samples': len(records),
        'exported_samples': len(unique_records),
        'duplicate_pairs_removed': len(duplicate_pairs),
        'split_counts': {name: len(rows) for name, rows in splits.items()},
        'cv_groups': len(group_splits),
        'cross_split_group_overlap': 0,
        'seed': seed,
        'sha256': checksums,
        'input_sha256': calculate_fingerprint(records),
        'purpose': purpose,
        'limitations': [
            'Grouping is heuristic; candidate identity is unavailable and cannot be guaranteed.',
            'Rewrites are rule-validated, not manually approved for semantic quality.',
            'user_info is empty; additional user information behavior is not trained.',
            'Token lengths depend on chosen Qwen tokenizer and have not been checked.',
        ],
    }
    write_json(output_dir / 'export_report.json', report)
    return report


