"""Predeclared samples, local rendering and batch health; no semantic KC edits."""
import argparse
import html as escape
import json
import os
import subprocess
from pathlib import Path

from lxml import html
from PIL import Image

from collect_fipi_bank import browser_math
from fipi_eda50 import validate_one
from fipi_extension import RUN, ROOT, read, freeze, hashed, validate_audit

QA = '''<script>addEventListener('load',()=>document.body.setAttribute('data-health',JSON.stringify({images:[...document.images].map(i=>i.complete&&i.naturalWidth>0),math:document.querySelectorAll('math').length,mfenced:document.querySelectorAll('mfenced').length,width:document.body.scrollWidth,math_ok:[...document.querySelectorAll('math')].every(m=>m.namespaceURI==='http://www.w3.org/1998/Math/MathML'&&m.getBoundingClientRect().height>0)})))</script>'''


def tasks(batch):
    return [t for t in read(RUN/'selection.json')['tasks'] if t['batch'] == batch]


def active(tid, role):
    overrides = read(RUN/'active-attempts.json') if (RUN/'active-attempts.json').exists() else {}
    return RUN / overrides.get(tid, {}).get(role, 'raw/'+role+'/'+tid+'.json')


def sample(batch):
    ts = tasks(batch); chosen = [ts[0]['task_id']]
    for field in ['images', 'mathml']:
        t = next((t for t in ts if t[field]), None)
        if t and t['task_id'] not in chosen: chosen.append(t['task_id'])
    for t in ts:
        if len(chosen) >= min(3, len(ts)): break
        if t['task_id'] not in chosen: chosen.append(t['task_id'])
    obj = {'batch': batch, 'task_ids': chosen,
           'rule': 'first task, first image, first MathML; deduplicate and fill next in selection order'}
    freeze(RUN/'checks'/f'batch-{batch:02}-sample-plan.json', obj)
    return obj


def card(tid):
    r = read(RUN/'inputs/tasks'/(tid+'.json'))
    statement = r['statement_html']
    for a in r['assets']:
        statement = statement.replace('../'+a['path'], (RUN/'inputs'/a['path']).as_uri())
    body = '<section><h2>'+escape.escape(tid)+'</h2><p>'+escape.escape(r['instruction'])+'</p>'+browser_math(statement)
    for role in ['author', 'auditor']:
        p = active(tid, role)
        if p.exists():
            body += '<h3>'+role+'</h3><pre>'+escape.escape(json.dumps(read(p), ensure_ascii=False, indent=2))+'</pre>'
    return body+'</section>'


def document(body):
    return '<!doctype html><html lang="ru"><meta charset="utf-8"><style>body{margin:28px;max-width:1450px;font:20px Georgia;background:white;color:#182b34}section{padding:18px;border-bottom:2px solid #aaa}pre{white-space:pre-wrap;font:15px monospace}img{max-width:100%;height:auto}math{font-size:1.3em}</style><body>'+body+QA+'</body></html>'


def render(batch):
    ts = tasks(batch); plan = sample(batch); results=[]
    groups = [('all', [t['task_id'] for t in ts])] + [(tid, [tid]) for tid in plan['task_ids']]
    for label, ids in groups:
        p = RUN/'checks'/f'batch-{batch:02}-{label}.html'
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(document(''.join(card(tid) for tid in ids)), encoding='utf-8')
        png = p.with_suffix('.png')
        command = ['C:/Program Files/Google/Chrome/Application/chrome.exe', '--headless', '--disable-gpu',
                   '--no-first-run', '--no-default-browser-check',
                   '--user-data-dir='+str(Path(os.environ['TEMP'])/f'fipi-extension-render-{batch}'),
                   '--window-size=1600,2200', '--virtual-time-budget=1000', '--dump-dom',
                   '--screenshot='+str(png), p.as_uri()]
        process = subprocess.run(command, capture_output=True, timeout=60)
        assert process.returncode == 0 and png.exists(), process.stderr.decode(errors='replace')[-300:]
        tree = html.fromstring(process.stdout.decode('utf-8')); h = json.loads(tree.xpath('//body/@data-health')[0])
        inputs = [read(RUN/'inputs/tasks'/(tid+'.json')) for tid in ids]
        assert h['math'] == sum(r['mathml_count'] for r in inputs) and h['mfenced'] == 0 and h['math_ok'], h
        assert len(h['images']) == sum(len(r['assets']) for r in inputs) and all(h['images']), h
        assert h['width'] <= 1600, h
        with Image.open(png) as im: im.verify()
        results.append({'label': label, 'task_ids': ids, 'browser': h, 'screenshot': hashed(png), 'html': hashed(p)})
    path = RUN/'checks'/f'batch-{batch:02}-render.json'
    freeze(path, {'batch': batch, 'status': 'technical_pass', 'cards': results})
    print(path)


def finish(batch):
    ts = tasks(batch); technical=[]; flags=[]
    for t in ts:
        tid=t['task_id']; p=active(tid,'author'); q=active(tid,'auditor')
        d=read(p); validate_one(d); assert d['task_id']==tid
        result=validate_audit(tid,q,author_path=p.relative_to(ROOT).as_posix());technical.append(result)
        a=read(q)
        if d['solution_status'] != 'solved' or a['issues']:
            flags.append({'task_id':tid,'solution_status':d['solution_status'],'issues':a['issues']})
    rendered=read(RUN/'checks'/f'batch-{batch:02}-render.json')
    visual=read(RUN/'checks'/f'batch-{batch:02}-visual.json')
    math=read(RUN/'checks'/f'batch-{batch:02}-math.json')
    plan=sample(batch)
    assert set(visual['reviewed_ids']) >= set(plan['task_ids'])
    assert {x['task_id'] for x in math['checks']} >= set(plan['task_ids'])
    assert not visual.get('systemic_unresolved') and not math.get('systemic_unresolved')
    quarantine=[t['task_id'] for t in ts if read(active(t['task_id'],'author'))['solution_status']!='solved'
                or any(i['blocking'] for i in read(active(t['task_id'],'auditor'))['issues'])]
    freeze(RUN/'checks'/f'batch-{batch:02}.json',{'batch':batch,'status':'quarantine' if quarantine else 'pass',
        'task_ids':[t['task_id'] for t in ts],'systemic_unresolved':False,'technical':technical,
        'render':rendered,'visual_review':visual,'math_spot_checks':math,'audit_flags':flags,'quarantined_ids':quarantine})
    print('Batch health complete:',batch,'quarantine:',quarantine)


def main():
    p=argparse.ArgumentParser();p.add_argument('command',choices=['plan','render','finish']);p.add_argument('--batch',type=int,required=True)
    a=p.parse_args()
    if a.command=='plan':print(json.dumps(sample(a.batch),ensure_ascii=False))
    elif a.command=='render':render(a.batch)
    else:finish(a.batch)


if __name__=='__main__':main()
