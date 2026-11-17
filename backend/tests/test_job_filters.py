"""Filtering must never guess currency, salary floors, or experience from JD text."""
import unittest
from pydantic import ValidationError
from backend.app.schemas.dashboard import JobPosting
from backend.app.services.job_filters import matches
from backend.app.services.job_importer import salary_metadata


def fixture(**overrides):
    values=dict(posting_id='posting_'+'a'*24,title='C++ Backend Engineer',company='QA',
                description='Python SQL 100% remote',source_name='fixture',external_id='1',
                imported_at='2026-11-09T00:00:00Z')
    values.update(overrides)
    return JobPosting(**values)


class JobFilterTests(unittest.TestCase):
    def test_salary_floor_requires_same_explicit_unit_and_currency(self):
        job=fixture(salary_min=20_000_000,salary_max=30_000_000,salary_currency='VND',salary_period='month')
        self.assertTrue(matches(job,salary_min=15_000_000))
        self.assertFalse(matches(job,salary_min=25_000_000))
        self.assertFalse(matches(job,salary_min=100,salary_currency='USD'))
        self.assertFalse(matches(job,salary_min=100,salary_period='year'))

    def test_unknown_metadata_is_not_inferred(self):
        job=fixture(salary='20–30 triệu/tháng',description='Senior Python developer in IT')
        self.assertFalse(matches(job,salary_min=1))
        self.assertFalse(matches(job,experience_level='Senior'))
        self.assertFalse(matches(job,industry='IT'))
        self.assertTrue(matches(job))

    def test_terms_and_punctuation_are_literal(self):
        self.assertTrue(matches(fixture(),q='SQL C++ 100%'))
        self.assertFalse(matches(fixture(),q='C++ Ruby'))
        self.assertFalse(matches(fixture(),q='_'))

    def test_source_metadata_and_saved_are_combined(self):
        job=fixture(industry='Software',experience_level='Senior',saved=True)
        self.assertTrue(matches(job,industry='Software',experience_level='Senior',saved=True))
        self.assertFalse(matches(job,industry='Finance',saved=True))

    def test_reversed_and_nonfinite_salary_rejected(self):
        for values in [dict(salary_min=30,salary_max=20),dict(salary_min=float('nan')),dict(salary_min=-1)]:
            with self.assertRaises(ValidationError):fixture(**values)

    def test_importer_keeps_unknown_units_unknown(self):
        self.assertIsNone(salary_metadata(100,200,None,None)['salary_currency'])
        self.assertIsNone(salary_metadata(100,200,'USD','unknown')['salary_period'])
        self.assertEqual(salary_metadata(100,200,'usd','YEAR')['salary_period'],'year')
        self.assertEqual(salary_metadata(200,100,'USD','year'),{})

    def test_filter_metadata_changes_snapshot_identity(self):
        from backend.app.db.job_posting_repository import source_hash
        first=fixture(salary_min=100,salary_currency='USD',salary_period='year')
        second=first.model_copy(update={'salary_min':200})
        self.assertNotEqual(source_hash(first),source_hash(second))
