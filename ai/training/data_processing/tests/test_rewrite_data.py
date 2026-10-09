import unittest
from test_data_processing import row
from ai.training.data_processing.rewrite_data import rewrite_records, rewrite_bullet, validate_rewritten_record


class RewriteTests(unittest.TestCase):
    def test_summary_uses_source_roles_and_skills_not_jd_requirements(self):
        record=row()
        record['job_description']='AWS engineer with 10 years experience managing 40 staff'
        records,_=rewrite_records([record])
        summary=records[0]['target_cv']['summary']
        self.assertNotIn('AWS',summary)
        self.assertNotIn('10 years',summary)
        self.assertNotIn('40',summary)
        self.assertIn('Python',summary)
        self.assertEqual(records[0]['original_cv'],record['original_cv'])

    def test_bullet_preserves_numbers_and_responsibility(self):
        self.assertEqual(rewrite_bullet('I was responsible for 30% of Python tests'),
                         'Responsible for 30% of Python tests.')
        self.assertEqual(rewrite_bullet('Involved in testing 5 APIs'),
                         'Contributed to testing 5 APIs.')
        self.assertEqual(rewrite_bullet('Not involved in AWS development.'),
                         'Not involved in AWS development.')
        self.assertEqual(rewrite_bullet('Assisted the team with 20 tests.'),
                         'Assisted the team with 20 tests.')

    def test_detects_invented_metrics_titles_and_evidence(self):
        for modification in ['metric','title','evidence']:
            records,_=rewrite_records([row()]);record=records[0]
            if modification=='metric':record['target_cv']['experience'][0]['bullet_points'][0]+=' Led 40 staff.'
            elif modification=='title':record['target_cv']['experience'][0]['title']='Manager'
            else:record['summary_evidence'][0]['text']='Invented'
            with self.assertRaises(ValueError):validate_rewritten_record(record)

    def test_export_accepts_only_traceable_rewrites(self):
        from ai.training.data_processing.export_data import export
        from pathlib import Path
        import tempfile
        records,_=rewrite_records([row()])
        with tempfile.TemporaryDirectory() as tmp:
            report=export(records,Path(tmp))
            self.assertEqual(report['purpose'],'Grounded editorial rewriting')
