"""Read-only saved-results EDA-250; collect/smoke permit incomplete Sol50, report does not."""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path

import fipi_team_checkpoint150 as sol
import fipi_checkpoint200 as opus

rep = sol.report
ROOT = sol.ROOT
TARGET = ROOT / 'data/annotation/analyses/2026-11-09-fipi-checkpoint-250-v1'
IMPORT_COMMIT = 'b8ad4499777b52c9878241268c62dea1a246c91c'
POPULATIONS = {
    'historical_editorial50': 'Редакторские 50',
    'historical_independent50': 'Исторические независимые 50',
    'Sol50': 'Sol50', 'Opus100': 'Opus100',
    'Opus_default15': 'Opus: по умолчанию (15)',
    'Opus_low85': 'Opus: effort low (85)',
    'baseline100': 'Исторические 100',
    'baseline200': 'Исторические 100 + Opus100',
    'new200': 'Все независимые новые 200',
    'cumulative250': 'Смешанные 250',
}


def collect(strict=False):
    """Reuse source collectors without writes or changing source inclusion policy."""
    data = sol.collect(strict=strict)
    if strict:
        assert len(data['health_checks']['sol50']) == 4
        for check in data['health_checks']['sol50']:
            health = rep.read(sol.RUN/check['path'])
            assert health['status'] == 'pass' and not health.get('quarantined_ids'), 'Sol health must pass without quarantine'
    paths = set()
    team, health, manifest = opus.collect_team(paths)
    for row in team:
        row.update(origin='Opus100', source_run=opus.TEAM.relative_to(ROOT).as_posix())
    data['sol'] = data['new'][50:]
    data['historical'] = data['new'][:50]
    data['opus'] = team
    data['new'] += team
    data.update(count=200, opus_health=health, opus_manifest=manifest)
    all_rows = data['baseline'] + data['new']
    assert len(all_rows) == len({r['task_id'] for r in all_rows}) == 250
    for r in all_rows:
        r['source_policy_included'] = r['included']
        r['source_policy_exclusion_reasons'] = list(r['exclusion_reasons'])
        # Preserve historical editorial exclusions, and apply one common solved gate.
        reasons = list(r['exclusion_reasons'])
        status = (r.get('author') or {}).get('solution_status')
        if status != 'solved' and status and not reasons:
            reasons.append(status)
        if not r['complete'] and not reasons:
            reasons.append('incomplete')
        audit = r.get('audit') or {}
        if any(x.get('blocking') for k in ('issues', 'decisions') for x in audit.get(k, [])):
            if 'blocking_audit_issue' not in reasons:
                reasons.append('blocking_audit_issue')
        r['included'] = r['complete'] and not reasons
        r['exclusion_reasons'] = reasons
    hashes = data['input_hashes']
    # Hash the complete saved lineage, including methodology and execution metadata.
    # This does not parse inactive invalid author JSON or use it as an analysis input.
    for source in (sol.RUN, opus.TEAM):
        lineage_folders = {'inputs', 'requests', 'raw', 'attempts', 'executions', 'checks', 'code'}
        paths.update(p.resolve() for p in source.rglob('*') if p.is_file()
                     and p.relative_to(source).parts[0] in lineage_folders)
    paths.update(p.resolve() for p in (ROOT/'data/annotation/team/imports').glob('2026-11-09-bogdan-pr5*.json'))
    for name in ('fipi_team_checkpoint250.py', 'fipi_checkpoint200.py', 'fipi_team_checkpoint150.py',
                 'report_fipi_extension.py', 'fipi_extension.py', 'archive_support.py', 'fipi_eda50.py'):
        paths.add((ROOT/'scripts'/name).resolve())
    for p in sorted(paths):
        hashes[p.relative_to(ROOT).as_posix()] = rep.sha(p)
    data['input_digest'] = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
    data['strict'] = strict
    corrected = next(r for r in data['sol'] if r['task_id'] == '9c96c5')
    assert corrected['author_path'].replace('\\', '/') == 'attempts/author-9c96c5-a02.json'
    accepted = next(r for r in team if r['task_id'] == '321FCD')
    assert accepted['source_policy_included'] and not accepted['included']
    assert accepted['author']['solution_status'] == 'partial'
    return data


def metrics(data, policy='harmonized'):
    """Recompute all populations from task records with historical metric definitions."""
    assert policy in ('harmonized', 'source_policy')
    if policy == 'source_policy':
        data = copy.deepcopy(data)
        for row in data['baseline'] + data['new']:
            row['included'] = row['source_policy_included']
            row['exclusion_reasons'] = row['source_policy_exclusion_reasons']
    h, s, o = data['historical'], data['sol'], data['opus']
    default = [r for r in o if 'effort=low' not in (r.get('model_requested') or '')]
    low = [r for r in o if 'effort=low' in (r.get('model_requested') or '')]
    assert len(default) == 15 and len(low) == 85, 'Execution metadata effort partition changed'
    calls = {
        'historical_editorial50': (h, 'baseline50'),
        'historical_independent50': (h, 'new_accumulated'),
        'Sol50': (s, 'new_accumulated'), 'Opus100': (o, 'new_accumulated'),
        'Opus_default15': (default, 'new_accumulated'), 'Opus_low85': (low, 'new_accumulated'),
        'baseline100': (h, 'mixed_cumulative'), 'baseline200': (h + o, 'mixed_cumulative'),
        'new200': (h + s + o, 'new_accumulated'), 'cumulative250': (h + s + o, 'mixed_cumulative'),
    }
    cache, summary, tables = {}, {}, {}
    for pop, (rows, key) in calls.items():
        ids = tuple(r['task_id'] for r in rows)
        if ids not in cache:
            cache[ids] = rep.metrics(dict(data, new=rows))
        sm, tb = cache[ids]
        summary[pop] = sm[key]
        for name, values in tb.items():
            if name != 'candidates':
                tables.setdefault(name, []).extend(dict(r, population=pop) for r in values if r.get('population') == key)
    tables['candidates'] = cache[tuple(r['task_id'] for r in h+s+o)][1]['candidates']
    lookup = {r['task_id']: r for r in data['baseline'] + data['new']}
    for name in ('tasks', 'candidates'):
        for row in tables[name]:
            source = lookup[row['task_id']]
            row.update(origin=source['origin'], batch=source.get('batch'),
                       model_requested=source.get('model_requested'),
                       source_policy_included=source['source_policy_included'])
    return summary, tables


def smoke(data=None):
    data = data or collect()
    summary, tables = metrics(data)
    source, _ = metrics(data, 'source_policy')
    old = rep.read(sol.HIST/'derived/checkpoint-100-v1/summary.json')['populations']['mixed_cumulative']
    assert json.loads(json.dumps(summary['baseline100'])) == old
    import csv
    saved_freq = list(csv.DictReader(open(sol.HIST/'derived/checkpoint-100-v1/frequencies.csv',encoding='utf-8-sig')))
    expected = [{k:str(v) for k,v in r.items()} for r in tables['frequencies'] if r['population']=='baseline100']
    for r in expected:
        r['population']='mixed_cumulative'
    assert [r for r in saved_freq if r['population']=='mixed_cumulative'] == expected
    saved200 = ROOT/opus.DEFAULT_OUT/'summary.json'
    if saved200.is_file():
        assert json.loads(json.dumps(source['baseline200'])) == rep.read(saved200)['populations']['mixed_cumulative200']
    assert summary['baseline100']['included_n'] == 98
    assert summary['cumulative250']['selected_n'] == 250
    assert source['Opus100']['included_n'] == 100 and summary['Opus100']['included_n'] == 99
    assert source['cumulative250']['included_n'] == summary['cumulative250']['included_n'] + 1
    for name in ('frequencies', 'cooccurrence', 'transitions'):
        assert all(0 <= r['task_n'] <= r['denominator'] for r in tables[name])
    return dict(mode='strict_complete' if data['strict'] else 'smoke_incomplete_permitted',
                historical100_reproduced=True, unique_selected=250,
                sol_complete_n=summary['Sol50']['complete_n'], sol_included_n=summary['Sol50']['included_n'],
                harmonized_included_n=summary['cumulative250']['included_n'],
                source_policy_included_n=source['cumulative250']['included_n'], input_digest=data['input_digest'])


def cards(out, data):
    # The historical collector already resolves source_run and active attempt paths.
    sol.cards(out, data)
    for row in data['baseline'] + data['new']:
        path = out/'cards'/f"{row['task_id']}.html"
        body = path.read_text(encoding='utf-8')
        refs = []
        for role in ('author', 'auditor'):
            rel = row.get(role+'_path')
            if role == 'author' and not rel and row['origin'] == 'historical_editorial50':
                rel = row['source_run']+'/raw/'+row['task_id']+'.json'
            if rel:
                p = ROOT/rel
                if not p.is_file():
                    p = ROOT/row['source_run']/rel
                assert p.is_file(), p
                refs.append('<a href="'+Path(os.path.relpath(p, path.parent)).as_posix()+'">'+role+' raw</a>')
        if row.get('accepted_after_review'):
            refs.append('<a href="'+Path(os.path.relpath(ROOT/row['accepted_after_review'], path.parent)).as_posix()+'">source review</a>')
        extra = '<p>'+ ' · '.join(refs) + '</p><pre>'+rep.esc(json.dumps({k:row[k] for k in ('included','exclusion_reasons','source_policy_included','source_policy_exclusion_reasons')},ensure_ascii=False,indent=2))+'</pre>'
        path.write_text(body.replace('</html>', extra+'</html>'), encoding='utf-8')


def figures(out, summary, tables):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    (out/'figures').mkdir()
    groups = ['historical_editorial50','historical_independent50','Sol50','Opus100']
    fig, ax = plt.subplots(figsize=(11,5))
    for j, key in enumerate(('selected_n','complete_n','included_n')):
        ax.bar([i+(j-1)*.25 for i in range(4)],[summary[g][key] for g in groups],.25,label=key)
    ax.set(xticks=range(4),xticklabels=groups,ylabel='Задач'); ax.legend()
    fig.tight_layout(); fig.savefig(out/'figures/readiness.png',dpi=150); plt.close(fig)
    fig, ax = plt.subplots(figsize=(10,5))
    for g in ('baseline100','baseline200','cumulative250'):
        vals=sorted([r['task_n'] for r in tables['frequencies'] if r['population']==g],reverse=True)
        ax.plot(range(1,len(vals)+1),vals,label=f"{g}: n={summary[g]['included_n']}")
    ax.set(xlabel='Ранг определения каталога',ylabel='Уникальных задач'); ax.legend()
    fig.tight_layout(); fig.savefig(out/'figures/catalog-frequency.png',dpi=150); plt.close(fig)


def notebook(out, digest):
    import nbformat
    from nbclient import NotebookClient
    code = "import sys\nfrom pathlib import Path\nroot=next(p for p in (Path.cwd(),*Path.cwd().parents) if (p/'scripts/fipi_team_checkpoint250.py').exists())\nsys.path.insert(0,str(root/'scripts'))\nimport fipi_team_checkpoint250 as cp\ndata=cp.collect(strict=True)\nassert data['input_digest']=="+repr(digest)+"\nsummary,tables=cp.metrics(data)\ncp.smoke(data), summary"
    nb=nbformat.v4.new_notebook(cells=[nbformat.v4.new_markdown_cell('Офлайн-пересчёт сохранённых 250 записей. Основная политика harmonized; отдельная source_policy сохраняет исходное принятие 321FCD.'),nbformat.v4.new_code_cell(code)],metadata={'kernelspec':{'display_name':'Python 3','language':'python','name':'python3'}})
    prev=os.environ.get('PATH',''); os.environ['PATH']=str(ROOT/'.venv/Scripts')+os.pathsep+prev
    try:
        NotebookClient(nb,timeout=600,startup_timeout=60,resources={'metadata':{'path':str(ROOT)}}).execute()
    finally:
        os.environ['PATH']=prev
    nbformat.write(nb,out/'review.ipynb')


def build():
    data=collect(strict=True)
    checks=smoke(data)
    summary,tables=metrics(data); source,source_tables=metrics(data,'source_policy')
    assert summary['Sol50']['complete_n']==50
    assert len(data['health_checks']['sol50'])==4 and all(c['valid'] for c in data['health_checks']['sol50'])
    assert not TARGET.exists(), 'Immutable checkpoint exists'
    out=TARGET.with_name(TARGET.name+'.building')
    assert not out.exists(), 'Inspect incomplete build before retry'
    out.mkdir(parents=True); (out/'tables').mkdir(); (out/'source-policy-tables').mkdir()
    for folder, group in [('tables',tables),('source-policy-tables',source_tables)]:
        for name,rows in group.items():
            if rows:
                fields=list(dict.fromkeys(k for r in rows for k in r))
                rep.csvout(out/folder,name+'.csv',rows,fields)
    rep.dump(out/'summary.json',dict(mode='checkpoint250',populations=summary,source_policy=source,self_checks=checks,
        harmonized_policy='Historical editorial review gate preserved; complete solved nonblocking required. 321FCD excluded because raw status is partial.',
        source_policy_definition='Original per-source inclusion decisions, including accepted_after_review 321FCD.',
        health_checks=data['health_checks'],opus_health=data['opus_health']))
    rep.dump(out/'manifest.json',[{k:r.get(k) for k in ('task_id','origin','source_run','author_path','auditor_path','author_mode','feedback_ref','included','exclusion_reasons','source_policy_included','source_policy_exclusion_reasons')} for r in data['baseline']+data['new']])
    cards(out,data); figures(out,summary,tables)
    lines=['# Накопленный анализ 250 задач','','Сохранённые исторические 100, отдельная серия Sol50 и 100 задач Bogdan108 (Opus). Частоты пересчитаны по записям задач, готовые таблицы не суммируются.','','| Слой | Выбрано | Полных | В частотах | Узлов каталога |','|---|---:|---:|---:|---:|']
    for key,s in summary.items():
        lines.append(f"| {POPULATIONS[key]} | {s['selected_n']} | {s['complete_n']} | {s['included_n']} | {s['confirmed_catalog_nodes']} |")
    lines += ['', 'Основная политика harmonized требует полного технически валидного разбора, solved и отсутствия блокировок. Исторические редакторские исключения сохраняются. eFF32e (partial) и C41083 (блокирующий аудит) остаются исключёнными. В Opus100 исходно приняты 100, но 321FCD имеет raw status partial: в harmonized включены 99. Исходное принятие после просмотра не менялось; отдельные source_policy и source-policy-tables/ показывают его влияние на каждую популяцию.', '',
        'Редакторские 50 не имеют независимого аудита. Остальные три слоя имеют агентный аудит. В Opus100 по сохранённым executions 15 задач выполнены с уровнем рассуждений по умолчанию, 85 с effort low. Для Sol 9c96c5 используется активная технически исправленная попытка author-9c96c5-a02, для исторического F416AF — попытка с обратной связью. Исходные данные и методика зафиксированы хешами.', '',
        'Состав описывается по всем выбранным задачам; частоты KC, совместная встречаемость и переходы — по включённым задачам; статусы аудитора — по кандидатам технически полных аудитов. Все знаменатели, исключения и структура доступны в summary.json и таблицах. Каталог фиксирован: прирост покрытия его узлов не равен числу новых навыков. Локальные new_candidate не консолидированы между задачами.', '',
        'Разборы и аудит предварительны, внешнего эталона и экспертной валидации нет. solved не означает точность решения или освоение учеником. Различия слоёв смешивают состав задач, исполнителей, модель, effort и процедуру; причинный эффект модели не установлен. Совместная встречаемость и переходы не доказывают зависимости навыков или порядок изучения.', '',
        '[Карточки всех 250 задач](index.html) · [исполненный пересчёт](review.ipynb) · [происхождение](provenance.json).']
    (out/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    links=''.join(f'<li><a href="cards/{r["task_id"]}.html">{r["task_id"]}</a> {r["origin"]}</li>' for r in data['baseline']+data['new'])
    (out/'index.html').write_text(rep.page('EDA-250','<h1>Накопленные 250</h1><a href="report.md">Отчёт</a> · <a href="summary.json">Знаменатели</a><ul>'+links+'</ul><img src="figures/readiness.png"><img src="figures/catalog-frequency.png">'),encoding='utf-8')
    snapshot=out/'code/checkpoint250-v1'; snapshot.mkdir(parents=True)
    for rel in data['input_hashes']:
        if rel.startswith('scripts/') and rel.endswith('.py'):
            (snapshot/Path(rel).name).write_bytes((ROOT/rel).read_bytes())
    notebook(out,data['input_digest'])
    assert all(rep.sha(ROOT/p)==h for p,h in data['input_hashes'].items()), 'Inputs changed during build'
    rep.dump(out/'provenance.json',dict(input_hashes=data['input_hashes'],input_digest=data['input_digest'],active_snapshots=data['active_snapshots'],
        import_commit=IMPORT_COMMIT,import_mode='git archive of PR5 added files; no merge into worktree',notebook_executed=True,
        method_version='report_fipi_extension.metrics unchanged; harmonized solved gate',code_snapshot='code/checkpoint250-v1',
        inactive_lineage='Inactive attempts are hashed for traceability, not parsed or selected as analysis records.'))
    rep.dump(out/'output-hashes.json',{p.relative_to(out).as_posix():rep.sha(p) for p in out.rglob('*') if p.is_file()})
    out.rename(TARGET)
    return str(TARGET)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('command',choices=['collect','smoke','report'])
    args=p.parse_args()
    if args.command=='report':
        print(build())
    else:
        data=collect()
        result=smoke(data)
        if args.command=='collect':
            result['populations']=metrics(data)[0]
        print(json.dumps(result,ensure_ascii=False,indent=2))
