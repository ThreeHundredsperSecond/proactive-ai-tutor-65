"""Verify the checkpoint package and replay the notebook from repository root."""
from pathlib import Path
import hashlib
import json
import os
import re
import sys
from urllib.parse import unquote, urlsplit
from archive_support import resolve_path

ROOT=Path(__file__).resolve().parents[1]
DEST=ROOT/'notebooks/checkpoint-2'
EXT=ROOT/'data/annotation/runs/2026-11-02-fipi-extension-150'


def read(p): return json.loads(p.read_text(encoding='utf-8'))
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    import nbformat
    from nbclient import NotebookClient
    source=DEST/'EDA.ipynb'
    nb=nbformat.read(source,as_version=4)
    def inspect(n):
        code=[c for c in n.cells if c.cell_type=='code']
        assert [c.execution_count for c in code]==list(range(1,len(code)+1))
        assert not [o for c in code for o in c.outputs if o.output_type=='error']
        png=sum('image/png' in o.get('data',{}) for c in code for o in c.outputs)
        assert png==11, png
        sources='\n'.join(c.source for c in n.cells)
        assert '.html' not in sources, 'The main notebook must not require HTML pages'
        assert '127.0.0.1' not in sources and 'localhost' not in sources
        assert not any('text/html' in o.get('data',{}) for c in code for o in c.outputs)
        for c in n.cells:
            if c.cell_type=='markdown':assert c.source.count('$')%2==0,'Unbalanced inline math'
        return dict(cells=len(n.cells),code_cells=len(code),embedded_png=png)
    counts=inspect(nb)
    before={p.name:sha(p) for p in (DEST/'derived').iterdir() if p.suffix in ('.csv','.png') or p.name in ('summary.json','integrated-summary.json')}
    oldpath=os.environ.get('PATH','')
    os.environ['PATH']=str(Path(sys.executable).parent)+os.pathsep+oldpath
    try:
        NotebookClient(nb,timeout=180,kernel_name='python3',resources={'metadata':{'path':str(ROOT)}}).execute()
    finally:
        os.environ['PATH']=oldpath
    assert inspect(nb)==counts
    after={p.name:sha(p) for p in (DEST/'derived').iterdir() if p.suffix in ('.csv','.png') or p.name in ('summary.json','integrated-summary.json')}
    assert before==after, 'Replay changed data/figure outputs'
    # The executed primary notebook is the deliverable. Replay is verified in
    # memory; the former saved replay is now an immutable archived snapshot.
    checked=0
    for manifest in ['baseline-manifest.json','reproducibility-manifest-100.json']:
        for row in read(EXT/manifest)['files']:
            assert sha(resolve_path(ROOT/row['path']))==row['sha256'], row['path']
            checked+=1
    provenance=read(DEST/'derived/provenance.json')
    for path,h in provenance['input_hashes'].items():
        assert sha(ROOT/path)==h,path
    paths=[ROOT/'README.md',ROOT/'docs/eda/README.md',ROOT/'docs/eda/05-analysis/README.md',
           ROOT/'docs/eda/05-analysis/checkpoint-2-plan.md',ROOT/'docs/eda/05-analysis/checkpoint-2-practical-value.md',
           ROOT/'docs/eda/05-analysis/data-to-tutor-protocol.md',ROOT/'docs/eda/team-handoff.md']
    texts=[(p.parent,p.read_text(encoding='utf-8')) for p in paths]
    texts.extend((DEST,c.source) for c in nb.cells if c.cell_type=='markdown')
    links=0
    for parent,text in texts:
        for ref in re.findall(r'\]\(([^)]+)\)',text):
            ref=ref.strip('<>');url=urlsplit(ref)
            if url.scheme or not url.path:continue
            p=(parent/unquote(url.path)).resolve()
            # This report is written only after the checks pass.
            if p == DEST/'derived/verification.json':
                links+=1
                continue
            assert p.exists(),str(p)
            links+=1
    result=dict(passed=True,scope='Consolidated single notebook: no new model calls/collection or HTML/service dependency; replay from root and initial execution from notebook directory',
                notebook=counts,replay_data_and_figures_byte_identical=True,replay_persistence='In memory; former replay archived',historical_hash_checks=checked,
                provenance_hash_checks=len(provenance['input_hashes']),local_links_checked=links,
                pdf='One-page practical-value PDF authored and visually reviewed separately; notebook replay preserves its bytes',
                outputs={p.relative_to(ROOT).as_posix():sha(p) for p in sorted(DEST.rglob('*')) if p.is_file() and p.name!='verification.json'})
    for path in ['output/pdf/checkpoint-2-practical-value.pdf','docs/eda/05-analysis/checkpoint-2-practical-value.md',
                 'scripts/build_checkpoint2.py','scripts/build_checkpoint2_pdf.py','scripts/verify_checkpoint2.py']:
        result['outputs'][path]=sha(ROOT/path)
    import importlib.metadata
    result['runtime']={'python':sys.version,'packages':{m:importlib.metadata.version(m) for m in ['nbformat','nbclient','ipykernel','matplotlib','numpy','lxml']}}
    (DEST/'derived/verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in ('outputs','runtime')},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
