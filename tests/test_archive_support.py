import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock,patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import archive_support as a


class ArchiveTests(unittest.TestCase):
    def test_archived_notebook_resolves(self):
        self.assertEqual(a.resolve_path(a.ROOT/'notebooks/EDA.ipynb'),a.ROOT/'research/archive/notebooks/fipi-50-EDA.ipynb')

    def test_existing_file_is_not_redirected(self):
        self.assertEqual(a.resolve_path(a.ROOT/'README.md'),a.ROOT/'README.md')

    def test_corrupt_expected_hash_rejected(self):
        data=json.loads(a.MAP.read_text(encoding='utf-8'))
        entry=next(e for e in data['files'] if e['old']=='notebooks/EDA.ipynb');entry['sha256']='0'*64
        fake=Mock();fake.read_text.return_value=json.dumps(data)
        with patch.object(a,'MAP',fake):
            with self.assertRaises(ValueError):a.resolve_path(a.ROOT/'notebooks/EDA.ipynb')

    def test_path_escape_rejected(self):
        data=json.loads(a.MAP.read_text(encoding='utf-8'))
        entry=next(e for e in data['files'] if e['old']=='notebooks/EDA.ipynb');entry['new']='README.md'
        fake=Mock();fake.read_text.return_value=json.dumps(data)
        with patch.object(a,'MAP',fake):
            with self.assertRaises(ValueError):a.resolve_path(a.ROOT/'notebooks/EDA.ipynb')


if __name__=='__main__':unittest.main()
