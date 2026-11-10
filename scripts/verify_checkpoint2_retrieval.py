"""Validate saved retrieval section and evidence without inference or network."""
import ast
import hashlib
import io
import json
from pathlib import Path
import zipfile
import nbformat as nb
import numpy as np
import pandas as pd
from checkpoint2_retrieval import ARCHIVE_SHA256, retrieval_cells


def verify():
    root=Path(__file__).resolve().parents[1]
    notebook=nb.read(root/'notebooks/checkpoint-2/EDA.ipynb',as_version=4)
    nb.validate(notebook)
    new=[c for c in notebook.cells if c.metadata.get('study')=='retrieval-2026-11-10']
    assert [c.source for c in new]==[c.source for c in retrieval_cells()]
    for c in notebook.cells:
        if c.cell_type=='code':
            ast.parse(c.source)
            assert not any(o.output_type=='error' for o in c.get('outputs',[]))
    assert all(c.execution_count is not None for c in new if c.cell_type=='code')
    path=root/'notebooks/checkpoint-2/derived/retrieval-study-results.zip'
    assert hashlib.sha256(path.read_bytes()).hexdigest()==ARCHIVE_SHA256
    with zipfile.ZipFile(path) as z:
        hashes=json.loads(z.read('results-sha256.json'))
        for name,digest in hashes.items():
            assert hashlib.sha256(z.read(name)).hexdigest()==digest
        data={t['task_id']:t for t in map(json.loads,z.read('source-data/tasks.jsonl').decode().splitlines())}
        split=json.loads(z.read('source-data/split.json'))
        qids,cids=split['query_ids'],split['candidate_ids']
        scores=np.load(io.BytesIO(z.read('scores.npz')),allow_pickle=False)
        saved=pd.read_csv(io.BytesIO(z.read('per-query.csv')))
        rel=np.array([[bool(set(data[q]['kes_codes'])&set(data[c]['kes_codes'])) for c in cids] for q in qids])
        for key in scores.files:
            stage,variant=key.split(' | ',1)
            values=scores[key]
            assert values.shape==(20,280) and np.isfinite(values).all()
            ordered=np.take_along_axis(rel,np.argsort(-values,axis=1,kind='stable'),axis=1)
            got=np.array([ordered[:,:5].mean(1),ordered[:,:5].any(1),
                np.where(ordered.any(1),1/(ordered.argmax(1)+1),0)]).T
            expected=saved[(saved.stage==stage)&(saved.variant==variant)].set_index('query_id').loc[qids]
            assert np.allclose(got,expected[['precision_at_5','hit_at_5','reciprocal_rank']],atol=1e-14)
    return {'notebook_valid':True,'new_cells':len(new),
        'new_code_cells_executed':sum(c.cell_type=='code' for c in new),
        'saved_comparisons_checked':len(scores.files),'saved_metric_rows_checked':len(saved),
        'archive_checksums_valid':True,'no_inference_or_network':True,
        'original_model_inference_repeated':False,'original_eda_cells_reexecuted':False}


if __name__=='__main__':
    result=verify()
    target=Path(__file__).resolve().parents[1]/'REVIEW-CHECK.json'
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))
