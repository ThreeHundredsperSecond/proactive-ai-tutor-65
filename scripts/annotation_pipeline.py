"""Offline preparation and analysis of saved agent runs. Never calls a model."""
import argparse
import csv
import hashlib
import itertools
import json
import platform
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / 'data/processed/sdamgia/90702516/tasks.jsonl'
PROMPT = ROOT / 'docs/eda/04-annotation/02.1-prompting-pilot/prompts/A.txt'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_bytes((json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))


def text(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_bytes(value.encode('utf-8'))


def prepare(run, repeats=3, positions=None):
    """Freeze statement-only inputs. Refuse overwriting an existing experiment."""
    run = Path(run).resolve()
    run.mkdir(parents=True, exist_ok=False)
    rows = [json.loads(s) for s in CORPUS.read_text(encoding='utf-8').splitlines() if s.strip()]
    if positions is not None:
        rows = [r for r in rows if r['position'] in positions]
    if not rows or repeats < 1:
        raise ValueError('Empty selection or nonpositive repeats')
    prompt = PROMPT.read_text(encoding='utf-8')
    text(run / 'prompt-A.txt', prompt)
    for folder in ('raw', 'reviews', 'derived', 'jobs', 'images'):
        (run / folder).mkdir()
    tasks, jobs = [], []
    for row in rows:
        tid = row['site_task_id']
        images = []
        for index, asset in enumerate(row['statement']['images'], 1):
            original = ROOT / asset['path']
            local = f'images/{tid}-{index}{original.suffix}'
            (run / local).write_bytes(original.read_bytes())
            images.append({'role': asset['role'], 'original_path': asset['path'],
                           'svg_path': local, 'original_sha256': sha(original),
                           'path': f'images/{tid}-{index}.png'})
        payload = {'task_id': tid, 'statement': row['statement']['text_accessibility'],
                   'images': [{'role': i['role'], 'path': i['path']} for i in images]}
        write(run / 'inputs' / f'{tid}.json', payload)
        request = prompt.replace('{task_json}', json.dumps(payload, ensure_ascii=False, indent=2))
        text(run / 'requests' / f'{tid}.txt', request)
        tasks.append({'task_id': tid, 'position': row['position'], 'images': images,
                      'input_sha256': sha(run / 'inputs' / f'{tid}.json'),
                      'request_sha256': sha(run / 'requests' / f'{tid}.txt')})
        for repeat in range(1, repeats + 1):
            job = f'{tid}_r{repeat}'
            instruction = (
                'Изолированный разбор. Не читай документы проекта, корпус, решения или чужие ответы. '
                f'Загрузи UTF-8 запрос {run.as_posix()}/requests/{tid}.txt через exec_command. '
                + ''.join(f'Просмотри {run.as_posix()}/{i["path"]} через view_image. ' for i in images)
                + 'После загрузки выполни неизменённый промпт A. Решай самостоятельно, без инструментов. '
                'Когда итоговый JSON полностью сформирован, разрешено только сохранить его как UTF-8 '
                f'в {run.as_posix()}/raw/{job}.txt. Не исправляй его другими средствами и не перезаписывай существующий файл. '
                'В итоговом сообщении основному агенту сообщи только путь сохранённого файла. '
                'Загрузка и запись — техническая обвязка; инструменты для математического решения запрещены.'
            )
            text(run / 'jobs' / f'{job}.txt', instruction)
            jobs.append({'job_id': job, 'task_id': tid, 'repeat': repeat,
                         'raw_path': f'raw/{job}.txt', 'instruction_sha256': sha(run / 'jobs' / f'{job}.txt')})
    commit = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    write(run / 'manifest.json', {'schema_version': 1, 'run_id': run.name,
          'created_at_utc': datetime.now(timezone.utc).isoformat(), 'git_commit': commit,
          'corpus_path': str(CORPUS.relative_to(ROOT)), 'corpus_sha256': sha(CORPUS),
          'prompt_source': str(PROMPT.relative_to(ROOT)), 'prompt_sha256': sha(run / 'prompt-A.txt'),
          'repeats': repeats, 'runtime': 'Codex isolated agents, fork_turns=none; no model override',
          'model_parameters': None, 'tasks': tasks, 'jobs': jobs})
    freeze = subprocess.run([sys.executable, '-m', 'pip', 'freeze'], capture_output=True, text=True, check=True).stdout
    text(run / 'environment.txt', f'Python {platform.python_version()}\n{platform.platform()}\n' + freeze)
    return run


def validate(d, task_id):
    """Return errors instead of silently repairing or dropping failed responses."""
    errors = []
    if not isinstance(d, dict):
        return ['root is not an object']
    if set(d) != {'task_id', 'solution_status', 'steps', 'kc_candidates', 'methods', 'warnings'}:
        errors.append('root keys')
    if d.get('task_id') != task_id:
        errors.append('task_id')
    if d.get('solution_status') not in ('solved', 'partial', 'unsolved'):
        errors.append('solution_status')
    if not isinstance(d.get('warnings'), list) or not all(isinstance(w, str) for w in d.get('warnings', [])):
        errors.append('warnings')
    schemas = {'steps': {'id': str, 'action': str, 'result': str, 'kc_ids': list},
               'kc_candidates': {'id': str, 'name': str, 'description': str},
               'methods': {'id': str, 'name': str, 'step_ids': list}}
    for field, schema in schemas.items():
        if not isinstance(d.get(field), list):
            errors.append(field + ' list'); continue
        ids = []
        for item in d[field]:
            if not isinstance(item, dict) or set(item) != set(schema):
                errors.append(field + ' keys'); continue
            for key, kind in schema.items():
                value = item[key]
                if not isinstance(value, kind): errors.append(field + '.' + key + ' type')
                elif kind is str and not value.strip(): errors.append(field + '.' + key + ' empty')
                elif kind is list and (not value or not all(isinstance(x, str) and x.strip() for x in value)):
                    errors.append(field + '.' + key + ' items')
            if isinstance(item.get('id'), str): ids.append(item['id'])
        if len(ids) != len(set(ids)): errors.append(field + ' duplicate ids')
    if errors:
        return sorted(set(errors))
    steps = [s['id'] for s in d['steps']]; kcs = {k['id'] for k in d['kc_candidates']}
    used = {k for s in d['steps'] for k in s['kc_ids']}
    if used != kcs: errors.append('unknown or unused KCs')
    covered = {s for m in d['methods'] for s in m['step_ids']}
    if covered != set(steps): errors.append('unknown or uncovered steps')
    for m in d['methods']:
        if all(s in steps for s in m['step_ids']):
            indices = [steps.index(s) for s in m['step_ids']]
            if indices != sorted(set(indices)): errors.append('method order or duplicates')
    if d['solution_status'] == 'solved' and not (steps and kcs and d['methods']): errors.append('empty solved solution')
    return errors


def table(path, records, fields):
    with Path(path).open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields); writer.writeheader(); writer.writerows(records)


def build(run):
    """Recompute derived tables. Raw inputs, reviews and mapping are never modified."""
    run = Path(run).resolve(); manifest = read(run / 'manifest.json')
    if sha(run / 'prompt-A.txt') != manifest['prompt_sha256']: raise ValueError('Changed prompt snapshot')
    for task in manifest['tasks']:
        if 'input_sha256' in task and sha(run / 'inputs' / f'{task["task_id"]}.json') != task['input_sha256']: raise ValueError('Changed statement input')
        if sha(run / 'requests' / f'{task["task_id"]}.txt') != task['request_sha256']: raise ValueError('Changed request')
        for image in task['images']:
            if sha(run / image['svg_path']) != image['original_sha256']: raise ValueError('Changed original image')
            if 'png_sha256' not in image or sha(run / image['path']) != image['png_sha256']: raise ValueError('PNG rendering not finalized or changed')
    derived = run / 'derived'; derived.mkdir(exist_ok=True)
    status, steps, kcs, methods, step_kc, method_steps = [], [], [], [], [], []
    valid = {}
    for job in manifest['jobs']:
        if 'instruction_sha256' in job and sha(run / 'jobs' / f'{job["job_id"]}.txt') != job['instruction_sha256']: raise ValueError('Changed agent instruction')
        jid = job['job_id']; raw = run / job['raw_path']
        row = {'job_id': jid, 'task_id': job['task_id'], 'repeat': job['repeat'], 'raw_path': job['raw_path'],
               'raw_sha256': sha(raw) if raw.exists() else '', 'json_valid': False, 'structure_valid': False,
               'errors': '', 'steps': 0, 'kcs': 0, 'methods': 0, 'math_status': 'not_reviewed', 'annotation_status': 'not_reviewed'}
        if (run/'responses.json').exists():
            captured=read(run/'responses.json')
            if jid in captured and captured[jid]['raw_sha256'] != row['raw_sha256']: raise ValueError('Changed captured response: ' + jid)
        review_path = run / 'reviews' / f'{job["task_id"]}.json'
        if review_path.exists():
            review = read(review_path)
            entry = next((e for e in review.get('results', []) if e.get('job_id') == jid), None)
            if entry:
                if entry.get('raw_sha256') != row['raw_sha256']: raise ValueError('Review hash mismatch: ' + jid)
                row.update({key: entry.get(key, 'not_reviewed') for key in ('math_status', 'annotation_status')})
                if row['math_status'] not in ('passed','failed','uncertain','not_reviewed'): raise ValueError('Unknown math status')
                if row['annotation_status'] not in ('accepted','needs_revision','rejected','not_reviewed'): raise ValueError('Unknown annotation status')
        if not raw.exists(): row['errors'] = 'missing'
        else:
            try: d = read(raw); row['json_valid'] = True
            except (ValueError, UnicodeError) as exc: row['errors'] = str(exc)
            else:
                errors = validate(d, job['task_id']); row['errors'] = '; '.join(errors)
                if not errors:
                    row.update(structure_valid=True, steps=len(d['steps']), kcs=len(d['kc_candidates']), methods=len(d['methods']))
                    valid[jid] = d
                    base = {'job_id': jid, 'task_id': job['task_id'], 'repeat': job['repeat'], 'raw_path': job['raw_path']}
                    for index, s in enumerate(d['steps']):
                        steps.append({**base, 'step_id': s['id'], 'order': index + 1, 'action': s['action'], 'result': s['result']})
                        step_kc.extend({**base, 'step_id': s['id'], 'kc_id': k} for k in s['kc_ids'])
                    kcs.extend({**base, 'kc_id': k['id'], 'name': k['name'], 'description': k['description']} for k in d['kc_candidates'])
                    for method in d['methods']:
                        methods.append({**base, 'method_id': method['id'], 'name': method['name'], 'length': len(method['step_ids'])})
                        method_steps.extend({**base, 'method_id': method['id'], 'step_id': s, 'order': i+1} for i,s in enumerate(method['step_ids']))
        status.append(row)
    base = ['job_id', 'task_id', 'repeat', 'raw_path']
    for name, records, fields in [('status',status,list(status[0])), ('steps',steps,base+['step_id','order','action','result']),
            ('kcs',kcs,base+['kc_id','name','description']), ('methods',methods,base+['method_id','name','length']),
            ('step_kc',step_kc,base+['step_id','kc_id']), ('method_steps',method_steps,base+['method_id','step_id','order'])]:
        table(derived / f'{name}.csv', records, fields)
    mapping_path = run / 'kc_mapping.json'; catalog_path = run / 'catalog.json'
    mapping = read(mapping_path) if mapping_path.exists() else []
    catalog = read(catalog_path) if catalog_path.exists() else []
    canonical_ids = {c['id'] for c in catalog}
    mapped = {}
    for entry in mapping:
        key = (entry['job_id'], entry['kc_id'])
        if key in mapped: raise ValueError('Duplicate mapping: ' + str(key))
        if entry['canonical_id'] not in canonical_ids: raise ValueError('Unknown canonical KC')
        if entry['job_id'] not in valid or entry['kc_id'] not in {k['id'] for k in valid[entry['job_id']]['kc_candidates']}: raise ValueError('Mapping target missing')
        if entry.get('raw_sha256') != sha(run / 'raw' / f'{entry["job_id"]}.txt'): raise ValueError('Stale mapping')
        mapped[key] = entry['canonical_id']
    complete = {jid for jid,d in valid.items() if all((jid,k['id']) in mapped for k in d['kc_candidates'])}
    sets = {jid: {mapped[jid,k['id']] for k in valid[jid]['kc_candidates']} for jid in complete}
    pairs = []
    for task in manifest['tasks']:
        jobs = [j for j in manifest['jobs'] if j['task_id'] == task['task_id']]
        for a,b in itertools.combinations(jobs,2):
            x,y=a['job_id'],b['job_id']; available = x in sets and y in sets and bool(sets[x] | sets[y])
            pairs.append({'task_id':task['task_id'],'a':x,'b':y,'available':available,
                          'jaccard': len(sets[x]&sets[y])/len(sets[x]|sets[y]) if available else '',
                          'both_math_passed': all(next(s for s in status if s['job_id']==j)['math_status']=='passed' for j in (x,y))})
    table(derived/'stability.csv',pairs,['task_id','a','b','available','jaccard','both_math_passed'])
    stability_summary=[]
    for task in manifest['tasks']:
        available=[p['jaccard'] for p in pairs if p['task_id']==task['task_id'] and p['available']]
        checked=[p['jaccard'] for p in pairs if p['task_id']==task['task_id'] and p['available'] and p['both_math_passed']]
        stability_summary.append({'task_id':task['task_id'],'position':task.get('position',''),
            'available_pairs':len(available),'mean_jaccard':sum(available)/len(available) if available else '',
            'math_passed_pairs':len(checked),'mean_jaccard_math_passed':sum(checked)/len(checked) if checked else ''})
    table(derived/'stability_summary.csv',stability_summary,list(stability_summary[0]))
    # Only explicitly reviewed answers enter corpus statistics; union across repeats is labelled.
    eligible={s['job_id'] for s in status if s['math_status']=='passed' and s['annotation_status']=='accepted' and s['job_id'] in complete}
    task_sets={t['task_id']:set().union(*(sets[j['job_id']] for j in manifest['jobs'] if j['task_id']==t['task_id'] and j['job_id'] in eligible)) for t in manifest['tasks']}
    frequencies=Counter(k for s in task_sets.values() for k in s)
    names={c['id']:c['name'] for c in catalog}
    table(derived/'kc_frequency.csv',[{'canonical_id':k,'name':names[k],'distinct_tasks_any_accepted_repeat':n} for k,n in sorted(frequencies.items())],['canonical_id','name','distinct_tasks_any_accepted_repeat'])
    presence=[{'task_id':j['task_id'],'repeat':j['repeat'],'job_id':j['job_id'],'canonical_id':k} for j in manifest['jobs'] if j['job_id'] in eligible for k in sorted(sets[j['job_id']])]
    table(derived/'task_kc.csv',presence,['task_id','repeat','job_id','canonical_id'])
    co=Counter()
    for task in manifest['tasks']:
        task_pairs={pair for j in manifest['jobs'] if j['task_id']==task['task_id'] and j['job_id'] in eligible
                    for pair in itertools.combinations(sorted(sets[j['job_id']]),2)}
        co.update(task_pairs)
    table(derived/'cooccurrence.csv',[{'kc_a':a,'kc_b':b,'distinct_tasks_same_accepted_repeat':n} for (a,b),n in sorted(co.items())],['kc_a','kc_b','distinct_tasks_same_accepted_repeat'])
    summary={'expected':len(status),'present':sum(s['errors']!='missing' for s in status),'json_valid':sum(s['json_valid'] for s in status),
             'structure_valid':len(valid),'math_reviewed':sum(s['math_status']!='not_reviewed' for s in status),
             'fully_mapped_responses':len(complete),'available_jaccard_pairs':sum(p['available'] for p in pairs),
             'eligible_corpus_responses':len(eligible),'eligible_distinct_tasks':sum(bool(s) for s in task_sets.values()),
             'canonical_kcs_in_eligible_tasks':len(frequencies),
             'singleton_fraction':sum(n==1 for n in frequencies.values())/len(frequencies) if frequencies else None,
             'corpus_policy':'union across mathematically passed, annotation accepted, fully mapped repeats; task counted once',
             'prerequisite_inference':False,'official_fipi_coverage':'not_computed_no_mapping'}
    summary['math_status_counts']=dict(Counter(s['math_status'] for s in status))
    summary['annotation_status_counts']=dict(Counter(s['annotation_status'] for s in status))
    summary['review_scope']='Preliminary LLM review, not independent expert validation'
    summary['mapping_scope']='Conservative draft matching of KC definitions; composite and differently scoped definitions kept separate; not an approved skill catalog'
    task_means=[s['mean_jaccard'] for s in stability_summary if s['available_pairs']]
    summary['mean_jaccard_over_available_tasks']=sum(task_means)/len(task_means) if task_means else None
    summary['tasks_with_jaccard']=len(task_means)
    write(derived/'summary.json',summary)
    dependencies=['manifest.json','prompt-A.txt']+[j['raw_path'] for j in manifest['jobs'] if (run/j['raw_path']).exists()]
    dependencies += [f'inputs/{t["task_id"]}.json' for t in manifest['tasks'] if (run/f'inputs/{t["task_id"]}.json').exists()]
    dependencies += [f'requests/{t["task_id"]}.txt' for t in manifest['tasks']]
    dependencies += [p for p in ('responses.json','environment.txt') if (run/p).exists()]
    dependencies += [p.relative_to(run).as_posix() for p in (run/'reviews').glob('*.json')]
    dependencies += [p for p in ('catalog.json','kc_mapping.json') if (run/p).exists()]
    write(derived/'provenance.json',{'pipeline_sha256':sha(__file__),'inputs':{p:sha(run/p) for p in sorted(dependencies)},
          'outputs':{p.name:sha(p) for p in sorted(derived.glob('*.csv'))},'summary_sha256':sha(derived/'summary.json')})
    return summary


def merge_catalog(run):
    """Materialize saved semantic decisions, without inventing new mappings."""
    run=Path(run); spec=run/'catalog-parts.json'
    if not spec.exists(): return
    catalogs={}; mapping=[]; seen=set()
    for part in read(spec):
        for candidate in read(run/part['catalog']):
            cid=candidate['id']
            if cid in catalogs and catalogs[cid]!=candidate: raise ValueError('Conflicting canonical definition: '+cid)
            catalogs[cid]=candidate
        for entry in read(run/part['mapping']):
            key=(entry['job_id'],entry['kc_id'])
            if key in seen: raise ValueError('Duplicate semantic decision: '+str(key))
            seen.add(key); mapping.append(entry)
    if any(e['canonical_id'] not in catalogs for e in mapping): raise ValueError('Undefined canonical ID')
    write(run/'catalog.json',[catalogs[k] for k in sorted(catalogs)])
    write(run/'kc_mapping.json',sorted(mapping,key=lambda e:(e['job_id'],e['kc_id'])))


def capture(run):
    """Seal received bytes after collection; never repair or overwrite a response."""
    run=Path(run).resolve(); manifest=read(run/'manifest.json')
    captured={}; positions={t['task_id']:t['position'] for t in manifest['tasks']}
    for job in manifest['jobs']:
        raw=run/job['raw_path']
        if not raw.is_file(): raise ValueError('Missing expected response: '+job['job_id'])
        captured[job['job_id']]={'raw_path':job['raw_path'],'raw_sha256':sha(raw),
            'agent_task':f'/root/a{positions[job["task_id"]]:02d}_r{job["repeat"]}',
            'capture_method':'Agent wrote completed JSON to file as a separate technical operation; original bytes retained.'}
        message=(f'Выполни только инструкцию из файла {run.as_posix()}/jobs/{job["job_id"]}.txt. '
                 'Прочитай его UTF-8 через exec_command; это техническая загрузка задания. Другие документы проекта не читай. '
                 'Исходный ответ сохрани в назначенный инструкцией raw-файл. В конце верни только его путь.')
        captured[job['job_id']]['launch_message']=message
    existing=run/'responses.json'
    if existing.exists() and read(existing)!=captured: raise ValueError('Captured ledger already exists and differs')
    write(existing,captured)
    return {'captured':len(captured)}


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['prepare','build','capture']); parser.add_argument('run',type=Path)
    parser.add_argument('--repeats',type=int,default=3); parser.add_argument('--positions',type=int,nargs='+')
    args=parser.parse_args()
    if args.command=='build': merge_catalog(args.run)
    if args.command=='prepare': result=prepare(args.run,args.repeats,args.positions)
    elif args.command=='capture': result=capture(args.run)
    else: result=build(args.run)
    print(json.dumps(result,ensure_ascii=False,indent=2) if isinstance(result,dict) else result)
