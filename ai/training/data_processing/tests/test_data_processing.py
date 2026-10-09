import copy
import json
from pathlib import Path
import tempfile
import unittest

from ai.training.data_processing.data_io import write_json
from ai.training.data_processing.prepare_data import normalize, parse_input, schema_errors, audit_facts
from ai.training.data_processing.audit_data import audit_content, audit_records, literal_supported


def cv():
    return {'personal_info': {'name': 'Test', 'email': None, 'phone': None, 'location': None, 'links': []},
            'summary': 'Developer', 'experience': [
                {'title': 'Developer', 'company': 'A', 'dates': '2020–2021', 'bullet_points': ['Python API improved throughput 30%']},
                {'title': 'Engineer', 'company': 'B', 'dates': '2022–2023', 'bullet_points': ['Built Java applications']}],
            'projects': [], 'skills': {'languages': ['Python'], 'frameworks': [], 'tools': [], 'domain_skills': []},
            'education': [], 'awards': [], 'leadership': []}


def row(identifier='a', split='train'):
    source = cv()
    return {'sample_id': identifier, 'source_split': split, 'instruction': 'Tailor', 'original_cv': source,
            'job_description': 'Python AWS', 'target_cv': copy.deepcopy(source),
            'review_status': 'pending', 'review_reasons': []}


class DataProcessingTests(unittest.TestCase):
    def test_parse_nested_json_and_missing_jd(self):
        source = cv()
        parsed, jd = parse_input('MASTER RESUME: '+json.dumps(source)+'\nJOB DESCRIPTION: content } here')
        self.assertEqual(parsed, source)
        self.assertEqual(jd, 'content } here')
        with self.assertRaises(ValueError):
            parse_input('MASTER RESUME: '+json.dumps(source))

    def test_normalization_does_not_infer_dates(self):
        changes = []
        self.assertEqual(normalize({'dates': ' XXX1 ', 'skills': ['Python', '', 'null']}, changes=changes),
                         {'dates': 'XXX1', 'skills': ['Python']})
        self.assertTrue(changes)

    def test_schema_missing_field(self):
        source = cv()
        self.assertEqual(schema_errors(source), [])
        del source['experience'][0]['bullet_points']
        self.assertTrue(schema_errors(source))

    def test_identity_reorder_allowed_changes_and_duplicates_flagged(self):
        source = cv(); target = copy.deepcopy(source)
        target['experience'].reverse()
        self.assertEqual(audit_facts(source, target), [])
        target['experience'][0]['company'] = 'Fake'
        self.assertTrue(any(i['code']=='experience_identity_changed' for i in audit_facts(source,target)))
        target = copy.deepcopy(source)
        target['experience'].append(copy.deepcopy(target['experience'][0]))
        self.assertTrue(any(i['code']=='experience_identity_changed' for i in audit_facts(source,target)))

    def test_literal_evidence_whole_cv_and_boundaries(self):
        source = cv()
        self.assertTrue(literal_supported('Python', source))
        self.assertFalse(literal_supported('C', source))
        self.assertFalse(literal_supported('AWS', source))
        record = row(); record['target_cv']['skills']['tools'] = ['AWS']
        candidates = next(i for i in audit_content(record) if i['code']=='skills_without_literal_source_evidence')
        self.assertTrue(candidates['candidates'][0]['appears_in_jd'])

    def test_metrics_moved_to_another_job_are_flagged(self):
        record = row()
        record['target_cv']['experience'][1]['bullet_points'] = ['Improved throughput 30%']
        self.assertTrue(any(i['code']=='new_numbers_in_section' and i['path']=='target_cv.experience[1]'
                            for i in audit_content(record)))

    def test_cross_split_overlap_and_duplicate_pairs(self):
        results, report = audit_records([row('a','train'), row('b','test')])
        self.assertEqual(report['cross_split_cv_overlap']['train/test'],1)
        self.assertTrue(any(i['code']=='duplicate_cv_jd_pair' for i in results[0]['audit_issues']))
        with self.assertRaises(ValueError):
            audit_records([row(),row()])

    def test_snapshot_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'raw.json'
            write_json(path,[{'original':'A'}],immutable=True)
            write_json(path,[{'original':'A'}],immutable=True)
            with self.assertRaises(RuntimeError):
                write_json(path,[{'original':'B'}],immutable=True)


if __name__ == '__main__':
    unittest.main()
