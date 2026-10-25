"""Technical checks for this saved two-task run; no model calls or writes."""
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
schemas = {
    'steps': {'id': str, 'action': str, 'result': str, 'kc_ids': list},
    'kc_candidates': {'id': str, 'name': str, 'description': str},
    'methods': {'id': str, 'name': str, 'step_ids': list},
}
records = []
for task_id in ('699085', '699090'):
    d = json.loads((root / 'raw' / f'{task_id}.txt').read_text(encoding='utf-8'))
    assert set(d) == {'task_id', 'solution_status', 'steps', 'kc_candidates', 'methods', 'warnings'}
    assert d['task_id'] == task_id
    assert d['solution_status'] in ('solved', 'partial', 'unsolved')
    assert isinstance(d['warnings'], list) and all(isinstance(w, str) for w in d['warnings'])
    for field, schema in schemas.items():
        assert isinstance(d[field], list)
        for item in d[field]:
            assert set(item) == set(schema)
            for key, kind in schema.items():
                assert isinstance(item[key], kind)
                if kind is str:
                    assert item[key].strip()
                else:
                    assert item[key] and all(isinstance(s, str) and s.strip() for s in item[key])
        ids = [item['id'] for item in d[field]]
        assert len(ids) == len(set(ids))
    steps = [s['id'] for s in d['steps']]
    kcs = {k['id'] for k in d['kc_candidates']}
    assert {k for s in d['steps'] for k in s['kc_ids']} == kcs
    assert {s for m in d['methods'] for s in m['step_ids']} == set(steps)
    for method in d['methods']:
        indexes = [steps.index(s) for s in method['step_ids']]
        assert indexes == sorted(set(indexes))
    records.append({'task_id': task_id, 'technical_status': 'passed',
                    'steps': len(steps), 'kc_candidates': len(kcs), 'methods': len(d['methods'])})
print(json.dumps(records, ensure_ascii=False, indent=2))
