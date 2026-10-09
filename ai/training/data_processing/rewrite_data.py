"""Viết lại summary và bullet bằng các quy tắc có thể truy vết."""

from collections import Counter
from copy import deepcopy
import re

from .audit_data import literal_supported
from .clean_data import make_source_only_target
from .data_io import write_json
from .prepare_data import schema_errors

METHOD = 'grounded_editorial_v1'


def rewrite_bullet(text):
    """Không đổi số, công nghệ, thời gian hay nâng mức trách nhiệm."""
    edited = text.strip()
    replacements = [
        (r'^I was responsible for\s+', 'Responsible for '),
        (r'^I am responsible for\s+', 'Responsible for '),
        (r'^I have been\s+', 'Have been '),
        (r'^I\s+', ''),
        (r'^Working on developing\s+', 'Developing '),
        (r'^Worked on developing\s+', 'Contributed to developing '),
        (r'^Worked on the development of\s+', 'Contributed to the development of '),
        (r'^Involved in\s+', 'Contributed to '),
        (r'\bUtilized\b', 'Used'),
        (r'\butilized\b', 'used'),
        (r'\bin order to\b', 'to'),
        (r'\bon a daily basis\b', 'daily'),
    ]
    for pattern, replacement in replacements:
        edited = re.sub(pattern, replacement, edited)
    if edited:
        edited = edited[0].upper() + edited[1:]
        if edited[-1] not in '.!?':
            edited += '.'
    return edited


def collect_skills(source):
    """Lấy kỹ năng và đường dẫn căn cứ, bỏ tên bị lặp."""
    skills = []
    seen_names = set()
    for category, values in source['skills'].items():
        for index, value in enumerate(values):
            name = value.casefold()
            if name in seen_names:
                continue
            seen_names.add(name)
            skills.append({
                'text': value,
                'source_path': f'skills.{category}[{index}]',
            })
    return skills


def choose_roles(source, relevant_skills):
    """Chọn tối đa hai chức danh theo mức liên quan của nhiệm vụ."""
    jobs = []
    for index, job in enumerate(source['experience']):
        if not job['title']:
            continue
        bullets = ' '.join(job['bullet_points'])
        score = 0
        for skill in relevant_skills:
            if literal_supported(skill['text'], bullets):
                score += 1
        jobs.append({
            'text': job['title'],
            'source_path': f'experience[{index}].title',
            'score': score,
        })

    jobs.sort(key=lambda job: job['score'], reverse=True)
    roles = []
    seen_titles = set()
    for job in jobs:
        title = job['text'].casefold()
        if title in seen_titles:
            continue
        seen_titles.add(title)
        roles.append(job)
        if len(roles) == 2:
            break
    return roles


def write_summary(source, job_description):
    """Ghép summary từ chức danh và kỹ năng có đường dẫn căn cứ."""
    skills = collect_skills(source)
    relevant_skills = []
    for skill in skills:
        if literal_supported(skill['text'], job_description):
            relevant_skills.append(skill)

    chosen_skills = (relevant_skills if relevant_skills else skills)[:6]
    roles = choose_roles(source, relevant_skills)
    sentences = []
    evidence = []

    if roles:
        titles = ' and '.join(role['text'] for role in roles)
        sentences.append(f'Experience in roles including {titles}.')
        for role in roles:
            evidence.append({
                'kind': 'role',
                'text': role['text'],
                'source_path': role['source_path'],
            })

    if chosen_skills:
        names = ', '.join(skill['text'] for skill in chosen_skills)
        sentences.append(f'Skills include {names}.')
        for skill in chosen_skills:
            evidence.append({'kind': 'skill', **skill})

    if not sentences:
        return source['summary'], [{'kind': 'unchanged_summary', 'source_path': 'summary'}]
    return ' '.join(sentences), evidence


def make_rewritten_target(source, job_description):
    target = make_source_only_target(source, job_description)
    target['summary'], evidence = write_summary(source, job_description)
    for section in ['experience', 'projects']:
        for entry in target[section]:
            entry['bullet_points'] = [rewrite_bullet(bullet) for bullet in entry['bullet_points']]
    return target, evidence


def validate_rewritten_record(record):
    """Tái tính đáp án để phát hiện mọi chỉnh sửa ngoài quy tắc cho phép."""
    if record.get('cleaning_method') != METHOD:
        raise ValueError('Unsupported rewrite method')
    for field in ['original_cv', 'target_cv']:
        if schema_errors(record[field]):
            raise ValueError(f'Invalid schema: {record["sample_id"]}')

    expected_target, expected_evidence = make_rewritten_target(
        record['original_cv'],
        record['job_description'],
    )
    if (
        expected_target != record['target_cv']
        or expected_evidence != record.get('summary_evidence')
    ):
        raise ValueError(f'Untraceable rewrite: {record["sample_id"]}')

    # Đếm số trong từng bullet: không cho phép đổi hoặc làm mất số.
    for section in ['experience', 'projects']:
        for original in record['original_cv'][section]:
            for bullet in original['bullet_points']:
                numbers_before = Counter(re.findall(r'\d+(?:[.,]\d+)*%?', bullet))
                numbers_after = Counter(
                    re.findall(r'\d+(?:[.,]\d+)*%?', rewrite_bullet(bullet))
                )
                if numbers_before != numbers_after:
                    raise ValueError('Numeric change in bullet')


def rewrite_records(records):
    rewritten_records = []
    rewrite_changes = []

    for record in records:
        edited = deepcopy(record)
        target_cv, evidence = make_rewritten_target(
            record['original_cv'],
            record['job_description'],
        )
        edited['target_cv'] = target_cv
        edited['summary_evidence'] = evidence
        edited['cleaning_method'] = METHOD
        edited['review_status'] = 'rule_validated_rewrite'
        edited['requires_manual_review'] = True
        validate_rewritten_record(edited)

        bullet_changes = []
        for section in ['experience', 'projects']:
            for index, entry in enumerate(record['original_cv'][section]):
                for bullet_index, bullet in enumerate(entry['bullet_points']):
                    rewritten_bullet = rewrite_bullet(bullet)
                    if rewritten_bullet != bullet:
                        bullet_changes.append({
                            'source_path': f'{section}[{index}].bullet_points[{bullet_index}]',
                            'before': bullet,
                            'after': rewritten_bullet,
                        })

        rewrite_changes.append({
            'sample_id': record['sample_id'],
            'summary_before': record['original_cv']['summary'],
            'summary_after': target_cv['summary'],
            'summary_evidence': evidence,
            'bullet_changes': bullet_changes,
        })
        rewritten_records.append(edited)

    return rewritten_records, rewrite_changes


def save_rewrites(records, folder):
    """Lưu bản hiện tại và lịch sử thay đổi để tái sử dụng trong pipeline."""
    rewritten_records, changes = rewrite_records(records)
    write_json(folder / 'rewritten_dataset.json', rewritten_records)
    write_json(folder / 'rewrite_changes.json', changes)

    report = {
        'samples': len(rewritten_records),
        'summaries_rewritten': sum(
            change['summary_before'] != change['summary_after']
            for change in changes
        ),
        'bullets_rewritten': sum(
            len(change['bullet_changes'])
            for change in changes
        ),
        'samples_with_rewritten_bullets': sum(
            bool(change['bullet_changes'])
            for change in changes
        ),
        'rule_and_numeric_checks': 'passed',
        'manually_approved_rewrites': 0,
        'limitations': [
            'Summary uses traceable role/skill templates; not creative model-generated text.',
            'Bullets only undergo conservative editing; many already clear bullets remain unchanged.',
            'Source facts may still be inconsistent. Semantic human review remains recommended.',
        ],
    }
    write_json(folder / 'rewrite_report.json', report)
    return rewritten_records, report


