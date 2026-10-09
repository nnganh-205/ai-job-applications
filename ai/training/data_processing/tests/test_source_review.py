import unittest
from test_data_processing import row
from ai.training.data_processing.apply_source_review import apply_reviews, checksum, normalize_reviewed_cv


class SourceReviewTests(unittest.TestCase):
    def make_record(self):
        r = row()
        r['review_reasons'] = [{'code': 'missing_experience_identity'}]
        for field in ['original_cv','target_cv']:
            r[field]['experience'][0]['dates'] = '05/XXX1 to 04/XXX2'
        return r

    def test_keep_normalizes_both_sides_without_inventing_dates(self):
        r = self.make_record()
        d = {'sample_id':'a','record_sha256':checksum(r),
             'recommendation':'retain_with_constraints','reason':'Masked dates','category':'masked_dates'}
        kept, rejected, changes = apply_reviews([r],[d])
        self.assertFalse(rejected)
        self.assertEqual(len(changes),1)
        self.assertIsNone(kept[0]['original_cv']['experience'][0]['dates'])
        self.assertIsNone(kept[0]['target_cv']['experience'][0]['dates'])
        self.assertTrue(kept[0]['requires_manual_review'])
        self.assertEqual(r['original_cv']['experience'][0]['dates'],'05/XXX1 to 04/XXX2')

    def test_excludes_only_decided_sample_and_rejects_stale_review(self):
        r = self.make_record()
        d = {'sample_id':'a','record_sha256':checksum(r),
             'recommendation':'exclude_until_repaired','reason':'Broken timeline','category':'timeline'}
        kept, rejected, _ = apply_reviews([r,row('b')],[d])
        self.assertEqual([x['sample_id'] for x in kept],['b'])
        self.assertEqual(len(rejected),1)
        d['record_sha256']='stale'
        with self.assertRaises(ValueError):apply_reviews([r],[d])
        with self.assertRaises(ValueError):apply_reviews([r],[])

    def test_does_not_change_unknown_prose_or_completed_status(self):
        r = row()['original_cv']
        r['summary']='Discovered previously unknown insights'
        r['education']=[{'degree':'MS','institution':'Unknown','dates':'25% Completed'}]
        result=normalize_reviewed_cv(r)
        self.assertEqual(result['summary'],r['summary'])
        self.assertIsNone(result['education'][0]['institution'])
        self.assertEqual(result['education'][0]['dates'],'25% Completed')
