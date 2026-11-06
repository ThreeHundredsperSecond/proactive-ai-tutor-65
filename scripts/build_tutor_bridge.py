"""Offline, evidence-linked EDA of content affordances. No inference/network."""
from pathlib import Path
from fractions import Fraction as F
from collections import Counter
from datetime import datetime,timezone
import ast
import csv
import hashlib
import html
import importlib.metadata
import itertools
import json
import os
import re
import subprocess
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from lxml import html as dom
from collect_fipi_bank import browser_math
import report_fipi_extension as report

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'data/annotation/analyses/2026-11-04-tutor-bridge-v2'
BASE=ROOT/'data/annotation/runs/2026-10-31-fipi-50x1'
EXT=ROOT/'data/annotation/runs/2026-11-02-fipi-extension-150'
SNAP=EXT/'active-scopes/first-050-603ec8fe8e05fe2d.json'
LAYERS=['historical_editorial','audited_new']
NAMES={LAYERS[0]:'Исторические редакторские связи',LAYERS[1]:'Независимые агентные назначения'}


def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def dump(p,x):Path(p).write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def rel(p,parent=OUT):return os.path.relpath(p,parent).replace('\\','/')
def esc(x):return html.escape(str(x))
def csvout(name,rows):
    rows=list(rows)
    if not rows:return
    with (OUT/'tables'/f'{name}.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def htable(rows):
    if not rows:return '<p>Нет записей.</p>'
    keys=list(rows[0]);return '<div class="scroll"><table><tr>'+''.join('<th>'+esc(k)+'</th>' for k in keys)+'</tr>'+''.join('<tr>'+''.join('<td>'+esc(r[k])+'</td>' for k in keys)+'</tr>' for r in rows)+'</table></div>'
def savefig(name):plt.tight_layout();plt.savefig(OUT/'figures'/f'{name}.png',dpi=160,bbox_inches='tight');plt.close()


# Small exact polynomial algebra. Supported grammar is intentionally restricted;
# no eval(), symbolic package, or claims about arbitrary student expressions.
def clean(p):return {k:v for k,v in p.items() if v}
def add(a,b):return clean({k:a.get(k,F(0))+b.get(k,F(0)) for k in set(a)|set(b)})
def scale(a,c):return clean({k:v*c for k,v in a.items()})
def mul(a,b):
    out={}
    for i,x in a.items():
        for j,y in b.items():out[i+j]=out.get(i+j,F(0))+x*y
    return clean(out)
def poly(expr,var):
    def walk(n):
        if isinstance(n,ast.Constant) and isinstance(n.value,int):return {0:F(n.value)}
        if isinstance(n,ast.Name) and n.id==var:return {1:F(1)}
        if isinstance(n,ast.UnaryOp) and isinstance(n.op,(ast.USub,ast.UAdd)):return scale(walk(n.operand),-1 if isinstance(n.op,ast.USub) else 1)
        if isinstance(n,ast.BinOp):
            a,b=walk(n.left),walk(n.right)
            if isinstance(n.op,ast.Add):return add(a,b)
            if isinstance(n.op,ast.Sub):return add(a,scale(b,-1))
            if isinstance(n.op,ast.Mult):return mul(a,b)
            if isinstance(n.op,ast.Div) and set(b)<={0} and b.get(0):return scale(a,1/b[0])
            if isinstance(n.op,ast.Pow) and set(b)<={0} and b.get(0,F(0)).denominator==1 and 0<=b.get(0,F(0))<=4:
                out={0:F(1)}
                for _ in range(int(b.get(0,F(0)))):out=mul(out,a)
                return out
        raise ValueError('Unsupported equation grammar')
    return walk(ast.parse(expr,mode='eval').body)
def equation(expr,var):
    left,right=expr.split('=');p=add(poly(left,var),scale(poly(right,var),-1))
    assert max(p,default=0)==1 and p.get(1),expr
    return p
def parse_number(text):
    text=text.strip().replace(',','.')
    if not re.fullmatch(r'[+-]?\d+(?:\.\d+)?(?:/[1-9]\d*)?',text):return None
    try:return F(text)
    except (ValueError,ZeroDivisionError):return None
def check_component(contract,text):
    value=parse_number(text)
    if value is None:return dict(status='clarification',reason='Формат вне узкой грамматики: нужен один числовой ответ без единиц и объяснения')
    p=equation(contract['normalized_equation'],contract['variable'])
    residual=sum((v*value**k for k,v in p.items()),F(0))
    return dict(status='satisfies_equation' if residual==0 else 'does_not_satisfy_equation',residual=str(residual),
        scope='Только данное уравнение; не диагноз, не полнота решения и не вся задача')


def build():
    for name in ['figures','tables','checks']:(OUT/name).mkdir(exist_ok=True)
    data=report.collect(50,strict=True,active_snapshot=SNAP)
    previous=read(EXT/'derived/checkpoint-100-v1/summary.json');summary,_=report.metrics(data)
    assert json.loads(json.dumps(summary))==previous['populations']
    rows=data['baseline']+data['new'];byid={r['task_id']:r for r in rows}
    assignments={(a['task_id'],a['local_id']):a['canonical_id'] for a in data['catalog']['assignments']}
    for r in rows:
        r['mapping']=report.mapping(r,assignments)
        src=BASE if r['layer']==LAYERS[0] else EXT
        r['author_file']=src/('raw/'+r['task_id']+'.json' if r['layer']==LAYERS[0] else r['author_path'])
        r['input_file']=src/'inputs/tasks'/f"{r['task_id']}.json"
        r['audit_file']=BASE/'catalog-decisions.json' if r['layer']==LAYERS[0] else EXT/r['auditor_path']
    contracts=read(OUT/'component-contracts.json')['records'];cases=read(OUT/'case-interpretations.json')['cases']
    assert {r['task_id'] for r in rows if r['included'] and 'linear_equation' in r['mapping'].values()}=={c['task_id'] for c in contracts}
    provenance=dict(data['input_hashes']);evidence=[]
    def cite(path,pointer,label):
        obj=read(path)
        for key in pointer.strip('/').split('/'):
            if not key:continue
            obj=obj[int(key)] if isinstance(obj,list) else obj[key.replace('~1','/').replace('~0','~')]
        provenance[path.relative_to(ROOT).as_posix()]=sha(path)
        rec=dict(id='E'+str(len(evidence)+1).zfill(3),path=path.relative_to(ROOT).as_posix(),sha256=sha(path),pointer=pointer,value=obj,label=label)
        evidence.append(rec);return rec['id']
    facts=[];tests=[]
    for c in contracts:
        r=byid[c['task_id']];a=r['author'];idx=next(i for i,s in enumerate(a['steps']) if s['id']==c['focal_step']);step=a['steps'][idx]
        assert any(r['mapping'].get(k)=='linear_equation' for k in step['kc_ids'])
        c['source_evidence']=[cite(r['author_file'],f'/steps/{idx}',c['task_id']+' focal step')]
        for i,s in enumerate(a['steps']):
            if i!=idx:c['source_evidence'].append(cite(r['author_file'],f'/steps/{i}',c['task_id']+' saved context'))
        c['final_answer_evidence']=cite(r['author_file'],'/answer',c['task_id']+' whole task answer')
        p=equation(c['normalized_equation'],c['variable']);sol=-p.get(0,F(0))/p[1]
        assert sol==F(c['expected_component_value']),c
        c['exact_normal_form']={str(k):str(v) for k,v in sorted(p.items())};c['exact_solution']=str(sol)
        c['component_is_final_quantity']=c['task_id'] not in {'D334F2','EA6D9D','F2A2EB'}
        c['step_kc_count']=len(step['kc_ids']);c['same_step_other_candidates']=[k for k in step['kc_ids'] if r['mapping'].get(k)!='linear_equation']
        c['whole_task_answer']=a['answer'];c['layer']=r['layer'];c['saved_context_steps_before']=idx
        facts.append({k:c[k] for k in ['task_id','context_label','route_family','focal_step','normalized_equation','expected_component_value','entry_availability','step_kc_count','component_is_final_quantity','whole_task_answer']})
        probes=[(str(sol),'satisfies_equation'),(str(sol+1),'does_not_satisfy_equation'),('не знаю','clarification'),
                (c['variable']+'='+str(sol),'clarification'),('1/0','clarification')]
        for text,want in probes:
            result=check_component(c,text);assert result['status']==want
            tests.append(dict(task_id=c['task_id'],synthetic_input=text,expected_status=want,actual_status=result['status'],origin='Synthetic software probe; not student data',residual=result.get('residual')))
    all_used={c['task_id'] for c in contracts}|{t for c in cases for t in c['tasks']}
    for case in cases:
        case['evidence_ids']=[]
        for tid in case['tasks']:
            r=byid[tid];case['evidence_ids'].append(cite(r['input_file'],'/statement_html',case['id']+' '+tid+' condition'))
            case['evidence_ids'].append(cite(r['author_file'],'/answer',case['id']+' '+tid+' answer'))
            for sid in case['step_refs'][tid]:
                idx=next(i for i,s in enumerate(r['author']['steps']) if s['id']==sid)
                case['evidence_ids'].append(cite(r['author_file'],f'/steps/{idx}',case['id']+' '+tid+'/'+sid))
            if r['audit']:case['evidence_ids'].append(cite(r['audit_file'],'/decisions',case['id']+' '+tid+' audit decisions'))
        if case['id']=='S02':
            case['evidence_ids'].extend([
                cite(EXT/'raw/author/F416AF.json','/steps/0','S02 original source misreading'),
                cite(EXT/'raw/author/F416AF.json','/answer','S02 original answer'),
                cite(EXT/'raw/auditor/F416AF.json','/decisions','S02 original auditor decisions'),
                cite(EXT/'checks/F416AF-source-discrepancy.json','','S02 source discrepancy and feedback provenance')])
        aa=set(byid[case['tasks'][0]]['mapping'].values());bb=set(byid[case['tasks'][-1]]['mapping'].values())
        case['accepted_set_jaccard']=len(aa&bb)/len(aa|bb) if aa|bb else None
    structural=[]
    for layer in LAYERS:
        rr=[r for r in rows if r['included'] and r['layer']==layer];steps=[s for r in rr for s in r['author']['steps']]
        structural.append(dict(layer=layer,tasks=len(rr),steps=len(steps),steps_with_multiple_candidates=sum(len(s['kc_ids'])>1 for s in steps),
            tasks_with_multiple_methods=sum(len(r['author']['methods'])>1 for r in rr),
            steps_with_any_unmapped_candidate=sum(any(k not in r['mapping'] for k in s['kc_ids']) for r in rr for s in r['author']['steps'])))
    math_checks=[]
    for tid,k,slope,roots in [('02A17e',9,F(1,3),[F(-3),F(9)]),('87FAA1',12,F(1,4),[F(-4),F(12)])]:
        for x in roots:assert x and F(k)/x==slope*x-2
        math_checks.append(dict(case=tid,check='Both saved roots satisfy the saved intersection equation and x!=0',passed=True))
    assert 3*(1-2*F(1,5)**2)==F(69,25)
    math_checks.append(dict(case='F6158A',check='3*(1-2*(1/5)^2)=69/25=2.76',passed=True))
    for tid,principal,payment,rate,n,overpay in [
        ('8B91B1',F(198600),F(79860),F(11,10),3,F(40980)),
        ('EA6D9D',F(165500),F(66550),F(11,10),3,F(34150)),
        ('D334F2',F(177120),F(75000),F(5,4),4,None)]:
        balance=principal;balances=[]
        for _ in range(n):balance=rate*balance-payment;balances.append(balance)
        assert balances[-1]==0 and all(v>0 for v in balances[:-1])
        if overpay is not None:assert n*payment-principal==overpay
        math_checks.append(dict(case=tid,check='Exact saved debt recurrence, positive intermediate balances and zero terminal balance; overpayment where given',balances=[str(v) for v in balances],passed=True))
    assert F(2)*F(3,10)*24000==120**2
    assert F(160)*(315+8)/(315-11)==170 and 315>11
    assert (5-F(8,3))**2==F(8,3)**2-F(8,3)+1 and (F(8,3)/4)**2==F(4,9)
    math_checks.extend([dict(case=tid,check=check,passed=True) for tid,check in [
        ('c15c1c','Positive acceleration; original square-root radicand equals 120 squared'),
        ('D6F31D','Original Doppler rational formula at c=315 yields 170; denominator nonzero'),
        ('F2A2EB','Saved length equation and area ratio consistent numerically; this does not reprove geometric similarity')]])
    for tid,p in [('C41083',F(7,10)),('F3F0DF',F(9,10))]:
        math_checks.append(dict(case=tid,check='Same marginal hit probability p for each shot: independent model vs all shots equal to one Bernoulli variable',
            independent_pattern=str(p*(1-p)**3),perfect_dependence_pattern='0',conclusion='Marginals alone do not determine HMMM; independent-shot convention must be explicit',passed=True))
    dump(OUT/'checks/exact-math.json',math_checks);dump(OUT/'checks/synthetic-component-tests.json',dict(scope='Software behavior on prepared affine states only; not accuracy or pedagogical validation',tests=tests))
    dump(OUT/'evidence.json',evidence);dump(OUT/'derived-contracts.json',contracts);dump(OUT/'derived-cases.json',cases)
    evbody='<h1>Точные свидетельства</h1><p><a href="index.html">Вернуться к сопоставлениям</a>. Значения полей сохранены буквально; смысловые выводы находятся отдельно.</p>'
    for e in evidence:
        evbody+='<section id="'+e['id']+'"><h2>'+esc(e['id']+' · '+e['label'])+'</h2><p><a href="'+esc(rel(ROOT/e['path']))+'">'+esc(e['path'])+'</a><br>JSON Pointer: '+esc(e['pointer'] or '/')+'<br>SHA-256: '+e['sha256']+'</p><pre>'+esc(json.dumps(e['value'],ensure_ascii=False,indent=2))+'</pre></section>'
    (OUT/'evidence.html').write_text('<!doctype html><html lang="ru"><meta charset="utf-8"><title>Основания выводов</title><style>body{font:16px/1.6 system-ui;max-width:1100px;margin:30px auto;padding:20px;color:#203b47}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#eef5f5;padding:20px}section{margin:35px 0}a{color:#08747d}</style>'+evbody+'</html>',encoding='utf-8')
    csvout('component-contexts',facts);csvout('structure',structural)
    pairrows=[]
    cm={c['task_id']:c for c in contracts}
    for a,b in itertools.combinations(sorted(cm),2):
        x,y=set(byid[a]['mapping'].values()),set(byid[b]['mapping'].values())
        pairrows.append(dict(task_a=a,task_b=b,same_accepted_target=True,same_analyst_route_family=cm[a]['route_family']==cm[b]['route_family'],
            accepted_set_jaccard=len(x&y)/len(x|y),entry_a=cm[a]['entry_availability'],entry_b=cm[b]['entry_availability']))
    csvout('same-kc-pairs',pairrows)
    counts=dict(task_n=100,included_n=98,qualitative_tasks=len(all_used),linear_contracts=len(contracts),
        same_kc_pairs=len(pairrows),same_coarse_route_pairs=sum(r['same_analyst_route_family'] for r in pairrows),
        prior_step_ready=sum(c['entry_availability']=='prior_step' for c in contracts),within_step_preparation=sum(c['entry_availability']=='within_step' for c in contracts),
        focal_steps_with_multiple_candidates=sum(c['step_kc_count']>1 for c in contracts),component_not_final_quantity=sum(not c['component_is_final_quantity'] for c in contracts),
        qualitative_pairs=sum(len(c['tasks'])==2 for c in cases),qualitative_single_cases=sum(len(c['tasks'])==1 for c in cases),structural=structural)
    dump(OUT/'summary.json',counts)
    # Three explicit content queries, not a learned recommendation policy.
    queries=[dict(id='Q1',intent='Поиск всех принятых применений линейного уравнения',task_ids=sorted(cm),basis='Только сохранённое принятое назначение'),
        dict(id='Q2',intent='Требовать явный аффинный вход в предыдущем шаге',task_ids=sorted(c['task_id'] for c in contracts if c['entry_availability']=='prior_step'),basis='Редакторское описание входного состояния; задачи требуют предметного просмотра'),
        dict(id='Q3',intent='Сузить полный маршрут до показательного семейства',task_ids=sorted(c['task_id'] for c in contracts if c['route_family']=='exponential'),basis='Исследовательская группа подготовки, не официальная категория и не диагноз ученика')]
    dump(OUT/'content-query-demo.json',queries)
    # Plot is an explanation of the actual contrast, with individual task IDs.
    fig,ax=plt.subplots(figsize=(12,5.5));ordered=sorted(contracts,key=lambda c:(c['entry_availability'],c['task_id']))
    ax.barh([c['task_id']+' · '+c['context_label'] for c in ordered],[c['saved_context_steps_before'] for c in ordered],
        color=['#087e8b' if c['entry_availability']=='prior_step' else '#bd7b2c' for c in ordered])
    ax.set_xlabel('Число предшествующих записанных шагов, не шкала трудности');ax.set_xticks([0,1,2,3,4])
    ax.set_title('Один KC не задаёт вход: бирюзовый — уравнение уже установлено; охра — нужна подготовка внутри шага',fontsize=10)
    savefig('entry-work')
    fig,ax=plt.subplots(figsize=(9,3.5));labels=['Только общий KC','Явный вход раньше','Показательный маршрут']
    vals=[len(q['task_ids']) for q in queries];bars=ax.barh(labels,vals,color=['#527b91','#087e8b','#bd7b2c']);ax.bar_label(bars,padding=4);ax.set_xlim(0,14)
    ax.set_xlabel('Задач из 12; фильтры Q2 и Q3 независимы, не последовательная воронка');ax.set_title('Контентный запрос меняет набор упражнений, даже при одном целевом KC')
    savefig('content-queries')
    figs=['entry-work','content-queries']
    source_html={}
    for tid in sorted(all_used):
        r=byid[tid];tree=dom.fromstring(browser_math(r['input']['statement_html']));src=(BASE if r['layer']==LAYERS[0] else EXT)/'inputs'
        for im in tree.xpath('.//img'):
            asset=next(x for x in r['input']['assets'] if Path(x['path']).name==Path(im.get('src')).name);path=src/asset['path']
            assert sha(path)==asset['sha256'];provenance[path.relative_to(ROOT).as_posix()]=sha(path);im.set('src',rel(path))
        source_html[tid]=dom.tostring(tree,encoding='unicode')
    # Preserve local research lineage as evidence, without claiming a new study.
    history=[]
    for p in [ROOT/'research/2026-10-27-map-context-transfer/README.md',ROOT/'research/2026-10-27-kc-investigation/README.md',ROOT/'docs/project-vision.md']:
        provenance[p.relative_to(ROOT).as_posix()]=sha(p);history.append(rel(p))
    for p in [OUT/'checks/method-review.json',OUT/'PROTOCOL.md',OUT/'component-contracts.json',OUT/'case-interpretations.json',Path(__file__),EXT/'derived/checkpoint-100-v1/summary.json']:
        provenance[p.relative_to(ROOT).as_posix()]=sha(p)
    dump(OUT/'provenance.json',dict(input_hashes=provenance,python=sys.version,packages={p:importlib.metadata.version(p) for p in ['matplotlib','numpy','lxml','nbformat','nbclient']},
        lineage=history,meaning='Hashes verify saved observations; qualitative contracts/interpretations are separate analyst inputs'))
    previous_manifest=read(OUT/'manifest.json') if (OUT/'manifest.json').exists() else {}
    dump(OUT/'manifest.json',dict(started_at=previous_manifest.get('started_at',datetime.now(timezone.utc).isoformat()),git_sha=previous_manifest.get('git_sha',subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT).decode().strip()),
        scope='Exploratory local content-to-tutor EDA; all 12 accepted linear cases + targeted counterexamples; no new task solving by models',
        contracts=[c['task_id'] for c in contracts],cases=[c['id'] for c in cases],task_ids=sorted(all_used),interpretations_author='Primary assistant; not independent experts',
        models_called=0,synthetic_probes_origin='Hand-coded software examples, no real students'))
    write_report(counts,contracts,cases,queries,source_html,figs)
    print(json.dumps(counts,ensure_ascii=False,indent=2))


def write_report(counts,contracts,cases,queries,source_html,figs):
    byid={c['task_id']:c for c in contracts}
    report_text='''# Как разметка может стать основой тьютора

**Предварительное локальное исследование v2.** Проверяем не обучение учеников, а достаточность представления содержания: какие задачи и шаги можно переиспользовать и какие условия для этого теряются.

Главный вывод: **KC — полезный поисковый ключ, но недостаточная единица учебного взаимодействия.** Для проверяемого упражнения нужны ещё входное состояние, наблюдаемое преобразование, ожидаемый результат, ограничения и роль результата в исходной задаче. Часть этих сведений уже есть в трассах, часть требует явной редакторской подготовки.

[Интерактивное сопоставление условий и решений](index.html) · [Исполненный EDA-ноутбук](review.ipynb) · [Методика](PROTOCOL.md) · [Проверки](checks/final.json).

## 1. Что проверили

Сохранённые 100 разборов, основные показатели по прежним 98. Для всех 12 принятых применений линейного уравнения выписаны отдельные контракты действия. Девять пар и два одиночных случая выбраны целенаправленно после просмотра для контрастов. Это исследование представления, не случайная выборка для оценки распространённости и не независимая экспертная оценка.

Фактический порядок: сначала просмотр исходников и подготовка смысловых входов, затем полный расчёт и целевой браузерный просмотр. Запланированный визуальный пилот 2–3 контрастов не был отдельным шлюзом перед полной обработкой; это отмечено в [журнале метода](checks/method-review.json). Работа исследовательская, не ослеплённая проверка.

Утверждения разных типов разделены: исходные поля с точными цитатами; интерпретации основного ассистента; ограниченные математические проверки; гипотезы дизайна. Нормализованные уравнения и контексты — отдельный редактируемый вход, а не результат автоматического парсинга. Любое новое предметное толкование требует просмотра.

## 2. Что общий KC скрывает

У 12 задач получается 66 возможных пар по одному общему KC. Только {route_pairs} пар относятся к одной из наших грубых групп подготовки; сама группировка исследовательская и не означает совпадения полного метода. Это не означает, что остальные пары плохие: им может соответствовать практика переноса, но они добавляют другое содержание.

{structural_table}

Число Method может означать разные пункты с общими шагами, а не альтернативные способы. Совместное присутствие KC в шаге не устанавливает, какой из них вызвал бы ошибку ученика.

В {prior}/12 случаев аффинный вход явно установлен предшествующим шагом; в {within}/12 требуется подготовка внутри шага с назначенным KC (подстановка, квадрат или сокращение квадратных членов). В {multi}/12 фокусных шагов указано несколько кандидатов. В {not_final}/12 результат линейного компонента не является спрашиваемой величиной всей задачи.

Числа описывают эти записи и новую явную рубрику; не измеряют трудность или владение навыком.

![Подготовка перед одним действием](figures/entry-work.png)

### Контракты всех 12 действий

{contracts_table}

В F2A2EB исходное равенство выглядит квадратным: (5−e)²=e²−e+1, но квадратные члены сокращаются и остаётся −9e+24=0. В c15c1c сначала нужно обосновать возведение в квадрат. Поэтому простой поиск «в шаге есть linear_equation» ещё не даёт готового одинакового входа для упражнения.

## 3. Содержательные сопоставления

{case_summaries}

Все условия, нужные шаги и решения аудитора доступны рядом в HTML. Доказательные поля сохранены в evidence.json с JSON Pointer и SHA-256. Сходство полного маршрута — интерпретация этих случаев, не измеренная взаимозаменяемость упражнений.

## 4. Минимальный исполнимый мост

Мы сделали узкую офлайн-демонстрацию: **сохранённая трасса → редакторский контракт → нормализованное аффинное уравнение → точная проверка числового ответа**. Для всех 12 уравнений коэффициенты вычислены рационально, квадратные члены при необходимости сокращены, проверена единственность корня и согласованность указанного значения.

60 искусственных программных проб проверяют ожидаемый числовой результат, заведомо другое число и неподдерживаемые форматы. Это тест программного поведения, не accuracy тьютора и не попытки учеников. Проверка не принимает свободное решение, не объясняет причину ошибки, не проверяет все ограничения модели и не засчитывает всю исходную задачу. Для любого уравнения принимается один точный числовой ответ; неподдерживаемый формат вызывает уточнение.

Например, 75000 удовлетворяет компонентному уравнению D334F2, но исходный вопрос требует 300000. Такой результат показывает необходимость отдельного поля «что сейчас проверяем», иначе компонентный успех превратится в ложное принятие полного ответа.

### Три контентных запроса

{queries}

![Разные цели подбора](figures/content-queries.png)

Это работающий фильтр по подготовленным описаниям, а не обученная рекомендательная политика. Q2 и Q3 независимы. Логарифмическая задача не превращается в чистую линейную только из-за наличия KC; можно выделить подготовленный фрагмент, но это уже отдельное упражнение с явно данным состоянием.

## 5. Что говорят ограничения и контрпримеры

{similarity_table}

В таблице Jaccard — размер пересечения принятых множеств KC, делённый на размер их объединения. Это описание сохранённой проекции, не метрика качества рекомендаций. Для C41083/F3F0DF сравниваются обе сохранённые записи, включая исключённую из основных частот; ноль возникает при близких условиях и разной политике допуска. Для 02A17e/87FAA1 единица не означает полноту описания: факторизация и выбор точки остаются без полных назначений. Так проверяется конкретная потеря информации при переходе от решения к набору принятых KC.

Пары C41083/F3F0DF показывают разный порог принятия одного модельного допущения. Независимые выстрелы дают p(1−p)³; если все четыре исхода равны одной бернуллиевской переменной с тем же p, событие «попадание, затем три промаха» невозможно. Обе модели имеют одинаковые отдельные вероятности выстрелов. Значит, одних маргинальных вероятностей недостаточно; экзаменационная конвенция должна быть отдельным правилом допуска, а не незаметной частью эталона. Мы не объявляем официальное задание ошибочным.

В F6158A ни у одного из двух кандидатов нет принятой связи, но формула и арифметика дают 3(1−2·0,2²)=2,76. Нулевая проекция на каталог не означает отсутствия действия. В 68Ac00 знакомая операция входит в составной кандидат и не получает узкого match. Следовательно, для поиска материалов нужны и исходные действия, и назначения, и причины неопределённости.

F416AF показывает отдельный разрыв: ошибка чтения картинки может пройти автора и аудитора. Происхождение источника, проверка математики и KC-сопоставление — разные проверки. Полнота каталога не заменяет ни одну из них.

## 6. Карта от данных к функциям тьютора

| Что есть / проверено | Какой ограниченный шаг можно сделать | Чего ещё нет |
|---|---|---|
| ID задач, принятые KC, исходные условия | Получать кандидатов для практики заданного действия | Предметного допуска и доказанной подходящести конкретному ученику |
| Шаги, результаты, input_refs + явные контракты | Подготовить вход, цель и результат компонентного упражнения | Универсального автоматического извлечения таких контрактов |
| 12 выписанных уравнений, точная арифметика | Проверять один числовой ответ к данному аффинному состоянию | Проверки свободного метода, источника и полного решения |
| Различия входа и последующей интерпретации | Разделять тренировку операции и полного маршрута | Проверенных диагностических вопросов и причин ошибок |
| Источник, версии и замечания аудитора | Сохранять условия допуска и неопределённость материала | Единой предметной рубрики допуска всех эталонов |
| Попыток учеников нет | Спроектировать журнал наблюдений, пока без оценок освоения | Эмпирического профиля, правила помощи, критерия освоения и образовательного эффекта |

### Предлагаемая единица содержания

`source_task + source_version + target_action + established_input_state + relevant_conditions + requested_output + accepted_variants + validation_scope + evidence + review_status`.

Это предложение схемы, а не миграция исходной разметки. Статус «правильный числовой ответ к подготовленному уравнению» не равен «самостоятельно решил задачу» или «освоил KC». Связь с профилем возникает только после реальной попытки, с сохранением помощи и контекста.

## 7. Какое решение оправдано теперь

**Можно переходить к проектированию маленького содержательного цикла**, опираясь на конкретный подготовленный контракт. Сначала отдельно проверить условие, математику и цель упражнения; затем определить допустимые ответы и границу отказа. Для компонентного режима вход даётся явно; для полного маршрута ученик должен сам его получить. Эти режимы нельзя смешивать в метриках успеха.

До живой диагностики: сформировать независимый предметно проверенный набор правильных, ошибочных и неоднозначных ответов, заморозить критерии до испытания, проверить ложное принятие и запросы уточнения. Примеры из этой работы — разработка, не отложенный тест. Далее нужны реальные попытки и отдельная проверка переноса. Никакая их результативность здесь не измерена.

## 8. Связь с прежними исследованиями и воспроизведение

В [опыте входного состояния](../../../../research/2026-10-27-map-context-transfer/README.md) контекст менял свидетельство применимости одного известного действия, но не устанавливал освоение. Здесь то же требование проявляется на конкретных материалах: текущий шаг нужно связывать с уже установленным состоянием. [Исследование границ KC](../../../../research/2026-10-27-kc-investigation/README.md) рекомендовало сохранять операции и контрпримеры; составные случаи подтверждают необходимость этого для представления содержания, а не правильность окончательных границ навыков. Старые исследования не являются независимой проверкой новой версии.

Команда: `.venv/Scripts/python.exe -B -X utf8 scripts/build_tutor_bridge.py` из корня. Она пересчитывает сохранённые данные и программные проверки без сети/моделей. Исполненный ноутбук строится и проверяется `scripts/finalize_tutor_bridge.py`; зависимости и SHA-256 фиксируются в provenance.json. Новые смысловые входы — component-contracts.json и case-interpretations.json. Их автоматическое воспроизведение без редакторского суждения не обещается.

Сохранены точные входы, цитаты и хеши; старые ответы/каталоги/EDA/v1 не меняются. Полная математическая экспертиза всех 100, реальные ученики и эффективность тьютора остаются вне проверки. Всё локально, без commit/push.
'''
    contract_lines=['| ID | Вход для компонента (редакторская запись) | Значение компонента | Что требуется после / дополнительно |','|---|---|---|---|']
    contract_lines += [f"| {c['task_id']} | `{c['normalized_equation']}` | {c['exact_solution']} | {c['postcondition_or_output']} |" for c in contracts]
    summaries='\n\n'.join('### '+c['id']+'. '+c['title']+'\n\n**Наблюдение:** '+c['observation']+'\n\n**Возможное применение:** '+c['possible_use']+'\n\n**Граница:** '+c['boundary'] for c in cases)
    replacements={'route_pairs':counts['same_coarse_route_pairs'],'prior':counts['prior_step_ready'],'within':counts['within_step_preparation'],'multi':counts['focal_steps_with_multiple_candidates'],'not_final':counts['component_not_final_quantity'],
        'structural_table':'\n'.join(['| Слой (по 49 включённых задач) | Шагов | Шагов с несколькими кандидатами | Шагов с неназначенным кандидатом |','|---|---:|---:|---:|']+[f"| {NAMES[r['layer']]} | {r['steps']} | {r['steps_with_multiple_candidates']} | {r['steps_with_any_unmapped_candidate']} |" for r in counts['structural']]),'contracts_table':'\n'.join(contract_lines),'case_summaries':summaries,'queries':'\n\n'.join(q['id']+': '+q['intent']+' → '+str(len(q['task_ids']))+' задач: '+', '.join(q['task_ids']) for q in queries)}
    selected=[c for c in cases if c['id'] in ['P01','P04','P05','P06','P09']]
    replacements['similarity_table']='\n'.join(['| Сопоставление | Jaccard принятых KC | Что надо учитывать сверх числа |','|---|---:|---|']+[
        '| '+('/'.join(c['tasks']))+' | '+f"{c['accepted_set_jaccard']:.3f}"+' | '+c['title']+' |' for c in selected])
    for k,v in replacements.items():report_text=report_text.replace('{'+k+'}',str(v))
    (OUT/'report.md').write_text(report_text,encoding='utf-8')
    body='''<header><span class="tag">Локальный исследовательский результат · предварительно</span><h1>От разметки к учебному действию</h1><p class="lead">Один KC связывает задачи. Для тьютора важно ещё, <b>что уже дано ученику, какое преобразование он выполняет и что именно считается результатом</b>.</p><p><a href="report.md">Аргументация</a> · <a href="review.ipynb">EDA-ноутбук</a> · <a href="PROTOCOL.md">Метод</a> · <a href="evidence.json">Точные свидетельства</a> · <a href="checks/final.json">Проверки</a></p></header>'''
    body+='<section><h2>Начните с контрастов</h2><p>Раскройте пару: условия и шаги сохранены из источников. Наблюдение и вывод автора исследования выделены отдельно.</p>'
    for i,case in enumerate(cases):
        body+='<details '+('open' if i<2 else '')+' id="'+case['id']+'"><summary>'+esc(case['id']+' · '+case['title'])+'</summary><div class="compare">'
        for tid in case['tasks']:
            body+='<article><h3>'+tid+'</h3><div class="source">'+source_html[tid]+'</div>'
            # Evidence contains exact saved steps, not paraphrases.
            ev=read(OUT/'evidence.json');steps=[e['value'] for e in ev if e['id'] in case['evidence_ids'] and e['pointer'].startswith('/steps/') and tid in e['label']]
            for s in steps:body+='<p><b>'+esc(s['id']+' · '+s['action'])+'</b><br>'+esc(s['result'])+'</p>'
            body+='</article>'
        score='<p>Jaccard принятых множеств KC: '+f"{case['accepted_set_jaccard']:.3f}"+'; это не оценка пригодности пары.</p>' if len(case['tasks'])==2 and case['accepted_set_jaccard'] is not None else ''
        body+='</div><div class="interpretation"><b>Интерпретация основного ассистента:</b> '+esc(case['observation'])+score+'<p><b>Возможное применение:</b> '+esc(case['possible_use'])+'</p><p><b>Граница:</b> '+esc(case['boundary'])+'</p><small>Целевой исследовательский отбор; '+', '.join('<a href="evidence.html#'+e+'">'+e+'</a>' for e in case['evidence_ids'])+'</small></div></details>'
    body+='</section><section><h2>Что выберет фильтр при разных целях?</h2><p>Работает по фиксированным данным и отдельным редакторским контрактам; не по профилю ученика.</p><select id="intent">'+''.join('<option value="'+q['id']+'">'+esc(q['intent'])+'</option>' for q in queries)+'</select><p id="query-note"></p><div id="query-results"></div></section>'
    body+='<section><h2>Один компонент — разные входы и выходы</h2><img src="figures/entry-work.png"><img src="figures/content-queries.png">'+htable([{'ID':c['task_id'],'Контекст (интерпретация)':c['context_label'],'Подготовленное уравнение':c['normalized_equation'],'Результат компонента':c['exact_solution'],'Ответ всей задачи':c['whole_task_answer'],'После / ограничения':c['postcondition_or_output']} for c in contracts])+'</section>'
    body+='<section><h2>Ограниченная исполнимая проверка</h2><p>Уравнение уже дано. Введите <b>одно число</b>; проверка использует точные дроби и только аффинное равенство. Словесные ответы не оцениваются. Это демонстрация компонента, не тьютор.</p><select id="component">'+''.join('<option value="'+c['task_id']+'">'+esc(c['task_id']+' · '+c['normalized_equation'])+'</option>' for c in contracts)+'</select><input id="answer" placeholder="Например: 2 или 8/3"><button id="check">Проверить равенство</button><p id="verdict"></p><p class="warning">Даже верное число не означает правильность полного решения. В D334F2 платёж 75000 — ещё не ответ 300000.</p></section>'
    body+='<section><h2>Мост и недостающие основания</h2>'+htable([
        {'Есть в данных':'Условие + принятый KC','Получается сейчас':'Список кандидатов упражнений с основаниями','Нужно ещё':'Предметный допуск, цель практики, контекст'},
        {'Есть в данных':'Трасса + явный редакторский контракт','Получается сейчас':'Вход / действие / результат / ограничения','Нужно ещё':'Допустимые варианты ответа и согласованная гранулярность'},
        {'Есть в данных':'12 аффинных состояний + точная арифметика','Получается сейчас':'Узкая проверка одного числа; отказ от неподдерживаемого формата','Нужно ещё':'Проверка метода, источника, допущений и целого решения'},
        {'Есть в данных':'Свидетельства неоднозначности и пропусков','Получается сейчас':'Не терять действия вне каталога, хранить неопределённость','Нужно ещё':'Отдельная предметная рубрика'},
        {'Есть в данных':'Попыток учеников нет','Получается сейчас':'Только проектировать журнал будущих наблюдений','Нужно ещё':'Диагностика, профиль, политика помощи и измерение эффекта'}])+'<p>Полный разбор, доказательства и следующий предлагаемый опыт — в <a href="report.md">отчёте</a>. Новых решений моделей и реальных учеников в исследовании нет.</p></section>'
    bridge_map=[
        dict(id='M1',function='Подбор материала',input='Принятый KC + исходное условие + контекст',affordance='Кандидаты для разных целей практики',evidence=['P01','P02','P05'],gap='Предметный допуск и данные о текущей цели ученика'),
        dict(id='M2',function='Проверяемое действие',input='Шаг + установленный вход + редакторский контракт',affordance='Ограниченная точная проверка подготовленного уравнения',evidence=['P02','P08'],gap='Свободные ответы, альтернативные методы, допущения'),
        dict(id='M3',function='Различение компонента и всей задачи',input='Результат шага + спрашиваемая величина',affordance='Не засчитывать платёж как общую сумму',evidence=['P03','P06'],gap='Явная цель текущего запроса и отдельная проверка полного решения'),
        dict(id='M4',function='Неопределённость предметной модели',input='Исходные действия + причина отсутствия match',affordance='Не терять операцию вне каталога',evidence=['P08','S01'],gap='Согласованные границы определений'),
        dict(id='M5',function='Допуск источника и модели',input='Изображения + история исправлений + допущения',affordance='Разделять контроль чтения, математики и KC',evidence=['P09','S02'],gap='Независимая предметная проверка'),
        dict(id='M6',function='Освоение и педагогическая политика',input='Реальных попыток в исследовании нет',affordance='Только сформулировать будущий журнал и испытание',evidence=[],gap='Наблюдения ученика, проверка диагностики и образовательного эффекта')]
    dump(OUT/'bridge-map.json',bridge_map)
    body+='<section><h2>Проверить основания карты</h2>'+''.join('<p><b>'+esc(m['id']+' · '+m['function'])+'</b> — '+esc(m['affordance'])+'<br>Свидетельства: '+(' · '.join('<a href="#'+case+'">'+case+'</a>' for case in m['evidence']) or 'нет ученических наблюдений; это граница исследования')+'</p>' for m in bridge_map)+'</section>'
    payload=json.dumps(dict(queries=queries,contracts=contracts),ensure_ascii=False).replace('</','<\\/')
    js='''const D=JSON.parse(document.getElementById('dataset').textContent);const E=s=>String(s).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;');
function show(){const q=D.queries.find(q=>q.id===document.getElementById('intent').value);document.getElementById('query-note').textContent=q.task_ids.length+' задач. '+q.basis;document.getElementById('query-results').innerHTML=q.task_ids.map(id=>{const c=D.contracts.find(c=>c.task_id===id);return '<article><b>'+E(id+' · '+c.context_label)+'</b><p>'+E(c.normalized_equation)+'</p><p>До: '+E(c.preparation)+'</p><p>После: '+E(c.postcondition_or_output)+'</p></article>'}).join('')};document.getElementById('intent').onchange=show;show();
// Exact rational check with BigInt, not binary floating-point grading.
function gcd(a,b){a=a<0n?-a:a;b=b<0n?-b:b;while(b){let t=a%b;a=b;b=t}return a||1n}function frac(a,b=1n){if(!b)throw Error();let g=gcd(a,b);if(b<0n)g=-g;return [a/g,b/g]}function strf(t){return t[0]+'/'+t[1]}
function parse(s){s=s.trim().replace(',','.');if(!/^[+-]?\\d+(?:\\.\\d+)?(?:\\/[1-9]\\d*)?$/.test(s))throw Error();let parts=s.split('/'),v=parts[0],sign=v.startsWith('-')?-1n:1n;v=v.replace(/^[+-]/,'');let d=v.split('.'),den=10n**BigInt((d[1]||'').length);return frac(sign*BigInt(d.join('')),den*BigInt(parts[1]||'1'))}
document.getElementById('check').onclick=()=>{const c=D.contracts.find(c=>c.task_id===document.getElementById('component').value);let msg;try{const x=parse(document.getElementById('answer').value),a=parse(c.exact_normal_form['1']),b=parse(c.exact_normal_form['0']||'0');let num=a[0]*x[0]*b[1]+b[0]*a[1]*x[1];msg=num===0n?'Число удовлетворяет данному уравнению. Проверена только эта операция.':'Число не удовлетворяет данному уравнению. Причину ошибки эта проверка не определяет.'}catch(e){msg='Нужно уточнение: поддерживается одно число, десятичная или обыкновенная дробь. Это не вердикт о математической правильности другого формата.'}document.getElementById('verdict').textContent=msg};'''
    css='''body{font:17px/1.6 system-ui;color:#203b47;background:#f4f7f8;margin:0}header,section{max-width:1200px;margin:22px auto;background:white;padding:28px 36px;border-radius:14px}h1{font-size:36px;line-height:1.2}.lead{font-size:21px}.tag{color:#08747d;font-weight:600}a{color:#08747d}details{border:1px solid #cbd9dc;border-radius:9px;padding:18px;margin:18px 0}summary{cursor:pointer;font-size:20px;font-weight:650}.compare{display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:22px}article{background:#f4f8f8;padding:18px;margin:12px 0;border-radius:8px}.source{background:white;padding:14px;border-left:3px solid #087e8b}.source img{background:white;max-width:100%}.interpretation{background:#fff4e3;padding:17px}small{color:#586d75}.warning{background:#fff4e3;padding:15px}table{border-collapse:collapse;width:100%;font-size:14px}td,th{border:1px solid #cbd9dc;padding:10px;vertical-align:top}th{background:#edf4f5}.scroll{overflow-x:auto}img{max-width:100%}select,input,button{font:inherit;padding:10px;margin:7px 7px 7px 0;max-width:100%}button{background:#08747d;color:white;border:0;border-radius:5px}#query-results{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:12px}math{font-size:1.12em}'''
    (OUT/'index.html').write_text('<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>От разметки к тьютору: EDA</title><style>'+css+'</style>'+body+'<script type="application/json" id="dataset">'+payload+'</script><script>'+js+'</script></html>',encoding='utf-8')
    (OUT/'README.md').write_text('# Аргументированный мост: разметка → тьютор\n\nПредварительный локальный результат v2. Начните с [интерактивного HTML](index.html) или [аргументации](report.md). [EDA-ноутбук](review.ipynb) показывает расчёты и выводы. Новые смысловые входы явно отделены от исторической разметки; всё воспроизводится офлайн по сохранённым данным. Метод, команды и границы описаны в отчёте.\n',encoding='utf-8')


if __name__=='__main__':build()
