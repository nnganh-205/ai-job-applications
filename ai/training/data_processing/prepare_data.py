"""Tách, chuẩn hóa và kiểm tra một mẫu dữ liệu CV."""
from collections import Counter
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[3]
SECTIONS = {
    'experience': {'title': str, 'company': str, 'dates': str, 'bullet_points': list},
    'projects': {'title': str, 'tech_stack': list, 'description': str, 'bullet_points': list},
    'education': {'degree': str, 'institution': str, 'dates': str},
    'awards': {'title': str, 'year': str, 'issuer': str, 'description': str},
    'leadership': {'role': str, 'organization': str, 'dates': str},
}
PERSONAL = {'name', 'email', 'phone', 'location', 'links'}
SKILLS = {'languages', 'frameworks', 'tools', 'domain_skills'}


def normalize(value, path='', changes=None):
    """Chuẩn hóa khoảng trắng và giá trị rỗng, không suy đoán dữ kiện thiếu."""
    changes = changes if changes is not None else []

    if isinstance(value, str):
        lines = value.replace('\r\n', '\n').split('\n')
        cleaned_lines = []
        for line in lines:
            cleaned_lines.append(re.sub(r'[ \t]+', ' ', line).strip())
        result = '\n'.join(cleaned_lines).strip()
        if result.lower() in {'null', 'none', 'n/a'} or not result:
            result = None
        if result != value:
            changes.append(path)
        return result

    if isinstance(value, list):
        result = []
        for index, item in enumerate(value):
            result.append(normalize(item, f'{path}[{index}]', changes))

        is_text_list = all(
            item is None or isinstance(item, str)
            for item in result
        )
        if is_text_list:
            if None in result:
                changes.append(f'{path}: removed empty/null list entries')
            return [item for item in result if item is not None]
        return result

    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            result[key] = normalize(item, f'{path}.{key}', changes)
        return result

    return value


def schema_errors(cv):
    """Trả về danh sách lỗi cấu trúc của một CV."""
    errors = []
    if not isinstance(cv, dict):
        return ['CV must be an object']

    expected = {'personal_info', 'summary', 'skills', *SECTIONS}
    if set(cv) != expected:
        missing_keys = sorted(expected - set(cv))
        extra_keys = sorted(set(cv) - expected)
        errors.append(f'root keys: missing={missing_keys}, extra={extra_keys}')

    def is_text_or_none(value):
        return value is None or isinstance(value, str)

    if not is_text_or_none(cv.get('summary')):
        errors.append('summary must be text or null')

    personal = cv.get('personal_info')
    if not isinstance(personal, dict) or set(personal) != PERSONAL:
        errors.append('personal_info has invalid keys/type')
    else:
        for field, value in personal.items():
            if field == 'links':
                valid_links = (
                    isinstance(value, list)
                    and all(isinstance(link, str) for link in value)
                )
                if not valid_links:
                    errors.append('personal_info.links must be a list of strings')
            elif not is_text_or_none(value):
                errors.append(f'personal_info.{field} must be text or null')

    skills = cv.get('skills')
    if not isinstance(skills, dict) or set(skills) != SKILLS:
        errors.append('skills has invalid keys/type')
    else:
        for category, values in skills.items():
            valid_skills = (
                isinstance(values, list)
                and all(isinstance(skill, str) for skill in values)
            )
            if not valid_skills:
                errors.append(f'skills.{category} must be a list of strings')

    for section, fields in SECTIONS.items():
        items = cv.get(section)
        if not isinstance(items, list):
            errors.append(f'{section} must be a list')
            continue

        for index, item in enumerate(items):
            if not isinstance(item, dict) or set(item) != set(fields):
                errors.append(f'{section}[{index}] has invalid keys/type')
                continue

            for field, expected_type in fields.items():
                value = item[field]
                if expected_type is list:
                    valid = (
                        isinstance(value, list)
                        and all(isinstance(text, str) for text in value)
                    )
                else:
                    valid = is_text_or_none(value)
                if not valid:
                    errors.append(f'{section}[{index}].{field} has invalid type')
    return errors


def parse_input(value):
    """Tách CV gốc và JD từ trường input của dataset ban đầu."""
    if not isinstance(value, str) or not value.strip().startswith('MASTER RESUME:'):
        raise ValueError('missing MASTER RESUME marker')

    body = value.strip()[len('MASTER RESUME:'):].lstrip()
    original_cv, json_end = json.JSONDecoder().raw_decode(body)
    remaining_text = body[json_end:].strip()
    marker = 'JOB DESCRIPTION:'
    if not remaining_text.startswith(marker):
        raise ValueError('missing or empty JOB DESCRIPTION')

    job_description = remaining_text[len(marker):].strip()
    if not job_description:
        raise ValueError('missing or empty JOB DESCRIPTION')
    return original_cv, job_description


def audit_facts(source, target):
    """Đối chiếu dữ kiện nhận dạng; chỉ báo lỗi, không tự sửa dữ liệu."""
    issues = []
    for key in sorted(PERSONAL):
        source_value = source['personal_info'][key]
        target_value = target['personal_info'][key]
        if key == 'links':
            source_value = sorted(source_value)
            target_value = sorted(target_value)
        if source_value != target_value:
            issues.append({
                'code': 'personal_info_changed',
                'path': f'personal_info.{key}',
                'original': source_value,
                'target': target_value,
            })
    identities = {
        'experience': ('title', 'company', 'dates'),
        'education': ('degree', 'institution', 'dates'),
        'projects': ('title',),
        'awards': ('title', 'year', 'issuer'),
        'leadership': ('role', 'organization', 'dates'),
    }
    for section, fields in identities.items():
        source_identities = count_identities(source[section], fields)
        target_identities = count_identities(target[section], fields)
        if source_identities != target_identities:
            issues.append({
                'code': f'{section}_identity_changed',
                'path': section,
                'missing_or_changed': [
                    json.loads(item)
                    for item in (source_identities - target_identities).elements()
                ],
                'added_or_changed': [
                    json.loads(item)
                    for item in (target_identities - source_identities).elements()
                ],
            })

    # Đây là kiểm tra toàn CV, chỉ dùng để phát hiện số mới cần xem lại.
    added = sorted(find_numbers(target) - find_numbers(source))
    if added:
        issues.append({'code': 'new_numeric_tokens_review', 'path': 'target_cv', 'values': added})
    return issues


def count_identities(items, fields):
    """Đếm bộ định danh; cho phép đổi thứ tự nhưng phát hiện thêm bản sao."""
    identities = []
    for item in items:
        identity = {field: item[field] for field in fields}
        identities.append(json.dumps(identity, sort_keys=True, ensure_ascii=False))
    return Counter(identities)


def find_numbers(cv):
    """Lấy các số trong toàn CV. Đây chỉ là dấu hiệu cần kiểm tra."""
    cv_text = json.dumps(cv, ensure_ascii=False)
    return set(re.findall(r'\b\d+(?:[.,]\d+)*%?', cv_text))


def prepare_record(row, split, index):
    """Xử lý một mẫu, ghi lỗi vào mẫu thay vì bỏ qua dữ liệu."""
    record = {
        'sample_id': f'{split}_{index:06d}',
        'source_split': split,
        'source_index': index,
        'instruction': row.get('instruction'),
        'original_cv': None,
        'job_description': None,
        'target_cv': None,
        'review_status': 'pending',
        'review_reasons': [],
        'normalization_changes': [],
    }
    try:
        original_cv, jd = parse_input(row['input'])
        target_cv = json.loads(row['output'])
        values = {
            'original_cv': original_cv,
            'target_cv': target_cv,
            'job_description': jd,
        }
        for field, value in values.items():
            record[field] = normalize(value, field, record['normalization_changes'])

        # Kiểm tra cấu trúc trước, nhưng vẫn thử đối chiếu dữ kiện nếu có thể.
        for field in ['original_cv', 'target_cv']:
            for error in schema_errors(record[field]):
                record['review_reasons'].append({
                    'code': 'schema_error', 'path': field, 'detail': error,
                })
        try:
            issues = audit_facts(record['original_cv'], record['target_cv'])
            record['review_reasons'].extend(issues)
        except (KeyError, TypeError):
            record['review_reasons'].append({
                'code': 'fact_audit_incomplete',
                'detail': 'Invalid schema prevents complete comparison.',
            })
    except (ValueError, TypeError, KeyError) as error:
        record['review_reasons'].append({'code': 'parse_error', 'detail': str(error)})

    if record['review_reasons']:
        record['review_status'] = 'needs_review'
    return record


