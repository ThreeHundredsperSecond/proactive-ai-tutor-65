"""Offline cumulative historical100 + separate Sol50 checkpoint. No model calls."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import report_fipi_extension as report
import fipi_team_run as team
from collect_fipi_bank import browser_math
from lxml import html as dom

ROOT, RUN, HIST = team.ROOT, team.RUN, team.HIST
TARGET = ROOT/'data/annotation/analyses/2026-11-08-fipi-checkpoint-150-sol-v1'
HIST_ACTIVE = HIST/'active-scopes/first-050-603ec8fe8e05fe2d.json'


def collect(strict=False):
    """Read-only, including active scopes; incomplete series allowed only for smoke."""
    team.verify_frozen()
    saved_run, saved_ext_run, saved_verify = report.RUN, report.ext.RUN, report.ext.verify_frozen
    saved_read = report.read
    def compatible_read(path):
        value = saved_read(path)
        if Path(path).resolve() == (RUN/"active-attempts.json").resolve() and "schema_version" in value:
            return value["tasks"]
        return value
    report.read = compatible_read
    try:
        report.ext.verify_frozen = team.verify_frozen
        report.RUN = report.ext.RUN = HIST
        hist = report.collect(50, strict=True, active_snapshot=HIST_ACTIVE)
        provenance = report.read(HIST/'derived/checkpoint-100-v1/provenance.json')['input_hashes']
        for row in hist['new']:
            if row['task_id'] == 'F416AF':
                assert row['author_mode'] == 'source_reading_feedback'
                assert row['author_path'].replace('\\','/') == 'attempts/author-F416AF-a02.json'
                for role in ('author','auditor'):
                    rel = (HIST/row[role+'_path']).relative_to(ROOT).as_posix()
                    assert hist['input_hashes'][rel] == provenance[rel]
        # Explicit active file prevents report.collect creating an active-scopes file.
        report.RUN = report.ext.RUN = RUN
        latest = report.collect(50, strict=strict, active_snapshot=RUN/'active-attempts.json')
    finally:
        report.RUN, report.ext.RUN, report.ext.verify_frozen = saved_run, saved_ext_run, saved_verify
        report.read = saved_read
    assert hist['catalog'] == latest['catalog'], 'Catalog changed between provenance layers'
    for rows, origin, source in [(hist['baseline'],'historical_editorial50',report.BASE), (hist['new'],'historical_independent50',HIST), (latest['new'],'sol50',RUN)]:
        for row in rows:
            row['origin'] = origin
            row['source_run'] = source.relative_to(ROOT).as_posix()
            inp = row['input']
            row.update(primary_kes=report.ext.meta(inp,'КЭС:')[0].split()[0], response_type=report.ext.meta(inp,'Тип ответа:')[0], images=len(inp['assets']),mathml=inp['mathml_count'])
    merged = dict(hist, new=hist['new']+latest['new'], count=100,
        health_checks={'historical':hist['health_checks'],'sol50':latest['health_checks']},
        technical_errors=hist['technical_errors']+latest['technical_errors'])
    rows = merged['baseline']+merged['new']
    assert len(rows) == len({r['task_id'] for r in rows}) == 150
    hashes = {**hist['input_hashes'], **latest['input_hashes']}
    # Include complete execution/request/check lineage, not only active responses.
    for source in (HIST,RUN):
        for folder in ('executions','requests','attempts','checks'):
            for p in sorted((source/folder).rglob('*')):
                if p.is_file(): hashes[p.relative_to(ROOT).as_posix()] = report.sha(p)
    for p in [Path(__file__), ROOT/'scripts/fipi_team_run.py', HIST/'derived/checkpoint-100-v1/provenance.json', HIST/'derived/checkpoint-100-v1/summary.json']:
        hashes[p.relative_to(ROOT).as_posix()] = report.sha(p)
    merged.update(input_hashes=hashes,input_digest=hashlib.sha256(json.dumps(hashes,sort_keys=True).encode()).hexdigest(),
        active_snapshots={'historical':str(HIST_ACTIVE.relative_to(ROOT)), 'sol50':str((RUN/'active-attempts.json').relative_to(ROOT))})
    return merged


def metrics(data):
    populations, tables = report.metrics(data)
    rename={'baseline50':'historical_editorial50','new_accumulated':'audited100','new_latest50':'latest50','mixed_cumulative':'mixed_cumulative150'}
    result={rename[k]:v for k,v in populations.items()}
    for values in tables.values():
        for row in values:
            if 'population' in row: row['population']=rename[row['population']]
    # Recompute 100 reference from task records using the same metric function.
    ref=dict(data,new=data['new'][:50])
    reference,reference_tables=report.metrics(ref)
    result['baseline100']=reference['mixed_cumulative']
    result['historical_independent50']=reference['new_accumulated']
    for key,values in reference_tables.items():
        tables[key] += [dict(row,population={'mixed_cumulative':'baseline100','new_accumulated':'historical_independent50'}[row['population']]) for row in values if row.get('population') in ('mixed_cumulative','new_accumulated')]
    return result,tables


def smoke():
    data=collect(); summary,tables=metrics(data)
    old=report.read(HIST/'derived/checkpoint-100-v1/summary.json')['populations']['mixed_cumulative']
    assert json.loads(json.dumps(summary['baseline100'])) == old, 'Historical metric regression'
    assert summary['baseline100']['included_n']==98
    assert summary['mixed_cumulative150']['selected_n']==150
    assert summary['audited100']['selected_n']==100
    assert summary['latest50']['selected_n']==50
    assert all(r['task_n']<=r['denominator'] for r in tables['frequencies']+tables['cooccurrence']+tables['transitions'])
    return {'mode':'smoke_only','historical100_reproduced':True,'selected_total':150,'latest_complete_n':summary['latest50']['complete_n'],'latest_included_n':summary['latest50']['included_n'],'checkpoint150_complete':False,'input_digest':data['input_digest']}


def cards(out,data):
    (out/'cards').mkdir()
    assignments=data['catalog']['assignments']
    for row in data['baseline']+data['new']:
        inp=row['input']; tree=dom.fromstring(browser_math(inp['statement_html']))
        for image in tree.xpath('.//img'):
            asset=next(a for a in inp['assets'] if Path(a['path']).name==Path(image.get('src','')).name)
            image.set('src',Path(os.path.relpath(ROOT/row['source_run']/'inputs'/asset['path'],out/'cards')).as_posix())
        body='<a href="../index.html">Сводка</a><h1>'+report.esc(row['task_id'])+'</h1><p>'+report.esc(row['origin'])+'</p><p>Предварительные разборы, внешнего эталона нет.</p><h2>Условие</h2>'+report.esc(inp['instruction'])+dom.tostring(tree,encoding='unicode')
        for label,value in [('Состав и исключения',{k:row.get(k) for k in ('complete','included','exclusion_reasons','author_mode','author_path','auditor_path','feedback_ref','source_run')}),('Буквальный сохранённый разбор: ответ, шаги, KC, методы',row['author']),('Буквальный независимый аудит',row['audit']),('Исторические редакторские назначения',[a for a in assignments if a['task_id']==row['task_id']])]:
            body+='<h2>'+label+'</h2><pre>'+report.esc(json.dumps(value,ensure_ascii=False,indent=2))+'</pre>'
        (out/'cards'/f"{row['task_id']}.html").write_text(report.page(row['task_id'],body),encoding='utf-8')


def build():
    import nbformat
    from nbclient import NotebookClient
    data=collect(strict=True); populations,tables=metrics(data)
    assert not TARGET.exists(), 'Immutable checkpoint exists'
    out=TARGET.with_name(TARGET.name+'.building')
    assert not out.exists(), 'Inspect incomplete build before retry'
    out.mkdir(parents=True); (out/'tables').mkdir(); (out/'figures').mkdir()
    summary={'mode':'checkpoint150','populations':populations,'active_snapshots':data['active_snapshots'],'technical_errors':data['technical_errors'],'health_checks':data['health_checks'],'blocking_issues':[{'task_id':r['task_id'],'issues':[i for i in (r['audit'] or {}).get('issues',[]) if i.get('blocking')],'decisions':[d for d in (r['audit'] or {}).get('decisions',[]) if d.get('blocking')]} for r in data['new'] if 'blocking_audit_issue' in r['exclusion_reasons']], 'denominator_policy':'Composition: selected tasks; frequencies/cooccurrence/transitions: complete solved nonblocking tasks; audit statuses: candidates of technically complete audits. Editorial50 have no independent audit. No accuracy or expert-validation claim.'}
    report.dump(out/'summary.json',summary)
    report.dump(out/'manifest.json',[{k:r.get(k) for k in ('task_id','origin','source_run','author_path','auditor_path','author_mode','feedback_ref','complete','included','exclusion_reasons')} for r in data['baseline']+data['new']])
    for name,rows in tables.items():
        if rows: report.csvout(out/'tables',name+'.csv',rows,list(rows[0]))
    cards(out,data)
    import matplotlib.pyplot as plt
    groups=['baseline100','latest50','mixed_cumulative150']
    fig,ax=plt.subplots(figsize=(10,5))
    for offset,key in enumerate(['selected_n','complete_n','included_n']):
        ax.bar([i+(offset-1)*.25 for i in range(3)],[populations[g][key] for g in groups],.25,label=key)
    ax.set(xticks=range(3),xticklabels=groups,ylabel='Задач'); ax.legend(); fig.tight_layout(); fig.savefig(out/'figures/readiness.png',dpi=150); plt.close(fig)
    fig,ax=plt.subplots(figsize=(10,5))
    for i,g in enumerate(groups):
        freq=sorted([r['task_n'] for r in tables['frequencies'] if r['population']==g],reverse=True)
        ax.plot(range(1,len(freq)+1),freq,label=f"{g}: n={populations[g]['included_n']}")
    ax.set(xlabel='Ранг определения каталога',ylabel='Уникальных задач'); ax.legend(); fig.tight_layout(); fig.savefig(out/'figures/catalog-frequency.png',dpi=150); plt.close(fig)
    lines=['# Накопленный анализ: исторические 100 и Sol50','','Добавлены 50 задач отдельной серии; 100 задач Bogdan108 в этот корпус не входят.','','| Слой | Выбрано | Полных пар / разборов | В частотах | Узлов каталога |','|---|---:|---:|---:|---:|']
    for key,s in populations.items(): lines.append(f"| {key} | {s['selected_n']} | {s['complete_n']} | {s['included_n']} | {s['confirmed_catalog_nodes']} |")
    lines += ['','Знаменатели и все исключения приведены в summary.json и tables/. Исторические редакторские связи и независимые аудиты показаны отдельными слоями. Для исправленного F416AF сохранено происхождение с обратной связью.','','Изменение числа наблюдаемых определений относительно EDA-100: '+str(populations['mixed_cumulative150']['confirmed_catalog_nodes']-populations['baseline100']['confirmed_catalog_nodes'])+'. Это изменение покрытия фиксированного каталога, а не число новых уникальных навыков.','','Отличия могут объясняться составом выборок, моделью и процедурой. solved не означает математическую точность. Аудит агентов не является внешней предметной экспертизой. Новые кандидаты остаются локальными; неполное сопоставление и блокировки не скрыты. Причинный эффект модели, освоение ученика, правильность каталога и зависимости навыков не установлены. Совстречаемость и переходы считаются по задачам; переходы не являются prerequisites.','','[Карточки всех 150 задач](index.html).']
    (out/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    links=''.join('<li><a href="cards/'+r['task_id']+'.html">'+r['task_id']+'</a> '+r['origin']+'</li>' for r in data['baseline']+data['new'])
    (out/'index.html').write_text(report.page('ФИПИ: накопленные 150','<h1>Накопленные 150</h1><a href="report.md">Отчёт</a> · <a href="summary.json">Знаменатели и исключения</a><ul>'+links+'</ul><img src="figures/readiness.png"><img src="figures/catalog-frequency.png">'),encoding='utf-8')
    code="import sys\nfrom pathlib import Path\nroot=next(p for p in (Path.cwd(),*Path.cwd().parents) if (p/'scripts/fipi_team_checkpoint150.py').exists())\nsys.path.insert(0,str(root/'scripts'))\nimport fipi_team_checkpoint150 as checkpoint\ndata=checkpoint.collect(strict=True)\nassert data['input_digest']=="+repr(data['input_digest'])+"\nsummary,tables=checkpoint.metrics(data)\nsummary"
    nb=nbformat.v4.new_notebook(cells=[nbformat.v4.new_markdown_cell('Пересчёт сохранённых данных без модельных запросов.'),nbformat.v4.new_code_cell(code)],metadata={'kernelspec':{'display_name':'Python 3','language':'python','name':'python3'}})
    previous=os.environ.get('PATH',''); os.environ['PATH']=str(ROOT/'.venv/Scripts')+os.pathsep+previous
    try: NotebookClient(nb,timeout=600,startup_timeout=60,resources={'metadata':{'path':str(ROOT)}}).execute()
    finally: os.environ['PATH']=previous
    nbformat.write(nb,out/'review.ipynb')
    report.dump(out/'provenance.json',{'input_hashes':data['input_hashes'],'input_digest':data['input_digest'],'active_snapshots':data['active_snapshots'],'notebook_executed':True,'created_at_utc':team.now(),'method_version':'fipi-extension-v1.1','model_policy':'requested gpt-6.1-sol for latest50; actual metadata only as saved in execution/environment logs'})
    assert all(report.sha(ROOT/p)==h for p,h in data['input_hashes'].items()), 'Inputs changed during build'
    report.dump(out/'output-hashes.json',{p.relative_to(out).as_posix():report.sha(p) for p in out.rglob('*') if p.is_file()})
    out.rename(TARGET)
    return str(TARGET)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('command',choices=['collect','smoke','report']); args=parser.parse_args()
    if args.command=='report': print(build())
    elif args.command=='smoke': print(json.dumps(smoke(),ensure_ascii=False,indent=2))
    else:
        d=collect(); s,_=metrics(d)
        print(json.dumps({'mode':'collection_only','populations':s,'input_digest':d['input_digest']},ensure_ascii=False,indent=2))
