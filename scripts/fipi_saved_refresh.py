"""Offline review of published saved records; no model or network calls."""
import copy
import csv
import hashlib
import json
import subprocess
from pathlib import Path

from PIL import Image
import fipi_team_checkpoint250 as previous
from fipi_eda50 import validate_one

ROOT = previous.ROOT
NEXT = ROOT/'data/annotation/runs/2026-11-09-fipi-team-bogdan108-next-100'
OUT = ROOT/'data/annotation/analyses/2026-11-10-saved-data-refresh-v1'
IMPORT = ROOT/'data/annotation/team/imports/2026-11-10-bogdan-next-2937b04.json'
BASE = '8119f21383ec6f83554da7a6d8f97f5d02bdb07d'
COMMIT = '2937b04d5e2df51da67e6a1a2a6c784204960a4e'


def read(p):
    return json.loads(Path(p).read_text(encoding='utf-8'))


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def write(p, value):
    p = Path(p)
    data = json.dumps(value, ensure_ascii=False, indent=2)+'\n'
    if p.exists():
        assert p.read_text(encoding='utf-8') == data, f'Immutable output differs: {p}'
    else:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(data, encoding='utf-8')


def protect_100():
    path = 'notebooks/checkpoint-2/EDA.ipynb'
    original = json.loads(subprocess.check_output(['git','show',f'{BASE}:{path}']))
    current = read(ROOT/path)
    text = lambda c: ''.join(c['source']) if isinstance(c['source'], list) else c['source']
    assert len(original['cells']) == 35
    assert all(text(c) == text(current['cells'][i]) for i,c in enumerate(original['cells']) if i)
    assert text(original['cells'][0]) in text(current['cells'][0])
    pngs = lambda n: [o['data']['image/png'] for c in n['cells'] for o in c.get('outputs',[]) if 'image/png' in o.get('data',{})]
    assert len(pngs(original)) == 11 and pngs(original) == pngs(current)[:11]
    return dict(source_commit=BASE, original_cells=35, preserved_body_cells=34,
                original_navigation_embedded=True, original_png_byte_equal=11)


def collect():
    protection = protect_100()
    data = previous.collect(strict=True)
    imported = read(IMPORT)
    assert imported['source_commit'] == COMMIT
    hashes = dict(data['input_hashes'])
    for f in imported['files']:
        assert sha(ROOT/f['local_path']) == f['sha256'], f['local_path']
        hashes[f['local_path']] = f['sha256']
    hashes[IMPORT.relative_to(ROOT).as_posix()] = sha(IMPORT)
    manifest = read(NEXT/'manifest.json')
    assert manifest['method_version'] == 'fipi-extension-v1.1'
    assert read(NEXT/'active-attempts.json') == {}, 'Adapt active attempts explicitly'
    for f in manifest['methodology']:
        assert sha(NEXT/f['path']) == f['sha256'], f['path']
    assert read(NEXT/'catalog-for-auditor.json') == read(previous.sol.RUN/'catalog-for-auditor.json')
    assert sha(ROOT/'data/fipi/2026-10-31-profile/tasks.jsonl') == manifest['sources']['data/fipi/2026-10-31-profile/tasks.jsonl']
    entries = {t['task_id']:t for t in manifest['tasks']}
    present_a = {p.stem for p in (NEXT/'raw/author').glob('*.json')}
    present_q = {p.stem for p in (NEXT/'raw/auditor').glob('*.json')}
    assert present_a == present_q and len(present_a) == 65
    assert present_a == {t['task_id'] for t in manifest['tasks'] if t['batch'] <= 5}
    metadata_drift = []
    for path, expected_sha in manifest['sources'].items():
        actual_sha = sha(ROOT/path)
        if actual_sha == expected_sha:
            continue
        if path.endswith('/claims.json'):
            reason = 'Mutable coordination snapshot; current claims differ from preparation state'
        elif path.endswith('/registry.json'):
            committed = json.loads(subprocess.check_output(['git','show',f"{manifest['base_commit']}:{path}"]))
            assert read(ROOT/path) == committed, 'Registry content changed'
            reason = 'Registry JSON content equals preparation base; byte serialization differs'
        else:
            raise AssertionError(f'Frozen source changed: {path}')
        metadata_drift.append(dict(path=path,prepared_sha256=expected_sha,current_sha256=actual_sha,reason=reason))
    rows, health, flags = [], [], []
    ext = previous.rep.ext
    saved_run = ext.RUN
    try:
        ext.RUN = NEXT
        for batch in range(1,6):
            h = read(NEXT/f'checks/batch-{batch:02}.json')
            expected = [t['task_id'] for t in manifest['tasks'] if t['batch'] == batch]
            assert h['task_ids'] == expected and h['status'] == 'pass' and not h['systemic_unresolved']
            assert not h['quarantined_ids']
            health.append({'batch':batch,'tasks':len(expected),'source_status':h['status']})
            for tid in expected:
                entry = entries[tid]
                inp = read(NEXT/f'inputs/tasks/{tid}.json')
                assert sha(NEXT/f'inputs/tasks/{tid}.json') == entry['input_sha256']
                assert inp == read(ROOT/f'data/fipi/2026-10-31-profile/tasks/{tid}.json')
                for asset in inp['assets']:
                    p = NEXT/'inputs'/asset['path']
                    assert sha(p) == asset['sha256']
                    with Image.open(p) as im: im.verify()
                author_path = NEXT/f'raw/author/{tid}.json'
                audit_path = NEXT/f'raw/auditor/{tid}.json'
                a, q = read(author_path), read(audit_path)
                validate_one(a)
                validation = ext.validate_audit(tid,audit_path,author_path=author_path.relative_to(ROOT).as_posix())
                saved = read(NEXT/f'validations/auditor-{tid}.json')['result']
                assert saved['author_sha256'] == validation['author_sha256'] and saved['audit_sha256'] == validation['audit_sha256']
                for role,path in [('author',author_path),('auditor',audit_path)]:
                    execution = read(NEXT/f'executions/{role}-{tid}.json')
                    assert execution['raw_sha256'] == sha(path)
                    assert sha(ROOT/execution['request']['path']) == execution['request']['sha256']
                reasons = []
                if a['solution_status'] != 'solved': reasons.append(a['solution_status'])
                if any(x['blocking'] for x in q['issues']+q['decisions']): reasons.append('blocking_audit_issue')
                for issue in q['issues']:
                    flags.append(dict(task_id=tid, **issue))
                rows.append(dict(entry, layer='audited_new',origin='Opus_next65_published_unmerged',
                    source_run=NEXT.relative_to(ROOT).as_posix(),input=inp,author=a,audit=q,complete=True,
                    included=not reasons,exclusion_reasons=reasons,technical_errors=[],author_mode='standalone_initial',
                    author_path=author_path.relative_to(ROOT).as_posix(),auditor_path=audit_path.relative_to(ROOT).as_posix()))
    finally:
        ext.RUN = saved_run
    prior = data['baseline']+data['new']
    assert len(prior+rows) == len({r['task_id'] for r in prior+rows}) == 315
    return data, rows, health, flags, hashes, protection, metadata_drift


def build():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    data, new, health, flags, hashes, protection, metadata_drift = collect()
    rep = previous.rep
    cohorts = {'baseline100':data['historical'], 'baseline200':data['historical']+data['opus'],
               'saved250':data['historical']+data['sol']+data['opus'],
               'published315':data['historical']+data['sol']+data['opus']+new}
    populations, frequencies = {}, []
    for name,rows in cohorts.items():
        summary,tables = rep.metrics(dict(baseline=data['baseline'],new=rows,catalog=data['catalog']))
        populations[name] = json.loads(json.dumps(summary['mixed_cumulative']))
        frequencies.extend(dict(row,population=name) for row in tables['frequencies'] if row['population']=='mixed_cumulative')
    next_summary,_ = rep.metrics(dict(baseline=[],new=new,catalog=data['catalog']))
    populations['next65'] = next_summary['new_accumulated']
    old = read(previous.TARGET/'summary.json')['populations']
    assert populations['baseline100'] == old['baseline100']
    assert populations['saved250'] == old['cumulative250']
    # Review holdout is not a rewritten auditor decision or expert rejection.
    pending = ['0B2322']
    assert any(i['task_id']=='0B2322' and i['kind']=='math' for i in flags)
    held = copy.deepcopy(cohorts['published315'])
    for row in held:
        if row['task_id'] in pending:
            row['included'] = False
            row['exclusion_reasons'] += ['unresolved_source_reading_review_holdout']
    holdout_summary,_ = rep.metrics(dict(baseline=data['baseline'],new=held,catalog=data['catalog']))
    populations['published315_review_holdout'] = holdout_summary['mixed_cumulative']
    summary = dict(source_commit=COMMIT,source_branch='annotation/bogdan108-fipi-next-100',
        new_pairs=65,prepared_queue=100,not_processed=35,new_batches=health,populations=populations,
        prior100_regression=True,prior250_regression=True,historical_notebook=protection,
        source_review_pending_ids=pending,math_input_flags=[i for i in flags if i['kind'] in ('math','input')],
        preparation_metadata_differences=metadata_drift,
        limitations='Published unmerged source, preliminary annotation; schema/hash/quote checks are not mathematical validation.')
    write(OUT/'summary.json',summary)
    write(OUT/'review-queue.json',dict(unresolved_answer=pending,issues=summary['math_input_flags']))
    records=data['baseline']+cohorts['published315']
    write(OUT/'manifest.json',[{k:r.get(k) for k in ['task_id','origin','source_run','author_path','auditor_path','included','exclusion_reasons']} for r in records])
    for name,rows in [('frequencies.csv',frequencies),('audit-flags.csv',[dict(task_id=i['task_id'],kind=i['kind'],blocking=i['blocking'],description=i['description']) for i in flags])]:
        p=OUT/name
        with p.open('w',encoding='utf-8-sig',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    (OUT/'figures').mkdir(exist_ok=True)
    keys=list(cohorts)
    fig,ax=plt.subplots(figsize=(10,4))
    for shift,key,label in [(-.2,'selected_n','Сохранено'),(.2,'included_n','В частотах')]:
        ax.bar([i+shift for i in range(len(keys))],[populations[k][key] for k in keys],.4,label=label)
    ax.set(xticks=range(4),xticklabels=['Исторические100','+ Богдан100','+ Sol50','+ опубликованные65'],ylabel='Задач')
    ax.legend();fig.tight_layout();fig.savefig(OUT/'figures/progression.png',dpi=140);plt.close(fig)
    statuses=populations['next65']['audit_statuses']
    fig,ax=plt.subplots(figsize=(9,4));names=list(statuses)
    ax.bar(range(len(names)),[statuses[k]['numerator'] for k in names]);ax.set(xticks=range(len(names)),xticklabels=names,ylabel='Локальных кандидатов KC')
    fig.tight_layout();fig.savefig(OUT/'figures/new65-audit.png',dpi=140);plt.close(fig)
    lines=['# Обновление сохранённых данных: 10 ноября','','Исходные 100 и ранее рассчитанный срез 250 воспроизведены без изменения метрик. Первый блок ноутбука и 11 исходных PNG сохранены.','',
           'Найдено 65 новых опубликованных пар Богдана в отдельной ветке; PR с ними не найден. Остальные 35 из его брони не обработаны в этом коммите. Новые решения, аудиты и сбор условий не выполнялись.','',
           '| Срез | Сохранено | В частотах |','|---|---:|---:|']
    for name,value in populations.items():lines.append(f"| {name} | {value['selected_n']} | {value['included_n']} |")
    lines += ['','Пять партий новых 65 прошли локальную повторную проверку схем, буквальных цитат, входов, assets и сохранённых хешей исполнения. Это технические проверки, не предметная экспертиза.','',
              'В 0B2322 источник прямо отмечает неразрешённое расхождение ответов 2/3 по графику. Сохранена основная гармонизированная политика и отдельная чувствительность с временным исключением этой задачи из частот; исходник и вердикт аудитора не переписаны. Остальные математические замечания доступны в review-queue.json.','',
              'Существуют два разных отчёта с именем EDA-250: наш с Sol50 и опубликованный Богданом с первыми 50 следующей брони. Его версия сохранена в отдельном пространстве импорта и не заменила наш результат. Наборы сравниваются по ID и происхождению, а не по названию папки.','',
              'Отличия байтов реестра при одинаковом JSON и изменившегося зеркала бронирования перечислены отдельно в summary.json. Эти состояния координации не подменяют хеши замороженных условий, промптов, авторских ответов и аудитов.','',
              'Следующий содержательный шаг — просмотр отмеченных математических случаев человеком. Согласие агентов и solved не являются экспертным подтверждением; поддержка узлов каталога не равна освоению ученика.']
    (OUT/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    hashes[Path(__file__).relative_to(ROOT).as_posix()]=sha(__file__)
    write(OUT/'provenance.json',dict(input_hashes=hashes,source_commit=COMMIT,model_calls=0))
    print(json.dumps({'selected':315,'harmonized':populations['published315']['included_n'],
        'review_holdout':populations['published315_review_holdout']['included_n'],'new_pairs':65,'original100_preserved':True},ensure_ascii=False))


if __name__ == '__main__':
    build()
