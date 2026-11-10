"""Saved-only FIPI extension reports. No inference, network, or baseline writes.

CLI: report --count 50|100|150; progress [--count 50|100|150].
Active paths: RUN/active-attempts.json = {task_id: {author: relative_path,
auditor: relative_path}}. Without an entry use raw/{author,auditor}/ID.json.
Checkpoints are immutable: changed input or implementation hashes require a new
explicit checkpoint version (--version), never overwriting the old artifact.
"""
import argparse
import csv
import hashlib
import html
import itertools
import json
import os
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from lxml import html as dom
from PIL import Image

import fipi_extension as ext
from fipi_eda50 import validate_one
from collect_fipi_bank import browser_math

ROOT, RUN, BASE = ext.ROOT, ext.RUN, ext.BASE
STATUSES = ('match', 'new_candidate', 'needs_split', 'uncertain')


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def dump(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def csvout(out, name, rows, fields):
    with (out / name).open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def active_path(tid, role, active):
    rel = active.get(tid, {}).get(role, f'raw/{role}/{tid}.json')
    p = (RUN / rel).resolve()
    if not p.is_relative_to(RUN.resolve()):
        raise ValueError(f'Active attempt escapes RUN: {tid}/{role}')
    return p


def task_template(inp, mask=False):
    """Same descriptive DOM/hash numeric-template heuristic as baseline EDA."""
    import re
    tree = dom.fromstring(inp['statement_html'])
    assets = {Path(a['path']).name: a['sha256'] for a in inp['assets']}
    def norm(s):
        s = ' '.join((s or '').replace('\u200b', '').split())
        return re.sub(r'\d+(?:[.,]\d+)?', '#', s) if mask else s
    def walk(e):
        if e.tag == 'img':
            return ('img', assets[Path(e.get('src', '')).name])
        attrs = tuple((k, e.get(k)) for k in ('open', 'close', 'separators', 'mathvariant', 'accent', 'stretchy') if e.get(k) is not None)
        return (e.tag, attrs, norm(e.text), tuple((walk(c), norm(c.tail)) for c in e if isinstance(c.tag, str)))
    return hashlib.sha256(json.dumps([inp['instruction'], walk(tree)], ensure_ascii=False).encode()).hexdigest()


def collect(count=150, strict=False, active_snapshot=None):
    """Validate saved files and return analysis inputs; never write anything."""
    if count not in (50, 100, 150):
        raise ValueError('count must be 50, 100 or 150 NEW tasks')
    ext.verify_frozen()
    paths = set()
    def load(p):
        p = Path(p); paths.add(p.resolve()); return read(p)
    selection = load(RUN / 'selection.json')
    cat = load(RUN / 'catalog-v1.json')
    load(RUN / 'catalog-for-auditor.json')
    selected = selection['tasks'][:count]
    selected_ids = {t['task_id'] for t in selected}
    if active_snapshot is not None:
        snapshot = Path(active_snapshot).resolve()
        assert snapshot.is_relative_to(RUN.resolve()), 'Active snapshot outside RUN'
        active = load(snapshot)
        assert set(active) <= selected_ids
    else:
        current = read(RUN / 'active-attempts.json') if (RUN / 'active-attempts.json').exists() else {}
        active = {tid: paths for tid, paths in current.items() if tid in selected_ids}
        encoded = json.dumps(active, sort_keys=True, ensure_ascii=False).encode('utf-8')
        snapshot = RUN / 'active-scopes' / f'first-{count:03}-{hashlib.sha256(encoded).hexdigest()[:16]}.json'
        ext.freeze(snapshot, active)
        active = load(snapshot)
    for name in ('baseline-manifest.json', 'freeze-manifest.json', 'PROTOCOL.md', 'author-prompt.txt', 'auditor-prompt.txt', 'author-wrapper.txt', 'environment.json'):
        paths.add((RUN / name).resolve())
    for name in ('report_fipi_extension.py', 'fipi_extension.py', 'fipi_eda50.py', 'collect_fipi_bank.py'):
        paths.add((ROOT / 'scripts' / name).resolve())
    assert len(selected) == count and len({t['task_id'] for t in selected}) == count
    rows, errors = [], []
    for entry in selected:
        tid = entry['task_id']; inp = load(RUN / 'inputs/tasks' / f'{tid}.json')
        r = dict(entry, layer='audited_new', input=inp, author=None, audit=None,
                 complete=False, included=False, technical_errors=[], exclusion_reasons=[])
        try:
            for a in inp['assets']:
                p = RUN / 'inputs' / a['path']; paths.add(p.resolve())
                assert sha(p) == a['sha256'], f'image hash {a["path"]}'
                with Image.open(p) as im: im.verify()
            for role in ('author', 'auditor'):
                p = active_path(tid, role, active)
                r[role + '_path'] = str(p.relative_to(RUN))
                if p.exists():
                    r['author' if role == 'author' else 'audit'] = load(p)
            if r['author'] is not None:
                validate_one(r['author']); assert r['author']['task_id'] == tid
            if r['audit'] is not None:
                assert r['author'] is not None, 'audit without active author'
                ext.validate_audit(tid, active_path(tid, 'auditor', active),
                                   author_path=active_path(tid, 'author', active).relative_to(ROOT).as_posix())
                r['complete'] = True
        except (AssertionError, KeyError, ValueError, TypeError, OSError) as e:
            r['technical_errors'].append(f'{type(e).__name__}: {e}')
            errors.append({'task_id': tid, 'error': r['technical_errors'][-1]})
        if not r['complete']:
            if r['technical_errors']: r['exclusion_reasons'].append('technical_validation_failure')
            elif r['author'] is None: r['exclusion_reasons'].append('author_pending')
            else: r['exclusion_reasons'].append('audit_pending')
        if r['author'] is not None and r['author'].get('solution_status') != 'solved':
            r['exclusion_reasons'].append(r['author'].get('solution_status', 'missing_status'))
        if r['audit'] is not None and (any(i.get('blocking') for i in r['audit'].get('issues', [])) or any(d.get('blocking') for d in r['audit'].get('decisions', []))):
            r['exclusion_reasons'].append('blocking_audit_issue')
        r['included'] = r['complete'] and not r['exclusion_reasons']
        default_author = f'raw/author/{tid}.json'
        r['author_mode'] = active.get(tid, {}).get('author_mode', 'standalone_initial' if active.get(tid, {}).get('author', default_author) == default_author else 'corrected_attempt_unspecified')
        r['feedback_ref'] = active.get(tid, {}).get('feedback_ref')
        rows.append(r)
    checks = []
    for batch in sorted({t['batch'] for t in selected}):
        p = RUN / 'checks' / f'batch-{batch:02d}.json'
        expected = [t['task_id'] for t in selection['tasks'] if t['batch'] == batch]
        result = {'batch': batch, 'valid': False, 'reason': 'missing_health_check'}
        if p.exists():
            c = load(p)
            valid = (c.get('batch') == batch and c.get('status') in ('pass', 'quarantine')
                     and c.get('systemic_unresolved') is False
                     and c.get('task_ids') == expected
                     and all(k in c for k in ('technical', 'render', 'math_spot_checks', 'visual_review', 'audit_flags')))
            result.update(valid=valid, reason=None if valid else 'incomplete_or_failed_health_check', path=str(p.relative_to(RUN)))
        checks.append(result)
    if strict:
        assert all(r['complete'] for r in rows), f'Checkpoint requires {count} completed technically valid author+audit pairs; got {sum(r["complete"] for r in rows)}'
        assert all(c['valid'] for c in checks), f'Checkpoint requires all batch health checks: {checks}'
    baseline_manifest = load(BASE / 'manifest.json')
    reviews = load(BASE / 'review-decisions.json')['tasks']
    baseline = []
    for entry in baseline_manifest['tasks']:
        tid = entry['task_id']; p = BASE / 'raw' / f'{tid}.json'; d = load(p)
        validate_one(d); assert sha(p) == reviews[tid]['raw_sha256']
        inp = load(BASE / 'inputs/tasks' / f'{tid}.json')
        baseline.append(dict(entry, layer='historical_editorial', author_mode='historical_shared_context', input=inp, author=d, audit=None,
                             complete=True, included=bool(reviews[tid]['include_primary_metrics']) and d['solution_status'] == 'solved',
                             exclusion_reasons=[] if reviews[tid]['include_primary_metrics'] and d['solution_status'] == 'solved' else ['historical_partial_or_review_exclusion']))
    provenance = {p.relative_to(ROOT).as_posix(): sha(p) for p in sorted(paths)}
    return dict(count=count, baseline=baseline, new=rows, catalog=cat, health_checks=checks,
                active_snapshot=str(snapshot),
                technical_errors=errors, input_hashes=provenance,
                input_digest=hashlib.sha256(json.dumps(provenance, sort_keys=True).encode()).hexdigest())


def mapping(row, assignments):
    if row['layer'] == 'historical_editorial':
        return {k['id']: assignments[(row['task_id'], k['id'])] for k in row['author']['kc_candidates']}
    if not row['complete']: return {}
    return {d['local_kc_id']: d['catalog_kc_id'] for d in row['audit']['decisions']
            if d['status'] == 'match' and not d['blocking']}


def metrics(data):
    assignments = {(a['task_id'], a['local_id']): a['canonical_id'] for a in data['catalog']['assignments']}
    groups = [('baseline50', data['baseline']), ('new_accumulated', data['new']),
              ('new_latest50', data['new'][-50:]), ('mixed_cumulative', data['baseline'] + data['new'])]
    result = {}
    frequencies, co, transitions, taskrows, composition, statusrows, candidates = [], [], [], [], [], [], []
    for group, rows in groups:
        included = [r for r in rows if r['included']]
        freq, pairs, trans = Counter(), Counter(), Counter()
        unmatched, total = 0, 0
        for r in rows:
            a = r['author']; m = mapping(r, assignments) if r['complete'] else {}
            if a:
                taskrows.append(dict(population=group, task_id=r['task_id'], layer=r['layer'],
                    status=a.get('solution_status'), author_mode=r.get('author_mode', 'unspecified'), complete=r['complete'], included=r['included'],
                    response_type=r['response_type'], steps=len(a.get('steps', [])), local_kcs=len(a.get('kc_candidates', [])),
                    methods=len(a.get('methods', [])), matched_catalog_nodes=len(set(m.values())),
                    unmatched_local_candidates=len(a.get('kc_candidates', [])) - len(m),
                    exclusion_reasons=';'.join(r['exclusion_reasons'])))
            if not r['included']: continue
            total += len(a['kc_candidates']); unmatched += len(a['kc_candidates']) - len(m)
            nodes = set(m.values()); freq.update(nodes); pairs.update(itertools.combinations(sorted(nodes), 2))
            steps = {s['id']: s for s in a['steps']}; seen = set()
            for method in a['methods']:
                for sa, sb in zip(method['step_ids'], method['step_ids'][1:]):
                    for ka in steps[sa]['kc_ids']:
                        for kb in steps[sb]['kc_ids']:
                            if ka in m and kb in m and m[ka] != m[kb]: seen.add((m[ka], m[kb]))
            trans.update(seen)
        decisions = [d for r in rows if r['layer'] == 'audited_new' and r['complete'] for d in r['audit']['decisions']]
        ds = Counter(d['status'] for d in decisions)
        for status in STATUSES:
            statusrows.append(dict(population=group, status=status, numerator=ds[status], denominator=len(decisions)))
        for k, n in sorted(freq.items()):
            frequencies.append(dict(population=group, catalog_kc_id=k, task_n=n, denominator=len(included)))
        co.extend(dict(population=group, kc_a=a, kc_b=b, task_n=n, denominator=len(included)) for (a, b), n in sorted(pairs.items()))
        transitions.extend(dict(population=group, from_kc=a, to_kc=b, task_n=n, denominator=len(included)) for (a, b), n in sorted(trans.items()))
        for dim in ('first_kes', 'all_kes', 'response_type', 'images', 'mathml', 'template_group'):
            c = Counter()
            for r in rows:
                inp = r['input']
                values = {'first_kes': [r['primary_kes']], 'all_kes': list(set(v.split()[0] for v in ext.meta(inp, 'КЭС:'))),
                          'response_type': [r['response_type']], 'images': [str(bool(inp['assets']))],
                          'mathml': [str(inp['mathml_count'] > 0)], 'template_group': [task_template(inp, True)]}[dim]
                c.update(values)
            composition.extend(dict(population=group, dimension=dim, value=v, task_n=n, denominator=len(rows)) for v, n in sorted(c.items()))
        structural = {}
        for typ in ('all', *sorted({r['response_type'] for r in rows})):
            subset = [r for r in included if typ == 'all' or r['response_type'] == typ]
            structural[typ] = {key: {'n': len(subset), 'median': statistics.median([len(r['author'][key]) for r in subset]) if subset else None,
                                  'distribution': dict(sorted(Counter(len(r['author'][key]) for r in subset).items()))}
                               for key in ('steps', 'kc_candidates', 'methods')}
        singleton = sum(v == 1 for v in freq.values())
        result[group] = dict(selected_n=len(rows), author_n=sum(r['author'] is not None for r in rows),
            complete_n=sum(r['complete'] for r in rows), included_n=len(included),
            solution_statuses=dict(Counter(r['author']['solution_status'] for r in rows if r['author'])),
            author_modes=dict(Counter(r.get('author_mode', 'unspecified') for r in rows if r['author'])),
            excluded=[{'task_id': r['task_id'], 'reasons': r['exclusion_reasons']} for r in rows if not r['included']],
            audit_statuses={s: {'numerator': ds[s], 'denominator': len(decisions)} for s in STATUSES},
            blocking_tasks=sum(r['audit'] is not None and 'blocking_audit_issue' in r['exclusion_reasons'] for r in rows),
            confirmed_catalog_nodes=len(freq), singleton_nodes={'numerator': singleton, 'denominator': len(freq)},
            incomplete_mapping_tasks=sum(len(mapping(r, assignments)) < len(r['author']['kc_candidates']) for r in included),
            unmatched_local_candidates={'numerator': unmatched, 'denominator': total}, structure=structural)
    for r in data['new']:
        if not r['complete']: continue
        names = {k['id']: k for k in r['author']['kc_candidates']}
        for d in r['audit']['decisions']:
            candidates.append(dict(task_id=r['task_id'], local_kc_id=d['local_kc_id'], name=names[d['local_kc_id']]['name'],
                status=d['status'], catalog_kc_id=d['catalog_kc_id'], blocking=d['blocking'],
                task_included=r['included'], rationale=d['rationale']))
    return result, dict(frequencies=frequencies, cooccurrence=co, transitions=transitions,
                       tasks=taskrows, composition=composition, audit_statuses=statusrows, candidates=candidates)


def page(title, body):
    return '<!doctype html><html lang="ru"><meta charset="utf-8"><title>' + html.escape(title) + '</title><style>body{font:17px/1.55 system-ui;max-width:1300px;margin:30px auto;padding:0 20px;color:#183340}table{border-collapse:collapse;width:100%}td,th{border:1px solid #ccd4da;padding:8px;vertical-align:top}img{max-width:100%;height:auto}pre{white-space:pre-wrap;overflow-wrap:anywhere}section{border-top:1px solid #abc;margin:20px 0}small{color:#567}a{color:#096c96}</style>' + body + '</html>'


def esc(value):
    return html.escape(str(value))


def cards(out, data):
    (out / 'cards').mkdir()
    for r in data['new']:
        tid = r['task_id']; inp = r['input']; tree = dom.fromstring(browser_math(inp['statement_html']))
        for image in tree.xpath('.//img'):
            match = next((a for a in inp['assets'] if Path(a['path']).name == Path(image.get('src', '')).name), None)
            if match:
                image.set('src', Path(os.path.relpath(RUN / 'inputs' / match['path'], out / 'cards')).as_posix())
        body = f'<nav><a href="../index.html">Отчёт</a></nav><h1>{r["order"]}. ФИПИ {esc(tid)}</h1>'
        body += '<p>Авторский разбор и аудит предварительны; внешней экспертизы нет.</p>'
        body += '<p>Технически завершена: ' + str(r['complete']) + '; в основных частотах: ' + str(r['included']) + ' · ' + esc('; '.join(r['exclusion_reasons'])) + '</p>'
        body += '<h2>Условие</h2><p>' + esc(inp['instruction']) + '</p>' + dom.tostring(tree, encoding='unicode')
        body += '<p>КЭС: ' + esc('; '.join(ext.meta(inp, 'КЭС:'))) + '</p>'
        a = r['author']
        if a:
            body += '<h2>Ответ</h2><p>' + esc(a.get('answer', '')) + '</p><h2>Шаги</h2><table><tr><th>ID / вход</th><th>Действие</th><th>Результат</th><th>Локальные KC</th></tr>'
            for s in a.get('steps', []):
                body += '<tr><td>' + esc(s['id'] + ' · ' + ', '.join(s['input_refs'])) + '</td><td>' + esc(s['action']) + '</td><td>' + esc(s['result']) + '</td><td>' + esc(', '.join(s['kc_ids'])) + '</td></tr>'
            body += '</table><h2>Методы</h2><pre>' + esc(json.dumps(a.get('methods', []), ensure_ascii=False, indent=2)) + '</pre><h2>Кандидаты и аудит</h2>'
            decisions = {d['local_kc_id']: d for d in r['audit'].get('decisions', [])} if r['audit'] else {}
            for k in a.get('kc_candidates', []):
                body += '<section id="' + esc(k['id']) + '"><h3>' + esc(k['id'] + ' · ' + k['name']) + '</h3><p>' + esc(k['description']) + '</p><pre>' + esc(json.dumps(decisions.get(k['id'], {'status': 'not_audited'}), ensure_ascii=False, indent=2)) + '</pre></section>'
            body += '<h2>Предупреждения автора</h2><pre>' + esc(json.dumps(a.get('warnings', []), ensure_ascii=False, indent=2)) + '</pre>'
        if r['audit']:
            body += '<h2>Замечания аудитора</h2><pre>' + esc(json.dumps(r['audit'].get('issues', []), ensure_ascii=False, indent=2)) + '</pre>'
        body += '<h2>Происхождение активных попыток</h2><pre>' + esc(json.dumps({k: v for k, v in r.items() if k.endswith('_path') or k == 'technical_errors'}, ensure_ascii=False, indent=2)) + '</pre>'
        (out / 'cards' / (tid + '.html')).write_text(page(tid, body), encoding='utf-8')


def figures(out, summary, tables):
    import textwrap
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 10})
    labels = {'baseline50': 'Исходные 50', 'new_latest50': 'Новые: последние 50', 'new_accumulated': 'Все новые'}
    def save(name):
        plt.tight_layout(); plt.savefig(out / (name + '.png'), dpi=140); plt.close()
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    for ax, dim in zip(axes, ('first_kes', 'response_type')):
        rows = [r for r in tables['composition'] if r['dimension'] == dim]
        vals = sorted({r['value'] for r in rows}); x = list(range(len(vals)))
        for i, group in enumerate(('baseline50', 'new_latest50', 'new_accumulated')):
            c = {r['value']: r for r in rows if r['population'] == group}
            label = labels[group] + f' · отобрано {summary[group]["selected_n"]}'
            ax.bar([v + (i - 1) * .25 for v in x], [100 * c[v]['task_n'] / c[v]['denominator'] if v in c else 0 for v in vals], .25, label=label)
        ax.set(xticks=x, xticklabels=vals, ylabel='% отобранных задач', title={'first_kes': 'Первая тематическая метка КЭС', 'response_type': 'Тип ответа'}[dim]); ax.tick_params(axis='x', rotation=60); ax.legend(fontsize=7)
    save('01-composition')
    fig, axes = plt.subplots(1, 3, figsize=(14, 4))
    for ax, key in zip(axes, ('steps', 'local_kcs', 'methods')):
        for i, group in enumerate(('baseline50', 'new_latest50', 'new_accumulated')):
            c = Counter(r[key] for r in tables['tasks'] if r['population'] == group and r['included'])
            n = summary[group]['included_n']
            label = labels[group] + f' · в анализе {n}'
            ax.bar([v + (i - 1) * .25 for v in sorted(c)], [100*c[v]/n if n else 0 for v in sorted(c)], .25, label=label)
        ax.set(title={'steps': 'Число содержательных шагов', 'local_kcs': 'Число локальных кандидатов KC', 'methods': 'Число методов'}[key], ylabel='% задач, включённых в анализ'); ax.legend(fontsize=7)
    save('02-structure')
    fig, ax = plt.subplots(figsize=(10, 4)); c = summary['new_accumulated']['audit_statuses']
    ax.bar(range(len(STATUSES)), [c[s]['numerator'] for s in STATUSES]); ax.set(xticks=range(len(STATUSES)), xticklabels=['Существующий KC', 'Новый кандидат', 'Требует разделения', 'Спорный'], ylabel='Локальных кандидатов', title=f'Статусы технически полных аудитов · n={c["match"]["denominator"]}')
    save('03-audit-statuses')
    freq = {(r['population'], r['catalog_kc_id']): r['task_n'] for r in tables['frequencies']}
    top = sorted({k for g, k in freq}, key=lambda k: (-freq.get(('mixed_cumulative', k), 0), k))[:20]
    names = {n['id']: n['name'] for n in read(RUN / 'catalog-for-auditor.json')['nodes']}
    fig, ax = plt.subplots(figsize=(14, 10)); y = list(range(len(top)))
    base = [freq.get(('baseline50', k), 0) for k in top]; new = [freq.get(('new_accumulated', k), 0) for k in top]
    ax.barh(y, base, label='Историческое редакторское'); ax.barh(y, new, left=base, label='Новое аудированное')
    ax.set(yticks=y, yticklabels=[textwrap.fill(names.get(k, k), 52) for k in top], xlabel='Подтверждения: уникальных задач', title='Фиксированный каталог · слои разделены'); ax.tick_params(axis='y', labelsize=8); ax.legend()
    save('04-catalog-evidence')


def notebook(out):
    """Executed notebook recomputes in memory from saved artifacts only."""
    import nbformat
    from nbclient import NotebookClient
    config = read(out / 'summary.json')
    final_name = out.name.removesuffix('.building')
    report_relative = (out.parent / final_name).relative_to(ROOT).as_posix()
    code = f'''import sys
from pathlib import Path
from IPython.display import display, Image, Markdown
root = next(p for p in (Path.cwd(), *Path.cwd().parents) if (p / 'scripts/report_fipi_extension.py').is_file())
sys.path.insert(0, str(root / 'scripts'))
import report_fipi_extension as report
data = report.collect({config['new_count']}, strict=False, active_snapshot=root / {config['active_snapshot']!r})
assert data['input_digest'] == {read(out / 'provenance.json')['input_digest']!r}, 'Saved inputs changed: use the code version recorded for this snapshot'
summary, tables = report.metrics(data)
report_path = root / {report_relative!r}
if not report_path.exists():
    report_path = report_path.with_name(report_path.name + '.building')
'''
    table_code = '''lines = ['| Слой | Отобрано | Завершено | В основных частотах | Узлов каталога с подтверждениями |', '|---|---:|---:|---:|---:|']
for key, name in [('baseline50','Исходные 50: редакторские связи'), ('new_latest50','Последние 50 новых'), ('new_accumulated','Все новые: агентный аудит'), ('mixed_cumulative','Смешанный накопленный корпус')]:
    s = summary[key]
    lines.append(f"| {name} | {s['selected_n']} | {s['complete_n']} | {s['included_n']} | {s['confirmed_catalog_nodes']} |")
display(Markdown('\\n'.join(lines)))
'''
    plots = '''for name in ['01-composition.png','02-structure.png','03-audit-statuses.png','04-catalog-evidence.png']:
    display(Image(filename=str(report_path / name)))
'''
    nb = nbformat.v4.new_notebook(cells=[nbformat.v4.new_markdown_cell('Офлайн-пересчёт сохранённого снимка. Новых агентов и сети нет. Метрики пересчитываются по зафиксированным попыткам; графики сохранённого снимка показаны ниже. Изменение исходных хешей останавливает пересчёт.'), nbformat.v4.new_code_cell(code), nbformat.v4.new_code_cell(table_code), nbformat.v4.new_code_cell("summary['new_accumulated']"), nbformat.v4.new_code_cell(plots)], metadata={'kernelspec': {'display_name': 'Python 3', 'language': 'python', 'name': 'python3'}})
    previous_path = os.environ.get('PATH', '')
    os.environ['PATH'] = str(ROOT / '.venv/Scripts') + os.pathsep + previous_path
    try:
        NotebookClient(nb, timeout=120, startup_timeout=30,
                       resources={'metadata': {'path': str(ROOT)}}).execute()
    finally:
        os.environ['PATH'] = previous_path
    nbformat.write(nb, out / 'review.ipynb')


def build(count, strict=False, version='v1', execute_notebook=True):
    data = collect(count, strict); summary, tables = metrics(data)
    target = RUN / 'derived' / (f'checkpoint-{count + 50}-{version}' if strict else 'progress-' + data['input_digest'][:16] + ('' if execute_notebook else '-without-notebook'))
    if target.exists():
        old = read(target / 'provenance.json')
        assert old['input_digest'] == data['input_digest'], f'Immutable checkpoint inputs changed: {target}; use explicit --version'
        for p, digest in read(target / 'output-hashes.json').items():
            assert sha(target / p) == digest, f'Existing artifact changed: {p}'
        print(str(target)); return target
    target.parent.mkdir(exist_ok=True)
    temp = target.with_name(target.name + '.building')
    assert not temp.exists(), f'Incomplete build exists; inspect before retry: {temp}'
    temp.mkdir()
    summary = dict(mode='checkpoint' if strict else 'progress_incomplete_permitted', new_count=count,
        checkpoint_total=count + 50, active_snapshot=Path(data['active_snapshot']).relative_to(ROOT).as_posix(), populations=summary, health_checks=data['health_checks'], technical_errors=data['technical_errors'],
        interpretations=['No answer key or external expertise: solved is not accuracy.', 'New candidates remain task-local; names do not establish identity.', 'Mixed cumulative frequencies combine historical editorial and independent audited provenance.', 'Transitions are task-presence across adjacent steps in a single method, excluding self-transitions; not prerequisites.', 'Composition describes selected tasks; main action frequencies exclude partial/unsolved, technical failures and any blocking audit issue.'])
    dump(temp / 'summary.json', summary)
    dump(temp / 'provenance.json', {k: data[k] for k in ('input_digest', 'input_hashes')})
    fields = dict(frequencies=['population','catalog_kc_id','task_n','denominator'], cooccurrence=['population','kc_a','kc_b','task_n','denominator'], transitions=['population','from_kc','to_kc','task_n','denominator'], tasks=['population','task_id','layer','status','author_mode','complete','included','response_type','steps','local_kcs','methods','matched_catalog_nodes','unmatched_local_candidates','exclusion_reasons'], composition=['population','dimension','value','task_n','denominator'], audit_statuses=['population','status','numerator','denominator'], candidates=['task_id','local_kc_id','name','status','catalog_kc_id','blocking','task_included','rationale'])
    for name, rows in tables.items(): csvout(temp, name + '.csv', rows, fields[name])
    dump(temp / 'active-tasks.json', [{k: r[k] for k in ('task_id', 'order', 'batch', 'complete', 'included', 'exclusion_reasons', 'technical_errors', 'author_path', 'auditor_path') if k in r} for r in data['new']])
    cards(temp, data); figures(temp, summary['populations'], tables)
    population_labels = {'baseline50':'Исходные 50: редакторские связи', 'new_latest50':'Последние 50 новых', 'new_accumulated':'Все новые: агентный аудит', 'mixed_cumulative':'Смешанный накопленный корпус'}
    status_labels = {'match':'Существующий KC', 'new_candidate':'Новый кандидат', 'needs_split':'Требует разделения', 'uncertain':'Спорный'}
    reason_labels = {'author_pending':'разбор ещё не получен', 'audit_pending':'аудит ещё не получен', 'technical_validation_failure':'ошибка технической проверки', 'blocking_audit_issue':'блокирующее замечание аудита', 'partial':'частичное решение', 'unsolved':'не решено', 'historical_partial_or_review_exclusion':'исторический partial или исключение прежней рецензией'}
    codebook = {}
    for row in data['baseline'] + data['new']:
        for m in row['input']['metadata']:
            if m['label'] == 'КЭС:':
                for v in m['values']:
                    code, _, title = v.partition(' ')
                    codebook[code] = title
    csvout(temp, 'kes-codebook.csv', [{'code':k,'title':v} for k,v in sorted(codebook.items())], ['code','title'])
    stage = 'Контрольная точка' if strict else 'Промежуточный снимок: работа продолжается'
    lines = [f'# ФИПИ: {stage}', '', f'Отобрано новых задач: {count}; плановый накопленный объём: {count + 50}. Фактическая готовность — в таблице.', '', 'Сохранённые решения и аудит; внешнего эталона нет. Статус solved не является оценкой точности.', '', '| Слой | Выбрано | Автор | Полных пар | В частотах | Подтверждённых определений | Единичные / определения |', '|---|---:|---:|---:|---:|---:|---:|']
    for group, s in summary['populations'].items():
        lines.append(f'| {population_labels[group]} | {s["selected_n"]} | {s["author_n"]} | {s["complete_n"]} | {s["included_n"]} | {s["confirmed_catalog_nodes"]} | {s["singleton_nodes"]["numerator"]}/{s["singleton_nodes"]["denominator"]} |')
    new = summary['populations']['new_accumulated']
    lines += ['', '## Происхождение активных решений', '', 'Самостоятельные первоначальные разборы и исправления с обратной связью учитываются раздельно; все исходные попытки сохранены. Их статусы не являются независимыми повторами.']
    mode_labels = {'standalone_initial':'Первоначальное самостоятельное решение', 'source_reading_feedback':'Исправление после указания ошибки чтения условия', 'corrected_attempt_unspecified':'Исправленная попытка: вид обратной связи не указан'}
    lines += [f'- {mode_labels.get(k,k)}: {n}.' for k,n in new['author_modes'].items()]
    for row in data['new']:
        if row.get('feedback_ref'):
            ref = os.path.relpath(RUN / row['feedback_ref'], temp).replace('\\', '/')
            lines.append(f'- {row["task_id"]}: [причина исправления и исходные попытки]({ref}); активное решение получено с обратной связью и не выдаётся за первоначальное самостоятельное.')
    lines += ['', f'Неполное сопоставление: {new["incomplete_mapping_tasks"]}/{new["included_n"]} задач основных частот. Несопоставленные локальные кандидаты: {new["unmatched_local_candidates"]["numerator"]}/{new["unmatched_local_candidates"]["denominator"]}. Это не число уникальных новых навыков.', '', '## Статусы аудита']
    lines += [f'- {status_labels[s]}: {v["numerator"]}/{v["denominator"]} локальных кандидатов технически полных аудитов.' for s, v in new['audit_statuses'].items()]
    lines += ['', '## Исключения из основных частот']
    lines += [f'- {r["task_id"]}: {", ".join(reason_labels.get(x,x) for x in r["reasons"])}' for r in summary['populations']['mixed_cumulative']['excluded']]
    lines += ['', '## Правила и ограничения'] + ['- ' + x for x in summary['interpretations']]
    lines += ['', 'Новая выборка случайна среди допустимого остатка; исторические 50 выбраны для охвата. Различия состава и процедуры не позволяют причинных выводов. Все метки КЭС и шаблоны — описательные характеристики, не подтверждение одинакового метода.', '', 'Первая метка КЭС — первая тематическая метка в записи банка, не обязательно главная тема задачи. Условия могут иметь несколько меток. Их [буквальные расшифровки](kes-codebook.csv) сохранены отдельно от KC; соответствие кодификатору конкретного года не установлено. [Карточки и графики](index.html).']
    (temp / 'report.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    body = '<h1>ФИПИ: офлайн-отчёт</h1><pre>' + esc('\n'.join(lines)) + '</pre>'
    body += ''.join(f'<h2>{i}</h2><img src="{name}.png">' for i, name in enumerate(('01-composition','02-structure','03-audit-statuses','04-catalog-evidence'), 1))
    body += '<h2>Карточки всех выбранных новых задач</h2><ul>' + ''.join(f'<li><a href="cards/{r["task_id"]}.html">{r["order"]}. {r["task_id"]}</a> · complete={r["complete"]}; included={r["included"]}</li>' for r in data['new']) + '</ul><h2>Контроль партий</h2><pre>' + esc(json.dumps(data['health_checks'], ensure_ascii=False, indent=2)) + '</pre>'
    (temp / 'index.html').write_text(page('ФИПИ: расширение', body), encoding='utf-8')
    if execute_notebook: notebook(temp)
    # Input changes during rendering must never silently produce a mixed snapshot.
    assert all(sha(ROOT / p) == h for p, h in data['input_hashes'].items()), 'Inputs changed during report build; inspect .building directory'
    dump(temp / 'output-hashes.json', {p.relative_to(temp).as_posix(): sha(p) for p in sorted(temp.rglob('*')) if p.is_file()})
    temp.rename(target)
    print(str(target)); return target


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('command', choices=['report', 'progress'])
    p.add_argument('--count', type=int, choices=[50, 100, 150], default=150, help='Number of NEW tasks; total = count + 50')
    p.add_argument('--version', default='v1', help='Explicit immutable checkpoint version')
    p.add_argument('--no-notebook', action='store_true', help='Progress only: skip notebook execution')
    a = p.parse_args()
    assert a.version and all(c.isalnum() or c in '-_' for c in a.version), 'Unsafe version'
    assert not (a.command == 'report' and a.no_notebook), 'Checkpoints require an executed notebook'
    build(a.count, a.command == 'report', a.version, not a.no_notebook)


if __name__ == '__main__':
    main()
