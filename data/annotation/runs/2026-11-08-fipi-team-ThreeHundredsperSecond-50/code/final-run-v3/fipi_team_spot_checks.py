"""Predeclared arithmetic checks; never reads model answers."""
import itertools
import json
from fractions import Fraction
from pathlib import Path

RUN = Path(__file__).resolve().parents[1] / 'data/annotation/runs/2026-11-08-fipi-team-ThreeHundredsperSecond-50'


def main():
    pairs = []
    for p in itertools.permutations('0123579'):
        if p[0] == '0' or p[4] == '0':
            continue
        a, b = int(''.join(p[:4])), int(''.join(p[4:]))
        if a % 45 == b % 45 == 0:
            pairs.append((a+b, a, b))
    cases = {
        2: [
            {'task_id': 'CFEFEF', 'expected_answer': 'a) yes; b) no; c) 10035',
             'basis': 'Exhaust all 5040 digit permutations, exclude leading zeros, require both divisible by 45',
             'pair_count': len(pairs), 'witness_2205': [t for t in pairs if t[0] == 2205],
             'witness_3435': [t for t in pairs if t[0] == 3435], 'maximum': max(pairs)},
            {'task_id': '09eF38', 'expected_answer': '21', 'basis': 'Source graph viewed: (1,3) and (4,6); f(x)=a*sqrt(x), a=3'},
            {'task_id': '586EF2', 'expected_answer': '-4', 'basis': 'Injectivity of log base7: 1-x=5; domain verified'}],
        3: [
            {'task_id': '8C0C15', 'status': 'not_checked', 'basis': 'Parameter equation requires full root-count proof; no numerical spot check asserted'},
            {'task_id': 'BE03FA', 'expected_answer': str(Fraction(6*9,3)), 'basis': 'Pyramid with triangular base area6 and perpendicular prism height9'},
            {'task_id': '37eA9D', 'expected_answer': '2', 'basis': '3^(x-5)=3^(-3), hence x=2'}],
        4: [
            {'task_id': '34F395', 'expected_answer': '20', 'basis': '7*(2,2)+(2,-2)=(16,12), 16^2+12^2=400'},
            {'task_id': '6709ee', 'expected_answer': str(180-54-2*30), 'basis': 'Angle bisector gives A=60; triangle angle sum gives B=66'},
            {'task_id': '51EADD', 'expected_answer': str(Fraction(6,100)*Fraction(96,100)+Fraction(94,100)*Fraction(1,100)), 'basis': 'Total probability over defective and serviceable batteries; 0.067'}]
    }
    for batch, checks in cases.items():
        dest = RUN / 'checks' / f'batch-{batch:02}-root-expectations.json'
        obj = {'batch': batch, 'declared_before_author_launch': True, 'scope': 'Independent preliminary checks, not expert validation', 'checks': checks}
        encoded = json.dumps(obj, ensure_ascii=False, indent=2)+'\n'
        if dest.exists():
            assert dest.read_text(encoding='utf-8') == encoded
        else:
            dest.write_text(encoded, encoding='utf-8')
    print('Independent expectations saved for batches 2-4; no model responses read.')


if __name__ == '__main__':
    main()
