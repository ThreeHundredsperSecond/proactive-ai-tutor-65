"""Prepare and inspect the 19-task A-FIPI run. All commands are offline."""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from annotation_pipeline import validate

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / 'data/annotation/runs/2026-10-26-A-FIPI-19x1'
OLD = ROOT / 'data/annotation/runs/2026-10-25-A-19x3'
TRIAL = ROOT / 'data/annotation/iterations/2026-10-26-A-FIPI-vector'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def write(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((json.dumps(obj, ensure_ascii=False, indent=2)+'\n').encode('utf-8'))


def prepare():
    RUN.mkdir(exist_ok=False)
    for directory in ('inputs', 'images', 'requests', 'jobs', 'raw', 'derived'):
        (RUN / directory).mkdir()
    trial_manifest = read(TRIAL / 'manifest.json')
    for name in ('catalog.json', 'prompt-A-FIPI-v1.txt', 'original-A.txt', 'delta-FIPI.txt'):
        assert sha(TRIAL / name) == trial_manifest['files'][name]
        (RUN / name).write_bytes((TRIAL / name).read_bytes())
    prompt = (RUN / 'prompt-A-FIPI-v1.txt').read_text(encoding='utf-8')
    catalog = read(RUN / 'catalog.json')['requirements']
    assert len(catalog) == 13 and all(r['requirement'] in prompt for r in catalog)
    tasks = []
    for task in read(OLD / 'manifest.json')['tasks']:
        tid, pos = task['task_id'], task['position']
        source = OLD / 'inputs' / f'{tid}.json'
        assert sha(source) == task['input_sha256']
        (RUN / 'inputs' / source.name).write_bytes(source.read_bytes())
        images = []
        for im in task['images']:
            assert sha(OLD / im['path']) == im['png_sha256']
            (RUN / im['path']).write_bytes((OLD / im['path']).read_bytes())
            images.append({'path': im['path'], 'sha256': im['png_sha256']})
        request = prompt.replace('{task_json}', json.dumps(read(source), ensure_ascii=False, indent=2))
        assert '{task_json}' not in request
        (RUN / 'requests' / f'{tid}.txt').write_bytes(request.encode('utf-8'))
        job = 'Прочитай только запрос ' + (RUN / 'requests' / f'{tid}.txt').as_posix() + '. '
        job += ''.join('Просмотри через view_image ' + (RUN / i['path']).as_posix() + '. ' for i in images)
        job += 'Выполни запрос самостоятельно. Не читай другие документы проекта, старые ответы или решения. Все требования ФИПИ уже внутри запроса. Загрузка запроса/изображений и запись ответа — технические операции. После загрузки математическое решение и разметка без инструментов, поиска или проверки. Полностью готовый JSON без Markdown сохрани в ' + (RUN / 'raw' / f'{tid}.txt').as_posix() + '. Не перезаписывай существующий файл. Верни только путь raw-файла.\n'
        (RUN / 'jobs' / f'{tid}.txt').write_bytes(job.encode('utf-8'))
        tasks.append({'task_id': tid, 'position': pos, 'images': images,
                      'input_sha256': sha(source), 'request_sha256': sha(RUN / 'requests' / f'{tid}.txt'),
                      'job_sha256': sha(RUN / 'jobs' / f'{tid}.txt'), 'agent_task': f'/root/fp19_{pos:02d}'})
    assert len(tasks) == 19
    write(RUN / 'manifest.json', {'run_id': RUN.name, 'created_at_utc': datetime.now(timezone.utc).isoformat(),
          'expected_responses': 19, 'repeats': 1, 'tasks': tasks,
          'prompt_sha256': sha(RUN / 'prompt-A-FIPI-v1.txt'), 'catalog_sha256': sha(RUN / 'catalog.json'),
          'prepare_script_sha256': sha(Path(__file__)),
          'protocol_sha256': sha(ROOT / 'docs/eda/04-annotation/10-fipi-19-run.md'),
          'runtime': '19 isolated agents, fork_turns=none, no overrides; exact model parameters unknown',
          'prior_single_trial_reused': False, 'review': 'primary agent, nonblind, preliminary; not expert validation'})
    (RUN / 'README.md').write_bytes(('''# A-FIPI-v1: 19 задач, один ответ на задачу

Протокол до запуска: [план и показатели](../../../../docs/eda/04-annotation/10-fipi-19-run.md).
Ожидаются ровно 19 новых самостоятельных разборов по условию и изображениям. Предыдущая одиночная проба в этот запуск не включается. Полный перечень 13 требований находится в каждом request.txt. Каталог содержания не используется. Промпт заморожен, G1 не добавлена.

`manifest.json` — реестр и SHA-256; `requests/` — полные запросы; `inputs/`, `images/` — входы; `jobs/` — техническая обвязка; `raw/` — неизменённые ответы.

Подготовка: `python scripts/fipi_annotation_run.py prepare` из корня. Отказывается перезаписать существующую папку; модель не вызывается. Генерация повторяется отдельно с job-файлами; совпадение ответов не гарантируется.
''').encode('utf-8'))
    print('Prepared 19 full requests:', RUN)


def inspect_response(d, catalog):
    extra = {'selected_requirements', 'fipi_links'}
    if not isinstance(d, dict) or not extra <= set(d):
        return ['missing FIPI fields']
    errors = validate({k: v for k, v in d.items() if k not in extra}, d.get('task_id'))
    selected = d['selected_requirements']
    if not isinstance(selected, list) or not all(isinstance(c, str) and c in catalog for c in selected) or len(selected) != len(set(selected)):
        errors.append('invalid selected_requirements')
    if not isinstance(d['fipi_links'], list):
        errors.append('fipi_links not list')
    if errors:
        return errors
    seen_kcs, seen_codes = set(), set()
    kcs = {k['id'] for k in d['kc_candidates']}
    for row in d['fipi_links']:
        if not isinstance(row, dict) or set(row) != {'requirement_code', 'kc_ids', 'anchor', 'reason'}:
            errors.append('link fields'); continue
        ids, code = row['kc_ids'], row['requirement_code']
        if not isinstance(ids, list) or not ids or not all(isinstance(k, str) and k in kcs for k in ids) or len(ids) != len(set(ids)):
            errors.append('KC link references'); continue
        seen_kcs.update(ids)
        if not isinstance(row['reason'], str) or not row['reason'].strip(): errors.append('missing reason')
        if code is None:
            if row['anchor'] != '': errors.append('unknown link anchor not empty')
        elif not isinstance(code, str) or code not in catalog:
            errors.append('unknown requirement code')
        else:
            seen_codes.add(code)
            if not isinstance(row['anchor'], str) or not row['anchor'].strip() or row['anchor'] not in catalog[code]:
                errors.append('anchor not literal substring')
    if seen_kcs != kcs: errors.append('unmapped KCs')
    if seen_codes != set(selected): errors.append('unused or unselected requirements')
    return errors


def capture():
    m = read(RUN / 'manifest.json')
    previous = read(RUN / 'responses.json') if (RUN / 'responses.json').exists() else {}
    for task in m['tasks']:
        tid = task['task_id']
        path = RUN / 'raw' / f'{tid}.txt'
        if path.exists():
            entry = {'agent_task': task['agent_task'], 'raw_sha256': sha(path),
                     'launch_message': f"Выполни только инструкцию C:/Users/U_M35CB/Documents/ВШЭ/proactive-ai-tutor-65/data/annotation/runs/2026-10-26-A-FIPI-19x1/jobs/{tid}.txt. Прочитай её и указанные запрос/изображения, другие материалы не читай. Сохрани полный итоговый JSON в назначенный raw-файл. Верни только его путь.",
                     'capture_method': 'Agent saved complete raw directly; no edits or replacements.'}
            if tid in previous and entry != previous[tid]: raise ValueError('Captured response changed')
            previous[tid] = entry
    write(RUN / 'responses.json', previous)
    print('Captured:', len(previous), '/ 19')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=('prepare', 'capture'))
    args = parser.parse_args()
    {'prepare': prepare, 'capture': capture}[args.command]()
