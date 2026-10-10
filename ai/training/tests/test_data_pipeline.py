"""Kiểm tra cơ bản cho parser và validator dataset v2."""

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from ai.training.prepare_data import (
    load_split,
    parse_conversation,
    verify_sample_mapping,
)
from ai.training.improve_targets import (
    build_approved_targets,
    make_review_record,
    validate_teacher_output,
)
from ai.training.validate_data import (
    immutable_errors,
    validate_cv_schema,
    validate_record,
)


def make_cv():
    return {
        'personal_info': {
            'name': 'Nguyen Van A',
            'email': 'a@example.com',
            'phone': None,
            'location': 'Hanoi',
            'links': [],
        },
        'summary': 'Backend developer.',
        'skills': {
            'languages': ['Python'],
            'frameworks': ['FastAPI'],
            'tools': ['Git'],
            'domain_skills': ['REST API'],
        },
        'experience': [{
            'title': 'Backend Developer',
            'company': 'Example Company',
            'dates': '2023 - 2024',
            'bullet_points': ['Built REST APIs with Python.'],
        }],
        'projects': [{
            'title': 'Job Platform',
            'tech_stack': ['Python'],
            'description': 'A job search platform.',
            'bullet_points': ['Developed the backend API.'],
        }],
        'education': [{
            'degree': 'Computer Science',
            'institution': 'Example University',
            'dates': '2020 - 2024',
        }],
        'awards': [],
        'leadership': [],
    }


def make_parsed_record():
    original_cv = make_cv()
    tailored_cv = deepcopy(original_cv)
    tailored_cv['summary'] = (
        'Experience in roles including Backend Developer. '
        'Skills include Python, FastAPI, Git.'
    )
    return {
        'sample_id': 'train_000001',
        'split': 'train',
        'group_id': 'group_1',
        'system_prompt': 'Return JSON.',
        'user_info': {},
        'original_cv': original_cv,
        'job_description': 'Looking for a Python backend developer.',
        'tailored_cv': tailored_cv,
        'parse_errors': [],
    }


class DataPipelineTests(unittest.TestCase):
    def test_parser_restores_sample_id(self):
        original_cv = make_cv()
        tailored_cv = deepcopy(original_cv)
        user_content = {
            'user_info': {},
            'original_cv': original_cv,
            'job_description': 'Looking for a Python backend developer.',
        }
        conversation = {
            'prompt': [
                {'role': 'system', 'content': 'Return JSON.'},
                {'role': 'user', 'content': json.dumps(user_content)},
            ],
            'completion': [{
                'role': 'assistant',
                'content': json.dumps(tailored_cv),
            }],
        }
        reference_record = {
            'sample_id': 'train_000001',
            'original_cv': original_cv,
            'job_description': user_content['job_description'],
            'target_cv': tailored_cv,
        }

        with tempfile.TemporaryDirectory() as temporary_dir:
            data_dir = Path(temporary_dir)
            (data_dir / 'splits').mkdir()
            (data_dir / 'processed').mkdir()
            (data_dir / 'splits' / 'train.json').write_text(
                json.dumps([conversation]),
                encoding='utf-8',
            )
            (data_dir / 'splits' / 'assignments.json').write_text(
                json.dumps([{
                    'sample_id': 'train_000001',
                    'group_id': 'group_1',
                    'split': 'train',
                    'source_split': 'train',
                }]),
                encoding='utf-8',
            )
            (data_dir / 'processed' / 'rewritten_dataset.json').write_text(
                json.dumps([reference_record]),
                encoding='utf-8',
            )

            records = load_split(data_dir, 'train')

        self.assertEqual(records[0]['sample_id'], 'train_000001')
        self.assertEqual(records[0]['original_cv'], original_cv)
        self.assertEqual(records[0]['tailored_cv'], tailored_cv)
        self.assertEqual(records[0]['parse_errors'], [])

    def test_parser_rejects_wrong_user_content_types(self):
        user_content = {
            'user_info': [],
            'original_cv': [],
            'job_description': '   ',
        }
        conversation = {
            'prompt': [
                {'role': 'system', 'content': 'Return JSON.'},
                {'role': 'user', 'content': json.dumps(user_content)},
            ],
            'completion': [{
                'role': 'assistant',
                'content': json.dumps(make_cv()),
            }],
        }

        record = parse_conversation(conversation, 'train_000001', 'train')
        validation = validate_record(record)

        self.assertIn('original_cv phải là object', record['parse_errors'])
        self.assertIn('user_info phải là object', record['parse_errors'])
        self.assertIn(
            'job_description phải là chuỗi không rỗng',
            record['parse_errors'],
        )
        self.assertEqual(validation['status'], 'FAIL')

    def test_parser_rejects_wrong_completion_type(self):
        user_content = {
            'user_info': {},
            'original_cv': make_cv(),
            'job_description': 'Python backend developer.',
        }
        conversation = {
            'prompt': [
                {'role': 'system', 'content': 'Return JSON.'},
                {'role': 'user', 'content': json.dumps(user_content)},
            ],
            'completion': [{
                'role': 'assistant',
                'content': json.dumps([]),
            }],
        }

        record = parse_conversation(conversation, 'train_000001', 'train')
        validation = validate_record(record)

        self.assertIn('tailored_cv phải là object', record['parse_errors'])
        self.assertEqual(validation['status'], 'FAIL')

    def test_assignment_mismatch_is_detected(self):
        original_cv = make_cv()
        record = {
            'sample_id': 'train_000001',
            'original_cv': original_cv,
            'job_description': 'Python backend developer.',
            'tailored_cv': deepcopy(original_cv),
            'parse_errors': [],
        }
        wrong_reference = {
            'original_cv': make_cv(),
            'job_description': 'Different job description.',
            'target_cv': deepcopy(original_cv),
        }

        with self.assertRaises(ValueError):
            verify_sample_mapping(record, wrong_reference)

    def test_missing_evidence_source_is_flagged(self):
        record = make_parsed_record()
        teacher_output = {
            'summary': (
                'Backend developer with experience building REST APIs using Python '
                'and FastAPI for a job search platform. Brings practical experience '
                'developing backend services and using Git in software projects.'
            ),
            'evidence': [{
                'claim': 'Experience deploying systems on AWS',
                'source': 'Deployed production systems on AWS.',
            }],
        }

        status, reasons = validate_teacher_output(teacher_output, record)

        self.assertEqual(status, 'REVIEW')
        self.assertTrue(any('không xuất hiện nguyên văn' in reason for reason in reasons))

    def test_empty_or_wrong_summary_is_rejected(self):
        record = make_parsed_record()
        for invalid_summary in ['', None, []]:
            with self.subTest(summary=invalid_summary):
                status, reasons = validate_teacher_output(
                    {'summary': invalid_summary, 'evidence': []},
                    record,
                )
                self.assertEqual(status, 'FAIL')
                self.assertTrue(any('Summary' in reason for reason in reasons))

    def test_old_summary_template_is_flagged(self):
        record = make_parsed_record()
        teacher_output = {
            'summary': (
                'Experience in roles including Backend Developer. '
                'Skills include Python, FastAPI, Git, and REST API development.'
            ),
            'evidence': [],
        }

        status, reasons = validate_teacher_output(teacher_output, record)

        self.assertEqual(status, 'REVIEW')
        self.assertTrue(any('khuôn mẫu v1' in reason for reason in reasons))

    def test_pending_record_cannot_be_exported(self):
        record = make_parsed_record()
        review_record = make_review_record(record)

        approved_targets = build_approved_targets([review_record], [record])

        self.assertEqual(approved_targets, [])

    def test_only_summary_changes_in_approved_target(self):
        record = make_parsed_record()
        teacher_output = {
            'summary': (
                'Backend developer experienced in building REST APIs with Python '
                'and FastAPI for a job search platform. Offers hands-on backend '
                'development experience supported by practical use of Git and '
                'API-focused project work.'
            ),
            'evidence': [
                {
                    'claim': 'Built REST APIs with Python',
                    'source': 'Built REST APIs with Python.',
                },
                {
                    'claim': 'Worked on a job search platform',
                    'source': 'A job search platform.',
                },
            ],
        }
        review_record = make_review_record(record, teacher_output)
        review_record['approval_status'] = 'approved'

        approved_targets = build_approved_targets([review_record], [record])
        new_target = approved_targets[0]['target_cv']
        old_without_summary = deepcopy(record['tailored_cv'])
        new_without_summary = deepcopy(new_target)
        old_without_summary.pop('summary')
        new_without_summary.pop('summary')

        self.assertEqual(old_without_summary, new_without_summary)
        self.assertNotEqual(
            record['tailored_cv']['summary'],
            new_target['summary'],
        )
        self.assertEqual(approved_targets[0]['sample_id'], record['sample_id'])
        self.assertEqual(approved_targets[0]['split'], record['split'])

    def test_nested_schema_detects_missing_field(self):
        cv = make_cv()
        self.assertEqual(validate_cv_schema(cv), [])

        del cv['experience'][0]['bullet_points']
        errors = validate_cv_schema(cv)
        self.assertTrue(any('experience[0]' in error for error in errors))

    def test_immutable_fields_detect_company_change(self):
        original_cv = make_cv()
        tailored_cv = deepcopy(original_cv)
        tailored_cv['experience'][0]['company'] = 'Another Company'

        errors = immutable_errors(original_cv, tailored_cv)

        self.assertTrue(any('company' in error for error in errors))


if __name__ == '__main__':
    unittest.main()
