#!/usr/bin/env python3
"""Intermediate cumulative FIPI checkpoint EDA-250 from saved results only (no model calls, no network).

Corpus (per task records, not summed frequencies):
  - EDA-200 corpus, collected by the unchanged scripts/fipi_checkpoint200.py (historical 50, first 50 new,
    100 tasks of reservation #2);
  - first 50 tasks (batches 1-4) of reservation #4 (Bogdan108, next 100):
    data/annotation/runs/2026-11-09-fipi-team-bogdan108-next-100.
Metrics reuse report_fipi_extension.metrics() unchanged, called on different subsets, so all definitions
match checkpoint-100-v1 and EDA-200. Self-checks: EDA-100 and EDA-150 checks of EDA-200, plus the recomputed
EDA-200 summary and frequencies equal the saved EDA-200 outputs.

Usage:
  .venv/bin/python scripts/fipi_checkpoint250.py check
  .venv/bin/python scripts/fipi_checkpoint250.py build [--out data/annotation/analyses/2026-11-09-fipi-checkpoint-250-v1]
The output directory is immutable: an existing directory is never overwritten (use a new -vN name).
"""
import argparse
import csv
import hashlib
import json
import os
import sys
import textwrap
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fipi_checkpoint200 as cp  # noqa: E402  (unchanged; provides EDA-200 corpus and helpers)

rep, ext = cp.rep, cp.ext
plt, dom, Image = cp.plt, cp.dom, cp.Image
ROOT = cp.ROOT
H200 = ROOT / 'data/annotation/analyses/2026-11-09-fipi-checkpoint-200-v1'
NEXT = ROOT / 'data/annotation/runs/2026-11-09-fipi-team-bogdan108-next-100'
NEXT_BATCHES = [1, 2, 3, 4]
DEFAULT_OUT = 'data/annotation/analyses/2026-11-09-fipi-checkpoint-250-v1'
STATUSES, STATUS_LABELS, REASON_LABELS = cp.STATUSES, cp.STATUS_LABELS, cp.REASON_LABELS
read, sha, dump, csvout, pct = cp.read, cp.sha, cp.dump, cp.csvout, cp.pct

POPULATIONS = {
    'baseline50': 'Исходные 50: редакторские связи',
    'ext_new50': 'Первые 50 новых (запуск 2026-11-02): агентный аудит',
    'team100': 'Бронь #2, 100 задач (партии 5–12): агентный аудит',
    'team_b5_default': 'Бронь #2, партия 5: Opus, уровень рассуждений по умолчанию',
    'team_b6_12_low': 'Бронь #2, партии 6–12: Opus, effort low',
    'next50': 'Бронь #4, первые 50 задач (партии 1–4): Opus, effort low',
    'audited_new200': 'Все новые 200: агентный аудит',
    'mixed_cumulative250': 'Смешанный накопленный корпус 250',
}


# ---------------------------------------------------------------- collection

def collect_next(paths):
    """Validate and load batches 1-4 of reservation #4; read-only. Mirrors fipi_checkpoint200.collect_team."""
    def load(p):
        p = Path(p); paths.add(p.resolve()); return read(p)
    manifest = load(NEXT / 'manifest.json')
    assert load(NEXT / 'active-attempts.json') == {}, 'active attempts present: selection must be adapted explicitly'
    for name in ('PROTOCOL.md', 'author-prompt.txt', 'auditor-prompt.txt', 'author-wrapper.txt', 'audit-format-wrapper-v1.1.txt',
                 'catalog-for-auditor.json', 'reservation.json', 'environment.json'):
        paths.add((NEXT / name).resolve())
    batches = {b: manifest['batches'][str(b)] for b in NEXT_BATCHES}
    entries = {t['task_id']: t for t in manifest['tasks']}
    health, accepted = {}, {}
    for b in NEXT_BATCHES:
        h = load(NEXT / f'checks/batch-{b:02}.json')
        assert h['batch'] == b and h['task_ids'] == batches[b], f'health check ids batch {b}'
        assert h['status'] == 'pass' and not h['quarantined_ids'] and h['systemic_unresolved'] is False, f'batch {b} not pass'
        for x in h.get('accepted_after_review', []):
            assert sha(ROOT / x['resolution']) == x['sha256']; paths.add((ROOT / x['resolution']).resolve())
            accepted[x['task_id']] = x['resolution']
        math = load(NEXT / f'checks/batch-{b:02}-math.json')
        review = NEXT / f'checks/batch-{b:02}-math-review.json'
        if review.exists():
            load(review)
        health[b] = dict(status=h['status'], controls=[dict(task_id=c['task_id'], status=c['status']) for c in math['checks']],
                         accepted_after_review=[x['task_id'] for x in h.get('accepted_after_review', [])])
    rows = []
    for b in NEXT_BATCHES:
        for tid in batches[b]:
            e = entries[tid]
            inp_path = NEXT / 'inputs/tasks' / f'{tid}.json'
            assert sha(inp_path) == e['input_sha256'], f'input hash {tid}'
            inp = load(inp_path)
            for a in inp['assets']:
                p = NEXT / 'inputs' / a['path']; paths.add(p.resolve())
                assert sha(p) == a['sha256'], f'image hash {a["path"]}'
                with Image.open(p) as im: im.verify()
            ap, qp = NEXT / 'raw/author' / f'{tid}.json', NEXT / 'raw/auditor' / f'{tid}.json'
            author, audit = load(ap), load(qp)
            cp.validate_one(author); assert author['task_id'] == tid and audit['task_id'] == tid
            va = load(NEXT / 'validations' / f'author-{tid}.json')['result']
            vq = load(NEXT / 'validations' / f'auditor-{tid}.json')['result']
            assert va['status'] == 'technical_pass' and vq['status'] == 'technical_pass', f'validation {tid}'
            assert vq['audit_sha256'] == sha(qp) and vq['author_sha256'] == sha(ap), f'validated bytes changed {tid}'
            ex = {role: load(NEXT / 'executions' / f'{role}-{tid}.json') for role in ('author', 'auditor')}
            reasons = []
            if author['solution_status'] != 'solved' and tid not in accepted:
                reasons.append(author['solution_status'])
            if any(i.get('blocking') for i in audit.get('issues', [])) or any(d.get('blocking') for d in audit.get('decisions', [])):
                reasons.append('blocking_audit_issue')
            rows.append(dict(task_id=tid, order=e['order'], batch=b, primary_kes=e['primary_kes'], response_type=e['response_type'],
                             layer='audited_new', source='next', input=inp, author=author, audit=audit, complete=True,
                             included=not reasons, exclusion_reasons=reasons, technical_errors=[],
                             author_mode='standalone_initial', feedback_ref=None,
                             accepted_after_review=accepted.get(tid),
                             author_path=str(ap.relative_to(ROOT)), auditor_path=str(qp.relative_to(ROOT)),
                             model=ex['author']['model'], model_requested=ex['author'].get('model_requested'),
                             auditor_model_requested=ex['auditor'].get('model_requested')))
    return rows, health, manifest


def collect():
    data = cp.collect()
    paths = {(ROOT / p).resolve() for p in data['input_hashes']}
    paths.add((ROOT / 'scripts/fipi_checkpoint250.py').resolve())
    for name in ('summary.json', 'batches.json', 'tables/frequencies.csv'):
        paths.add((H200 / name).resolve())
    nxt, health, manifest = collect_next(paths)
    provenance = {Path(p).resolve().relative_to(ROOT).as_posix(): sha(p) for p in sorted(paths)}
    data.update(next=nxt, next_health=health, next_manifest=manifest, input_hashes=provenance,
                input_digest=hashlib.sha256(json.dumps(provenance, sort_keys=True).encode()).hexdigest())
    return data


# ---------------------------------------------------------------- metrics (historical definitions)

def metrics(data):
    team, nxt = data['team'], data['next']
    calls = {  # population -> (new rows, population key of report_fipi_extension.metrics)
        'baseline50': (data['ext'], 'baseline50'),
        'ext_new50': (data['ext'], 'new_accumulated'),
        'team100': (team, 'new_accumulated'),
        'team_b5_default': ([r for r in team if r['batch'] == 5], 'new_accumulated'),
        'team_b6_12_low': ([r for r in team if r['batch'] != 5], 'new_accumulated'),
        'next50': (nxt, 'new_accumulated'),
        'audited_new200': (data['ext'] + team + nxt, 'new_accumulated'),
        'mixed_cumulative250': (data['ext'] + team + nxt, 'mixed_cumulative'),
    }
    cache, summary = {}, {}
    tables = {k: [] for k in ('frequencies', 'cooccurrence', 'transitions', 'tasks', 'composition', 'audit_statuses')}
    for pop, (rows, key) in calls.items():
        k = tuple(r['task_id'] for r in rows)
        if k not in cache:
            cache[k] = rep.metrics(cp._subset(data, rows))
        s, t = cache[k]
        summary[pop] = s[key]
        for name in tables:
            tables[name] += [dict(row, population=pop) for row in t[name] if row['population'] == key]
    source = {r['task_id']: r for r in data['ext'] + team + nxt}
    resv = {'ext': '', 'team': 'issue-2', 'next': 'issue-4'}
    for row in tables['tasks']:
        r = source.get(row['task_id'])
        if r is None:
            continue
        row.update(batch=r['batch'], reservation=resv[r['source']])
        if r['source'] in ('team', 'next'):
            row.update(layer='audited_team' if r['source'] == 'team' else 'audited_next', model_requested=r['model_requested'],
                       accepted_after_review=bool(r['accepted_after_review']))
    _, t_all = cache[tuple(r['task_id'] for r in data['ext'] + team + nxt)]
    tables['candidates'] = [dict(c, source=source[c['task_id']]['source'], reservation=resv[source[c['task_id']]['source']],
                                 batch=source[c['task_id']]['batch']) for c in t_all['candidates']]
    return summary, tables


def self_checks(data):
    """EDA-200 self-checks plus: recomputed EDA-200 summary and frequencies equal the saved EDA-200 outputs."""
    checks = cp.self_checks(data)
    s200, t200 = cp.metrics(data)
    checks['eda200_summary_reproduced'] = json.loads(json.dumps(s200)) == read(H200 / 'summary.json')['populations']
    saved = list(csv.DictReader(open(H200 / 'tables/frequencies.csv', encoding='utf-8-sig')))
    fields = ['population', 'catalog_kc_id', 'task_n', 'denominator']
    checks['eda200_frequencies_reproduced'] = saved == [{k: str(r[k]) for k in fields} for r in t200['frequencies']]
    return checks


# ---------------------------------------------------------------- outputs

def cards(out, data):
    (out / 'cards').mkdir()
    esc = rep.esc
    for r in data['next']:
        tid, inp = r['task_id'], r['input']
        tree = dom.fromstring(cp.browser_math(inp['statement_html']))
        for image in tree.xpath('.//img'):
            match = next((a for a in inp['assets'] if Path(a['path']).name == Path(image.get('src', '')).name), None)
            if match:
                image.set('src', Path(os.path.relpath(NEXT / 'inputs' / match['path'], out / 'cards')).as_posix())
        body = f'<nav><a href="../index.html">Отчёт</a></nav><h1>{r["order"]}. ФИПИ {esc(tid)} · бронь #4, партия {r["batch"]}</h1>'
        body += '<p>Авторский разбор и аудит предварительны; внешней экспертизы нет.</p>'
        body += f'<p>Модель автора: {esc(r["model"])} ({esc(r["model_requested"])}); в основных частотах: {r["included"]}'
        body += (' · принята после просмотра' if r['accepted_after_review'] else '') + ' · ' + esc('; '.join(r['exclusion_reasons'])) + '</p>'
        body += '<h2>Условие</h2><p>' + esc(inp['instruction']) + '</p>' + dom.tostring(tree, encoding='unicode')
        body += '<p>КЭС: ' + esc('; '.join(ext.meta(inp, 'КЭС:'))) + '</p>'
        a = r['author']
        body += '<h2>Ответ</h2><p>' + esc(a.get('answer', '')) + '</p><h2>Шаги</h2><table><tr><th>ID / вход</th><th>Действие</th><th>Результат</th><th>Локальные KC</th></tr>'
        for s in a['steps']:
            body += '<tr><td>' + esc(s['id'] + ' · ' + ', '.join(s['input_refs'])) + '</td><td>' + esc(s['action']) + '</td><td>' + esc(s['result']) + '</td><td>' + esc(', '.join(s['kc_ids'])) + '</td></tr>'
        body += '</table><h2>Методы</h2><pre>' + esc(json.dumps(a['methods'], ensure_ascii=False, indent=2)) + '</pre><h2>Кандидаты и аудит</h2>'
        decisions = {d['local_kc_id']: d for d in r['audit']['decisions']}
        for k in a['kc_candidates']:
            body += '<section id="' + esc(k['id']) + '"><h3>' + esc(k['id'] + ' · ' + k['name']) + '</h3><p>' + esc(k['description']) + '</p><pre>' + esc(json.dumps(decisions.get(k['id'], {'status': 'not_audited'}), ensure_ascii=False, indent=2)) + '</pre></section>'
        body += '<h2>Предупреждения автора</h2><pre>' + esc(json.dumps(a.get('warnings', []), ensure_ascii=False, indent=2)) + '</pre>'
        body += '<h2>Замечания аудитора</h2><pre>' + esc(json.dumps(r['audit'].get('issues', []), ensure_ascii=False, indent=2)) + '</pre>'
        body += '<h2>Источник</h2><pre>' + esc(json.dumps({k: r[k] for k in ('author_path', 'auditor_path', 'accepted_after_review')}, ensure_ascii=False, indent=2)) + '</pre>'
        (out / 'cards' / f'{tid}.html').write_text(rep.page(tid, body), encoding='utf-8')


FIG_GROUPS = ('baseline50', 'ext_new50', 'team100', 'next50')
FIG_LABELS = {'baseline50': 'Исходные 50', 'ext_new50': 'Первые 50 новых', 'team100': 'Бронь #2, 100', 'next50': 'Бронь #4, 50'}


def figures(out, summary, tables):
    fig_dir = out / 'figures'; fig_dir.mkdir()
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 10})
    w = .2

    def save(name):
        plt.tight_layout(); plt.savefig(fig_dir / f'{name}.png', dpi=140); plt.close()

    def off(i, n):
        return (i - (n - 1) / 2) * w
    fig, axes = plt.subplots(1, 2, figsize=(15, 5))
    for ax, dim in zip(axes, ('first_kes', 'response_type')):
        rows = [r for r in tables['composition'] if r['dimension'] == dim]
        vals = sorted({r['value'] for r in rows}); x = list(range(len(vals)))
        for i, g in enumerate(FIG_GROUPS):
            c = {r['value']: r for r in rows if r['population'] == g}
            ax.bar([v + off(i, len(FIG_GROUPS)) for v in x], [100 * c[v]['task_n'] / c[v]['denominator'] if v in c else 0 for v in vals], w,
                   label=f'{FIG_LABELS[g]} · отобрано {summary[g]["selected_n"]}')
        ax.set(xticks=x, xticklabels=vals, ylabel='% отобранных задач',
               title={'first_kes': 'Первая тематическая метка КЭС', 'response_type': 'Тип ответа'}[dim])
        ax.tick_params(axis='x', rotation=60); ax.legend(fontsize=7)
    save('01-composition')
    fig, axes = plt.subplots(1, 3, figsize=(16, 4))
    for ax, key in zip(axes, ('steps', 'local_kcs', 'methods')):
        for i, g in enumerate(FIG_GROUPS):
            c = Counter(r[key] for r in tables['tasks'] if r['population'] == g and r['included'])
            n = summary[g]['included_n']
            ax.bar([v + off(i, len(FIG_GROUPS)) for v in sorted(c)], [100 * c[v] / n for v in sorted(c)], w, label=f'{FIG_LABELS[g]} · в анализе {n}')
        ax.set(title={'steps': 'Число содержательных шагов', 'local_kcs': 'Число локальных кандидатов KC', 'methods': 'Число методов'}[key],
               ylabel='% задач, включённых в анализ'); ax.legend(fontsize=7)
    save('02-structure')
    fig, ax = plt.subplots(figsize=(12, 4.5))
    groups = ('ext_new50', 'team_b5_default', 'team_b6_12_low', 'next50')
    names = {'ext_new50': 'Первые 50 новых', 'team_b5_default': 'Бронь #2: партия 5 (по умолчанию)',
             'team_b6_12_low': 'Бронь #2: партии 6–12 (effort low)', 'next50': 'Бронь #4: партии 1–4 (effort low)'}
    for i, g in enumerate(groups):
        c = summary[g]['audit_statuses']; d = c['match']['denominator']
        ax.bar([x + off(i, len(groups)) for x in range(len(STATUSES))], [100 * c[s]['numerator'] / d for s in STATUSES], w, label=f'{names[g]} · n={d}')
    ax.set(xticks=range(len(STATUSES)), xticklabels=[STATUS_LABELS[s] for s in STATUSES], ylabel='% локальных кандидатов',
           title='Решения аудитора по слоям происхождения'); ax.legend(fontsize=8)
    save('03-audit-statuses')
    freq = {(r['population'], r['catalog_kc_id']): r['task_n'] for r in tables['frequencies']}
    top = sorted({k for g, k in freq if g == 'mixed_cumulative250'}, key=lambda k: (-freq[('mixed_cumulative250', k)], k))[:25]
    cat_names = {n['id']: n['name'] for n in read(cp.EXT / 'catalog-for-auditor.json')['nodes']}
    fig, ax = plt.subplots(figsize=(14, 12)); y = list(range(len(top))); left = [0] * len(top)
    for g, label in (('baseline50', 'Исторические редакторские'), ('ext_new50', 'Первые 50 новых'), ('team100', 'Бронь #2, 100'), ('next50', 'Бронь #4, 50')):
        vals = [freq.get((g, k), 0) for k in top]
        ax.barh(y, vals, left=left, label=label); left = [a + b for a, b in zip(left, vals)]
    ax.set(yticks=y, yticklabels=[textwrap.fill(cat_names.get(k, k), 52) for k in top], xlabel='Подтверждения: уникальных задач',
           title='Фиксированный каталог: 25 самых частых узлов, слои разделены'); ax.invert_yaxis(); ax.tick_params(axis='y', labelsize=8); ax.legend()
    save('04-catalog-evidence')


def report_lines(data, summary, tables, checks):
    s = summary
    lines = ['# ФИПИ: промежуточная накопленная контрольная точка 250 задач', '',
             'Расчёт по сохранённым разборам и аудитам, без новых модельных запросов. Корпус — [EDA-200](../2026-11-09-fipi-checkpoint-200-v1/report.md) '
             'и первые 50 задач брони #4 Bogdan108 (партии 1–4 из 8). Определения метрик — как в '
             '[EDA-100](../../runs/2026-11-02-fipi-extension-150/derived/checkpoint-100-v1/report.md) и EDA-200: узел каталога считается '
             'подтверждённым в задаче, если аудитор поставил `match` без блокировки; частоты — число задач, а не упоминаний; '
             'единичный узел — подтверждён ровно в одной включённой задаче. Внешнего эталона нет; статус `solved` не является оценкой точности.', '',
             '## 1. Слои и готовность', '',
             '| Слой | Выбрано | Полных пар | В частотах | Подтверждённых узлов | Единичные / узлы | Несопоставленные кандидаты |',
             '|---|---:|---:|---:|---:|---:|---:|']
    for pop, label in POPULATIONS.items():
        p = s[pop]
        lines.append(f'| {label} | {p["selected_n"]} | {p["complete_n"]} | {p["included_n"]} | {p["confirmed_catalog_nodes"]} | '
                     f'{p["singleton_nodes"]["numerator"]}/{p["singleton_nodes"]["denominator"]} | '
                     f'{p["unmatched_local_candidates"]["numerator"]}/{p["unmatched_local_candidates"]["denominator"]} |')
    lines += ['', 'Слой «Исходные 50» содержит редакторские связи основного ассистента; остальные слои — независимый агентный аудит. '
              'Смешанный корпус объединяет разное происхождение, поэтому его частоты описательные. '
              'Бронь #4 выполнена наполовину: партии 5–8 (ещё 50 задач) не входят в эту точку.', '']
    freq = {}
    for r in tables['frequencies']:
        freq.setdefault(r['population'], {})[r['catalog_kc_id']] = r['task_n']
    old_nodes = set(freq['baseline50']) | set(freq['ext_new50']) | set(freq['team100'])
    next_nodes = set(freq['next50'])
    added = sorted(next_nodes - old_nodes)
    m200 = read(H200 / 'summary.json')['populations']['mixed_cumulative200']
    m250 = s['mixed_cumulative250']
    lines += ['## 2. Что добавилось', '',
              f'- Бронь #4 добавила {s["next50"]["included_n"]} включённых задач. Узлов каталога, подтверждённых в них: {len(next_nodes)}; '
              f'из них не подтверждённых в EDA-200: {len(added)} ({", ".join(f"`{k}`" for k in added) or "нет"}).',
              f'- Подтверждённых узлов в смешанном корпусе: {m200["confirmed_catalog_nodes"]} (EDA-200) → {m250["confirmed_catalog_nodes"]} (EDA-250); '
              f'единичных: {m200["singleton_nodes"]["numerator"]}/{m200["singleton_nodes"]["denominator"]} → '
              f'{m250["singleton_nodes"]["numerator"]}/{m250["singleton_nodes"]["denominator"]}.',
              f'- Кандидаты брони #4, которым аудитор не нашёл узла (`new_candidate`): {s["next50"]["audit_statuses"]["new_candidate"]["numerator"]}. '
              'Это локальные предложения отдельных задач, а не число уникальных новых навыков: межзадачной консолидации не было.', '']
    lines += ['## 3. Изменения относительно EDA-200 по тем же определениям', '',
              '| Показатель | Бронь #2, партии 6–12 (effort low) | Бронь #4, партии 1–4 (effort low) | Бронь #2, 100 | Все новые 200 |', '|---|---:|---:|---:|---:|']
    cols = ('team_b6_12_low', 'next50', 'team100', 'audited_new200')
    for st in STATUSES:
        lines.append(f'| {STATUS_LABELS[st]} | ' + ' | '.join(pct(s[c]['audit_statuses'][st]['numerator'], s[c]['audit_statuses'][st]['denominator']) for c in cols) + ' |')
    for key, label in (('steps', 'Медиана шагов'), ('kc_candidates', 'Медиана локальных KC')):
        lines.append(f'| {label} | ' + ' | '.join(f"{s[c]['structure']['all'][key]['median']:g}".replace('.', ',') for c in cols) + ' |')
    lines.append('| Задачи с неполным сопоставлением | ' + ' | '.join(pct(s[c]['incomplete_mapping_tasks'], s[c]['included_n']) for c in cols) + ' |')
    lines += ['', 'Бронь #4 исполнена той же моделью и с тем же уровнем рассуждений, что партии 6–12 брони #2 (`claude-opus-5-5`, `effort: low`), '
              'по той же методике и тем же каталогом. Различия между этими слоями не объясняются моделью, но могут объясняться составом: '
              'задачи брони #4 — отдельный случайный отбор из остатка банка после брони #2 и #3, а выборки малы (85 и 50 задач). '
              'В партии 3 брони #4 аудиторы прерывались лимитом API и продолжали работу в том же контексте. '
              '[Состав выборки](figures/01-composition.png), [статусы аудита](figures/03-audit-statuses.png).', '']
    lines += ['## 4. Контрольные задачи, исключения и спорные случаи', '']
    ctrl = Counter(); after = []
    for b, h in data['next_health'].items():
        for c in h['controls']:
            ctrl[c['status']] += 1
            if c['status'] != 'match': after.append(f'{c["task_id"]} (партия {b})')
    lines.append(f'- Контрольные задачи брони #4, сверенные с ожиданиями, записанными до авторских ответов: {sum(ctrl.values())}; '
                 f'`match` — {ctrl["match"]}, `match_after_review` — {ctrl["match_after_review"]} ({", ".join(after) or "нет"}). '
                 '`match_after_review` означает, что ответ из нескольких пунктов не сравнивается строкой; сравнение сделано после просмотра '
                 'ответа и слепой проверкой не является.')
    acc = [r['task_id'] for r in data['next'] if r['accepted_after_review']]
    lines.append(f'- Приняты после просмотра при статусе автора не `solved`: {", ".join(acc) or "нет"}.')
    excl = s['mixed_cumulative250']['excluded']
    lines += ['- Исключены из основных частот смешанного корпуса:'] + [f'  - {e["task_id"]}: {", ".join(REASON_LABELS.get(x, x) for x in e["reasons"])}' for e in excl]
    warn = [r['task_id'] for r in data['next'] if r['author'].get('warnings')]
    issues = sum(len(r['audit']['issues']) for r in data['next'])
    blocking = sum(i['blocking'] for r in data['next'] for i in r['audit']['issues'])
    math_issues = [r['task_id'] for r in data['next'] if any(i.get('kind') == 'math' for i in r['audit']['issues'])]
    lines += [f'- В брони #4 задач с предупреждениями авторов: {len(warn)}; замечаний аудиторов: {issues}, из них блокирующих: {blocking}. '
              f'Спорных решений аудитора (`uncertain`): {s["next50"]["audit_statuses"]["uncertain"]["numerator"]}. '
              'Подробности — в [карточках](index.html) и [таблице кандидатов](tables/candidates.csv).',
              f'- Неблокирующие математические замечания аудиторов брони #4: {", ".join(math_issues) or "нет"}. '
              'Они не отменяют сопоставлений KC, поэтому задачи входят в частоты, но ответы этих задач независимым ожиданием не проверялись:',
              '  - FAAE63 (прямоугольник и перпендикуляр к диагонали): аудитор отметил неточную формулировку обоснования угла в шаге s2 '
              'и оценил итог как верный.',
              '  - 0B2322 (число точек, где производная положительна, по графику функции): автор отнёс точки вблизи экстремумов к участкам '
              'монотонности на глаз и ответил 3; аудитор допускает, что x3 — локальный максимум, и тогда ответ 2.',
              '  - 724631 (задача с пунктами а–в о десятичной записи чисел): текст шага s2 оборван; аудитор отметил, что граничный случай a = 1, '
              'b = c = 0 в выводе s2 требует оговорки, и оценил, что на итоговый ответ это не влияет.',
              '- Задачи с чтением координат по рисунку (97C4EA, FEE4C3, 6F2D5E, 6FA927, c1936D, 0B2322) зависят от качества изображения; '
              'в FEE4C3 автор дополнительно считал пиксели узлов сетки во временной копии рисунка.', '']
    lines += ['## 5. Какие выводы пока невозможны', '',
              '- Это промежуточная точка: бронь #4 выполнена наполовину, и доли слоя «Бронь #4» могут измениться после партий 5–8.',
              '- Нельзя оценить точность решений: внешнего эталона нет, контрольные ответы проверены выборочно (3 задачи на партию).',
              '- Нельзя считать `new_candidate` новыми уникальными навыками и сравнивать их число между слоями как прирост каталога.',
              '- Нельзя приписать различия долей статусов аудита между бронями #2 и #4 исполнителю: модель и уровень рассуждений совпадают, '
              'а состав задач различается.',
              '- Совместная встречаемость и переходы между узлами — описательные; они не доказывают порядок изучения или зависимость навыков.', '',
              '## 6. Самопроверки', '',
              f'- Пересчёт EDA-100 из тех же записей совпал с сохранённой сводкой: {checks["eda100_summary_reproduced"]}; частоты: {checks["eda100_frequencies_reproduced"]}.',
              f'- Пересчёт частот узлов на 150 задачах совпал с кратким EDA-150: {checks["eda150_node_frequencies_reproduced"]} ({checks["eda150_included_tasks"]} включённых задач).',
              f'- Пересчёт EDA-200 совпал с сохранённой сводкой: {checks["eda200_summary_reproduced"]}; частоты: {checks["eda200_frequencies_reproduced"]}.', '',
              '## Материалы', '',
              '- [Карточки задач брони #4 и графики](index.html); карточки брони #2 — в [EDA-200](../2026-11-09-fipi-checkpoint-200-v1/index.html); '
              'первых 50 новых — в [EDA-100](../../runs/2026-11-02-fipi-extension-150/derived/checkpoint-100-v1/index.html); '
              'разборы исходных 50 — в [EDA-50](../../runs/2026-10-31-fipi-50x1/derived/index.html).',
              '- Таблицы: [задачи](tables/tasks.csv), [кандидаты](tables/candidates.csv), [частоты](tables/frequencies.csv), '
              '[совместная встречаемость](tables/cooccurrence.csv), [переходы](tables/transitions.csv), [состав](tables/composition.csv), '
              '[статусы аудита](tables/audit_statuses.csv), [расшифровка КЭС](tables/kes-codebook.csv).',
              '- Исполненный ноутбук пересчёта: [review.ipynb](review.ipynb). Входы и хеши: [provenance.json](provenance.json), '
              'партии: [batches.json](batches.json).', '',
              'Первая метка КЭС — первая тематическая метка в записи банка, не обязательно главная тема задачи. '
              'Метки КЭС и шаблоны — описательные характеристики, не подтверждение одинакового метода.']
    return lines


def notebook(out, digest):
    import nbformat
    from nbclient import NotebookClient
    final = out.name.removesuffix('.building')
    rel = (out.parent / final).relative_to(ROOT).as_posix()
    code = f'''import sys
from pathlib import Path
from IPython.display import display, Image, Markdown
root = next(p for p in (Path.cwd(), *Path.cwd().parents) if (p / 'scripts/fipi_checkpoint250.py').is_file())
sys.path.insert(0, str(root / 'scripts'))
import fipi_checkpoint250 as cp
data = cp.collect()
assert data['input_digest'] == {digest!r}, 'Saved inputs changed: use the code version recorded for this snapshot'
summary, tables = cp.metrics(data)
checks = cp.self_checks(data)
report_path = root / {rel!r}
if not report_path.exists():
    report_path = report_path.with_name(report_path.name + '.building')
checks
'''
    table = '''lines = ['| Слой | Отобрано | В частотах | Подтверждённых узлов | Единичные |', '|---|---:|---:|---:|---:|']
for key, name in cp.POPULATIONS.items():
    s = summary[key]
    lines.append(f"| {name} | {s['selected_n']} | {s['included_n']} | {s['confirmed_catalog_nodes']} | {s['singleton_nodes']['numerator']} |")
display(Markdown('\\n'.join(lines)))
'''
    plots = '''for name in ['01-composition', '02-structure', '03-audit-statuses', '04-catalog-evidence']:
    display(Image(filename=str(report_path / 'figures' / (name + '.png'))))
'''
    nb = nbformat.v4.new_notebook(cells=[
        nbformat.v4.new_markdown_cell('Офлайн-пересчёт промежуточной накопленной контрольной точки 250 задач из сохранённых разборов и аудитов. '
                                      'Новых агентов и сети нет; изменение исходных хешей останавливает пересчёт.'),
        nbformat.v4.new_code_cell(code), nbformat.v4.new_code_cell(table),
        nbformat.v4.new_code_cell("{k: summary[k]['audit_statuses'] for k in ('ext_new50', 'team100', 'team_b6_12_low', 'next50')}"),
        nbformat.v4.new_code_cell(plots)],
        metadata={'kernelspec': {'display_name': 'Python 3', 'language': 'python', 'name': 'python3'}})
    prev = os.environ.get('PATH', '')
    os.environ['PATH'] = str(ROOT / '.venv/bin') + os.pathsep + prev
    try:
        NotebookClient(nb, timeout=300, startup_timeout=60, resources={'metadata': {'path': str(ROOT)}}).execute()
    finally:
        os.environ['PATH'] = prev
    nbformat.write(nb, out / 'review.ipynb')


def build(out_rel):
    target = ROOT / out_rel
    assert not target.exists(), f'{target} exists; immutable checkpoint: choose a new version'
    temp = target.with_name(target.name + '.building')
    assert not temp.exists(), f'Incomplete build exists; inspect before retry: {temp}'
    data = collect(); summary, tables = metrics(data); checks = self_checks(data)
    assert all(v for k, v in checks.items() if k != 'eda150_included_tasks'), f'Self-check failed: {checks}'
    temp.mkdir(parents=True)
    (temp / 'tables').mkdir()
    fields = dict(
        frequencies=['population', 'catalog_kc_id', 'task_n', 'denominator'],
        cooccurrence=['population', 'kc_a', 'kc_b', 'task_n', 'denominator'],
        transitions=['population', 'from_kc', 'to_kc', 'task_n', 'denominator'],
        tasks=['population', 'task_id', 'layer', 'reservation', 'batch', 'model_requested', 'status', 'author_mode', 'complete', 'included',
               'accepted_after_review', 'response_type', 'steps', 'local_kcs', 'methods', 'matched_catalog_nodes',
               'unmatched_local_candidates', 'exclusion_reasons'],
        composition=['population', 'dimension', 'value', 'task_n', 'denominator'],
        audit_statuses=['population', 'status', 'numerator', 'denominator'],
        candidates=['source', 'reservation', 'batch', 'task_id', 'local_kc_id', 'name', 'status', 'catalog_kc_id', 'blocking', 'task_included', 'rationale'])
    for name, rows in tables.items():
        csvout(temp / 'tables' / f'{name}.csv', rows, fields[name])
    codebook = {}
    for row in data['baseline'] + data['ext'] + data['team'] + data['next']:
        for m in row['input']['metadata']:
            if m['label'] == 'КЭС:':
                for v in m['values']:
                    code, _, title = v.partition(' '); codebook[code] = title
    csvout(temp / 'tables' / 'kes-codebook.csv', [{'code': k, 'title': v} for k, v in sorted(codebook.items())], ['code', 'title'])
    m = data['next_manifest']
    batches = dict(
        eda200=dict(path=H200.relative_to(ROOT).as_posix(), batches=read(H200 / 'batches.json')),
        reservation4=dict(run=NEXT.relative_to(ROOT).as_posix(), issue=m['issue_url'], owner=m['owner'],
                          method_version=m['method_version'], queue_orders=m['queue_orders'], selection=m.get('selection'),
                          included_batches=NEXT_BATCHES,
                          batches={str(b): dict(tasks=[r['task_id'] for r in data['next'] if r['batch'] == b],
                                                model_requested=sorted({r['model_requested'] for r in data['next'] if r['batch'] == b}),
                                                **data['next_health'][b]) for b in NEXT_BATCHES}))
    dump(temp / 'batches.json', batches)
    dump(temp / 'summary.json', dict(scope='EDA-250 (intermediate): EDA-200 corpus + Bogdan108 reservation #4 batches 1-4 (50 tasks)',
                                     definitions='report_fipi_extension.metrics (checkpoint-100-v1) applied unchanged to each population',
                                     populations=summary, self_checks=checks,
                                     interpretations=['No answer key or external expertise: solved is not accuracy.',
                                                      'New candidates remain task-local; names do not establish identity.',
                                                      'Mixed cumulative frequencies combine historical editorial and independent audited provenance.',
                                                      'Transitions are task-presence across adjacent steps in a single method, excluding self-transitions; not prerequisites.',
                                                      'Reservation #4 is half complete (batches 1-4 of 8); its layer shares model and effort with reservation #2 batches 6-12 but not task composition.']))
    cards(temp, data); figures(temp, summary, tables)
    lines = report_lines(data, summary, tables, checks)
    (temp / 'report.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    esc = rep.esc
    body = '<h1>ФИПИ: промежуточная контрольная точка 250</h1><p><a href="report.md">report.md</a></p><pre>' + esc('\n'.join(lines)) + '</pre>'
    body += ''.join(f'<h2>{i}</h2><img src="figures/{n}.png">' for i, n in enumerate(('01-composition', '02-structure', '03-audit-statuses', '04-catalog-evidence'), 1))
    body += ('<h2>Карточки</h2><p>Исходные 50: <a href="../../runs/2026-10-31-fipi-50x1/derived/index.html">EDA-50</a>. '
             'Первые 50 новых: <a href="../../runs/2026-11-02-fipi-extension-150/derived/checkpoint-100-v1/index.html">EDA-100</a>. '
             'Бронь #2, 100 задач: <a href="../2026-11-09-fipi-checkpoint-200-v1/index.html">EDA-200</a>.</p>'
             '<h3>Бронь #4 Bogdan108, партии 1–4</h3><ul>')
    body += ''.join(f'<li><a href="cards/{r["task_id"]}.html">{r["order"]}. {r["task_id"]}</a> · партия {r["batch"]} · included={r["included"]}</li>' for r in data['next'])
    body += '</ul>'
    (temp / 'index.html').write_text(rep.page('ФИПИ: EDA-250', body), encoding='utf-8')
    notebook(temp, data['input_digest'])
    assert all(sha(ROOT / p) == h for p, h in data['input_hashes'].items()), 'Inputs changed during build; inspect .building directory'
    import importlib.metadata as md
    dump(temp / 'provenance.json', dict(input_digest=data['input_digest'], input_hashes=data['input_hashes'],
                                        notebook='executed (nbclient) during build',
                                        packages={p: md.version(p) for p in ('lxml', 'Pillow', 'numpy', 'matplotlib', 'nbformat', 'nbclient', 'ipykernel')},
                                        python=sys.version.split()[0]))
    dump(temp / 'output-hashes.json', {p.relative_to(temp).as_posix(): sha(p) for p in sorted(temp.rglob('*')) if p.is_file()})
    temp.rename(target)
    print(target.relative_to(ROOT))
    return target


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('command', choices=['build', 'check'])
    p.add_argument('--out', default=DEFAULT_OUT)
    a = p.parse_args()
    if a.command == 'check':
        data = collect(); print(json.dumps(self_checks(data), ensure_ascii=False))
        summary, _ = metrics(data)
        print(json.dumps({k: (v['selected_n'], v['included_n'], v['confirmed_catalog_nodes']) for k, v in summary.items()}, ensure_ascii=False))
    else:
        build(a.out)


if __name__ == '__main__':
    main()
