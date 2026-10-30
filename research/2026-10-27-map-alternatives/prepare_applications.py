"""Freeze small application probes after maps, with provenance and exact jobs.

Synthetic probes are short descriptions, not collected exam tasks or student data.
"""
import json
from pathlib import Path
from run_offline import HERE, ROOT, digest, read, write


def main():
    frozen = read(HERE / 'frozen-catalogs.json')
    assert not (HERE / 'inputs/stimuli.json').exists(), 'Refusing to replace stimuli'
    specs = [
        ('T01', 'Вектор: чтение рисунка и разности координат', '2026-10-25-A-19x3/raw/699086_r1.txt', 's1'),
        ('T02', 'Сумма векторов', '2026-10-25-A-19x3/raw/699086_r1.txt', 's2'),
        ('T03', 'Длина вектора', '2026-10-25-A-19x3/raw/699086_r1.txt', 's3'),
        ('T04', 'Нули производной: множители и нулевое произведение', '2026-10-25-A-19x3/raw/699096_r1.txt', 's3'),
        ('T05', 'Квадратное уравнение: дискриминант', '2026-10-25-A-19x3/raw/699100_r1.txt', 's4'),
        ('T06', 'Ограничения логарифмов и знаменателей', '2026-10-25-A-19x3/raw/699099_r1.txt', 's1'),
        ('T07', 'Фиксация параметра и модуль', '2026-10-26-A-FIPI-19x1/raw/699102.txt', 's4'),
    ]
    stimuli = []
    for id_, title, rel, step_id in specs:
        path = ROOT / 'data/annotation/runs' / rel
        doc = read(path)
        index, step = next((i, s) for i, s in enumerate(doc['steps']) if s['id'] == step_id)
        stimuli.append({'id': id_, 'title': title, 'origin': 'saved_solution',
                        'text': step['action'] + '\n' + step['result'],
                        'source': {'path': path.relative_to(ROOT).as_posix(), 'sha256': digest(path),
                                   'json_pointer': f'/steps/{index}'}})
    synthetic = [
        ('T08', 'Среднее по точным значениям и частотам', 'Для конечного набора наблюдений дана таблица точных числовых значений и их целых неотрицательных частот с положительной общей численностью. Умножили каждое значение на его частоту, сложили произведения и разделили на сумму частот, получив среднее арифметическое набора.'),
        ('T09', 'Медиана при чётной численности', 'Для непустого конечного набора точных числовых наблюдений с чётной численностью упорядочили значения с учётом повторений. Взяли два центральных значения и нашли их среднее; результат назвали медианой набора.'),
        ('T10', 'Интервальные данные вместо точных', 'Дана только интервальная гистограмма: границы интервалов и численность в каждом; индивидуальные значения неизвестны. Середину каждого интервала умножили на его частоту, сумму разделили на общее число наблюдений и объявили полученное число точным средним исходных наблюдений без дополнительных допущений.'),
        ('T11', 'Вырожденное основание', 'В равенстве 1^{u(x)}=1^{v(x)}, где u(x) и v(x) определены в действительных числах, без дополнительных ограничений заменили уравнение на u(x)=v(x), объявив переход равносильным.'),
        ('T12', 'Нет наблюдаемого действия', 'Известно только, что это текстовая задача на движение. Условие, выражение, шаг решения и полученный результат не приведены.'),
    ]
    stimuli.extend({'id': id_, 'title': title, 'origin': 'synthetic_description', 'text': text,
                    'source': {'author': 'primary agent', 'purpose': 'Specification/contrast probe, not an exam task or learner attempt.'}}
                   for id_, title, text in synthetic)
    write(HERE / 'inputs/stimuli.json', {'selection': 'Purposeful known cases and synthetic descriptions; not heldout, no random-sample inference.',
                                       'catalogs_sha256_before_selection': digest(HERE / 'frozen-catalogs.json'),
                                       'stimuli': stimuli})
    maps = [{'map_id': m['label'], 'nodes': m['catalog']['nodes'], 'relationships': m['catalog']['relationships']} for m in frozen['maps']]
    common = '''Это применение фиксированных определений, не решение задач. Работай только с назначенным входом. Не читать исходный корпус, протокол исследования, чужие ответы и источники построения карт. Не browse и не вызывай модель/API. Ничего не вычисляй заново. Не дописывай отсутствующие операции. Отсутствие подходящего узла допустимо.
Даны две замороженные карты X/Y и12 неизменных описаний. Для каждой карты и каждого описания реши, какие узлы подтверждаются именно данным текстом. При покрытии части описания выбери partial; если нет подходящего узла — no_match; если текст или границы не позволяют решить — uncertain. covered допустим, когда существенные действия описания покрыты без нарушения условий узлов. Частичная связь не означает эквивалентность всего определения. Сравнивай существенные условия, включая представление и роли объектов. Техническая правильность текста описания не гарантируется: если применение нарушает условия узла, не засчитывай его как covered и укажи конкретное нарушение. Для такой проверки не требуется решать задачу.
Каждая связь должна иметь точную непрерывную цитату evidence из поля text. relation=exact означает соответствие описанной операции узлу, component — лишь подтверждённую часть. Сохрани uncovered — явно не покрытые действия или нарушенные условия. Не требуй всех возможных знаний, которых нет в тексте.
Выход: только JSON в назначенном файле, схема:
{"maps":[{"map_id":"X","items":[{"id":"T01","status":"covered|partial|no_match|uncertain","links":[{"node_id":"...","relation":"exact|component","evidence":"буквальная цитата","reason":"почему подходит с учётом условий"}],"uncovered":["..."],"note":"сомнения или основание отказа"}]}],"notes":["общие ограничения"]}
В maps должны быть обе карты, в каждой все12 описаний ровно один раз; при no_match links пуст. Проверить полноту и цитаты. Другие файлы не менять. В конце сообщить путь, число строк и трудные случаи, не повторять JSON.'''
    for repeat in (1, 2):
        input_path = HERE / f'inputs/application-r{repeat}.json'
        write(input_path, {'maps': maps if repeat == 1 else list(reversed(maps)),
                           'stimuli': [{'id': s['id'], 'text': s['text']} for s in (stimuli if repeat == 1 else list(reversed(stimuli)))]})
        job = common + f'\nВХОД: {input_path.relative_to(ROOT).as_posix()}\nВЫХОД: research/2026-10-27-map-alternatives/raw/application-r{repeat}.json\n'
        (HERE / f'jobs/application-r{repeat}.txt').write_text(job, encoding='utf-8')
    write(HERE / 'application-input-manifest.json', {'catalogs_sha256': digest(HERE / 'frozen-catalogs.json'),
          'stimuli_sha256': digest(HERE / 'inputs/stimuli.json'),
          'inputs': {f'application-r{r}': digest(HERE / f'inputs/application-r{r}.json') for r in (1, 2)},
          'jobs': {f'application-r{r}': digest(HERE / f'jobs/application-r{r}.txt') for r in (1, 2)},
          'blinding': 'Neutral labels and no design names; content may reveal the design. Both use the same model family; not independent experts.'})
    print('Prepared 12 descriptions: 7 saved steps + 5 synthetic. Two applications, reversed order in r2.')


if __name__ == '__main__':
    main()
