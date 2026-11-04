"""Verify the saved 100-task checkpoint, its replay notebook and the user stop cap."""
import base64
import json
import importlib.metadata
from pathlib import Path

import nbformat
from lxml import html
from PIL import Image

from fipi_extension import ROOT, RUN, read, freeze, sha, hashed, verify_frozen


def archive_reproducibility(summary):
    scripts=['fipi_extension.py','prepare_fipi_audit_packet.py','health_fipi_extension.py',
             'numeric_fipi_extension_checks.py','report_fipi_extension.py',
             'verify_fipi_checkpoint100.py','replay_fipi_checkpoint100.py','fipi_eda50.py','collect_fipi_bank.py']
    for name in scripts:
        freeze(RUN/'code-snapshot-100/scripts'/name,(ROOT/'scripts'/name).read_bytes())
    for p in RUN.glob('*.py'):
        freeze(RUN/'code-snapshot-100/run'/p.name,p.read_bytes())
    packages=['lxml','Pillow','numpy','matplotlib','nbformat','nbclient','ipykernel','jupyter-client','pyzmq','tornado','IPython']
    freeze(RUN/'code-snapshot-100/used-package-versions.json',
           {p:importlib.metadata.version(p) for p in packages})
    files=[]
    for folder in ['raw','attempts','executions','validations','requests','inputs','calibration',
                   'code-snapshot-100','active-scopes','checks']:
        files += [p for p in (RUN/folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts
                  and p.name!='checkpoint100-final-verification.json']
    for name in ['PROTOCOL.md','selection.json','eligible.json','exclusions.json','freeze-manifest.json',
                 'baseline-manifest.json','catalog-v1.json','catalog-for-auditor.json','author-prompt.txt',
                 'author-wrapper.txt','auditor-prompt.txt','audit-format-wrapper-v1.1.txt',
                 'execution-protocol-v1.1.json','environment.json','scope-change-2026-11-03.json']:
        files.append(RUN/name)
    manifest={'checkpoint_total':100,'new_task_limit':50,'active_snapshot':summary['active_snapshot'],
              'files':[hashed(p) for p in sorted(set(files))],
              'code_replay':'Restore files from code-snapshot-100/scripts to their original scripts paths if current code has changed; snapshot copies are not runnable from their archive location.',
              'model_replay':'Exact requests and actual dispatch logs are preserved; identical new model outputs are not guaranteed. Model ID/settings unavailable are recorded as unknown.'}
    freeze(RUN/'reproducibility-manifest-100.json',manifest)
    return hashed(RUN/'reproducibility-manifest-100.json')


def notebook_check(path, figures):
    nb=nbformat.read(path,as_version=4)
    cells=[c for c in nb.cells if c.cell_type=='code']
    assert len(cells)==4 and all(c.execution_count is not None for c in cells)
    assert not [o for c in cells for o in c.get('outputs',[]) if o.output_type=='error']
    png=[base64.b64decode(o['data']['image/png']) for c in cells for o in c.get('outputs',[]) if 'image/png' in o.get('data',{})]
    assert len(png)==4 and {sha(b) for b in png}=={sha(p.read_bytes()) for p in figures}
    return {'path':hashed(path),'executed_code_cells':4,'embedded_figures_match':4}


def main():
    verify_frozen()
    selection=read(RUN/'selection.json');ids={t['task_id'] for t in selection['tasks'][:50]}
    assert len(ids)==50
    for role in ['author','auditor']:
        actual={p.stem for p in (RUN/'raw'/role).glob('*.json')}
        assert actual==ids,(role,'missing',ids-actual,'outside_user_cap',actual-ids)
    cap=read(RUN/'scope-change-2026-11-03.json');assert cap['target_total']==100 and cap['new_task_limit']==50
    for batch in range(1,5):
        h=read(RUN/'checks'/f'batch-{batch:02}.json')
        assert h['status'] in ['pass','quarantine'] and not h['systemic_unresolved']
    assert not list((RUN/'checks').glob('batch-0[5-9].json'))
    out=RUN/'derived/checkpoint-100-v1'
    for name,digest in read(out/'output-hashes.json').items():
        assert sha((out/name).read_bytes())==digest,('output changed',name)
    for name,digest in read(out/'provenance.json')['input_hashes'].items():
        assert sha((ROOT/name).read_bytes())==digest,('input changed',name)
    summary=read(out/'summary.json');new=summary['populations']['new_accumulated']
    assert summary['mode']=='checkpoint' and summary['checkpoint_total']==100
    assert new['author_n']==new['complete_n']==50
    assert new['author_modes'].get('source_reading_feedback',0)==1
    figures=sorted(out.glob('0*.png'));assert len(figures)==4
    for p in figures:
        with Image.open(p) as im:im.verify()
    notebooks=[notebook_check(out/'review.ipynb',figures)]
    replay=RUN/'checks/checkpoint100-replay.ipynb'
    if replay.exists():notebooks.append(notebook_check(replay,figures))
    links=0
    for p in out.rglob('*.html'):
        tree=html.fromstring(p.read_text(encoding='utf-8'))
        for value in tree.xpath('//@href | //@src'):
            if not value or value.startswith(('#','https:','http:','data:','mailto:')):continue
            target=(p.parent/value.split('#')[0]).resolve()
            assert target.exists(),(p,value)
            links+=1
    result={'status':'passed','original_50_and_bank':'byte-identical','new_tasks':50,'total_tasks':100,
            'health_batches':[1,2,3,4],'checkpoint':str(out.relative_to(ROOT)).replace('\\','/'),
            'included_new':new['included_n'],'author_modes':new['author_modes'],
            'figures':4,'local_html_links_checked':links,'notebooks':notebooks,
            'new_task_cap_respected':True,'no_tasks_101_to_200_generated':True,
            'math_validation':'Primary-assistant spot calculations and independent KC audits; no expert answer key',
            'reproducibility_manifest':archive_reproducibility(summary),
            'verifier':hashed(Path(__file__).resolve())}
    freeze(RUN/'checks/checkpoint100-final-verification.json',result)
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
