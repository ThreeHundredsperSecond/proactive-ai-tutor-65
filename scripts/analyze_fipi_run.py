"""Rebuild A-FIPI tables, figures and navigable reports from saved responses/reviews."""
import base64
import csv
import html
import json
from collections import Counter, defaultdict
from pathlib import Path

from fipi_annotation_run import ROOT, RUN, inspect_response, read, sha, write


def table(name, rows, fields):
    with (RUN / 'derived' / name).open('w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields, lineterminator='\n')
        w.writeheader()
        w.writerows(rows)


def main():
    m = read(RUN / 'manifest.json')
    ledger, reviews = read(RUN / 'responses.json'), read(RUN / 'reviews.json')
    catalog = {r['code']: r['requirement'] for r in read(RUN / 'catalog.json')['requirements']}
    assert sha(RUN / 'prompt-A-FIPI-v1.txt') == m['prompt_sha256']
    assert sha(RUN / 'catalog.json') == m['catalog_sha256']
    assert sha(ROOT / 'scripts/fipi_annotation_run.py') == m['prepare_script_sha256']
    assert sha(ROOT / 'docs/eda/04-annotation/10-fipi-19-run.md') == m['protocol_sha256']
    corpus_path = ROOT / 'data/processed/sdamgia/90702516/tasks.jsonl'
    corpus = {r['site_task_id']: r for r in map(json.loads, corpus_path.read_text(encoding='utf-8').splitlines())}
    status, kc_rows, link_rows, assignment_rows, matrix = [], [], [], [], []
    frequency, plausible_frequency = defaultdict(set), defaultdict(set)
    support, canonical_names = defaultdict(set), {}
    responses, inspected = {}, set()
    source_files = {RUN / 'manifest.json', RUN / 'responses.json', RUN / 'reviews.json', RUN / 'catalog.json',
                    RUN / 'interpretation.md', RUN / 'math-check.json', ROOT / 'scripts/check_fipi_math.py', Path(__file__), ROOT / 'scripts/fipi_annotation_run.py',
                    ROOT / 'scripts/annotation_pipeline.py', corpus_path}
    for t in m['tasks']:
        tid = t['task_id']
        for folder, expected in [('inputs', t['input_sha256']), ('requests', t['request_sha256']), ('jobs', t['job_sha256'])]:
            name = f'{tid}.json' if folder == 'inputs' else f'{tid}.txt'
            assert sha(RUN / folder / name) == expected
        for im in t['images']:
            assert sha(RUN / im['path']) == im['sha256']
        path = RUN / 'raw' / f'{tid}.txt'
        if not path.exists():
            status.append({'position': t['position'], 'task_id': tid, 'status': 'missing', 'errors': 'missing', 'math_status': 'not_reviewed'})
            continue
        assert sha(path) == ledger[tid]['raw_sha256']
        source_files.add(path)
        try:
            d = read(path)
            errors = inspect_response(d, catalog)
            if d.get('task_id') != tid: errors.append('wrong task_id')
        except (ValueError, TypeError) as exc:
            errors = [str(exc)]
        if errors:
            status.append({'position': t['position'], 'task_id': tid, 'status': 'invalid', 'errors': '; '.join(errors), 'math_status': 'not_reviewed'})
            continue
        review = reviews['tasks'][tid]
        assert review['raw_sha256'] == sha(path)
        assert len(review['fipi_links']) == len(d['fipi_links'])
        assert set(review['kcs']) == {k['id'] for k in d['kc_candidates']}
        actual_assignments = {(s['id'], k) for s in d['steps'] for k in s['kc_ids']}
        assignment_reviews = {(x['step_id'], x['kc_id']): x for x in review['assignments']}
        assert set(assignment_reviews) == actual_assignments
        assert len(assignment_reviews) == len(review['assignments'])
        inspected.add(tid)
        responses[tid] = d
        status.append({'position': t['position'], 'task_id': tid, 'status': 'valid', 'errors': '', 'math_status': review['math_status']})
        for row in review['assignments']:
            assert row['status'] in ('supported', 'questionable', 'unsupported')
            assignment_rows.append({'position': t['position'], 'task_id': tid, **row})
        for k in d['kc_candidates']:
            kr = review['kcs'][k['id']]
            cid = kr['canonical_id']
            assert cid in reviews['canonical_definitions']
            canonical_names[cid] = reviews['canonical_definitions'][cid]
            support[cid].add(tid)
            step_ids = [s['id'] for s in d['steps'] if k['id'] in s['kc_ids']]
            assigned_codes = sorted({r['requirement_code'] for r in d['fipi_links'] if k['id'] in r['kc_ids'] and r['requirement_code'] is not None}, key=int)
            kc_rows.append({'position': t['position'], 'task_id': tid, 'kc_id': k['id'], 'name': k['name'],
                            'description': k['description'], 'step_ids': ','.join(step_ids),
                            'requirement_codes': ','.join(assigned_codes), 'canonical_id': cid,
                            'mapping_reason': kr['reason'], 'granularity_note': kr.get('granularity_note', '')})
        cell = defaultdict(list)
        for i, (r, lr) in enumerate(zip(d['fipi_links'], review['fipi_links'], strict=True)):
            assert lr['index'] == i and lr['status'] in ('plausible', 'questionable', 'unsupported')
            code = r['requirement_code']
            link_rows.append({'position': t['position'], 'task_id': tid, 'index': i, 'requirement_code': code,
                              'kc_ids': ','.join(r['kc_ids']), 'anchor': r['anchor'], 'model_reason': r['reason'],
                              'review_status': lr['status'], 'review_reason': lr['reason']})
            if code is not None:
                frequency[code].add(tid)
                if lr['status'] == 'plausible': plausible_frequency[code].add(tid)
                cell[code].append(lr['status'])
        for code in catalog:
            severity = {'plausible': 1, 'questionable': 2, 'unsupported': 3}
            matrix.append({'position': t['position'], 'task_id': tid, 'code': code,
                           'value': max((severity[s] for s in cell[code]), default=0)})
    assert inspected == set(reviews['tasks']), 'Unexpected/missing saved reviews'
    req_rows = [{'code': c, 'tasks_assigned': len(frequency[c]), 'tasks_with_plausible_link': len(plausible_frequency[c]), 'requirement': catalog[c]} for c in sorted(catalog, key=int)]
    support_rows = sorted([{'canonical_id': c, 'name': canonical_names[c], 'task_count': len(tids), 'task_ids': ','.join(sorted(tids))} for c, tids in support.items()], key=lambda r: (-r['task_count'], r['name']))
    summary = {'expected': 19, 'received': len(ledger), 'valid': sum(r['status'] == 'valid' for r in status),
               'technical_status': dict(Counter(r['status'] for r in status)),
               'kc_mentions': len(kc_rows), 'canonical_candidates': len(support),
               'reused_candidates': sum(len(v) > 1 for v in support.values()),
               'singleton_candidates': sum(len(v) == 1 for v in support.values()),
               'fipi_links': len(link_rows), 'fipi_review': dict(Counter(r['review_status'] for r in link_rows)),
               'step_kc_links': len(assignment_rows), 'assignment_review': dict(Counter(r['status'] for r in assignment_rows)),
               'requirements_with_assignments': sum(bool(frequency[c]) for c in catalog),
               'math_review': dict(Counter(r['math_status'] for r in status)),
               'explicit_missing_action_notes': sum(len(r['missing_actions']) for r in reviews['tasks'].values()),
               'stability': 'not measured: one response per task',
               'limits': 'Known development set; nonblind primary-agent semantic judgments; no expert standard.'}
    kc_codes = defaultdict(set)
    for r in link_rows:
        if r['requirement_code'] is not None:
            for kid in r['kc_ids'].split(','): kc_codes[(r['task_id'], kid)].add(r['requirement_code'])
    summary['kcs_with_known_requirement'] = sum(bool(kc_codes[(r['task_id'], r['kc_id'])]) for r in kc_rows)
    summary['kcs_with_multiple_requirements'] = sum(len(kc_codes[(r['task_id'], r['kc_id'])]) > 1 for r in kc_rows)
    summary['kcs_without_known_requirement'] = len(kc_rows) - summary['kcs_with_known_requirement']
    table('technical.csv', status, ['position', 'task_id', 'status', 'errors', 'math_status'])
    table('kcs.csv', kc_rows, ['position', 'task_id', 'kc_id', 'name', 'description', 'step_ids', 'requirement_codes', 'canonical_id', 'mapping_reason', 'granularity_note'])
    table('fipi-links.csv', link_rows, ['position', 'task_id', 'index', 'requirement_code', 'kc_ids', 'anchor', 'model_reason', 'review_status', 'review_reason'])
    table('step-kc.csv', assignment_rows, ['position', 'task_id', 'step_id', 'kc_id', 'status', 'reason'])
    table('requirements.csv', req_rows, ['code', 'tasks_assigned', 'tasks_with_plausible_link', 'requirement'])
    table('matrix.csv', matrix, ['position', 'task_id', 'code', 'value'])
    table('kc-support.csv', support_rows, ['canonical_id', 'name', 'task_count', 'task_ids'])
    write(RUN / 'derived/canonical-catalog.json', [
        {'id': r['canonical_id'], 'name': r['name'], 'status': 'primary_agent_candidate',
         'description': next(k['description'] for k in kc_rows if k['canonical_id'] == r['canonical_id']),
         'task_count': r['task_count'], 'task_ids': r['task_ids'].split(','),
         'scope_note': 'Описание из первого исходного KC; ограничения других формулировок и основания сопоставления сохранены в reviews.json. Это кандидат, не утверждённое умение.',
         'sources': [{'task_id': k['task_id'], 'kc_id': k['kc_id'], 'step_ids': k['step_ids'].split(',')}
                     for k in kc_rows if k['canonical_id'] == r['canonical_id']]}
        for r in support_rows])
    write(RUN / 'derived/summary.json', summary)

    # Plot the saved tables, so each figure has a directly reusable data input.
    def csv_rows(name):
        with (RUN / 'derived' / name).open(encoding='utf-8', newline='') as f:
            return list(csv.DictReader(f))
    req_rows = csv_rows('requirements.csv')
    for row in req_rows:
        for field in ('tasks_assigned', 'tasks_with_plausible_link'):
            row[field] = int(row[field])
    matrix = csv_rows('matrix.csv')
    for row in matrix:
        row['position'], row['value'] = int(row['position']), int(row['value'])
    support_rows = csv_rows('kc-support.csv')
    for row in support_rows:
        row['task_count'] = int(row['task_count'])

    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.colors import ListedColormap, BoundaryNorm
    plt.rcParams['svg.hashsalt'] = 'fipi-19-fixed'
    def savefig(fig, name):
        fig.tight_layout()
        fig.savefig(RUN / 'derived' / f'{name}.png', dpi=145)
        fig.savefig(RUN / 'derived' / f'{name}.svg', metadata={'Date': None})
        plt.close(fig)
    fig, ax = plt.subplots(figsize=(9, 4.2))
    xx = list(range(13))
    ax.bar([x-.18 for x in xx], [r['tasks_assigned'] for r in req_rows], width=.36, label='Назначено моделью')
    ax.bar([x+.18 for x in xx], [r['tasks_with_plausible_link'] for r in req_rows], width=.36, label='Есть связь, признанная подходящей агентом')
    ax.set(xticks=xx, xticklabels=[r['code'] for r in req_rows], xlabel='Код предметного требования ФИПИ', ylabel='Разных задач', title='Представленность требований в 19 задачах — не полнота покрытия')
    ax.yaxis.get_major_locator().set_params(integer=True)
    ax.legend(fontsize=8)
    savefig(fig, 'requirements')
    mat = [[next(r['value'] for r in matrix if r['position'] == pos and r['code'] == str(c)) for c in range(1,14)] for pos in range(1,20)]
    fig, ax = plt.subplots(figsize=(8.4,7.3))
    cmap = ListedColormap(['#f0f0f0','#4178b5','#efad3d','#ce4d4d'])
    im = ax.imshow(mat, cmap=cmap, norm=BoundaryNorm([-.5,.5,1.5,2.5,3.5],4), aspect='auto')
    ax.set(xticks=range(13), xticklabels=range(1,14), yticks=range(19), yticklabels=range(1,20), xlabel='Код требования ФИПИ', ylabel='Позиция задачи', title='Назначения и предварительная оценка связей')
    cb = fig.colorbar(im, ax=ax, ticks=[0,1,2,3], fraction=.05)
    cb.ax.set_yticklabels(['Нет','Подходит','Спорно','Не подходит'])
    savefig(fig, 'matrix')
    reused = [r for r in support_rows if r['task_count'] > 1][:20]
    fig, ax = plt.subplots(figsize=(11, max(3.5, len(reused)*.42+1.2)))
    if reused:
        labels = [r['name'] for r in reused]
        ax.barh(range(len(reused)), [r['task_count'] for r in reused])
        ax.set_yticks(range(len(reused)), labels)
        ax.invert_yaxis()
    ax.set(xlabel='Разных задач с кандидатным KC', title='Повторяемость после явного сопоставления основным агентом')
    ax.xaxis.get_major_locator().set_params(integer=True)
    savefig(fig, 'kc-support')

    interpretation = (RUN / 'interpretation.md').read_text(encoding='utf-8')
    md = ['# A-FIPI-v1: обзор 19 задач', '',
          '19 новых ответов, один на задачу; все исходные данные и оценки доступны по ссылкам ниже. Статусы — предварительная оценка основного агента, не экспертный эталон.', '',
          '## Summary', '', f'- Получено: {summary["received"]}/19; технически валидных: {summary["valid"]}/19.',
          f'- KC: {len(kc_rows)} исходных упоминаний → {len(support)} кандидатных определений после явного сопоставления; в нескольких задачах: {summary["reused_candidates"]}.',
          f'- Связей с ФИПИ: {len(link_rows)}; оценки: {summary["fipi_review"]}.',
          f'- Назначений шаг → KC: {len(assignment_rows)}; оценки: {summary["assignment_review"]}.',
          f'- Представлены назначениями {summary["requirements_with_assignments"]} из 13 широких требований. Это не процент покрытия программы.',
          f'- Предварительная проверка решений: {summary["math_review"]}. Стабильность не измерялась.', '',
          interpretation, '', '## Графики', '', '![Представленность требований](requirements.png)', '', '![Матрица назначений](matrix.png)', '', '![Повторяемость KC](kc-support.png)', '',
          '## Навигация по задачам', '', '| № | Классы модели | Математический просмотр | Содержательные замечания | Материалы |', '|---|---|---|---|---|']
    for t in m['tasks']:
        tid = t['task_id']; r = reviews['tasks'].get(tid)
        classes = ', '.join(responses[tid]['selected_requirements']) if tid in responses else '—'
        note = r['note'].replace('|','/').replace('\n',' ') if r else 'Не оценено'
        md.append(f'| {t["position"]} | {classes} | {r["math_status"] if r else "not_reviewed"} | {note} | [Карточка](review.html#task-{t["position"]}) · [raw](../raw/{tid}.txt) · [запрос](../requests/{tid}.txt) |')
    md += ['', '## Пересчёт и пределы выводов', '',
           'Из корня: `python scripts/fipi_annotation_run.py capture`, затем `python scripts/analyze_fipi_run.py`. Модель/сеть не вызываются. Смысловые входы — `../reviews.json` и `../interpretation.md`; численные таблицы CSV находятся рядом с отчётом. SHA-256 кода, ответов, оценок, таблиц, отчётов и графиков — `provenance.json`.', '',
           'Количество кандидатов зависит от консервативных решений о границах KC. Изменение числа KC не является автоматически улучшением; объединения по широким темам не выполнялись. Направление связи с ФИПИ выбирала модель; смысл проверял основной агент. Переиспользование кандидатных действий не доказывает перенос навыка у ученика. Все 19 задач — известный набор разработки. Полнота программы, устойчивость повторов и эффективность тьютора не проверены.', '']
    (RUN / 'derived/report.md').write_bytes(('\n'.join(md)).encode('utf-8'))
    esc = html.escape
    def image(path, alt):
        return '<img alt="'+esc(alt)+'" src="data:image/png;base64,'+base64.b64encode(path.read_bytes()).decode('ascii')+'">'
    web = ['<!doctype html><meta charset="utf-8"><title>A-FIPI: 19 задач</title><style>body{font:16px system-ui;max-width:1200px;margin:30px auto;padding:0 20px;line-height:1.5}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f4f5f7;padding:14px}img{max-width:100%;height:auto}section{border-top:2px solid #ccc;padding-top:20px;margin-top:35px}table{border-collapse:collapse}td,th{border:1px solid #ccc;padding:7px}a{color:#195fab}</style>',
           '<h1>A-FIPI-v1: 19 задач</h1><p>Один ответ на задачу. Предварительная проверка основным агентом; независимой экспертизы нет. Каталог и математические решения не считаются подтверждённой моделью ученика.</p>',
           '<p>'+ ' · '.join(f'<a href="#task-{t["position"]}">№{t["position"]}</a>' for t in m['tasks']) + '</p>',
           '<h2>Summary</h2><pre>'+esc(json.dumps(summary,ensure_ascii=False,indent=2))+'</pre>',
           '<h2>Выводы</h2><pre>'+esc(interpretation)+'</pre>']
    for name in ('requirements','matrix','kc-support'):
        web.append(image(RUN / 'derived' / f'{name}.png', name))
    for t in m['tasks']:
        tid = t['task_id']; r = reviews['tasks'].get(tid)
        web += [f'<section id="task-{t["position"]}"><h2>№{t["position"]} · {tid}</h2>',
                f'<p><a href="../requests/{tid}.txt">Полный запрос</a> · <a href="../raw/{tid}.txt">Исходный ответ</a> · <a href="../reviews.json">Оценки и сопоставление</a> · <a href="../catalog.json">Все требования</a></p>',
                '<h3>Условие</h3><pre>'+esc(read(RUN / 'inputs' / f'{tid}.json')['statement'])+'</pre>']
        web += [image(RUN / im['path'], f'Условие №{t["position"]}') for im in t['images']]
        if r:
            web += ['<h3>Предварительная проверка</h3><pre>'+esc(json.dumps(r,ensure_ascii=False,indent=2))+'</pre>']
        web += ['<h3>Ответ источника для отдельного сравнения, не эталон</h3><pre>'+esc(corpus[tid]['answer']['text_accessibility'])+'</pre>',
                '<h3>Полный исходный ответ модели</h3><pre>'+esc((RUN / 'raw' / f'{tid}.txt').read_text(encoding='utf-8'))+'</pre></section>']
    (RUN / 'derived/review.html').write_bytes(('\n'.join(web)).encode('utf-8'))
    outputs = [p for p in (RUN / 'derived').iterdir() if p.name != 'provenance.json']
    write(RUN / 'derived/provenance.json', {'inputs': {p.relative_to(ROOT).as_posix(): sha(p) for p in sorted(source_files)},
          'outputs': {p.name: sha(p) for p in sorted(outputs)}, 'figure_sources': {
              'requirements': 'requirements.csv', 'matrix': 'matrix.csv', 'kc-support': 'kc-support.csv'},
          'review_process': reviews['process']})
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
