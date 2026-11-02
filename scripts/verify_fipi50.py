"""Audit frozen inputs, authored raw, editorial mappings and offline EDA outputs."""
import csv
import base64
import itertools
from collections import Counter
from pathlib import Path
import nbformat
from lxml import html
from PIL import Image
from fipi_eda50 import ROOT,RUN,read,write,digest,validate


def main():
    validate();m=read(RUN/'manifest.json');out=RUN/'derived';s=read(out/'summary.json')
    assert len(m['tasks'])==len({t['task_id'] for t in m['tasks']})==50
    assert digest((RUN/'baseline-A.txt').read_bytes())==m['baseline_sha256']
    captures=read(RUN/'captures.json');review=read(RUN/'review-decisions.json')
    raw={t['task_id']:read(RUN/'raw'/f'{t["task_id"]}.json') for t in m['tasks']}
    for tid,r in raw.items():
        h=digest((RUN/'raw'/f'{tid}.json').read_bytes())
        assert h==captures[tid]['sha256']==review['tasks'][tid]['raw_sha256']
    cat=read(RUN/'catalog-decisions.json');mapping={}
    for a in cat['assignments']:
        tid,kid=a['task_id'],a['local_id'];assert (tid,kid) not in mapping
        k=next(k for k in raw[tid]['kc_candidates'] if k['id']==kid)
        assert (k['name'],k['description'])==(a['source_name'],a['source_description'])
        expected=[dict(step_id=x['id'],action=x['action'],result=x['result']) for x in raw[tid]['steps'] if kid in x['kc_ids']]
        assert a['evidence']==expected
        mapping[(tid,kid)]=a['canonical_id']
    assert len(mapping)==sum(len(r['kc_candidates']) for r in raw.values())==204
    included=[tid for tid in raw if review['tasks'][tid]['include_primary_metrics']]
    assert len(included)==49 and 'eFF32e' not in included
    counts=Counter();pairs=Counter()
    for tid in included:
        nodes=sorted({mapping[(tid,k['id'])] for k in raw[tid]['kc_candidates']})
        counts.update(nodes);pairs.update(itertools.combinations(nodes,2))
    with (out/'kc-frequencies.csv').open(encoding='utf-8-sig') as f:freqrows=list(csv.DictReader(f))
    assert {r['kc_id']:int(r['task_n']) for r in freqrows}==dict(counts)
    with (out/'kc-cooccurrence.csv').open(encoding='utf-8-sig') as f:pairrows=list(csv.DictReader(f))
    assert {(r['kc_a'],r['kc_b']):int(r['task_n']) for r in pairrows}==dict(pairs)
    assert s['editorial_nodes_included']==len(counts) and s['singleton_nodes']==sum(n==1 for n in counts.values())
    assert counts['linear_equation']==7 and counts['pythagoras']==5
    assert s['all_steps']==sum(len(r['steps']) for r in raw.values())==162
    checked_links=0
    for tid in raw:
        path=out/'cards'/f'{tid}.html';tree=html.fromstring(path.read_text(encoding='utf-8'))
        frozen=read(RUN/'inputs/tasks'/f'{tid}.json')
        assert len(tree.xpath('//math'))==frozen['mathml_count']
        assert len(tree.xpath('//img'))==len(frozen['assets'])
        assert not tree.xpath('//mfenced')
        for target in tree.xpath('//@href|//img/@src'):
            if '://' in target or target.startswith('#'):continue
            assert (path.parent/target.split('#')[0]).resolve().exists(),(tid,target)
            checked_links+=1
    figures=list(out.glob('0*.png'));assert len(figures)==6
    for f in figures:
        with Image.open(f) as im:im.verify()
    nb=nbformat.read(ROOT/'notebooks/EDA.ipynb',as_version=4)
    code=[c for c in nb.cells if c.cell_type=='code']
    assert len(code)==6 and all(c.execution_count is not None for c in code)
    assert not [o for c in code for o in c.get('outputs',[]) if o.output_type=='error']
    embedded=[base64.b64decode(o['data']['image/png']) for c in code for o in c.get('outputs',[]) if 'image/png' in o.get('data',{})]
    assert len(embedded)==6 and {digest(b) for b in embedded}=={digest(f.read_bytes()) for f in figures}
    prov=read(out/'provenance.json')
    for r in prov['inputs']+prov['scripts']:assert digest((ROOT/r['path']).read_bytes())==r['sha256'],r['path']
    health=[read(RUN/'checks'/f'health-{i:02}.json') for i in range(1,8)]
    result=dict(status='passed',frozen_tasks=50,immutable_raw=50,included_for_primary_metrics=49,
                local_candidate_links=len(mapping),nodes_all=len(cat['nodes']),nodes_included=len(counts),
                steps=s['all_steps'],local_candidates=s['all_local_kcs'],figures=6,
                executed_notebook_cells=len(code),notebook_images_match_current_figures=True,html_links_checked=checked_links,health_check_files=len(health),
                math_validation='Preliminary primary-assistant review and recorded spot checks; no external expert key',
                notebook_sha256=digest((ROOT/'notebooks/EDA.ipynb').read_bytes()))
    write(RUN/'verification.json',result);print(result)


if __name__=='__main__':main()
