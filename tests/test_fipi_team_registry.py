import importlib.util
import unittest
from pathlib import Path

SPEC = importlib.util.spec_from_file_location('team_registry', Path(__file__).resolve().parents[1] / 'scripts/fipi_team_registry.py')
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


class ClaimTests(unittest.TestCase):
    def setUp(self):
        self.registry = {'tasks': [dict(task_id=tid, processing_status=status,
                                       source_issues=issues, eligible_for_next_queue=queued)
                                   for tid, status, issues, queued in (
                                       ('Ab1234', 'not_started', [], True),
                                       ('DONE01', 'independent_audit', [], False),
                                       ('BAD001', 'not_started', ['source defect'], False),
                                       ('OTHER1', 'not_started', [], False))]}

    def check(self, ids, claims=()):
        return module.check_claim(self.registry, {'claims': claims}, ids)

    def test_unknown_case_duplicate_and_completed_ids_rejected(self):
        self.assertTrue(self.check(['ab1234']))
        self.assertTrue(self.check(['Ab1234', 'Ab1234']))
        self.assertTrue(self.check(['DONE01']))

    def test_source_defect_and_outside_queue_rejected(self):
        self.assertTrue(self.check(['BAD001']))
        self.assertTrue(self.check(['OTHER1']))

    def test_accepted_claim_blocks_until_registry_catches_up(self):
        claim = dict(status='accepted', task_ids=['Ab1234'], issue_url='issue/1')
        self.assertTrue(self.check(['Ab1234'], [claim]))

    def test_overlapping_confirmations_rejected(self):
        claims = [dict(status=s, task_ids=['Ab1234'], issue_url=f'issue/{i}')
                  for i, s in enumerate(('reserved', 'in_progress'))]
        self.assertTrue(any('Overlapping' in e for e in self.check(['Ab1234'], claims)))

    def test_released_claim_does_not_block(self):
        claim = dict(status='released', task_ids=['Ab1234'], issue_url='issue/1')
        self.assertEqual(self.check(['Ab1234'], [claim]), [])


if __name__ == '__main__':
    unittest.main()
