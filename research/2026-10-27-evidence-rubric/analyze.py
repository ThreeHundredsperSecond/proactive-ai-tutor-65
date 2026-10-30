"""Offline analysis of eight fixed evidence/node pairs. No model calls."""
import hashlib
import json
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OLD = ROOT / 'research/2026-10-27-map-alternatives'


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, obj):
    path.parent.mkdir(exist_ok=True, parents=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def expected_support(row):
    if row['operation_match'] == 'none':
        return 'no_application'
    statuses = [c['status'] for c in row['conditions']]
    if 'violated' in statuses:
        return 'violated_application'
    if row['operation_match'] == 'full' and all(x in ('given', 'checked') for x in statuses):
        return 'supported_application'
    return 'conditional_application'


def validate(doc, pairs):
    errors = []
    rows = doc.get('rows', [])
    if len(rows) != len(pairs) or {r['id'] for r in rows} != set(pairs):
        errors.append('Wrong set of pairs')
    for row in rows:
        pair = pairs[row['id']]
        if row['operation_match'] not in ('full', 'partial', 'none', 'uncertain'):
            errors.append(f"{row['id']}: invalid operation_match")
        if row['fragment_coverage'] not in ('full', 'partial', 'none'):
            errors.append(f"{row['id']}: invalid coverage")
        if row['operation_evidence'] and row['operation_evidence'] not in pair['text']:
            errors.append(f"{row['id']}: nonliteral operation evidence")
        if row['operation_match'] in ('full', 'partial') and not row['operation_evidence']:
            errors.append(f"{row['id']}: operation evidence missing")
        ids = {c['id'] for c in pair['constraints']}
        if len(row['conditions']) != len(ids) or {c['id'] for c in row['conditions']} != ids:
            errors.append(f"{row['id']}: wrong constraints")
        for c in row['conditions']:
            if c['status'] not in ('given', 'checked', 'not_shown', 'violated'):
                errors.append(f"{row['id']}: invalid condition status")
            if c['status'] == 'not_shown' and c['evidence']:
                errors.append(f"{row['id']}: unknown condition must have empty quote")
            if c['status'] != 'not_shown' and (not c['evidence'] or c['evidence'] not in pair['text']):
                errors.append(f"{row['id']}: nonliteral/missing condition evidence")
        for quote in row['remainder']:
            if not quote or quote not in pair['text']:
                errors.append(f"{row['id']}: nonliteral remainder")
        if row['fragment_coverage'] in ('partial', 'none') and not row['remainder']:
            errors.append(f"{row['id']}: uncovered text missing")
        if row['support'] != expected_support(row):
            errors.append(f"{row['id']}: support violates frozen rule")
    return errors


def main():
    for item in read(HERE / 'captures.json')['files']:
        assert sha(HERE / item['path']) == item['sha256'], item['path']
    for r in read(HERE / 'manifest.json')['files']:
        assert sha(HERE / r['path']) == r['sha256'], r['path']
    source = read(HERE / 'inputs/pairs.json')
    context_path = HERE / 'context-audit.json'
    if context_path.exists():
        for item in read(context_path)['sources']:
            path = ROOT / item['path']
            assert sha(path) == item['sha256']
            value = read(path)
            for part in item['json_pointer'].strip('/').split('/'):
                value = value[int(part)] if isinstance(value, list) else value[part]
            assert value == item['value']
    for name, expected in source['source_hashes'].items():
        assert sha(OLD / name) == expected, name
    pairs = {p['id']: p for p in source['pairs']}
    frozen = read(OLD / 'frozen-catalogs.json')
    nodes = {n['id']: n for m in frozen['maps'] for n in m['catalog']['nodes']}
    stims = {s['id']: s for s in read(OLD / 'inputs/stimuli.json')['stimuli']}
    for sel in source['selection']:
        p = pairs[sel['id']]
        assert p['node'] == nodes[sel['node']]
        assert p['text'] == stims[sel['stimulus']]['text']
    docs = [read(HERE / f'raw/r{r}.json') for r in (1, 2)]
    errors = [validate(doc, pairs) for doc in docs]
    write(HERE / 'derived/technical.json', {'errors': errors})
    if any(errors):
        print(json.dumps({'technical_errors': errors}, ensure_ascii=False))
        return
    indexed = [{r['id']: r for r in d['rows']} for d in docs]
    fields = ('operation_match', 'fragment_coverage', 'support')
    agreement = {f: {'same': sum(indexed[0][k][f] == indexed[1][k][f] for k in pairs),
                     'total': len(pairs)} for f in fields}
    comparisons = []
    condition_same = condition_total = 0
    for id_, pair in pairs.items():
        a, b = (x[id_] for x in indexed)
        ca, cb = ({c['id']: c for c in r['conditions']} for r in (a, b))
        differences = []
        for c in pair['constraints']:
            key = c['id']
            condition_total += 1
            condition_same += ca[key]['status'] == cb[key]['status']
            if ca[key]['status'] != cb[key]['status']:
                differences.append({'id': key, 'constraint': c['text'],
                                    'r1': ca[key]['status'], 'r2': cb[key]['status'],
                                    'r1_note': ca[key]['note'], 'r2_note': cb[key]['note']})
        comparisons.append({'id': id_, 'node': pair['node']['id'],
                            'r1': {f: a[f] for f in fields}, 'r2': {f: b[f] for f in fields},
                            'condition_differences': differences})
    agreement['condition_status'] = {'same': condition_same, 'total': condition_total}
    summary = {'pairs': len(pairs), 'technical_valid_passes': 2, 'agreement': agreement,
               'support_counts': [dict(Counter(r['support'] for r in d['rows'])) for d in docs],
               'limits': 'Known pairs, fixed node selection, same model family; different outcome targets from earlier exact/component, no direct score comparison, no mastery inference.'}
    write(HERE / 'derived/summary.json', summary)
    write(HERE / 'derived/comparisons.json', comparisons)
    lines = ['# Два прохода новой рубрики: все восемь пар', '',
             'Смысловые оценки агентов, не экспертный эталон. Тексты и узлы не менялись.', '']
    for row in comparisons:
        id_ = row['id']
        lines += [f"## {id_}: {row['node']}", '', '```text', pairs[id_]['text'], '```', '',
                  '| Суждение | Проход1 | Проход2 |', '|---|---|---|']
        for f in fields:
            lines.append(f"| {f} | {row['r1'][f]} | {row['r2'][f]} |")
        lines += ['', '**Расхождения условий:**', '']
        if not row['condition_differences']:
            lines += ['Нет.', '']
        for d in row['condition_differences']:
            lines += [f"- {d['constraint']}: {d['r1']} / {d['r2']}. "
                      f"Первый: {d['r1_note']} Второй: {d['r2_note']}", '']
    (HERE / 'derived/report.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
