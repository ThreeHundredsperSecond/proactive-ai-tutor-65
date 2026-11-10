"""Refresh the approved notebook structure from the pinned 315 saved records."""
import csv
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SAVED = ROOT/'data/annotation/analyses/2026-11-10-saved-data-refresh-v1'


def read(p):
    return json.loads(Path(p).read_text(encoding='utf-8'))


def current_families(data, out):
    import fipi_domain_quality as domain
    import report_fipi_extension as report
    assignments={(a['task_id'],a['local_id']):a['canonical_id'] for a in data['catalog']['assignments']}
    tasks=[];support={n['id']:set() for n in data['catalog']['nodes']};families={k:set() for k in support}
    for row in data['baseline']+data['new']:
        if not row['included']:continue
        family=domain.task_template(row['input'],mask=True)
        tasks.append(dict(task_id=row['task_id'],origin=row['origin'],family=family))
        for cid in set(report.mapping(row,assignments).values()):
            support[cid].add(row['task_id']);families[cid].add(family)
    rows=[dict(catalog_kc_id=k,task_frequency=len(support[k]),family_frequency=len(families[k])) for k in sorted(support)]
    assert len(tasks)==312
    summary=dict(included_tasks=len(tasks),families=len({r['family'] for r in tasks}),catalog_nodes=len(rows),
        support_bins={b:sum((r['family_frequency']==int(b) if b!='>=3' else r['family_frequency']>=3) for r in rows) for b in ['0','1','2','>=3']},
        linear_equation=next(r for r in rows if r['catalog_kc_id']=='linear_equation'))
    (out/'current-kc-family-summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    for name,values in [('current-kc-family-frequency.csv',rows),('current-kc-family-tasks.csv',tasks)]:
        with (out/name).open('w',encoding='utf-8-sig',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(values[0]));w.writeheader();w.writerows(values)
    return summary,rows


def analyze_current():
    import build_checkpoint2 as build
    import fipi_team_checkpoint250 as previous
    import report_fipi_extension as report
    _, _, _, bank_stats, bank, _ = build.analyze()
    prior = previous.collect(strict=True)
    records = {r['task_id']:r for r in prior['baseline']+prior['new']}
    manifest = read(SAVED/'manifest.json')
    for m in manifest:
        if m['task_id'] in records:
            continue
        tid = m['task_id']
        inp = read(ROOT/m['source_run']/'inputs/tasks'/f'{tid}.json')
        codes = [v.split()[0] for item in inp['metadata'] if item['label']=='КЭС:' for v in item['values']]
        records[tid] = dict(m, input=inp, author=read(ROOT/m['author_path']), audit=read(ROOT/m['auditor_path']),
            layer='audited_new', complete=True, author_mode='standalone_initial', primary_kes=codes[0],
            response_type=next(item['values'][0] for item in inp['metadata'] if item['label']=='Тип ответа:'),
            source_policy_included=m['included'], technical_errors=[])
    rows = [records[m['task_id']] for m in manifest]
    assert len(rows)==len({r['task_id'] for r in rows})==315
    for r,m in zip(rows,manifest):
        assert r['included']==m['included'] and r['exclusion_reasons']==m['exclusion_reasons']
    data = dict(baseline=rows[:50],new=rows[50:],catalog=prior['catalog'])
    summary,tables = report.metrics(data)
    summary = json.loads(json.dumps(summary))
    assert summary['mixed_cumulative']==read(SAVED/'summary.json')['populations']['published315']
    # Recompute rather than merely relabel the primary tables. Match frozen exports.
    for name in ['frequencies','cooccurrence','transitions','tasks','composition','audit_statuses']:
        with (SAVED/'tables'/f'{name}.csv').open(encoding='utf-8-sig',newline='') as f:
            expected=list(csv.DictReader(f))
        actual=[{k:str(v) for k,v in r.items()} for r in tables[name] if r['population']=='mixed_cumulative']
        assert actual==expected, name
    for name,values in tables.items():
        with (build.OUT/f'{name}.csv').open('w',encoding='utf-8-sig',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(values[0]));w.writeheader();w.writerows(values)
    current_families(data,build.OUT)
    (build.OUT/'summary.json').write_text(json.dumps(dict(bank=bank_stats,populations=summary,
        selected_n=315,included_n=312,scope='Main EDA on pinned saved315; strict solved/nonblocking policy'),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    composition=[]
    bank_by_id={r['id']:r for r in bank}
    def primary(inp):
        return next(m['values'][0].split()[0] for m in inp['metadata'] if m['label']=='КЭС:')
    all_codes=sorted({primary(r) for r in bank})
    for label,inputs in [('Банк, n=1148',bank),('Исходные 100',[bank_by_id[r['task_id']] for r in rows[:100]]),
                         ('Добавленные 215',[bank_by_id[r['task_id']] for r in rows[100:]]),('Все 315',[r['input'] for r in rows])]:
        counts=Counter(primary(r) for r in inputs)
        composition.extend(dict(layer=label,code=c,tasks=counts[c],percent=100*counts[c]/len(inputs)) for c in all_codes)
    p=build.OUT/'provenance.json';provenance=read(p)
    exports=read(SAVED/'tables-provenance.json')
    provenance['input_hashes'].update(exports['input_hashes'])
    provenance['input_hashes'].update(exports['outputs'])
    for path in [Path(__file__),ROOT/'scripts/fipi_domain_quality.py',SAVED/'manifest.json',SAVED/'summary.json']:
        provenance['input_hashes'][path.relative_to(ROOT).as_posix()]=hashlib.sha256(path.read_bytes()).hexdigest()
    provenance['scope']='Main quantitative EDA: pinned saved315/included312; qualitative subset12 remains fixed'
    p.write_text(json.dumps(provenance,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return data,summary,tables,bank_stats,bank,composition


def update_cells(cells):
    """Keep chapter order and explanatory argument; replace quantitative cells in place."""
    def setcell(i,s):cells[i].source=s.strip()
    def replace(i,a,b):
        assert a in cells[i].source,(i,a)
        cells[i].source=cells[i].source.replace(a,b)
    # The heading and questions remain the opening, without dated append-only banners.
    s=cells[0].source
    s=s[s.index('# EDA.'):]
    s=s.replace('5 ноября 2026.','10 ноября 2026.')
    s=s.replace('**Объём:** 1148 условий банка; 100 задач с предварительными разборами; 98 задач в основных частотах. Последующий качественный разбор использует 19 из этих задач, в том числе все 12 принятых применений линейного уравнения. Это вложенные, а не складываемые объёмы.',
        '**Объём:** 1148 условий банка; **315 уникальных задач с предварительными разборами; 312 задач в основных частотах**. Состав: исходные 100 + первые дополнительные 100 Богдана + 50 Sol + следующие 65 Богдана. Все основные количественные графики разделов 3–6 пересчитаны на этом наборе. Качественный разбор в разделе 8 сохраняет отдельную подвыборку 19 исторических задач, включая 12 применений линейного уравнения; эти объёмы не складываются с 315.')
    s=s.replace('Как отобраны 100 задач','Как сформирован набор из 315 задач').replace('#3-как-отобраны-100-задач','#3-как-сформирован-набор-из-315-задач').replace('Отбор 100 задач и распределение по темам ФИПИ.','Происхождение 315 задач и распределение по темам ФИПИ.')
    setcell(0,s)
    replace(1,'к текущим 100 ФИПИ','к текущим 315 ФИПИ')
    replace(1,'| Содержательное продолжение EDA |','| Расширение 100→315 | Сохранённые 100 Богдана, 50 Sol и следующие 65 Богдана; единая политика включения и пересчёт | 315 уникальных задач, 312 в частотах; раздельное происхождение | Различаются состав и процедуры; новые 65 опубликованы в отдельной, ещё не слитой ветке |\n| Содержательное продолжение EDA |')
    replace(2,'Разобраны 100 задач в два этапа по 50: сначала пилот для отработки представления шагов и KC, затем расширение с агентным аудитом и промежуточными проверками партий.',
        'Сохранены разборы 315 уникальных задач: пилот 50, историческое независимое дополнение 50, первые дополнительные 100 Богдана, 50 Sol и следующие 65 Богдана. После пилота разборы имеют агентный аудит и проверки партий; источник и процедура сохранены отдельно.')
    replace(5,'from build_checkpoint2 import analyze, integrated_inputs, OUT, BASE, EXT','from build_checkpoint2 import integrated_inputs, OUT, BASE, EXT\nfrom checkpoint2_current import analyze_current')
    replace(5,'composition=analyze()','composition=analyze_current()')
    replace(5,'Пересчитаны банк и 100 разборов; основные показатели по 98.','Пересчитаны банк и 315 разборов; основные показатели по 312.')
    replace(10,'## 3. Как отобраны 100 задач','## 3. Как сформирован набор из 315 задач')
    replace(10,'Выполнены только первые 50: партии 15+15+15+5 с проверками.','В историческом дополнении выполнены первые 50: партии 15+15+15+5 с проверками.')
    cells[10].source+='\n\nЗатем добавлены сохранённые 100 Богдана из первого командного дополнения, 50 Sol и следующие 65 Богдана из коммита `2937b04`. ID не пересекаются: всего 315. Следующие 35 ID брони Богдана ещё без разборов и в анализ не входят. Новые 65 происходят из отдельной, ещё не слитой ветки; [манифест 315](../../data/annotation/analyses/2026-11-10-saved-data-refresh-v1/manifest.json) сохраняет источники и активные попытки. Совокупный набор также не является простой случайной выборкой банка.'
    # composition code already consumes runtime data; correct its surrounding prose.
    setcell(12,'''**Как читать график состава.** По горизонтали — первые метки КЭС. Четыре столбца показывают доли в банке 1148, исходных 100, добавленных 215 и всех 315 задачах. Высота вычисляется внутри своей группы; различие столбцов означает разный состав, а не изменение программы экзамена.

**Зачем это учитывать дальше.** Пилот отбирался для разнообразия, последующие слои — отдельными очередями. Частота KC означает число задач с таким назначением в нашем наборе, а не вероятность встретить умение на экзамене. Форматы ответа и точные объёмы текущего набора показаны ниже.''')
    cells[11].source+="\ntable([{'Формат ответа':typ,'Задач из 315':sum(r['response_type']==typ for r in tables['tasks'] if r['population']=='mixed_cumulative')} for typ in ['Краткий ответ','Развернутый ответ']])"
    replace(13,'100 задачах','315 задачах');replace(13,'из наших 100','из наших 315')
    for a,b in [('==100','==315'),('sample_size\':100','sample_size\':315'),('из 100','из 315'),('100 разобранных','315 разобранных'),('превышать 100','превышать 315'),('topic-memberships-100.csv','topic-memberships-315.csv'),('topic-distribution-100.csv','topic-distribution-315.csv')]:
        cells[14].source=cells[14].source.replace(a,b)
    replace(15,'В исходных файлах есть 100 разборов. Для подсчёта повторяемости действий использованы 98 - по 49 из каждой части. Две задачи сохранены, но не участвуют в основных частотах:',
        'В исходных файлах есть 315 разборов. По единому правилу завершённого решения без блокирующего замечания в основные частоты входят 312. Три задачи сохранены, но исключены:')
    replace(15,'Исключение означает,','- **321FCD:** в исходном ответе сохранён статус `partial`; по общей политике задача исключена, хотя источник допускал её после просмотра.\n\nДля **0B2322** остаётся спорное чтение графика: основной срез включает её по сохранённому неблокирующему вердикту, отдельная проверка чувствительности без неё использует 311 задач.\n\nИсключение означает,')
    replace(15,'Число 98 описывает','Число 312 описывает')
    setcell(16,'''keys=[('baseline50','Пилот 50'),('new_accumulated','Дополнительные 265'),('mixed_cumulative','Все 315')]
table([{'Слой':label,'Разборов':summary[k]['selected_n'],'В частотах':summary[k]['included_n'],
        'Определений KC с назначениями':summary[k]['confirmed_catalog_nodes'],
        'Встречаются только в одной задаче':f"{summary[k]['singleton_nodes']['numerator']}/{summary[k]['singleton_nodes']['denominator']}"} for k,label in keys])
table([{'Формат':typ,'Задач':summary['mixed_cumulative']['structure'][typ]['steps']['n'],
        'Медиана шагов':summary['mixed_cumulative']['structure'][typ]['steps']['median'],
        'Медиана кандидатов KC':summary['mixed_cumulative']['structure'][typ]['kc_candidates']['median']}
       for typ in ['Краткий ответ','Развернутый ответ']])
fig,axes=plt.subplots(1,2,figsize=(11,3.5))
for ax,(field,label) in zip(axes,[('steps','Шагов'),('kc_candidates','Кандидатов KC')]):
    dist=summary['mixed_cumulative']['structure']['all'][field]['distribution'];xs=sorted(map(int,dist))
    ax.bar(xs,[dist[str(x)] for x in xs],color='#087e8b');ax.set_title(label+': 312 включённых разборов');ax.set_xlabel(label+' в разборе');ax.set_ylabel('Задач')
chart('03-step-counts')''')
    # Replace only the numeric interpretation, keeping the project argument below.
    s=cells[17].source
    s='''**Что получилось.** Среди 312 включённых разборов медиана — 3 шага и 4 кандидата KC. Для краткого ответа (187 задач) медианы равны 3 шагам и 3 кандидатам; для развёрнутого (125 задач) — 5 и 5. Эти значения описывают сохранённые записи, включая различия детализации авторов, а не измеренную трудность задач.

'''+s[s.index('**Что это даёт проекту.**'):]
    s=s.replace('Например, частота 12 для линейного уравнения означает 12 задач с таким назначением, а не 12 уравнений или 12 ученических попыток.',
        'Например, частота 27 для линейного уравнения означает 27 задач с таким назначением, а не 27 уравнений или ученических попыток.')
    s=s[:s.index('**Как читать таблицу и график.**')]+'''**Как читать таблицу и график.** Таблица содержит десять наиболее частых определений среди 312 задач. На графике — восемь из них: K1–K8 расшифрованы под ним. Показаны доли в пилоте (49 включённых), последующих 265 задачах (263 включённых) и всех 312. Различия описательны: темы, исполнители и процедуры смешаны.'''
    setcell(17,s)
    cells[18].source=cells[18].source.replace('Задач / 98','Задач / 312')
    s=cells[19].source
    s='''**Какие повторения нашли.** Линейное уравнение связано с 27 из 312 включённых задач. В исторической сотне таких задач было 12; их подробное качественное сопоставление сохранено в разделе 8 как отдельная подвыборка. В разных темах встречается одно действие, но подготовка и роль результата могут различаться.

**Что изменилось с расширением.** Наблюдаемых определений каталога стало 139 против 138 в исходных 100; сам каталог сохраняет 144 определения. Одной задачей поддержаны 45 из 139 наблюдаемых узлов (32,4%), прежде — 76 из 138 (55,1%). От последних 65 число наблюдаемых узлов не выросло (139→139): они преимущественно добавили примеры к существующим назначениям. Это не доказывает полноту сопоставления всех действий; она рассматривается отдельно.

'''+s[s.index('### Какие действия встречаются вместе'):]
    setcell(19,s)
    cells[20].source=cells[20].source.replace('n=98','n=312').replace('Задач / 98','Задач / 312')
    # Counts in this paragraph are emitted from the same computed pair tables.
    setcell(21,'''**Что видно на данных.** Точные частоты сочетаний и переходов вычисляются ниже из тех же 312 задач. Считывание координат и составление уравнения пересечения описывают разные действия одного маршрута, а не одно общее умение.

**Как использовать этот результат.** Сочетания помогают разбирать упражнение на отдельные цели: чтение рисунка, восстановление функции, составление уравнения. Это основания для поиска материала и будущей проверки шага, а не результаты диагностики ученика.

Матрица отвечает на вопрос «встречаются ли действия вместе», таблица — «в каком порядке они записаны». Они не устанавливают обязательный порядок обучения; ноль означает отсутствие принятой пары в этих 312 разборах, в том числе из-за неполного сопоставления.''')
    cells[20].source+='\ndisplay(Markdown("**Пример сочетания:** чтение координат и уравнение пересечения — "+str(co.get(tuple(sorted(("graph_coordinates","graph_intersection"))),0))+" задач из 312."))'
    cells[22].source=cells[22].source.replace('из 98 задач','из 312 задач').replace('этих 98','этих 312')
    for a,b in [('==98','==312'),('task-topic-kc-98.csv','task-topic-kc-312.csv'),('topic-kc-98.csv','topic-kc-312.csv'),('98 включённых','312 включённых'),('в 12 разных','в 27 разных'),('больше 12','больше 27')]:cells[23].source=cells[23].source.replace(a,b)
    replace(25,'Для дополнительных 50 задач','Для дополнительных 265 задач')
    s=cells[25].source
    s=s[:s.index('**Что показывает график.**')]+'''**Что показывает график.** В дополнительных 265 разборах есть 1011 кандидатов KC и столько же решений аудиторов. График учитывает все эти аудиты, включая две задачи, исключённые из частот.

Для основных частот отдельно учитываются 263 включённые дополнительные задачи. Пилотные назначения редакторские и не выдаются за независимый аудит. Разница между объёмом аудита и допущенной разметкой указана в выводах ниже.'''
    setcell(25,s)
    cells[26].source=cells[26].source.replace('ax.set_xlim(0,110)','ax.set_xlim(0,max(v[\'numerator\'] for v in vs)*1.15)').replace('Кандидатов из 199','Кандидатов из 1011').replace('199 описаний','1011 описаний')
    s=cells[27].source
    s='''**Что получилось.** Из 1011 описаний дополнительных задач аудиты отметили 373 полных соответствия, 376 новых предложений, 200 составных описаний и 62 спорных соответствия. Новое предложение не равно новому уникальному умению: повторяющиеся предложения ещё не объединены.

В 263 включённых дополнительных задачах находятся 1007 кандидатов; 635 не получили полного соответствия (63,1%). Хотя бы один такой случай есть в 239 из 263 задач. Это неполнота связи с каталогом, а не число неправильных решений. В последних 65 полностью сопоставлены только четыре задачи; поэтому рост корпуса не означает автоматическую готовность разметки для тьютора.

'''+s[s.index('### Три примера:'):]
    setcell(27,s)
    replace(29,'Дополнительные 50 задач обрабатывались партиями 15+15+15+5.','Исторические дополнительные 50 обрабатывались партиями 15+15+15+5; следующие слои также имеют сохранённые проверки партий и отдельные источники.')
    replace(29,'остальные 48 включённых дополнительных задач имеют первоначальные авторские ответы.','в историческом дополнении остальные 48 включённых задач имеют первоначальные авторские ответы. В Sol50 выбрана отдельная техническая коррекция `9c96c5`; исходник сохранён. Источник новых 65 сообщает о перезаписи двух ответов до публикации, поэтому история их первоначальных версий недоступна.')
    replace(29,'| eFF32e |','| 0B2322 | В новых 65 не разрешено чтение точки на графике: ответ 2 или 3; аудит не блокировал включение | Нужна предметная сверка; показан также срез без задачи (311) |\n| 321FCD | В первом дополнении Богдана авторский статус partial | Единая политика исключает задачу независимо от исходного допуска |\n| eFF32e |')
    replace(30,'**Метод продолжения:** все 12 включённых задач с принятым linear_equation',
        '**Границы качественного продолжения:** из 27 текущих задач с linear_equation подробно описаны исторические 12 из исходной сотни. Этот фиксированный разбор не расширялся на новые задачи. **Метод:** эти 12 задач')
    replace(32,'В разделе 5 линейное уравнение встретилось в 12 задачах разных тем.','В разделе 5 линейное уравнение встретилось в 27 задачах разных тем; здесь подробно рассматриваются исторические 12.')
    replace(32,'на **всех 12 задачах с назначением linear_equation**, а не только на выбранных примерах.',
        'на **12 задачах с назначением linear_equation из исторической сотни**. Это качественная подвыборка; выводы о подготовке не пересчитаны как доли всех 27 текущих назначений.')
    replace(33,'Что предшествует решению линейного уравнения в 12 задачах','Историческая подвыборка: подготовка в 12 из 27 задач с линейным уравнением')
    replace(34,'Линейное уравнение назначено в 12 задачах;','Линейное уравнение назначено в 27 из 312 задач;')
    replace(34,'У 110 из 197 кандидатов включённых разборов нет полного соответствия;','В 263 дополнительных включённых задачах у 635 из 1007 кандидатов нет полного соответствия;')
    replace(34,'Частоты описывают выбранные 100 задач и 98 включённых разборов.','Частоты описывают 315 сохранённых задач и 312 включённых разборов.')
    replace(34,'Состав и метрики 100 задач','Состав и метрики 315 задач')
    replace(34,'[Зафиксированный отчёт](../../docs/eda/05-analysis/fipi-100-checkpoint.md)',
        '[Текущий состав](../../data/annotation/analyses/2026-11-10-saved-data-refresh-v1/manifest.json), [исторические 100](../../docs/eda/05-analysis/fipi-100-checkpoint.md)')
    for a,b in [('topic-distribution-100.csv','topic-distribution-315.csv'),('topic-memberships-100.csv','topic-memberships-315.csv'),('topic-kc-98.csv','topic-kc-312.csv'),('task-topic-kc-98.csv','task-topic-kc-312.csv')]:cells[34].source=cells[34].source.replace(a,b)
    # Neutral description of the accumulated corpus; provenance remains in source manifests.
    for c in cells:
        if c.cell_type!='markdown':continue
        c.source=c.source.replace('первые дополнительные 100 Богдана','дополнительные 100').replace('следующие 65 Богдана','ещё 65')
        c.source=c.source.replace('первые 100 Богдана','дополнительные 100').replace('100 Богдана','100 задач').replace('65 Богдана','65 задач')
        c.source=c.source.replace('50 Sol','ещё 50').replace('Sol50','дополнении 50')
        c.source=c.source.replace('Следующие 35 ID брони Богдана ещё без разборов и в анализ не входят. ','')
        c.source=c.source.replace('Новые 65 происходят из отдельной, ещё не слитой ветки; ','')
        c.source=c.source.replace('Источник новых 65 сообщает о перезаписи двух ответов до публикации, поэтому история их первоначальных версий недоступна.','У двух ответов последнего дополнения история первоначальных версий недоступна; сохранены опубликованные файлы.')
        c.source=c.source.replace('Богдана','участника')
    return cells


def verify_current(root):
    """Check actual primary tables, cohort IDs, archived original and chapter order."""
    root=Path(root);out=root/'notebooks/checkpoint-2/derived'
    manifest=read(SAVED/'manifest.json');ids={r['task_id'] for r in manifest}
    def csvrows(p):
        with p.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
    tasks=[r for r in csvrows(out/'tasks.csv') if r['population']=='mixed_cumulative']
    assert len(tasks)==len({r['task_id'] for r in tasks})==315 and {r['task_id'] for r in tasks}==ids
    assert sum(r['included']=='True' for r in tasks)==312
    for name in ['frequencies','cooccurrence','transitions','tasks','composition','audit_statuses']:
        rows=[r for r in csvrows(out/f'{name}.csv') if r['population']=='mixed_cumulative']
        assert rows==csvrows(SAVED/'tables'/f'{name}.csv'), name
    current=read(out/'summary.json')
    assert current['populations']['mixed_cumulative']==read(SAVED/'summary.json')['populations']['published315']
    memberships=csvrows(out/'topic-memberships-315.csv')
    assert {r['task_id'] for r in memberships}==ids
    assert all(int(r['sample_size'])==315 for r in csvrows(out/'topic-distribution-315.csv'))
    links=csvrows(out/'task-topic-kc-312.csv')
    assert {r['task_id'] for r in links}<={r['task_id'] for r in tasks if r['included']=='True'}
    assert len(links)==len({(r['task_id'],r['topic_code'],r['catalog_kc_id']) for r in links})
    family_tasks=csvrows(out/'current-kc-family-tasks.csv')
    assert len(family_tasks)==312 and {r['task_id'] for r in family_tasks}=={r['task_id'] for r in tasks if r['included']=='True'}
    checked=0
    for directory in ['checkpoint-2-100-8119f21','checkpoint-2-250-before-2026-11-10']:
        for row in read(root/'research/archive'/directory/'manifest.json')['files']:
            assert hashlib.sha256((root/row['snapshot_path']).read_bytes()).hexdigest()==row['sha256'];checked+=1
    archive=root/'research/archive/checkpoint-2-100-8119f21/notebooks/checkpoint-2/EDA.ipynb'
    old=read(archive);new=read(root/'notebooks/checkpoint-2/EDA.ipynb')
    source=lambda c:''.join(c['source'])
    headings=lambda n:[m.group(1) for c in n['cells'] for m in re.finditer(r'^## (\d+)\. (.*)',source(c),re.MULTILINE)]
    assert headings(old)==headings(new)[:10]==[str(i) for i in range(1,11)]
    for i in [3,4,6,7,8,9,24,28,31]:assert source(old['cells'][i])==source(new['cells'][i]),i
    assert '315 уникальных' in source(new['cells'][0]) and '312 задач в основных частотах' in source(new['cells'][0])
    assert '635 из 1007' in source(new['cells'][34])
    assert current['populations']['new_accumulated']['unmatched_local_candidates']==dict(numerator=635,denominator=1007)
    import base64
    for index in [11,14,16,18,20,23,26]:
        cell=new['cells'][index]
        filename=re.search(r"chart\('([^']+)'\)",source(cell)).group(1)+'.png'
        images=[o['data']['image/png'] for o in cell['outputs'] if 'image/png' in o.get('data',{})]
        assert len(images)==1
        assert base64.b64decode(''.join(images[0]))==(out/filename).read_bytes(),filename
    return dict(original100_archived=True,archive_files_verified=checked,approved_chapter_order_preserved=True,
        main_selected=315,main_included=312,current_table_exports_exact=True,topic_ids_checked=True,
        quantitative_figures_match_current_files=7,qualitative_linear_subset=12,total_linear_assignments=27)
