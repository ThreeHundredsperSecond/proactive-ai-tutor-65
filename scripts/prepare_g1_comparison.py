"""Freeze the authorized 5-task x 3 G1 test. No model calls; never overwrite a run."""
import json
import hashlib
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
OLD = ROOT / 'data/annotation/runs/2026-10-25-A-19x3'
RUN = ROOT / 'data/annotation/runs/2026-10-26-G1-5x3'


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    RUN.mkdir(exist_ok=False)
    for directory in ('inputs', 'images', 'requests', 'jobs', 'raw', 'baseline', 'derived'):
        (RUN / directory).mkdir()
    a = (OLD / 'prompt-A.txt').read_text(encoding='utf-8')
    delta = (ROOT / 'data/annotation/iterations/2026-10-26-G1-vector/delta-G1.txt').read_text(encoding='utf-8')
    candidate = a.replace('В одном ответе построй решение', delta + '\nВ одном ответе построй решение')
    assert candidate != a
    (RUN / 'baseline-A.txt').write_bytes(a.encode('utf-8'))
    (RUN / 'delta-G1.txt').write_bytes(delta.encode('utf-8'))
    (RUN / 'candidate-A-G1.txt').write_bytes(candidate.encode('utf-8'))
    old_manifest = json.loads((OLD / 'manifest.json').read_text(encoding='utf-8'))
    old_ledger = json.loads((OLD / 'responses.json').read_text(encoding='utf-8'))
    tasks, jobs = [], []
    for task in old_manifest['tasks']:
        if task['position'] not in (2, 3, 6, 7, 8):
            continue
        tid = task['task_id']
        inp = OLD / 'inputs' / f'{tid}.json'
        assert sha(inp) == task['input_sha256']
        (RUN / 'inputs' / inp.name).write_bytes(inp.read_bytes())
        for im in task['images']:
            assert sha(OLD / im['path']) == im['png_sha256']
            (RUN / im['path']).write_bytes((OLD / im['path']).read_bytes())
        payload = json.loads(inp.read_text(encoding='utf-8'))
        request = candidate.replace('{task_json}', json.dumps(payload, ensure_ascii=False, indent=2))
        (RUN / 'requests' / f'{tid}.txt').write_bytes(request.encode('utf-8'))
        for repeat in (1, 2, 3):
            job = f'{tid}_r{repeat}'
            old_raw = OLD / 'raw' / f'{job}.txt'
            assert sha(old_raw) == old_ledger[job]['raw_sha256']
            (RUN / 'baseline' / old_raw.name).write_bytes(old_raw.read_bytes())
            instruction = (
                'Прочитай только этот job и UTF-8 запрос '
                + (RUN / 'requests' / f'{tid}.txt').as_posix() + '. '
                + ''.join('Просмотри изображение ' + (RUN / i['path']).as_posix() + ' через view_image. ' for i in task['images'])
                + 'Затем выполни запрос: решай самостоятельно, без инструментов для решения или проверки. '
                'Не читай документы, baseline, другие ответы или исходный корпус. '
                'Загрузка входа и запись результата — разрешённые технические операции. '
                'Когда итоговый JSON готов, сохрани его полностью без Markdown в '
                + (RUN / 'raw' / f'{job}.txt').as_posix()
                + '. Не перезаписывай существующий ответ. Верни только путь raw-файла.\n'
            )
            (RUN / 'jobs' / f'{job}.txt').write_bytes(instruction.encode('utf-8'))
            jobs.append({'job_id': job, 'task_id': tid, 'repeat': repeat,
                         'agent_task': f'/root/g1p{task["position"]:02d}r{repeat}',
                         'raw_path': f'raw/{job}.txt', 'baseline_sha256': sha(old_raw),
                         'instruction_sha256': sha(RUN / 'jobs' / f'{job}.txt')})
        tasks.append({'task_id': tid, 'position': task['position'], 'images': [
            {'path': i['path'], 'sha256': i['png_sha256']} for i in task['images']],
            'input_sha256': sha(inp), 'request_sha256': sha(RUN / 'requests' / f'{tid}.txt')})
    manifest = {'run_id': RUN.name, 'created_at_utc': datetime.now(timezone.utc).isoformat(),
                'selection': 'purposeful: positions 2,3,6,7,8; boundaries differ in previous responses',
                'expected_responses': 15, 'repeats': 3, 'tasks': tasks, 'jobs': jobs,
                'baseline_run': OLD.relative_to(ROOT).as_posix(),
                'baseline_prompt_sha256': sha(OLD / 'prompt-A.txt'),
                'candidate_sha256': sha(RUN / 'candidate-A-G1.txt'),
                'delta_sha256': sha(RUN / 'delta-G1.txt'),
                'prepare_script_sha256': sha(Path(__file__)),
                'protocol_sha256': sha(ROOT / 'docs/eda/04-annotation/08-g1-five-task-comparison.md'),
                'runtime': 'isolated agents, fork_turns=none, no override; model parameters unknown',
                'reviewer': 'primary agent, nonblind; not expert validation'}
    (RUN / 'manifest.json').write_bytes((json.dumps(manifest, ensure_ascii=False, indent=2)+'\n').encode('utf-8'))
    print('Frozen:', RUN, '| expected new responses:', len(jobs))


if __name__ == '__main__':
    main()
