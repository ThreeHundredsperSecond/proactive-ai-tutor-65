"""Independent finite enumeration for the explicit small-digit-sum lists in task 19."""
from fipi_annotation_run import RUN, write, sha
from pathlib import Path

groups = {s: [] for s in range(1, 6)}
for number in range(1, 1_000_001):
    digit_sum = sum(map(int, str(number)))
    if digit_sum in groups and len(groups[digit_sum]) < 7:
        groups[digit_sum].append(number)
    if all(len(g) == 7 for g in groups.values()):
        break
expected = {
    1: [1, 10, 100, 1000, 10000, 100000, 1000000],
    2: [2, 11, 20, 101, 110, 200, 1001],
    3: [3, 12, 21, 30, 102, 111, 120],
    4: [4, 13, 22, 31, 40, 103, 112],
    5: [5, 14, 23, 32, 41, 50, 104],
}
assert groups == expected
assert [sum(groups[s]) for s in range(1, 6)] == [1111111, 1445, 399, 325, 269]
assert sum([6, 15, 24, 33, 42, 51, 60]) == 231
write(RUN / 'math-check.json', {'status': 'passed', 'script_sha256': sha(Path(__file__)),
      'raw_sha256': sha(RUN / 'raw/699103.txt'), 'smallest_seven': groups,
      'sums': {s: sum(g) for s, g in groups.items()},
      'scope': 'Exhaustive enumeration verifies five explicit finite lists and their sums, plus sum of attaining example. It does not validate all solutions or pedagogical usefulness.'})
print('Verified task 19: all five smallest-seven lists and sums; raw unchanged.')
