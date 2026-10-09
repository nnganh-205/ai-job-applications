import copy
import unittest
from ai.training.data_processing.clean_data import clean_records, assert_source_only, make_source_only_target
from test_data_processing import cv, row


class CleaningTests(unittest.TestCase):
    def test_removes_hallucinated_summary_metrics_skills_and_company(self):
        record = row()
        record['target_cv']['summary'] = 'Salesforce expert with 10 years experience'
        record['target_cv']['skills']['tools'] = ['AWS']
        record['target_cv']['experience'][0]['company'] = 'Invented'
        record['target_cv']['experience'][0]['bullet_points'] = ['Managed 40 staff']
        candidates, rejected, log = clean_records([record])
        self.assertFalse(rejected)
        target = candidates[0]['target_cv']
        assert_source_only(record['original_cv'], target)
        self.assertEqual(target['summary'], 'Developer')
        self.assertEqual(target['skills']['tools'], [])
        self.assertEqual(target['experience'][0]['company'], 'A')
        self.assertTrue(candidates[0]['requires_manual_review'])
        self.assertTrue(log[0]['changed_paths'])

    def test_prioritizes_jd_skills_and_bullets_without_mutating_source(self):
        source = cv()
        source['skills']['languages'] = ['Java', 'Python']
        source['experience'][0]['bullet_points'] = ['Built Java apps', 'Built Python APIs']
        saved = copy.deepcopy(source)
        target = make_source_only_target(source, 'Python developer')
        self.assertEqual(target['skills']['languages'], ['Python','Java'])
        self.assertEqual(target['experience'][0]['bullet_points'][0], 'Built Python APIs')
        self.assertEqual(source, saved)
        assert_source_only(source, target)
        target['summary'] = 'Invented experience'
        with self.assertRaises(ValueError):
            assert_source_only(source, target)

    def test_rejects_invalid_source_even_when_target_valid(self):
        record = row()
        del record['original_cv']['experience'][0]['dates']
        candidates, rejected, _ = clean_records([record])
        self.assertFalse(candidates)
        self.assertEqual(len(rejected),1)


if __name__ == '__main__':
    unittest.main()
