"""Freeze cards, exact incoming states and paired context-probe jobs.

No model calls. Refuses replacement of frozen inputs.
"""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, data):
    path.parent.mkdir(exist_ok=True, parents=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


JOB = '''Применение фиксированной карточки к ТЕКУЩЕМУ шагу, не решение задачи. Читай только назначенный вход и задание. Не читать другие исследования, корпус, другой вариант контекста или ответы других агентов. Не browse, не вычисляй решение заново, не дописывай шаги. Вход содержит3случая; узел уже задан.
current — действие, которое оценивается сейчас. context — буквальные результаты предшествующих шагов, если они переданы. Контекст можно использовать для известности входного состояния и предусловий, но он НЕ доказывает, что предыдущее действие заново выполнено в current. Нужна ссылка на сторону каждой цитаты.
Для каждого случая:
operation_observed=full|partial|none|uncertain — форма и объём одного применения core_operation в current. Учитывай evidence_rule, includes/excludes. Если правило было применено при нарушенных условиях, форму и допустимость оценивай раздельно. Нельзя приписывать действие только по совпадению слов или выполнению его раньше. operation_evidence — буквальные цитаты только из current.
input_state=supported|not_shown|violated — доступно ли требуемое input_representation. input_evidence может ссылаться на current или context. Нельзя восстанавливать недостающий вход по одной применённой формуле.
Для каждого precondition: status=known|not_shown|violated; evidence с источником current либо id элемента context. known допустимо для явно данного факта или непосредственного чтения явно предъявленного входа (например, ненулевой числовой старший коэффициент в записанном квадратном уравнении). Объясни такое чтение. Неизвестное условие не означает ошибку математики. checked_in_current=true только если current сам устанавливает/проверяет этот предикат, не просто использует известный факт. Примечания алгоритма не являются дополнительными предусловиями.
coverage=full|partial|none — покрывает ли узел все действия current. remainder — цитаты непокрытого; эта оценка отделена от operation_observed.
Итог support СТРОГО:
если operation_observed=none -> no_current_action;
иначе если input_state=violated или хотябыоднопредусловие violated -> violated_application;
иначе если operation_observed=full, input_state=supported и всепредусловия known -> supported_application;
иначе -> conditional_application.
Не выводить освоение ученика. Случаи с недостатком контекста и неисполненной операцией — разные причины отказа.
JSONвыход:
{"rows":[{"id":"Q01","operation_observed":"full|partial|none|uncertain","operation_evidence":[{"source":"current","quote":"буквальная цитата"}],"input_state":"supported|not_shown|violated","input_evidence":[{"source":"current|before_s1|...","quote":"..."}],"preconditions":[{"id":"p1","status":"known|not_shown|violated","checked_in_current":false,"evidence":[{"source":"...","quote":"..."}],"reason":"основание"}],"coverage":"full|partial|none","remainder":[{"source":"current","quote":"..."}],"support":"...","note":"что доказано/неизвестно"}],"limits":["..."]}
Для known/violated и supported/violated input нужны непустые буквальные evidence; для not_shown допускаются пустые. Все id предусловий карточки присутствуют ровно один раз. Каждый Q01/Q02/Q03 ровно один раз. Точные источники ограничены current и id реально переданного context. Сохраняй только назначенный выход, проверь JSON и цитаты. Финал — путь и прочитанные файлы, без повторения всего ответа.
'''


def main():
    assert not (HERE / 'frozen.json').exists(), 'Already frozen'
    cards_path = HERE / 'raw/cards-v02.json'
    cards_doc = read(cards_path)
    cards = {c['candidate_id']: c for c in cards_doc['cards']}
    assert set(cards) == {'lin_eq', 'quad_D', 'log_domain', 'vec_endpoints', 'vec_lincomb', 'vec_dot', 'mean_freq', 'median'}
    official = read(HERE / 'inputs/official.json')
    lookups = {kind: {r['code']: r['text'] for r in official[kind]['entries']} for kind in ('content', 'requirements')}
    for c in cards.values():
        assert 0 < len(c['preconditions']) <= 4
        assert len({p['id'] for p in c['preconditions']}) == len(c['preconditions'])
        assert any(l['kind'] == 'content' for l in c['official_links'])
        for link in c['official_links']:
            assert link['anchor'] and link['anchor'] in lookups[link['kind']][link['code']]
    specs = [('Q01', '699100', 's4', ['s1', 's3'], 'quad_D'),
             ('Q02', '699086', 's3', ['s1', 's2'], 'vec_dot'),
             ('Q03', '699099', 's2', ['s1'], 'log_domain')]
    cases = []
    for id_, task, current_id, before_ids, candidate in specs:
        path = ROOT / f'data/annotation/runs/2026-10-25-A-19x3/raw/{task}_r1.txt'
        doc = read(path)
        indexed = {s['id']: (i, s) for i, s in enumerate(doc['steps'])}
        i, current = indexed[current_id]
        context = []
        for before_id in before_ids:
            before_i, step = indexed[before_id]
            assert before_i < i
            context.append({'id': 'before_' + before_id, 'text': step['result'],
                            'provenance': {'path': path.relative_to(ROOT).as_posix(),
                                           'sha256': sha(path), 'json_pointer': f'/steps/{before_i}/result'}})
        cases.append({'id': id_, 'candidate': cards[candidate],
                      'current': current['action'] + '\n' + current['result'],
                      'context': context,
                      'provenance': {'path': path.relative_to(ROOT).as_posix(), 'sha256': sha(path),
                                     'json_pointer': f'/steps/{i}'}})
    write(HERE / 'inputs/context-cases.json', {'cases': cases})
    for arm in ('plain', 'state'):
        for repeat in (1, 2):
            name = f'context-{arm}-r{repeat}'
            rows = []
            for c in cases if repeat == 1 else reversed(cases):
                rows.append({'id': c['id'], 'candidate': c['candidate'], 'current': c['current'],
                             'context': [{'id': t['id'], 'text': t['text']} for t in c['context']] if arm == 'state' else []})
            write(HERE / f'inputs/{name}.json', {'cases': rows})
            (HERE / f'jobs/{name}.txt').write_text(JOB + f'\nВХОД: research/2026-10-27-map-context-transfer/inputs/{name}.json\nВЫХОД: research/2026-10-27-map-context-transfer/raw/{name}.json\n', encoding='utf-8')
    files = ['PROTOCOL.md', 'jobs/cards.txt', 'jobs/legacy-source.txt', 'inputs/official.json',
             'raw/cards-v02.json', 'inputs/legacy-sample.json', 'inputs/context-cases.json']
    files += [f'{kind}/context-{arm}-r{r}.{ext}' for arm in ('plain', 'state') for r in (1, 2)
              for kind, ext in [('inputs', 'json'), ('jobs', 'txt')]]
    write(HERE / 'frozen.json', {'files': [{'path': name, 'sha256': sha(HERE / name)} for name in files],
                               'limits': 'Refined cards, known cases; this freezes inputs, not semantic truth or learner skill boundaries.'})
    print('Frozen8cards,6legacytasks,3pairedcasesand4jobs')


if __name__ == '__main__':
    main()
