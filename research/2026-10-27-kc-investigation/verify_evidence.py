"""Check saved research quotations and preservation of the starting materials.

This verifies bytes and attribution, not mathematical truth or KC equivalence.
Run from any directory using the repository Python interpreter.
"""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    evidence = json.loads((HERE / 'evidence.json').read_text(encoding='utf-8-sig'))
    checked = 0
    paths = set()
    for case in evidence['cases']:
        for source in case['sources']:
            path = ROOT / source['path']
            assert sha(path) == source['sha256'], f"Changed source: {source['path']}"
            value = json.loads(path.read_text(encoding='utf-8-sig'))
            pointer = source['json_pointer']
            for part in pointer.lstrip('/').split('/') if pointer else []:
                part = part.replace('~1', '/').replace('~0', '~')
                value = value[int(part)] if isinstance(value, list) else value[part]
            assert value == source['value'], f"Wrong quotation: {source['path']} {pointer}"
            checked += 1
            paths.add(source['path'])
    baseline = json.loads((HERE / 'baseline-files.json').read_text(encoding='utf-8'))
    # Only these navigation/instruction files may receive a research status append.
    allowed = {'AGENTS.md', 'docs/eda/README.md', 'docs/eda/04-annotation/README.md'}
    changed_navigation = []
    preserved = 0
    for row in baseline['files']:
        path = ROOT / row['path']
        assert path.is_file(), f"Missing initial file: {row['path']}"
        if sha(path) != row['sha256']:
            assert row['path'] in allowed, f"Unexpected change: {row['path']}"
            changed_navigation.append(row['path'])
        else:
            preserved += 1
    output = {'cases': len(evidence['cases']), 'exact_fields_verified': checked,
              'source_files_verified': len(paths), 'baseline_files_preserved': preserved,
              'allowed_navigation_changes': changed_navigation,
              'limits': 'Byte and JSON Pointer checks only; semantic judgments are research hypotheses.'}
    (HERE / 'verification.json').write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
