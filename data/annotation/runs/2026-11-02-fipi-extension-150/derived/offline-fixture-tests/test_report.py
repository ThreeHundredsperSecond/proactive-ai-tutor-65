"""Offline regression cases; no saved author/auditor inputs are edited."""
import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[6]
sys.path.insert(0, str(ROOT / 'scripts'))
import report_fipi_extension as report


def fixture():
    inp = {'instruction': '', 'statement_html': '<div>1</div>', 'assets': [],
           'mathml_count': 0, 'metadata': [{'label': 'КЭС:', 'values': ['1.1 test']}]}
    author = {'solution_status': 'solved', 'steps': [
        {'id': 's1', 'kc_ids': ['k1', 'k2']},
        {'id': 's2', 'kc_ids': ['k3', 'k4']},
        {'id': 's3', 'kc_ids': ['k5', 'u']}],
        'methods': [{'step_ids': ['s1', 's2']}, {'step_ids': ['s3']}],
        'kc_candidates': [{'id': k, 'name': 'same name'} for k in ['k1','k2','k3','k4','k5','u']]}
    audit = {'decisions': [dict(local_kc_id=k, status='match', catalog_kc_id=c, blocking=False, rationale='fixture') for k,c in [('k1','A'),('k2','B'),('k3','B'),('k4','C'),('k5','D')]] + [dict(local_kc_id='u', status='new_candidate', catalog_kc_id=None, blocking=False, rationale='fixture')], 'issues': []}
    rows = [dict(task_id=str(i), layer='audited_new', primary_kes='1.1', response_type='short', input=inp,
                 author=copy.deepcopy(author), audit=copy.deepcopy(audit), complete=True,
                 included=True, exclusion_reasons=[]) for i in range(2)]
    return dict(baseline=[], new=rows, catalog={'assignments': []})


class MetricsTests(unittest.TestCase):
    def test_multikc_cartesian_transitions_and_task_deduplication(self):
        summary, tables = report.metrics(fixture())
        transitions = {(r['from_kc'],r['to_kc']):r['task_n'] for r in tables['transitions'] if r['population']=='new_accumulated'}
        self.assertEqual(transitions, {('A','B'):2, ('A','C'):2, ('B','C'):2})
        self.assertEqual(summary['new_accumulated']['confirmed_catalog_nodes'], 4)

    def test_same_named_unmatched_candidates_are_local(self):
        summary, tables = report.metrics(fixture())
        self.assertEqual(summary['new_accumulated']['unmatched_local_candidates'], {'numerator':2,'denominator':12})
        self.assertEqual(len([r for r in tables['candidates'] if r['status']=='new_candidate']), 2)
        self.assertFalse(any(r['catalog_kc_id'] is None for r in tables['frequencies']))

    def test_excluded_blocking_task_not_in_primary_frequencies(self):
        data = fixture()
        data['new'][0]['included'] = False
        data['new'][0]['exclusion_reasons'] = ['blocking_audit_issue']
        summary,tables = report.metrics(data)
        self.assertEqual(summary['new_accumulated']['included_n'], 1)
        self.assertEqual(summary['new_accumulated']['audit_statuses']['match']['denominator'], 12)
        self.assertTrue(all(r['task_n']==1 and r['denominator']==1 for r in tables['frequencies'] if r['population']=='new_accumulated'))

    def test_historical_partial_remains_excluded(self):
        data = fixture(); old = copy.deepcopy(data['new'][0])
        old.update(layer='historical_editorial', included=False, audit=None,
                   exclusion_reasons=['historical_partial_or_review_exclusion'])
        old['author']['solution_status']='partial'
        data['baseline']=[old]
        data['catalog']['assignments']=[{'task_id':old['task_id'],'local_id':k['id'],'canonical_id':'OLD'} for k in old['author']['kc_candidates']]
        summary,tables=report.metrics(data)
        self.assertEqual(summary['baseline50']['included_n'], 0)
        self.assertEqual(summary['mixed_cumulative']['included_n'], 2)
        self.assertFalse(any(r['catalog_kc_id']=='OLD' for r in tables['frequencies']))

    def test_active_attempt_path_cannot_escape_run(self):
        with self.assertRaises(ValueError):
            report.active_path('x','author',{'x':{'author':'../../outside.json'}})


if __name__=='__main__':
    unittest.main()
