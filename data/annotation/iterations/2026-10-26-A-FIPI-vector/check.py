"""Check saved input/JSON/code/anchor integrity; not a semantic or math judge."""
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / 'scripts'))
from annotation_pipeline import validate


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    m = json.loads((HERE / 'manifest.json').read_text(encoding='utf-8'))
    for name, expected in m['files'].items():
        assert sha(HERE / name) == expected, name
    assert sha(ROOT / m['source_catalog']) == m['source_catalog_sha256']
    assert sha(HERE / 'prepare.py') == m['prepare_script_sha256']
    catalog = json.loads((HERE / 'catalog.json').read_text(encoding='utf-8'))['requirements']
    codes = {r['code']: r['requirement'] for r in catalog}
    request = (HERE / 'request.txt').read_text(encoding='utf-8')
    assert len(codes) == 13 and all(r in request for r in codes.values())
    assert '{task_json}' not in request
    result = {'raw_sha256': sha(HERE / 'raw.txt'), 'checker_sha256': sha(Path(__file__)),
              'base_validator_sha256': sha(ROOT / 'scripts/annotation_pipeline.py'),
              'requirements_in_request': len(codes), 'errors': [],
              'scope': 'Integrity/format/reference/quote checks only. Semantic and math review separate.'}
    errors = result['errors']
    try:
        d = json.loads((HERE / 'raw.txt').read_text(encoding='utf-8'))
        extra = {'selected_requirements', 'fipi_links'}
        if not extra <= set(d):
            errors.append('missing FIPI fields')
        else:
            base = {k: v for k, v in d.items() if k not in extra}
            errors.extend(validate(base, '699086'))
            selected = d['selected_requirements']
            if not isinstance(selected, list) or not all(isinstance(c, str) and c in codes for c in selected) or len(selected) != len(set(selected)):
                errors.append('invalid selected_requirements')
            links = d['fipi_links']
            if not isinstance(links, list):
                errors.append('fipi_links not list')
            elif not errors:
                kc_ids = {k['id'] for k in d['kc_candidates']}
                seen_kcs, seen_codes = set(), set()
                for row in links:
                    if set(row) != {'requirement_code', 'kc_ids', 'anchor', 'reason'}:
                        errors.append('link fields'); continue
                    code = row['requirement_code']
                    ids = row['kc_ids']
                    if not isinstance(ids, list) or not ids or not all(isinstance(k, str) and k in kc_ids for k in ids) or len(ids) != len(set(ids)):
                        errors.append('link KC references'); continue
                    seen_kcs.update(ids)
                    if not isinstance(row['reason'], str) or not row['reason'].strip():
                        errors.append('empty reason')
                    if code is None:
                        if row['anchor'] != '': errors.append('unknown link anchor must be empty')
                    elif not isinstance(code, str) or code not in codes:
                        errors.append('unknown requirement code')
                    else:
                        seen_codes.add(code)
                        if not isinstance(row['anchor'], str) or not row['anchor'].strip() or row['anchor'] not in codes[code]:
                            errors.append('anchor not literal substring')
                if seen_kcs != kc_ids: errors.append('unmapped KCs')
                if seen_codes != set(selected): errors.append('unused or unselected requirements')
                result['selected_requirements'] = selected
                result['kc_count'] = len(kc_ids)
                result['unknown_links'] = sum(row['requirement_code'] is None for row in links)
    except (ValueError, TypeError, KeyError) as exc:
        errors.append(str(exc))
    result['status'] = 'passed' if not errors else 'failed'
    (HERE / 'technical-check.json').write_bytes((json.dumps(result, ensure_ascii=False, indent=2)+'\n').encode('utf-8'))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
