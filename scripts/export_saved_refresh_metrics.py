"""Export complete tables for the pinned saved-data refresh; no inference."""
import csv
import hashlib
import json
from pathlib import Path

import fipi_saved_refresh as refresh


def main():
    base, new, _, _, hashes, _, _ = refresh.collect()
    rows = base['historical']+base['sol']+base['opus']+new
    summary,tables = refresh.previous.rep.metrics(dict(baseline=base['baseline'],new=rows,catalog=base['catalog']))
    saved=refresh.read(refresh.OUT/'summary.json')['populations']['published315']
    assert json.loads(json.dumps(summary['mixed_cumulative'])) == saved
    out=refresh.OUT/'tables';out.mkdir(exist_ok=True)
    outputs={}
    for name, values in tables.items():
        selected=[r for r in values if r.get('population','mixed_cumulative')=='mixed_cumulative']
        assert selected,name
        p=out/(name+'.csv')
        with p.open('w',encoding='utf-8-sig',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(selected[0]));w.writeheader();w.writerows(selected)
        outputs[p.relative_to(refresh.ROOT).as_posix()]=refresh.sha(p)
    hashes[Path(__file__).relative_to(refresh.ROOT).as_posix()]=refresh.sha(__file__)
    hashes[(refresh.OUT/'provenance.json').relative_to(refresh.ROOT).as_posix()]=refresh.sha(refresh.OUT/'provenance.json')
    refresh.write(refresh.OUT/'tables-provenance.json',dict(input_hashes=hashes,outputs=outputs,
        counts_match_saved_summary=True,model_calls=0,scope='All standard checkpoint metrics for published315'))
    print(json.dumps({'tables':len(outputs),'selected':saved['selected_n'],'included':saved['included_n']}))


if __name__=='__main__':main()
