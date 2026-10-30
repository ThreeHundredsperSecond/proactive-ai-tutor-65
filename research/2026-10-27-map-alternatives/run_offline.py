"""Validate/freeze prototype maps and rebuild analysis of saved applications.

No network, model invocation or solving of source tasks. Run from any directory.
"""
import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, obj):
    path.parent.mkdir(exist_ok=True, parents=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def validate_map(doc, official):
    errors = []
    nodes = doc.get('nodes', [])
    if not 8 <= len(nodes) <= 16:
        errors.append('Expected 8..16 nodes')
    ids = [n['id'] for n in nodes]
    if len(ids) != len(set(ids)):
        errors.append('Duplicate node id')
    coverage = Counter()
    refs = {kind: {r['code']: r['text'] for r in official[kind]['entries']}
            for kind in ('content', 'requirements')}
    for node in nodes:
        for field in ('id', 'name', 'operation', 'object', 'input_representation', 'output', 'example', 'counterexample'):
            if not isinstance(node.get(field), str) or not node[field].strip():
                errors.append(f"{node.get('id')}: missing text {field}")
        for field in ('conditions', 'includes', 'excludes'):
            if not isinstance(node.get(field), list):
                errors.append(f"{node['id']}: missing list {field}")
        if node.get('source_status') != 'project_candidate':
            errors.append(f"{node['id']}: wrong official/project status")
        if not node.get('content_links'):
            errors.append(f"{node['id']}: no content link")
        for field, kind in [('content_links', 'content'), ('requirement_links', 'requirements')]:
            for link in node.get(field, []):
                code, anchor = link.get('code'), link.get('anchor')
                if code not in refs[kind] or not anchor or anchor not in refs[kind].get(code, ''):
                    errors.append(f"{node['id']}: invalid {kind} code/quote {code}")
                if kind == 'content':
                    coverage[code] += 1
    for code in official['selected_content_codes']:
        if coverage[code] < 2:
            errors.append(f'Not enough candidates in {code}')
    for rel in doc.get('relationships', []):
        if rel['from'] not in ids or rel['to'] not in ids or rel['from'] == rel['to']:
            errors.append(f'Bad relationship {rel}')
        if rel['type'] not in ('component_of', 'specialization_of', 'alternative_to'):
            errors.append(f'Bad relation type {rel}')
    return {'errors': errors, 'nodes': len(nodes), 'content_assignments': dict(coverage)}


def freeze():
    target = HERE / 'frozen-catalogs.json'
    if target.exists():
        raise RuntimeError('Already frozen; refusing replacement')
    official = read(HERE / 'inputs/official.json')
    # X/Y are neutral labels, not evidence that an evaluator cannot infer the design.
    maps = []
    for label, name in [('X', 'curriculum'), ('Y', 'facets')]:
        path = HERE / f'raw/{name}.json'
        doc = read(path)
        check = validate_map(doc, official)
        if check['errors']:
            raise ValueError(check)
        maps.append({'label': label, 'source': path.relative_to(HERE).as_posix(),
                     'sha256': digest(path), 'catalog': doc, 'technical_check': check})
    write(target, {'official_sha256': digest(HERE / 'inputs/official.json'),
                   'jobs': {name: digest(HERE / f'jobs/{name}.txt') for name in ('curriculum', 'facets')},
                   'maps': maps})
    print('Frozen', {m['label']: m['technical_check'] for m in maps})


def validate_application(doc, maps, stimuli):
    errors = []
    by_id = {s['id']: s for s in stimuli}
    if len(doc.get('maps', [])) != len(maps) or {m['map_id'] for m in doc.get('maps', [])} != set(maps):
        errors.append('Wrong set of maps')
    for m in doc.get('maps', []):
        label = m['map_id']
        rows = m.get('items', [])
        if len(rows) != len(by_id) or {r['id'] for r in rows} != set(by_id):
            errors.append(f'{label}: wrong set of stimuli')
        nodes = {n['id'] for n in maps[label]['nodes']}
        for row in rows:
            if row.get('status') not in ('covered', 'partial', 'no_match', 'uncertain'):
                errors.append(f'{label}/{row["id"]}: invalid status')
            for link in row.get('links', []):
                if link['node_id'] not in nodes:
                    errors.append(f'{label}/{row["id"]}: wrong node')
                if link.get('relation') not in ('exact', 'component'):
                    errors.append(f'{label}/{row["id"]}: wrong relation')
                if not link.get('evidence') or link['evidence'] not in by_id[row['id']]['text']:
                    errors.append(f'{label}/{row["id"]}: evidence not literal')
            if row.get('status') == 'no_match' and row.get('links'):
                errors.append(f'{label}/{row["id"]}: no_match has links')
            if row.get('status') in ('covered', 'partial') and not row.get('links'):
                errors.append(f'{label}/{row["id"]}: coverage has no links')
    return errors


def analyze():
    frozen = read(HERE / 'frozen-catalogs.json')
    assert frozen['official_sha256'] == digest(HERE / 'inputs/official.json')
    official = read(HERE / 'inputs/official.json')
    for name, expected in frozen['jobs'].items():
        assert digest(HERE / f'jobs/{name}.txt') == expected
    app_manifest = read(HERE / 'application-input-manifest.json')
    assert app_manifest['catalogs_sha256'] == digest(HERE / 'frozen-catalogs.json')
    assert app_manifest['stimuli_sha256'] == digest(HERE / 'inputs/stimuli.json')
    for name, expected in app_manifest['inputs'].items():
        assert digest(HERE / f'inputs/{name}.json') == expected
    for name, expected in app_manifest['jobs'].items():
        assert digest(HERE / f'jobs/{name}.txt') == expected
    for capture in read(HERE / 'captures.json')['files']:
        assert digest(HERE / capture['path']) == capture['sha256']
    maps = {m['label']: m['catalog'] for m in frozen['maps']}
    for m in frozen['maps']:
        assert digest(HERE / m['source']) == m['sha256']
        assert not validate_map(m['catalog'], official)['errors']
    stimuli = read(HERE / 'inputs/stimuli.json')['stimuli']
    for s in stimuli:
        if s['origin'] == 'saved_solution':
            path = ROOT / s['source']['path']
            assert digest(path) == s['source']['sha256']
            value = read(path)
            for part in s['source']['json_pointer'].strip('/').split('/'):
                value = value[int(part)] if isinstance(value, list) else value[part]
            assert s['text'] == value['action'] + '\n' + value['result']
    applications = [read(HERE / f'raw/application-r{r}.json') for r in (1, 2)]
    technical = [validate_application(doc, maps, stimuli) for doc in applications]
    assert not any(technical), technical
    indexed = [{m['map_id']: {r['id']: r for r in m['items']} for m in d['maps']} for d in applications]
    comparisons = []
    summary = {}
    for label in maps:
        exact_count = status_count = 0
        same_nodes_count = 0
        same_nodes_nonempty = 0
        jac = []
        used = set()
        for s in stimuli:
            a, b = indexed[0][label][s['id']], indexed[1][label][s['id']]
            aset, bset = ({(l['node_id'], l['relation']) for l in row['links']} for row in (a, b))
            same = aset == bset
            node_same = {x[0] for x in aset} == {x[0] for x in bset}
            status_same = a['status'] == b['status']
            j = len(aset & bset) / len(aset | bset) if aset | bset else None
            if j is not None:
                jac.append(j)
                same_nodes_nonempty += node_same
            used.update(node for node, _ in aset | bset)
            exact_count += same
            same_nodes_count += node_same
            status_count += status_same
            comparisons.append({'map': label, 'stimulus': s['id'], 'origin': s['origin'],
                                'r1_status': a['status'], 'r2_status': b['status'],
                                'r1_assignments': sorted(aset), 'r2_assignments': sorted(bset),
                                'assignments_equal': same, 'nodes_equal': node_same,
                                'status_equal': status_same, 'jaccard': j})
        summary[label] = {'nodes': len(maps[label]['nodes']), 'stimuli': len(stimuli),
                          'same_assignments': exact_count, 'same_status': status_count,
                          'same_node_sets_including_empty': same_nodes_count,
                          'same_node_sets_nonempty_union': same_nodes_nonempty,
                          'nonempty_union_pairs': len(jac),
                          'mean_assignment_jaccard_nonempty': sum(jac) / len(jac) if jac else None,
                          'nodes_used_in_either_pass': len(used),
                          'nodes_not_used': sorted({n['id'] for n in maps[label]['nodes']} - used),
                          'statuses_by_pass': [dict(Counter(p[label][s['id']]['status'] for s in stimuli)) for p in indexed]}
    write(HERE / 'derived/summary.json', {'technical_errors': technical, 'maps': summary,
          'limits': 'Two agent applications of two fixed prototypes; no expert labels, no learner data, no proof of stability/generalisation. Empty-set agreement shown separately by statuses.'})
    write(HERE / 'derived/comparisons.json', comparisons)
    render_maps(frozen, official)
    review_path = HERE / 'primary-review.json'
    if review_path.exists():
        render_applications(stimuli, indexed, read(review_path))
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def render_maps(frozen, official):
    """Human-readable definitions plus the entire official scaffold, no inferred prerequisites."""
    (HERE / 'derived').mkdir(exist_ok=True)
    lines = ['# Две замороженные карты: определения', '',
             'Кандидаты проекта, не официальные KC. Построены по одним входам до показа проб применения. '
             'Точные ответы агентов сохранены; эта страница лишь меняет представление.', '']
    for m in frozen['maps']:
        doc = m['catalog']
        lines += [f"## Карта {m['label']}: {doc['method']}", '']
        for n in doc['nodes']:
            lines += [f"### {n['id']}. {n['name']}", '',
                      f"**Операция:** {n['operation']}", '',
                      f"**Объект:** {n['object']}", '',
                      f"**Представление на входе:** {n['input_representation']}", '',
                      f"**Результат:** {n['output']}", '',
                      '**Условия:** ' + '; '.join(n['conditions']), '',
                      '**Включает:** ' + '; '.join(n['includes']), '',
                      '**Исключает:** ' + '; '.join(n['excludes']), '',
                      f"**Пример:** {n['example']}", '', f"**Контрпример:** {n['counterexample']}", '',
                      '**Коды содержания (проектные связи):** ' + ', '.join(l['code'] for l in n['content_links']), '',
                      '**Коды требований (проектные связи):** ' + ', '.join(l['code'] for l in n['requirement_links']), '']
        lines += ['**Открытые пробелы:** ' + '; '.join(doc['gaps']), '']
    (HERE / 'derived/maps.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    scaffold = []
    for entry in official['content']['entries']:
        links = {m['label']: [n['id'] for n in m['catalog']['nodes']
                             if any(l['code'] == entry['code'] for l in n['content_links'])]
                 for m in frozen['maps']}
        scaffold.append({**entry, 'status': 'prototype_slice' if any(links.values()) else 'not_developed_in_this_trial',
                         'candidate_links': links})
    write(HERE / 'derived/scaffold.json', scaffold)
    slines = ['# Официальный каркас: все 41 пункт содержания', '',
              'Наличие кандидата не означает покрытие пункта или подтверждённое умение. '
              '«Не разрабатывался» не означает отсутствие темы в программе. '
              'Ни одна связь здесь не объявляется официальным соответствием требования и содержания.', '',
              '| Код | Официальная формулировка | Уровень программы | X | Y |', '|---|---|---|---|---|']
    for row in scaffold:
        slines.append('| ' + ' | '.join([row['code'], row['text'], row['program_level'],
                       ', '.join(row['candidate_links']['X']) or 'не разрабатывался',
                       ', '.join(row['candidate_links']['Y']) or 'не разрабатывался']) + ' |')
    (HERE / 'derived/scaffold.md').write_text('\n'.join(slines) + '\n', encoding='utf-8')


def render_applications(stimuli, indexed, review):
    notes = {r['id']: r for r in review['cases']}
    lines = ['# Применение карт: все12 описаний', '',
             'Два изолированных прохода. Степень связи exact/component — соглашение разметки, '
             'не степень освоения ученика. Семантические пояснения основного агента записаны '
             'после просмотра; не внешний эталон.', '',
             'X — curriculum; Y — facets. Полные определения: [maps.md](maps.md).', '']
    for s in stimuli:
        lines += [f"## {s['id']}. {s['title']}", '',
                  '**Происхождение:** ' + s['origin'], '', '```text', s['text'], '```', '',
                  '| Карта | Проход1 | Проход2 |', '|---|---|---|']
        for label in ('X', 'Y'):
            rendered = []
            for p in indexed:
                row = p[label][s['id']]
                links = ', '.join(l['node_id'] + ':' + l['relation'] for l in row['links']) or 'нет связей'
                rendered.append(row['status'] + '; ' + links)
            lines.append('| ' + ' | '.join([label] + rendered) + ' |')
        lines += ['', '**Интерпретация основного агента:** ' + notes[s['id']]['reason'], '']
    (HERE / 'derived/application-review.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=('freeze', 'analyze'))
    args = parser.parse_args()
    freeze() if args.command == 'freeze' else analyze()
