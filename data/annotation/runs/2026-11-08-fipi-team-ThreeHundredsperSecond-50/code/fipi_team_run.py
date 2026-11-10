"""Isolated team run tooling; no model calls and no historical mutations."""
import argparse
import json
import platform
import subprocess
import os
from collections import Counter
from pathlib import Path

import fipi_extension as old
from fipi_eda50 import validate_one

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / 'data/annotation/runs/2026-11-08-fipi-team-ThreeHundredsperSecond-50'
HIST = ROOT / 'data/annotation/runs/2026-11-02-fipi-extension-150'
BANK = ROOT / 'data/fipi/2026-10-31-profile'
SELECTION = ROOT / 'data/annotation/team/selections/2026-11-08-ThreeHundredsperSecond-50-v1.json'
read, freeze, sha, hashed, now = old.read, old.freeze, old.sha, old.hashed, old.now


def prepare():
    if (RUN / 'manifest.json').exists():
        verify_frozen()
        print('Already prepared; frozen inputs verified.')
        return
    registry = read(ROOT / 'data/annotation/team/registry.json')
    selection = read(SELECTION)
    assert len(selection['tasks']) == len({t['task_id'] for t in selection['tasks']}) == 50
    methodology = []
    for path, digest in registry['methodology_sha256'].items():
        src = ROOT / path
        assert sha(src.read_bytes()) == digest, path
        freeze(RUN / src.name, src.read_bytes())
        methodology.append(hashed(src))
    freeze(RUN / 'catalog-v1.json', (HIST / 'catalog-v1.json').read_bytes())
    freeze(RUN / 'selection.json', SELECTION.read_bytes())
    for folder in ['raw/author', 'raw/auditor', 'executions', 'validations', 'checks', 'attempts', 'requests/auditor']:
        (RUN / folder).mkdir(parents=True, exist_ok=True)
    for t in selection['tasks']:
        tid = t['task_id']
        src = ROOT / t['source_path']
        inp = read(src)
        assert inp['id'] == tid
        freeze(RUN / 'inputs/tasks' / (tid + '.json'), src.read_bytes())
        for a in inp['assets']:
            freeze(RUN / 'inputs' / a['path'], (BANK / a['path']).read_bytes())
        body = {'task_id': tid, **old.condition(inp), 'image_files': [str((RUN / 'inputs' / a['path']).resolve()) for a in inp['assets']]}
        packet = (RUN / 'author-prompt.txt').read_text(encoding='utf-8') + '\n' + (RUN / 'author-wrapper.txt').read_text(encoding='utf-8') + '\nВХОД:\n' + json.dumps(body, ensure_ascii=False, indent=2)
        freeze(RUN / 'requests/author' / (tid + '.txt'), packet)
    # Protocol sample; input-only selection, without reading any responses.
    controls = []
    for batch in range(1, 5):
        tasks = [t for t in selection['tasks'] if t['batch'] == batch]
        chosen = [tasks[0]['task_id']]
        for field in ['assets', 'mathml_count']:
            match = next((t['task_id'] for t in tasks if read(RUN/'inputs/tasks'/(t['task_id']+'.json'))[field]), None)
            if match and match not in chosen: chosen.append(match)
        for t in tasks:
            if len(chosen) >= 3: break
            if t['task_id'] not in chosen: chosen.append(t['task_id'])
        controls.append({'batch': batch, 'task_ids': chosen, 'selection': 'first task, first image, first MathML; deduplicate and fill next in selection order', 'mathematical_expectations': 'pending independent checker before inspecting responses'})
    freeze(RUN / 'checks/predeclared-controls-v2.json', {'created_at_utc': now(), 'supersedes': 'predeclared-controls.json: sampling rule corrected to protocol; no responses inspected by tooling engineer', 'batches': controls})
    freeze(RUN / 'active-attempts.json', {})
    freeze(RUN / 'environment.json', {'prepared_at_utc': now(), 'git_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT).decode().strip(), 'branch': subprocess.check_output(['git', 'branch', '--show-current'], cwd=ROOT).decode().strip(), 'python': platform.python_version(), 'platform': platform.platform(), 'requested_model': 'gpt-6.1-sol', 'actual_model': 'unknown; record reported metadata per execution', 'isolation': 'fresh author and separate fresh auditor per task; fork_turns=none', 'prepare_command': 'python scripts/fipi_team_run.py prepare'})
    baseline = [hashed(p) for base in [BANK, HIST, ROOT/'data/annotation/runs/2026-10-31-fipi-50x1'] for p in sorted(base.rglob('*')) if p.is_file()]
    freeze(RUN / 'baseline-manifest.json', {'created_at_utc': now(), 'files': baseline})
    freeze(RUN / 'README.md', '# Командная партия ThreeHundredsperSecond: 50 задач\n\nМетодика `fipi-extension-v1.1`; отдельный слой происхождения, модель requested `gpt-6.1-sol`. Партии: 15 + 15 + 15 + 5. Источник — сохранённый банк ФИПИ; каталог и буквальные инструкции скопированы побитово.\n\nВходы: `inputs/`, запросы: `requests/`, исходные ответы: `raw/`, исполнения: `executions/`, проверки: `validations/` и `checks/`. Наличие запроса не означает исполнение. Анализ по сохранённым результатам — `derived/eda-v1/`.\n')
    roots = [RUN/'inputs', RUN/'requests/author']
    explicit = [RUN/Path(p).name for p in registry['methodology_sha256']] + [RUN/'catalog-v1.json', RUN/'selection.json', RUN/'environment.json', RUN/'checks/predeclared-controls-v2.json']
    frozen = [hashed(p) for p in sorted(set(explicit + [p for folder in roots for p in folder.rglob('*') if p.is_file()]))]
    freeze(RUN / 'freeze-manifest.json', {'created_at_utc': now(), 'files': frozen})
    freeze(RUN / 'manifest.json', {'schema_version': 1, 'created_at_utc': now(), 'issue_url': 'https://github.com/ThreeHundredsperSecond/proactive-ai-tutor-65/issues/3', 'method_version': 'fipi-extension-v1.1', 'tasks': selection['tasks'], 'methodology': methodology, 'code': hashed(Path(__file__)), 'selection': hashed(SELECTION)})
    print(json.dumps({'prepared': 50, 'author_requests': 50, 'controls': controls}, ensure_ascii=False))


def verify_frozen():
    for name in ['baseline-manifest.json', 'freeze-manifest-v2.json' if (RUN/'freeze-manifest-v2.json').exists() else 'freeze-manifest.json']:
        for item in read(RUN / name)['files']:
            assert sha((ROOT / item['path']).read_bytes()) == item['sha256'], item['path']


def correct_freeze_scope():
    """Preserve the original preparation record, supersede its overly broad scope."""
    controls = []
    for batch in range(1, 5):
        tasks = [t for t in read(RUN/'selection.json')['tasks'] if t['batch'] == batch]
        chosen = [tasks[0]['task_id']]
        for field in ['assets', 'mathml_count']:
            match = next((t['task_id'] for t in tasks if read(RUN/'inputs/tasks'/(t['task_id']+'.json'))[field]), None)
            if match and match not in chosen: chosen.append(match)
        for t in tasks:
            if len(chosen) >= 3: break
            if t['task_id'] not in chosen: chosen.append(t['task_id'])
        controls.append({'batch': batch, 'task_ids': chosen, 'rule': 'first task, first image, first MathML; deduplicate and fill next in selection order'})
    freeze(RUN/'checks/predeclared-controls-v2.json', {'created_at_utc': now(), 'supersedes': 'predeclared-controls.json', 'reason': 'Correct sampling rule to frozen protocol. Input-only correction; engineer has not inspected responses. Batch 1 mathematical expectations were separately predeclared by root before authors.', 'batches': controls})
    names = [Path(p).name for p in read(ROOT/'data/annotation/team/registry.json')['methodology_sha256']] + ['catalog-v1.json', 'selection.json', 'environment.json', 'checks/predeclared-controls-v2.json']
    files = [RUN/n for n in names] + [p for folder in ['inputs', 'requests/author'] for p in (RUN/folder).rglob('*') if p.is_file()]
    freeze(RUN/'freeze-manifest-v2.json', {'created_at_utc': now(), 'supersedes': 'freeze-manifest.json', 'reason': 'Scope only immutable methodology/input/author requests; exclude raw outputs, execution logs, README and mutable code.', 'files': [hashed(p) for p in sorted(set(files))]})


def audit_request(tid):
    assert tid in {t['task_id'] for t in read(RUN/'selection.json')['tasks']}
    d = read(RUN/'raw/author'/(tid+'.json'))
    validate_one(d)
    assert d['task_id'] == tid
    inp = read(RUN/'inputs/tasks'/(tid+'.json'))
    refs = ['condition'] + [f"step:{s['id']}:{field}" for s in d['steps'] for field in ['action', 'result']] + ['image:'+a['path'] for a in inp['assets']]
    body = {'task_id': tid, **old.condition(inp), 'author_response': d, 'image_files': [str((RUN/'inputs'/a['path']).resolve()) for a in inp['assets']], 'catalog': read(RUN/'catalog-for-auditor.json'), 'allowed_refs': refs}
    packet = (RUN/'auditor-prompt.txt').read_text(encoding='utf-8')+'\n'+(RUN/'audit-format-wrapper-v1.1.txt').read_text(encoding='utf-8')+'\nВХОД:\n'+json.dumps(body, ensure_ascii=False, indent=2)
    freeze(RUN/'requests/auditor'/(tid+'.txt'), packet)
    print(str(RUN/'requests/auditor'/(tid+'.txt')))


def validate(tid):
    d = read(RUN/'raw/author'/(tid+'.json'))
    validate_one(d)
    assert d['task_id'] == tid
    old.RUN = RUN  # In-process dependency adaptation only; historical sources unchanged.
    result = old.validate_audit(tid, RUN/'raw/auditor'/(tid+'.json'))
    freeze(RUN/'validations'/(tid+'.json'), result)
    print(json.dumps(result, ensure_ascii=False))
    return result


def health(batch):
    """Technical saved-data gate; root supplies actual visual and math reviews."""
    from PIL import Image
    results, errors, quarantined = [], [], []
    for task in [t for t in read(RUN/'selection.json')['tasks'] if t['batch'] == batch]:
        tid = task['task_id']
        try:
            inp = read(RUN/'inputs/tasks'/(tid+'.json'))
            for a in inp['assets']:
                p = RUN/'inputs'/a['path']
                assert sha(p.read_bytes()) == a['sha256']
                with Image.open(p) as image: image.verify()
            results.append(validate(tid))
            audit = read(RUN/'raw/auditor'/(tid+'.json'))
            author = read(RUN/'raw/author'/(tid+'.json'))
            if author['solution_status'] != 'solved' or any(i['blocking'] for i in audit['issues']) or any(d['blocking'] for d in audit['decisions']): quarantined.append(tid)
        except (AssertionError, OSError, ValueError, KeyError, TypeError) as exc:
            errors.append({'task_id': tid, 'error': repr(exc)})
    controls = next(b for b in read(RUN/'checks/predeclared-controls-v2.json')['batches'] if b['batch'] == batch)
    result = {'batch': batch, 'technical_pairs': len(results), 'technical_errors': errors, 'quarantined_ids': quarantined, 'controls': controls, 'visual_and_independent_math': 'not assessed by this command; inspect root saved review evidence', 'continue_gate': 'requires root visual/math review and disposition of flags', 'created_at_utc': now()}
    # Immutable dated snapshot, never overwrite earlier checks.
    dest = RUN/'checks'/f'batch-{batch:02}-technical-{sha(json.dumps(result,sort_keys=True).encode())[:12]}.json'
    freeze(dest, result)
    evidence = {kind: RUN/'checks'/f'batch-{batch:02}-{kind}.json' for kind in ['visual','math','render']}
    if not errors and all(p.exists() for p in evidence.values()):
        visual, math, rendered = [read(evidence[k]) for k in ['visual','math','render']]
        expected = set(controls['task_ids'])
        assert set(visual['reviewed_ids']) >= expected
        assert {x['task_id'] for x in math['checks']} >= expected
        assert not visual.get('systemic_unresolved', True) and not math.get('systemic_unresolved', True)
        assert all(x.get('status') == 'pass' for x in math['checks']), 'Independent math review unresolved'
        assert visual.get('status') == 'pass' and rendered.get('status') == 'technical_pass'
        freeze(RUN/'checks'/f'batch-{batch:02}.json', {'batch':batch,'status':'quarantine' if quarantined else 'pass','task_ids':[t['task_id'] for t in read(RUN/'selection.json')['tasks'] if t['batch']==batch],'systemic_unresolved':False,'technical':results,'render':rendered,'visual_review':visual,'math_spot_checks':math,'audit_flags':[{'task_id':tid,'quarantined':True} for tid in quarantined],'quarantined_ids':quarantined})
    print(json.dumps(result, ensure_ascii=False))
    return result


def analysis_data():
    import report_fipi_extension as report
    old.RUN = RUN
    old.verify_frozen = verify_frozen
    report.RUN = RUN
    report.ext.RUN = RUN
    data = report.collect(50, strict=False)
    for row in data['new']:
        inp = row['input']
        row.update(primary_kes=old.meta(inp, 'КЭС:')[0].split()[0], response_type=old.meta(inp, 'Тип ответа:')[0], images=len(inp['assets']), mathml=inp['mathml_count'])
    summary, tables = report.metrics(data)
    return report, data, summary, tables


def report_run():
    """New-layer EDA plus descriptive historical reference; no semantic inference."""
    import csv
    import nbformat
    from nbclient import NotebookClient
    report, data, populations, tables = analysis_data()
    target = RUN/'derived/eda-v1'
    assert not target.exists(), 'Immutable EDA exists; use a new version for changed inputs.'
    out = RUN/'derived/eda-v1.building'
    assert not out.exists(), 'Inspect incomplete build before retry.'
    out.mkdir(parents=True)
    (out/'tables').mkdir(); (out/'figures').mkdir()
    historical = read(HIST/'derived/checkpoint-100-v1/summary.json')
    summary = {'scope': '50 new tasks, separate model/procedure layer', 'new': populations['new_accumulated'], 'historical100_reference': historical, 'historical50_plus_new50_descriptive_only': populations['mixed_cumulative'], 'technical_errors': data['technical_errors'], 'denominator_policy': 'solved complete technically valid pairs without blocking audit issues; no accuracy claim'}
    freeze(out/'summary.json', summary)
    fields = dict(frequencies=['population','catalog_kc_id','task_n','denominator'], cooccurrence=['population','kc_a','kc_b','task_n','denominator'], transitions=['population','from_kc','to_kc','task_n','denominator'], tasks=['population','task_id','layer','status','author_mode','complete','included','response_type','steps','local_kcs','methods','matched_catalog_nodes','unmatched_local_candidates','exclusion_reasons'], composition=['population','dimension','value','task_n','denominator'], audit_statuses=['population','status','numerator','denominator'], candidates=['task_id','local_kc_id','name','status','catalog_kc_id','blocking','task_included','rationale'])
    for name, rows in tables.items(): report.csvout(out/'tables', name+'.csv', rows, fields[name])
    report.cards(out, data)
    report.figures(out/'figures', populations, tables)
    new = populations['new_accumulated']
    lines = ['# Отчёт новой партии: 50 задач', '', f"Полных пар: {new['complete_n']}/50; в основных частотах: {new['included_n']}/50.", '', 'Добавляется отдельный слой происхождения с requested моделью gpt-6.1-sol и свежими контекстами автора/аудитора. Фактические модели и настройки подтверждаются только журналами исполнений.', '', 'Историческая точка 100 сохранена в summary.json отдельно. Этот отчёт не является накопленным EDA-150: приёмка партий и явный список активных попыток нужны для накопленного анализа.', '', f"Подтверждённых узлов каталога в новой серии: {new['confirmed_catalog_nodes']}. Неполное сопоставление: {new['incomplete_mapping_tasks']}/{new['included_n']} задач основных частот.", '', 'Различия относительно EDA-100 могут объясняться составом выборки, моделью и процедурой. Ни математическая точность, ни причинный эффект модели, ни новые уникальные навыки этими числами не установлены.', '', 'Ошибки технической проверки и исключения перечислены в summary.json и tables/tasks.csv. Семантические вердикты и блокировки сохраняются буквально; контроль изображений и независимые расчёты учитываются по отдельным checks.', '', 'Совстречаемость считается по присутствию в задаче, переходы — между соседними шагами одного метода. Переходы не являются prerequisites.', '', '[Карточки, графики и таблицы](index.html).']
    freeze(out/'report.md', '\n'.join(lines)+'\n')
    links = ''.join(f'<li><a href="cards/{t["task_id"]}.html">{t["task_id"]}</a></li>' for t in read(RUN/'selection.json')['tasks'])
    historical_link = os.path.relpath(HIST/'derived/checkpoint-100-v1/index.html', out).replace('\\','/')
    freeze(out/'index.html', report.page('Новая партия ФИПИ: 50', '<h1>Новая партия: 50 задач</h1><a href="report.md">Отчёт</a> · <a href="summary.json">Числа и знаменатели</a> · <a href="'+historical_link+'">Исторические карточки 100</a><ul>'+links+'</ul>'+''.join('<img style="max-width:100%" src="figures/'+p.name+'">' for p in sorted((out/'figures').glob('*.png')))))
    code = """import sys,json,hashlib
from pathlib import Path
root=next(p for p in [Path.cwd(),*Path.cwd().parents] if (p/'scripts/fipi_team_run.py').exists())
sys.path.insert(0,str(root/'scripts'))
import fipi_team_run as team
module,data,populations,tables=team.analysis_data()
populations['new_accumulated']
"""
    nb = nbformat.v4.new_notebook(cells=[nbformat.v4.new_markdown_cell('Пересчёт по сохранённым входам; новые модельные запросы не выполняются.'), nbformat.v4.new_code_cell(code)], metadata={'kernelspec': {'display_name':'Python 3','language':'python','name':'python3'}})
    previous = os.environ.get('PATH','')
    os.environ['PATH'] = str(ROOT/'.venv/Scripts')+os.pathsep+previous
    try: NotebookClient(nb,timeout=600,startup_timeout=60,resources={'metadata':{'path':str(ROOT)}}).execute()
    finally: os.environ['PATH'] = previous
    nbformat.write(nb, out/'review.ipynb')
    freeze(out/'provenance.json', {'input_digest':data['input_digest'], 'input_hashes':data['input_hashes'], 'code':hashed(Path(__file__)), 'method_version':'fipi-extension-v1.1', 'notebook_executed':True, 'created_at_utc':now(), 'historical_reference':hashed(HIST/'derived/checkpoint-100-v1/summary.json')})
    assert all(sha((ROOT/p).read_bytes()) == digest for p,digest in data['input_hashes'].items()), 'Inputs changed while reporting; inspect building snapshot.'
    out.rename(target)
    print(str(target))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['prepare', 'audit-request', 'validate', 'health', 'report', 'verify-frozen'])
    parser.add_argument('--task')
    parser.add_argument('--batch', type=int)
    args = parser.parse_args()
    if args.command == 'prepare': prepare()
    elif args.command == 'audit-request': audit_request(args.task)
    elif args.command == 'validate': validate(args.task)
    elif args.command == 'verify-frozen': verify_frozen()
    elif args.command == 'health': health(args.batch)
    elif args.command == 'report': report_run()


if __name__ == '__main__':
    main()
