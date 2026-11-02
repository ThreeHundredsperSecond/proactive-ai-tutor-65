"""Rebuild descriptive bank EDA and the reviewed 50-task pilot without inference."""
import csv
import html as H
import itertools
import json
import re
import statistics
import textwrap
from collections import Counter,defaultdict
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from lxml import html

from fipi_eda50 import ROOT,BANK,RUN,read,write,digest,metadata,stratum,validate
from collect_fipi_bank import browser_math

OUT=RUN/'derived'


def csvout(name,rows,fields=None):
    rows=list(rows)
    if not fields and rows:fields=list(rows[0])
    with (OUT/name).open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields or []);w.writeheader();w.writerows(rows)


def key_condition(r,mask_numbers=False):
    tree=html.fromstring(r['statement_html'])
    hashes={a['path'].split('/')[-1]:a['sha256'] for a in r['assets']}
    def norm(s):
        s=' '.join((s or '').replace('\u200b','').split())
        return re.sub(r'\d+(?:[.,]\d+)?','#',s) if mask_numbers else s
    def walk(e):
        if e.tag=='img':return ('img',hashes[e.get('src','').split('/')[-1]])
        attributes=tuple((k,e.get(k)) for k in ['open','close','separators','mathvariant','accent','stretchy'] if e.get(k) is not None)
        return (e.tag,attributes,norm(e.text),tuple((walk(c),norm(c.tail)) for c in e if isinstance(c.tag,str)))
    return digest(json.dumps([r['instruction'],walk(tree)],ensure_ascii=False).encode())


def savefig(name):
    plt.tight_layout();plt.savefig(OUT/(name+'.png'),dpi=150,bbox_inches='tight');plt.close()


def describe(values):
    return dict(n=len(values),median=statistics.median(values),min=min(values),max=max(values),mean=round(statistics.mean(values),3))


def build_cards(raws,entries,catalog,links):
    (OUT/'cards').mkdir(exist_ok=True)
    byid={n['id']:n for n in catalog['nodes']}
    for r in raws:
        tid=r['task_id'];inp=read(RUN/'inputs/tasks'/f'{tid}.json')
        condition=browser_math(inp['statement_html']).replace('../assets/','../../inputs/assets/')
        steps=''.join('<tr><td>'+s['id']+'</td><td>'+H.escape(s['action'])+'</td><td>'+H.escape(s['result'])+'</td><td>'+
                      ', '.join('<a href="../catalog.html#'+links[(tid,k)]+'">'+H.escape(k)+' → '+H.escape(byid[links[(tid,k)]]['name'])+'</a>' for k in s['kc_ids'])+
                      '</td><td>'+H.escape(', '.join(s['input_refs']))+'</td></tr>' for s in r['steps'])
        kcs=''.join('<li><b>'+H.escape(k['id']+' · '+k['name'])+'</b>: '+H.escape(k['description'])+'</li>' for k in r['kc_candidates'])
        methods=''.join('<li>'+H.escape(m['name'])+' · '+', '.join(m['step_ids'])+'</li>' for m in r['methods'])
        warnings=''.join('<li>'+H.escape(x)+'</li>' for x in r['warnings'])
        banner='<p class="warn">Нужно уточнение условия / частичный разбор. Исключено из основных частот.</p>' if r['solution_status']!='solved' else ''
        body=f'<nav><a href="../index.html">Все задачи и графики</a></nav><h1>{entries[tid]["order"]}. ФИПИ {tid}</h1>'+banner
        body+='<p>Предварительный разбор основным ассистентом; не официальный ответ и не экспертиза.</p><h2>Условие</h2>'+condition
        body+='<p class="meta">КЭС банка: '+H.escape('; '.join(metadata(inp,'КЭС:')))+'</p>'
        body+='<h2>Ответ разбора</h2><p>'+H.escape(r['answer'])+'</p><h2>Содержательные шаги</h2><table><tr><th>ID</th><th>Действие</th><th>Результат</th><th>Кандидаты KC</th><th>Основания входа</th></tr>'+steps+'</table>'
        body+='<h2>Локальные определения KC</h2><ul>'+kcs+'</ul><h2>Использованные маршруты</h2><ul>'+methods+'</ul><h2>Предупреждения</h2><ul>'+warnings+'</ul>'
        body+='<p><a href="'+H.escape(inp['source_url'])+'">Официальное условие</a></p>'
        (OUT/'cards'/f'{tid}.html').write_text(page(tid,body),encoding='utf-8')
    body='<h1>Предварительный редакторский каталог</h1><p>Определения и соответствия — отдельный постфактум вход анализа. Это не установленная карта освоения.</p>'
    for node in catalog['nodes']:
        members=', '.join('<a href="cards/'+m['task_id']+'.html">'+m['task_id']+'/'+m['local_id']+'</a>' for m in node['members'])
        body+='<section id="'+node['id']+'"><h2>'+H.escape(node['name'])+'</h2><p>'+H.escape(node['definition'])+'</p><p class="meta">'+node['decision_basis']+'</p><p>'+members+'</p></section>'
    (OUT/'catalog.html').write_text(page('Каталог KC',body),encoding='utf-8')


def page(title,body):
    return '<!doctype html><html lang="ru"><meta charset="utf-8"><title>'+H.escape(title)+'</title><style>body{font:18px/1.55 system-ui;max-width:1400px;margin:30px auto;padding:0 24px;color:#172b38}img{max-width:100%;height:auto}section{margin:24px 0}math{font-size:1.1em}table{border-collapse:collapse;width:100%}td,th{border:1px solid #ccd4d8;padding:9px;vertical-align:top}th{background:#eef3f5}.warn{background:#fff0cc;padding:14px}.meta{font-size:14px;color:#52616b}a{color:#166b8b}</style>'+body+'</html>'


def analyze():
    OUT.mkdir(exist_ok=True)
    validate()
    manifest=read(RUN/'manifest.json');entries={t['task_id']:t for t in manifest['tasks']}
    raws=[read(RUN/'raw'/f'{t["task_id"]}.json') for t in manifest['tasks']]
    review=read(RUN/'review-decisions.json')
    for r in raws:
        assert digest((RUN/'raw'/f'{r["task_id"]}.json').read_bytes())==review['tasks'][r['task_id']]['raw_sha256']
    included=[r for r in raws if review['tasks'][r['task_id']]['include_primary_metrics']]
    assert len(raws)==50
    bank=[json.loads(x) for x in (BANK/'tasks.jsonl').read_text(encoding='utf-8').splitlines()]
    cat=read(RUN/'catalog-decisions.json');nodes={n['id']:n for n in cat['nodes']}
    links={(a['task_id'],a['local_id']):a['canonical_id'] for a in cat['assignments']}
    assert len(links)==sum(len(r['kc_candidates']) for r in raws)
    primary=Counter(stratum(r)[0] for r in bank)
    alltags=Counter(v.split()[0] for r in bank for v in metadata(r,'КЭС:'))
    sample_primary=Counter(t['primary_kes'] for t in manifest['tasks'])
    titles={v.split()[0]:' '.join(v.split()[1:]) for r in bank for v in metadata(r,'КЭС:')}
    codes=sorted(primary,key=lambda x:tuple(map(int,x.split('.'))))
    topicrows=[dict(code=c,title=titles[c],bank_primary_n=primary[c],bank_primary_pct=round(100*primary[c]/len(bank),3),
                    bank_any_label_n=alltags[c],sample_primary_n=sample_primary[c],sample_primary_pct=2*sample_primary[c]) for c in codes]
    csvout('topics.csv',topicrows)
    representation=[]
    for c in codes:
        group=[r for r in bank if stratum(r)[0]==c]
        representation.append(dict(code=c,n=len(group),extended=sum(stratum(r)[1]=='Развернутый ответ' for r in group),
                                   images=sum(bool(r['assets']) for r in group),mathml=sum(r['mathml_count']>0 for r in group)))
    csvout('representation.csv',representation)
    exact=defaultdict(list);templates=defaultdict(list)
    for r in bank:
        exact[key_condition(r)].append(r['id']);templates[key_condition(r,True)].append(r['id'])
    exactgroups=[v for v in exact.values() if len(v)>1]
    templategroups=sorted([v for v in templates.values() if len(v)>1],key=lambda x:(-len(x),x))
    write(OUT/'duplicate-groups.json',dict(exact_groups=exactgroups,numeric_template_candidates=templategroups,
         definition='Normalized statement DOM, text, instruction and image content hashes. Numeric masks produce candidates, not confirmed methods.'))
    taskrows=[];freq=Counter();literal_freq=Counter();pairs=Counter();transitions=Counter()
    sets={}
    for r in raws:
        tid=r['task_id'];ss={links[(tid,k['id'])] for k in r['kc_candidates']}
        taskrows.append(dict(order=entries[tid]['order'],task_id=tid,primary_kes=entries[tid]['primary_kes'],response_type=entries[tid]['response_type'],
                             status=r['solution_status'],included=r in included,steps=len(r['steps']),local_kcs=len(r['kc_candidates']),
                             editorial_kcs=len(ss),methods=len(r['methods']),warnings=len(r['warnings'])))
        if r not in included:continue
        sets[tid]=ss;freq.update(sorted(ss))
        literal_freq.update(sorted({(k['name'],k['description']) for k in r['kc_candidates']}))
        pairs.update(itertools.combinations(sorted(ss),2))
        steps={s['id']:s for s in r['steps']};seen=set()
        for method in r['methods']:
            for a,b in zip(method['step_ids'],method['step_ids'][1:]):
                for ka in steps[a]['kc_ids']:
                    for kb in steps[b]['kc_ids']:
                        ca,cb=links[(tid,ka)],links[(tid,kb)]
                        if ca!=cb:seen.add((ca,cb))
        transitions.update(sorted(seen))
    csvout('pilot-tasks.csv',taskrows)
    freqrows=[dict(kc_id=k,name=nodes[k]['name'],task_n=n,task_pct=round(100*n/len(included),3),definition=nodes[k]['definition']) for k,n in freq.most_common()]
    csvout('kc-frequencies.csv',freqrows)
    csvout('kc-cooccurrence.csv',[dict(kc_a=a,kc_b=b,task_n=n) for (a,b),n in pairs.most_common()])
    csvout('kc-transitions.csv',[dict(from_kc=a,to_kc=b,task_n=n) for (a,b),n in transitions.most_common()])
    top=[k for k,_ in freq.most_common(12)]
    csvout('task-kc-matrix.csv',[dict(task_id=r['task_id'],**{k:int(k in sets[r['task_id']]) for k in top}) for r in included])
    summary=dict(bank_tasks=len(bank),bank_primary_codes=len(primary),bank_all_label_codes=len(alltags),bank_label_assignments=sum(alltags.values()),
                 bank_response_types=dict(Counter(stratum(r)[1] for r in bank)),bank_with_images=sum(bool(r['assets']) for r in bank),
                 bank_with_mathml=sum(r['mathml_count']>0 for r in bank),bank_with_source_warnings=sum(bool(r['source_issues']) for r in bank),
                 exact_duplicate_groups=len(exactgroups),exact_duplicate_extra_records=sum(len(g)-1 for g in exactgroups),
                 template_candidate_groups=len(templategroups),pilot_tasks=50,pilot_strata=len(manifest['strata']),
                 status_counts=dict(Counter(r['solution_status'] for r in raws)),included_primary_n=len(included),
                 all_steps=sum(len(r['steps']) for r in raws),all_local_kcs=sum(len(r['kc_candidates']) for r in raws),
                 editorial_catalog_all_nodes=len(cat['nodes']),literal_definition_nodes_included=len(literal_freq),
                 editorial_nodes_included=len(freq),singleton_nodes=sum(n==1 for n in freq.values()),
                 singleton_fraction=round(sum(n==1 for n in freq.values())/len(freq),4),
                 steps=describe([len(r['steps']) for r in included]),local_kcs=describe([len(r['kc_candidates']) for r in included]),
                 methods=describe([len(r['methods']) for r in included]),top_kcs=freqrows[:12],
                 by_response_type={t:{key:describe([len(r[key]) for r in included if entries[r['task_id']]['response_type']==t]) for key in ['steps','kc_candidates','methods']} for t in ['Краткий ответ','Развернутый ответ']},
                 limits=['No external expert answer key; no model accuracy estimate.','Shared-context single pass; no stability estimate.',
                         'Coverage sample is not proportional to bank; unweighted pilot frequencies are conditional on these tasks.',
                         'Editorial KC mappings are post-hoc assumptions, not automatic parsing or validated mastery units.',
                         'Transitions count task occurrence between adjacent steps within used methods; not prerequisites.'])
    write(OUT/'summary.json',summary)
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,'axes.spines.right':False})
    fig,ax=plt.subplots(figsize=(13,6));x=np.arange(len(codes));w=.4
    ax.bar(x-w/2,[100*primary[c]/len(bank) for c in codes],w,label='Банк: 1148',color='#126b7b')
    ax.bar(x+w/2,[2*sample_primary[c] for c in codes],w,label='Выборка охвата: 50',color='#e5a344')
    ax.set(xticks=x,xticklabels=codes,ylabel='Доля задач по первому КЭС, %',title='Выборка обеспечивает разнообразие, а не пропорции банка');ax.legend();savefig('01-bank-and-sample')
    fig,ax=plt.subplots(figsize=(12,8));matrix=np.array([[100*r[k]/r['n'] for k in ['extended','images','mathml']] for r in representation])
    im=ax.imshow(matrix,aspect='auto',vmin=0,vmax=100,cmap='YlGnBu');ax.set(yticks=range(len(codes)),yticklabels=codes,xticks=range(3),xticklabels=['Развёрнутый ответ','Есть изображения','Есть MathML'],title='Представление условий по первому КЭС банка, %')
    fig.colorbar(im,ax=ax,label='% внутри категории');savefig('02-representation')
    fig,axes=plt.subplots(1,2,figsize=(12,5))
    for ax,field,title in zip(axes,['steps','local_kcs'],['Число шагов','Число локальных кандидатов KC']):
        for offset,(typ,color) in zip([-.18,.18],[('Краткий ответ','#126b7b'),('Развернутый ответ','#e5a344')]):
            c=Counter(r[field] for r in taskrows if r['included'] and r['response_type']==typ)
            ax.bar([k+offset for k in sorted(c)],[c[k] for k in sorted(c)],width=.34,label=typ,color=color)
        ax.set(xlabel=title,ylabel='Число задач',title=title+' · n=49',xticks=range(1,8));ax.legend(fontsize=8)
    savefig('03-solution-structure')
    fig,ax=plt.subplots(figsize=(12,7));popular=freq.most_common(12)[::-1]
    ax.barh(range(len(popular)),[n for _,n in popular],color='#126b7b')
    ax.set(yticks=range(len(popular)),yticklabels=['\n'.join(textwrap.wrap(nodes[k]['name'],46)) for k,_ in popular],xlabel='Уникальных задач из 49',title='Повторяющиеся кандидатные действия · редакторская версия v1')
    savefig('04-recurrent-kcs')
    fig,ax=plt.subplots(figsize=(15,12));mat=np.array([[int(k in sets[r['task_id']]) for k in top] for r in included])
    ax.imshow(mat,cmap='Blues',vmin=0,vmax=1,aspect='auto',interpolation='none')
    ax.set(yticks=range(len(included)),yticklabels=[r['task_id'] for r in included],xticks=range(len(top)),xticklabels=[f'K{i+1}' for i in range(len(top))],title='Задачи × 12 наиболее повторяющихся кандидатов KC · легенда в отчёте')
    savefig('05-task-kc-matrix')
    fig,ax=plt.subplots(figsize=(11,9));co=np.array([[freq[a] if a==b else pairs[tuple(sorted((a,b)))] for b in top] for a in top])
    im=ax.imshow(co,cmap='YlGnBu');labels=[f'K{i+1}' for i in range(len(top))]
    ax.set(xticks=range(len(top)),xticklabels=labels,yticks=range(len(top)),yticklabels=labels,title='Совместное появление в задачах · диагональ — частота')
    for i in range(len(top)):
        for j in range(len(top)):ax.text(j,i,str(co[i,j]),ha='center',va='center',fontsize=8,color='white' if co[i,j]>co.max()*.6 else 'black')
    fig.colorbar(im,ax=ax,label='Задач из 49');savefig('06-cooccurrence')
    csvout('cooccurrence-legend.csv',[dict(label=f'K{i+1}',kc_id=k,name=nodes[k]['name']) for i,k in enumerate(top)])
    top_table='\n'.join(f'| K{i+1} | {nodes[k]["name"]} | {freq[k]} / {len(included)} |' for i,k in enumerate(top))
    trans_table='\n'.join(f'| {nodes[a]["name"]} → {nodes[b]["name"]} | {n} |' for (a,b),n in transitions.most_common(8))
    report=f'''# EDA ФИПИ: банк условий и пилот 50 задач

31 октября 2026. [Карточки, каталог и графики](index.html) · [Протокол до разбора](../PROTOCOL.md).

## Что исследовали и как

По всему банку Python обработал {len(bank)} условий без передачи банка модели. Отдельно основной ассистент в одном общем контексте подготовил 50 новых самостоятельных разборов по одному на задачу. Первые два просмотрены до продолжения, затем шесть партий по восемь с [health checks](../checks/). Изолированных запусков, платного API и независимых повторов нет. `requests/` — зафиксированные инструкции и входы, не журнал API. Это предварительная разметка для разработки, не внешний эталон.

Выборка покрывает все 38 непустых страт «первый КЭС × тип ответа»: 29 кратких и 21 развёрнутая. Она специально перепредставляет редкие категории, поэтому частоты навыков ниже относятся только к ней. График 01 показывает отличие её долей от банка. Один ранее подтверждённый дефект символа `697AC9` заранее исключён из отбора; это не то же замечание, что неоднозначность геометрии ниже.

## 1. Какие материалы есть в банке

- Краткий ответ: 673/1148 (58,6%); развёрнутый: 475/1148 (41,4%). Ответов и решений источник этим сбором не предоставил.
- Изображения есть у {summary['bank_with_images']}/1148 ({100*summary['bank_with_images']/1148:.1f}%); MathML — у {summary['bank_with_mathml']}/1148 ({100*summary['bank_with_mathml']/1148:.1f}%). Эти группы пересекаются. Изображения включают не только геометрию/графики, но и формулы.
- У задач {len(primary)} разных первых кодов КЭС и {len(alltags)} кодов среди всех меток. Всего {sum(alltags.values())} назначений КЭС на 1148 задач: многометочные частоты не должны суммироваться в 100%.
- Самые большие категории по первому КЭС: {', '.join(c+' — '+str(n) for c,n in primary.most_common(5))}. Это частоты открытого банка, не распределение заданий реального экзамена.
- Соответствие кодов банка кодификатору конкретного года не сверено. Отсутствие категории среди первых меток не означает отсутствие её задач или пробел официальной программы. Официальное покрытие всей программы этой таблицей не установлено.

![Категории банка и выборки](01-bank-and-sample.png)

![Форматы представления](02-representation.png)

**Для тьютора:** вход должен сохранять смешанное представление текста, MathML и изображений; одного извлечённого текста недостаточно. Баланс практики нельзя выбирать только по частотам банка.

## 2. Повторы условий

По строгому ключу «нормализованный DOM и текст условия + инструкция + SHA-256 содержимого изображений» найдено {len(exactgroups)} групп точных совпадений. Это не доказательство отсутствия смысловых дублей.

После маскирования чисел найдено {len(templategroups)} групп **кандидатных числовых шаблонов**; все ID сохранены в [реестре](duplicate-groups.json). Картинки при этом не маскируются, а сравниваются по содержимому. Эти группы не объявлены одинаковыми методами и не удалены. Перед разделением разработки/проверки нужно просматривать похожие семейства, чтобы близкие варианты не дали завышенное качество переноса.

## 3. Что получилось при разборе 50 задач

Все 50 JSON технически валидны. Сохранены {summary['all_steps']} шагов и {summary['all_local_kcs']} локальных кандидата KC. Предварительный просмотр оставил 49 `solved` и один `partial`; это **не accuracy 98%**: официального ключа, независимого оценщика и ослепления нет.

Неоднозначность — [eFF32e](cards/eFF32e.html). При обычном внутреннем пересечении ребра получено SK:KA=1:2. Если разрешить K=S, построена конфигурация с равносторонним вертикальным сечением нужной площади, в которой пункт а) не выполняется. Это требует уточнения принятой геометрической интерпретации; не утверждаем, что доказана ошибка официальной задачи. Исходный разбор не исправлялся молча. Эта задача исключена из основных частот; ниже n=49 (29 кратких, 20 развёрнутых).

| Показатель | Краткий ответ, n=29 | Развёрнутый, n=20 |
|---|---:|---:|
| Медиана шагов | {summary['by_response_type']['Краткий ответ']['steps']['median']} | {summary['by_response_type']['Развернутый ответ']['steps']['median']} |
| Диапазон шагов | 2–4 | 3–5 |
| Медиана локальных KC | {summary['by_response_type']['Краткий ответ']['kc_candidates']['median']} | {summary['by_response_type']['Развернутый ответ']['kc_candidates']['median']} |
| Диапазон локальных KC | 1–6 | 3–7 |

![Структура разборов](03-solution-structure.png)

**Для тьютора:** в этой выборке развёрнутые задачи требуют более длинной наблюдаемой цепочки. Однако число шагов зависит от принятой детализации и не является калиброванной трудностью. Число Method означает использованные маршруты/части, а не число всех возможных способов решения.

## 4. Какие действия повторяются

Отдельный [редакторский вход](../catalog-decisions.json) содержит определения, все соответствия и цитаты шагов. Явно заданные группы операций объединены основным ассистентом после просмотра ответов; вне этих групп объединяются только буквально одинаковые название и описание. Это не автоматическое смысловое распознавание и не внешняя экспертиза. Старые каталоги не менялись.

По включённым 49 задачам: {len(literal_freq)} различных буквальных пар «название + описание» и {len(freq)} узлов редакторской версии v1. Всего для всех 50 — {len(cat['nodes'])} узла, включая частичный разбор. Разница показывает зависимость результата от решения о сопоставлении, а не доказанное улучшение.

| Метка графиков | Кандидатное действие | Задач |
|---|---|---:|
{top_table}

![Повторяемость действий](04-recurrent-kcs.png)

Линейное уравнение встретилось в семи задачах: графики прямых `7D21DC`, показательные `B948D4`/`19FBCF`, геометрия `F2A2EB`, физическая формула `c15c1c`, логарифм `517970` и проценты `6D1598`. Оно не дробилось на отдельные переносы и деление. Это конкретный кандидат для подбора практики одного действия в разных контекстах; успех ученика на одном контексте ещё не доказывает перенос.

Чтение координат, восстановление функции и решение уравнения пересечения сохранены раздельно (`7D21DC`, `DDA73A`, `6E8B6F`). По ошибке ученика тьютор мог бы уточнять разные этапы, но такое диагностическое различение пока не проверено на попытках учеников.

У {summary['singleton_nodes']} из {len(freq)} узлов ({100*summary['singleton_fraction']:.1f}%) только одно применение. Причины могут сочетать широкий отбор, малое число примеров каждого типа и несогласованную детализацию; нельзя объявлять все единичные узлы лишними или все повторения доказанными навыками. Следующее полезное действие — просмотр определений и контрпримеров, а не автоматическое сжатие каталога.

![Задачи и общие действия](05-task-kc-matrix.png)

## 5. Сочетания и наблюдаемый порядок

![Совместная встречаемость](06-cooccurrence.png)

В клетке — число задач с обоими узлами, диагональ — число задач с узлом. Легенда K1–K12 приведена выше и в [CSV](cooccurrence-legend.csv). Все пары — в [CSV](kc-cooccurrence.csv).

Переход считается только между соседними шагами **внутри записанного Method**, без искусственного соединения независимых пунктов. Несколько KC внутри одного шага не упорядочиваются. Частота — число задач, где переход встречается хотя бы в одном маршруте; повтор в той же задаче не увеличивает частоту.

| Наблюдаемый переход | Задач |
|---|---:|
{trans_table}

Полный [реестр переходов](kc-transitions.csv). Совместное появление и направление в решении не доказывают prerequisites, эффективность обучения или единственный допустимый метод.

## Что теперь можно показать и что проверять дальше

Есть весь банк условий, 50 читаемых разборов, шесть графиков, матрицы, явные определения и один разобранный спорный случай. Пилот показывает конкретные повторения действий между категориями и ограничения входных представлений. Он не устанавливает окончательную карту KC, устойчивость промпта, корректность всех решений или освоение ученика.

Дальше: просмотреть `eFF32e`, определения популярных узлов и несколько единичных кандидатов; затем выбрать новые подтверждения/контрпримеры и отделить проверочную выборку. Новый пакет, повторы и весь банк автоматически не запускаются. Все материалы локальные; commit/push и PDF не выполнялись.

Пересчёт без модели: `.venv/Scripts/python.exe -B -X utf8 scripts/analyze_fipi50.py`.
Ноутбук: `notebooks/EDA.ipynb`. Входы и код связаны SHA-256 в [provenance](provenance.json).
'''
    (OUT/'report.md').write_text(report,encoding='utf-8')
    build_cards(raws,entries,cat,links)
    body='<h1>ФИПИ: банк и пилот 50 задач</h1><p>1148 условий банка · 50 новых разборов · основные частоты по 49 задачам. Предварительные решения и каталог, без внешнего эталона.</p>'
    body+='<p><a href="catalog.html">Определения и соответствия KC</a> · <a href="report.md">Отчёт</a></p><h2>Разборы</h2><table><tr><th>№</th><th>Задача</th><th>КЭС банка</th><th>Формат</th><th>Шаги</th><th>KC</th><th>Статус</th></tr>'
    for r in taskrows:
        body+='<tr><td>'+str(r['order'])+'</td><td><a href="cards/'+r['task_id']+'.html">'+r['task_id']+'</a></td><td>'+r['primary_kes']+'</td><td>'+r['response_type']+'</td><td>'+str(r['steps'])+'</td><td>'+str(r['local_kcs'])+'</td><td>'+r['status']+'</td></tr>'
    body+='</table><h2>Графики</h2>'
    for name in ['01-bank-and-sample','02-representation','03-solution-structure','04-recurrent-kcs','05-task-kc-matrix','06-cooccurrence']:
        body+='<p><a href="'+name+'.png"><img src="'+name+'.png"></a></p>'
    body+='<h2>Легенда совместной встречаемости</h2><ol>'+''.join('<li>'+H.escape(nodes[k]['name'])+'</li>' for k in top)+'</ol>'
    (OUT/'index.html').write_text(page('EDA ФИПИ: 50 задач',body),encoding='utf-8')
    sources=[RUN/'manifest.json',RUN/'prompt.txt',RUN/'baseline-A.txt',RUN/'PROTOCOL.md',RUN/'captures.json',RUN/'review-decisions.json',RUN/'catalog-decisions.json',BANK/'tasks.jsonl']+[RUN/'raw'/f'{r["task_id"]}.json' for r in raws]+sorted((RUN/'checks').glob('health-*.json'))
    codepaths=[ROOT/'scripts'/name for name in ['fipi_eda50.py','write_fipi50_annotations.py','build_fipi50_catalog.py','analyze_fipi50.py','build_fipi50_notebook.py']]+sorted((RUN/'batches').glob('b*.py'))
    write(OUT/'provenance.json',dict(inputs=[dict(path=p.relative_to(ROOT).as_posix(),sha256=digest(p.read_bytes())) for p in sources],
          scripts=[dict(path=p.relative_to(ROOT).as_posix(),sha256=digest(p.read_bytes())) for p in codepaths],execution='Offline Python; no model calls'))
    return summary


if __name__=='__main__':print(json.dumps(analyze(),ensure_ascii=False,indent=2))
