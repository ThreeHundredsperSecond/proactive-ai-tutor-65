"""Check preservation, frozen requests, source quotes and deterministic rebuilding."""
import ast
import copy
import json
import re
import subprocess
import sys
from pathlib import Path

from run_offline import HERE, ROOT, digest, read, validate_map, validate_application, write


def main():
    for p in HERE.glob('*.py'):
        ast.parse(p.read_text(encoding='utf-8-sig'))
    allowed = {'AGENTS.md', 'docs/eda/README.md', 'docs/eda/04-annotation/README.md'}
    changed = []
    baseline = read(HERE / 'baseline-files.json')
    for row in baseline['files']:
        path = ROOT / row['path']
        assert path.is_file(), row['path']
        if digest(path) != row['sha256']:
            assert row['path'] in allowed, f"Unexpected modification: {row['path']}"
            changed.append(row['path'])
    official = read(HERE / 'inputs/official.json')
    assert len(official['content']['entries']) == 41
    assert len(official['requirements']['entries']) == 13
    for kind in ('content', 'requirements'):
        assert digest(ROOT / official[kind]['source']) == official[kind]['sha256']
    frozen = read(HERE / 'frozen-catalogs.json')
    maps = {m['label']: m['catalog'] for m in frozen['maps']}
    # Meaningful corruption checks operate only on in-memory copies.
    bad = copy.deepcopy(maps['X'])
    bad['nodes'][0]['content_links'][0]['anchor'] = 'NOT_AN_OFFICIAL_QUOTE'
    assert validate_map(bad, official)['errors']
    stimuli = read(HERE / 'inputs/stimuli.json')['stimuli']
    bad = copy.deepcopy(read(HERE / 'raw/application-r1.json'))
    row = next(row for m in bad['maps'] for row in m['items'] if row['links'])
    row['links'][0]['node_id'] = 'NONEXISTENT_NODE'
    assert validate_application(bad, maps, stimuli)
    before = {p.name: digest(p) for p in (HERE / 'derived').iterdir() if p.is_file()}
    subprocess.run([sys.executable, '-X', 'utf8', str(HERE / 'run_offline.py'), 'analyze'],
                   check=True, stdout=subprocess.DEVNULL)
    after = {p.name: digest(p) for p in (HERE / 'derived').iterdir() if p.is_file()}
    assert before == after, 'Rebuild changed derived bytes'
    missing = []
    unbalanced = []
    for p in HERE.rglob('*.md'):
        text = p.read_text(encoding='utf-8-sig')
        if len(re.findall(r'^```', text, re.M)) % 2:
            unbalanced.append(p.relative_to(HERE).as_posix())
        for match in re.finditer(r'\]\(([^\n]+?)\)', text):
            target = match.group(1)
            if target.startswith(('https://', 'http://', '#', 'mailto:')):
                continue
            if not (p.parent / target.split('#')[0]).exists():
                missing.append([p.relative_to(HERE).as_posix(), target])
    assert not missing, missing
    assert not unbalanced, unbalanced
    result = {'baseline_files': len(baseline['files']),
              'baseline_preserved': len(baseline['files']) - len(changed),
              'allowed_navigation_changes': changed,
              'official_entries_verified': {'content': 41, 'requirements': 13},
              'saved_solution_steps_verified': sum(s['origin'] == 'saved_solution' for s in stimuli),
              'synthetic_descriptions': sum(s['origin'] == 'synthetic_description' for s in stimuli),
              'json_application_rows': sum(len(m['items']) for r in (1, 2)
                                           for m in read(HERE / f'raw/application-r{r}.json')['maps']),
              'source_and_request_hashes': 'pass via run_offline.analyze',
              'corruption_checks': ['wrong official quote rejected', 'unknown node rejected'],
              'derived_rebuild': 'byte-identical', 'derived_files': len(after),
              'local_links_and_fences': 'pass',
              'limits': 'Technical checks; no expert standard, mathematical re-solving or learner validation.'}
    write(HERE / 'verification.json', result)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
