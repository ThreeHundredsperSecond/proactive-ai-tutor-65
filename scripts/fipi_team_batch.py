"""Team batch packets for the frozen FIPI queue (fipi-extension-v1.1). No model calls.

Prepares a separate run directory for a reserved range of the queue: copies the
methodology files bitwise, copies task inputs and images from the saved bank,
builds author/auditor request packets with local image paths, logs agent
executions and validates saved answers with the historical validators.
Historical runs and scripts are read, never modified.

Commands (from the repository root):
  prepare        --run DIR --issue URL --owner LOGIN --from-order N --to-order M --model ID
  reserve        --run DIR --confirmed-by NAME --comment-url URL   (record coordinator's `reserved`)
  verify         --run DIR
  audit-request  --run DIR --task ID
  exec-start     --run DIR --role author|auditor --task ID
  exec-finish    --run DIR --role author|auditor --task ID [--agent-id X] [--message TEXT]
  validate       --run DIR --role author|auditor --task ID
  status         --run DIR
"""
import argparse
import hashlib
import importlib.metadata
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import fipi_extension as fx  # noqa: E402  (historical module; RUN is patched per call)
from fipi_eda50 import validate_one  # noqa: E402

SRC = ROOT / 'data/annotation/runs/2026-11-02-fipi-extension-150'
BANK = ROOT / 'data/fipi/2026-10-31-profile'
TEAM = ROOT / 'data/annotation/team'
METHOD_VERSION = 'fipi-extension-v1.1'
METHOD_FILES = ['PROTOCOL.md', 'author-prompt.txt', 'author-wrapper.txt', 'auditor-prompt.txt',
                'audit-format-wrapper-v1.1.txt', 'catalog-for-auditor.json', 'execution-protocol-v1.1.json']
CHECK_KINDS = ['sample-plan', 'math-expected', 'math-supplement']
SEP = '\nВХОД:\n'


def now():
    return datetime.now(timezone.utc).isoformat()


def sha(b):
    return hashlib.sha256(b).hexdigest()


def fsha(p):
    return sha(Path(p).read_bytes())


def read(p):
    return json.loads(Path(p).read_text(encoding='utf-8'))


def rel(p):
    return Path(p).resolve().relative_to(ROOT).as_posix()


def write(p, data):
    """Mutable JSON (logs, reservation state)."""
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def freeze(p, data):
    """Write once; on rerun the content must be byte-identical."""
    fx.freeze(p, data)


def condition(r):
    return {k: r[k] for k in ['instruction', 'statement_html', 'assets', 'mathml_count']}


def run_dir(arg):
    p = (ROOT / arg).resolve()
    assert p.is_relative_to(ROOT / 'data/annotation/runs'), 'run must be under data/annotation/runs/'
    assert p != SRC.resolve(), 'never write into the historical run'
    return p


def bank_records():
    return {r['id']: r for r in (json.loads(x) for x in (BANK / 'tasks.jsonl').read_text(encoding='utf-8').splitlines())}


def author_packet(run, r):
    packet = (run / 'author-prompt.txt').read_text(encoding='utf-8') + '\n' + (run / 'author-wrapper.txt').read_text(encoding='utf-8')
    packet += SEP + json.dumps({'task_id': r['id'], **condition(r),
                                'image_files': [str((run / 'inputs' / a['path']).resolve()) for a in r['assets']]},
                               ensure_ascii=False, indent=2)
    return packet


def same_request_except_images(old, new):
    """Historical requests carry absolute Windows image paths; everything else must match."""
    op, oj = old.split(SEP, 1)
    np_, nj = new.split(SEP, 1)
    oj, nj = json.loads(oj), json.loads(nj)
    oi, ni = oj.pop('image_files'), nj.pop('image_files')
    names = lambda xs: [x.replace('\\', '/').rsplit('/', 1)[-1] for x in xs]
    return op == np_ and oj == nj and names(oi) == names(ni)


def prepare(a):
    run = run_dir(a.run)
    if (run / 'manifest.json').exists():
        verify(a)
        print('Already prepared; nothing re-selected or rewritten.')
        return
    registry = read(TEAM / 'registry.json')
    assert registry['method_version'] == METHOD_VERSION
    methodology = []
    for name in METHOD_FILES:
        src = SRC / name
        want = registry['methodology_sha256'][rel(src)]
        assert fsha(src) == want, f'methodology drift: {name}'
        freeze(run / name, src.read_bytes())
        methodology.append({'path': name, 'sha256': want, 'source': rel(src)})

    from fipi_team_registry import check_claim
    selection = read(SRC / 'selection.json')
    items = [t for t in selection['tasks'] if a.from_order <= t['order'] <= a.to_order]
    assert items and len(items) == a.to_order - a.from_order + 1
    ids = [t['task_id'] for t in items]
    errors = check_claim(registry, read(TEAM / 'claims.json'), ids)
    assert not errors, errors

    bank = bank_records()
    tasks = []
    for t in items:
        tid = t['task_id']
        r = bank[tid]
        src_input = BANK / 'tasks' / (tid + '.json')
        freeze(run / 'inputs/tasks' / (tid + '.json'), src_input.read_bytes())
        assert fsha(src_input) == fsha(SRC / 'inputs/tasks' / (tid + '.json')), f'input differs from frozen queue: {tid}'
        assets = []
        for asset in r['assets']:
            data = (BANK / asset['path']).read_bytes()
            assert sha(data) == fsha(SRC / 'inputs' / asset['path']), f'asset differs: {asset["path"]}'
            if asset.get('sha256'):
                assert sha(data) == asset['sha256'], f'asset hash mismatch: {asset["path"]}'
            freeze(run / 'inputs' / asset['path'], data)
            assets.append({'path': asset['path'], 'sha256': sha(data)})
        packet = author_packet(run, r)
        assert same_request_except_images((SRC / 'requests/author' / (tid + '.txt')).read_text(encoding='utf-8'), packet), tid
        req = run / 'requests/author' / (tid + '.txt')
        freeze(req, packet)
        tasks.append({**{k: t[k] for k in ['order', 'task_id', 'batch', 'primary_kes', 'response_type', 'images', 'mathml']},
                      'input_sha256': fsha(src_input), 'request_sha256': fsha(req), 'assets': assets})

    batches = sorted({t['batch'] for t in items})
    checks = []
    for b in batches:
        for kind in CHECK_KINDS:
            src = SRC / 'checks' / f'batch-{b:02}-{kind}.json'
            if src.exists():
                freeze(run / 'checks' / src.name, src.read_bytes())
                checks.append({'path': 'checks/' + src.name, 'sha256': fsha(src), 'source': rel(src)})

    freeze(run / 'active-attempts.json', {})
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT).decode().strip()
    branch = subprocess.check_output(['git', 'branch', '--show-current'], cwd=ROOT).decode().strip()
    freeze(run / 'manifest.json', {
        'schema_version': 1, 'method_version': METHOD_VERSION, 'issue_url': a.issue, 'owner': a.owner,
        'base_commit': commit, 'branch': branch, 'source_run': rel(SRC),
        'queue_orders': [a.from_order, a.to_order], 'batches': {str(b): [t['task_id'] for t in items if t['batch'] == b] for b in batches},
        'sources': {rel(p): fsha(p) for p in [BANK / 'tasks.jsonl', SRC / 'selection.json', TEAM / 'registry.json']},
        'methodology': methodology, 'predeclared_checks': checks,
        'request_equivalence': 'author requests identical to the frozen queue requests except absolute image_files paths',
        'tasks': tasks})
    packages = {}
    for p in ['lxml', 'Pillow', 'numpy', 'matplotlib', 'nbformat', 'nbclient']:
        try:
            packages[p] = importlib.metadata.version(p)
        except importlib.metadata.PackageNotFoundError:
            packages[p] = None
    freeze(run / 'environment.json', {
        'prepared_at': now(), 'python': platform.python_version(), 'platform': platform.platform(),
        'git_commit': commit, 'branch': branch, 'packages': packages,
        'prepare_command': 'python3 scripts/fipi_team_batch.py ' + ' '.join(sys.argv[1:]),
        'agent_mechanism': 'Claude Code Agent tool; fresh general-purpose subagent per author/auditor task; no fork',
        'model_identifier': a.model, 'api_client': 'none; agents run inside a Claude Code session'})
    if not (run / 'reservation.json').exists():
        write(run / 'reservation.json', {'issue_url': a.issue, 'status': 'proposed', 'task_ids': ids,
                                         'updated_at': now(), 'note': 'Only coordinator `reserved` in the issue authorizes generation.'})
    print(json.dumps({'run': rel(run), 'tasks': len(tasks), 'batches': {b: len(v) for b, v in
                      read(run / 'manifest.json')['batches'].items()}, 'predeclared_checks': len(checks)}, ensure_ascii=False))


def reserve(a):
    run = run_dir(a.run)
    r = read(run / 'reservation.json')
    r.update(status='reserved', confirmed_by=a.confirmed_by, confirmation_url=a.comment_url, updated_at=now())
    write(run / 'reservation.json', r)
    print('Recorded coordinator confirmation:', a.comment_url)


def verify(a):
    run = run_dir(a.run)
    m = read(run / 'manifest.json')
    for x in m['methodology'] + m['predeclared_checks']:
        assert fsha(run / x['path']) == x['sha256'], x['path']
    for t in m['tasks']:
        assert fsha(run / 'inputs/tasks' / (t['task_id'] + '.json')) == t['input_sha256'], t['task_id']
        assert fsha(run / 'requests/author' / (t['task_id'] + '.txt')) == t['request_sha256'], t['task_id']
        for x in t['assets']:
            assert fsha(run / 'inputs' / x['path']) == x['sha256'], x['path']
    print('Frozen inputs, requests, methodology and predeclared checks byte-identical:', len(m['tasks']), 'tasks')


def active(run, tid, role):
    overrides = read(run / 'active-attempts.json')
    return run / overrides.get(tid, {}).get(role, f'raw/{role}/{tid}.json')


def audit_request(run, tid):
    dest = run / 'requests/auditor-v1.1' / (tid + '.txt')
    freeze(dest, audit_packet(run, tid))
    return dest


def audit_packet(run, tid):
    author = active(run, tid, 'author')
    d = read(author); validate_one(d); assert d['task_id'] == tid
    inp = read(run / 'inputs/tasks' / (tid + '.json'))
    body = {'task_id': tid, **condition(inp), 'author_response': d,
            'image_files': [str((run / 'inputs' / x['path']).resolve()) for x in inp['assets']],
            'catalog': read(run / 'catalog-for-auditor.json')}
    packet = (run / 'auditor-prompt.txt').read_text(encoding='utf-8') + SEP + json.dumps(body, ensure_ascii=False, indent=2)
    refs = ['condition'] + [f'step:{s["id"]}:{k}' for s in d['steps'] for k in ['action', 'result']]
    refs += ['image:' + x['path'] for x in inp['assets']]
    packet += '\n' + (run / 'audit-format-wrapper-v1.1.txt').read_text(encoding='utf-8') + '\n'
    packet += json.dumps({'allowed_refs': refs}, ensure_ascii=False, indent=2) + '\n'
    return packet


def check(run, role, tid):
    raw = active(run, tid, role)
    if role == 'author':
        d = read(raw); validate_one(d); assert d['task_id'] == tid
        return {'task_id': tid, 'status': 'technical_pass', 'solution_status': d['solution_status']}
    fx.RUN = run  # historical validator reads inputs and catalog from RUN
    return fx.validate_audit(tid, raw, author_path=rel(active(run, tid, 'author')))


def exec_start(a):
    run = run_dir(a.run)
    res = read(run / 'reservation.json')
    assert res['status'] == 'reserved' and res.get('confirmation_url'), 'No coordinator `reserved` recorded: generation not authorized'
    assert a.task in res['task_ids'], 'task outside the reservation'
    rec = run / 'executions' / f'{a.role}-{a.task}.json'
    raw = run / 'raw' / a.role / (a.task + '.json')
    assert not rec.exists() and not raw.exists(), 'already started; corrections go to attempts/'
    req = run / 'requests/author' / (a.task + '.txt') if a.role == 'author' else audit_request(run, a.task)
    inp = read(run / 'inputs/tasks' / (a.task + '.json'))
    images = [run / 'inputs' / x['path'] for x in inp['assets']]
    msg = (f'Роль: {a.role}. Прочитай только запрос {req} и перечисленные в нём image_files; '
           'каждое изображение открой инструментом Read. Следуй полной инструкции запроса. '
           'Другие файлы, решения, каталоги вне запроса, история и сеть запрещены. Нельзя запускать агентов. '
           f'Сохрани ровно один точный JSON без markdown в {raw}; создай родительскую папку при необходимости, '
           'файл создавать только если отсутствует, не перезаписывать. '
           'После сохранения сообщи путь и фактически просмотренные image_files. Не изменяй иных файлов.')
    write(rec, {'role': a.role, 'task_id': a.task, 'spawn_message': msg, 'agent_id': None, 'start_utc': now(), 'end_utc': None,
                'request': {'path': rel(req), 'sha256': fsha(req)},
                'passed_image_paths': [{'path': rel(p), 'sha256': fsha(p)} for p in images],
                'raw_path': rel(raw), 'fork': 'none', 'model': read(run / 'environment.json')['model_identifier'],
                'mechanism': 'Claude Code Agent tool; fresh subagent context'})
    print(msg)


def exec_finish(a):
    run = run_dir(a.run)
    rec = run / 'executions' / f'{a.role}-{a.task}.json'
    d = read(rec)
    raw = run / 'raw' / a.role / (a.task + '.json')
    d.update(end_utc=now(), agent_id=a.agent_id or d['agent_id'], raw_sha256=fsha(raw) if raw.exists() else None,
             completion_message=a.message or '')
    write(rec, d)
    try:
        result, code = check(run, a.role, a.task), 0
    except Exception as e:  # validation failure is data, not a crash
        result, code = {'task_id': a.task, 'status': 'technical_fail', 'error': repr(e)}, 1
    write(run / 'validations' / f'{a.role}-{a.task}.json', {'result': result, 'at_utc': now()})
    print(json.dumps(result, ensure_ascii=False))
    sys.exit(code)


def validate(a):
    print(json.dumps(check(run_dir(a.run), a.role, a.task), ensure_ascii=False))


def status(a):
    run = run_dir(a.run)
    m = read(run / 'manifest.json')
    res = read(run / 'reservation.json')
    rows = []
    for b, ids in m['batches'].items():
        authors = sum((run / 'raw/author' / (t + '.json')).exists() for t in ids)
        auditors = sum((run / 'raw/auditor' / (t + '.json')).exists() for t in ids)
        health = (run / 'checks' / f'batch-{int(b):02}.json').exists()
        rows.append({'batch': int(b), 'tasks': len(ids), 'authors': authors, 'auditors': auditors, 'health_check': health})
    print(json.dumps({'reservation': res['status'], 'issue': res['issue_url'], 'batches': rows}, ensure_ascii=False, indent=1))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('command', choices=['prepare', 'reserve', 'verify', 'audit-request', 'exec-start', 'exec-finish', 'validate', 'status'])
    p.add_argument('--run', required=True)
    p.add_argument('--issue'); p.add_argument('--owner'); p.add_argument('--model')
    p.add_argument('--from-order', type=int); p.add_argument('--to-order', type=int)
    p.add_argument('--confirmed-by'); p.add_argument('--comment-url')
    p.add_argument('--role', choices=['author', 'auditor']); p.add_argument('--task')
    p.add_argument('--agent-id'); p.add_argument('--message')
    a = p.parse_args()
    if a.command == 'audit-request':
        print(rel(audit_request(run_dir(a.run), a.task)))
    else:
        {'prepare': prepare, 'reserve': reserve, 'verify': verify, 'exec-start': exec_start,
         'exec-finish': exec_finish, 'validate': validate, 'status': status}[a.command](a)


if __name__ == '__main__':
    main()
