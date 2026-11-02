"""Create and execute the offline EDA notebook for the frozen 50-task pilot."""
import os
from pathlib import Path
import nbformat as nbf
from nbclient import NotebookClient

ROOT=Path(__file__).resolve().parents[1]
DEST=ROOT/'notebooks/EDA.ipynb'
RUN_REL='data/annotation/runs/2026-10-31-fipi-50x1'


def main():
    if DEST.exists() and nbf.read(DEST,as_version=4).metadata.get('fipi_run')!='2026-10-31-fipi-50x1':
        raise RuntimeError('Do not overwrite an unrelated notebook')
    md=nbf.v4.new_markdown_cell;code=nbf.v4.new_code_cell
    nb=nbf.v4.new_notebook(metadata={'kernelspec':{'display_name':'Python 3','language':'python','name':'python3'},
                                   'language_info':{'name':'python'},'fipi_run':'2026-10-31-fipi-50x1'})
    nb.cells=[
        md('''# EDA: открытый банк ФИПИ и пилот 50 задач

31 октября 2026. Предметная область — вся профильная математика ЕГЭ. Это описательный пилот, а не законченная модель освоения.

**Два разных объёма:** 1148 условий анализируются Python без модели; 50 задач имеют новые разборы основного ассистента в одном общем контексте. Нет независимых повторов, внешнего экспертного ключа и оценки устойчивости. Основные частоты KC рассчитаны по 49 задачам, одна неоднозначная задача показана отдельно.

Сценарий: состав банка → качество и похожие условия → состав выборки → шаги/KC/маршруты → повторения и сочетания → ограничения и польза для тьютора.

Повторный запуск ноутбука **не вызывает модель и не скачивает сайт**. Рецензия и межзадачные соответствия — явные отдельные входы анализа.'''),
        code('''from pathlib import Path
import sys, json, csv, html
from IPython.display import display, HTML, Image, Markdown
root = next(p for p in [Path.cwd(), *Path.cwd().parents] if (p / 'scripts/analyze_fipi50.py').is_file())
sys.path.insert(0, str(root / 'scripts'))
from analyze_fipi50 import analyze, OUT, RUN
summary = analyze()
def table(rows, columns=None, limit=None):
    rows = list(rows)[:limit]
    columns = columns or list(rows[0])
    head = ''.join('<th>'+html.escape(str(c))+'</th>' for c in columns)
    body = ''.join('<tr>'+''.join('<td>'+html.escape(str(r.get(c,'')))+'</td>' for c in columns)+'</tr>' for r in rows)
    display(HTML('<table><tr>'+head+'</tr>'+body+'</table>'))
def rows(name):
    with (OUT/name).open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))
print('Пересчитано без модели:', summary['bank_tasks'], 'условий банка;', summary['pilot_tasks'], 'разборов;', summary['included_primary_n'], 'задач в основных частотах')'''),
        md('''## 1. Что представлено в банке

Первый КЭС используется как воспроизводимая группировка. Отдельно сохранены все метки: одна задача может иметь несколько. Коды банка не приравниваются к кодам кодификатора другой редакции. Эти частоты не являются распределением реального экзамена и не доказывают покрытие всех официальных требований.'''),
        code('''table([{'Показатель':k, 'Значение':summary[k]} for k in ['bank_tasks','bank_primary_codes','bank_all_label_codes','bank_label_assignments','bank_with_images','bank_with_mathml','bank_with_source_warnings']])
table(rows('topics.csv'), ['code','title','bank_primary_n','bank_primary_pct','bank_any_label_n','sample_primary_n'])
display(Image(filename=str(OUT/'01-bank-and-sample.png')))
display(Image(filename=str(OUT/'02-representation.png')))'''),
        md('''**Вывод.** Выборка специально даёт примеры редких сочетаний категории и формата, поэтому её доли отличаются от банка. Поддержка смешанных условий обязательна: рисунки и формулы-картинки не заменяются обычным текстом. Баланс упражнений для ученика нельзя выбирать только по количеству задач в банке.'''),
        md('''## 2. Повторы и шаблоны

Точное совпадение означает совпадение нормализованного DOM, текста, инструкции и содержимого изображений. Маски чисел создают только кандидатов на похожие шаблоны: смена показателя степени тоже может менять метод. Семейства требуют предметного просмотра до разделения разработки и проверки.'''),
        code('''dups = json.loads((OUT/'duplicate-groups.json').read_text(encoding='utf-8'))
print('Групп строгих совпадений:', summary['exact_duplicate_groups'])
print('Кандидатных числовых шаблонов:', summary['template_candidate_groups'])
table([{'Число задач':len(g),'ID':', '.join(g)} for g in dups['numeric_template_candidates'][:8]])'''),
        md('''## 3. Выборка и качество разборов

50 задач выбраны до решения: по одному из 38 непустых сочетаний «первый КЭС × тип ответа» плюс 12 мест по размеру страт. Сначала проверены 2 задачи, затем партии по 8. Один подтверждённый дефект символа из сбора заранее исключён.

Разборы — авторская работа основного ассистента; сохранённые инструкции не выдаются за изолированные API-запуски. `solved` означает статус предварительного разбора, а не внешнюю валидацию. Поэтому 49/50 не называется accuracy.

Для `eFF32e` требуется уточнение, исключает ли формулировка K=S. В карточке сохранены контрпример при таком допущении и условное решение при внутреннем K; задача исключена из основных метрик.'''),
        code('''print('Статусы:', summary['status_counts'])
print('Всего шагов:', summary['all_steps'], '; локальных кандидатов KC:', summary['all_local_kcs'])
table(rows('pilot-tasks.csv'))
display(Image(filename=str(OUT/'03-solution-structure.png')))'''),
        md('''**Вывод.** Включённые краткие задачи имеют медиану 2 шага и 3 локальных KC, развёрнутые — 4 шага и 5 KC. Это описывает выбранную разметку; не является шкалой сложности. Каждый Method — использованный маршрут или часть решения, не перечень всех возможных методов.'''),
        md('''## 4. Межзадачные соответствия и повторяющиеся действия

`catalog-decisions.json` содержит определения, все назначения и цитаты шагов. Явные редакторские группы применены постфактум основным ассистентом. Вне них совпадение требуется и по названию, и по описанию. Старые каталоги и промпты не менялись.

Линейное уравнение, построение уравнения, линейное неравенство и снятие логарифма остаются разными действиями. Восстановление y=kx по одной точке не приравнено к восстановлению y=kx+b по двум точкам.'''),
        code('''table([{'Показатель':k,'Значение':summary[k]} for k in ['literal_definition_nodes_included','editorial_nodes_included','singleton_nodes','singleton_fraction']])
table(rows('kc-frequencies.csv'), ['kc_id','name','task_n','task_pct'], limit=15)
display(Image(filename=str(OUT/'04-recurrent-kcs.png')))
display(Image(filename=str(OUT/'05-task-kc-matrix.png')))'''),
        md('''**Вывод.** Решение линейного уравнения встречается после графической модели, снятия показателей и логарифма, в физической формуле, процентах и геометрии. Это даёт кандидатов для смены контекста практики одного действия. Однако перенос у ученика этим не измерен.

У большинства узлов пока один пример. Широкий охват, малый объём и неодинаковая детализация смешаны; не следует автоматически склеивать единичные узлы. Нужны просмотр определений и контрпримеры.'''),
        md('''## 5. Совместная встречаемость и порядок

Пары считаются на уровне уникальных задач. Переходы — между соседними шагами внутри каждого использованного Method, с дедупликацией по задаче. Не соединяем независимые пункты искусственным порядком; внутри шага с несколькими KC порядок не известен.'''),
        code('''display(Image(filename=str(OUT/'06-cooccurrence.png')))
table(rows('cooccurrence-legend.csv'))
catalog = json.loads((RUN/'catalog-decisions.json').read_text(encoding='utf-8'))
names = {r['id']:r['name'] for r in catalog['nodes']}
table([{'Из':names[r['from_kc']],'В':names[r['to_kc']],'Задач':r['task_n']} for r in rows('kc-transitions.csv')[:10]])'''),
        md('''**Вывод.** Сочетания и повторяющиеся переходы дают кандидатов на структуру упражнений и подсказок. Они не доказывают prerequisites и не требуют одинаковых списков KC у разных правильных методов.

## 6. Что просмотреть дальше

1. Неоднозначность `eFF32e`: внутреннее пересечение ребра и случай вершины.
2. Границы популярных узлов: линейное уравнение, чтение графика, нулевое произведение.
3. Единичные кандидаты: найти дополнительные подтверждения и контрпримеры, прежде чем менять каталог.
4. Отделить новую проверочную выборку, учитывая похожие числовые шаблоны.

Нет данных учеников, внешнего экспертного эталона и независимых повторов. Полезность тьютору остаётся проверяемой проектной гипотезой. Новых пакетов автоматически нет.

[Все 50 карточек и графики](../'''+RUN_REL+'''/derived/index.html) · [Определения KC](../'''+RUN_REL+'''/derived/catalog.html) · [Подробный отчёт](../'''+RUN_REL+'''/derived/report.md)''')
    ]
    env=dict(os.environ);env['PATH']=str(ROOT/'.venv/Scripts')+os.pathsep+env.get('PATH','')
    print('Starting local notebook kernel',flush=True)
    NotebookClient(nb,timeout=120,startup_timeout=30,kernel_name='python3',resources={'metadata':{'path':str(ROOT)}},
                   on_cell_executed=lambda cell,cell_index,**kwargs:print('Executed cell',cell_index,flush=True)).execute(env=env)
    DEST.parent.mkdir(exist_ok=True)
    nbf.write(nb,DEST)
    print('Executed notebook saved:',DEST)


if __name__=='__main__':main()
