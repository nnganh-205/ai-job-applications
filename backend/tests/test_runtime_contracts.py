"""Regression coverage for import provenance and PostgreSQL feed persistence."""
import unittest
from unittest.mock import patch
from pydantic import ValidationError
from backend.app.schemas.dashboard import JobImportRequest
from backend.app.services.job_importer import himalayas_job, is_expired, sync_state


class RuntimeContractTests(unittest.TestCase):
    def test_text_can_keep_source_without_fetching(self):
        from backend.app.services.job_importer import import_job
        request = JobImportRequest(source_url='https://www.topcv.vn/viec-lam/example', job_description_text='Backend Engineer\n' + 'Python PostgreSQL experience. ' * 4)
        with patch('backend.app.services.job_importer.fetch_job_content', side_effect=AssertionError('Must not fetch pasted text')), patch('backend.app.services.job_importer.upsert_posting', side_effect=lambda job: (job, 'inserted')):
            job = import_job(request)
        self.assertEqual(job.source_name, 'TopCV')
        self.assertEqual(job.import_method, 'text')
        self.assertIsNone(job.fetched_at)

    def test_invalid_source_urls_rejected(self):
        for url in ['javascript:alert(1)', 'https://user:password@example.com']:
            with self.assertRaises(ValidationError):
                JobImportRequest(source_url=url)

    def test_feed_metadata_survives_validation(self):
        job = himalayas_job(dict(guid='https://himalayas.app/jobs/example', applicationLink='https://himalayas.app/jobs/example', title='Backend Engineer', description='Python developer', locationRestrictions=['Vietnam'], timezoneRestrictions=['Asia/Ho_Chi_Minh'], expiryDate='2020-01-01'))
        self.assertTrue(is_expired(job))
        self.assertEqual(job.location_restrictions, ['Vietnam'])

    def test_sync_uses_repository(self):
        with patch('backend.app.services.job_importer.read_aux', return_value={'attempted_at': 'saved'}) as read:
            self.assertEqual(sync_state(), {'attempted_at': 'saved'})
            read.assert_called_once_with('feed_state', 'current')
