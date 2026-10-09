"""Tạo đáp án chỉ dùng dữ kiện trong CV gốc."""
from collections import Counter
from copy import deepcopy
import hashlib
import json

from .audit_data import audit_content, literal_supported
from .prepare_data import audit_facts, schema_errors


def relevance(text, skills, job_description):
    """Đếm kỹ năng gốc vừa có trong JD vừa xuất hiện trong nội dung."""
    score = 0
    for skill in skills:
        appears_in_jd = literal_supported(skill, job_description)
        appears_in_text = literal_supported(skill, text)
        if appears_in_jd and appears_in_text:
            score += 1
    return score


def make_source_only_target(source, job_description):
    """Chỉ sắp xếp lại dữ kiện gốc, không phát sinh câu hoặc kỹ năng mới."""
    target = deepcopy(source)
    source_skills = []
    for values in source['skills'].values():
        source_skills.extend(values)
    # Giữ thứ tự tương đối nếu các mục có cùng điểm.
    for category, values in target['skills'].items():
        target['skills'][category] = sorted(
            values,
            key=lambda skill: literal_supported(skill, job_description),
            reverse=True,
        )
    # Không đổi thứ tự công việc: giữ lịch sử kinh nghiệm như CV gốc.
    for section in ['experience', 'projects']:
        for entry in target[section]:
            entry['bullet_points'] = sorted(
                entry['bullet_points'],
                key=lambda bullet: relevance(bullet, source_skills, job_description),
                reverse=True,
            )
    return target


def changed_paths(before, after, path='target_cv'):
    """Trả về đường dẫn của những trường đã thay đổi."""
    if isinstance(before, dict) and isinstance(after, dict):
        paths = []
        for key in sorted(set(before) | set(after)):
            paths.extend(changed_paths(before.get(key), after.get(key), f'{path}.{key}'))
        return paths
    if before != after:
        return [path]
    return []


def assert_source_only(source, target):
    """Kiểm chứng chỉ đổi thứ tự skills/bullet; mọi nội dung còn lại như nguồn."""
    restored = deepcopy(target)
    for category, values in source['skills'].items():
        if Counter(values) != Counter(target['skills'][category]):
            raise ValueError(f'Skills changed: {category}')
        restored['skills'][category] = deepcopy(values)
    for section in ['experience', 'projects']:
        if len(source[section]) != len(target[section]):
            raise ValueError(f'Section length changed: {section}')
        for original, edited in zip(source[section], restored[section]):
            if Counter(original['bullet_points']) != Counter(edited['bullet_points']):
                raise ValueError(f'Bullet content changed: {section}')
            edited['bullet_points'] = deepcopy(original['bullet_points'])
    if restored != source:
        raise ValueError('Non-reorder source content changed')


def clean_records(records):
    cleaned_records = []
    rejected_records = []
    change_log = []

    for record in records:
        source_cv = record.get('original_cv')
        job_description = record.get('job_description')
        errors = schema_errors(source_cv)

        if not isinstance(job_description, str) or not job_description.strip():
            errors.append('missing JD')
        if errors:
            rejected_records.append({
                'sample_id': record['sample_id'],
                'reasons': errors,
            })
            continue

        target_cv = make_source_only_target(source_cv, job_description)
        assert_source_only(source_cv, target_cv)
        if schema_errors(target_cv) or audit_facts(source_cv, target_cv):
            raise ValueError(f'Output failed invariant: {record["sample_id"]}')

        cleaned_record = deepcopy(record)
        cleaned_record['target_cv'] = target_cv
        cleaned_record['previous_review_status'] = record['review_status']
        cleaned_record['previous_review_reasons'] = record['review_reasons']
        cleaned_record['review_status'] = 'source_only_candidate'
        cleaned_record['review_reasons'] = audit_content(cleaned_record)
        cleaned_record['cleaning_method'] = 'source_only_reordering_v1'
        cleaned_record['requires_manual_review'] = True
        cleaned_record['source_cv_sha256'] = hashlib.sha256(
            json.dumps(source_cv, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()
        cleaned_records.append(cleaned_record)
        change_log.append({
            'sample_id': record['sample_id'],
            'changed_paths': changed_paths(record.get('target_cv'), target_cv),
            'reordered_from_source': target_cv != source_cv,
            'reason': 'Unverified generated claims replaced by original CV content; only reorder skills/bullets using JD.',
            'remaining_issues': cleaned_record['review_reasons'],
        })
    return cleaned_records, rejected_records, change_log


