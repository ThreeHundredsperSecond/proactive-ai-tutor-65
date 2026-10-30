"""Failure-injection tests of the checks that protect this small analysis.

Fixtures are copies of saved responses, not new mathematical examples.
"""
import copy
import json
import tempfile
import unittest
from pathlib import Path

import analyze as a


class AnalysisChecks(unittest.TestCase):
    def setUp(self):
        self.case = a.read(a.HERE / 'inputs/context-state-r1.json')['cases'][0]
        self.row = copy.deepcopy(a.read(a.HERE / 'raw/context-state-r1.json')['rows'][0])
        self.sources = {'current': self.case['current'],
                        **{c['id']: c['text'] for c in self.case['context']}}

    def check_row(self, row):
        quotes = []
        a.validate_application(row, self.case['candidate'], self.sources, 'fixture', quotes)
        return quotes

    def test_saved_row_passes(self):
        self.assertTrue(all(q['literal_match'] for q in self.check_row(self.row)))

    def test_context_cannot_be_current_operation(self):
        self.row['operation_evidence'] = [{'source': 'before_s3',
                                           'quote': self.sources['before_s3']}]
        self.assertTrue(any(not q['literal_match'] for q in self.check_row(self.row)))

    def test_nonliteral_punctuation_is_rejected(self):
        # Neither normalizing the Unicode minus nor smoothing punctuation is allowed.
        e = self.row['operation_evidence'][0]
        e['quote'] = e['quote'].replace('−', '-')
        self.assertTrue(any(not q['literal_match'] for q in self.check_row(self.row)))

    def test_unavailable_source_is_rejected(self):
        self.row['input_evidence'][0]['source'] = 'before_s999'
        self.assertTrue(any(not q['literal_match'] for q in self.check_row(self.row)))

    def test_wrong_support_is_rejected(self):
        self.row['support'] = 'conditional_application'
        with self.assertRaisesRegex(ValueError, 'support rule'):
            self.check_row(self.row)

    def test_absent_precondition_is_rejected(self):
        self.row['preconditions'].pop()
        with self.assertRaisesRegex(ValueError, 'identifiers'):
            self.check_row(self.row)

    def test_duplicated_case_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'identifiers'):
            a.unique([self.row, self.row], 'id', {'Q01'}, 'fixture')

    def test_known_requires_evidence(self):
        self.row['preconditions'][0]['evidence'] = []
        with self.assertRaisesRegex(ValueError, 'evidence absent'):
            self.check_row(self.row)

    def test_checked_in_current_requires_current_source(self):
        self.row['preconditions'][0]['checked_in_current'] = True
        with self.assertRaisesRegex(ValueError, 'checked source'):
            self.check_row(self.row)

    def test_byte_change_breaks_freeze(self):
        # Keep the generated fixture and automatic cleanup inside this task folder.
        with tempfile.TemporaryDirectory(dir=a.HERE) as tmp:
            base = Path(tmp)
            self.assertEqual(base.resolve().parent, a.HERE)
            p = base / 'input.txt'
            p.write_bytes(b'original\n')
            manifest = {'files': [{'path': p.name, 'sha256': a.sha(p)}]}
            self.assertTrue(a.hash_checks(manifest, base)[0]['match'])
            p.write_bytes(b'original\r\n')
            self.assertFalse(a.hash_checks(manifest, base)[0]['match'])

    def test_corrupted_raw_copy_is_rejected_even_when_json_is_valid(self):
        manifest = a.read(a.HERE / 'captures.json')
        with tempfile.TemporaryDirectory(dir=a.HERE) as tmp:
            base = Path(tmp)
            self.assertEqual(base.resolve().parent, a.HERE)
            (base / 'raw').mkdir()
            for entry in manifest['files']:
                (base / entry['path']).write_bytes((a.HERE / entry['path']).read_bytes())
            self.assertTrue(all(c['match'] for c in a.capture_checks(manifest, base)))
            altered = base / 'raw/context-state-r1.json'
            obj = a.read(altered)
            obj['rows'][0]['note'] += ' Changed copy for corruption test.'
            altered.write_text(json.dumps(obj, ensure_ascii=False), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'Raw capture hash mismatch'):
                a.capture_checks(manifest, base)

    def test_absence_of_operation_precedes_conditions(self):
        self.assertEqual(a.support('none', 'violated', ['violated']), 'no_current_action')

    def test_full_operation_with_unknown_condition_stays_conditional(self):
        self.assertEqual(a.support('full', 'supported', ['known', 'not_shown']),
                         'conditional_application')

    def test_partial_operation_cannot_be_supported(self):
        self.assertEqual(a.support('partial', 'supported', ['known']), 'conditional_application')


if __name__ == '__main__':
    unittest.main()
