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
  exec-start     --run DIR --role author|auditor --task ID [--model ID]   (default: environment.json)
  attach         --run DIR --role author|auditor --task ID --agent-id X
  exec-finish    --run DIR --role author|auditor --task ID [--agent-id X] [--message TEXT]
  validate       --run DIR --role author|auditor --task ID
  status         --run DIR
  health-render  --run DIR --batch N       (needs .venv with lxml/Pillow and Google Chrome)
  health-math    --run DIR --batch N
  health-visual  --run DIR --batch N --reviewer TEXT [--findings JSON]
  health-finish  --run DIR --batch N

Re-running a finished batch (e.g. with another model) as a named attempt; raw/ stays unchanged:
  attempt-init   --run DIR --attempt NAME --batch N --model ID --reason TEXT
  exec-start / attach / exec-finish / validate / status / health-*  ... --attempt NAME
                 answers -> attempts/NAME/{author,auditor}/ID.json, logs -> executions|validations/ROLE-ID-NAME.json,
                 auditor requests -> requests/NAME/auditor-v1.1/, checks -> checks/batch-NN-NAME*.json
  activate       --run DIR --attempt NAME   (after health-finish; points active-attempts.json at the attempt)
"""
import argparse
import hashlib
import importlib.metadata
import json
import platform
import re
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


def paths(run, role, tid, attempt=None):
    """Answer, execution log and validation log of the original run (raw/) or of a named attempt."""
    if attempt:
        return (run / 'attempts' / attempt / role / (tid + '.json'),
                run / 'executions' / f'{role}-{tid}-{attempt}.json',
                run / 'validations' / f'{role}-{tid}-{attempt}.json')
    return (run / 'raw' / role / (tid + '.json'),
            run / 'executions' / f'{role}-{tid}.json',
            run / 'validations' / f'{role}-{tid}.json')


def answer(run, tid, role, attempt=None):
    """A named attempt's answer, or the active one (raw/ unless active-attempts.json points elsewhere)."""
    return paths(run, role, tid, attempt)[0] if attempt else active(run, tid, role)


def sfx(attempt):
    return f'-{attempt}' if attempt else ''


def attempt_meta(run, attempt):
    return read(run / 'attempts' / attempt / 'attempt.json')


def attempt_init(a):
    """Declare a separate re-run of one batch (e.g. another model). Originals in raw/ stay unchanged."""
    run = run_dir(a.run)
    assert a.attempt and a.model and a.batch and a.reason, '--attempt, --model, --batch and --reason are required'
    assert a.attempt.isidentifier() and a.attempt != 'raw', 'attempt name: letters, digits, underscore'
    meta = run / 'attempts' / a.attempt / 'attempt.json'
    if meta.exists():
        print('Attempt already declared:', rel(meta))
        return
    freeze(meta, {'attempt': a.attempt, 'model_identifier': a.model, 'batch': a.batch, 'task_ids': batch_ids(run, a.batch),
                  'reason': a.reason, 'created_at': now(),
                  'originals': 'raw/author and raw/auditor stay unchanged; activation only switches active-attempts.json'})
    print(rel(meta))


def activate(a):
    """Make a finished attempt the active answers of its batch. Originals stay where they are."""
    run = run_dir(a.run)
    assert a.attempt, '--attempt is required'
    meta = attempt_meta(run, a.attempt)
    b, ids = meta['batch'], meta['task_ids']
    health = read(run / 'checks' / f'batch-{b:02}{sfx(a.attempt)}.json')
    act = read(run / 'active-attempts.json')
    for t in ids:
        for role in ['author', 'auditor']:
            assert read(paths(run, role, t, a.attempt)[2])['result']['status'] == 'technical_pass', (role, t)
        new = {r: paths(run, r, t, a.attempt)[0].relative_to(run).as_posix() for r in ['author', 'auditor']}
        assert act.get(t) in (None, new), f'{t} already points to another attempt: {act.get(t)}'
        act[t] = new
    write(run / 'active-attempts.json', act)
    freeze(run / 'attempts' / a.attempt / 'activation.json', {
        'attempt': a.attempt, 'batch': b, 'model_identifier': meta['model_identifier'], 'activated_at': now(),
        'health_status': health['status'], 'quarantined_ids': health['quarantined_ids'], 'task_ids': ids,
        'previous_active': 'raw/ (kept unchanged)'})
    print('Activated', a.attempt, 'for batch', b, '-', len(ids), 'tasks')


def audit_request(run, tid, author=None, attempt=None):
    dest = run / 'requests' / (f'{attempt}/auditor-v1.1' if attempt else 'auditor-v1.1') / (tid + '.txt')
    freeze(dest, audit_packet(run, tid, author))
    return dest


def audit_packet(run, tid, author=None):
    author = author or active(run, tid, 'author')
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


def check(run, role, tid, attempt=None, exact=False):
    """Validate an answer: a named attempt, the exact raw/ file (exact=True) or the active one."""
    pick = (lambda r: paths(run, r, tid, attempt)[0]) if (attempt or exact) else (lambda r: active(run, tid, r))
    raw = pick(role)
    if role == 'author':
        d = read(raw); validate_one(d); assert d['task_id'] == tid
        return {'task_id': tid, 'status': 'technical_pass', 'solution_status': d['solution_status']}
    fx.RUN = run  # historical validator reads inputs and catalog from RUN
    return fx.validate_audit(tid, raw, author_path=rel(pick('author')))


def exec_start(a):
    run = run_dir(a.run)
    res = read(run / 'reservation.json')
    assert res['status'] == 'reserved' and res.get('confirmation_url'), 'No coordinator `reserved` recorded: generation not authorized'
    assert a.task in res['task_ids'], 'task outside the reservation'
    if a.attempt:
        meta = attempt_meta(run, a.attempt)
        assert a.task in meta['task_ids'], 'task outside the declared attempt'
        model = meta['model_identifier']
    else:
        model = a.model or read(run / 'environment.json')['model_identifier']
    raw, rec, _ = paths(run, a.role, a.task, a.attempt)
    assert not rec.exists() and not raw.exists(), 'already started; a re-run needs a new attempt name'
    if a.role == 'author':
        req = run / 'requests/author' / (a.task + '.txt')
    else:
        author_raw, _, author_val = paths(run, 'author', a.task, a.attempt)
        assert author_val.exists() and read(author_val)['result']['status'] == 'technical_pass', 'author answer not validated'
        req = audit_request(run, a.task, author_raw if a.attempt else active(run, a.task, 'author'), a.attempt)
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
                'raw_path': rel(raw), 'fork': 'none', 'model': model, 'attempt': a.attempt,
                'mechanism': 'Claude Code Agent tool; fresh subagent context'})
    print(msg)


def attach(a):
    """Record which launched agent took this execution (right after launching it)."""
    run = run_dir(a.run)
    rec = paths(run, a.role, a.task, a.attempt)[1]
    d = read(rec)
    assert d['agent_id'] in (None, a.agent_id), f'already attached to {d["agent_id"]}'
    d.update(agent_id=a.agent_id, subagent_type=a.subagent_type, model_requested=a.model_requested)
    write(rec, d)
    print('attached', a.role, a.task)


def exec_finish(a):
    run = run_dir(a.run)
    raw, rec, val = paths(run, a.role, a.task, a.attempt)
    d = read(rec)
    d.update(end_utc=now(), agent_id=a.agent_id or d['agent_id'], raw_sha256=fsha(raw) if raw.exists() else None,
             completion_message=a.message or '')
    write(rec, d)
    try:
        result, code = check(run, a.role, a.task, a.attempt, exact=True), 0
    except Exception as e:  # validation failure is data, not a crash
        result, code = {'task_id': a.task, 'status': 'technical_fail', 'error': repr(e)}, 1
    write(val, {'result': result, 'attempt': a.attempt, 'at_utc': now()})
    print(json.dumps(result, ensure_ascii=False))
    sys.exit(code)


def validate(a):
    print(json.dumps(check(run_dir(a.run), a.role, a.task, a.attempt), ensure_ascii=False))


def status(a):
    run = run_dir(a.run)
    m = read(run / 'manifest.json')
    res = read(run / 'reservation.json')
    batches = m['batches'].items()
    if a.attempt:
        meta = attempt_meta(run, a.attempt)
        batches = [(str(meta['batch']), meta['task_ids'])]
    rows = []
    for b, ids in batches:
        authors = sum(paths(run, 'author', t, a.attempt)[0].exists() for t in ids)
        auditors = sum(paths(run, 'auditor', t, a.attempt)[0].exists() for t in ids)
        health = (run / 'checks' / f'batch-{int(b):02}{sfx(a.attempt)}.json').exists()
        rows.append({'batch': int(b), 'tasks': len(ids), 'authors': authors, 'auditors': auditors, 'health_check': health})
    attempts = sorted(p.parent.name for p in (run / 'attempts').glob('*/attempt.json'))
    print(json.dumps({'reservation': res['status'], 'issue': res['issue_url'], 'attempt': a.attempt or 'raw',
                      'declared_attempts': attempts, 'active_overrides': len(read(run / 'active-attempts.json')),
                      'batches': rows}, ensure_ascii=False, indent=1))


CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'


def batch_ids(run, b):
    return read(run / 'manifest.json')['batches'][str(b)]


def norm_answer(s):
    s = str(s).lower().replace('−', '-').replace('∞', 'inf').replace('∪', 'u').replace('union', 'u')
    s = s.replace(';', ',').replace(' ', '').replace(' ', '')
    s = s.replace('+inf', 'inf')            # "[4; +∞)" == "[4,inf)"
    s = re.sub(r'^[a-z](∈|=)', '', s)       # "x ∈ (...)", "x = 5"
    s = re.sub(r'[а-яё./]+$', '', s)        # trailing units: "км/ч", "рублей"
    try:
        return repr(float(s.replace(',', '.')))
    except ValueError:
        return s


def health_render(a):
    """Same cards and browser assertions as health_fipi_extension.render; macOS Chrome path."""
    import tempfile
    from lxml import html as lhtml
    from PIL import Image
    import health_fipi_extension as hx
    run = run_dir(a.run); b = a.batch; s = sfx(a.attempt)
    hx.RUN = run
    if a.attempt:  # cards must show this attempt's answers, not the active ones
        hx.active = lambda tid, role: paths(run, role, tid, a.attempt)[0]
    ids = batch_ids(run, b)
    plan = read(run / 'checks' / f'batch-{b:02}-sample-plan.json')
    assert set(plan['task_ids']) <= set(ids)
    results = []
    for label, group in [('all', ids)] + [(t, [t]) for t in plan['task_ids']]:
        page = run / 'checks' / f'batch-{b:02}{s}-{label}.html'
        page.write_text(hx.document(''.join(hx.card(t) for t in group)), encoding='utf-8')
        png = page.with_suffix('.png')
        with tempfile.TemporaryDirectory() as profile:
            common = [CHROME, '--headless', '--disable-gpu', '--no-first-run', '--no-default-browser-check',
                      '--user-data-dir=' + profile, '--window-size=1600,2200', '--virtual-time-budget=1000']
            dom = subprocess.run(common + ['--dump-dom', page.as_uri()], capture_output=True, timeout=120)
            shot = subprocess.run(common + ['--screenshot=' + str(png), page.as_uri()], capture_output=True, timeout=120)
        assert dom.returncode == 0 and shot.returncode == 0 and png.exists(), (dom.stderr + shot.stderr).decode(errors='replace')[-400:]
        h = json.loads(lhtml.fromstring(dom.stdout.decode('utf-8')).xpath('//body/@data-health')[0])
        inputs = [read(run / 'inputs/tasks' / (t + '.json')) for t in group]
        assert h['math'] == sum(r['mathml_count'] for r in inputs) and h['mfenced'] == 0 and h['math_ok'], h
        assert len(h['images']) == sum(len(r['assets']) for r in inputs) and all(h['images']), h
        assert h['width'] <= 1600, h
        with Image.open(png) as im:
            im.verify()
        results.append({'label': label, 'task_ids': group, 'browser': h,
                        'screenshot': {'path': rel(png), 'sha256': fsha(png)}, 'html': {'path': rel(page), 'sha256': fsha(page)}})
    out = run / 'checks' / f'batch-{b:02}{s}-render.json'
    freeze(out, {'batch': b, 'attempt': a.attempt, 'status': 'technical_pass', 'browser': 'Google Chrome headless (macOS)',
                 'cards': results})
    print(rel(out))


def health_math(a):
    """Compare predeclared expectations (written before any author answer) with active author answers."""
    run = run_dir(a.run); b = a.batch
    plan = read(run / 'checks' / f'batch-{b:02}-sample-plan.json')
    expected = {}
    for kind in ['math-expected', 'math-supplement']:
        p = run / 'checks' / f'batch-{b:02}-{kind}.json'
        if p.exists():
            for c in read(p)['checks']:
                if c.get('status') == 'independent_expected_before_author' or c['task_id'] not in expected:
                    expected[c['task_id']] = {**c, 'source': 'checks/' + p.name}
    # Optional post-hoc review of string mismatches (e.g. multi-part answers the normalizer cannot compare).
    # Written after seeing the author answer, so it is recorded as such and never as a blind check.
    rp = run / 'checks' / f'batch-{b:02}{sfx(a.attempt)}-math-review.json'
    reviews = {r['task_id']: r for r in read(rp)['reviews']} if rp.exists() else {}
    checks = []
    for t in plan['task_ids']:
        e = expected.get(t, {'status': 'not_checked', 'source': None})
        ans = read(answer(run, t, 'author', a.attempt))['answer']
        review = None
        if e.get('status') == 'independent_expected_before_author':
            status = 'match' if norm_answer(e['expected_answer']) == norm_answer(ans) else 'mismatch'
            r = reviews.get(t)
            if status == 'mismatch' and r and r.get('verdict') == 'equivalent' and r.get('author_answer') == ans:
                status, review = 'match_after_review', {**r, 'source': 'checks/' + rp.name}
        else:
            status = 'not_checked'
        checks.append({'task_id': t, 'status': status, 'expected_answer': e.get('expected_answer'), 'author_answer': ans,
                       'calculation': e.get('calculation'), 'expectation_source': e['source'],
                       'prepared_before_new_author_answers': e.get('prepared_before_new_author_answers', False),
                       'scope': 'Predeclared primary-assistant spot expectation from the 2026-11-02 run; not full expert proof',
                       **({'post_hoc_review': review} if review else {})})
    out = run / 'checks' / f'batch-{b:02}{sfx(a.attempt)}-math.json'
    freeze(out, {'batch': b, 'attempt': a.attempt, 'checks': checks,
                 'systemic_unresolved': any(c['status'] == 'mismatch' for c in checks), 'recorded_at': now()})
    print(json.dumps(checks, ensure_ascii=False, indent=1))


def health_visual(a):
    """Record an actual look at the rendered screenshots; reviewer and findings are given explicitly."""
    run = run_dir(a.run); b = a.batch
    plan = read(run / 'checks' / f'batch-{b:02}-sample-plan.json')
    rendered = read(run / 'checks' / f'batch-{b:02}{sfx(a.attempt)}-render.json')
    findings = json.loads(a.findings) if a.findings else []
    out = run / 'checks' / f'batch-{b:02}{sfx(a.attempt)}-visual.json'
    freeze(out, {'batch': b, 'attempt': a.attempt, 'reviewed_ids': plan['task_ids'], 'reviewer': a.reviewer,
                 'scope': 'Source conditions, images and MathML in Chrome screenshots of the sample cards; not full solution expertise',
                 'findings': findings, 'systemic_unresolved': False, 'recorded_at': now(),
                 'screenshots': [c['screenshot'] for c in rendered['cards'] if c['label'] != 'all']})
    print(rel(out))


def health_finish(a):
    run = run_dir(a.run); b = a.batch; ids = batch_ids(run, b); att = a.attempt; s = sfx(att)
    if att:
        assert attempt_meta(run, att)['batch'] == b, 'attempt belongs to another batch'
    technical, flags = [], []
    for t in ids:
        d = read(answer(run, t, 'author', att)); validate_one(d); assert d['task_id'] == t
        technical.append(check(run, 'auditor', t, att))
        q = read(answer(run, t, 'auditor', att))
        if d['solution_status'] != 'solved' or q['issues']:
            flags.append({'task_id': t, 'solution_status': d['solution_status'], 'issues': q['issues']})
    rendered = read(run / 'checks' / f'batch-{b:02}{s}-render.json')
    visual = read(run / 'checks' / f'batch-{b:02}{s}-visual.json')
    math = read(run / 'checks' / f'batch-{b:02}{s}-math.json')
    plan = read(run / 'checks' / f'batch-{b:02}-sample-plan.json')
    assert set(visual['reviewed_ids']) >= set(plan['task_ids'])
    assert {x['task_id'] for x in math['checks']} >= set(plan['task_ids'])
    assert not visual.get('systemic_unresolved') and not math.get('systemic_unresolved')
    quarantine = [t for t in ids if read(answer(run, t, 'author', att))['solution_status'] != 'solved'
                  or any(i['blocking'] for i in read(answer(run, t, 'auditor', att))['issues'])]
    executions = []
    for t in ids:
        for role in ['author', 'auditor']:
            _, e, v = paths(run, role, t, att)
            assert read(v)['result']['status'] == 'technical_pass', (role, t)
            executions.append({'path': rel(e), 'sha256': fsha(e), 'execution': read(e)})
    if att:
        answers = {t: {r: paths(run, r, t, att)[0].relative_to(run).as_posix() for r in ['author', 'auditor']} for t in ids}
    else:
        current = read(run / 'active-attempts.json')
        answers = {t: current[t] for t in ids if t in current}
    freeze(run / f'batch-execution-{b:02}{s}.json', {'batch': b, 'attempt': att, 'completed_at': now(), 'tasks': ids,
           'executions': executions, 'active_attempts': answers,
           'technical_validation': 'passed', 'mathematical_correctness': 'not established by coordinator'})
    freeze(run / 'checks' / f'batch-{b:02}{s}.json', {'batch': b, 'attempt': att, 'status': 'quarantine' if quarantine else 'pass',
           'task_ids': ids, 'systemic_unresolved': False, 'technical': technical, 'render': rendered, 'visual_review': visual,
           'math_spot_checks': math, 'audit_flags': flags, 'quarantined_ids': quarantine})
    print('Batch health complete:', b, 'attempt:', att or 'raw', 'quarantine:', quarantine)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('command', choices=['prepare', 'reserve', 'verify', 'audit-request', 'attempt-init', 'exec-start', 'attach',
                                       'exec-finish', 'validate', 'status', 'health-render', 'health-math', 'health-visual',
                                       'health-finish', 'activate'])
    p.add_argument('--attempt'); p.add_argument('--reason')
    p.add_argument('--subagent-type', default='general-purpose'); p.add_argument('--model-requested', default='opus')
    p.add_argument('--batch', type=int); p.add_argument('--reviewer'); p.add_argument('--findings')
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
        {'prepare': prepare, 'reserve': reserve, 'verify': verify, 'exec-start': exec_start, 'attach': attach,
         'exec-finish': exec_finish, 'validate': validate, 'status': status,
         'health-render': health_render, 'health-math': health_math, 'health-visual': health_visual,
         'health-finish': health_finish, 'attempt-init': attempt_init, 'activate': activate}[a.command](a)


if __name__ == '__main__':
    main()
