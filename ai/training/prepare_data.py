"""Đọc dataset v1 và chuyển từng hội thoại thành bản ghi dễ kiểm tra."""

import argparse
import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_DIR = PROJECT_ROOT / 'ai/data'
VALID_SPLITS = ('train', 'validation', 'test')


def read_json(path: Path):
    """Đọc JSON và báo rõ file bị lỗi."""
    if not path.exists():
        raise FileNotFoundError(f'Không tìm thấy file: {path}')

    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except json.JSONDecodeError as error:
        raise ValueError(f'JSON không hợp lệ trong {path}: {error}') from error


def parse_json_content(content, field_name: str, errors: list[str]):
    """Parse chuỗi JSON nằm trong message user hoặc assistant."""
    if not isinstance(content, str) or not content.strip():
        errors.append(f'{field_name} phải là chuỗi JSON không rỗng')
        return None

    try:
        return json.loads(content)
    except json.JSONDecodeError as error:
        errors.append(f'{field_name} chứa JSON không hợp lệ: {error.msg}')
        return None


def parse_conversation(row, sample_id: str, split: str, group_id: str | None = None):
    """Tách một dòng prompt-completion thành các thành phần của bài toán CV."""
    record = {
        'sample_id': sample_id,
        'split': split,
        'group_id': group_id,
        'system_prompt': None,
        'user_info': None,
        'original_cv': None,
        'job_description': None,
        'tailored_cv': None,
        'parse_errors': [],
    }
    errors = record['parse_errors']

    if not isinstance(row, dict):
        errors.append('Mẫu dữ liệu phải là object')
        return record

    prompt = row.get('prompt')
    completion = row.get('completion')
    if not isinstance(prompt, list) or len(prompt) != 2:
        errors.append('prompt phải có đúng hai message system và user')
        return record
    if not isinstance(completion, list) or len(completion) != 1:
        errors.append('completion phải có đúng một message assistant')
        return record

    system_message = prompt[0]
    user_message = prompt[1]
    assistant_message = completion[0]
    messages = [system_message, user_message, assistant_message]
    if not all(isinstance(message, dict) for message in messages):
        errors.append('Mỗi message phải là object')
        return record

    expected_roles = ['system', 'user', 'assistant']
    actual_roles = [message.get('role') for message in messages]
    if actual_roles != expected_roles:
        errors.append(f'Role không hợp lệ: {actual_roles}')

    record['system_prompt'] = system_message.get('content')
    user_content = parse_json_content(user_message.get('content'), 'prompt.user.content', errors)
    tailored_cv = parse_json_content(
        assistant_message.get('content'),
        'completion.assistant.content',
        errors,
    )

    if isinstance(user_content, dict):
        required_fields = {'user_info', 'original_cv', 'job_description'}
        missing_fields = sorted(required_fields - set(user_content))
        if missing_fields:
            errors.append(f'User content thiếu trường: {missing_fields}')
        record['user_info'] = user_content.get('user_info')
        record['original_cv'] = user_content.get('original_cv')
        record['job_description'] = user_content.get('job_description')
    elif user_content is not None:
        errors.append('prompt.user.content phải parse thành object')

    record['tailored_cv'] = tailored_cv

    # JSON hợp lệ vẫn có thể chứa sai kiểu dữ liệu ở các trường bên trong.
    if not isinstance(record['original_cv'], dict):
        errors.append('original_cv phải là object')
    if not isinstance(record['tailored_cv'], dict):
        errors.append('tailored_cv phải là object')
    if not isinstance(record['user_info'], dict):
        errors.append('user_info phải là object')
    if (
        not isinstance(record['job_description'], str)
        or not record['job_description'].strip()
    ):
        errors.append('job_description phải là chuỗi không rỗng')

    return record


def verify_sample_mapping(record, reference_record):
    """Đối chiếu sample_id với bản processed v1 để tránh lệch vị trí."""
    if record['parse_errors']:
        return

    fields = ['original_cv', 'job_description']
    for field in fields:
        if record[field] != reference_record[field]:
            raise ValueError(
                f'Assignment không khớp {field} của {record["sample_id"]}'
            )
    if record['tailored_cv'] != reference_record['target_cv']:
        raise ValueError(
            f'Assignment không khớp tailored_cv của {record["sample_id"]}'
        )


def load_split(data_dir: Path, split: str, limit: int | None = None):
    """Đọc một split v1 và khôi phục sample_id từ assignments.json."""
    if split not in VALID_SPLITS:
        raise ValueError(f'Split phải thuộc {VALID_SPLITS}')
    if limit is not None and limit <= 0:
        raise ValueError('limit phải lớn hơn 0')

    split_rows = read_json(data_dir / 'splits' / f'{split}.json')
    assignments = read_json(data_dir / 'splits' / 'assignments.json')
    split_assignments = [
        assignment
        for assignment in assignments
        if assignment.get('split') == split
    ]

    if len(split_rows) != len(split_assignments):
        raise ValueError(
            f'Số assignment của {split} không khớp số mẫu: '
            f'{len(split_assignments)} != {len(split_rows)}'
        )

    reference_rows = read_json(data_dir / 'processed' / 'rewritten_dataset.json')
    references_by_id = {
        record['sample_id']: record
        for record in reference_rows
    }

    records = []
    selected_rows = zip(split_rows, split_assignments)
    for row, assignment in selected_rows:
        sample_id = assignment['sample_id']
        record = parse_conversation(
            row,
            sample_id=sample_id,
            split=split,
            group_id=assignment.get('group_id'),
        )

        reference_record = references_by_id.get(sample_id)
        if reference_record is None:
            raise ValueError(f'Không tìm thấy sample_id trong processed v1: {sample_id}')
        verify_sample_mapping(record, reference_record)

        records.append(record)
        if limit is not None and len(records) == limit:
            break

    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--split', choices=VALID_SPLITS, default='train')
    parser.add_argument('--limit', type=int)
    parser.add_argument('--data-dir', type=Path, default=DEFAULT_DATA_DIR)
    args = parser.parse_args()

    records = load_split(args.data_dir, args.split, args.limit)
    parse_error_count = sum(bool(record['parse_errors']) for record in records)
    print(f'Split: {args.split}')
    print(f'Số mẫu đã đọc: {len(records)}')
    print(f'Số mẫu có lỗi parse: {parse_error_count}')
    if records:
        print(f'Sample ID đầu tiên: {records[0]["sample_id"]}')


if __name__ == '__main__':
    main()
