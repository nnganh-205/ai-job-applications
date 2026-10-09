import copy
import json
from pathlib import Path
import tempfile
import unittest
from test_data_processing import row
from ai.training.data_processing.export_data import assign_groups, export, split_records, to_training_row


class ExportTests(unittest.TestCase):
    def test_variants_remain_in_same_group(self):
        a=row('a');b=row('b','test')
        b['original_cv']['summary']='Rephrased summary'
        b['original_cv']['experience'][0]['bullet_points']=['Changed wording']
        groups=assign_groups([a,b])
        self.assertEqual(len(groups),1)
        _, assignments=split_records([a,b])
        self.assertEqual(len({r['split'] for r in assignments}),1)

    def test_chat_format_has_no_answer_in_user_input(self):
        r=row();result=to_training_row(r)
        self.assertEqual([x['role'] for x in result['prompt']],['system','user'])
        self.assertEqual(result['completion'][0]['role'],'assistant')
        user=json.loads(result['prompt'][1]['content'])
        self.assertEqual(set(user),{'user_info','original_cv','job_description'})
        self.assertEqual(json.loads(result['completion'][0]['content']),r['target_cv'])

    def test_duplicate_pairs_removed_and_deterministic(self):
        a=row('a');b=row('b')
        with tempfile.TemporaryDirectory() as tmp:
            report=export([a,b],Path(tmp))
            self.assertEqual(report['exported_samples'],1)
            before={p.name:p.read_bytes() for p in Path(tmp).iterdir()}
            export([a,b],Path(tmp))
            self.assertEqual(before,{p.name:p.read_bytes() for p in Path(tmp).iterdir()})

    def test_export_rejects_new_skill(self):
        r=row();r['target_cv']['skills']['tools']=['AWS']
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):export([r],Path(tmp))
