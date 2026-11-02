"""Regression: legacy MathML fences must remain visible in local cards."""
import sys
import unittest
from pathlib import Path

from lxml import html

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from collect_fipi_bank import browser_math


class FipiMathRenderTests(unittest.TestCase):
    def test_fences_and_separators(self):
        cases = [
            ('<math><mfenced><mi>x</mi><mi>y</mi></mfenced></math>', '(x,y)'),
            ('<math><mfenced open="[" close="]" separators=";"><mi>x</mi><mi>y</mi><mi>z</mi></mfenced></math>', '[x;y;z]'),
            ('<math><mfenced open="" close="" separators=""><mi>x</mi><mi>y</mi></mfenced></math>', 'xy'),
            ('<math><mfenced><mfenced><mi>x</mi></mfenced></mfenced></math>', '((x))'),
        ]
        for source, expected in cases:
            with self.subTest(expected=expected):
                tree = html.fromstring(browser_math(source))
                self.assertEqual(''.join(tree.itertext()), expected)
                self.assertFalse(tree.xpath('.//mfenced'))


if __name__ == '__main__':
    unittest.main()
