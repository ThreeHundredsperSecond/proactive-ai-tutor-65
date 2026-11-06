"""Saved-data analysis; pilot gate before expansion. No model calls or network."""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import csv
import hashlib
import html
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import textwrap

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
from lxml import html as dom

import report_fipi_extension as report
from collect_fipi_bank import browser_math

ROOT=Path(__file__).resolve().parents[1]
EXT=ROOT/'data/annotation/runs/2026-11-02-fipi-extension-150'
BASE=ROOT/'data/annotation/runs/2026-10-31-fipi-50x1'
OUT=ROOT/'data/annotation/analyses/2026-11-04-data-to-tutor-v1'
PROTOCOL=ROOT/'docs/eda/05-analysis/data-to-tutor-protocol.md'
SNAP=EXT/'active-scopes/first-050-603ec8fe8e05fe2d.json'
LAYERS=['historical_editorial','audited_new']
LABELS={'historical_editorial':'Исходные: редакторские связи','audited_new':'Новые: независимый аудит'}
COLORS={'historical_editorial':'#087e8b','audited_new':'#aa6b25'}


def read(p): return json.loads(Path(p).read_text(encoding='utf-8'))
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def dump(p,v):
    Path(p).parent.mkdir(parents=True,exist_ok=True)
    Path(p).write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def rel(p,parent=OUT): return os.path.relpath(p,parent).replace('\\','/')
def esc(s): return html.escape(str(s))
def link(p,label,parent=OUT): return f'<a href="{esc(rel(p,parent))}">{esc(label)}</a>'
def csvout(name,rows):
    rows=list(rows)
    if not rows:return
    with (OUT/'tables'/f'{name}.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def page(title,body):
    return '<!doctype html><html lang="ru"><meta charset="utf-8"><title>'+esc(title)+'</title><style>body{font:17px/1.55 system-ui;color:#203844;max-width:1250px;margin:30px auto;padding:0 22px}img{max-width:100%;height:auto}table{border-collapse:collapse;width:100%;margin:20px 0}td,th{border:1px solid #ccd8df;padding:8px;vertical-align:top}th{background:#edf3f6}a{color:#087080}pre{white-space:pre-wrap}.warn{padding:12px;background:#fff2d7}section{margin:32px 0}math{font-size:1.2em}</style>'+body+'</html>'
def htable(rows):
    rows=list(rows)
    if not rows:return '<p>Нет наблюдений.</p>'
    keys=list(rows[0]);return '<table><tr>'+''.join('<th>'+esc(k)+'</th>' for k in keys)+'</tr>'+''.join('<tr>'+''.join('<td>'+esc(r[k])+'</td>' for k in keys)+'</tr>' for r in rows)+'</table>'
def savefig(name):
    plt.tight_layout();plt.savefig(OUT/'figures'/f'{name}.png',dpi=150,bbox_inches='tight');plt.close()
def freeze(p,b):
    if p.exists():assert p.read_bytes()==b,f'Frozen input changed: {p}'
    else:p.write_bytes(b)


def load():
    data=report.collect(50,strict=True,active_snapshot=SNAP)
    summary,tables=report.metrics(data)
    assert json.loads(json.dumps(summary))==read(EXT/'derived/checkpoint-100-v1/summary.json')['populations']
    assert not data['technical_errors']
    rows=data['baseline']+data['new'];assert len({r['task_id'] for r in rows})==100
    included=[r for r in rows if r['included']];assert len(included)==98
    assignments={(a['task_id'],a['local_id']):a['canonical_id'] for a in data['catalog']['assignments']}
    for r in rows:r['mapping']=report.mapping(r,assignments)
    return data,rows,summary,tables


def select_display(rows):
    def pick(layer,n):
        pool=sorted([r for r in rows if r['layer']==layer],key=lambda r:r['task_id'])
        first=[];seen=set()
        for r in pool:
            key=(r['primary_kes'],r['response_type'])
            if key not in seen:first.append(r);seen.add(key)
        ranked=first+[r for r in pool if r not in first]
        return ranked[:n]
    selected=pick(LAYERS[0],6)+pick(LAYERS[1],6)
    remaining=12-len(selected)
    if remaining:
        selected+=sorted([r for r in rows if r not in selected],key=lambda r:r['task_id'])[:remaining]
    return selected


def derive(data,rows):
    included=[r for r in rows if r['included']]
    names={r['id']:r['name'] for r in data['catalog']['nodes']}
    edges=[];chains=[];profiles=[]
    for r in rows:
        tid=r['task_id'];m=r['mapping'];a=r['author'];src=BASE if r['layer']==LAYERS[0] else EXT
        author=src/('raw/'+tid+'.json' if r['layer']==LAYERS[0] else r['author_path'])
        audit=src/('catalog-decisions.json' if r['layer']==LAYERS[0] else r['auditor_path'])
        r['author_file']=author;r['audit_file']=audit
        unm=len(a['kc_candidates'])-len(m)
        profiles.append(dict(task_id=tid,layer=r['layer'],included=r['included'],local_candidates=len(a['kc_candidates']),
            matched_candidates=len(m),unmatched=unm,completeness='all' if unm==0 else 'none' if not m else 'some',
            source_issues=json.dumps(r['input']['source_issues'],ensure_ascii=False),solution_status=a['solution_status'],
            blocking=bool(r['audit'] and any(x.get('blocking') for x in r['audit']['issues']+r['audit']['decisions'])),
            author_mode=r['author_mode'],exclusion_reasons=';'.join(r['exclusion_reasons'])))
        steps={s['id']:s for s in a['steps']}
        for method in a['methods']:
            for order,sid in enumerate(method['step_ids'],1):
                s=steps[sid]
                chains.append(dict(task_id=tid,layer=r['layer'],included=r['included'],method_id=method['id'],order=order,step_id=sid,
                    action=s['action'],result=s['result'],input_refs=json.dumps(s['input_refs'],ensure_ascii=False),
                    local_ids=';'.join(s['kc_ids']),catalog_ids=';'.join(sorted({m[k] for k in s['kc_ids'] if k in m})),
                    unmatched_ids=';'.join(k for k in s['kc_ids'] if k not in m),author_path=rel(author,ROOT),audit_path=rel(audit,ROOT)))
        if not r['included']:continue
        for cid in sorted(set(m.values())):
            local=[k for k,v in m.items() if v==cid]
            stepids=[s['id'] for s in a['steps'] if set(s['kc_ids'])&set(local)]
            edges.append(dict(task_id=tid,catalog_id=cid,name=names[cid],layer=r['layer'],first_kes=r['primary_kes'],response_type=r['response_type'],
                all_kes=json.dumps(report.ext.meta(r['input'],'КЭС:'),ensure_ascii=False),local_ids=';'.join(local),step_ids=';'.join(stepids),
                author_path=rel(author,ROOT),mapping_path=rel(audit,ROOT)))
    assert len({(e['task_id'],e['catalog_id']) for e in edges})==len(edges)
    bykc=defaultdict(list)
    for e in edges:bykc[e['catalog_id']].append(e)
    eligible=[cid for cid,es in bykc.items() if len(es)>=3 and {e['layer'] for e in es}==set(LAYERS) and cid!='linear_equation']
    foci=['linear_equation']+sorted(eligible,key=lambda cid:(-len(bykc[cid]),cid))[:2]
    stats=[]
    for cid,es in sorted(bykc.items()):
        for layer in LAYERS+['mixed']:
            ee=[e for e in es if layer=='mixed' or e['layer']==layer]
            stats.append(dict(catalog_id=cid,name=names[cid],layer=layer,tasks=len(ee),denominator=98 if layer=='mixed' else 49,
                first_kes_n=len({e['first_kes'] for e in ee}),first_kes=';'.join(sorted({e['first_kes'] for e in ee})),
                short=sum(e['response_type']=='Краткий ответ' for e in ee),extended=sum(e['response_type']!='Краткий ответ' for e in ee)))
    return names,edges,chains,profiles,foci,stats


def graph(cid,shown,names,total):
    fig,ax=plt.subplots(figsize=(13,6.5));ax.set_xlim(-.05,1.05);ax.set_ylim(-.13,1.12);ax.axis('off')
    for x,layer in [(0.01,LAYERS[0]),(.70,LAYERS[1])]:
        rr=[r for r in shown if r['layer']==layer]
        ax.text(x+.14,1.08,LABELS[layer],ha='center',fontsize=10,color=COLORS[layer],weight='bold')
        for i,r in enumerate(rr):
            y=.96-i*(.90/max(len(rr)-1,1))
            ax.plot([.5,x+.14],[.5,y],color=COLORS[layer],alpha=.45,zorder=1)
            ax.add_patch(FancyBboxPatch((x,y-.045),.28,.09,boxstyle='round,pad=.008',facecolor='white',edgecolor=COLORS[layer],zorder=2))
            typ='краткий' if r['response_type']=='Краткий ответ' else 'развёрнутый'
            ax.text(x+.14,y,r['task_id']+'\nКЭС '+r['primary_kes']+' · '+typ,ha='center',va='center',fontsize=9,zorder=3)
    ax.text(.5,.5,textwrap.fill(names[cid],23),ha='center',va='center',fontsize=11,weight='bold',
            bbox=dict(boxstyle='round,pad=.7',facecolor='#edf3f6',edgecolor='#456'),zorder=4)
    ax.text(.5,-.11,f'Показано {len(shown)} из {total} задач с принятой связью. Цвет — происхождение, линия — назначение KC.\nКЭС — метка банка. Связи не устанавливают освоение или пригодность учебного эталона.',ha='center',fontsize=9)
    ax.set_title('Один KC — разные задачи: '+cid,fontsize=12,pad=20)
    savefig('graph-'+cid)


def chain_picture(r,names):
    a=r['author'];steps={s['id']:s for s in a['steps']};n=sum(len(m['step_ids'])+1 for m in a['methods'])
    fig,ax=plt.subplots(figsize=(13,max(4,n*1.05)));ax.axis('off');ax.set_xlim(0,1);ax.set_ylim(0,n)
    y=n-.3
    for method in a['methods']:
        ax.text(.02,y,method['id']+' · '+method['name'],fontsize=11,weight='bold');y-=.85
        for i,sid in enumerate(method['step_ids']):
            s=steps[sid];cids=sorted({r['mapping'][k] for k in s['kc_ids'] if k in r['mapping']})
            missing=[k for k in s['kc_ids'] if k not in r['mapping']]
            txt=sid+' | '+textwrap.shorten(s['action'],width=145,placeholder='…')+'\n'+textwrap.shorten('Результат: '+s['result'],width=150,placeholder='…')
            txt+='\nKC: '+textwrap.shorten('; '.join(names[c] for c in cids) or 'нет принятого назначения',width=140,placeholder='…')
            if missing:txt+=' | без назначения: '+','.join(missing)
            ax.text(.04,y,textwrap.fill(txt.split('\n')[0],145)+'\n'+'\n'.join(txt.split('\n')[1:]),va='center',fontsize=8.5,
                bbox=dict(boxstyle='round,pad=.45',facecolor='#fff2d7' if missing else '#edf6f6',edgecolor='#c4d2d5'))
            if i<len(method['step_ids'])-1:ax.annotate('',xy=(.015,y-.72),xytext=(.015,y-.2),arrowprops=dict(arrowstyle='->',color='#456'))
            y-=1
    ax.set_title(r['task_id']+' · '+LABELS[r['layer']]+'\nСохранённые шаги; сокращённые подписи, полный текст — в карточке',fontsize=12,pad=16)
    savefig('chain-'+r['task_id'])


def card(r,names,inputs):
    tid=r['task_id'];dest=OUT/'cards';src=(BASE if r['layer']==LAYERS[0] else EXT)/'inputs'
    tree=dom.fromstring(browser_math(r['input']['statement_html']))
    assets={Path(a['path']).name:a for a in r['input']['assets']}
    for im in tree.xpath('.//img'):
        asset=assets[Path(im.get('src')).name];p=src/asset['path'];assert sha(p)==asset['sha256']
        inputs[p.relative_to(ROOT).as_posix()]=sha(p);im.set('src',rel(p,dest))
    body='<nav><a href="../index.html">Обзор</a></nav><h1>'+tid+'</h1><p>'+esc(LABELS[r['layer']])+'</p>'
    body+='<p class="warn">Предварительный разбор; не официальный эталон. '+esc('; '.join(r['exclusion_reasons']))+'</p>'
    body+='<h2>Условие</h2>'+dom.tostring(tree,encoding='unicode')
    body+='<p>'+esc('; '.join(report.ext.meta(r['input'],'КЭС:')))+'</p>'
    body+='<p>'+link(r['author_file'],'Исходный разбор',dest)+' · '+link(r['audit_file'],'Основание назначений / аудит',dest)+'</p>'
    body+='<h2>Шаги решения: полный сохранённый текст</h2>'+htable([{'ID':s['id'],'Действие':s['action'],'Результат':s['result'],
        'Входные ссылки':'; '.join(s['input_refs']),'KC (группа, без порядка)':'; '.join(k+' → '+(r['mapping'].get(k,'НЕТ ПОЛНОГО НАЗНАЧЕНИЯ')) for k in s['kc_ids'])} for s in r['author']['steps']])
    body+='<h2>Маршруты отдельно</h2>'+htable([{'Method':m['id'],'Название':m['name'],'Шаги':' → '.join(m['step_ids'])} for m in r['author']['methods']])
    if r['audit']:body+='<h2>Сохранённые решения аудитора</h2>'+htable([{'Кандидат':d['local_kc_id'],'Статус':d['status'],'Обоснование':d['rationale']} for d in r['audit']['decisions']])
    body+='<h2>Локальные определения</h2>'+htable([{'ID':k['id'],'Название':k['name'],'Описание':k['description']} for k in r['author']['kc_candidates']])
    (dest/f'{tid}.html').write_text(page(tid,body),encoding='utf-8')


def adjacent(rows,cid):
    pairs=defaultdict(set);missing=set();allids=set()
    for r in rows:
        if not r['included'] or cid not in r['mapping'].values():continue
        tid=r['task_id'];allids.add(tid);steps={s['id']:s for s in r['author']['steps']};m=r['mapping']
        for method in r['author']['methods']:
            for x,y in zip(method['step_ids'],method['step_ids'][1:]):
                aa,bb=steps[x]['kc_ids'],steps[y]['kc_ids'];an={m[k] for k in aa if k in m};bn={m[k] for k in bb if k in m}
                if cid in an or cid in bn:
                    if (cid in an and any(k not in m for k in bb)) or (cid in bn and any(k not in m for k in aa)):
                        missing.add(tid)
                    for a in an:
                        for b in bn:
                            if a!=b and cid in (a,b):pairs[(a,b)].add(tid)
    return [dict(from_kc=a,to_kc=b,tasks=len(ids),task_ids=';'.join(sorted(ids)),denominator=len(allids)) for (a,b),ids in sorted(pairs.items())],sorted(missing)


def execute(phase):
    for name in ['tables','figures','cards','checks']:(OUT/name).mkdir(parents=True,exist_ok=True)
    freeze(OUT/'PROTOCOL.md',PROTOCOL.read_bytes())
    data,rows,summary,oldtables=load();names,edges,chains,profiles,foci,stats=derive(data,rows)
    byid={r['task_id']:r for r in rows};inputs=dict(data['input_hashes'])
    for p in [ROOT/'data/fipi/2026-10-31-profile/tasks.jsonl',PROTOCOL,Path(__file__),EXT/'derived/checkpoint-100-v1/summary.json']:
        inputs[p.relative_to(ROOT).as_posix()]=sha(p)
    current=read(OUT/'manifest.json') if (OUT/'manifest.json').exists() else {}
    started=current.get('started_at',datetime.now(timezone.utc).isoformat())
    manifest=dict(started_at=started,git_sha=current.get('git_sha',subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT).decode().strip()),
        protocol_sha256=sha(PROTOCOL),input_digest=data['input_digest'],foci=foci,all_task_ids=[r['task_id'] for r in rows],
        included_task_ids=[r['task_id'] for r in rows if r['included']],exclusions=[p for p in profiles if not p['included']],
        selection_rule='Fixed linear_equation + up to two nodes >=3 tasks in both layers, degree descending then ID; shown cap12, 6/layer then fill, first per stratum by task ID then remaining IDs',
        layout='Fixed left/right coordinates; no random layout',shown={},focus_task_ids={},chain_task_ids=[],phase=phase)
    targets=foci[:1] if phase=='pilot' else foci
    if phase=='complete':
        approved=read(OUT/'checks/pilot-visual-review.json')
        assert approved['passed'] is True
        assert approved['script_sha256']==sha(Path(__file__))
        for path,h in approved['reviewed_hashes'].items():assert sha(OUT/path)==h,path
    checks=[]
    for cid in targets:
        linked=[r for r in rows if r['included'] and cid in r['mapping'].values()]
        shown=select_display(linked);manifest['shown'][cid]=[r['task_id'] for r in shown];manifest['focus_task_ids'][cid]=[r['task_id'] for r in linked]
        graph(cid,shown,names,len(linked))
        for r in shown:
            card(r,names,inputs)
            assert any(e['task_id']==r['task_id'] and e['catalog_id']==cid for e in edges)
            checks.append(dict(focus=cid,task_id=r['task_id'],edge_exists=True,step_ids=[s['id'] for s in r['author']['steps'] if any(r['mapping'].get(k)==cid for k in s['kc_ids'])]))
    focus=[byid[tid] for tid in manifest['focus_task_ids'][foci[0]]]
    picked=[]
    for predicate,limit in [(lambda r:r['layer']==LAYERS[0],1),(lambda r:r['layer']==LAYERS[1],1),
                            (lambda r:r['layer']==LAYERS[1] and len(r['mapping'])<len(r['author']['kc_candidates']),2)]:
        eligible=sorted([r for r in focus if predicate(r) and r not in picked],key=lambda r:r['task_id'])[:limit];picked+=eligible
    for r in picked:card(r,names,inputs);chain_picture(r,names)
    manifest['chain_task_ids']=[r['task_id'] for r in picked]
    transitions,missing=adjacent(rows,'linear_equation')
    manifest['focus_tasks_with_incomplete_adjacent_step']=missing
    completeness=[]
    for layer in LAYERS:
        pp=[p for p in profiles if p['layer']==layer and p['included']]
        for status in ['all','some','none']:completeness.append(dict(layer=layer,status=status,tasks=sum(p['completeness']==status for p in pp),denominator=len(pp)))
    status_table=[]
    for population,subset in [('all_new',[r for r in rows if r['layer']==LAYERS[1]]),
                              ('included_new',[r for r in rows if r['layer']==LAYERS[1] and r['included']])]:
        decisions=[d for r in subset for d in r['audit']['decisions']]
        counts=Counter(d['status'] for d in decisions if d['status']!='match' or d['blocking'])
        for status in report.STATUSES:
            if status!='match':status_table.append(dict(population=population,status=status,candidates=counts[status],denominator=len(decisions),tasks=len(subset)))
    if phase=='complete':
        fig,ax=plt.subplots(figsize=(10,3.5));left=[0,0]
        for status,label,color in [('all','Все назначены','#087e8b'),('some','Часть назначена','#d38b32'),('none','Нет назначений','#9b6574')]:
            vals=[next(p['tasks'] for p in completeness if p['layer']==l and p['status']==status) for l in LAYERS]
            ax.barh([LABELS[l] for l in LAYERS],vals,left=left,label=label,color=color)
            for i,v in enumerate(vals):
                if v:ax.text(left[i]+v/2,i,str(v),ha='center',va='center',color='white')
            left=[a+b for a,b in zip(left,vals)]
        ax.set_xlim(0,49);ax.set_xlabel('Включённых задач, по 49 в каждом слое');ax.legend(loc='upper center',bbox_to_anchor=(.5,-.22),ncol=3,fontsize=9)
        ax.set_title('Полнота назначений, а не математическая правильность; процедуры различаются')
        savefig('mapping-completeness')
        for tid in ['68Ac00','F6158A','F416AF','C41083']:card(byid[tid],names,inputs)
    for name,rr in [('edges',edges),('chains',chains),('profiles',profiles),('kc-contexts',stats),('focus-transitions',transitions),('completeness',completeness),('unmatched-statuses',status_table)]:csvout(name,rr)
    dump(OUT/'manifest.json',manifest);dump(OUT/'checks/structural.json',dict(passed=True,checked_edges=checks,control_metrics_match=True))
    dump(OUT/'summary.json',dict(foci=[dict(id=cid,name=names[cid],metrics=[s for s in stats if s['catalog_id']==cid]) for cid in targets],
        completeness=completeness,focus_transitions=transitions,incomplete_adjacent_tasks=missing,
        audit_statuses=summary['new_accumulated']['audit_statuses'],phase=phase))
    dump(OUT/'provenance.json',dict(input_hashes=inputs,python=__import__('sys').version,
        packages={m:importlib.metadata.version(m) for m in ['matplotlib','lxml','numpy','nbformat','nbclient']},scope='Saved data only; no new semantic labels or inference'))
    body='<h1>От данных к материалам тьютора</h1><p class="warn">Предварительное исследование сохранённых назначений. Это не проверка учеников и не готовый учебный эталон.</p>'
    body+='<p>'+link(OUT/'report.md','Выводы')+' · '+link(OUT/'review.ipynb','Исполненный ноутбук')+' · '+link(OUT/'PROTOCOL.md','Зафиксированный протокол')+'</p>'
    for cid in targets:
        body+='<section><h2>'+esc(names[cid])+'</h2><img src="figures/graph-'+cid+'.png">'
        body+=htable([{'Слой':LABELS.get(s['layer'],'Смешанный'),'Задач':s['tasks'],'Разных первых КЭС':s['first_kes_n'],'Кратких':s['short'],'Развёрнутых':s['extended']} for s in stats if s['catalog_id']==cid])
        for tid in manifest['shown'][cid]:
            r=byid[tid];matched=[s for s in r['author']['steps'] if any(r['mapping'].get(k)==cid for k in s['kc_ids'])]
            body+='<h3>'+link(OUT/'cards'/f'{tid}.html',tid)+'</h3><p>'+esc('; '.join(report.ext.meta(r['input'],'КЭС:')))+'</p>'
            tree=dom.fromstring(browser_math(r['input']['statement_html']))
            for im in tree.xpath('.//img'):
                asset=next(a for a in r['input']['assets'] if Path(a['path']).name==Path(im.get('src')).name)
                src=(BASE if r['layer']==LAYERS[0] else EXT)/'inputs'/asset['path'];im.set('src',rel(src))
            body+=dom.tostring(tree,encoding='unicode')
            body+=htable([{'Шаг':s['id'],'Действие (сохранённое) ':s['action'],'Результат':s['result']} for s in matched])
        body+='</section>'
    body+='<h2>Цепочки сохранённых шагов</h2>'
    for tid in manifest['chain_task_ids']:body+='<p>'+link(OUT/'cards'/f'{tid}.html',tid+' — полный разбор')+'</p><img src="figures/chain-'+tid+'.png">'
    body+='<h2>Соседние принятые действия в фокусе linear_equation</h2>'+htable([dict(Из=names[t['from_kc']],В=names[t['to_kc']],Задач=t['tasks'],ID=t['task_ids']) for t in transitions])
    if phase=='complete':
        body+='<h2>Границы использования</h2><img src="figures/mapping-completeness.png"><p>Исторические редакторские назначения и независимый аудит имеют разные процедуры. Полнота не является проверкой математики.</p>'
        for tid,why in [('68Ac00','Составной кандидат'),('F6158A','Перекрытие определений'),('F416AF','Исправление чтения изображения'),('C41083','Спорное модельное допущение')]:body+='<p>'+link(OUT/'cards'/f'{tid}.html',tid+' — '+why)+'</p>'
    (OUT/'index.html').write_text(page('Данные и материалы тьютора',body),encoding='utf-8')
    print(json.dumps(dict(phase=phase,foci=targets,shown=manifest['shown'],chains=manifest['chain_task_ids'],completeness=completeness),ensure_ascii=False,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--phase',choices=['pilot','complete'],default='pilot');args=p.parse_args();execute(args.phase)
