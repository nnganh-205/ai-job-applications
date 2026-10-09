import hashlib
from pathlib import Path
import tempfile
import unittest
from ai.training.data_processing.data_io import read_json, write_json


class DataIOTests(unittest.TestCase):
    def test_multiline_json_preserves_nested_values_and_unicode(self):
        rows = [{'name': 'Nguyễn Anh', 'cv': {'skills': ['Python', 'SQL']},
                 'content': 'Line one\nLine two', 'missing': None}]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'data.json'
            checksum = write_json(path, rows)
            self.assertEqual(read_json(path), rows)
            self.assertIn('  {\n', path.read_text())
            self.assertEqual(checksum, hashlib.sha256(path.read_bytes()).hexdigest())

    def test_empty_list_and_report_object_are_readable(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'data.json'
            for data in [[], {'count': 589, 'checks': 'passed'}]:
                write_json(path, data)
                self.assertEqual(read_json(path), data)
