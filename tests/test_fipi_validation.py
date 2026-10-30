"""Check that the extra FIPI fields cannot pass on codes/quotes alone."""
import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from fipi_annotation_run import inspect_response


class FipiValidationTests(unittest.TestCase):
    def setUp(self):
        self.catalog = {'12': 'координаты вектора, сумма векторов'}
        self.response = {
            'task_id': 'x', 'solution_status': 'solved', 'selected_requirements': ['12'],
            'steps': [{'id': 's1', 'action': 'Сложить', 'result': 'Сумма', 'kc_ids': ['k1']}],
            'kc_candidates': [{'id': 'k1', 'name': 'Складывать', 'description': 'Складывать координаты'}],
            'methods': [{'id': 'm1', 'name': 'Координатный', 'step_ids': ['s1']}],
            'fipi_links': [{'requirement_code': '12', 'kc_ids': ['k1'], 'anchor': 'сумма векторов', 'reason': 'Выполнено сложение'}],
            'warnings': [],
        }

    def test_requires_literal_quote_and_real_code(self):
        self.assertEqual(inspect_response(self.response, self.catalog), [])
        for field, value in [('anchor', 'сумма Векторов'), ('requirement_code', '99')]:
            changed = copy.deepcopy(self.response)
            changed['fipi_links'][0][field] = value
            self.assertTrue(inspect_response(changed, self.catalog))

    def test_requires_kc_coverage_and_consistent_selected_codes(self):
        for changes in ({'fipi_links': []}, {'selected_requirements': []}):
            changed = copy.deepcopy(self.response)
            changed.update(changes)
            self.assertTrue(inspect_response(changed, self.catalog))
        changed = copy.deepcopy(self.response)
        changed['fipi_links'][0]['kc_ids'] = ['nonexistent']
        self.assertTrue(inspect_response(changed, self.catalog))

    def test_explicit_unknown_is_allowed_without_false_quote(self):
        changed = copy.deepcopy(self.response)
        changed['selected_requirements'] = []
        changed['fipi_links'][0].update(requirement_code=None, anchor='', reason='Не удалось сопоставить')
        self.assertEqual(inspect_response(changed, self.catalog), [])
        changed['fipi_links'][0]['anchor'] = 'сумма векторов'
        self.assertTrue(inspect_response(changed, self.catalog))


if __name__ == '__main__':
    unittest.main()
