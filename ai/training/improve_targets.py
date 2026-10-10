"""Tạo, nhập, duyệt và xuất professional summary cho dataset v2."""

import argparse
from copy import deepcopy
import json
import os
from pathlib import Path
import re
import sys
from urllib.request import Request, urlopen

from tqdm import tqdm


# Cho phép chạy trực tiếp bằng: python ai/training/improve_targets.py
if __package__ in {None, ''}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ai.training.prepare_data import DEFAULT_DATA_DIR, VALID_SPLITS, load_split, read_json
from ai.training.validate_data import (
    collect_strings,
    immutable_errors,
    is_template_summary,
    validate_cv_schema,
    validate_record,
)


DEFAULT_V2_DIR = DEFAULT_DATA_DIR / 'processed' / 'v2'
DEFAULT_QUEUE_PATH = DEFAULT_V2_DIR / 'summary_review.json'
DEFAULT_APPROVED_PATH = DEFAULT_V2_DIR / 'approved_targets.json'
APPROVAL_STATUSES = {'pending', 'approved', 'rejected'}

TEACHER_INSTRUCTIONS = """You are an expert resume writer and ATS optimization specialist.

Write a professional summary in English using only facts from original_cv and user_info. Use the job description only to decide which supported facts are most relevant.

Requirements:
- Write 2–3 natural, professional sentences, approximately 40–75 words.
- Prioritize relevant experience, technologies, and supported achievements.
- Preserve the meaning of all facts.
- Do not infer years of experience unless the source states them clearly.
- Do not invent skills, certifications, education, technologies, responsibilities, metrics, or achievements.
- Do not convert job requirements into candidate experience.
- Do not use "Experience in roles including" or "Skills include".
- Do not mention the hiring company unless necessary.
- Avoid unsupported clichés such as "passionate", "world-class", or "exceptional".

Return only JSON with this structure:
{
  "summary": "Professional summary...",
  "evidence": [
    {
      "claim": "A claim used in the summary",
      "source": "An exact quote from original_cv or user_info"
    }
  ]
}

Every evidence.source must be copied verbatim from original_cv or user_info, never from the job description."""


def write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + '\n',
        encoding='utf-8',
    )


def build_teacher_prompt(record) -> str:
    """Tạo prompt gồm hướng dẫn và ba input cần thiết cho teacher."""
    teacher_input = {
        'original_cv': record['original_cv'],
        'user_info': record['user_info'],
        'job_description': record['job_description'],
    }
    return (
        f'{TEACHER_INSTRUCTIONS}\n\nINPUT:\n'
        + json.dumps(teacher_input, ensure_ascii=False, indent=2)
    )


def parse_teacher_response(response):
    """Parse response JSON từ teacher; không sửa response sai định dạng."""
    if isinstance(response, dict):
        return response
    if not isinstance(response, str) or not response.strip():
        raise ValueError('Teacher response phải là JSON object hoặc chuỗi JSON')

    try:
        parsed = json.loads(response)
    except json.JSONDecodeError as error:
        raise ValueError(f'Teacher response không phải JSON hợp lệ: {error.msg}') from error
    if not isinstance(parsed, dict):
        raise ValueError('Teacher response phải parse thành object')
    return parsed


def call_teacher_endpoint(
    prompt: str,
    endpoint_url: str,
    api_key_env: str | None = None,
):
    """Gọi endpoint do người dùng cấu hình; hàm này không chạy mặc định."""
    headers = {'Content-Type': 'application/json'}
    if api_key_env:
        api_key = os.getenv(api_key_env)
        if not api_key:
            raise ValueError(f'Chưa có biến môi trường {api_key_env}')
        headers['Authorization'] = f'Bearer {api_key}'

    request = Request(
        endpoint_url,
        data=json.dumps({'prompt': prompt}).encode('utf-8'),
        headers=headers,
        method='POST',
    )
    with urlopen(request, timeout=120) as response:
        response_data = json.loads(response.read().decode('utf-8'))

    # Endpoint có thể trả trực tiếp object hoặc đặt kết quả trong trường output.
    teacher_output = response_data.get('output', response_data)
    return parse_teacher_response(teacher_output)


def evidence_exists(source: str, original_cv, user_info) -> bool:
    """Kiểm tra evidence.source có được trích nguyên văn từ nguồn hay không."""
    source = source.strip()
    source_texts = [
        text
        for text in collect_strings([original_cv, user_info])
        if text.strip()
    ]
    return bool(source) and any(source in text for text in source_texts)


def validate_teacher_output(teacher_output, record):
    """Kiểm tra cấu trúc, độ dài và evidence; không tự động PASS."""
    if not isinstance(teacher_output, dict):
        return 'FAIL', ['Teacher output phải là object']

    summary = teacher_output.get('summary')
    evidence = teacher_output.get('evidence')
    fail_reasons = []
    review_reasons = []

    if not isinstance(summary, str) or not summary.strip():
        fail_reasons.append('Summary phải là chuỗi không rỗng')
    if not isinstance(evidence, list):
        fail_reasons.append('Evidence phải là list')

    if fail_reasons:
        return 'FAIL', fail_reasons

    for index, item in enumerate(evidence):
        if not isinstance(item, dict):
            fail_reasons.append(f'evidence[{index}] phải là object')
            continue
        claim = item.get('claim')
        source = item.get('source')
        if not isinstance(claim, str) or not claim.strip():
            fail_reasons.append(f'evidence[{index}].claim phải là chuỗi không rỗng')
        if not isinstance(source, str) or not source.strip():
            fail_reasons.append(f'evidence[{index}].source phải là chuỗi không rỗng')
        elif not evidence_exists(source, record['original_cv'], record['user_info']):
            review_reasons.append(
                f'evidence[{index}].source không xuất hiện nguyên văn trong nguồn'
            )

    if fail_reasons:
        return 'FAIL', fail_reasons + review_reasons

    word_count = len(summary.split())
    sentence_count = len([
        sentence
        for sentence in re.split(r'(?<=[.!?])\s+', summary.strip())
        if sentence
    ])
    if not 40 <= word_count <= 75:
        review_reasons.append(f'Summary có {word_count} từ, ngoài khoảng 40–75')
    if not 2 <= sentence_count <= 3:
        review_reasons.append(f'Summary có {sentence_count} câu, ngoài khoảng 2–3')
    if is_template_summary(summary):
        review_reasons.append('Summary vẫn dùng khuôn mẫu v1')
    if not evidence:
        review_reasons.append('Chưa có evidence cho summary')

    lowered_summary = summary.casefold()
    unsupported_cliches = [
        phrase
        for phrase in ['passionate', 'world-class', 'exceptional']
        if phrase in lowered_summary
    ]
    if unsupported_cliches:
        review_reasons.append(
            f'Có từ sáo rỗng cần review: {unsupported_cliches}'
        )

    # Evidence đúng định dạng chưa đủ để chứng minh mọi claim là chính xác.
    review_reasons.append('Cần người duyệt xác nhận summary và evidence')
    return 'REVIEW', review_reasons


def make_review_record(record, teacher_output=None):
    """Tạo một dòng review; mọi đề xuất mới luôn bắt đầu ở trạng thái pending."""
    proposed_summary = None
    evidence = []
    validation_status = 'REVIEW'
    review_reasons = ['Chưa có teacher output']

    if teacher_output is not None:
        teacher_output = parse_teacher_response(teacher_output)
        proposed_summary = teacher_output.get('summary')
        evidence = teacher_output.get('evidence', [])
        validation_status, review_reasons = validate_teacher_output(
            teacher_output,
            record,
        )

    return {
        'sample_id': record['sample_id'],
        'split': record['split'],
        'job_description': record['job_description'],
        'old_summary': record['tailored_cv']['summary'],
        'proposed_summary': proposed_summary,
        'evidence': evidence,
        'validation_status': validation_status,
        'review_reasons': review_reasons,
        'approval_status': 'pending',
        'teacher_prompt': build_teacher_prompt(record),
    }


def create_review_queue(records, endpoint_url=None, api_key_env=None):
    """Tạo queue từ record hợp lệ; record FAIL không được tạo target."""
    review_queue = []
    skipped_sample_ids = []

    for record in tqdm(records, desc='Đang tạo summary review queue'):
        if validate_record(record)['status'] == 'FAIL':
            skipped_sample_ids.append(record['sample_id'])
            continue

        teacher_output = None
        if endpoint_url:
            teacher_output = call_teacher_endpoint(
                build_teacher_prompt(record),
                endpoint_url,
                api_key_env,
            )
        review_queue.append(make_review_record(record, teacher_output))

    return review_queue, skipped_sample_ids


def records_by_id(records):
    result = {}
    for record in records:
        sample_id = record['sample_id']
        if sample_id in result:
            raise ValueError(f'Trùng sample_id: {sample_id}')
        result[sample_id] = record
    return result


def load_source_records(review_queue, data_dir: Path):
    """Đọc lại các split cần thiết và lấy đúng source record theo sample_id."""
    needed_splits = {item['split'] for item in review_queue}
    source_records = []
    for split in VALID_SPLITS:
        if split in needed_splits:
            source_records.extend(load_split(data_dir, split))

    source_by_id = records_by_id(source_records)
    queue_ids = {item['sample_id'] for item in review_queue}
    missing_ids = sorted(queue_ids - set(source_by_id))
    if missing_ids:
        raise ValueError(f'Sample ID không tồn tại trong dataset v1: {missing_ids}')
    return source_by_id


def apply_teacher_outputs(review_queue, teacher_outputs, source_by_id):
    """Nhập output từ Colab/endpoint vào queue và đưa về trạng thái pending."""
    queue_by_id = records_by_id(review_queue)
    output_by_id = records_by_id(teacher_outputs)
    unknown_ids = sorted(set(output_by_id) - set(queue_by_id))
    if unknown_ids:
        raise ValueError(f'Teacher output chứa sample_id không hợp lệ: {unknown_ids}')

    for sample_id, teacher_output in output_by_id.items():
        review_record = queue_by_id[sample_id]
        source_record = source_by_id[sample_id]
        if review_record['split'] != source_record['split']:
            raise ValueError(f'Split không khớp cho {sample_id}')

        parsed_output = {
            'summary': teacher_output.get('summary'),
            'evidence': teacher_output.get('evidence'),
        }
        status, reasons = validate_teacher_output(parsed_output, source_record)
        review_record['proposed_summary'] = parsed_output['summary']
        review_record['evidence'] = parsed_output['evidence']
        review_record['validation_status'] = status
        review_record['review_reasons'] = reasons
        review_record['approval_status'] = 'pending'

    return review_queue


def replace_summary(target_cv, summary: str):
    """Deep copy target v1 và chỉ thay đổi trường summary."""
    new_target = deepcopy(target_cv)
    new_target['summary'] = summary

    old_without_summary = deepcopy(target_cv)
    new_without_summary = deepcopy(new_target)
    old_without_summary.pop('summary')
    new_without_summary.pop('summary')
    if old_without_summary != new_without_summary:
        raise ValueError('Có trường ngoài summary đã bị thay đổi')
    return new_target


def build_approved_targets(review_queue, source_records):
    """Chỉ tạo target cho record được người dùng đánh dấu approved."""
    queue_by_id = records_by_id(review_queue)
    source_by_id = (
        source_records
        if isinstance(source_records, dict)
        else records_by_id(source_records)
    )
    approved_targets = []

    for sample_id, review_record in queue_by_id.items():
        approval_status = review_record.get('approval_status')
        if approval_status not in APPROVAL_STATUSES:
            raise ValueError(f'approval_status không hợp lệ cho {sample_id}')
        if approval_status != 'approved':
            continue
        if sample_id not in source_by_id:
            raise ValueError(f'Sample ID không tồn tại trong dataset v1: {sample_id}')

        source_record = source_by_id[sample_id]
        if review_record['split'] != source_record['split']:
            raise ValueError(f'Split không khớp cho {sample_id}')

        teacher_output = {
            'summary': review_record.get('proposed_summary'),
            'evidence': review_record.get('evidence'),
        }
        validation_status, review_reasons = validate_teacher_output(
            teacher_output,
            source_record,
        )
        if validation_status == 'FAIL':
            raise ValueError(
                f'Summary đã approved nhưng không hợp lệ cho {sample_id}: '
                f'{review_reasons}'
            )

        new_target = replace_summary(
            source_record['tailored_cv'],
            teacher_output['summary'],
        )
        schema_errors = validate_cv_schema(new_target, 'target_cv')
        changed_immutable = immutable_errors(source_record['original_cv'], new_target)
        if schema_errors or changed_immutable:
            raise ValueError(
                f'Target không hợp lệ cho {sample_id}: '
                f'{schema_errors + changed_immutable}'
            )

        approved_targets.append({
            'sample_id': sample_id,
            'split': source_record['split'],
            'target_cv': new_target,
            'evidence': teacher_output['evidence'],
            'validation_status': validation_status,
            'approval_status': 'approved',
        })

    return approved_targets


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--split', choices=VALID_SPLITS, default='train')
    parser.add_argument('--limit', type=int, default=20)
    parser.add_argument('--data-dir', type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument('--queue-path', type=Path, default=DEFAULT_QUEUE_PATH)
    parser.add_argument('--approved-path', type=Path, default=DEFAULT_APPROVED_PATH)
    parser.add_argument('--teacher-endpoint')
    parser.add_argument('--api-key-env')
    parser.add_argument('--import-teacher', type=Path)
    parser.add_argument('--export-approved', action='store_true')
    parser.add_argument('--overwrite', action='store_true')
    args = parser.parse_args()

    if args.import_teacher and args.export_approved:
        parser.error('Chỉ chọn --import-teacher hoặc --export-approved')

    if args.import_teacher:
        review_queue = read_json(args.queue_path)
        teacher_outputs = read_json(args.import_teacher)
        source_by_id = load_source_records(review_queue, args.data_dir)
        updated_queue = apply_teacher_outputs(
            review_queue,
            teacher_outputs,
            source_by_id,
        )
        write_json(args.queue_path, updated_queue)
        print(f'Đã nhập {len(teacher_outputs)} teacher output vào {args.queue_path}')
        return

    if args.export_approved:
        review_queue = read_json(args.queue_path)
        source_by_id = load_source_records(review_queue, args.data_dir)
        approved_targets = build_approved_targets(review_queue, source_by_id)
        write_json(args.approved_path, approved_targets)
        print(f'Đã xuất {len(approved_targets)} target approved: {args.approved_path}')
        return

    if args.queue_path.exists() and not args.overwrite:
        raise FileExistsError(
            f'Queue đã tồn tại: {args.queue_path}. Dùng --overwrite nếu muốn tạo lại.'
        )

    records = load_split(args.data_dir, args.split, args.limit)
    review_queue, skipped_ids = create_review_queue(
        records,
        endpoint_url=args.teacher_endpoint,
        api_key_env=args.api_key_env,
    )
    write_json(args.queue_path, review_queue)
    if not args.approved_path.exists():
        write_json(args.approved_path, [])

    print(f'Đã tạo {len(review_queue)} review record: {args.queue_path}')
    print(f'Số record FAIL bị bỏ qua: {len(skipped_ids)}')
    if not args.teacher_endpoint:
        print('Chưa cấu hình teacher; proposed_summary đang để null.')


if __name__ == '__main__':
    main()
