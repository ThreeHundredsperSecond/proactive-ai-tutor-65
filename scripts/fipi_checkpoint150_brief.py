#!/usr/bin/env python3
"""Brief cumulative checkpoint EDA-150 from saved results only (no model calls).

Inputs:
  - EDA-100: data/annotation/runs/2026-11-02-fipi-extension-150/derived/checkpoint-100-v1 (frequencies, tasks, summary)
  - batches 5-8 of data/annotation/runs/2026-11-07-fipi-team-bogdan108-051-150 (raw/ answers, checks/, attempts/)
Metric definitions follow checkpoint-100-v1: a catalog node is "assigned" in a task when an auditor decision has
status `match`; frequencies count tasks, not mentions; singleton = node assigned in exactly one included task.
The new 50 tasks are disjoint from the 100, so per-node task counts of the two corpora add up exactly.

Usage: python3 scripts/fipi_checkpoint150_brief.py --out data/annotation/analyses/2026-11-08-fipi-checkpoint-150-v1
"""
import argparse, csv, hashlib, json, statistics, subprocess, sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
H100 = ROOT / 'data/annotation/runs/2026-11-02-fipi-extension-150/derived/checkpoint-100-v1'
RUN = ROOT / 'data/annotation/runs/2026-11-07-fipi-team-bogdan108-051-150'
BATCHES = ['5', '6', '7', '8']
STATUSES = ['match', 'new_candidate', 'needs_split', 'uncertain']


def rj(p):
    return json.loads(Path(p).read_text(encoding='utf-8'))


def rcsv(p):
    with open(p, encoding='utf-8-sig') as f:
        return list(csv.DictReader(f))


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def med(xs):
    return statistics.median(xs) if xs else None


def task_records(answers_dir_author, answers_dir_auditor, ids):
    out = []
    for t in ids:
        a = rj(answers_dir_author / f'{t}.json')
        q = rj(answers_dir_auditor / f'{t}.json')
        inp = rj(RUN / 'inputs/tasks' / f'{t}.json')
        meta = {m['label']: m['values'] for m in inp['metadata']}
        matched = {d['catalog_kc_id'] for d in q['decisions'] if d['status'] == 'match' and d.get('catalog_kc_id')}
        n_match = sum(d['status'] == 'match' for d in q['decisions'])
        out.append(dict(task_id=t, status=a['solution_status'], steps=len(a['steps']), local_kcs=len(a['kc_candidates']),
                        methods=len(a['methods']), response_type=(meta.get('Тип ответа:') or [''])[0],
                        first_kes=(meta.get('КЭС:') or [''])[0].split(' ')[0], nodes=sorted(matched),
                        decisions=Counter(d['status'] for d in q['decisions']), issues=len(q['issues']),
                        blocking=sum(i['blocking'] for i in q['issues']), unmatched=len(a['kc_candidates']) - n_match,
                        new_candidates=[(c['id'], c['name']) for c in a['kc_candidates']
                                        if any(d['local_kc_id'] == c['id'] and d['status'] == 'new_candidate' for d in q['decisions'])],
                        warnings=len(a.get('warnings', []))))
    return out


def layer_stats(recs):
    dec = Counter()
    for r in recs:
        dec.update(r['decisions'])
    total = sum(dec.values())
    by_type = {}
    for rt in sorted({r['response_type'] for r in recs}):
        sub = [r for r in recs if r['response_type'] == rt]
        by_type[rt] = dict(n=len(sub), median_steps=med([r['steps'] for r in sub]), median_local_kcs=med([r['local_kcs'] for r in sub]))
    return dict(tasks=len(recs), solution_statuses=dict(Counter(r['status'] for r in recs)),
                median_steps=med([r['steps'] for r in recs]), median_local_kcs=med([r['local_kcs'] for r in recs]),
                by_response_type=by_type,
                audit_statuses={s: {'numerator': dec[s], 'denominator': total} for s in STATUSES},
                incomplete_mapping_tasks={'numerator': sum(r['unmatched'] > 0 for r in recs), 'denominator': len(recs)},
                unmatched_local_candidates={'numerator': sum(r['unmatched'] for r in recs), 'denominator': sum(r['local_kcs'] for r in recs)},
                issues=sum(r['issues'] for r in recs), blocking=sum(r['blocking'] for r in recs))


def node_freq(recs):
    f = Counter()
    for r in recs:
        f.update(r['nodes'])
    return f


def pct(numerator, denominator):
    n, d = numerator, denominator
    return f'{n}/{d} ({100 * n / d:.0f}%)' if d else '—'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True)
    out = ROOT / ap.parse_args().out
    assert not out.exists(), f'{out} exists; write a new version instead of overwriting'
    (out / 'tables').mkdir(parents=True)

    man = rj(RUN / 'manifest.json')['batches']
    catalog = {k['id']: k for k in rj(RUN / 'catalog-for-auditor.json')['kcs']} if 'kcs' in rj(RUN / 'catalog-for-auditor.json') else {}
    if not catalog:
        cat = rj(RUN / 'catalog-for-auditor.json')
        items = cat if isinstance(cat, list) else next(v for v in cat.values() if isinstance(v, list))
        catalog = {k.get('id') or k.get('catalog_kc_id'): k for k in items}

    # ---- new 50 (active answers = raw/, active-attempts.json is empty) ----
    assert rj(RUN / 'active-attempts.json') == {}, 'active attempts present: adapt selection'
    batch_of, recs = {}, []
    for b in BATCHES:
        for t in man[b]:
            batch_of[t] = b
        recs += task_records(RUN / 'raw/author', RUN / 'raw/auditor', man[b])
    health = {b: rj(RUN / f'checks/batch-{int(b):02}.json') for b in BATCHES}
    math = {b: rj(RUN / f'checks/batch-{int(b):02}-math.json') for b in BATCHES}
    accepted = [x['task_id'] for b in BATCHES for x in health[b].get('accepted_after_review', [])]
    quarantined = [t for b in BATCHES for t in health[b]['quarantined_ids']]
    included = [r for r in recs if r['task_id'] not in quarantined and r['blocking'] == 0]
    model = {b: {rj(p)['model'] + ' / ' + (rj(p).get('model_requested') or '?')
                 for p in RUN.glob('executions/*.json') if p.stem.split('-', 1)[1] in man[b]} for b in BATCHES}

    layers = {'opus_default_b5': [r for r in included if batch_of[r['task_id']] == '5'],
              'opus_low_b6_8': [r for r in included if batch_of[r['task_id']] in '678'],
              'new50_all': included}
    layer_summary = {k: layer_stats(v) for k, v in layers.items()}

    # ---- EDA-100 reference (same definitions) ----
    s100 = rj(H100 / 'summary.json')['populations']
    f100 = {r['catalog_kc_id']: int(r['task_n']) for r in rcsv(H100 / 'frequencies.csv') if r['population'] == 'mixed_cumulative'}
    inc100 = s100['mixed_cumulative']['included_n']
    f50 = node_freq(included)
    f150 = Counter(f100) + f50
    newly_observed = sorted(set(f50) - set(f100))

    # ---- calibration on batch 5: same 15 tasks, three models ----
    calib = {}
    for name, ad, qd in [('claude-opus-5-5 (raw/)', RUN / 'raw/author', RUN / 'raw/auditor'),
                         ('claude-haiku-5-5 (attempt haiku)', RUN / 'attempts/haiku/author', RUN / 'attempts/haiku/auditor'),
                         ('claude-sonnet-5-5 (attempt sonnet)', RUN / 'attempts/sonnet/author', RUN / 'attempts/sonnet/auditor')]:
        suffix = '' if 'raw' in name else '-' + name.split('attempt ')[1].rstrip(')')
        ids = man['5']
        av = sum(rj(RUN / f'validations/author-{t}{suffix}.json')['result']['status'] == 'technical_pass' for t in ids)
        qv = [t for t in ids if rj(RUN / f'validations/auditor-{t}{suffix}.json')['result']['status'] == 'technical_pass']
        authors = {t: rj(ad / f'{t}.json') for t in ids}
        dec = Counter()
        for t in qv:
            dec.update(d['status'] for d in rj(qd / f'{t}.json')['decisions'])
        mfile = RUN / f'checks/batch-05{suffix}-math.json'
        calib[name] = dict(valid_authors=av, valid_audits=len(qv), tasks=len(ids),
                           steps=sum(len(a['steps']) for a in authors.values()),
                           local_kcs=sum(len(a['kc_candidates']) for a in authors.values()),
                           answer_3F02c4=authors['3F02c4']['answer'],
                           control_matches=sum(c['status'].startswith('match') for c in rj(mfile)['checks']) if mfile.exists() else None,
                           audit_statuses_valid_audits=dict(dec))

    # ---- tables ----
    def wcsv(name, fields, rows):
        with open(out / 'tables' / name, 'w', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(rows)
    wcsv('tasks-new50.csv', ['task_id', 'batch', 'status', 'response_type', 'first_kes', 'steps', 'local_kcs', 'methods',
                             'matched_nodes', 'unmatched_local_candidates', 'issues', 'included'],
         [dict(task_id=r['task_id'], batch=batch_of[r['task_id']], status=r['status'], response_type=r['response_type'],
               first_kes=r['first_kes'], steps=r['steps'], local_kcs=r['local_kcs'], methods=r['methods'],
               matched_nodes=';'.join(r['nodes']), unmatched_local_candidates=r['unmatched'], issues=r['issues'],
               included=r in included) for r in recs])
    wcsv('node-frequencies-150.csv', ['catalog_kc_id', 'name', 'tasks_eda100', 'tasks_new50', 'tasks_150'],
         [dict(catalog_kc_id=k, name=(catalog.get(k) or {}).get('name', ''), tasks_eda100=f100.get(k, 0), tasks_new50=f50.get(k, 0),
               tasks_150=v) for k, v in sorted(f150.items(), key=lambda x: (-x[1], x[0]))])
    wcsv('new-candidates-new50.csv', ['task_id', 'batch', 'local_kc_id', 'name'],
         [dict(task_id=r['task_id'], batch=batch_of[r['task_id']], local_kc_id=i, name=n) for r in included for i, n in r['new_candidates']])

    summary = dict(
        generated_at=datetime.now(timezone.utc).isoformat(), scope='EDA-150 brief: EDA-100 (98 included) + batches 5-8 (50 tasks)',
        definitions='checkpoint-100-v1: assignment = audit status match; task-level counts; singleton = assigned in exactly one included task',
        new50=dict(tasks=len(recs), included=len(included), quarantined=quarantined, accepted_after_review=accepted,
                   batches={b: dict(tasks=len(man[b]), models=sorted(model[b]), health=health[b]['status'],
                                    controls=[(c['task_id'], c['status']) for c in math[b]['checks']]) for b in BATCHES},
                   response_types=dict(Counter(r['response_type'] for r in recs)),
                   first_kes_section=dict(Counter(r['first_kes'].split('.')[0] for r in recs))),
        layers=layer_summary,
        eda100_new_layer=dict(audit_statuses=s100['new_accumulated']['audit_statuses'],
                              incomplete_mapping_tasks={'numerator': s100['new_accumulated']['incomplete_mapping_tasks'],
                                                        'denominator': s100['new_accumulated']['included_n']},
                              unmatched_local_candidates=s100['new_accumulated']['unmatched_local_candidates'],
                              structure=s100['new_accumulated']['structure']['all']),
        catalog=dict(catalog_definitions=len(catalog), included_tasks_100=inc100, included_tasks_150=inc100 + len(included),
                     nodes_100=len(f100), nodes_new50=len(f50), nodes_150=len(f150), newly_observed_in_new50=newly_observed,
                     singleton_100={'numerator': sum(v == 1 for v in f100.values()), 'denominator': len(f100)},
                     singleton_new50={'numerator': sum(v == 1 for v in f50.values()), 'denominator': len(f50)},
                     singleton_150={'numerator': sum(v == 1 for v in f150.values()), 'denominator': len(f150)},
                     top_new50=f50.most_common(10),
                     new_candidates_new50=sum(len(r['new_candidates']) for r in included)),
        calibration_batch5=calib)
    (out / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    # ---- report ----
    L = layer_summary; c = summary['catalog']; e = summary['eda100_new_layer']
    def st(x):
        a = x['audit_statuses']; d = sum(v['numerator'] for v in a.values())
        return ' / '.join(f"{a[s]['numerator']}" for s in STATUSES) + f' (из {d})'
    lines = ['# ФИПИ: промежуточная контрольная точка 150 задач (кратко)', '',
             f'Собрано {datetime.now(timezone.utc):%Y-%m-%d} скриптом `scripts/fipi_checkpoint150_brief.py` из сохранённых ответов, без вызовов моделей. '
             'Определения метрик — как в [EDA-100](../../runs/2026-11-02-fipi-extension-150/derived/checkpoint-100-v1/report.md): '
             'назначение узла каталога — решение аудитора `match`, частоты считаются по задачам. Это краткий отчёт: ноутбук, карточки и графики не строились.', '',
             '## 1. Зафиксированные результаты: новые 50 задач (партии 5–8)', '',
             '| Партия | Задач | Модель / запрошено | Health check | Контрольные задачи |', '|---|---:|---|---|---|']
    for b, v in summary['new50']['batches'].items():
        lines.append(f"| {b} | {v['tasks']} | {'; '.join(x.replace('claude-', '') for x in v['models'])} | {v['health']} | "
                     + ', '.join(f'{t} {s}' for t, s in v['controls']) + ' |')
    n = summary['new50']
    lines += ['', f"Все 50 пар «автор + аудитор» технически валидны, блокирующих замечаний нет; в основные частоты входят {n['included']}/50. "
              f"Статус `partial` у {', '.join(accepted) or '—'}: ответ совпал с ожиданием и принят после просмотра. "
              f"Типы ответа: {', '.join(f'{k} — {v}' for k, v in n['response_types'].items())}.", '',
              '## 2. Что добавилось в карту навыков', '',
              f"Каталог не менялся: {c['catalog_definitions']} предварительных определений. Новые задачи дали назначения в {c['nodes_new50']} узлах; "
              f"впервые получили назначение (в EDA-100 их не было): **{len(c['newly_observed_in_new50'])}**.", '',
              '| Показатель | EDA-100 (98 задач) | Новые 50 | Вместе (148 задач) |', '|---|---:|---:|---:|',
              f"| Узлы каталога с назначениями | {c['nodes_100']} | {c['nodes_new50']} | {c['nodes_150']} |",
              f"| Узлы с назначением ровно в одной задаче | {pct(**c['singleton_100'])} | {pct(**c['singleton_new50'])} | {pct(**c['singleton_150'])} |", '',
              'Впервые наблюдаемые узлы: ' + ', '.join(f"`{k}` ({(catalog.get(k) or {}).get('name', '')})" for k in c['newly_observed_in_new50']) + '.', '',
              'Чаще всего в новых 50 (задач): ' + '; '.join(f"`{k}` — {v}" for k, v in c['top_new50']) + '.', '',
              f"Аудиторы предложили {c['new_candidates_new50']} новых локальных кандидатов (`new_candidate`), список — `tables/new-candidates-new50.csv`. "
              'Межзадачной консолидации нет, поэтому это не число новых уникальных навыков.', '',
              '## 3. Разметка на разных моделях', '',
              '| Слой | Задач | Медиана шагов | Медиана локальных KC | match / new / split / uncertain | Неполное сопоставление |', '|---|---:|---:|---:|---|---:|',
              f"| EDA-100, новые 50 (агенты Codex) | {s100['new_accumulated']['included_n']} | {e['structure']['steps']['median']} | {e['structure']['kc_candidates']['median']} | "
              + ' / '.join(str(e['audit_statuses'][s]['numerator']) for s in STATUSES) + f" | {pct(**e['incomplete_mapping_tasks'])} |"]
    for key, label in [('opus_default_b5', 'Партия 5: Opus, уровень по умолчанию'), ('opus_low_b6_8', 'Партии 6–8: Opus, `effort: low`')]:
        x = L[key]
        lines.append(f"| {label} | {x['tasks']} | {x['median_steps']} | {x['median_local_kcs']} | {st(x)} | {pct(**x['incomplete_mapping_tasks'])} |")
    lines += ['', 'Калибровка на одних и тех же 15 задачах партии 5:', '',
              '| Модель | Валидные авторы | Валидные аудиты | Контрольные | 3F02c4 | Шаги / KC |', '|---|---:|---:|---:|---|---:|']
    for k, v in calib.items():
        lines.append(f"| {k} | {v['valid_authors']}/15 | {v['valid_audits']}/15 | {v['control_matches']}/3 | `{v['answer_3F02c4']}` | {v['steps']} / {v['local_kcs']} |")
    lines += ['', 'В 3F02c4 правильно прочитал рисунок только Opus (ответ 10; проверено измерением рисунка после знакомства с ответами, не вслепую). '
              'Невалидные аудиты Haiku и Sonnet — переименование ID кандидатов (`kc1`→`k1`). Haiku и Sonnet не активированы и в частоты не входят.', '',
              '## 4. Ограничения', '',
              '- Слои различаются моделью, уровнем рассуждений, средой исполнения (Codex и Claude Code) и составом задач; различия описательные, причинный эффект не установлен.',
              '- Сравнение слоёв по числу шагов и KC зависит от задач в партиях; партии 6–8 выбраны из той же очереди, но это другие задачи, чем партия 5.',
              '- Контрольные ответы — выборочные проверки основного ассистента, не экспертиза. В партии 7 одна контрольная задача (92FD74) сравнена после просмотра ответа.',
              '- Частоты — частоты принятых связей с фиксированным каталогом, а не полный перечень действий в решениях.', '',
              'Таблицы: `tables/tasks-new50.csv`, `tables/node-frequencies-150.csv`, `tables/new-candidates-new50.csv`; числа — `summary.json`; входы и хеши — `provenance.json`.']
    (out / 'report.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')

    inputs = [H100 / 'summary.json', H100 / 'frequencies.csv', RUN / 'manifest.json', RUN / 'catalog-for-auditor.json', RUN / 'active-attempts.json']
    inputs += [RUN / f'checks/batch-{int(b):02}.json' for b in BATCHES] + [RUN / f'checks/batch-{int(b):02}-math.json' for b in BATCHES]
    for b in BATCHES:
        for t in man[b]:
            inputs += [RUN / 'raw/author' / f'{t}.json', RUN / 'raw/auditor' / f'{t}.json', RUN / 'inputs/tasks' / f'{t}.json']
    for att in ['haiku', 'sonnet']:
        inputs += sorted((RUN / 'attempts' / att).rglob('*.json'))
    head = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    prov = dict(generated_at=summary['generated_at'], code={'path': 'scripts/fipi_checkpoint150_brief.py', 'sha256': sha(__file__)},
                git_head=head, python=sys.version.split()[0], executed=True, notebook=None,
                inputs=[{'path': str(p.relative_to(ROOT)), 'sha256': sha(p)} for p in inputs],
                outputs=[{'path': str(p.relative_to(ROOT)), 'sha256': sha(p)} for p in sorted(out.rglob('*')) if p.is_file()])
    (out / 'provenance.json').write_text(json.dumps(prov, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(out.relative_to(ROOT))


if __name__ == '__main__':
    main()
