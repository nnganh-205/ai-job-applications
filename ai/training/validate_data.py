"""Kiểm tra chất lượng dataset CV và xuất báo cáo PASS/REVIEW/FAIL."""

import argparse
from collections import Counter, defaultdict
import csv
from difflib import SequenceMatcher
import hashlib
from itertools import combinations
import json
from pathlib import Path
import re

from tqdm import tqdm

from .prepare_data import DEFAULT_DATA_DIR, VALID_SPLITS, load_split


PERSONAL_FIELDS = {'name', 'email', 'phone', 'location', 'links'}
SKILL_GROUPS = {'languages', 'frameworks', 'tools', 'domain_skills'}
SECTION_SCHEMAS = {
    'experience': {
        'title': str,
        'company': str,
        'dates': str,
        'bullet_points': list,
    },
    'projects': {
        'title': str,
        'tech_stack': list,
        'description': str,
        'bullet_points': list,
    },
    'education': {
        'degree': str,
        'institution': str,
        'dates': str,
    },
    'awards': {
        'title': str,
        'year': str,
        'issuer': str,
        'description': str,
    },
    'leadership': {
        'role': str,
        'organization': str,
        'dates': str,
    },
}
CSV_FIELDS = [
    'sample_id',
    'split',
    'status',
    'reasons',
    'json_valid',
    'schema_valid',
    'immutable_valid',
    'template_summary',
    'unsupported_skills',
]


def is_text_or_none(value) -> bool:
    return value is None or isinstance(value, str)


def validate_cv_schema(cv, cv_name: str = 'cv') -> list[str]:
    """Kiểm tra đầy đủ các trường và kiểu dữ liệu trong CV lồng nhau."""
    if not isinstance(cv, dict):
        return [f'{cv_name} phải là object']

    expected_root_fields = {
        'personal_info',
        'summary',
        'skills',
        *SECTION_SCHEMAS,
    }
    errors = []
    if set(cv) != expected_root_fields:
        missing = sorted(expected_root_fields - set(cv))
        extra = sorted(set(cv) - expected_root_fields)
        errors.append(f'{cv_name} sai root fields: missing={missing}, extra={extra}')

    if not is_text_or_none(cv.get('summary')):
        errors.append(f'{cv_name}.summary phải là text hoặc null')

    personal_info = cv.get('personal_info')
    if not isinstance(personal_info, dict) or set(personal_info) != PERSONAL_FIELDS:
        errors.append(f'{cv_name}.personal_info sai cấu trúc')
    else:
        for field, value in personal_info.items():
            if field == 'links':
                valid_links = (
                    isinstance(value, list)
                    and all(isinstance(link, str) for link in value)
                )
                if not valid_links:
                    errors.append(f'{cv_name}.personal_info.links phải là list text')
            elif not is_text_or_none(value):
                errors.append(f'{cv_name}.personal_info.{field} sai kiểu dữ liệu')

    skills = cv.get('skills')
    if not isinstance(skills, dict) or set(skills) != SKILL_GROUPS:
        errors.append(f'{cv_name}.skills sai cấu trúc')
    else:
        for group_name, values in skills.items():
            valid_values = (
                isinstance(values, list)
                and all(isinstance(skill, str) for skill in values)
            )
            if not valid_values:
                errors.append(f'{cv_name}.skills.{group_name} phải là list text')

    for section_name, field_types in SECTION_SCHEMAS.items():
        items = cv.get(section_name)
        if not isinstance(items, list):
            errors.append(f'{cv_name}.{section_name} phải là list')
            continue

        for index, item in enumerate(items):
            item_path = f'{cv_name}.{section_name}[{index}]'
            if not isinstance(item, dict) or set(item) != set(field_types):
                errors.append(f'{item_path} sai cấu trúc')
                continue

            for field, expected_type in field_types.items():
                value = item[field]
                if expected_type is list:
                    valid_value = (
                        isinstance(value, list)
                        and all(isinstance(text, str) for text in value)
                    )
                else:
                    valid_value = is_text_or_none(value)
                if not valid_value:
                    errors.append(f'{item_path}.{field} sai kiểu dữ liệu')

    return errors


def count_items(items, fields) -> Counter:
    """Đếm các item theo những trường cần giữ nguyên, không phụ thuộc thứ tự."""
    values = []
    for item in items:
        selected_fields = {field: item.get(field) for field in fields}
        values.append(json.dumps(selected_fields, sort_keys=True, ensure_ascii=False))
    return Counter(values)


def immutable_errors(original_cv, tailored_cv) -> list[str]:
    """Kiểm tra thông tin ứng viên không được phép thay đổi theo JD."""
    errors = []

    original_personal = dict(original_cv['personal_info'])
    tailored_personal = dict(tailored_cv['personal_info'])
    original_personal['links'] = sorted(original_personal['links'])
    tailored_personal['links'] = sorted(tailored_personal['links'])
    if original_personal != tailored_personal:
        errors.append('personal_info đã thay đổi')

    experience_fields = ['title', 'company', 'dates']
    original_experience = count_items(original_cv['experience'], experience_fields)
    tailored_experience = count_items(tailored_cv['experience'], experience_fields)
    if original_experience != tailored_experience:
        errors.append('company, title hoặc dates trong experience đã thay đổi')

    education_fields = ['degree', 'institution', 'dates']
    original_education = count_items(original_cv['education'], education_fields)
    tailored_education = count_items(tailored_cv['education'], education_fields)
    if original_education != tailored_education:
        errors.append('education đã thay đổi')

    return errors


def collect_strings(value):
    """Lấy tất cả chuỗi trong một object JSON lồng nhau."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from collect_strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from collect_strings(item)


def normalize_text(value: str) -> str:
    return re.sub(r'\s+', ' ', value).strip().casefold()


def has_literal_evidence(skill: str, original_cv) -> bool:
    """Tìm bằng chứng nguyên văn; không suy diễn alias hoặc nghĩa tương đương."""
    normalized_skill = normalize_text(skill)
    source_text = normalize_text(' '.join(collect_strings(original_cv)))
    pattern = r'(?<!\w)' + re.escape(normalized_skill) + r'(?!\w)'
    return bool(re.search(pattern, source_text))


def review_skills(original_cv, tailored_cv):
    """Tìm skill mới, skill đổi nhóm và skill bị loại để đưa vào review."""
    original_groups = original_cv['skills']
    tailored_groups = tailored_cv['skills']
    original_all = {
        normalize_text(skill)
        for values in original_groups.values()
        for skill in values
    }
    unsupported_skills = []
    reasons = []

    for group_name, skills in tailored_groups.items():
        original_group = {
            normalize_text(skill)
            for skill in original_groups[group_name]
        }
        for skill in skills:
            normalized_skill = normalize_text(skill)
            if normalized_skill in original_group:
                continue
            if normalized_skill in original_all:
                reasons.append(f'Skill đổi nhóm cần review: {skill}')
            elif has_literal_evidence(skill, original_cv):
                reasons.append(
                    f'Skill mới có bằng chứng nguyên văn nhưng cần review ngữ cảnh: {skill}'
                )
            else:
                unsupported_skills.append(skill)

    tailored_all = {
        normalize_text(skill)
        for values in tailored_groups.values()
        for skill in values
    }
    removed_skills = sorted(original_all - tailored_all)
    if removed_skills:
        reasons.append(f'Có {len(removed_skills)} skill gốc bị loại cần review')
    if unsupported_skills:
        reasons.append(
            f'Có {len(unsupported_skills)} skill mới chưa có bằng chứng nguyên văn'
        )

    return unsupported_skills, reasons


def is_template_summary(summary) -> bool:
    if not isinstance(summary, str):
        return False
    normalized = summary.casefold()
    return (
        'experience in roles including' in normalized
        and 'skills include' in normalized
    )


def semantic_review_reasons(original_cv, tailored_cv) -> list[str]:
    """Đánh dấu phần viết lại mà code không thể xác minh đầy đủ về ngữ nghĩa."""
    reasons = []
    if original_cv['summary'] != tailored_cv['summary']:
        reasons.append('Summary đã viết lại, cần người kiểm tra ý nghĩa và bằng chứng')

    original_bullets = Counter()
    tailored_bullets = []
    for section_name in ['experience', 'projects']:
        for item in original_cv[section_name]:
            original_bullets.update(item['bullet_points'])
        for item in tailored_cv[section_name]:
            tailored_bullets.extend(item['bullet_points'])

    rewritten_bullet_count = 0
    available_bullets = original_bullets.copy()
    for bullet in tailored_bullets:
        if available_bullets[bullet] > 0:
            available_bullets[bullet] -= 1
        else:
            rewritten_bullet_count += 1
    if rewritten_bullet_count:
        reasons.append(
            f'{rewritten_bullet_count} bullet đã viết lại cần kiểm tra ngữ nghĩa'
        )

    return reasons


def validate_record(record):
    """Kiểm tra một mẫu và gán PASS, REVIEW hoặc FAIL."""
    result = {
        'sample_id': record['sample_id'],
        'split': record['split'],
        'status': 'PASS',
        'reasons': [],
        'json_valid': not record['parse_errors'],
        'schema_valid': False,
        'immutable_valid': False,
        'template_summary': False,
        'unsupported_skills': [],
    }

    if record['parse_errors']:
        result['status'] = 'FAIL'
        result['reasons'].extend(record['parse_errors'])
        return result

    input_errors = []
    if not isinstance(record['user_info'], dict):
        input_errors.append('user_info phải là object')
    if (
        not isinstance(record['job_description'], str)
        or not record['job_description'].strip()
    ):
        input_errors.append('job_description phải là chuỗi không rỗng')

    original_errors = validate_cv_schema(record['original_cv'], 'original_cv')
    tailored_errors = validate_cv_schema(record['tailored_cv'], 'tailored_cv')
    schema_errors = input_errors + original_errors + tailored_errors
    result['schema_valid'] = not schema_errors
    if schema_errors:
        result['status'] = 'FAIL'
        result['reasons'].extend(schema_errors)
        return result

    changed_immutable_fields = immutable_errors(
        record['original_cv'],
        record['tailored_cv'],
    )
    result['immutable_valid'] = not changed_immutable_fields
    if changed_immutable_fields:
        result['status'] = 'FAIL'
        result['reasons'].extend(changed_immutable_fields)
        return result

    result['template_summary'] = is_template_summary(
        record['tailored_cv']['summary']
    )
    if result['template_summary']:
        result['reasons'].append('Summary dùng khuôn mẫu v1, cần cải thiện')

    unsupported_skills, skill_reasons = review_skills(
        record['original_cv'],
        record['tailored_cv'],
    )
    result['unsupported_skills'] = unsupported_skills
    result['reasons'].extend(skill_reasons)
    result['reasons'].extend(
        semantic_review_reasons(record['original_cv'], record['tailored_cv'])
    )

    if result['reasons']:
        result['status'] = 'REVIEW'
    return result


def fingerprint(value) -> str:
    content = json.dumps(value, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(content.encode()).hexdigest()


def dataset_patterns(records) -> dict:
    """Thống kê duplicate và độ giống nhau; không dùng để tự động loại mẫu."""
    valid_records = [record for record in records if not record['parse_errors']]
    records_by_cv = defaultdict(list)
    records_by_group = defaultdict(list)
    full_sample_counts = Counter()
    similarities = []

    for record in valid_records:
        cv_fingerprint = fingerprint(record['original_cv'])
        records_by_cv[cv_fingerprint].append(record)
        if record['group_id']:
            records_by_group[record['group_id']].append(record)
        full_sample_counts[fingerprint([
            record['original_cv'],
            record['job_description'],
            record['tailored_cv'],
        ])] += 1

        original_text = json.dumps(record['original_cv'], sort_keys=True, ensure_ascii=False)
        tailored_text = json.dumps(record['tailored_cv'], sort_keys=True, ensure_ascii=False)
        similarities.append(SequenceMatcher(None, original_text, tailored_text).ratio())

    multi_jd_groups = 0
    same_output_pairs = 0
    for group in records_by_cv.values():
        if len({record['job_description'] for record in group}) < 2:
            continue
        multi_jd_groups += 1
        for first, second in combinations(group, 2):
            different_jd = first['job_description'] != second['job_description']
            same_output = first['tailored_cv'] == second['tailored_cv']
            if different_jd and same_output:
                same_output_pairs += 1

    near_duplicate_groups = 0
    for group in records_by_group.values():
        distinct_cvs = {fingerprint(record['original_cv']) for record in group}
        if len(distinct_cvs) > 1:
            near_duplicate_groups += 1

    duplicate_samples = sum(
        count - 1
        for count in full_sample_counts.values()
        if count > 1
    )
    mean_similarity = (
        sum(similarities) / len(similarities)
        if similarities
        else 0.0
    )
    return {
        'exact_duplicate_samples': duplicate_samples,
        'same_cv_multiple_jd_groups': multi_jd_groups,
        'same_cv_different_jd_same_output_pairs': same_output_pairs,
        'heuristic_near_duplicate_groups': near_duplicate_groups,
        'mean_original_target_similarity': round(mean_similarity, 4),
    }


def write_reports(results, records, output_dir: Path, split: str, limit: int | None):
    """Ghi báo cáo chi tiết dạng JSON và CSV."""
    output_dir.mkdir(parents=True, exist_ok=True)
    suffix = f'_{limit}' if limit is not None else ''
    report_name = f'validation_{split}{suffix}'
    json_path = output_dir / f'{report_name}.json'
    csv_path = output_dir / f'{report_name}.csv'

    status_counts = Counter(result['status'] for result in results)
    summary = {
        'split': split,
        'limit': limit,
        'total_samples': len(results),
        'status_counts': {
            'PASS': status_counts['PASS'],
            'REVIEW': status_counts['REVIEW'],
            'FAIL': status_counts['FAIL'],
        },
        'json_valid_samples': sum(result['json_valid'] for result in results),
        'schema_valid_samples': sum(result['schema_valid'] for result in results),
        'immutable_valid_samples': sum(result['immutable_valid'] for result in results),
        'template_summary_samples': sum(result['template_summary'] for result in results),
        'samples_with_unsupported_skills': sum(
            bool(result['unsupported_skills'])
            for result in results
        ),
        'dataset_patterns': dataset_patterns(records),
        'limitations': [
            'PASS chỉ có nghĩa là các kiểm tra đã triển khai không phát hiện vấn đề.',
            'Validator không chứng minh được một target hoàn toàn không có hallucination.',
            'Exact text matching không nhận biết đầy đủ alias, phủ định hoặc nghĩa tương đương.',
            'Summary và bullet viết lại cần người kiểm tra ngữ nghĩa trước khi dùng để train.',
            'Similarity chỉ dùng để mô tả dữ liệu, không tự động kết luận chất lượng.',
        ],
    }
    json_report = {'summary': summary, 'samples': results}
    json_path.write_text(
        json.dumps(json_report, ensure_ascii=False, indent=2) + '\n',
        encoding='utf-8',
    )

    with csv_path.open('w', encoding='utf-8', newline='') as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for result in results:
            csv_row = dict(result)
            csv_row['reasons'] = json.dumps(result['reasons'], ensure_ascii=False)
            csv_row['unsupported_skills'] = json.dumps(
                result['unsupported_skills'],
                ensure_ascii=False,
            )
            writer.writerow(csv_row)

    return json_path, csv_path, summary


def load_selected_records(data_dir: Path, split: str, limit: int | None):
    if split != 'all':
        return load_split(data_dir, split, limit)

    records = []
    for split_name in VALID_SPLITS:
        split_records = load_split(data_dir, split_name)
        records.extend(split_records)
        if limit is not None and len(records) >= limit:
            return records[:limit]
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--split', choices=(*VALID_SPLITS, 'all'), default='all')
    parser.add_argument('--limit', type=int)
    parser.add_argument('--data-dir', type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument('--output-dir', type=Path, default=DEFAULT_DATA_DIR / 'reports')
    args = parser.parse_args()

    if args.limit is not None and args.limit <= 0:
        parser.error('--limit phải lớn hơn 0')

    records = load_selected_records(args.data_dir, args.split, args.limit)
    results = [
        validate_record(record)
        for record in tqdm(records, desc='Đang kiểm tra dữ liệu')
    ]
    json_path, csv_path, summary = write_reports(
        results,
        records,
        args.output_dir,
        args.split,
        args.limit,
    )

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f'Báo cáo JSON: {json_path}')
    print(f'Báo cáo CSV: {csv_path}')


if __name__ == '__main__':
    main()
