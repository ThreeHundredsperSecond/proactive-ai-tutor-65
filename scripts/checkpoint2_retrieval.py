"""Cells for section 8 of checkpoint EDA; replay saved scores, no inference/network."""
import hashlib
import nbformat as nb

ARCHIVE_SHA256 = 'dbcddc49b99b1ef4db05948ded51a52ffd582608365fb2af4d93bc24b50e6449'


def retrieval_cells():
    cells = []
    def md(text):
        cells.append(nb.v4.new_markdown_cell(text.strip()))
    def code(text):
        cells.append(nb.v4.new_code_cell(text.strip()))

    md('''### Г. Помогает ли разметка находить другие задачи

Частоты и сопоставления выше показывают повторяющиеся действия. Для проекта возникает следующий вопрос: **можно ли использовать уже подготовленные описания действий и KC, чтобы находить задачи для дальнейшей практики?** Проверяем первый необходимый компонент — поиск тематически связанных кандидатов. Соответствие упражнения затруднению ученика требует отдельной проверки.

**Данные.** Используем сохранённые разборы текущего корпуса: из 312 включённых задач исключили спорную `0B2322`, затем фиксированным seed выбрали 300 из 311. Из них 20 запросов и 280 кандидатов; список ID сохранён. Эвристические семейства по нормализованному условию между запросами и кандидатами не пересекаются. Это не устраняет все близкие формулировки. Один запрос не имеет кандидатов с общим полным КЭС. Все средние считаются по 20, включая его.

**Откуда разметка.** Новые решения не генерируем: берём сохранённые действия `steps.action` и названия/описания всех локальных `kc_candidates`, включая не сопоставленные с каталогом. Первые 50 задач проходили редакторскую процедуру, дополнительные серии — отдельного автора и аудитора. Каталог и разметка предварительные. Названия KC описывают операции; они не тождественны официальным темам ФИПИ или устойчивым ID каталога.

**Вход.** Очищенное условие; условие с действиями; условие с названиями KC; условие с названиями и описаниями KC; полная комбинация. Отдельно проверяем только названия KC. Идентификаторы, КЭС, итоговый ответ и результаты шагов на вход не передаются. Рисунки доступны читателю, но модели получают только текст.

**Оценка.** Кандидат релевантен, если есть хотя бы один общий **полный** код КЭС. Precision@5 — доля таких задач в пятёрке; Hit@5 — наличие хотя бы одной; MRR@280 — обратная позиция первого релевантного кандидата среди всех 280. Это проверка тематической связи, а не эквивалентности методов.

Исходные прогоны выполнены 10 ноября 2026 года. Следующие ячейки воспроизводят анализ сохранённых оценок из внешнего архива; обучение, сеть и GPU для этого не нужны.''')
    code('''from pathlib import Path
import hashlib, io, json, zipfile
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from IPython.display import display, Image

rx_candidates = [Path('derived/retrieval-study-results.zip'),
                 Path('notebooks/checkpoint-2/derived/retrieval-study-results.zip')]
rx_archive = next((p for p in rx_candidates if p.is_file()), None)
assert rx_archive is not None, 'Откройте папку проекта или notebooks/checkpoint-2; нужен derived/retrieval-study-results.zip'
assert hashlib.sha256(rx_archive.read_bytes()).hexdigest() == ARCHIVE_DIGEST
rx_zip = zipfile.ZipFile(rx_archive)
rx_manifest = json.loads(rx_zip.read('results-sha256.json'))
for rx_name, rx_digest in rx_manifest.items():
    assert hashlib.sha256(rx_zip.read(rx_name)).hexdigest() == rx_digest, rx_name
rx_tasks = {r['task_id']:r for r in map(json.loads, rx_zip.read('source-data/tasks.jsonl').decode('utf-8').splitlines())}
rx_split = json.loads(rx_zip.read('source-data/split.json'))
rx_env = json.loads(rx_zip.read('environment.json'))
rx_qids, rx_cids = rx_split['query_ids'], rx_split['candidate_ids']
rx_scores = np.load(io.BytesIO(rx_zip.read('scores.npz')), allow_pickle=False)
rx_vectors = np.load(io.BytesIO(rx_zip.read('e5-embeddings.npz')), allow_pickle=False)
rx_inputs = json.loads(rx_zip.read('model-inputs.json'))
rx_lengths = pd.read_csv(io.BytesIO(rx_zip.read('length-audit.csv')))
assert len(rx_tasks)==300 and len(rx_qids)==20 and len(rx_cids)==280
assert not set(rx_qids)&set(rx_cids)
assert not {rx_tasks[q]['family'] for q in rx_qids}&{rx_tasks[c]['family'] for c in rx_cids}
print('Проверен архив:', rx_archive, '; файлов с контрольными суммами:', len(rx_manifest))
print('Вход: 300 задач, 20 запросов, 280 кандидатов; запросы и кандидаты не пересекаются.')
print('Окружение исходного прогона:', rx_env['gpu'], rx_env['torch'])
display(pd.DataFrame([
    dict(model=rx_env['e5_model'], revision=rx_env['e5_revision'], limits='512', representation='384-d, mean pooling, L2, query:/passage:'),
    dict(model=rx_env['reranker_model'], revision=rx_env['reranker_revision'], limits='512 / 1024', representation='совместная оценка пары, без префиксов E5')]))
'''.replace('ARCHIVE_DIGEST', repr(ARCHIVE_SHA256)))
    md('''**Метод.** E5 сравнивает независимые векторы по косинусу. Готовый reranker читает пару целиком и выдаёт logit; сравниваем его варианты внутри одной модели. Обе модели без дообучения. Для reranker рассчитаны все 5600 пар на вариант: предварительного отбора E5 top-k не было. Векторы E5 нормированы, длина ограничена 512 токенами; пары reranker проверены с лимитами 512 и 1024.

Ниже заново считаем метрики непосредственно из матриц оценок и кодов КЭС. При равенстве оценок сохраняется порядок кандидатов в зафиксированном split. Проверка сравнивает все строки с исходными результатами, а не копирует готовые средние.''')
    code('''rx_rel = np.array([[bool(set(rx_tasks[q]['kes_codes']) & set(rx_tasks[c]['kes_codes']))
                    for c in rx_cids] for q in rx_qids])
rx_rows = []
for rx_key in rx_scores.files:
    rx_stage, rx_variant = rx_key.split(' | ', 1)
    rx_matrix = rx_scores[rx_key]
    assert rx_matrix.shape == (20,280) and np.isfinite(rx_matrix).all()
    rx_order = np.argsort(-rx_matrix, axis=1, kind='stable')
    rx_relevant = np.take_along_axis(rx_rel, rx_order, axis=1)
    for rx_i, rx_qid in enumerate(rx_qids):
        rx_positions = np.flatnonzero(rx_relevant[rx_i])
        rx_rows.append(dict(stage=rx_stage, variant=rx_variant, query_id=rx_qid,
            precision_at_5=float(rx_relevant[rx_i,:5].mean()), hit_at_5=int(rx_relevant[rx_i,:5].any()),
            reciprocal_rank=1/(int(rx_positions[0])+1) if len(rx_positions) else 0.0))
rx_metrics = pd.DataFrame(rx_rows)
rx_cols = ['precision_at_5','hit_at_5','reciprocal_rank']
rx_index = ['stage','variant','query_id']
rx_saved = pd.read_csv(io.BytesIO(rx_zip.read('per-query.csv'))).set_index(rx_index).sort_index()
rx_check = rx_metrics.set_index(rx_index).sort_index()
assert rx_saved.index.equals(rx_check.index)
assert np.allclose(rx_saved[rx_cols], rx_check[rx_cols], atol=1e-14)
for rx_vecname in rx_vectors.files:
    assert np.allclose(np.linalg.norm(rx_vectors[rx_vecname],axis=1),1,atol=1e-5)
print('Выход: совпали',len(rx_scores.files),'сравнений и',len(rx_metrics),'строк метрик.')
print('Запросы без положительных кандидатов:', [q for q,n in zip(rx_qids,rx_rel.sum(1)) if n==0])

def rx_table(stage):
    return rx_metrics[rx_metrics.stage==stage].groupby('variant')[rx_cols].mean().rename(columns={'reciprocal_rank':'MRR@280'})
display(rx_table('02_both_sides').round(6))
''')
    md('''**Результат первого сравнения.** При обычном запросе полная разметка кандидатов не улучшила E5: Precision@5 0.69 вместо 0.71. При полной разметке обеих сторон получили 0.83, Hit@5 0.95, MRR 0.818333. Следовательно, наличие полезной разметки само по себе не гарантирует прирост: важны представления обеих сторон. Двусторонний вариант относится к поиску по уже разобранной задаче; для новой нерешённой задачи такой вход ещё нужно получить.

#### Какая часть разметки нужна поиску

Сравниваем состав текста при тех же E5, split и лимите. Полная разметка объединяет условие, действия, названия и описания навыков. Компактное представление содержит условие и только названия KC.''')
    code('''display(rx_table('03_annotation_parts').round(6))
display(rx_lengths[rx_lengths.model=='E5'][['variant','inputs','median_tokens','max_tokens','truncated']])
rx_best = rx_table('03_annotation_parts').loc[['условие → условие','условие+KC → условие+KC','полная разметка → полная разметка']]
rx_ax = rx_best.plot.barh(figsize=(10,3.6), xlim=(0,1))
rx_ax.set_xlabel('Среднее по 20 запросам'); rx_ax.set_ylabel('')
rx_ax.set_title('E5: короткие названия KC и полный разбор')
rx_ax.legend(loc='upper left',bbox_to_anchor=(1.02,1))
plt.tight_layout()
rx_figure = io.BytesIO()
rx_ax.figure.savefig(rx_figure,format='png',dpi=150,bbox_inches='tight')
plt.close(rx_ax.figure)
display(Image(data=rx_figure.getvalue()))
print('Пример входа E5 — обогащённый запрос:')
print(rx_inputs['E5_queries_kc_names'][0])
print('Пример кандидата:')
print(rx_inputs['E5_candidates_kc_names'][20])
''')
    md('''**Вывод.** Условие с названиями KC с обеих сторон дало 0.83 / 0.95 / 0.887500. Полная разметка дала те же P@5 и Hit@5, но MRR 0.818333. Ни один компактный вход E5 не обрезался; у полного варианта обрезались 72 кандидата и 5 запросов. Это поддерживает отдельное компактное представление для поиска; подробные разборы остаются материалом для объяснений и проверки шагов.

#### Другой оценщик, длина текста и три заключительные проверки

Чтобы отделить эффект состава разметки от одного способа поиска, проверили совместную оценку пары reranker. Затем увеличили его лимит, убрали условие из E5, объединили две выдачи фиксированным RRF и дали reranker компактные тексты. RRF использует равные веса и сумму `0.5 / (60 + ранг)`; параметры не подбирались на этих запросах.''')
    code('''print('Reranker, 512:'); display(rx_table('04_reranker_512').round(6))
print('Изменение при 1024 минус 512:')
display((rx_table('05_reranker_1024')-rx_table('04_reranker_512')).round(6))
print('Длины пар reranker:')
display(rx_lengths[rx_lengths.model=='reranker'][['variant','limit','inputs','max_tokens','truncated']])
for rx_stage,rx_title in [('06_KC_only','Условие и только KC'),('07_fusion','Объединение выдач'),('08_compact_reranker','Компактный reranker')]:
    print(rx_title); display(rx_table(rx_stage).round(6))
''')
    md('''**Что выяснили.**

| Проверка | Наблюдение | Следствие для проекта |
|---|---|---|
| Полная разметка кандидатов, обычный запрос, reranker | P@5 0.54 → 0.68; Hit@5 0.80 → 0.95; MRR 0.704676 → 0.793333 | Полезный сигнал наблюдается также при совместной оценке пары |
| Лимит reranker 512 → 1024 | При обычном запросе P@5 полных кандидатов 0.68 → 0.64; при полной разметке обеих сторон 0.66 → 0.66 | Обрезание не является достаточным объяснением; больший лимит не гарантирует улучшение |
| Только KC у обеих сторон E5 | 0.75 / 0.90 / 0.85 против 0.83 / 0.95 / 0.8875 с условием | Сохраняем конкретику условия рядом с навыками |
| Фиксированный RRF двух выдач | Лучший из двух вариантов: 0.80 / 0.95 / 0.833333 | Преимущество перед компактным E5 не получено |
| Компактный reranker обеих сторон | 0.74 / 0.85 / 0.744674 против полного 0.66 / 0.90 / 0.764583 | Состав разметки зависит от модели и целевой метрики; улучшения всех метрик нет |

Даже при 1024 полная двусторонняя разметка обрезалась в 1188 из 5600 пар. Увеличение лимита уменьшает обрезание, но не означает сохранность всего текста. По этим опытам нельзя сделать вывод о качестве двухэтапной схемы E5 → reranker: здесь оценщик получал всех кандидатов.

#### На каких задачах появился прирост

Средние могут скрывать крупные изменения в нескольких запросах. Сравним компактный двусторонний E5 с обычным и посмотрим реальные выдачи. Следующий разбор выбран после просмотра результатов и служит анализом ошибок.''')
    code('''def rx_perquery(stage,variant):
    return rx_metrics[(rx_metrics.stage==stage)&(rx_metrics.variant==variant)].set_index('query_id')[rx_cols]
rx_base = rx_perquery('01_initial','условие → условие')
rx_compact = rx_perquery('03_annotation_parts','условие+KC → условие+KC')
rx_delta = rx_compact-rx_base
display(rx_delta.sort_values('precision_at_5'))
display(pd.DataFrame({'improved':(rx_delta>1e-9).sum(),'unchanged':(rx_delta.abs()<=1e-9).sum(),'worsened':(rx_delta< -1e-9).sum()}))
rx_other_ids = [q for q in rx_qids if q not in ['A92B9D','0cc4F3']]
display(pd.DataFrame({'условия, 18 запросов':rx_base.loc[rx_other_ids].mean(),
                     'условие+KC, 18 запросов':rx_compact.loc[rx_other_ids].mean()}).T)
print('Максимальный Hit@5 по покрытию КЭС:', float(rx_rel.any(axis=1).mean()))
rx_rr_base = rx_perquery('04_reranker_512','условие → условие')
rx_rr_full = rx_perquery('04_reranker_512','условие → полная разметка')
rx_rr_delta = rx_rr_full-rx_rr_base
print('Reranker: изменение по запросам при полной разметке кандидатов')
display(pd.DataFrame({'improved':(rx_rr_delta>1e-9).sum(),'unchanged':(rx_rr_delta.abs()<=1e-9).sum(),'worsened':(rx_rr_delta< -1e-9).sum()}))
display(pd.DataFrame({'условия, 18 запросов':rx_rr_base.loc[rx_other_ids].mean(),
                     'разметка кандидатов, 18 запросов':rx_rr_full.loc[rx_other_ids].mean()}).T)

def rx_top5(query_id, key):
    i=rx_qids.index(query_id)
    print()
    print('ЗАПРОС',query_id,':',rx_tasks[query_id]['condition_text'])
    print('KC запроса:', '; '.join(s['name'] for s in rx_tasks[query_id]['skills']))
    print('ВЫХОД:',key)
    order=np.argsort(-rx_scores[key][i],kind='stable')[:5]
    display(pd.DataFrame([dict(rank=rank,candidate_id=rx_cids[j],relevant=bool(rx_rel[i,j]),
        condition=rx_tasks[rx_cids[j]]['condition_text'],
        skills='; '.join(s['name'] for s in rx_tasks[rx_cids[j]]['skills'])) for rank,j in enumerate(order,1)]))
with pd.option_context('display.max_colwidth',180):
    for rx_q in ['0cc4F3','BE30B7']:
        rx_top5(rx_q,'01_initial | условие → условие')
        rx_top5(rx_q,'03_annotation_parts | условие+KC → условие+KC')
''')
    md('''**Что уточняет разбор.** P@5 E5 вырос у 4 запросов, не изменился у 15 и снизился у 1. Из 100 позиций первых пятёрок релевантными стали 83 вместо 71. Два близких запроса про массу хлеба перешли от 0/5 к 5/5 каждый: 10 из 12 чистых дополнительных попаданий. Их family-ID различаются; эвристика не обнаружила это сходство. Без этих запросов P@5 0.788889 → 0.811111, а Hit@5 и MRR не меняются. Это разбор чувствительности, не замена основному набору.

У reranker добавление полной разметки кандидатам при обычном запросе улучшило P@5 у 7 запросов, ухудшило у 5; без двух хлебных задач среднее растёт с 0.60 до 0.688889. Следовательно, наблюдаемая польза не сводится к двум запросам E5, но равномерное улучшение по всем типам задач не установлено.

Компактный E5 достиг Hit@5 19/20 — потолка покрытия этой оценки: у `E1812B` нет кандидатов с общим КЭС. Это не означает идеального поиска или отсутствия семантически подходящих задач. В примере вероятности общий КЭС объединяет разные операции; подходящий материал для тренировки конкретного шага ещё требует предметного отбора.

#### Как результат связан с тьютором

| Вопрос проекта | Что даёт этот опыт | Что остаётся проверить |
|---|---|---|
| Как найти другую задачу после разбора текущей? | Кандидат на поисковое представление: условие и короткие названия KC с обеих сторон | Перенос на новые запросы и близость нужного метода |
| Как искать по задаче без готового разбора? | Отдельные результаты для обычного запроса и размеченных кандидатов | Получение KC запроса и стоимость такого шага; показатели двустороннего варианта сюда не переносятся |
| Как дать практику на затруднение ученика? | Найденный тематический пул и сохранённые описания операций позволяют обсуждать предметный отбор | Соответствие целевому действию, сложности и попыткам ученика |
| Что хранить в базе? | Компактный поисковый текст и полный разбор выполняют разные роли | Формат их использования в прототипе; окончательная архитектура этим опытом не выбирается |

**Итог.** Сохранённая разметка даёт полезный сигнал для поиска задач с общими КЭС. На этих 20 запросах лучший наблюдаемый E5 — условие с названиями KC у обеих сторон; готовый reranker также получает пользу от разметки кандидатов. Прирост зависит от сценария и сосредоточен в части задач. Это вычислительное основание для компонента поиска, дополняющее содержательные сопоставления выше.

Все варианты исследовательские и сравнивались на одних запросах после просмотра результатов. Повторное выполнение подтверждает воспроизводимость, а не обобщение. Разметка предварительная, рисунки не читаются, близость методов экспертно не оценена. Готовая разметка запроса — дополнительная информация. Оценка освоения, полезности следующего упражнения и образовательного эффекта здесь не проводилась. Следующий отдельный этап — зафиксировать конфигурацию, проверить новые запросы и предметно оценить найденные пары.''')
    for cell in cells:
        cell.id = 'retrieval-' + hashlib.sha256((cell.cell_type+cell.source).encode()).hexdigest()[:12]
        cell.metadata['study'] = 'retrieval-2026-11-10'
    return cells


def add_retrieval_cells(cells, executed=None):
    """Insert before chapter 9, preserving chapter numbering and existing material."""
    cells = [nb.from_dict(dict(c)) for c in cells]
    if any('### Г. Помогает ли разметка находить другие задачи' in c.source for c in cells):
        raise ValueError('Retrieval section is already present')
    addition = executed if executed is not None else retrieval_cells()
    for i, cell in enumerate(cells):
        marker='## 9. Итог:'
        if cell.cell_type=='markdown' and marker in cell.source:
            before, after=cell.source.split(marker,1)
            tail=nb.v4.new_markdown_cell(marker+after,metadata=dict(cell.metadata))
            cell.source=before.rstrip()
            cells[i:i+1]=([cell] if cell.source else [])+addition+[tail]
            break
    else:
        raise ValueError('Chapter 9 anchor is missing')
    for cell in cells:
        if cell.cell_type!='markdown':
            continue
        if '## 9. Итог:' in cell.source:
            anchor='### Практическая ценность:'
            note='''### Поиск задач по разметке

Сопоставления дополнены поисковой проверкой на 20 запросах и 280 кандидатах. Компактный E5 по условию и названиям KC с обеих сторон дал P@5 0.83 против 0.71 по условиям; Hit@5 0.95 против 0.85 и MRR 0.887500 против 0.793125. Разметка кандидатов помогла и выбранному reranker. Это основание для поискового компонента, но не готовая политика подбора практики: общий КЭС не устанавливает нужный ученику метод, а 10 из 12 дополнительных попаданий E5 дали два близких запроса. Подробности, реальные выдачи и границы результата приведены в разделе 8.Г.

'''
            cell.source=cell.source.replace(anchor,note+anchor,1)
        if '## 10. Источники' in cell.source:
            cell.source += '\n\nПоисковая проверка раздела 8.Г: [сохранённые оценки, входы и данные](derived/retrieval-study-results.zip), [метод и воспроизведение](../../docs/eda/05-analysis/retrieval-study.md), [генератор раздела](../../scripts/checkpoint2_retrieval.py). Внешний ZIP содержит манифест SHA-256, ID split, версии моделей, векторы, оценки, полные ранжирования и исходные материалы.\n'
    return cells
