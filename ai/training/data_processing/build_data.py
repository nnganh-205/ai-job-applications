"""Tái tạo dữ liệu từ bản gốc, viết lại và xuất các tập huấn luyện."""
import argparse
import hashlib
import json
from pathlib import Path

from .apply_source_review import apply_reviews
from .clean_data import clean_records
from .data_io import read_json, write_json
from .export_data import export
from .prepare_data import ROOT, prepare_record
from .rewrite_data import save_rewrites

# Chỉ dọn file trung gian của pipeline, không xóa file người dùng khác.
INTERMEDIATE_FILES = [
    'review_dataset.json', 'report.json', 'audit_results.json', 'audit_report.json',
    'cleaned_candidates.json', 'cleaning_changes.json', 'cleaning_report.json',
    'flagged_source_review.json', 'flagged_source_review.csv', 'flagged_source_review_report.json',
    'source_review_report.json', 'needs_review.json', 'rejected_sources.json',
]


def load_raw_records(data_dir):
    """Kiểm tra bản gốc rồi chuẩn bị từng mẫu."""
    raw_dir = data_dir / 'raw'
    manifest = read_json(raw_dir / 'manifest.json')
    prepared_records = []

    for split in ['train', 'validation', 'test']:
        path = raw_dir / f'{split}.json'
        expected = manifest['splits'][split]
        actual_checksum = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual_checksum != expected['sha256']:
            raise ValueError(f'Raw checksum mismatch: {split}')

        raw_records = read_json(path)
        if len(raw_records) != expected['rows']:
            raise ValueError(f'Raw row count mismatch: {split}')

        for index, row in enumerate(raw_records):
            prepared_records.append(prepare_record(row, split, index))

    return prepared_records


def remove_intermediate_files(folder):
    """Dọn bản trung gian sau khi bản cuối đã được kiểm tra."""
    deleted = []
    for name in INTERMEDIATE_FILES:
        path = folder / name
        if path.exists():
            path.unlink()
            deleted.append(name)
    return deleted


def build(data_dir):
    # 1. Chuẩn bị và tạo đáp án từ nội dung nguồn.
    prepared_records = load_raw_records(data_dir)
    cleaned_records, rejected_records, _cleaning_changes = clean_records(prepared_records)
    if rejected_records:
        raise ValueError('New invalid sources: review decisions must be updated')

    # 2. Áp dụng quyết định duyệt 35 mẫu.
    decisions_path = Path(__file__).with_name('source_review_decisions.json')
    decisions = read_json(decisions_path)
    selected_records, excluded_records, source_changes = apply_reviews(
        cleaned_records,
        decisions,
    )

    # 3. Viết lại và xuất các tập train/validation/test.
    processed_dir = data_dir / 'processed'
    processed_dir.mkdir(parents=True, exist_ok=True)
    rewritten_records, rewrite_report = save_rewrites(
        selected_records,
        processed_dir,
    )
    export_report = export(rewritten_records, data_dir / 'splits')

    # 4. Lưu kết quả duyệt nguồn rồi dọn bản trung gian.
    write_json(processed_dir / 'excluded_by_source_review.json', excluded_records)
    write_json(processed_dir / 'source_review_changes.json', source_changes)
    deleted = remove_intermediate_files(processed_dir)

    return {
        'rewrite': rewrite_report,
        'export': export_report,
        'deleted_intermediates': deleted,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, default=ROOT / 'ai/data')
    args = parser.parse_args()
    report = build(args.data_dir)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
