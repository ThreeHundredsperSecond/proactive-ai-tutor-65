"""Render cross-task candidate evidence from saved judgments; never call a model."""
import csv
import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data/annotation/reviews/2026-10-26-cross-task'
OUT = ROOT / 'docs/eda/04-annotation/09-cross-task-kc-examples.md'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def link(path):
    return Path(os.path.relpath(path, OUT.parent)).as_posix()


def main():
    decisions = json.loads((DATA / 'decisions.json').read_text(encoding='utf-8'))
    run = ROOT / decisions['source_run']
    ledger = json.loads((run / 'responses.json').read_text(encoding='utf-8'))
    req = ROOT / 'docs/eda/01-exam/requirements-map.md'
    content = ROOT / 'docs/eda/01-exam/content-map.md'
    maps = {'requirement': req, 'content': content}
    sources = {DATA / 'decisions.json', run / 'responses.json', req, content, Path(__file__)}
    rows, all_positions = [], set()

    def evidence(e):
        tid = str(699084 + e['position'])
        job = f'{tid}_r{e["repeat"]}'
        path = run / 'raw' / f'{job}.txt'
        assert sha(path) == ledger[job]['raw_sha256']
        d = json.loads(path.read_text(encoding='utf-8'))
        s = next(x for x in d['steps'] if x['id'] == e['step'])
        k = next(x for x in d['kc_candidates'] if x['id'] == e['kc'])
        assert k['id'] in s['kc_ids']
        sources.add(path)
        all_positions.add(e['position'])
        return path, s, k

    lines = ['# Примеры общих KC между разными задачами', '',
             '26 октября 2026. Предварительные кандидаты основного агента; не экспертная проверка, не окончательный каталог. Новых генераций нет. Рассмотрены сохранённые r1 на семи задачах, выбранных целевым образом.', '',
             '## Краткий результат', '',
             '| Кандидат | Задачи | Что совпадает | Статус связи |', '|---|---|---|---|']
    for c in decisions['candidates']:
        positions = sorted({e['position'] for e in c['evidence']})
        status = 'Одна операция, кандидат' if c['relation'] == 'same_operation_candidate' else 'Общий компонент более широких KC'
        lines.append(f'| {c["name"]} | {", ".join("№" + str(p) for p in positions)} | Действие и результат при указанных условиях | {status} |')
    lines += ['', 'Это четыре примера существования общих операций, а не четыре новых доказанных навыка. Связи чтения координат уже встречались в прежнем черновом каталоге. Для остальных примеров выделен общий компонент; целые исходные определения не объявлены эквивалентными.', '',
              '## Свидетельства и границы', '']
    for c in decisions['candidates']:
        lines += [f'### {c["name"]}', '', f'Кандидат `{c["id"]}`. {c["definition"]}', '']
        for e in c['evidence']:
            path, s, k = evidence(e)
            lines += [f'**[№{e["position"]}, r{e["repeat"]}, {e["step"]}, {e["kc"]}]({link(path)})**', '',
                      'Точное действие и результат:', '', '```text', s['action'], s['result'], '```', '',
                      f'Исходный KC: **{k["name"]}**. {k["description"]}', '']
            rows.append({'candidate_id': c['id'], 'relation': c['relation'], 'position': e['position'],
                         'task_id': str(699084 + e['position']), 'repeat': e['repeat'],
                         'step_id': e['step'], 'source_kc_id': e['kc'],
                         'raw_path': path.relative_to(ROOT).as_posix(), 'raw_sha256': sha(path)})
        lines += [f'**Основание связи:** {c["reason"]}', '', f'**Граница:** {c["boundary"]}', '',
                  f'**Для тьютора — гипотеза:** {c["tutor_hypothesis"]}', '']
        refs = []
        for ref in c['fipi_directions']:
            source = maps[ref['kind']]
            assert f'| {ref["code"]} |' in source.read_text(encoding='utf-8')
            label = 'требование' if ref['kind'] == 'requirement' else 'содержание'
            refs.append(f'[{label} {ref["code"]}]({link(source)})')
        lines += ['**Предложенное направление связи с ФИПИ:** ' + '; '.join(refs) + '. Это интерпретация проекта, не опубликованное ФИПИ соответствие задачи и KC. Коды требований и содержания независимы.', '']
    lines += ['## Контрпример: похожая тема, разные операции', '']
    for case in decisions['negative_cases']:
        lines += [f'### {case["name"]}', '']
        for e in case['evidence']:
            path, s, k = evidence(e)
            lines += [f'**[№{e["position"]}, {e["step"]}, {e["kc"]}]({link(path)})** — {k["name"]}.', '',
                      '```text', s['result'], '```', '']
        lines += [case['reason'], '', '**Решение:** ' + case['decision'], '']
    lines += ['## Что удалось посчитать, а что ещё нет', '',
              '- У каждого из четырёх кандидатов есть свидетельства минимум в двух разных задачах: всего восемь положительных связей с конкретными шагами. Повторы одной задачи не увеличивают число задач.',
              '- Одна пара исходных определений рассматривается как одна операция; три других пары связываются через общий компонент. Это разные типы соответствия, их нельзя смешать в число «объединённых KC».',
              '- Два подтверждающих примера — нижняя граница поддержки, а не полная частота по 19 задачам: другие повторы и задачи систематически не проверялись.',
              '- Доля корректных связей не установлена: примеры отбирал и оценивал один агент. Наличие цитаты проверяется кодом, смысл соответствия — нет.',
              '- Покрытие ФИПИ в процентах не рассчитано. Направления связи с широкими официальными пунктами не означают полного покрытия этих пунктов.', '',
              '**Вывод:** общий каталог может связывать разные типы задач, однако нужно хранить точную операцию, контекст и отношение «тот же KC / общий компонент / иной способ». Совпадение цели или темы недостаточно. Полезность для диагностики ученика пока не подтверждена.', '',
              '## Воспроизведение и продолжение', '',
              f'Смысловые решения — [decisions.json]({link(DATA / "decisions.json")}); таблица свидетельств — [evidence.csv]({link(DATA / "evidence.csv")}); SHA-256 — [provenance.json]({link(DATA / "provenance.json")}).', '',
              'Из корня репозитория: `python scripts/review_cross_task_kcs.py`. Код проверяет сохранность raw, существование шагов, назначение исходного KC шагу и наличие официальных кодов в локальных картах; затем воспроизводит документ и таблицу. Он не принимает решения о семантическом равенстве и не запускает модель.', '',
              'Следующий ограниченный шаг — просмотреть эти четыре определения и на уже сохранённых ответах проверить дополнительные подтверждения и контрпримеры. Если пригодность границ подтверждается, использовать определения как рабочие кандидаты общего каталога. Новую генерацию или расширение всего каталога автоматически не запускаем.', '']
    OUT.write_bytes(('\n'.join(lines)).encode('utf-8'))
    with (DATA / 'evidence.csv').open('w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator='\n')
        w.writeheader()
        w.writerows(rows)
    provenance = {'status': decisions['status'], 'positive_candidates': len(decisions['candidates']),
                  'positive_evidence_rows': len(rows), 'tasks_inspected_including_negative': sorted(all_positions),
                  'inputs': {p.relative_to(ROOT).as_posix(): sha(p) for p in sorted(sources)},
                  'outputs': {p.relative_to(ROOT).as_posix(): sha(p) for p in (OUT, DATA / 'evidence.csv')}}
    (DATA / 'provenance.json').write_bytes((json.dumps(provenance, ensure_ascii=False, indent=2)+'\n').encode('utf-8'))
    print(f'Built {len(decisions["candidates"])} candidates, {len(rows)} evidence rows, {len(all_positions)} inspected tasks; no model calls.')


if __name__ == '__main__':
    main()
