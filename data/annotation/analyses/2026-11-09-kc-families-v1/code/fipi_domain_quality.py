"""Saved-bank domain EDA; no network, generation, training or source mutation."""
import csv, hashlib, json, random, re, statistics, unicodedata
from collections import Counter, defaultdict
from pathlib import Path
import numpy as np
from lxml import html
from PIL import Image
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
ROOT = Path(__file__).resolve().parents[1]
BANK = ROOT / 'data/fipi/2026-10-31-profile'
OUT = ROOT / 'data/annotation/analyses/2026-11-09-domain-quality-v1'
SEED = 20261109  # fixed before training; independent of model scores

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def dump(p,v): p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def load_bank(): return [json.loads(s) for s in (BANK/'tasks.jsonl').read_text(encoding='utf-8').splitlines()]
def extract_text(record):
    """Naive flatten for the ablation; formulas lose tree boundaries."""
    tree=html.fromstring(record['statement_html'])
    return ' '.join(tree.text_content().split())
def semantic_tokens(record, mask_numbers=False):
    """Text plus explicit MathML boundaries and image placeholders, never metadata labels."""
    tree=html.fromstring(record['statement_html'])
    def norm(s):
        s=' '.join((s or '').split())
        return re.sub(r'\d+(?:[.,]\d+)?',' NUM ',s) if mask_numbers else s
    def walk(e):
        tag=e.tag.split('}')[-1]
        if tag=='img': return ' IMAGE '
        math_tag=tag.startswith('m') and tag not in ('main','meta')
        body=' '.join([norm(e.text)]+[walk(c)+' '+norm(c.tail) for c in e if isinstance(c.tag,str)])
        return (' '+tag.upper()+' '+body+' END_'+tag.upper()+' ') if math_tag else body
    return ' '.join(walk(tree).split())
def task_template(record, mask=False):
    """Faithful report_fipi_extension.task_template; absent image mappings use explicit marker."""
    tree=html.fromstring(record['statement_html']); assets={Path(a['path']).name:a['sha256'] for a in record['assets']}
    def norm(s):
        s=' '.join((s or '').replace('\u200b','').split())
        return re.sub(r'\d+(?:[.,]\d+)?','#',s) if mask else s
    def walk(e):
        if e.tag=='img': return ('img',assets.get(Path(e.get('src','')).name,'MISSING:'+e.get('src','')))
        attrs=tuple((k,e.get(k)) for k in ('open','close','separators','mathvariant','accent','stretchy') if e.get(k) is not None)
        return (e.tag,attrs,norm(e.text),tuple((walk(c),norm(c.tail)) for c in e if isinstance(c.tag,str)))
    return hashlib.sha256(json.dumps([record['instruction'],walk(tree)],ensure_ascii=False).encode()).hexdigest()
def labels(record):
    return [v for m in record['metadata'] if m['label'].startswith('КЭС') for v in m['values']]
def class_label(record):
    """First-listed KES code, first two levels. Not primary topic, KC or student mastery."""
    ls=labels(record)
    return '.'.join(ls[0].split()[0].split('.')[:2]) if ls else '__missing__'
def template_groups(records, mask=True):
    groups=defaultdict(list)
    for r in records: groups[task_template(r,mask)].append(r['id'])
    return dict(sorted(groups.items()))
def make_split(records):
    groups=template_groups(records); keys=list(groups); random.Random(SEED).shuffle(keys)
    # Group-count allocation, not record stratification: retains rare/unseen labels honestly.
    n=len(keys); names=['train']*int(.7*n)+['dev']*int(.15*n)+['test']*(n-int(.7*n)-int(.15*n))
    split={k:[] for k in ('train','dev','test')}; assignments={}
    for key,name in zip(keys,names): split[name].extend(groups[key]); assignments[key]=name
    for v in split.values(): v.sort()
    return dict(seed=SEED,unit='numeric-template SHA256 groups',ratios=[.7,.15,.15],method='sorted group SHA; seeded shuffle; floor 70/15%, remainder test; no stratification',label_definition='first-listed KES code, first two levels; not main topic or KC',splits=split,template_assignments=assignments,classes={r['id']:class_label(r) for r in records},template_groups=groups)
def csvout(name,rows):
    if not rows: return
    with (OUT/name).open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
def main():
    OUT.mkdir(parents=True,exist_ok=True); records=load_bank(); split=make_split(records); dump(OUT/'split.json',split)
    rows=[]; assets={}; issues=[]; tags=Counter(); examples=[]; parser_messages=Counter()
    for r in records:
        tree=html.fromstring(r['statement_html']); text=extract_text(r); ct=Counter(e.tag for e in tree.iter() if isinstance(e.tag,str)); tags.update(ct)
        arity={'mfrac':2,'msup':2,'msub':2,'mroot':2,'msubsup':3}
        arity_bad=sum(len([c for c in e if isinstance(c.tag,str)])!=arity[e.tag] for e in tree.iter() if e.tag in arity)
        ls=labels(r); response=[v for m in r['metadata'] if m['label'].startswith('Тип ответа') for v in m['values']]
        imgs=tree.xpath('//img'); mapped={Path(a['path']).name for a in r['assets']}
        unknown=sum(Path(i.get('src','')).name not in mapped for i in imgs)
        parser=html.HTMLParser(); html.fromstring(r['statement_html'],parser=parser)
        parser_messages.update(e.message for e in parser.error_log)
        row=dict(task_id=r['id'],first_kes=ls[0] if ls else '',class_label=class_label(r),all_kes=' | '.join(ls),label_count=len(ls),response_type=' | '.join(response),text_chars=len(text),html_chars=len(r['statement_html']),mathml=ct['math'],math_nodes=sum(v for k,v in ct.items() if k.startswith('m')),images=len(imgs),asset_refs=len(r['assets']),replacement_chars=text.count('\ufffd'),zero_width=text.count('\u200b'),nbsp=r['statement_html'].count('\u00a0'),control_chars=sum(unicodedata.category(c)=='Cc' and c not in '\n\r\t' for c in text),empty_text=not bool(text),html_parser_diagnostics=len(parser.error_log),unmapped_images=unknown,mathml_count_mismatch=ct['math']!=r['mathml_count'],mathml_arity_candidates=arity_bad,source_issues=json.dumps(r['source_issues'],ensure_ascii=False),exam_year_missing=r.get('exam_year') is None,answer_missing=r.get('answer') is None,solution_missing=r.get('solution') is None,exact_sha=task_template(r),template_sha=task_template(r,True),source_url=r['source_url'])
        rows.append(row)
        for a in r['assets']: assets[a['path']]=a
        for tag in ('msqrt','msup','mfrac'):
            if ct[tag] and not any(x['tag']==tag for x in examples):
                e=tree.xpath('//'+tag)[0]; examples.append(dict(task_id=r['id'],tag=tag,mathml=html.tostring(e,encoding='unicode',with_tail=False),flattened=e.text_content(),semantic=semantic_tokens(dict(statement_html=html.tostring(e,encoding='unicode',with_tail=False))),source_url=r['source_url']))
    assetrows=[]
    for path,a in sorted(assets.items()):
        p=BANK/path; row=dict(path=path,exists=p.exists(),expected_sha=a['sha256'],actual_sha=sha(p) if p.exists() else '',hash_ok=p.exists() and sha(p)==a['sha256'],decode_ok=False,width=None,height=None,format=None,error='')
        try:
            with Image.open(p) as im: im.load(); row.update(decode_ok=True,width=im.width,height=im.height,format=im.format)
        except Exception as e: row['error']=str(e)
        assetrows.append(row)
    csvout('tasks.csv',rows); csvout('assets.csv',assetrows)
    csvout('html-parser-diagnostics.csv',[dict(message=k,count=v) for k,v in parser_messages.most_common()])
    assert set(assets)=={p.relative_to(BANK).as_posix() for p in (BANK/'assets').iterdir() if p.is_file()}, 'Unreferenced assets must also be inspected'
    multilabel=Counter(l for r in records for l in set(labels(r))); first=Counter(labels(r)[0] for r in records if labels(r))
    balance=[dict(label=k,all_label_tasks=multilabel[k],first_listed_tasks=first[k]) for k in sorted(multilabel)]
    csvout('label-balance.csv',balance)
    groups={kind:template_groups(records,mask) for kind,mask in [('exact',False),('numeric_template',True)]}
    csvout('duplicate-groups.csv',[dict(kind=k,sha=s,size=len(ids),task_ids=' '.join(ids)) for k,g in groups.items() for s,ids in g.items() if len(ids)>1])
    coverage=[]; train=Counter(split['classes'][i] for i in split['splits']['train'])
    for c in sorted(set(split['classes'].values())):
        counts={s:sum(split['classes'][i]==c for i in ids) for s,ids in split['splits'].items()}
        coverage.append(dict(class_label=c,**counts,unseen_in_train=not train[c],total=sum(counts.values()),test_singleton=counts['test']==1))
    csvout('split-coverage.csv',coverage)
    outliers=[]; stats={}
    for field in ('text_chars','html_chars','mathml','math_nodes','images'):
        vals=np.array([r[field] for r in rows]); med=float(np.median(vals)); mad=float(np.median(abs(vals-med))); p99=float(np.percentile(vals,99)); threshold=med+3*1.4826*mad
        stats[field]=dict(min=int(vals.min()),median=med,p99=p99,max=int(vals.max()),mad=mad,mad_threshold=threshold,mad_zero=mad==0,candidates_p99=int(sum(vals>p99)),candidates_mad=int(sum(vals>threshold)) if mad else None)
        for r in sorted(rows,key=lambda r:(-r[field],r['task_id']))[:5]: outliers.append(dict(metric=field,value=r[field],task_id=r['task_id'],source_url=r['source_url'],candidate_only=True))
    csvout('outlier-top5.csv',outliers); dump(OUT/'flatten-examples.json',examples)
    summary=dict(records=len(records),assets=len(assets),response_types=dict(Counter(r['response_type'] for r in rows)),all_kes_labels=len(multilabel),multilabel_tasks=sum(r['label_count']>1 for r in rows),label_assignments=sum(multilabel.values()),math_tags=dict(tags),tasks_with_images=sum(r['images']>0 for r in rows),tasks_with_mathml=sum(r['mathml']>0 for r in rows),quality={k:sum(bool(r[k]) for r in rows) for k in ('replacement_chars','zero_width','control_chars','empty_text','html_parser_diagnostics','unmapped_images','mathml_count_mismatch','mathml_arity_candidates','exam_year_missing','answer_missing','solution_missing')},source_issue_tasks=[r['id'] for r in records if r['source_issues']],asset_failures=sum(not(r['hash_ok'] and r['decode_ok']) for r in assetrows),length_statistics=stats,duplicates={k:dict(groups=len(g),repeated_groups=sum(len(ids)>1 for ids in g.values()),tasks_in_repeated_groups=sum(len(ids) for ids in g.values() if len(ids)>1)) for k,g in groups.items()},split_sizes={k:len(v) for k,v in split['splits'].items()},classes=len(coverage),unseen_test_classes=[r['class_label'] for r in coverage if r['test'] and r['unseen_in_train']],test_singleton_classes=[r['class_label'] for r in coverage if r['test_singleton']])
    dump(OUT/'summary.json',summary)
    source_paths=[BANK/'tasks.jsonl',BANK/'README.md',Path(__file__),ROOT/'scripts/report_fipi_extension.py']+list((BANK/'tasks').glob('*.json'))+list((BANK/'raw').glob('*.html'))+[BANK/p for p in assets]
    dump(OUT/'provenance.json',dict(source_url=records[0]['source_url'].split('&qid=')[0],snapshot='2026-10-31',license='Open access; redistribution license not established; local research snapshot',seed=SEED,hashes={p.relative_to(ROOT).as_posix():sha(p) for p in source_paths}))
    # Smoke invariants verify source copies, template nesting, disjoint exhaustive split.
    assert len(records)==1148 and len({r['id'] for r in records})==1148
    assert all(json.loads((BANK/'tasks'/f"{r['id']}.json").read_text(encoding='utf-8'))==r for r in records)
    partitions=[set(v) for v in split['splits'].values()]
    assert set.union(*partitions)=={r['id'] for r in records} and sum(map(len,partitions))==len(records)
    assert all(sum(bool(set(ids)&p) for p in partitions)==1 for g in groups.values() for ids in g.values())
    assert sum(multilabel.values())==sum(len(set(labels(r))) for r in records)
    assert summary['asset_failures']==0
    assert make_split(records)==split
    assert all(semantic_tokens(r) for r in records)
    dump(OUT/'smoke-tests.json',dict(status='pass',checks=['1148 unique IDs','JSONL equals individual JSON','split exhaustive/disjoint','exact and template groups never cross partitions','all multilabel assignments counted','all asset hashes and Pillow decode valid']))
    fig,ax=plt.subplots(figsize=(10,8)); ax.barh([r['label'].split()[0] for r in balance],[r['all_label_tasks'] for r in balance]); ax.set_xlabel('Tasks, all KES labels (multilabel); full names in CSV'); fig.tight_layout(); fig.savefig(OUT/'01-label-balance.png',dpi=140); plt.close(fig)
    fig,axs=plt.subplots(1,3,figsize=(12,3))
    for ax,f in zip(axs,['text_chars','mathml','images']): ax.hist([r[f] for r in rows],bins=30); ax.set_title(f); ax.set_yscale('log')
    fig.tight_layout(); fig.savefig(OUT/'02-structure.png',dpi=140); plt.close(fig)
    fig,ax=plt.subplots(figsize=(8,4)); ax.scatter([r['text_chars'] for r in rows],[r['mathml'] for r in rows],c=[r['images'] for r in rows],alpha=.4); ax.set(xlabel='Flattened text chars',ylabel='MathML formula count'); fig.tight_layout(); fig.savefig(OUT/'03-multimodal.png',dpi=140); plt.close(fig)
    fig,ax=plt.subplots(figsize=(10,5)); x=np.arange(len(coverage)); bottom=np.zeros(len(x))
    for s in ('train','dev','test'): v=np.array([r[s] for r in coverage]); ax.bar(x,v,bottom=bottom,label=s); bottom+=v
    ax.set_xticks(x,[r['class_label'] for r in coverage],rotation=90); ax.legend(); fig.tight_layout(); fig.savefig(OUT/'04-split-coverage.png',dpi=140); plt.close(fig)
    report(summary,examples)

def report(s,examples):
    lines=['# Доменный EDA сохранённого банка ФИПИ','',f"Измерены {s['records']} условий всей профильной математики: математический NLP с деревьями MathML и растровыми изображениями. Единица — условие задачи; метки КЭС являются метаданными источника, не KC и не свидетельствами освоения.",'','## Баланс и доступные данные','',f"Все метки: {s['all_kes_labels']} различных формулировок, {s['label_assignments']} назначений; {s['multilabel_tasks']} задач имеют несколько меток. `label-balance.csv` содержит все назначения и отдельно первую перечисленную метку. Первая метка не объявляется основной. Типы ответа: {s['response_types']}.",'','Для всех задач год экзамена, официальный ответ и решение отсутствуют. Дата снимка не задаёт год экзамена. Классификация условий по КЭС возможна; оценка правильности решений и диагностики ученика по этому банку невозможна.','', '## Представление и качество','',f"Изображения встречаются в {s['tasks_with_images']} задачах; MathML — в {s['tasks_with_mathml']}. Проверены существование, SHA256 и полное декодирование Pillow всех {s['assets']} уникальных файлов: ошибок {s['asset_failures']}. Это проверка файлов, не полноты рисунка и не математического смысла.",f"Измеренные индикаторы по числу задач: `{s['quality']}`. Сохранённые source_issues: {s['source_issue_tasks']}. `html-parser-diagnostics.csv` раскрывает сообщения: lxml HTML4 сообщает об HTML5 section и MathML как неизвестных тегах во всех условиях; это не 1148 дефектов источника. Проверка HTML является диагностикой восстанавливающего парсера lxml, а не доказательством валидности или браузерного рендера; нулевые предупреждения не означают отсутствие смысловых опечаток. Unicode replacement символ — кандидат для просмотра, в 697AC9 он ранее подтверждён в источнике. NBSP сохранён в таблице как нормальная типографика.",'','`tasks.csv` содержит длины, пустоты, Unicode, формулы и картинки, согласованность числа MathML и арность mfrac/msup/msub/mroot/msubsup; `assets.csv` — проверки каждого файла. Ограничение: растр остаётся непрочитанным, OCR и полная предметная экспертиза не проводились.','', '## Формулы и потеря структуры','']
    for e in examples: lines += [f"- {e['task_id']}, `{e['tag']}`: flatten `{e['flattened'].strip()}`; структурно `{e['semantic']}`."]
    lines += ['','При flatten исчезают границы радикала, числителя/знаменателя и основания/показателя. `semantic_tokens` сохраняет названия и закрытия MathML-узлов; изображение обозначается IMAGE. Эти токены дают структурные признаки, но не распознают рисунок. Метаданные КЭС и ответы не включаются в представление.','', '## Повторы и фиксированное разбиение','',f"Группы: `{s['duplicates']}`. Точное совпадение — нормализованный DOM, инструкция, SHA рисунков; numeric-template дополнительно маскирует числа в текстовых узлах, включая MathML. Это эвристика, не доказательство одинакового метода; изменение рисунка создаёт отдельную группу. Пробелы и zero-width нормализуются как в report_fipi_extension.task_template. Отсутствующая привязка картинки кодируется явным MISSING-маркером; такое условие требует просмотра.",f"До обучения задан seed {SEED}; сортированные SHA групп перемешаны и разделены 70/15/15% по числу групп, без подбора seed по качеству. Числа задач: {s['split_sizes']}. Ни exact-, ни numeric-template-группа не пересекает части. Стратификации нет; редкие классы не удалены.",f"Downstream цель — первый перечисленный код КЭС до двух уровней, не основная тема. Всего классов {s['classes']}; классы test, отсутствующие в train: {s['unseen_test_classes']}; с одной test-задачей: {s['test_singleton_classes']}. Полная coverage в split-coverage.csv; выводы по малым классам ненадёжны. Разбиение не исключает более глубокого семантического сходства разных шаблонов.",'', '## Структурные выбросы и применение','', 'Для длины текста/HTML, числа формул/MathML-узлов/картинок рассчитаны p99 и median + 3 × 1.4826 MAD (`summary.json`). При нулевом MAD флаг по MAD не применяется. `outlier-top5.csv` содержит пять максимальных значений каждого признака с ID и URL. Это кандидаты для просмотра: длинное условие или несколько рисунков не являются ошибками.', '', 'В тьюторе результаты помогут сохранить формулы при индексации, маршрутизировать задачи с рисунками на визуальный просмотр и проверять источники перед учебным использованием. Баланс КЭС задаёт охват банка и дефициты примеров, но не учебный граф навыков. Групповое разбиение пригодно для честного первичного baseline и абляции представлений; текущий EDA сам модель не обучает. Проверки Unicode и структуры пригодны как входной контроль новых источников, с отдельной содержательной проверкой помеченных условий.','', '## Происхождение и воспроизведение','', 'Источник — сохранённый снимок открытого банка ФИПИ от 31.10.2026, URL и хеши исходных страниц, JSON, изображений и кода находятся в provenance.json. Открытый доступ не устанавливает лицензию на массовое распространение; условия повторного использования не подтверждены, материалы исследуются локально. Новые задачи, решения и разметка не создавались.', '', 'Команда: `.venv/Scripts/python.exe -B -X utf8 scripts/fipi_domain_quality.py`. Все входы только читаются. Smoke-инварианты сохранены в smoke-tests.json; графики 01–04 и CSV воспроизводимы.']
    (OUT/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
if __name__=='__main__': main()
