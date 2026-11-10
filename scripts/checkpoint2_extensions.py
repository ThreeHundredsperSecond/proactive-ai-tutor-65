"""Saved, separately dated notebook extension; never invokes collectors or models."""
from pathlib import Path
import csv
import hashlib
import json

BASE = 'data/annotation/analyses/'
DIRS = dict(corpus=BASE+'2026-11-09-fipi-checkpoint-250-v1', quality=BASE+'2026-11-09-domain-quality-v1', baseline=BASE+'2026-11-09-routing-baseline-v1', families=BASE+'2026-11-09-kc-families-v1')
FIGURES = [('quality','01-label-balance.png'), ('quality','02-structure.png'), ('quality','03-multimodal.png'), ('baseline','01-model-comparison.png'), ('baseline','04-format-robustness.png'), ('families','task-vs-family.png')]
PNG_COUNT = len(FIGURES)
REQUIRED = dict(corpus=['summary.json','manifest.json','report.md','provenance.json'], quality=['summary.json','report.md','provenance.json','flatten-examples.json','outlier-top5.csv','label-balance.csv'], baseline=['summary.json','report.md','provenance.json','metrics.csv','distinctive-features.csv','explanations.json','predictions.csv'], families=['summary.json','report.md','provenance.json','kc-family-frequency.csv'])


def read(p):
    return json.loads(p.read_text(encoding='utf-8'))


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def load_saved(root):
    """Require every declared input and verify saved artifact references, not raw collectors."""
    hashes = {}
    for key, names in REQUIRED.items():
        for name in names + [n for k,n in FIGURES if k == key]:
            p = root / DIRS[key] / name
            assert p.is_file(), f'Incomplete chapter 11 inputs: {p}'
            hashes[p.relative_to(root).as_posix()] = sha(p)
        prov = read(root / DIRS[key] / 'provenance.json')
        for name, digest in prov.get('artifacts', {}).items():
            p = root / DIRS[key] / name
            assert sha(p) == digest, str(p)
        # These are small canonical dependencies. Thousands of frozen attempts
        # remain checked by the independent corpus verifier, not notebook replay.
        for name,digest in prov.get('hashes', {}).items():
            p = root / name
            if p.is_file() and (name.startswith('scripts/') or name.endswith('/tasks.jsonl') or name.endswith('/split.json')):
                assert sha(p) == digest, name
    objects = {k:read(root / d / 'summary.json') for k,d in DIRS.items()}
    manifest = read(root / DIRS['corpus'] / 'manifest.json')
    assert len(manifest) == len({r['task_id'] for r in manifest}) == 250
    assert sum(r['included'] for r in manifest) == 247
    assert sum(r['source_policy_included'] for r in manifest) == 248
    assert len({r['origin'] for r in manifest}) == 4
    q = objects['quality']
    assert (q['records'], q['assets'], q['classes'], q['math_tags']['math']) == (1148,443,26,4067)
    assert q['split_sizes'] == dict(train=789,dev=176,test=183)
    assert objects['baseline']['augmentation']['signature_pass'] == 1148
    return objects, hashes


def extension_cells(root):
    import nbformat as nb
    # Fail closed before starting an expensive kernel if the chapter is incomplete.
    load_saved(root)
    cells=[]
    def md(s): cells.append(nb.v4.new_markdown_cell(s.strip()))
    def code(s): cells.append(nb.v4.new_code_cell(s.strip()))
    md('''## 11. Дополнение 9 ноября: 250 разборов, доменные проверки и ML baseline

Разделы 1–10 сохраняют исторический срез **100 разборов / 98 в частотах**. Здесь отдельный датированный анализ: **250 уникальных разборов / 247 в частотах** по единой политике и **248** по исходным правилам участников. Все результаты ниже уже вычислены; notebook читает сохранённые артефакты, без обучения и новых вызовов моделей.

### 11.1. Корпус и границы сравнения

Четыре слоя: редакторские 50, исторические независимые 50, Sol50 и 100 Богдана (reported Opus). Редакторские 50 не имеют независимого аудита. Остальные аудиты — агентные, не экспертный математический эталон. `321FCD` принят в исходной политике при raw partial и исключён из harmonized; исторические исключения сохранены. Для `F416AF` используется сохранённая попытка после обратной связи, для `9c96c5` — отдельная техническая коррекция порядка ссылок метода с сохранением исходника. Различия слоёв смешивают темы, исполнителей, effort и процедуры и не измеряют преимущество модели.''')
    code('''from checkpoint2_extensions import load_saved, DIRS, FIGURES
ROOT = root
extension, extension_hashes = load_saved(ROOT)
import csv
from IPython.display import Image, Markdown, display

def ext_json(key, name):
    return json.loads((ROOT / DIRS[key] / name).read_text(encoding='utf-8'))

def ext_rows(key, name):
    with (ROOT / DIRS[key] / name).open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))

def ext_table(rows, keys):
    def clean(v): return str(v).replace('|',' / ').replace('\\n',' ')
    display(Markdown('| '+' | '.join(keys)+' |\\n| '+' | '.join(['---']*len(keys))+' |\\n'+'\\n'.join('| '+' | '.join(clean(r.get(k,'')) for k in keys)+' |' for r in rows)))

def ext_figure(key, name):
    display(Image(filename=str(ROOT / DIRS[key] / name)))

manifest250 = ext_json('corpus','manifest.json')
from collections import Counter
ext_table([{'слой':k,'выбрано':v,'harmonized':sum(r['included'] for r in manifest250 if r['origin']==k),'source policy':sum(r['source_policy_included'] for r in manifest250 if r['origin']==k)} for k,v in Counter(r['origin'] for r in manifest250).items()], ['слой','выбрано','harmonized','source policy'])''')
    md('''### 11.2. Домен: текст, формулы и рисунки

Банк — смешанный NLP/CV-источник: 1148 условий, 4067 узлов MathML, 443 локальных assets; 286 задач содержат рисунки, 859 — MathML. Модель ниже не видит содержание рисунков. Официальных ответов, решений и надёжного года отдельной задачи нет; 250 разборов — слабая предварительная разметка для исследования, а не ground truth правильности.

Первая сохранённая метка КЭС даёт 26 операционных классов для routing; все метки — 29 кодов и 1707 назначений. У 409 задач несколько меток. Первая метка не означает единственную тему, а КЭС не равен KC. График сравнивает эти два знаменателя.''')
    code("ext_figure('quality','01-label-balance.png')")
    md('''Проверены файлы изображений, длины, символы, MathML и шаблонные повторы. Нулевой/битый asset не обнаружен; есть один символ замены и 80 задач с zero-width символами. Диагностика HTML-парсера сама по себе не равна повреждению: MathML/HTML требует контекстной проверки. Выброс по длине или числу формул — кандидат на просмотр, а не ошибка и не измеренная трудность для ученика. Порог MAD для изображений вырождается из-за нулевой медианы, поэтому не используется как содержательный классификатор.''')
    code("ext_figure('quality','02-structure.png')\next_table(ext_rows('quality','outlier-top5.csv')[:5], list(ext_rows('quality','outlier-top5.csv')[0])[:5])")
    md('''Обычное извлечение текста теряет отношения. Например, в `4CBD4E` дробь $1/7$ становится `1 7`, а степень $(1/7)^{x+4}$ — последовательностью символов без границ основания и показателя. Структурные токены `MFRAC` и `MSUP` сохраняют тип и вложенность узлов. Это техническая сохранность записи, не понимание математики. Ниже — сохранённый конкретный пример и сравнение модальностей.''')
    code("example_flat = ext_json('quality','flatten-examples.json')[1]\next_table([example_flat], ['task_id','tag','flattened','semantic'])\next_figure('quality','03-multimodal.png')")
    md('''### 11.3. Вспомогательный routing baseline

Цель — предсказать первую метку КЭС по условию. Это маршрутизация к разделу банка, а не решение задачи, оценка LLM, диагностика ученика или качество тьютора. Реализованы NumPy majority, multinomial Naive Bayes и TF–IDF cosine 1NN; DL не обучался. Из входа исключены ID, URL, метаданные КЭС, ответы, решения и аудит. Словарь и веса строятся на train; test не подбирает модель.

Group split удерживает числовые шаблоны целиком: train/dev/test = 789/176/183, test — 154 группы. Группировка по всему банку — заранее заданная transductive проверка целостности, не обучение на test-метках. В test есть классы с единичной поддержкой; интервалы bootstrap считаются по группам. Random split имеет 21 test-задачу с шаблоном из train; group — ни одной. На этом seed завышение random-качества **не показано**.

Первичный baseline заранее зафиксирован как semantic NB: accuracy 0.6776, macro-F1 0.4308, top-3 0.8634. Структурное представление не улучшает все модели: NB хуже plain NB (0.7377 / 0.4804), semantic 1NN лучше plain 1NN (0.8251 / 0.6886 против 0.7705 / 0.6307). Random semantic NB имеет ту же accuracy, random semantic 1NN — немного ниже group. Полезен сам анализ зависимости от представления, а не обещание неизбежного роста.''')
    code("ext_figure('baseline','01-model-comparison.png')\nmetrics11 = [r for r in extension['baseline']['metrics'] if r['partition']=='test' and 'semantic' in r['model']]\next_table(metrics11, ['model','accuracy','macro_f1','top3_accuracy'])\next_table([{'метрика':k,'нижняя':v[0],'верхняя':v[1]} for k,v in extension['baseline']['group_bootstrap_ci95'].items()], ['метрика','нижняя','верхняя'])")
    md('''NB объясним через вклад токенов в разность log-вероятностей классов. Частые тематические слова помогают, но пунктуация и оформление также несут корреляции. Ниже — характерные признаки и две ошибки с локальными вкладами; ошибкой считается несовпадение с операционной первой КЭС, а не доказанная математическая ошибочность условия.''')
    code("features11=ext_rows('baseline','distinctive-features.csv')\next_table([r for r in features11 if r['rank']=='1'][:8], ['class_label','feature','distinctive_log_probability'])\nerrors11=[r for r in ext_json('baseline','explanations.json') if not r['correct']][:2]\nassert len(errors11)==2, 'Two saved baseline error explanations required'\nfor err in errors11:\n    display(Markdown('**'+err['task_id']+'**: первая КЭС '+err['actual']+' → предсказано '+err['predicted']))\n    ext_table(err['features'][:4], ['token','count','margin'])")
    md('''### 11.4. Проверенная аугментация оформления

Детерминированная смена пробелов, эквивалентных Unicode-символов и HTML-обёрток проверена по сигнатурам математической структуры, чисел/операторов и assets: 1148/1148 проходят. Semantic token invariance — 100%; взвешенные counts после дублирования совпадают точно. Поэтому прироста качества здесь нет: это полезная отрицательная проверка и основание нормализовать оформление. Устойчивость постоянного majority сама по себе не свидетельствует о полезности. Варианты не увеличивают число независимых задач; замена чисел и геометрические трансформации этим опытом не проверены.''')
    code("ext_figure('baseline','04-format-robustness.png')")
    md('''### 11.5. KC и независимые семейства упражнений

Частота задач с KC может завышать запас разнообразной практики. В этом корпусе массовой шаблонной избыточности не обнаружено: 247 задач образуют 239 семейств; для linear_equation — 26 задач и 23 семейства. Числовые варианты одного шаблона всё равно не дают независимых контекстов. Ниже число задач сопоставлено с числом консервативных шаблонных семейств. Это структурная обеспеченность банка, а не доказанный перенос освоения. В mixed247 у 5 из 144 определений нет поддержки, у 50 — одно семейство, у 26 — два и у 63 — не менее трёх; `catalog_nodes` в таблице означает полный размер фиксированного каталога, не число поддержанных определений. В Sol50 44 из 50 задач содержат несопоставленных кандидатов; полностью сопоставлены 59 из 186 шагов. Каталог фиксирован и предварителен, new_candidate между задачами не консолидированы; редакторские назначения отличаются по происхождению от независимых аудитов.''')
    code("ext_figure('families','task-vs-family.png')\nfamily11=extension['families']['populations']\next_table([{'слой':k,**{x:v.get(x,'') for x in ['included_tasks','families','catalog_nodes','tasks_with_unmatched_candidates']}} for k,v in family11.items()], ['слой','included_tasks','families','catalog_nodes','tasks_with_unmatched_candidates'])")
    md('''### 11.6. Что выполнено и как применять в тьюторе

| Критерий | Исполненный результат | Граница |
|---|---|---|
| Специфика домена | Текст, MathML, рисунки; конкретная потеря дроби/степени | Структура не равна математическому пониманию |
| Баланс классов | Все КЭС против первой метки; редкие классы сохранены | 26 классов routing не равны навыкам |
| Качество, объём, выбросы | 1148 условий, 250 разборов, технические проверки и кандидаты аномалий | Нет официальных ответов и экспертного эталона |
| Простой ML baseline | Majority, NB, TF–IDF 1NN; random/group; признаки, ошибки, bootstrap | Вспомогательная маршрутизация, не DL и не оценка тьютора |
| Аугментация | Проверены инварианты и предсказания форматного преобразования | Прироста и новых независимых задач нет |
| Предметная модель | KC × задачи × шаблонные семейства | Не prerequisites и не адаптивная рекомендация |

В будущем прототипе результаты задают требования к сохранению формул и рисунков, подсказке раздела для нового условия и отбору упражнений с разными контекстами. Результаты не обновляют профиль ученика: для этого нужны наблюдаемые самостоятельные попытки, различение помощи и решения, проверка математической корректности и учебный эксперимент.

Полные сохранённые отчёты: [250 разборов](../../data/annotation/analyses/2026-11-09-fipi-checkpoint-250-v1/report.md), [доменное качество](../../data/annotation/analyses/2026-11-09-domain-quality-v1/report.md), [routing baseline](../../data/annotation/analyses/2026-11-09-routing-baseline-v1/report.md), [KC и семейства](../../data/annotation/analyses/2026-11-09-kc-families-v1/report.md). Их provenance фиксируют происхождение и хеши; исполнение главы проверяет SHA сохранённых артефактов и независимые счётчики manifest, не вызывает collectors.''')
    return cells
