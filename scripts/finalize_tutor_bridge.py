"""Execute the bridge notebook and verify evidence, replay, and preservation."""
from pathlib import Path
import json
import os
import re
import sys
from urllib.parse import unquote,urlsplit

import nbformat as nb
from nbclient import NotebookClient
from lxml import html
import build_tutor_bridge as b


def pointer(obj,ptr):
    for part in ptr.strip('/').split('/'):
        if part:obj=obj[int(part)] if isinstance(obj,list) else obj[part.replace('~1','/').replace('~0','~')]
    return obj


def main():
    b.build();out=b.OUT
    text=(out/'report.md').read_text(encoding='utf-8')
    # Capture the complete current pre-existing analysis v1 as an additional
    # preservation boundary; it remains a historical exploratory output.
    old=b.ROOT/'data/annotation/analyses/2026-11-04-data-to-tutor-v1'
    keep=out/'checks/prior-v1-preservation.json'
    if not keep.exists():b.dump(keep,{p.relative_to(b.ROOT).as_posix():b.sha(p) for p in old.rglob('*') if p.is_file()})
    book=nb.v4.new_notebook(metadata={'kernelspec':{'name':'python3','display_name':'Python 3','language':'python'}})
    parts=text.split('\n## ')
    book.cells.append(nb.v4.new_markdown_cell(parts[0]))
    book.cells.append(nb.v4.new_code_cell('''from pathlib import Path
import sys, json
from IPython.display import display, Image, HTML, Markdown
root=next(p for p in (Path.cwd(), *Path.cwd().parents) if (p/'scripts/build_tutor_bridge.py').exists())
sys.path.insert(0,str(root/'scripts'))
import build_tutor_bridge as bridge
bridge.build()
out=bridge.OUT
summary=bridge.read(out/'summary.json')
print('Без моделей и сети. Структурный анализ 100 разборов; основные показатели по 98; качественные контрасты 19 задач.')'''))
    for part in parts[1:]:
        imgs=re.findall(r'!\[[^\]]*\]\(([^)]+)\)',part)
        book.cells.append(nb.v4.new_markdown_cell('## '+re.sub(r'!\[[^\]]*\]\([^)]+\)','',part)))
        if imgs:book.cells.append(nb.v4.new_code_cell('\n'.join('display(Image(filename=str(out / '+repr(p)+')))' for p in imgs)))
        if part.startswith('3.'):
            book.cells.append(nb.v4.new_code_cell('''from lxml import html as dom
tree=dom.fromstring((out/'index.html').read_text(encoding='utf-8'))
for case_id in ['P02','P03','P04']:
    panel=tree.get_element_by_id(case_id)
    # HTML snapshots in the notebook carry the same original formulas/images.
    # Rewrite relative source image URLs for this notebook's identical folder.
    panel.set('open','open')
    display(HTML(dom.tostring(panel,encoding='unicode')))'''))
        if part.startswith('4.'):
            book.cells.append(nb.v4.new_code_cell('''contracts=bridge.read(out/'derived-contracts.json')
c=next(c for c in contracts if c['task_id']=='D334F2')
for value in ['75000','300000','x=75000']:
    print(value, bridge.check_component(c,value))
print('Искусственные программные примеры: 75000 — ответ компонента; полный вопрос требует 300000.')'''))
    before={p.relative_to(out).as_posix():b.sha(p) for p in out.rglob('*') if p.is_file() and (p.suffix in ('.csv','.png') or p.name in ('summary.json','derived-contracts.json','evidence.json','index.html','report.md'))}
    oldpath=os.environ.get('PATH','');os.environ['PATH']=str(Path(sys.executable).parent)+os.pathsep+oldpath
    try:NotebookClient(book,timeout=180,kernel_name='python3',resources={'metadata':{'path':str(out)}}).execute()
    finally:os.environ['PATH']=oldpath
    nb.write(book,out/'review.ipynb')
    after={p.relative_to(out).as_posix():b.sha(p) for p in out.rglob('*') if p.is_file() and (p.suffix in ('.csv','.png') or p.name in ('summary.json','derived-contracts.json','evidence.json','index.html','report.md'))}
    assert before==after,'Replay changed data/figures/report'
    evidence=b.read(out/'evidence.json')
    for e in evidence:
        path=b.ROOT/e['path'];assert b.sha(path)==e['sha256']
        assert pointer(b.read(path),e['pointer'])==e['value'],e['id']
    provenance=b.read(out/'provenance.json');provenance['input_hashes'][Path(__file__).relative_to(b.ROOT).as_posix()]=b.sha(Path(__file__))
    b.dump(out/'provenance.json',provenance)
    for path,h in provenance['input_hashes'].items():assert b.sha(b.ROOT/path)==h,path
    frozen=0
    for name in ['baseline-manifest.json','reproducibility-manifest-100.json']:
        for e in b.read(b.EXT/name)['files']:assert b.sha(b.ROOT/e['path'])==e['sha256'];frozen+=1
    for path,h in b.read(keep).items():assert b.sha(b.ROOT/path)==h,path
    preliminary=b.read(b.ROOT/'notebooks/checkpoint-2/derived/verification.json')
    for path,h in preliminary['outputs'].items():assert b.sha(b.ROOT/path)==h,path
    links=0
    for path in out.rglob('*'):
        if path.suffix=='.html':refs=html.fromstring(path.read_text(encoding='utf-8')).xpath('//@src | //@href')
        elif path.suffix=='.md':refs=re.findall(r'\]\(([^)]+)\)',path.read_text(encoding='utf-8'))
        else:continue
        for ref in refs:
            url=urlsplit(ref)
            if url.scheme or not url.path:continue
            p=(path.parent/unquote(url.path)).resolve()
            if p==out/'checks/final.json':continue
            assert p.exists(),(path,ref);links+=1
    assert sum('image/png' in o.get('data',{}) for c in book.cells for o in c.get('outputs',[]))==2
    tests=b.read(out/'checks/synthetic-component-tests.json')['tests'];assert len(tests)==60 and all(t['expected_status']==t['actual_status'] for t in tests)
    b.dump(out/'checks/final.json',dict(passed=True,scope='Local exploratory content representation, not learner or tutoring efficacy evaluation',
        replay_data_report_and_figures_identical=True,exact_evidence_fields=len(evidence),input_hash_checks=len(provenance['input_hashes']),
        historical_hash_checks=frozen,prior_v1_files_preserved=len(b.read(keep)),preliminary_outputs_preserved=len(preliminary['outputs']),
        software_probes=len(tests),software_probes_are_synthetic=True,local_links_checked=links,embedded_png=2,
        browser_checks='See separately recorded checks/browser-review.json; visual/UI checks are not mathematical expertise'))
    b.dump(out/'output-hashes.json',{p.relative_to(out).as_posix():b.sha(p) for p in sorted(out.rglob('*')) if p.is_file() and p.name!='output-hashes.json'})
    print(json.dumps(b.read(out/'checks/final.json'),ensure_ascii=False,indent=2))


if __name__=='__main__':main()
