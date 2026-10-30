"""Recheck selected arithmetic/row operations in the saved legacy sample.

Numbers are explicitly transcribed from the six captured tasks, never eval'ed.
This is not independent validation of modelling assumptions or KC labels.
"""
import hashlib
import json
import math
from fractions import Fraction as F
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main():
    rows = []
    value = math.log(30) / math.log(5)
    assert round(value, 2) == 2.11
    rows.append({'task': 'L01', 'check': 'logarithmic expression and final rounding only',
                 'computed': value, 'rounded': round(value, 2), 'status': 'pass'})
    assert 0 + 3 * 1 + 2 ** 5 == 35
    rows.append({'task': 'L02', 'check': 'stated elementary values and sum', 'computed': 35, 'status': 'pass'})
    a = [F(2), F(5), F(-4), F(7)]
    b = [F(3), F(-7), F(3), F(5)]
    c = [F(-5), F(9), F(-2), F(-8)]
    b2 = [2 * y - 3 * x for x, y in zip(a, b)]
    c2 = [2 * y + 5 * x for x, y in zip(a, c)]
    c3 = [29 * y + 43 * x for x, y in zip(b2, c2)]
    assert b2 == [0, -29, 18, -11]
    assert c2 == [0, 43, -24, 19]
    assert c3 == [0, 0, 78, 78]
    reconstruction = [3 * x + y + z for x, y, z in zip((2, 3, -5), (5, -7, 9), (-4, 3, -2))]
    assert reconstruction == [7, 5, -8]
    rows.append({'task': 'L03', 'check': 'reported Gaussian row operations and proposed decomposition',
                 'final_row': [str(x) for x in c3], 'reconstruction': reconstruction, 'status': 'pass',
                 'note': 'The source notation78*1 is unusual but the intended arithmetic row78*c3=78 is consistent.'})
    rows.append({'task': 'L04', 'check': 'primary-agent reasoning, not an executable proof',
                 'status': 'manual_plausible', 'note': 'Four vectors in a two-dimensional real vector space cannot be linearly independent. No claim about instructional completeness.'})
    assert 50 * F(1, 50) == 1
    rows.append({'task': 'L05', 'check': 'linearity arithmetic conditional on uniform placement',
                 'computed': '1', 'status': 'conditional_pass',
                 'unverified_assumption': 'Each key has probability1/50 of its original position; the short condition does not specify the probability model.'})
    circulation = [500, 1000, 2000, 3000, 4000]
    cost = [225000, 250000, 300000, 350000, 400000]
    probabilities = [F(20, 100), F(40, 100), F(25, 100), F(10, 100), F(5, 100)]
    profit = [200 * n - q for n, q in zip(circulation, cost)]
    assert profit == [-125000, -50000, 100000, 250000, 400000]
    assert sum(probabilities) == 1
    expected = sum(q * p for q, p in zip(profit, probabilities))
    assert expected == 25000
    rows.append({'task': 'L06', 'check': 'reported profit list and weighted expectation',
                 'profit': profit, 'computed': str(expected), 'status': 'conditional_pass',
                 'unverified_assumption': 'Circulation is treated as copies sold, and publisher receipts per copy are200. No independent modelling validation.'})
    path = HERE / 'inputs/legacy-sample.json'
    output = {'source_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
              'code_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'checks': rows, 'limits': 'Selected computations and explicit manual reasoning, no external expert or validation of learner skills, source provenance or modelling assumptions.'}
    (HERE / 'legacy-math-check.json').write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('Checked6savedentries: arithmetic/row operations passed where tested;2modelling assumptions remain conditional.')


if __name__ == '__main__':
    main()
