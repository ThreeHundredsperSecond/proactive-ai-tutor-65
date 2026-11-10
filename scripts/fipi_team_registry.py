"""Offline inventory and reservation preflight. Never grants a GitHub reservation."""
import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUN = Path('data/annotation/runs/2026-11-02-fipi-extension-150')
BASE = Path('data/annotation/runs/2026-10-31-fipi-50x1')
TEAM = Path('data/annotation/team')
SOURCES = [
    Path('data/fipi/2026-10-31-profile/tasks.jsonl'), RUN / 'selection.json',
    RUN / 'exclusions.json', RUN / 'derived/checkpoint-100-v1/active-tasks.json',
    RUN / 'derived/checkpoint-100-v1/summary.json',
]
METHOD = [RUN / x for x in (
    'author-prompt.txt', 'author-wrapper.txt', 'auditor-prompt.txt',
    'audit-format-wrapper-v1.1.txt', 'catalog-for-auditor.json',
    'execution-protocol-v1.1.json', 'PROTOCOL.md',
)]


def read(path):
    return json.loads((ROOT / path).read_text(encoding='utf-8'))


def digest(path):
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()


def build():
    bank = [json.loads(s) for s in (ROOT / SOURCES[0]).read_text(encoding='utf-8').splitlines()]
    old = {x['task_id'] for x in read(RUN / 'exclusions.json') if x['reason'] == 'baseline_50'}
    selected = {x['task_id']: x for x in read(RUN / 'selection.json')['tasks']}
    active = {x['task_id']: x for x in read(SOURCES[3])}
    excluded_old = {x['task_id'] for x in read(SOURCES[4])['populations']['baseline50']['excluded']}
    records = []
    for task in bank:
        tid = task['id']
        a = active.get(tid)
        included = tid not in excluded_old if tid in old else a['included'] if a else None
        status = ('historical_review' if tid in old else 'independent_audit') if tid in old or a else 'not_started'
        record = dict(task_id=tid, processing_status=status, included_in_checkpoint100=included,
                      review_required=included is False, source_issues=task['source_issues'],
                      queue_order=selected.get(tid, {}).get('order'),
                      queue_batch=selected.get(tid, {}).get('batch'),
                      reservation_status='unpublished', owner=None,
                      eligible_for_next_queue=bool(tid in selected and not a),
                      source_path=f"data/fipi/2026-10-31-profile/tasks/{tid}.json")
        if tid in old:
            record['author_path'] = (BASE / 'raw' / f'{tid}.json').as_posix()
        elif a:
            for role in ('author', 'auditor'):
                record[f'{role}_path'] = (RUN / a[f'{role}_path'].replace('\\', '/')).as_posix()
        records.append(record)
    return dict(schema_version=1, snapshot='checkpoint-100-v1', method_version='fipi-extension-v1.1',
                branch='docs/full-ege-math-scope', generation_authorized=False,
                reservation_authority='GitHub issue plus explicit coordinator confirmation; not this offline snapshot',
                sources={p.as_posix(): digest(p) for p in SOURCES},
                methodology_sha256={p.as_posix(): digest(p) for p in METHOD},
                counts=dict(Counter(x['processing_status'] for x in records)), tasks=records)


def check_claim(registry, claims, ids, selection=None):
    errors = []
    if len(set(ids)) != len(ids):
        errors.append('Repeated ID in proposal')
    tasks = {x['task_id']: x for x in registry['tasks']}
    selection_ids = None
    if selection is not None:
        selected = [x['task_id'] for x in selection['tasks']]
        selection_ids = set(selected)
        if len(selected) != len(selection_ids):
            errors.append('Repeated ID in additional selection')
    occupied = {}
    for claim in claims['claims']:
        if claim['status'] not in ('reserved', 'in_progress', 'submitted', 'accepted'):
            continue
        for tid in claim['task_ids']:
            if tid in occupied:
                errors.append(f'Overlapping active claims for {tid}')
            occupied[tid] = claim['issue_url']
    for tid in ids:
        task = tasks.get(tid)
        if task is None:
            errors.append(f'Unknown ID (case-sensitive): {tid}')
        elif task['processing_status'] != 'not_started':
            errors.append(f'Already processed: {tid}')
        elif task['source_issues']:
            errors.append(f'Source issue: {tid}')
        elif selection_ids is not None and tid not in selection_ids:
            errors.append(f'Outside additional selection: {tid}')
        elif selection_ids is None and not task['eligible_for_next_queue']:
            errors.append(f'Outside frozen remaining queue: {tid}')
        if tid in occupied:
            errors.append(f'Occupied: {tid}: {occupied[tid]}')
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('build', 'check', 'check-claim'))
    parser.add_argument('--ids', nargs='+')
    parser.add_argument('--claims', type=Path, default=TEAM / 'claims.json')
    parser.add_argument('--selection', type=Path,
                        help='Explicit additional queue; does not change the frozen queue')
    args = parser.parse_args()
    path = ROOT / TEAM / 'registry.json'
    if args.command == 'build':
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(build(), ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    elif args.command == 'check':
        if read(TEAM / 'registry.json') != build():
            raise SystemExit('Registry differs from pinned source files; inspect before rebuilding')
    else:
        if not args.ids:
            parser.error('--ids required')
        registry = read(TEAM / 'registry.json')
        if registry != build():
            raise SystemExit('Stale registry; inspect source changes before proposing IDs')
        selection = read(args.selection) if args.selection else None
        errors = check_claim(registry, read(args.claims), args.ids, selection)
        if errors:
            raise SystemExit('\n'.join(errors))
        print('Local preflight passed. This does NOT reserve IDs or authorize generation. Recheck live GitHub with coordinator.')
    print('OK')


if __name__ == '__main__':
    main()
