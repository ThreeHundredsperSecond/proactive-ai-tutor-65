#!/usr/bin/env python3
"""Cumulative FIPI checkpoint EDA-300 from saved results only (no model calls, no network).

Corpus (per task records, not summed frequencies):
  - EDA-200 corpus, collected by the unchanged scripts/fipi_checkpoint200.py (historical 50, first 50 new,
    100 tasks of reservation #2);
  - all 100 tasks (batches 1-8) of reservation #4 (Bogdan108, next 100):
    data/annotation/runs/2026-11-09-fipi-team-bogdan108-next-100.
Metrics reuse report_fipi_extension.metrics() unchanged, called on different subsets, so all definitions
match checkpoint-100-v1, EDA-200 and EDA-250. Self-checks: EDA-100, EDA-150 and EDA-200 checks of EDA-250, plus
the recomputed EDA-250 (batches 1-4) summary and frequencies equal the saved EDA-250 outputs.

Usage:
  .venv/bin/python scripts/fipi_checkpoint300.py check
  .venv/bin/python scripts/fipi_checkpoint300.py build [--out data/annotation/analyses/2026-11-10-fipi-checkpoint-300-v1]
The output directory is immutable: an existing directory is never overwritten (use a new -vN name).
"""
import argparse
import csv
import hashlib
import json
import os
import re
import sys
import textwrap
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fipi_checkpoint200 as cp  # noqa: E402  (unchanged; EDA-200 corpus and helpers)
import fipi_checkpoint250 as c250  # noqa: E402  (unchanged; EDA-250 metrics, cards and self-checks)

rep, ext = cp.rep, cp.ext
plt, Image = cp.plt, cp.Image
ROOT = cp.ROOT
H200 = c250.H200
H250 = ROOT / 'data/annotation/analyses/2026-11-09-fipi-checkpoint-250-v1'
NEXT = c250.NEXT
NEXT_BATCHES = [1, 2, 3, 4, 5, 6, 7, 8]
DEFAULT_OUT = 'data/annotation/analyses/2026-11-10-fipi-checkpoint-300-v1'
STATUSES, STATUS_LABELS, REASON_LABELS = cp.STATUSES, cp.STATUS_LABELS, cp.REASON_LABELS
read, sha, dump, csvout, pct = cp.read, cp.sha, cp.dump, cp.csvout, cp.pct
FIGURES = ('01-composition', '02-structure', '03-audit-statuses', '04-catalog-evidence', '05-next-batches')

POPULATIONS = {
    'baseline50': 'Исходные 50: редакторские связи',
    'ext_new50': 'Первые 50 новых (запуск 2026-11-02): агентный аудит',
    'team100': 'Бронь #2, 100 задач (партии 5–12): агентный аудит',
    'team_b5_default': 'Бронь #2, партия 5: Opus, уровень рассуждений по умолчанию',
    'team_b6_12_low': 'Бронь #2, партии 6–12: Opus, effort low',
    'next100': 'Бронь #4, 100 задач (партии 1–8): Opus, effort low',
    'next_b1_4': 'Бронь #4, партии 1–4 (50 задач, вошли в EDA-250)',
    'next_b5_8': 'Бронь #4, партии 5–8 (50 задач)',
    'audited_new250': 'Все новые 250: агентный аудит',
    'mixed_cumulative300': 'Смешанный накопленный корпус 300',
}

# Tasks whose saved author answers depend on reading coordinates or shapes from a figure (author warnings,
# auditor confirmations); listed in the batch paragraphs of the run README.
FIGURE_READING = {
    'next_b1_4': ['97C4EA', 'FEE4C3', '6F2D5E', '6FA927', 'c1936D', '0B2322'],
    'next_b5_8': ['D00D6F', '5F9519', '8BF7C8', 'A2E26B', 'B537B2', 'e3e194', 'ECB413', '62A335'],
}
# Non-blocking auditor issues of batches 5-8 about gaps of mathematical justification (kinds boundary/coverage,
# none of kind math); paraphrased from raw/auditor.
JUSTIFICATION_GAPS_5_8 = [
    ('c19c6e', 'в шаге s3 не показана промежуточная запись √2·cos(2x + π/4) = −1 перед делением на √2; результат верен.'),
    ('B9281F', 'при умножении на k + 1 не отмечено условие k + 1 ≠ 0; на ответ не влияет.'),
    ('9595A4', 'для вывода «трапеция, а не параллелограмм» указано только H ≠ A1, без сравнения C1B1 и A1H; вывод и ответ б) 6 аудитор считает верными.'),
    ('4F4F44', 'вывод о параллелограмме из векторного равенства требует неколлинеарности векторов, в шаге это явно не отмечено.'),
    ('B19404', 'не записано, что MH ⊥ BC по теореме о трёх перпендикулярах, и не обосновано, что проекция M — середина OA.'),
    ('8755EE', 'в примере пункта в) прослежен только наибольший кусок; что остальные доходят до 1 за те же ходы, не проговорено.'),
    ('2F9BDB', 'для наклонной призмы переход от отношения периметров оснований к отношению периметров перпендикулярных сечений явно не показан.'),
]


# ---------------------------------------------------------------- collection

def collect_next(paths, batch_numbers):
    """Validate and load the given batches of reservation #4; read-only. Same checks as fipi_checkpoint250.collect_next."""
    def load(p):
        p = Path(p); paths.add(p.resolve()); return read(p)
    manifest = load(NEXT / 'manifest.json')
    assert load(NEXT / 'active-attempts.json') == {}, 'active attempts present: selection must be adapted explicitly'
    for name in ('PROTOCOL.md', 'author-prompt.txt', 'auditor-prompt.txt', 'author-wrapper.txt', 'audit-format-wrapper-v1.1.txt',
                 'catalog-for-auditor.json', 'reservation.json', 'environment.json'):
        paths.add((NEXT / name).resolve())
    batches = {b: manifest['batches'][str(b)] for b in batch_numbers}
    entries = {t['task_id']: t for t in manifest['tasks']}
    health, accepted, executions = {}, {}, {}
    for b in batch_numbers:
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
    for b in batch_numbers:
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
            executions[tid] = {role: dict(message=ex[role].get('completion_message', ''), mechanism=ex[role].get('mechanism'))
                               for role in ex}
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
    return rows, health, manifest, executions


def collect():
    data = cp.collect()
    paths = {(ROOT / p).resolve() for p in data['input_hashes']}
    for name in ('fipi_checkpoint250.py', 'fipi_checkpoint300.py'):
        paths.add((ROOT / 'scripts' / name).resolve())
    for h in (H200, H250):
        for name in ('summary.json', 'batches.json', 'tables/frequencies.csv'):
            paths.add((h / name).resolve())
    nxt, health, manifest, executions = collect_next(paths, NEXT_BATCHES)
    provenance = {Path(p).resolve().relative_to(ROOT).as_posix(): sha(p) for p in sorted(paths)}
    data.update(next=nxt, next_health=health, next_manifest=manifest, next_executions=executions, input_hashes=provenance,
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
        'next100': (nxt, 'new_accumulated'),
        'next_b1_4': ([r for r in nxt if r['batch'] <= 4], 'new_accumulated'),
        'next_b5_8': ([r for r in nxt if r['batch'] >= 5], 'new_accumulated'),
        'audited_new250': (data['ext'] + team + nxt, 'new_accumulated'),
        'mixed_cumulative300': (data['ext'] + team + nxt, 'mixed_cumulative'),
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
    """EDA-250 self-checks (EDA-100, EDA-150, EDA-200) plus: batches 1-4 load identically to the EDA-250 collector,
    and the recomputed EDA-250 summary and frequencies equal the saved EDA-250 outputs."""
    checks = c250.self_checks(data)
    first = [r for r in data['next'] if r['batch'] <= 4]
    rows250, _, _ = c250.collect_next(set())
    checks['next_b1_4_rows_equal_eda250_collector'] = rows250 == first
    s250, t250 = c250.metrics(dict(data, next=first))
    checks['eda250_summary_reproduced'] = json.loads(json.dumps(s250)) == read(H250 / 'summary.json')['populations']
    saved = list(csv.DictReader(open(H250 / 'tables/frequencies.csv', encoding='utf-8-sig')))
    fields = ['population', 'catalog_kc_id', 'task_n', 'denominator']
    checks['eda250_frequencies_reproduced'] = saved == [{k: str(r[k]) for k in fields} for r in t250['frequencies']]
    return checks


def interruptions(data):
    """Interruptions and reruns as recorded in the completion messages of executions/."""
    lim, rerun = [], []
    for r in data['next']:
        for role, e in data['next_executions'][r['task_id']].items():
            if re.search(r'прерван лимитом', e['message']):
                lim.append((r['batch'], role, r['task_id']))
            if re.search(r'предыдущих ответа свежих агентов', e['message']):
                rerun.append((r['batch'], role, r['task_id']))
    return lim, rerun


# ---------------------------------------------------------------- outputs

FIG_GROUPS = ('baseline50', 'ext_new50', 'team100', 'next100')
FIG_LABELS = {'baseline50': 'Исходные 50', 'ext_new50': 'Первые 50 новых', 'team100': 'Бронь #2, 100', 'next100': 'Бронь #4, 100'}


def figures(out, summary, tables):
    fig_dir = out / 'figures'; fig_dir.mkdir()
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 10})

    def save(name):
        plt.tight_layout(); plt.savefig(fig_dir / f'{name}.png', dpi=140); plt.close()

    def off(i, n, w):
        return (i - (n - 1) / 2) * w
    w = .2
    fig, axes = plt.subplots(1, 2, figsize=(15, 5))
    for ax, dim in zip(axes, ('first_kes', 'response_type')):
        rows = [r for r in tables['composition'] if r['dimension'] == dim]
        vals = sorted({r['value'] for r in rows}); x = list(range(len(vals)))
        for i, g in enumerate(FIG_GROUPS):
            c = {r['value']: r for r in rows if r['population'] == g}
            ax.bar([v + off(i, len(FIG_GROUPS), w) for v in x], [100 * c[v]['task_n'] / c[v]['denominator'] if v in c else 0 for v in vals], w,
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
            ax.bar([v + off(i, len(FIG_GROUPS), w) for v in sorted(c)], [100 * c[v] / n for v in sorted(c)], w, label=f'{FIG_LABELS[g]} · в анализе {n}')
        ax.set(title={'steps': 'Число содержательных шагов', 'local_kcs': 'Число локальных кандидатов KC', 'methods': 'Число методов'}[key],
               ylabel='% задач, включённых в анализ'); ax.legend(fontsize=7)
    save('02-structure')
    groups = ('ext_new50', 'team_b5_default', 'team_b6_12_low', 'next_b1_4', 'next_b5_8')
    names = {'ext_new50': 'Первые 50 новых', 'team_b5_default': 'Бронь #2: партия 5 (по умолчанию)',
             'team_b6_12_low': 'Бронь #2: партии 6–12 (effort low)', 'next_b1_4': 'Бронь #4: партии 1–4 (effort low)',
             'next_b5_8': 'Бронь #4: партии 5–8 (effort low)'}
    w = .16
    fig, ax = plt.subplots(figsize=(12, 4.5))
    for i, g in enumerate(groups):
        c = summary[g]['audit_statuses']; d = c['match']['denominator']
        ax.bar([x + off(i, len(groups), w) for x in range(len(STATUSES))], [100 * c[s]['numerator'] / d for s in STATUSES], w, label=f'{names[g]} · n={d}')
    ax.set(xticks=range(len(STATUSES)), xticklabels=[STATUS_LABELS[s] for s in STATUSES], ylabel='% локальных кандидатов',
           title='Решения аудитора по слоям происхождения'); ax.legend(fontsize=8)
    save('03-audit-statuses')
    freq = {(r['population'], r['catalog_kc_id']): r['task_n'] for r in tables['frequencies']}
    top = sorted({k for g, k in freq if g == 'mixed_cumulative300'}, key=lambda k: (-freq[('mixed_cumulative300', k)], k))[:25]
    cat_names = {n['id']: n['name'] for n in read(cp.EXT / 'catalog-for-auditor.json')['nodes']}
    fig, ax = plt.subplots(figsize=(14, 12)); y = list(range(len(top))); left = [0] * len(top)
    for g, label in (('baseline50', 'Исторические редакторские'), ('ext_new50', 'Первые 50 новых'), ('team100', 'Бронь #2, 100'),
                     ('next_b1_4', 'Бронь #4, партии 1–4'), ('next_b5_8', 'Бронь #4, партии 5–8')):
        vals = [freq.get((g, k), 0) for k in top]
        ax.barh(y, vals, left=left, label=label); left = [a + b for a, b in zip(left, vals)]
    ax.set(yticks=y, yticklabels=[textwrap.fill(cat_names.get(k, k), 52) for k in top], xlabel='Подтверждения: уникальных задач',
           title='Фиксированный каталог: 25 самых частых узлов, слои разделены'); ax.invert_yaxis(); ax.tick_params(axis='y', labelsize=8); ax.legend()
    save('04-catalog-evidence')
    cand = [c for c in tables['candidates'] if c['source'] == 'next']
    fig, ax = plt.subplots(figsize=(12, 4.5)); bottom = [0.0] * len(NEXT_BATCHES)
    by = {b: Counter(c['status'] for c in cand if c['batch'] == b) for b in NEXT_BATCHES}
    for s in STATUSES:
        vals = [100 * by[b][s] / sum(by[b].values()) for b in NEXT_BATCHES]
        ax.bar(range(len(NEXT_BATCHES)), vals, .6, bottom=bottom, label=STATUS_LABELS[s]); bottom = [a + v for a, v in zip(bottom, vals)]
    ax.set(xticks=range(len(NEXT_BATCHES)), xticklabels=[f'Партия {b}\nn={sum(by[b].values())}' for b in NEXT_BATCHES],
           ylabel='% локальных кандидатов партии', title='Бронь #4: решения аудитора по партиям (малые выборки, описательно)')
    ax.axvline(3.5, color='grey', ls='--', lw=1); ax.legend(fontsize=8, loc='lower right')
    save('05-next-batches')


def report_lines(data, summary, tables, checks):
    s = summary
    lines = ['# ФИПИ: накопленная контрольная точка 300 задач', '',
             'Расчёт по сохранённым разборам и аудитам, без новых модельных запросов. Корпус — [EDA-200](../2026-11-09-fipi-checkpoint-200-v1/report.md) '
             'и все 100 задач брони #4 Bogdan108 (партии 1–8); первые 50 из них вошли в промежуточный '
             '[EDA-250](../2026-11-09-fipi-checkpoint-250-v1/report.md). Определения метрик — как в '
             '[EDA-100](../../runs/2026-11-02-fipi-extension-150/derived/checkpoint-100-v1/report.md), EDA-200 и EDA-250: узел каталога считается '
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
              'Смешанный корпус объединяет разное происхождение, поэтому его частоты описательные. Слои брони #4 «партии 1–4» и «партии 5–8» '
              'являются частями слоя «Бронь #4, 100».', '']
    freq = {}
    for r in tables['frequencies']:
        freq.setdefault(r['population'], {})[r['catalog_kc_id']] = r['task_n']
    nodes200 = set(freq['baseline50']) | set(freq['ext_new50']) | set(freq['team100'])
    nodes250 = nodes200 | set(freq['next_b1_4'])
    added200 = sorted(set(freq['next100']) - nodes200)
    added250 = sorted(set(freq['next_b5_8']) - nodes250)
    saved = {'EDA-200': read(H200 / 'summary.json')['populations']['mixed_cumulative200'],
             'EDA-250': read(H250 / 'summary.json')['populations']['mixed_cumulative250']}
    m300 = s['mixed_cumulative300']
    fmt = lambda ks: ', '.join(f'`{k}`' for k in ks) or 'нет'  # noqa: E731
    lines += ['## 2. Что добавилось', '',
              f'- Бронь #4 добавила {s["next100"]["included_n"]} включённых задач. Узлов каталога, подтверждённых в них: {len(freq["next100"])}; '
              f'из них не подтверждённых в EDA-200: {len(added200)} ({fmt(added200)}).',
              f'- Партии 5–8 добавили к EDA-250 {s["next_b5_8"]["included_n"]} включённых задач. Подтверждённых в них узлов: {len(freq["next_b5_8"])}; '
              f'из них не подтверждённых в EDA-250: {len(added250)} ({fmt(added250)}).',
              '- Подтверждённых узлов в смешанном корпусе: ' + ' → '.join(f'{v["confirmed_catalog_nodes"]} ({k})' for k, v in saved.items())
              + f' → {m300["confirmed_catalog_nodes"]} (EDA-300); единичных: '
              + ' → '.join(f'{v["singleton_nodes"]["numerator"]}/{v["singleton_nodes"]["denominator"]}' for v in saved.values())
              + f' → {m300["singleton_nodes"]["numerator"]}/{m300["singleton_nodes"]["denominator"]}.',
              f'- Кандидаты брони #4, которым аудитор не нашёл узла (`new_candidate`): {s["next100"]["audit_statuses"]["new_candidate"]["numerator"]} '
              f'(партии 1–4 — {s["next_b1_4"]["audit_statuses"]["new_candidate"]["numerator"]}, партии 5–8 — '
              f'{s["next_b5_8"]["audit_statuses"]["new_candidate"]["numerator"]}). Это локальные предложения отдельных задач, а не число уникальных '
              'новых навыков: межзадачной консолидации не было.', '']
    lines += ['## 3. Сравнение слоёв по тем же определениям', '',
              '| Показатель | Бронь #2, партии 6–12 | Бронь #4, партии 1–4 | Бронь #4, партии 5–8 | Бронь #4, 100 | Все новые 250 |',
              '|---|---:|---:|---:|---:|---:|']
    cols = ('team_b6_12_low', 'next_b1_4', 'next_b5_8', 'next100', 'audited_new250')
    for st in STATUSES:
        lines.append(f'| {STATUS_LABELS[st]} | ' + ' | '.join(pct(s[c]['audit_statuses'][st]['numerator'], s[c]['audit_statuses'][st]['denominator']) for c in cols) + ' |')
    for key, label in (('steps', 'Медиана шагов'), ('kc_candidates', 'Медиана локальных KC')):
        lines.append(f'| {label} | ' + ' | '.join(f"{s[c]['structure']['all'][key]['median']:g}".replace('.', ',') for c in cols) + ' |')
    lines.append('| Задачи с неполным сопоставлением | ' + ' | '.join(pct(s[c]['incomplete_mapping_tasks'], s[c]['included_n']) for c in cols) + ' |')
    a, b_ = s['next_b1_4']['audit_statuses'], s['next_b5_8']['audit_statuses']
    lines += ['', 'Партии 6–12 брони #2 и обе половины брони #4 — `claude-opus-5-5` с `effort: low`, одна методика, одни запросы и один '
              'замороженный каталог. Партии 1–5 брони #4 '
              'запускались субагентами Claude Code, партии 6–8 — субагентами Cursor (`claude-opus-5-5-low`) с теми же сообщениями `exec-start`; '
              'поле `mechanism` в журналах `executions/` у всех партий содержит значение по умолчанию сценария, фактический способ запуска '
              'указан в [README брони](../../runs/2026-11-09-fipi-team-bogdan108-next-100/README.md). '
              f'Доля `match` в партиях 5–8 — {pct(b_["match"]["numerator"], b_["match"]["denominator"])}, в партиях 1–4 — '
              f'{pct(a["match"]["numerator"], a["match"]["denominator"])}, в партиях 6–12 брони #2 — '
              f'{pct(s["team_b6_12_low"]["audit_statuses"]["match"]["numerator"], s["team_b6_12_low"]["audit_statuses"]["match"]["denominator"])}. '
              f'Доля спорных решений в обеих половинах брони #4 ({pct(a["uncertain"]["numerator"], a["uncertain"]["denominator"])} и '
              f'{pct(b_["uncertain"]["numerator"], b_["uncertain"]["denominator"])}) выше, чем в партиях 6–12 брони #2. Различия нельзя приписать исполнителю: '
              'модель и уровень рассуждений совпадают, а партии различаются составом задач (случайные порции очереди из 15 задач), '
              'и выборки малы (50 и 85 задач). Внутри брони #4 доли заметно колеблются от партии к партии '
              '([по партиям](figures/05-next-batches.png)). [Состав выборки](figures/01-composition.png), '
              '[структура разборов](figures/02-structure.png), [статусы аудита](figures/03-audit-statuses.png).', '']
    lines += ['## 4. Контрольные задачи, исключения и спорные случаи', '']
    ctrl = Counter(); after = []; reviewed = []
    for b, h in data['next_health'].items():
        for c in h['controls']:
            ctrl[c['status']] += 1
            if c['status'] != 'match': after.append(f'{c["task_id"]} (партия {b})')
        review = NEXT / f'checks/batch-{b:02}-math-review.json'
        if review.exists():
            reviewed += [f'{x["task_id"]} — «{x["author_answer"].split("б) ")[-1]}» при ожидании {x["expected_answer"]}'
                         for x in read(review)['reviews'] if x['verdict'] == 'equivalent']
    lines.append(f'- Контрольные задачи брони #4, сверенные с ожиданиями, записанными до авторских ответов: {sum(ctrl.values())}; '
                 f'`match` — {ctrl["match"]}, `match_after_review` — {ctrl["match_after_review"]} ({", ".join(after) or "нет"}). '
                 'Во всех трёх случаях ответ состоит из доказательного пункта а) и числового пункта б); ожидание записано только для б), '
                 f'и строковое сравнение невозможно. Ответ пункта б) совпал с ожиданием: {"; ".join(reviewed)}; '
                 'доказательства пунктов а) не сравнивались. Сравнение сделано после просмотра ответа и слепой проверкой не является; '
                 'первые версии сверки сохранены как `checks/batch-NN-math.v0-normalizer.json`.')
    acc = [r['task_id'] for r in data['next'] if r['accepted_after_review']]
    lines.append(f'- Приняты после просмотра при статусе автора не `solved`: {", ".join(acc) or "нет"}. '
                 f'Статус `solved` у всех {sum(r["author"]["solution_status"] == "solved" for r in data["next"])} авторов брони #4.')
    excl = s['mixed_cumulative300']['excluded']
    lines += ['- Исключены из основных частот смешанного корпуса:'] + [f'  - {e["task_id"]}: {", ".join(REASON_LABELS.get(x, x) for x in e["reasons"])}' for e in excl]
    lines.append('  В брони #4 исключений нет: блокирующих замечаний аудита и технических ошибок в принятых файлах нет.')
    halves = {'партии 1–4': [r for r in data['next'] if r['batch'] <= 4], 'партии 5–8': [r for r in data['next'] if r['batch'] >= 5]}
    parts = []
    for name, rows in halves.items():
        warn = sum(bool(r['author'].get('warnings')) for r in rows)
        iss = sum(len(r['audit']['issues']) for r in rows)
        blk = sum(i['blocking'] for r in rows for i in r['audit']['issues'])
        kinds = Counter(i['kind'] for r in rows for i in r['audit']['issues'])
        parts.append(f'{name}: задач с предупреждениями авторов — {warn}, замечаний аудиторов — {iss} (блокирующих {blk}; '
                     + ', '.join(f'`{k}` — {v}' for k, v in kinds.most_common()) + ')')
    lines.append('- В брони #4 ' + '; '.join(parts) + '. '
                 f'Спорных решений аудитора (`uncertain`): {s["next100"]["audit_statuses"]["uncertain"]["numerator"]}. '
                 'Чаще всего (`boundary`) замечания касаются границ узлов каталога; в частности, почти совпадающие узлы (`literal_cc7d68a38f29` и `literal_55d5a6d9eb3c` '
                 'для формул приведения и двойного угла; три узла подсчёта различных корней) не позволяют выбрать одно соответствие. '
                 'Подробности — в [карточках](index.html) и [таблице кандидатов](tables/candidates.csv).')
    math_issues = [r['task_id'] for r in data['next'] if any(i.get('kind') == 'math' for i in r['audit']['issues'])]
    lines += [f'- Неблокирующие замечания вида `math`: {", ".join(math_issues) or "нет"} (все в партиях 1–4). '
              'Они не отменяют сопоставлений KC, поэтому задачи входят в частоты, но ответы этих задач независимым ожиданием не проверялись:',
              '  - FAAE63 (прямоугольник и перпендикуляр к диагонали): аудитор отметил неточную формулировку обоснования угла в шаге s2 '
              'и оценил итог как верный.',
              '  - 0B2322 (число точек, где производная положительна, по графику функции): автор отнёс точки вблизи экстремумов к участкам '
              'монотонности на глаз и ответил 3; аудитор допускает, что x3 — локальный максимум, и тогда ответ 2.',
              '  - 724631 (задача с пунктами а–в о десятичной записи чисел): текст шага s2 оборван; аудитор отметил, что граничный случай a = 1, '
              'b = c = 0 в выводе s2 требует оговорки, и оценил, что на итоговый ответ это не влияет.',
              '- В партиях 5–8 замечаний вида `math` нет, но несколько замечаний видов `boundary` и `coverage` касаются пробелов математического '
              'обоснования. Аудиторы оценили, что ответ от них не меняется:']
    lines += [f'  - {tid} (партия {next(r["batch"] for r in data["next"] if r["task_id"] == tid)}): {text}' for tid, text in JUSTIFICATION_GAPS_5_8]
    lines += [f'- Задачи с чтением координат или формы по рисунку: партии 1–4 — {", ".join(FIGURE_READING["next_b1_4"])}; '
              f'партии 5–8 — {", ".join(FIGURE_READING["next_b5_8"])}. Ответы зависят от качества изображения; авторы отмечали прочтение '
              'в `warnings`, аудиторы сверяли его с тем же рисунком. В FEE4C3 автор дополнительно считал пиксели узлов сетки во временной копии рисунка; '
              'в A2E26B крутизна графика в двух точках сравнена на глаз; в e3e194 призма на рисунке может быть наклонной, использованная формула '
              'верна в обоих случаях.', '']
    lim, rerun = interruptions(data)
    lim_b = Counter((b, role) for b, role, _ in lim)
    lines += ['## 5. Прерывания и повторы', '',
              '- ' + ('; '.join(f'партия {b}: {n} {"аудиторов" if role == "auditor" else "авторов"}' for (b, role), n in sorted(lim_b.items())) or 'нет')
              + ' — прерваны лимитом API до записи ответа и возобновлены тем же агентом нейтральным сообщением после сброса лимита '
              '(записи `completion_message` в `executions/`). Ответы записаны однократно и прошли валидатор; влияние прерывания на содержание '
              'аудита не оценивалось.',
              '- ' + ('; '.join(f'{tid} (партия {b}, {"автор" if role == "author" else "аудитор"})' for b, role, tid in rerun) or 'нет')
              + ': принят третий запуск автора. Первые два свежих агента с тем же сообщением и моделью дали ответы с пустым `kc_ids` '
              'у шага вывода пункта а) и не прошли техническую проверку; ответы удалены до аудита и коммита, их SHA-256 записаны в '
              '[журнале автора](../../runs/2026-11-09-fipi-team-bogdan108-next-100/executions/author-73BE23.json). В инструкции автора явного требования '
              'непустого `kc_ids` у каждого шага нет, поэтому для задач с чисто логическими шагами возможны повторы.',
              '- Других повторов и прерываний в журналах нет. Перед стартом агентов партии 8 запуск был отклонён средой (модель временно недоступна); '
              'агенты не запускались и файлов не создавали.', '']
    lines += ['## 6. Как читать графики', '',
              '- [Состав](figures/01-composition.png): доли отобранных задач по первой метке КЭС и типу ответа в четырёх крупных слоях. '
              'Различия состава между бронями — первое объяснение различий долей статусов аудита.',
              '- [Структура](figures/02-structure.png): распределения числа шагов, локальных KC и методов на задачу; это свойство разборов '
              'авторов, а не сложности задач.',
              '- [Статусы аудита](figures/03-audit-statuses.png): доли решений аудитора по слоям; столбцы одного цвета суммируются в 100% по слою. '
              'Знаменатель — число локальных кандидатов, не задач.',
              '- [Узлы каталога](figures/04-catalog-evidence.png): 25 самых частых подтверждённых узлов смешанного корпуса; длина полосы — '
              'число задач, цвет — слой происхождения. Исторические редакторские связи и агентный аудит получены по-разному.',
              '- [Партии брони #4](figures/05-next-batches.png): доли статусов внутри каждой партии; пунктир отделяет партии, вошедшие в EDA-250. '
              'Партия 4 и партия 8 содержат по 5 задач, поэтому их доли особенно неустойчивы.', '']
    lines += ['## 7. Какие выводы пока невозможны', '',
              '- Нельзя оценить точность решений: внешнего эталона нет, контрольные ответы проверены выборочно (3 задачи на партию, 24 в брони #4).',
              '- Нельзя считать `new_candidate` новыми уникальными навыками и сравнивать их число между слоями как прирост каталога.',
              '- Нельзя приписать различия долей статусов аудита между бронями #2 и #4 или между половинами брони #4 исполнителю: '
              'модель и уровень рассуждений совпадают, а состав задач различается; смена среды запуска в партиях 6–8 не отделима от состава.',
              '- Нельзя считать узлы, не подтверждённые в корпусе, отсутствующими в экзамене: корпус — 300 из 1148 условий банка, отбор по очереди.',
              '- Совместная встречаемость и переходы между узлами — описательные; они не доказывают порядок изучения или зависимость навыков.', '',
              '## 8. Самопроверки', '',
              f'- Пересчёт EDA-100 из тех же записей совпал с сохранённой сводкой: {checks["eda100_summary_reproduced"]}; частоты: {checks["eda100_frequencies_reproduced"]}.',
              f'- Пересчёт частот узлов на 150 задачах совпал с кратким EDA-150: {checks["eda150_node_frequencies_reproduced"]} ({checks["eda150_included_tasks"]} включённых задач).',
              f'- Пересчёт EDA-200 совпал с сохранённой сводкой: {checks["eda200_summary_reproduced"]}; частоты: {checks["eda200_frequencies_reproduced"]}.',
              f'- Записи партий 1–4 совпали с загруженными сборщиком EDA-250: {checks["next_b1_4_rows_equal_eda250_collector"]}; '
              f'пересчёт EDA-250 совпал с сохранённой сводкой: {checks["eda250_summary_reproduced"]}; частоты: {checks["eda250_frequencies_reproduced"]}.', '',
              '## Материалы', '',
              '- [Карточки всех 100 задач брони #4 и графики](index.html); карточки брони #2 — в [EDA-200](../2026-11-09-fipi-checkpoint-200-v1/index.html); '
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
root = next(p for p in (Path.cwd(), *Path.cwd().parents) if (p / 'scripts/fipi_checkpoint300.py').is_file())
sys.path.insert(0, str(root / 'scripts'))
import fipi_checkpoint300 as cp
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
    plots = '''for name in cp.FIGURES:
    display(Image(filename=str(report_path / 'figures' / (name + '.png'))))
'''
    nb = nbformat.v4.new_notebook(cells=[
        nbformat.v4.new_markdown_cell('Офлайн-пересчёт накопленной контрольной точки 300 задач из сохранённых разборов и аудитов. '
                                      'Новых агентов и сети нет; изменение исходных хешей останавливает пересчёт.'),
        nbformat.v4.new_code_cell(code), nbformat.v4.new_code_cell(table),
        nbformat.v4.new_code_cell("{k: summary[k]['audit_statuses'] for k in ('team_b6_12_low', 'next_b1_4', 'next_b5_8', 'next100')}"),
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
    ids = {r['task_id']: r for r in data['next']}
    assert all(t in ids and ids[t]['input']['assets'] for v in FIGURE_READING.values() for t in v), 'figure-reading list'
    assert all(tid in ids and ids[tid]['batch'] >= 5 and any(not i['blocking'] for i in ids[tid]['audit']['issues'])
               for tid, _ in JUSTIFICATION_GAPS_5_8), 'justification-gap list'
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
        eda250=dict(path=H250.relative_to(ROOT).as_posix()),
        reservation4=dict(run=NEXT.relative_to(ROOT).as_posix(), issue=m['issue_url'], owner=m['owner'],
                          method_version=m['method_version'], queue_orders=m['queue_orders'], selection=m.get('selection'),
                          included_batches=NEXT_BATCHES,
                          batches={str(b): dict(tasks=[r['task_id'] for r in data['next'] if r['batch'] == b],
                                                model_requested=sorted({r['model_requested'] for r in data['next'] if r['batch'] == b}),
                                                launcher='Claude Code subagents' if b <= 5 else 'Cursor subagents (claude-opus-5-5-low)',
                                                **data['next_health'][b]) for b in NEXT_BATCHES}))
    dump(temp / 'batches.json', batches)
    lim, rerun = interruptions(data)
    dump(temp / 'summary.json', dict(scope='EDA-300: EDA-200 corpus + Bogdan108 reservation #4 batches 1-8 (100 tasks)',
                                     definitions='report_fipi_extension.metrics (checkpoint-100-v1) applied unchanged to each population',
                                     populations=summary, self_checks=checks,
                                     interruptions=dict(api_limit_resumed=[dict(batch=b, role=r, task_id=t) for b, r, t in lim],
                                                        author_reruns=[dict(batch=b, role=r, task_id=t, accepted_run=3) for b, r, t in rerun]),
                                     interpretations=['No answer key or external expertise: solved is not accuracy.',
                                                      'New candidates remain task-local; names do not establish identity.',
                                                      'Mixed cumulative frequencies combine historical editorial and independent audited provenance.',
                                                      'Transitions are task-presence across adjacent steps in a single method, excluding self-transitions; not prerequisites.',
                                                      'Reservation #4 shares model and effort with reservation #2 batches 6-12 but not task composition; '
                                                      'batches 6-8 were launched from a different environment with the same messages.']))
    c250.cards(temp, data); figures(temp, summary, tables)
    lines = report_lines(data, summary, tables, checks)
    (temp / 'report.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    esc = rep.esc
    body = '<h1>ФИПИ: контрольная точка 300</h1><p><a href="report.md">report.md</a></p><pre>' + esc('\n'.join(lines)) + '</pre>'
    body += ''.join(f'<h2>{i}</h2><img src="figures/{n}.png">' for i, n in enumerate(FIGURES, 1))
    body += ('<h2>Карточки</h2><p>Исходные 50: <a href="../../runs/2026-10-31-fipi-50x1/derived/index.html">EDA-50</a>. '
             'Первые 50 новых: <a href="../../runs/2026-11-02-fipi-extension-150/derived/checkpoint-100-v1/index.html">EDA-100</a>. '
             'Бронь #2, 100 задач: <a href="../2026-11-09-fipi-checkpoint-200-v1/index.html">EDA-200</a>.</p>'
             '<h3>Бронь #4 Bogdan108, партии 1–8</h3><ul>')
    body += ''.join(f'<li><a href="cards/{r["task_id"]}.html">{r["order"]}. {r["task_id"]}</a> · партия {r["batch"]} · included={r["included"]}</li>' for r in data['next'])
    body += '</ul>'
    (temp / 'index.html').write_text(rep.page('ФИПИ: EDA-300', body), encoding='utf-8')
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
        print(interruptions(data))
    else:
        build(a.out)


if __name__ == '__main__':
    main()
