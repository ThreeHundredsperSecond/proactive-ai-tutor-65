"""Offline structural counts from minimal, version-pinned legacy extracts.

No model calls or execution of legacy scripts. Not a semantic KC validator.
"""
import json
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main():
    source = json.loads((HERE / 'legacy-calculus-input.json').read_text(encoding='utf-8'))
    tasks = []
    within_file_reuse = []
    for doc in source['analyses']:
        assert doc['block_kcs_occurrences'] == 0
        assert doc['task_markers'] == len(doc['tasks'])
        frequency = Counter(k for t in doc['tasks'] for k in set(t['kcs']))
        within_file_reuse.append({'source': doc['path'], 'tasks': len(doc['tasks']),
                                 'distinct_literal_ids': len(frequency),
                                 'ids_in_two_or_more_tasks': sum(v >= 2 for v in frequency.values())})
        tasks.extend(doc['tasks'])
    ids = Counter(k for t in tasks for k in set(t['kcs']))
    canon = {c['id'] for c in source['catalog']}
    aliases = defaultdict(set)
    for c in source['catalog']:
        for alias in c['synonyms']:
            aliases[alias].add(c['id'])
    leaf_ids = {Path(f['path']).stem for f in source['leaf_files']}
    # Tree also contains group and overview notes; do not count these as skill definitions.
    missing_files = sorted(set(ids) - leaf_ids)
    unmatched_catalog = sorted(set(ids) - canon - set(aliases))
    collapsed = []
    for t in tasks:
        mapped = set()
        for k in t['kcs']:
            candidates = aliases.get(k, set())
            mapped.add(k if k in canon or len(candidates) != 1 else next(iter(candidates)))
        collapsed.append(mapped)
    mapped_ids = Counter(k for ks in collapsed for k in ks)
    result = {
        'ref': source['ref'],
        'scope': 'Only the 10 calculus analysis files; different corpus from EGE, no quality comparison.',
        'tasks': len(tasks),
        'task_kc_assignments_deduplicated_per_task': sum(ids.values()),
        'distinct_literal_ids': len(ids),
        'literal_ids_in_two_or_more_tasks': sum(v >= 2 for v in ids.values()),
        'canonical_entries': len(canon),
        'literal_ids_with_exact_skill_filename': len(set(ids) & leaf_ids),
        'literal_ids_without_exact_skill_filename': missing_files,
        'literal_ids_not_addressed_by_catalog_or_synonym': unmatched_catalog,
        'ambiguous_aliases': {k: sorted(v) for k, v in aliases.items() if len(v) > 1},
        'illustration_only_apply_saved_aliases': {
            'warning': 'Mechanical legacy mapping, includes disputed merges; NOT an accepted catalog.',
            'remaining_distinct_ids': len(mapped_ids),
            'ids_in_two_or_more_tasks': sum(v >= 2 for v in mapped_ids.values()),
        },
        'within_file': within_file_reuse,
        'literal_frequency': dict(sorted(ids.items(), key=lambda kv: (-kv[1], kv[0]))),
    }
    output = HERE / 'legacy-calculus-counts.json'
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in result.items() if k not in ('within_file', 'literal_frequency', 'literal_ids_without_exact_skill_filename', 'literal_ids_not_addressed_by_catalog_or_synonym')}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
