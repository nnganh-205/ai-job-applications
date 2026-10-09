"""Các kiểm tra nội dung dùng trong bước làm sạch dữ liệu."""
from collections import Counter, defaultdict
import hashlib
import json
import re

from .prepare_data import SECTIONS


def strings(value):
    """Lấy lần lượt tất cả chuỗi nằm trong list hoặc dict lồng nhau."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from strings(item)


def text_key(value):
    """Chuẩn hóa chuỗi để so sánh mà không phụ thuộc chữ hoa, chữ thường."""
    return re.sub(r'\s+', ' ', value).strip().casefold()


def digest(value):
    content = json.dumps(value, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(content.encode()).hexdigest()


def literal_supported(skill, source):
    """Kiểm tra cụm kỹ năng có xuất hiện nguyên văn trong nguồn hay không."""
    normalized_skill = text_key(skill)
    normalized_source = text_key(' '.join(strings(source)))
    pattern = r'(?<!\w)' + re.escape(normalized_skill) + r'(?!\w)'
    return bool(re.search(pattern, normalized_source))


def audit_content(record):
    issues = []
    source_cv = record.get('original_cv')
    target_cv = record.get('target_cv')

    if not isinstance(source_cv, dict) or not isinstance(target_cv, dict):
        return [{'code': 'content_audit_skipped', 'detail': 'CV is not an object'}]

    for cv_name, cv in [('original_cv', source_cv), ('target_cv', target_cv)]:
        for section in SECTIONS:
            items = cv.get(section)
            if not isinstance(items, list):
                continue

            item_counts = Counter(digest(item) for item in items)
            if any(count > 1 for count in item_counts.values()):
                extra_entries = sum(
                    count - 1
                    for count in item_counts.values()
                    if count > 1
                )
                issues.append({
                    'code': 'duplicate_section_entries',
                    'path': f'{cv_name}.{section}',
                    'extra_entries': extra_entries,
                })

            if section == 'experience':
                for index, item in enumerate(items):
                    if not isinstance(item, dict):
                        continue
                    identity_fields = ['title', 'company', 'dates']
                    if any(item.get(field) is None for field in identity_fields):
                        issues.append({
                            'code': 'missing_experience_identity',
                            'path': f'{cv_name}.{section}[{index}]',
                        })

        contains_masked_value = any(
            re.search(r'XXX|\b(?:redacted|unknown)\b', text, re.I)
            for text in strings(cv)
        )
        if contains_masked_value:
            issues.append({'code': 'masked_or_unknown_values', 'path': cv_name})

    skills = target_cv.get('skills', {})
    unsupported_skills = []
    if isinstance(skills, dict):
        for category, values in skills.items():
            if isinstance(values, list):
                for skill in values:
                    if isinstance(skill, str) and not literal_supported(skill, source_cv):
                        unsupported_skills.append({
                            'category': category,
                            'skill': skill,
                            'appears_in_jd': literal_supported(
                                skill,
                                record.get('job_description') or '',
                            ),
                        })
    if unsupported_skills:
        issues.append({
            'code': 'skills_without_literal_source_evidence',
            'candidates': unsupported_skills,
        })

    projects = target_cv.get('projects', [])
    if not isinstance(projects, list):
        projects = []
    for index, project in enumerate(projects):
        if isinstance(project, dict) and isinstance(project.get('tech_stack'), list):
            unsupported_tech = [
                technology
                for technology in project['tech_stack']
                if isinstance(technology, str)
                and not literal_supported(technology, source_cv)
            ]
            if unsupported_tech:
                issues.append({
                    'code': 'project_tech_without_literal_source_evidence',
                    'path': f'target_cv.projects[{index}].tech_stack',
                    'values': unsupported_tech,
                })

    # So sánh số trong đúng công việc/dự án để tránh gắn thành tích nhầm vị trí.
    number_pattern = r'(?<!\w)\d+(?:[.,]\d+)*%?'
    scopes = [('summary', source_cv.get('summary'), target_cv.get('summary'))]
    for section, keys in [('experience', ['title', 'company', 'dates']), ('projects', ['title'])]:
        source_items = source_cv.get(section)
        target_items = target_cv.get(section)
        if not isinstance(source_items, list) or not isinstance(target_items, list):
            continue

        for index, target_item in enumerate(target_items):
            if not isinstance(target_item, dict):
                continue

            matches = [
                source_item
                for source_item in source_items
                if isinstance(source_item, dict)
                and all(source_item.get(key) == target_item.get(key) for key in keys)
            ]
            if len(matches) == 1:
                scopes.append((f'{section}[{index}]', matches[0], target_item))

    for path, source_value, target_value in scopes:
        source_numbers = set(
            re.findall(number_pattern, ' '.join(strings(source_value)))
        )
        target_numbers = set(
            re.findall(number_pattern, ' '.join(strings(target_value)))
        )
        added_numbers = sorted(target_numbers - source_numbers)
        if added_numbers:
            issues.append({
                'code': 'new_numbers_in_section',
                'path': f'target_cv.{path}',
                'values': added_numbers,
            })
    return issues


def audit_records(records):
    sample_id_counts = Counter(record['sample_id'] for record in records)
    if any(count != 1 for count in sample_id_counts.values()):
        raise ValueError('Duplicate sample IDs')

    results = []
    records_by_cv = defaultdict(list)
    records_by_cv_and_jd = defaultdict(list)
    records_by_full_content = defaultdict(list)

    for record in records:
        audit_result = {
            'sample_id': record['sample_id'],
            'source_split': record['source_split'],
            'preparation_issues': record['review_reasons'],
            'audit_issues': audit_content(record),
        }
        if not isinstance(record.get('instruction'), str) or not record['instruction'].strip():
            audit_result['audit_issues'].append({'code': 'empty_instruction'})
        if not isinstance(record.get('job_description'), str) or not record['job_description'].strip():
            audit_result['audit_issues'].append({'code': 'empty_jd'})

        results.append(audit_result)
        if isinstance(record.get('original_cv'), dict) and record.get('job_description'):
            cv_checksum = digest(record['original_cv'])
            pair_checksum = digest([
                record['original_cv'],
                record['job_description'],
            ])
            full_checksum = digest([
                record['original_cv'],
                record['job_description'],
                record['target_cv'],
            ])
            records_by_cv[cv_checksum].append(audit_result)
            records_by_cv_and_jd[pair_checksum].append(audit_result)
            records_by_full_content[full_checksum].append(audit_result)

    duplicate_checks = [
        (records_by_cv, 'same_cv_across_splits', True),
        (records_by_cv_and_jd, 'duplicate_cv_jd_pair', False),
        (records_by_full_content, 'duplicate_full_sample', False),
    ]
    for groups, issue_code, cross_split_only in duplicate_checks:
        for group in groups.values():
            source_splits = {item['source_split'] for item in group}
            if len(group) < 2 or (cross_split_only and len(source_splits) < 2):
                continue

            for audit_result in group:
                related_ids = [
                    item['sample_id']
                    for item in group
                    if item is not audit_result
                ]
                audit_result['audit_issues'].append({
                    'code': issue_code,
                    'related_sample_ids': related_ids,
                })

    # Chỉ so sánh CV giống hệt; không tự gộp các phiên bản khác nhau của một người.
    cross_split_overlap = {}
    split_pairs = [
        ('train', 'validation'),
        ('train', 'test'),
        ('validation', 'test'),
    ]
    for first_split, second_split in split_pairs:
        pair = {first_split, second_split}
        overlap_count = 0
        for group in records_by_cv.values():
            group_splits = {item['source_split'] for item in group}
            if pair.issubset(group_splits):
                overlap_count += 1
        cross_split_overlap[f'{first_split}/{second_split}'] = overlap_count

    all_issue_codes = {
        issue['code']
        for result in results
        for issue in result['preparation_issues'] + result['audit_issues']
    }
    samples_by_issue = {}
    for issue_code in sorted(all_issue_codes):
        count = 0
        for result in results:
            all_issues = result['preparation_issues'] + result['audit_issues']
            if any(issue['code'] == issue_code for issue in all_issues):
                count += 1
        samples_by_issue[issue_code] = count

    report = {
        'total_samples': len(results),
        'samples_flagged': sum(
            bool(result['preparation_issues'] or result['audit_issues'])
            for result in results
        ),
        'samples_by_issue': samples_by_issue,
        'unique_original_cvs': len(records_by_cv),
        'cross_split_cv_overlap': cross_split_overlap,
        'limitations': [
            'Flags require review. Literal skill matching misses aliases and cannot validate proficiency, negation or claims in context.',
            'Summary/bullet semantic truth and JD alignment have not been fully evaluated. No sample is approved.',
            'New numbers may be legitimate derived values; matching numbers may still be assigned to the wrong claim.',
            'Duplicate detection compares normalized objects, not all versions of the same candidate.',
            'Targets are not repaired; records are not deleted or re-split.',
        ],
    }
    return results, report


