import unittest
from ai.training.review_pack import assert_isolated,build,jd_groups
from backend.app.schemas.dashboard import JobPosting


def jobs():
    return [JobPosting(posting_id='posting_'+f'{i:024x}',title=f'Fixture role {i}',description=(' '.join(f'unique{i}word{j}' for j in range(60))),source_name='fixture',external_id=str(i),imported_at='2026-11-09T00:00:00Z',content_hash=str(i)) for i in range(20)]


class ReviewPackTests(unittest.TestCase):
    def test_splits_keep_both_cv_families_and_jd_groups_isolated(self):
        rows,manifest=build(jobs())
        self.assertEqual(len(rows),180)
        self.assertFalse(manifest['training_ready'])
        self.assertTrue(all(r['annotation']['status']=='pending' and r['annotation']['cv_plan'] is None for r in rows))
        assert_isolated(rows)
        self.assertEqual({r['split'] for r in rows},{'train','validation','test'})

    def test_near_duplicate_jobs_stay_in_one_group(self):
        sample=jobs();sample[1]=sample[1].model_copy(update={'description':sample[0].description,'content_hash':sample[0].content_hash})
        grouped=jd_groups(sample)
        self.assertEqual(grouped[sample[0].posting_id],grouped[sample[1].posting_id])

    def test_cross_fold_cv_reuse_is_rejected(self):
        with self.assertRaises(ValueError):assert_isolated([{'cv_identity':'same','jd_group':'a','split':'train'},{'cv_identity':'same','jd_group':'b','split':'test'}])
