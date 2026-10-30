"""Offline analysis of the frozen G1 trial and explicit primary-agent judgments."""
import csv
import hashlib
import itertools
import json
import statistics
from pathlib import Path

from annotation_pipeline import validate

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / 'data/annotation/runs/2026-10-26-G1-5x3'


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def read(p):
    return json.loads(p.read_text(encoding='utf-8'))


def write(p, obj):
    p.write_bytes((json.dumps(obj, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))


def table(name, rows):
    if not rows:
        return
    with (RUN / 'derived' / name).open('w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def jaccard(a, b):
    return len(a & b) / len(a | b) if a | b else None


def main():
    manifest = read(RUN / 'manifest.json')
    judgments = read(RUN / 'judgments.json')
    ledger = read(RUN / 'responses.json')
    sources = {RUN / 'manifest.json', RUN / 'judgments.json', RUN / 'responses.json',
               RUN / 'interpretation.md', Path(__file__), ROOT / 'scripts/annotation_pipeline.py'}
    assert sha(RUN / 'baseline-A.txt') == manifest['baseline_prompt_sha256']
    assert sha(RUN / 'candidate-A-G1.txt') == manifest['candidate_sha256']
    assert sha(RUN / 'delta-G1.txt') == manifest['delta_sha256']
    assert sha(ROOT / 'scripts/prepare_g1_comparison.py') == manifest['prepare_script_sha256']
    assert sha(ROOT / 'docs/eda/04-annotation/08-g1-five-task-comparison.md') == manifest['protocol_sha256']
    base = (RUN / 'baseline-A.txt').read_text(encoding='utf-8')
    delta = (RUN / 'delta-G1.txt').read_text(encoding='utf-8')
    assert base.replace('В одном ответе построй решение', delta + '\nВ одном ответе построй решение') == (RUN / 'candidate-A-G1.txt').read_text(encoding='utf-8')
    for task in manifest['tasks']:
        tid = task['task_id']
        assert sha(RUN / 'inputs' / f'{tid}.json') == task['input_sha256']
        assert sha(RUN / 'requests' / f'{tid}.txt') == task['request_sha256']
        for im in task['images']:
            assert sha(RUN / im['path']) == im['sha256']
    valid_ops = set(judgments['operation_definitions'])
    sets, status, annotations, expected_keys = {}, [], [], set()
    for job in manifest['jobs']:
        assert sha(RUN / 'jobs' / f'{job["job_id"]}.txt') == job['instruction_sha256']
        for variant, folder in [('A', 'baseline'), ('A_G1', 'raw')]:
            key = f'{folder}/{job["job_id"]}.txt'
            expected_keys.add(key)
            path = RUN / key
            sources.add(path)
            if not path.is_file():
                status.append({'variant': variant, 'job': job['job_id'], 'valid': False, 'errors': 'missing'})
                continue
            expected_sha = job['baseline_sha256'] if folder == 'baseline' else ledger[job['job_id']]['raw_sha256']
            assert sha(path) == expected_sha, key
            try:
                d = read(path)
                errors = validate(d, job['task_id'])
            except (ValueError, TypeError) as exc:
                errors = [str(exc)]
            status.append({'variant': variant, 'job': job['job_id'], 'valid': not errors, 'errors': '; '.join(errors)})
            if errors:
                continue
            review = judgments['responses'][key]
            assert review['raw_sha256'] == sha(path)
            kc_map = review['kc_operations']
            assert set(kc_map) == {k['id'] for k in d['kc_candidates']}
            assert all(v and set(v) <= valid_ops and len(v) == len(set(v)) for v in kc_map.values())
            assert set(review['performed_operations']) <= valid_ops
            represented = {op for ops in kc_map.values() for op in ops}
            signatures = {tuple(sorted(ops)) for ops in kc_map.values()}
            sets[(variant, job['task_id'], job['repeat'])] = (represented, signatures)
            links = [(s['id'], k) for s in d['steps'] for k in s['kc_ids']]
            unsupported = {tuple(pair) for pair in review['unsupported_links']}
            uncertain = {tuple(pair) for pair in review['uncertain_links']}
            assert not unsupported & uncertain and unsupported | uncertain <= set(links)
            row = {
                'variant': variant, 'job': job['job_id'], 'task_id': job['task_id'],
                'steps': len(d['steps']), 'kcs': len(kc_map),
                'mixed_kcs': sum(len(v) > 1 for v in kc_map.values()),
                'performed_actions': len(review['performed_operations']),
                'covered_actions': len(set(review['performed_operations']) & represented),
                'links': len(links), 'supported_links': len(links) - len(unsupported) - len(uncertain),
                'unsupported_links': len(unsupported), 'uncertain_links': len(uncertain),
                'within_response_duplicate_pairs': sum(a == b for a, b in itertools.combinations([tuple(sorted(v)) for v in kc_map.values()], 2)),
                'math_review': review['math_review'],
                'overfragmentation': review['overfragmentation'],
            }
            annotations.append(row)
    assert set(judgments['responses']) == expected_keys
    pairs = []
    by_task = []
    for task in manifest['tasks']:
        for variant in ('A', 'A_G1'):
            local = []
            for a, b in itertools.combinations((1, 2, 3), 2):
                x = sets.get((variant, task['task_id'], a))
                y = sets.get((variant, task['task_id'], b))
                op = jaccard(x[0], y[0]) if x and y else None
                sig = jaccard(x[1], y[1]) if x and y else None
                item = {'variant': variant, 'task_id': task['task_id'], 'position': task['position'],
                        'repeat_a': a, 'repeat_b': b, 'operations_jaccard': op, 'boundaries_jaccard': sig}
                pairs.append(item)
                local.append(item)
            rows = [r for r in annotations if r['variant'] == variant and r['task_id'] == task['task_id']]
            by_task.append({'position': task['position'], 'variant': variant,
                            'mean_operations_jaccard': statistics.mean([r['operations_jaccard'] for r in local if r['operations_jaccard'] is not None]),
                            'mean_boundaries_jaccard': statistics.mean([r['boundaries_jaccard'] for r in local if r['boundaries_jaccard'] is not None]),
                            'kcs': sum(r['kcs'] for r in rows), 'mixed_kcs': sum(r['mixed_kcs'] for r in rows)})
    summary = {}
    for variant in ('A', 'A_G1'):
        rows = [r for r in annotations if r['variant'] == variant]
        pp = [r for r in pairs if r['variant'] == variant]
        summary[variant] = {'expected': 15, 'valid': sum(r['valid'] for r in status if r['variant'] == variant),
                            'kcs': sum(r['kcs'] for r in rows), 'mixed_kcs': sum(r['mixed_kcs'] for r in rows),
                            'mean_operations_jaccard': statistics.mean(r['operations_jaccard'] for r in pp if r['operations_jaccard'] is not None),
                            'mean_boundaries_jaccard': statistics.mean(r['boundaries_jaccard'] for r in pp if r['boundaries_jaccard'] is not None),
                            'available_pairs': sum(r['boundaries_jaccard'] is not None for r in pp)}
        for field in ('performed_actions', 'covered_actions', 'links', 'supported_links', 'unsupported_links', 'uncertain_links', 'within_response_duplicate_pairs', 'overfragmentation'):
            summary[variant][field] = sum(r[field] for r in rows)
        summary[variant]['task_macro_coverage'] = statistics.mean(
            statistics.mean(r['covered_actions'] / r['performed_actions'] for r in rows if r['task_id'] == t['task_id'])
            for t in manifest['tasks'])
        summary[variant]['task_macro_support'] = statistics.mean(
            statistics.mean(r['supported_links'] / r['links'] for r in rows if r['task_id'] == t['task_id'])
            for t in manifest['tasks'])
    table('technical.csv', status)
    table('responses.csv', annotations)
    table('pairs.csv', pairs)
    table('by-task.csv', by_task)
    write(RUN / 'derived/summary.json', summary)
    report = ['# Результаты малого сравнения A и A + G1', '',
              '26 октября 2026. **15 новых ответов и 15 исторических ответов базы.** Целевая выборка пяти коротких задач, не слепой или независимый тест. Смысловые соответствия заданы основным агентом; код лишь проверяет и считает.', '',
              '## Числа', '', '| Показатель | A | A + G1 |', '|---|---:|---:|']
    for label, field in [('Валидных ответов из 15', 'valid'), ('Всего KC', 'kcs'),
                         ('Составных KC', 'mixed_kcs'), ('Средний Жаккар наборов операций', 'mean_operations_jaccard'),
                         ('Средний Жаккар границ KC', 'mean_boundaries_jaccard'),
                         ('Ответов с избыточным дроблением по оценке агента', 'overfragmentation')]:
        vals = [summary[v][field] for v in ('A', 'A_G1')]
        vals = [f'{x:.3f}' if isinstance(x, float) else str(x) for x in vals]
        report.append(f'| {label} | {vals[0]} | {vals[1]} |')
    report += ['', 'Каждый Жаккар усреднён по 15 парам (три пары на задачу), все пары доступны. Границы сравниваются как множества наборов операций внутри каждого KC: составной KC отличается от двух отдельных. Широта определений и диагностическая полезность этим числом полностью не отражены.', '',
               '| Задача | Границы KC: A → A + G1 | Составных KC: A → A + G1 |', '|---|---:|---:|']
    for task in manifest['tasks']:
        bb = next(r for r in by_task if r['position'] == task['position'] and r['variant'] == 'A')
        nn = next(r for r in by_task if r['position'] == task['position'] and r['variant'] == 'A_G1')
        report.append(f'| №{task["position"]} | {bb["mean_boundaries_jaccard"]:.3f} → {nn["mean_boundaries_jaccard"]:.3f} | {bb["mixed_kcs"]}/{bb["kcs"]} → {nn["mixed_kcs"]}/{nn["kcs"]} |')
    report += ['', '## Содержательный вывод основного агента', '', (RUN / 'interpretation.md').read_text(encoding='utf-8'), '',
               '## Формулировки всех 30 ответов', '']
    for task in manifest['tasks']:
        report += [f'### №{task["position"]}: {task["task_id"]}', '']
        for variant, folder in [('A', 'baseline'), ('A + G1', 'raw')]:
            for repeat in (1, 2, 3):
                filename = f'{task["task_id"]}_r{repeat}.txt'
                d = read(RUN / folder / filename)
                report += [f'**[{variant}, r{repeat}](../{folder}/{filename})**', '']
                report += [f'- `{k["id"]}`: {k["name"]}' for k in d['kc_candidates']]
                report += ['']
    report += ['## Воспроизведение', '',
               'Из корня: `python scripts/analyze_g1_comparison.py`. Сеть и модель не вызываются. Входы смыслового анализа — `judgments.json` и `interpretation.md`; raw и запросы не исправляются. Таблицы находятся рядом с этим отчётом, хеши — в `provenance.json`.', '',
               'Полная доля эквивалентных пар определений из протокола 06 здесь не оценивалась: отдельно посчитаны только дубли составов KC внутри ответа (0 в обеих группах). Это другой, узкий показатель; его нельзя выдавать за уменьшение всех дубликатов каталога.', '',
               'По предварительной шкале покрытия A: 59/60, A + G1: 58/58; поддержанных связей 54/54 и 52/52. Эти числа зависят от ручного определения выполненных операций и их границ. Перечень составлялся тем же оценщиком при сопоставлении, не независимо; это проверка явных пропусков, не внешний эталон. В A/№8/r2 явно описана монотонность, но отдельного соответствующего KC нет. Отсутствие необязательной подстановки в корректном равносильном решении №6 не считается ошибкой.', '',
               'Явных математических ошибок основной агент при просмотре не обнаружил; экспертная проверка не выполнена. Историческая база, малый целевой набор, известные примеры и оценка без ослепления ограничивают причинные и обобщающие выводы.', '']
    (RUN / 'derived/report.md').write_bytes(('\n'.join(report)).encode('utf-8'))
    outputs = sorted((RUN / 'derived').glob('*.csv')) + [RUN / 'derived/summary.json', RUN / 'derived/report.md']
    write(RUN / 'derived/provenance.json', {
        'inputs': {p.relative_to(ROOT).as_posix(): sha(p) for p in sorted(sources)},
        'outputs': {p.name: sha(p) for p in outputs},
        'limits': 'Nonblind primary-agent operation mapping; coarse application-level equivalence; no expert standard or statistical significance claim.'})
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
