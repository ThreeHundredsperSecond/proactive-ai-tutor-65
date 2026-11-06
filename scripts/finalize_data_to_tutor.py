"""Create readable conclusions/notebook and verify a saved analysis by replay."""
from pathlib import Path
import json
import os
import re
import sys
from urllib.parse import unquote,urlsplit

import analyze_data_to_tutor as a


def finish():
    out=a.OUT;manifest=a.read(out/'manifest.json');s=a.read(out/'summary.json')
    assert manifest['phase']=='complete'
    data,rows,summary,_=a.load()
    names,edges,chains,profiles,foci,stats=a.derive(data,rows)
    descriptions=[]
    for f in s['foci']:
        by={m['layer']:m for m in f['metrics']};m=by['mixed']
        descriptions.append(f"| {f['name']} | {by[a.LAYERS[0]]['tasks']} | {by[a.LAYERS[1]]['tasks']} | {m['tasks']} | {m['first_kes_n']} | {m['short']} / {m['extended']} |")
    text='''# От данных к материалам тьютора: результат

Предварительное описательное исследование, 4 ноября 2026. Только сохранённые 100 разборов; основные частоты по 98. Новых решений, аудитов, ответов учеников и изменений каталога нет.

[Открыть картинки, условия и карточки](index.html) · [Исполненный ноутбук](review.ipynb) · [Протокол до запуска](PROTOCOL.md) · [Проверки](checks/final.json)

## 1. Что связывает задачи

| Принятое действие | Исходные / 49 | Новые / 49 | Вместе / 98 | Разных первых КЭС | Краткие / развёрнутые |
|---|---:|---:|---:|---:|---:|
'''+ '\n'.join(descriptions)+'''

Первый фокус задан заранее: линейное уравнение. Два следующих выбраны по числу задач среди узлов с минимум тремя задачами и назначениями в обоих слоях; при равенстве — по ID. На всех трёх графах показаны все связанные задачи: 12, 9 и 7 соответственно. Некоторые задачи входят в несколько фокусов, эти числа нельзя складывать как число разных задач.

У линейного уравнения есть задания с разными метками содержания, восемь кратких и четыре развёрнутых. Это даёт список кандидатов для смены контекста практики одного принятого действия. В задаче 19FBCF к уравнению приходят после приведения степеней, в 91CD43 — после перехода от равенства логарифмов к аргументам, в 8B91B1 и D334F2 — после построения кредитной модели. Последние примеры показывают: общее действие не означает общий полный метод.

Разнообразие КЭС описывает метаданные банка, а не измеренный перенос навыка. Назначения имеют разное происхождение: историческая редакторская версия и независимый агентный аудит. Большая частота рационального преобразования среди новых задач не устанавливает причинный эффект промпта или распространённость этого действия во всём банке.

### Графы принятых связей

'''+ '\n\n'.join(f"![{f['name']}](figures/graph-{f['id']}.png)" for f in s['foci'])+'''

## 2. Что видно в последовательностях

Показаны четыре цепочки из первого фокуса: 19FBCF (историческая), 8B91B1 (новая), 91CD43 и D334F2 (ещё две новые с неполными назначениями), по заранее записанному порядку ID. Полная таблица шагов и контекста — [chains.csv](tables/chains.csv). Несколько KC в шаге — неупорядоченная группа; разные Method не соединяются.

Среди 12 фокусных задач переход «равенство показателей → линейное уравнение» наблюдается в двух задачах; «равенство аргументов логарифмов → линейное уравнение» — также в двух. Остальные показанные направленные пары имеют по одной задаче. Это конкретные наблюдения, а не устойчивый граф prerequisite. [Все соседние пары с ID](tables/focus-transitions.csv).

{ADJACENT_RESULT} Здесь учитывается именно соседний шаг, содержащий неназначенного кандидата; неполнота внутри самого фокусного шага отмечается на схемах отдельно. Пропуски не удаляются, рёбра через них не достраиваются.

Особенно показателен 91CD43: в s3 решено 8−x=2 и проверено x<8. Назначение linear_equation принято для kc3, проверка допустимости kc4 остаётся без полного назначения. Схема сохраняет обе операции. В 8B91B1 исходные шаги построения модели остаются неназначенными, даже если позднейшее линейное уравнение сопоставлено.

'''+ '\n\n'.join(f'![Сохранённые шаги {tid}](figures/chain-{tid}.png)' for tid in manifest['chain_task_ids'])+'''

## 3. Где связи неполны

| Слой включённых задач | Все кандидаты назначены | Часть | Ни одного | Знаменатель |
|---|---:|---:|---:|---:|
| Исторические редакторские связи | 49 | 0 | 0 | 49 |
| Новые независимые аудиты | 4 | 35 | 10 | 49 |

![Полнота назначений](figures/mapping-completeness.png)

Эта разница **не означает**, что старые решения правильнее. Пилотный каталог построен по исходным кандидатам с редакторскими назначениями; для новых используется замороженный каталог и отдельная процедура. Полнота назначения не проверяет математику и не означает пригодность учебного эталона. В 10 новых включённых задачах ноль принятых назначений, но это не отсутствие математических действий.

Без полного назначения остаются 110/197 кандидатов включённых новых задач; статусы всех новых 50 используют другой знаменатель — 199. [Статусы с отдельными знаменателями](tables/unmatched-statuses.csv), [профиль всех 100 задач и исключения](tables/profiles.csv).

Причины иллюстрируются сохранёнными случаями, а не новой классификацией корпуса:

- [68Ac00](cards/68Ac00.html): составной кандидат соединяет решение уравнения и выбор именованной точки; части не назначаются автоматически.
- [F6158A](cards/F6158A.html): два определения перекрываются на одном действии, однозначный ID не выбран.
- [F416AF](cards/F416AF.html): исправлено чтение изображения с обратной связью, первоначальный автор и аудитор ошибку пропустили. Активная исправленная версия не является независимым повтором.
- [C41083](cards/C41083.html): блокирующий вердикт о предположении независимости; задача исключена из основных частот. Исторический eFF32e также исключён по прежней политике. Эти признаки могут пересекаться с неполными связями, их нельзя складывать в единый процент качества.

## Что это даёт следующему этапу

1. **Для подбора упражнений:** готов список конкретных задач с одним принятым действием, метаданными и основаниями связи. Перед предъявлением ученику нужны предметная проверка решений и согласование границ действия.
2. **Для пошагового представления:** есть наблюдаемые операции и контекст, которые можно сделать явными в интерфейсе. Данные пока не определяют диагностический вопрос, причину ученической ошибки или правило выбора помощи.
3. **Для организации материалов:** видно, где не хватает связей с каталогом и где есть ограничения чтения/допущений. Можно адресно проверять небольшой набор вместо автоматического допуска всех 100 решений.

Не установлены освоение, образовательный эффект, перенос или prerequisite. Следующий шаг — просмотр этих конкретных материалов и отдельное решение о проектировании учебного сценария. Автоматического перехода к прототипу или новой разметке нет.

## Воспроизведение и границы просмотра

Сначала выполнен один фокус, проверены 19FBCF, 8B91B1, 91CD43 и исходное изображение 7D21DC; затем зафиксирован [выборочный просмотр](checks/pilot-visual-review.json) и построены ещё два фокуса. Все восемь картинок просмотрены; HTML проверяется по структуре, ссылкам и сохранности формул/изображений. Полное браузерное отображение HTML не проверялось. Это технический и выборочный просмотр основного ассистента, не независимая математическая экспертиза.

Из корня репозитория:

```powershell
.venv/Scripts/python.exe -B -X utf8 scripts/analyze_data_to_tutor.py --phase complete
.venv/Scripts/python.exe -B -X utf8 scripts/finalize_data_to_tutor.py
```

Первоначальный запуск использовал --phase pilot, затем сохранённую визуальную проверку с хешами кода и графиков. Повторное исполнение complete требует этот журнал и неизменную копию PROTOCOL.md; при изменении кода проверку надо выполнить заново в новой версии результата. Нужны matplotlib, numpy, lxml, Pillow, nbformat, nbclient и ipykernel из существующей .venv; версии сохранены в provenance.json. Ядру Jupyter требуется локальное loopback-соединение, внешней сети и моделей нет.

manifest.json хранит Git SHA начала, полные/показанные ID и правила; provenance.json — входы и хеши; checks/final.json — результаты проверки и replay; output-hashes.json — хеши выходов. Исторические данные, каталоги и предварительный EDA остаются без изменений. Результат локальный, без commit/push.
'''
    missing=s['incomplete_adjacent_tasks']
    text=text.replace('{ADJACENT_RESULT}',f"Соседний шаг с неполным назначением есть у {len(missing)} из 12 фокусных задач: {', '.join(missing) or 'нет таких задач'}.")
    (out/'report.md').write_text(text,encoding='utf-8')
    # Preserve the protocol literally; its original relative report link gets
    # an explicit local pointer instead of silently rewriting the frozen text.
    source_report=a.ROOT/'docs/eda/05-analysis/fipi-100-checkpoint.md'
    (out/'fipi-100-checkpoint.md').write_text('# Исходный отчёт EDA-100\n\n[Открыть сохранённый отчёт]('+a.rel(source_report)+').\n',encoding='utf-8')
    (out/'README.md').write_text('# Исследование связей данных, v1\n\nПредварительный результат. [Выводы](report.md) · [Картинки и условия](index.html) · [Ноутбук](review.ipynb) · [Протокол](PROTOCOL.md).\n\nКод и команды воспроизведения, ограничения и происхождение описаны в отчёте. Новых модельных прогонов нет.\n',encoding='utf-8')
    provenance=a.read(out/'provenance.json');provenance['input_hashes'][Path(__file__).relative_to(a.ROOT).as_posix()]=a.sha(Path(__file__))
    a.dump(out/'provenance.json',provenance)
    import nbformat as nb
    from nbclient import NotebookClient
    # Each narrative section immediately precedes its figures; report remains source.
    parts=text.split('\n## ')
    cells=[nb.v4.new_markdown_cell(parts[0].replace('](index.html)','](index.html)'))]
    cells.append(nb.v4.new_code_cell('''from pathlib import Path
import sys, json
from IPython.display import display, Image, Markdown
root=next(p for p in (Path.cwd(), *Path.cwd().parents) if (p/'scripts/analyze_data_to_tutor.py').exists())
sys.path.insert(0,str(root/'scripts'))
import analyze_data_to_tutor as a
a.execute('complete')
out=a.OUT
print('Пересчитано без моделей и сети: 100 сохранённых разборов; частоты по 98 задачам.')'''))
    for part in parts[1:]:
        imgs=re.findall(r'!\[[^\]]*\]\(([^)]+)\)',part)
        md=re.sub(r'!\[[^\]]*\]\([^)]+\)','',part)
        cells.append(nb.v4.new_markdown_cell('## '+md))
        if imgs:cells.append(nb.v4.new_code_cell('\n'.join(f"display(Image(filename=str(out / {p!r})))" for p in imgs)))
    book=nb.v4.new_notebook(cells=cells,metadata={'kernelspec':{'name':'python3','language':'python','display_name':'Python 3'}})
    before={p.relative_to(out).as_posix():a.sha(p) for p in out.rglob('*') if p.is_file() and (p.suffix in ('.png','.csv') or p.name=='summary.json')}
    oldpath=os.environ.get('PATH','');os.environ['PATH']=str(Path(sys.executable).parent)+os.pathsep+oldpath
    try:NotebookClient(book,timeout=180,kernel_name='python3',resources={'metadata':{'path':str(out)}}).execute()
    finally:os.environ['PATH']=oldpath
    nb.write(book,out/'review.ipynb')
    # execute() rewrites provenance; reattach this finalizer's exact version.
    provenance=a.read(out/'provenance.json');provenance['input_hashes'][Path(__file__).relative_to(a.ROOT).as_posix()]=a.sha(Path(__file__));a.dump(out/'provenance.json',provenance)
    after={p.relative_to(out).as_posix():a.sha(p) for p in out.rglob('*') if p.is_file() and (p.suffix in ('.png','.csv') or p.name=='summary.json')}
    assert before==after,'Replay changed data or figures'
    for path,h in provenance['input_hashes'].items():assert a.sha(a.ROOT/path)==h,path
    assert sum('image/png' in o.get('data',{}) for c in book.cells for o in c.get('outputs',[]))==8
    # Independently verify exported edges against saved source mappings.
    import csv
    with (out/'tables/edges.csv').open(encoding='utf-8-sig',newline='') as f:export=list(csv.DictReader(f))
    byid={r['task_id']:r for r in rows};catalog=a.read(a.BASE/'catalog-decisions.json')
    mappings={(x['task_id'],x['local_id']):x['canonical_id'] for x in catalog['assignments']}
    for e in export:
        r=byid[e['task_id']];assert r['included']
        if r['layer']==a.LAYERS[0]:accepted={mappings[(r['task_id'],k['id'])] for k in r['author']['kc_candidates']}
        else:accepted={d['catalog_kc_id'] for d in r['audit']['decisions'] if d['status']=='match' and not d['blocking']}
        assert e['catalog_id'] in accepted,e
    assert len(export)==len({(e['task_id'],e['catalog_id']) for e in export})
    cards_checked=0
    from lxml import html
    for path in (out/'cards').glob('*.html'):
        r=byid[path.stem];tree=html.fromstring(path.read_text(encoding='utf-8'))
        assert len(tree.xpath('.//math'))==r['input']['mathml_count'],path
        assert len(tree.xpath('.//img'))==len(r['input']['assets']),path
        cards_checked+=1
    # Link/image checks cover every generated local HTML and Markdown file.
    checked=0
    for path in out.rglob('*'):
        if path.suffix=='.html':refs=html.fromstring(path.read_text(encoding='utf-8')).xpath('//@href | //@src')
        elif path.suffix=='.md':refs=re.findall(r'\]\(([^)]+)\)',path.read_text(encoding='utf-8'))
        else:continue
        for ref in refs:
            url=urlsplit(ref)
            if url.scheme or not url.path:continue
            target=(path.parent/unquote(url.path)).resolve()
            if target==out/'checks/final.json':continue
            assert target.exists(),(path,ref);checked+=1
    frozen=0
    for filename in ['baseline-manifest.json','reproducibility-manifest-100.json']:
        for e in a.read(a.EXT/filename)['files']:assert a.sha(a.ROOT/e['path'])==e['sha256'];frozen+=1
    # The preliminary checkpoint is also protected, including all of its outputs.
    preliminary=a.read(a.ROOT/'notebooks/checkpoint-2/derived/verification.json')
    for path,h in preliminary['outputs'].items():assert a.sha(a.ROOT/path)==h,path
    a.dump(out/'checks/final.json',dict(passed=True,replay_data_figures_identical=True,embedded_png=8,
        edges_independently_checked=len(export),input_hash_checks=len(provenance['input_hashes']),historical_hash_checks=frozen,
        preliminary_checkpoint_outputs_unchanged=len(preliminary['outputs']),local_links_checked=checked,cards_mathml_assets_checked=cards_checked,
        limits='No expert validation; no live student attempts; HTML not visually browser-rendered'))
    a.dump(out/'output-hashes.json',{p.relative_to(out).as_posix():a.sha(p) for p in sorted(out.rglob('*')) if p.is_file() and p.name!='output-hashes.json'})
    print(json.dumps(a.read(out/'checks/final.json'),ensure_ascii=False,indent=2))


if __name__=='__main__':finish()
