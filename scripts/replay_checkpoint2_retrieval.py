"""Recompute only retrieval analysis from saved evidence; no model imports/network."""
import argparse
import copy
from pathlib import Path
import nbformat as nb
from nbclient import NotebookClient
from checkpoint2_retrieval import retrieval_cells, add_retrieval_cells


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path,
        help='Original repository EDA to integrate into; omit to refresh the existing retrieval section')
    parser.add_argument('--kernel', default='python3', help='Jupyter kernel with numpy, pandas, matplotlib')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    target = args.output or root/'notebooks/checkpoint-2/EDA.ipynb'
    source = nb.read(args.source or target, as_version=4)
    if not args.source:
        source.cells = [c for c in source.cells if c.metadata.get('study')!='retrieval-2026-11-10']
        # Keep the chapter 9/10 synthesis already added by the integration.
        fresh = copy.deepcopy(source)
        fresh.cells = retrieval_cells()
        NotebookClient(fresh,timeout=180,kernel_name=args.kernel,
            resources={'metadata':{'path':str(target.parent)}}).execute()
        marker = next(i for i,c in enumerate(source.cells)
            if c.cell_type=='markdown' and '## 9. Итог:' in c.source)
        source.cells[marker:marker] = fresh.cells
    else:
        fresh = nb.v4.new_notebook(cells=retrieval_cells())
        NotebookClient(fresh,timeout=180,kernel_name=args.kernel,
            resources={'metadata':{'path':str(target.parent)}}).execute()
        source.cells = add_retrieval_cells(source.cells, fresh.cells)
    source.metadata['retrieval_evidence'] = {
        'scope':'Replay of saved scores only; original model runs are not repeated',
        'archive':'derived/retrieval-study-results.zip',
        'comparisons':39,'queries':20,'candidates':280}
    # Keep one coherent execution sequence after replaying the inserted section.
    count = 0
    for cell in source.cells:
        if cell.cell_type == 'code':
            count += 1
            cell.execution_count = count
            for output in cell.get('outputs', []):
                if output.output_type == 'execute_result':
                    output.execution_count = count
    nb.validate(source)
    nb.write(source,target)
    print(target)


if __name__=='__main__':
    main()
