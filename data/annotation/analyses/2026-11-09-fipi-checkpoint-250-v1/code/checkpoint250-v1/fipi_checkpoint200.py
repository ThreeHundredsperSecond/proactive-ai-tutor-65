#!/usr/bin/env python3
"""Cumulative FIPI checkpoint EDA-200 from saved results only (no model calls, no network).

Corpus (per task records, not summed frequencies):
  - historical 50 + first 50 new: data/annotation/runs/2026-11-02-fipi-extension-150, loaded with the
    unchanged collector of checkpoint-100-v1 (scripts/report_fipi_extension.py via archive_support);
  - 100 reserved tasks of Bogdan108 (queue 51-150, batches 5-12):
    data/annotation/runs/2026-11-07-fipi-team-bogdan108-051-150.
Metrics reuse report_fipi_extension.metrics() unchanged, called on different subsets, so all definitions
match checkpoint-100-v1. Self-checks: recomputed EDA-100 equals the saved summary; recomputed 150-task
node frequencies equal the saved brief EDA-150 table.

Usage:
  .venv/bin/python scripts/fipi_checkpoint200.py build [--out data/annotation/analyses/2026-11-09-fipi-checkpoint-200-v1]
The output directory is immutable: an existing directory is never overwritten (use a new -vN name).
"""
import argparse
import csv
import hashlib
import json
import os
import statistics
import sys
import textwrap
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from lxml import html as dom
from PIL import Image

import report_fipi_extension as rep
import fipi_extension as ext
from archive_support import collect_saved
from fipi_eda50 import validate_one
from collect_fipi_bank import browser_math

ROOT = rep.ROOT
EXT = rep.RUN
H100 = EXT / 'derived/checkpoint-100-v1'
H150 = ROOT / 'data/annotation/analyses/2026-11-08-fipi-checkpoint-150-v1'
TEAM = ROOT / 'data/annotation/runs/2026-11-07-fipi-team-bogdan108-051-150'
BASE50 = ROOT / 'data/annotation/runs/2026-10-31-fipi-50x1'
DEFAULT_OUT = 'data/annotation/analyses/2026-11-09-fipi-checkpoint-200-v1'
TEAM_BATCHES = [5, 6, 7, 8, 9, 10, 11, 12]
STATUSES = rep.STATUSES

POPULATIONS = {
    'baseline50': 'Исходные 50: редакторские связи',
    'ext_new50': 'Первые 50 новых (запуск 2026-11-02): агентный аудит',
    'team100': 'Бронь Bogdan108, 100 задач (партии 5–12): агентный аудит',
    'team_b5_default': 'Бронь, партия 5: Opus, уровень рассуждений по умолчанию',
    'team_b6_12_low': 'Бронь, партии 6–12: Opus, effort low',
    'audited_new150': 'Все новые 150: агентный аудит',
    'mixed_cumulative200': 'Смешанный накопленный корпус 200',
}
STATUS_LABELS = {'match': 'Существующий KC', 'new_candidate': 'Новый кандидат', 'needs_split': 'Требует разделения', 'uncertain': 'Спорный'}
REASON_LABELS = {'technical_validation_failure': 'ошибка технической проверки', 'blocking_audit_issue': 'блокирующее замечание аудита',
                 'partial': 'частичное решение', 'unsolved': 'не решено', 'audit_pending': 'аудит не получен', 'author_pending': 'разбор не получен',
                 'historical_partial_or_review_exclusion': 'исторический partial или исключение прежней рецензией'}


def read(p):
    return json.loads(Path(p).read_text(encoding='utf-8'))


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def dump(p, value):
    Path(p).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def csvout(path, rows, fields):
    with open(path, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        w.writeheader()
        w.writerows(rows)


# ---------------------------------------------------------------- collection

def collect_team(paths):
    """Validate and load the 100 reserved tasks; read-only."""
    def load(p):
        p = Path(p); paths.add(p.resolve()); return read(p)
    manifest = load(TEAM / 'manifest.json')
    assert load(TEAM / 'active-attempts.json') == {}, 'active attempts present: selection must be adapted explicitly'
    for name in ('PROTOCOL.md', 'author-prompt.txt', 'auditor-prompt.txt', 'author-wrapper.txt', 'audit-format-wrapper-v1.1.txt',
                 'catalog-for-auditor.json', 'reservation.json', 'environment.json'):
        paths.add((TEAM / name).resolve())
    batches = {b: manifest['batches'][str(b)] for b in TEAM_BATCHES}
    entries = {t['task_id']: t for t in manifest['tasks']}
    health, accepted = {}, {}
    for b in TEAM_BATCHES:
        h = load(TEAM / f'checks/batch-{b:02}.json')
        assert h['batch'] == b and h['task_ids'] == batches[b], f'health check ids batch {b}'
        assert h['status'] == 'pass' and not h['quarantined_ids'] and h['systemic_unresolved'] is False, f'batch {b} not pass'
        for x in h.get('accepted_after_review', []):
            assert sha(ROOT / x['resolution']) == x['sha256']; paths.add((ROOT / x['resolution']).resolve())
            accepted[x['task_id']] = x['resolution']
        math = load(TEAM / f'checks/batch-{b:02}-math.json')
        health[b] = dict(status=h['status'], controls=[dict(task_id=c['task_id'], status=c['status']) for c in math['checks']],
                         accepted_after_review=[x['task_id'] for x in h.get('accepted_after_review', [])])
    rows = []
    for b in TEAM_BATCHES:
        for tid in batches[b]:
            e = entries[tid]
            inp_path = TEAM / 'inputs/tasks' / f'{tid}.json'
            assert sha(inp_path) == e['input_sha256'], f'input hash {tid}'
            inp = load(inp_path)
            for a in inp['assets']:
                p = TEAM / 'inputs' / a['path']; paths.add(p.resolve())
                assert sha(p) == a['sha256'], f'image hash {a["path"]}'
                with Image.open(p) as im: im.verify()
            ap, qp = TEAM / 'raw/author' / f'{tid}.json', TEAM / 'raw/auditor' / f'{tid}.json'
            author, audit = load(ap), load(qp)
            validate_one(author); assert author['task_id'] == tid and audit['task_id'] == tid
            va = load(TEAM / 'validations' / f'author-{tid}.json')['result']
            vq = load(TEAM / 'validations' / f'auditor-{tid}.json')['result']
            assert va['status'] == 'technical_pass' and vq['status'] == 'technical_pass', f'validation {tid}'
            assert vq['audit_sha256'] == sha(qp) and vq['author_sha256'] == sha(ap), f'validated bytes changed {tid}'
            ex = {role: load(TEAM / 'executions' / f'{role}-{tid}.json') for role in ('author', 'auditor')}
            reasons = []
            if author['solution_status'] != 'solved' and tid not in accepted:
                reasons.append(author['solution_status'])
            if any(i.get('blocking') for i in audit.get('issues', [])) or any(d.get('blocking') for d in audit.get('decisions', [])):
                reasons.append('blocking_audit_issue')
            rows.append(dict(task_id=tid, order=e['order'], batch=b, primary_kes=e['primary_kes'], response_type=e['response_type'],
                             layer='audited_new', source='team', input=inp, author=author, audit=audit, complete=True,
                             included=not reasons, exclusion_reasons=reasons, technical_errors=[],
                             author_mode='standalone_initial', feedback_ref=None,
                             accepted_after_review=accepted.get(tid),
                             author_path=str(ap.relative_to(ROOT)), auditor_path=str(qp.relative_to(ROOT)),
                             model=ex['author']['model'], model_requested=ex['author'].get('model_requested'),
                             auditor_model_requested=ex['auditor'].get('model_requested')))
    return rows, health, manifest


def collect():
    saved100 = read(H100 / 'summary.json')
    hist = collect_saved(rep, 50, strict=True, active_snapshot=ROOT / saved100['active_snapshot'])
    for r in hist['new']:
        r['source'] = 'ext'
    paths = {ROOT / p for p in hist['input_hashes']}
    for name in ('fipi_checkpoint200.py', 'archive_support.py'):
        paths.add((ROOT / 'scripts' / name).resolve())
    paths.add((ROOT / 'docs/archive-paths.json').resolve())
    for name in ('summary.json', 'frequencies.csv', 'provenance.json'):
        paths.add((H100 / name).resolve())
    paths.add((H150 / 'tables/node-frequencies-150.csv').resolve())
    team, health, manifest = collect_team(paths)
    provenance = {Path(p).resolve().relative_to(ROOT).as_posix(): sha(p) for p in sorted(paths)}
    return dict(baseline=hist['baseline'], ext=hist['new'], team=team, catalog=hist['catalog'],
                ext_health_checks=hist['health_checks'], team_health=health, manifest=manifest,
                ext_active_snapshot=saved100['active_snapshot'], input_hashes=provenance,
                input_digest=hashlib.sha256(json.dumps(provenance, sort_keys=True).encode()).hexdigest())


# ---------------------------------------------------------------- metrics (historical definitions)

def _subset(data, new_rows):
    return dict(baseline=data['baseline'], new=new_rows, catalog=data['catalog'])


def metrics(data):
    team = data['team']
    b5 = [r for r in team if r['batch'] == 5]
    low = [r for r in team if r['batch'] != 5]
    calls = {  # population -> (new rows, population key of report_fipi_extension.metrics)
        'baseline50': (data['ext'], 'baseline50'),
        'ext_new50': (data['ext'], 'new_accumulated'),
        'team100': (team, 'new_accumulated'),
        'team_b5_default': (b5, 'new_accumulated'),
        'team_b6_12_low': (low, 'new_accumulated'),
        'audited_new150': (data['ext'] + team, 'new_accumulated'),
        'mixed_cumulative200': (data['ext'] + team, 'mixed_cumulative'),
    }
    cache, summary = {}, {}
    tables = {k: [] for k in ('frequencies', 'cooccurrence', 'transitions', 'tasks', 'composition', 'audit_statuses')}
    for pop, (rows, key) in calls.items():
        k = tuple(r['task_id'] for r in rows)
        if k not in cache:
            cache[k] = rep.metrics(_subset(data, rows))
        s, t = cache[k]
        summary[pop] = s[key]
        for name in tables:
            tables[name] += [dict(row, population=pop) for row in t[name] if row['population'] == key]
    source = {r['task_id']: r for r in data['ext'] + team}
    for row in tables['tasks']:
        r = source.get(row['task_id'])
        if r is not None and r['source'] == 'team':
            row.update(layer='audited_team', batch=r['batch'], model_requested=r['model_requested'],
                       accepted_after_review=bool(r['accepted_after_review']))
        elif r is not None:
            row.update(batch=r['batch'])
    _, t_all = cache[tuple(r['task_id'] for r in data['ext'] + team)]
    tables['candidates'] = [dict(c, source='team' if source[c['task_id']]['source'] == 'team' else 'ext',
                                 batch=source[c['task_id']]['batch']) for c in t_all['candidates']]
    return summary, tables


def self_checks(data):
    """Recomputed EDA-100 must equal the saved summary; recomputed 150-task frequencies must equal EDA-150."""
    s100, t100 = rep.metrics(_subset(data, data['ext']))
    saved = read(H100 / 'summary.json')['populations']
    eda100 = json.loads(json.dumps(s100)) == saved
    saved_freq = [r for r in csv.DictReader(open(H100 / 'frequencies.csv', encoding='utf-8-sig'))]
    eda100_freq = saved_freq == [{k: str(v) for k, v in r.items()} for r in t100['frequencies']]
    first150 = data['ext'] + [r for r in data['team'] if r['batch'] <= 8]
    s150, t150 = rep.metrics(_subset(data, first150))
    f150 = {r['catalog_kc_id']: r['task_n'] for r in t150['frequencies'] if r['population'] == 'mixed_cumulative'}
    saved150 = {r['catalog_kc_id']: int(r['tasks_150']) for r in csv.DictReader(open(H150 / 'tables/node-frequencies-150.csv', encoding='utf-8'))}
    return dict(eda100_summary_reproduced=eda100, eda100_frequencies_reproduced=eda100_freq,
                eda150_node_frequencies_reproduced=f150 == saved150,
                eda150_included_tasks=s150['mixed_cumulative']['included_n'])


# ---------------------------------------------------------------- outputs

def cards(out, data):
    (out / 'cards').mkdir()
    for r in data['team']:
        tid, inp = r['task_id'], r['input']
        tree = dom.fromstring(browser_math(inp['statement_html']))
        for image in tree.xpath('.//img'):
            match = next((a for a in inp['assets'] if Path(a['path']).name == Path(image.get('src', '')).name), None)
            if match:
                image.set('src', Path(os.path.relpath(TEAM / 'inputs' / match['path'], out / 'cards')).as_posix())
        esc = rep.esc
        body = f'<nav><a href="../index.html">Отчёт</a></nav><h1>{r["order"]}. ФИПИ {esc(tid)} · партия {r["batch"]}</h1>'
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


FIG_GROUPS = ('baseline50', 'ext_new50', 'team100')
FIG_LABELS = {'baseline50': 'Исходные 50', 'ext_new50': 'Первые 50 новых', 'team100': 'Бронь 100'}


def figures(out, summary, tables):
    fig_dir = out / 'figures'; fig_dir.mkdir()
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 10})
    def save(name):
        plt.tight_layout(); plt.savefig(fig_dir / f'{name}.png', dpi=140); plt.close()
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    for ax, dim in zip(axes, ('first_kes', 'response_type')):
        rows = [r for r in tables['composition'] if r['dimension'] == dim]
        vals = sorted({r['value'] for r in rows}); x = list(range(len(vals)))
        for i, g in enumerate(FIG_GROUPS):
            c = {r['value']: r for r in rows if r['population'] == g}
            ax.bar([v + (i - 1) * .27 for v in x], [100 * c[v]['task_n'] / c[v]['denominator'] if v in c else 0 for v in vals], .27,
                   label=f'{FIG_LABELS[g]} · отобрано {summary[g]["selected_n"]}')
        ax.set(xticks=x, xticklabels=vals, ylabel='% отобранных задач',
               title={'first_kes': 'Первая тематическая метка КЭС', 'response_type': 'Тип ответа'}[dim])
        ax.tick_params(axis='x', rotation=60); ax.legend(fontsize=7)
    save('01-composition')
    fig, axes = plt.subplots(1, 3, figsize=(15, 4))
    for ax, key in zip(axes, ('steps', 'local_kcs', 'methods')):
        for i, g in enumerate(FIG_GROUPS):
            c = Counter(r[key] for r in tables['tasks'] if r['population'] == g and r['included'])
            n = summary[g]['included_n']
            ax.bar([v + (i - 1) * .27 for v in sorted(c)], [100 * c[v] / n for v in sorted(c)], .27, label=f'{FIG_LABELS[g]} · в анализе {n}')
        ax.set(title={'steps': 'Число содержательных шагов', 'local_kcs': 'Число локальных кандидатов KC', 'methods': 'Число методов'}[key],
               ylabel='% задач, включённых в анализ'); ax.legend(fontsize=7)
    save('02-structure')
    fig, ax = plt.subplots(figsize=(11, 4.5))
    groups = ('ext_new50', 'team_b5_default', 'team_b6_12_low')
    names = {'ext_new50': 'Первые 50 новых', 'team_b5_default': 'Бронь: партия 5 (по умолчанию)', 'team_b6_12_low': 'Бронь: партии 6–12 (effort low)'}
    for i, g in enumerate(groups):
        c = summary[g]['audit_statuses']; d = c['match']['denominator']
        ax.bar([x + (i - 1) * .27 for x in range(len(STATUSES))], [100 * c[s]['numerator'] / d for s in STATUSES], .27, label=f'{names[g]} · n={d}')
    ax.set(xticks=range(len(STATUSES)), xticklabels=[STATUS_LABELS[s] for s in STATUSES], ylabel='% локальных кандидатов',
           title='Решения аудитора по слоям происхождения'); ax.legend(fontsize=8)
    save('03-audit-statuses')
    freq = {(r['population'], r['catalog_kc_id']): r['task_n'] for r in tables['frequencies']}
    top = sorted({k for g, k in freq if g == 'mixed_cumulative200'}, key=lambda k: (-freq[('mixed_cumulative200', k)], k))[:25]
    cat_names = {n['id']: n['name'] for n in read(EXT / 'catalog-for-auditor.json')['nodes']}
    fig, ax = plt.subplots(figsize=(14, 12)); y = list(range(len(top))); left = [0] * len(top)
    for g, label in (('baseline50', 'Исторические редакторские'), ('ext_new50', 'Первые 50 новых'), ('team100', 'Бронь 100')):
        vals = [freq.get((g, k), 0) for k in top]
        ax.barh(y, vals, left=left, label=label); left = [a + b for a, b in zip(left, vals)]
    ax.set(yticks=y, yticklabels=[textwrap.fill(cat_names.get(k, k), 52) for k in top], xlabel='Подтверждения: уникальных задач',
           title='Фиксированный каталог: 25 самых частых узлов, слои разделены'); ax.invert_yaxis(); ax.tick_params(axis='y', labelsize=8); ax.legend()
    save('04-catalog-evidence')


def pct(n, d):
    return f'{n}/{d} ({100 * n / d:.0f}%)' if d else '—'


def report_lines(data, summary, tables, checks):
    s = summary
    lines = ['# ФИПИ: накопленная контрольная точка 200 задач', '',
             'Расчёт по сохранённым разборам и аудитам, без новых модельных запросов. Определения метрик — как в '
             '[EDA-100](../../runs/2026-11-02-fipi-extension-150/derived/checkpoint-100-v1/report.md): узел каталога считается '
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
              'Смешанный корпус объединяет разное происхождение, поэтому его частоты описательные.', '']
    # what was added
    freq = {}
    for r in tables['frequencies']:
        freq.setdefault(r['population'], {})[r['catalog_kc_id']] = r['task_n']
    old_nodes = set(freq['baseline50']) | set(freq['ext_new50'])
    team_nodes = set(freq['team100'])
    added = sorted(team_nodes - old_nodes)
    m100 = read(H100 / 'summary.json')['populations']['mixed_cumulative']
    m200 = s['mixed_cumulative200']
    lines += ['## 2. Что добавилось', '',
              f'- Бронь добавила {s["team100"]["included_n"]} включённых задач. Узлов каталога, подтверждённых в них: {len(team_nodes)}; '
              f'из них не подтверждённых в EDA-100: {len(added)} ({", ".join(f"`{k}`" for k in added) or "нет"}).',
              f'- Подтверждённых узлов в смешанном корпусе: {m100["confirmed_catalog_nodes"]} (EDA-100) → {m200["confirmed_catalog_nodes"]} (EDA-200); '
              f'единичных: {m100["singleton_nodes"]["numerator"]}/{m100["singleton_nodes"]["denominator"]} → '
              f'{m200["singleton_nodes"]["numerator"]}/{m200["singleton_nodes"]["denominator"]}.',
              f'- Кандидаты брони, которым аудитор не нашёл узла (`new_candidate`): {s["team100"]["audit_statuses"]["new_candidate"]["numerator"]}. '
              'Это локальные предложения отдельных задач, а не число уникальных новых навыков: межзадачной консолидации не было.', '']
    # changes vs EDA-100
    lines += ['## 3. Изменения относительно EDA-100 по тем же определениям', '',
              '| Показатель | Первые 50 новых | Бронь 100 | Партия 5 (по умолчанию) | Партии 6–12 (effort low) |', '|---|---:|---:|---:|---:|']
    cols = ('ext_new50', 'team100', 'team_b5_default', 'team_b6_12_low')
    for st in STATUSES:
        lines.append(f'| {STATUS_LABELS[st]} | ' + ' | '.join(pct(s[c]['audit_statuses'][st]['numerator'], s[c]['audit_statuses'][st]['denominator']) for c in cols) + ' |')
    for key, label in (('steps', 'Медиана шагов'), ('kc_candidates', 'Медиана локальных KC')):
        lines.append(f'| {label} | ' + ' | '.join(f"{s[c]['structure']['all'][key]['median']:g}".replace('.', ',') for c in cols) + ' |')
    lines.append('| Задачи с неполным сопоставлением | ' + ' | '.join(pct(s[c]['incomplete_mapping_tasks'], s[c]['included_n']) for c in cols) + ' |')
    lines += ['', 'Различия между слоями нельзя приписать одной причине. Слои различаются составом задач (позиции очереди 1–50 и 51–150 '
              'выбраны случайно из одного допустимого остатка, но выборки малы), исполнителями (агенты запуска 2026-11-02 и агенты брони), '
              'моделью и уровнем рассуждений (партия 5 — уровень по умолчанию, партии 6–12 — `effort: low`), а также ходом работы '
              '(в части партий аудиторы прерывались и продолжались или перезапускались). [Состав выборки](figures/01-composition.png).', '']
    # errors and disputed
    lines += ['## 4. Контрольные задачи, исключения и спорные случаи', '']
    ctrl = Counter(); after = []
    for b, h in data['team_health'].items():
        for c in h['controls']:
            ctrl[c['status']] += 1
            if c['status'] != 'match': after.append(f'{c["task_id"]} (партия {b})')
    lines.append(f'- Контрольные задачи брони, сверенные с ожиданиями, записанными до авторских ответов: {sum(ctrl.values())}; '
                 f'`match` — {ctrl["match"]}, `match_after_review` — {ctrl["match_after_review"]} ({", ".join(after)}). '
                 'Во всех случаях `match_after_review` расхождение было только в записи ответа из нескольких пунктов или в нормализации строки; '
                 'сравнение сделано после просмотра ответа и слепой проверкой не является.')
    acc = [r['task_id'] for r in data['team'] if r['accepted_after_review']]
    lines.append(f'- Приняты после просмотра при статусе автора не `solved`: {", ".join(acc) or "нет"} '
                 '(ответ совпал с заранее записанным ожиданием, блокирующих замечаний нет; включены в частоты, как в кратком EDA-150).')
    excl = s['mixed_cumulative200']['excluded']
    lines += ['- Исключены из основных частот смешанного корпуса:'] + [f'  - {e["task_id"]}: {", ".join(REASON_LABELS.get(x, x) for x in e["reasons"])}' for e in excl]
    warn = [r['task_id'] for r in data['team'] if r['author'].get('warnings')]
    issues = sum(len(r['audit']['issues']) for r in data['team'])
    blocking = sum(i['blocking'] for r in data['team'] for i in r['audit']['issues'])
    lines += [f'- В брони авторы записали предупреждения в {len(warn)} задачах; аудиторы — {issues} замечаний, блокирующих {blocking}. '
              f'Спорных решений аудитора (`uncertain`): {s["team100"]["audit_statuses"]["uncertain"]["numerator"]}. '
              'Подробности — в [карточках](index.html) и [таблице кандидатов](tables/candidates.csv).',
              '- Задачи с чтением координат по рисунку (например, 3F02c4, FFE757, F9EA20) остаются зависимыми от качества изображения; '
              'в партии 5 модели Haiku и Sonnet ошиблись в чтении 3F02c4 (калибровочные попытки, в корпус не входят).', '']
    lines += ['## 5. Какие выводы пока невозможны', '',
              '- Нельзя оценить точность решений: внешнего эталона нет, контрольные ответы проверены выборочно (3 задачи на партию).',
              '- Нельзя считать `new_candidate` новыми уникальными навыками и сравнивать их число между слоями как прирост каталога.',
              '- Нельзя приписать различия долей статусов аудита модели или уровню рассуждений: слои отличаются составом, а партия 5 мала (15 задач).',
              '- Совместная встречаемость и переходы между узлами — описательные; они не доказывают порядок изучения или зависимость навыков.', '',
              '## 6. Самопроверки', '',
              f'- Пересчёт EDA-100 из тех же записей совпал с сохранённой сводкой: {checks["eda100_summary_reproduced"]}; частоты: {checks["eda100_frequencies_reproduced"]}.',
              f'- Пересчёт частот узлов на 150 задачах совпал с кратким EDA-150: {checks["eda150_node_frequencies_reproduced"]} ({checks["eda150_included_tasks"]} включённых задач).', '',
              '## Материалы', '',
              '- [Карточки задач брони и графики](index.html); карточки первых 50 новых — в [EDA-100](../../runs/2026-11-02-fipi-extension-150/derived/checkpoint-100-v1/index.html); '
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
root = next(p for p in (Path.cwd(), *Path.cwd().parents) if (p / 'scripts/fipi_checkpoint200.py').is_file())
sys.path.insert(0, str(root / 'scripts'))
import fipi_checkpoint200 as cp
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
        nbformat.v4.new_markdown_cell('Офлайн-пересчёт накопленной контрольной точки 200 задач из сохранённых разборов и аудитов. '
                                      'Новых агентов и сети нет; изменение исходных хешей останавливает пересчёт.'),
        nbformat.v4.new_code_cell(code), nbformat.v4.new_code_cell(table),
        nbformat.v4.new_code_cell("{k: summary[k]['audit_statuses'] for k in ('ext_new50', 'team100', 'team_b5_default', 'team_b6_12_low')}"),
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
        tasks=['population', 'task_id', 'layer', 'batch', 'model_requested', 'status', 'author_mode', 'complete', 'included',
               'accepted_after_review', 'response_type', 'steps', 'local_kcs', 'methods', 'matched_catalog_nodes',
               'unmatched_local_candidates', 'exclusion_reasons'],
        composition=['population', 'dimension', 'value', 'task_n', 'denominator'],
        audit_statuses=['population', 'status', 'numerator', 'denominator'],
        candidates=['source', 'batch', 'task_id', 'local_kc_id', 'name', 'status', 'catalog_kc_id', 'blocking', 'task_included', 'rationale'])
    for name, rows in tables.items():
        csvout(temp / 'tables' / f'{name}.csv', rows, fields[name])
    codebook = {}
    for row in data['baseline'] + data['ext'] + data['team']:
        for m in row['input']['metadata']:
            if m['label'] == 'КЭС:':
                for v in m['values']:
                    code, _, title = v.partition(' '); codebook[code] = title
    csvout(temp / 'tables' / 'kes-codebook.csv', [{'code': k, 'title': v} for k, v in sorted(codebook.items())], ['code', 'title'])
    batches = dict(
        historical=dict(run='data/annotation/runs/2026-11-02-fipi-extension-150', checkpoint='derived/checkpoint-100-v1',
                        active_snapshot=data['ext_active_snapshot'], health_checks=data['ext_health_checks']),
        reservation=dict(run=TEAM.relative_to(ROOT).as_posix(), issue=data['manifest']['issue_url'], owner=data['manifest']['owner'],
                         method_version=data['manifest']['method_version'], queue_orders=data['manifest']['queue_orders'],
                         batches={str(b): dict(tasks=[r['task_id'] for r in data['team'] if r['batch'] == b],
                                               model_requested=sorted({r['model_requested'] for r in data['team'] if r['batch'] == b}),
                                               **data['team_health'][b]) for b in TEAM_BATCHES}))
    dump(temp / 'batches.json', batches)
    dump(temp / 'summary.json', dict(scope='EDA-200: historical 50 + first 50 new (2026-11-02) + Bogdan108 reservation 100 (batches 5-12)',
                                     definitions='report_fipi_extension.metrics (checkpoint-100-v1) applied unchanged to each population',
                                     populations=summary, self_checks=checks,
                                     interpretations=['No answer key or external expertise: solved is not accuracy.',
                                                      'New candidates remain task-local; names do not establish identity.',
                                                      'Mixed cumulative frequencies combine historical editorial and independent audited provenance.',
                                                      'Transitions are task-presence across adjacent steps in a single method, excluding self-transitions; not prerequisites.',
                                                      'Layer differences confound task composition, executing agents, model/effort and procedure.']))
    cards(temp, data); figures(temp, summary, tables)
    lines = report_lines(data, summary, tables, checks)
    (temp / 'report.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    esc = rep.esc
    body = '<h1>ФИПИ: накопленная контрольная точка 200</h1><p><a href="report.md">report.md</a></p><pre>' + esc('\n'.join(lines)) + '</pre>'
    body += ''.join(f'<h2>{i}</h2><img src="figures/{n}.png">' for i, n in enumerate(('01-composition', '02-structure', '03-audit-statuses', '04-catalog-evidence'), 1))
    body += ('<h2>Карточки</h2><p>Исходные 50: <a href="../../runs/2026-10-31-fipi-50x1/derived/index.html">EDA-50</a>. '
             'Первые 50 новых: <a href="../../runs/2026-11-02-fipi-extension-150/derived/checkpoint-100-v1/index.html">EDA-100</a>.</p>'
             '<h3>Бронь Bogdan108, 100 задач</h3><ul>')
    body += ''.join(f'<li><a href="cards/{r["task_id"]}.html">{r["order"]}. {r["task_id"]}</a> · партия {r["batch"]} · included={r["included"]}</li>' for r in data['team'])
    body += '</ul>'
    (temp / 'index.html').write_text(rep.page('ФИПИ: EDA-200', body), encoding='utf-8')
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
