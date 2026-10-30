"""Offline checks and reports for the frozen context/transfer probe.

Standard library only. Never changes inputs, jobs, raw, or historical artifacts.
Semantic judgments remain in the agent responses and review-notes.json; checks
of literal quotes and the mechanical support rule do not validate mathematics.
"""
import hashlib
import json
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CARD_IDS = {'lin_eq', 'quad_D', 'log_domain', 'vec_endpoints', 'vec_lincomb',
            'vec_dot', 'mean_freq', 'median'}
OP = {'full', 'partial', 'none', 'uncertain'}
STATE = {'supported', 'not_shown', 'violated'}
PRE = {'known', 'not_shown', 'violated'}
RAW_PATHS = {'raw/cards-v02.json', 'raw/context-plain-r1.json', 'raw/context-plain-r2.json',
             'raw/context-state-r1.json', 'raw/context-state-r2.json', 'raw/transfer.json'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def unique(rows, key, expected, label):
    values = [row[key] for row in rows]
    require(len(values) == len(set(values)) and set(values) == set(expected),
            f'{label}: unexpected or repeated identifiers: {values}')
    return {row[key]: row for row in rows}


def support(operation, state, statuses):
    if operation == 'none':
        return 'no_current_action'
    if state == 'violated' or 'violated' in statuses:
        return 'violated_application'
    if operation == 'full' and state == 'supported' and all(s == 'known' for s in statuses):
        return 'supported_application'
    return 'conditional_application'


def quote_checks(items, sources, key, label, allowed=None):
    """No Unicode, whitespace, punctuation or substring normalization."""
    records = []
    require(isinstance(items, list), f'{label}: evidence must be a list')
    for i, item in enumerate(items):
        source, quote = item.get(key), item.get('quote')
        valid = (source in sources and isinstance(quote, str) and bool(quote)
                 and quote in sources[source] and (allowed is None or source in allowed))
        records.append({'field': label, 'index': i, 'source': source,
                        'quote': quote, 'literal_match': bool(valid)})
    return records


def hash_checks(manifest, base):
    checks = []
    for row in manifest['files']:
        path = base / row['path']
        actual = sha(path) if path.is_file() else None
        checks.append({'path': row['path'], 'expected_sha256': row['sha256'],
                       'actual_sha256': actual, 'match': actual == row['sha256']})
    return checks


def capture_checks(manifest, base):
    """Reject corruption against the separate, retained raw checkpoint."""
    unique(manifest['files'], 'path', RAW_PATHS, 'raw captures')
    checks = hash_checks(manifest, base)
    require(all(c['match'] for c in checks), 'Raw capture hash mismatch')
    return checks


def pointer(doc, path):
    for token in path.lstrip('/').split('/'):
        token = token.replace('~1', '/').replace('~0', '~')
        doc = doc[int(token)] if isinstance(doc, list) else doc[token]
    return doc


def provenance(record, expected_text=None):
    p = record['provenance']
    path = ROOT / p['path']
    require(path.is_file() and sha(path) == p['sha256'], f"Provenance hash: {p['path']}")
    obj = pointer(read(path), p['json_pointer'])
    if expected_text is not None:
        require(obj == expected_text, f"Provenance text: {p['path']}#{p['json_pointer']}")
    return obj


def validate_application(row, card, sources, label, quotes, transfer=False):
    operation = row['action_match' if transfer else 'operation_observed']
    require(operation in (OP - {'none'} if transfer else OP), f'{label}: operation')
    require(row['input_state'] in STATE, f'{label}: input_state')
    pres = unique(row['preconditions'], 'id', [p['id'] for p in card['preconditions']], label)
    key = 'segment' if transfer else 'source'
    operations_allowed = set(sources) - {'question'} if transfer else {'current'}
    quotes.extend(quote_checks(row['operation_evidence'], sources, key,
                               label + '/operation_evidence', operations_allowed))
    require(operation == 'none' or row['operation_evidence'], f'{label}: operation evidence absent')
    require(operation != 'none' or not row['operation_evidence'], f'{label}: evidence for absent action')
    quotes.extend(quote_checks(row['input_evidence'], sources, key, label + '/input_evidence'))
    require(row['input_state'] == 'not_shown' or row['input_evidence'], f'{label}: input evidence absent')
    for id_, p in pres.items():
        require(p['status'] in PRE, f'{label}/{id_}: status')
        require(isinstance(p['reason'], str) and p['reason'], f'{label}/{id_}: reason')
        require(p['status'] == 'not_shown' or p['evidence'], f'{label}/{id_}: evidence absent')
        quotes.extend(quote_checks(p['evidence'], sources, key, label + '/' + id_))
        if not transfer:
            require(type(p['checked_in_current']) is bool, f'{label}/{id_}: checked type')
            if p['checked_in_current']:
                require(any(e['source'] == 'current' for e in p['evidence']), f'{label}/{id_}: checked source')
    expected = support(operation, row['input_state'], [p['status'] for p in pres.values()])
    require(row['support'] == expected, f'{label}: support rule, expected {expected}')
    if not transfer:
        require(row['coverage'] in {'full', 'partial', 'none'}, f'{label}: coverage')
        quotes.extend(quote_checks(row['remainder'], sources, key, label + '/remainder', {'current'}))
    return {'operation': operation, 'input_state': row['input_state'],
            'preconditions': {id_: p['status'] for id_, p in pres.items()},
            'support': row['support']}


def agreement(a, b, fields):
    result = {}
    for field in fields:
        rows = [{'id': id_, 'r1': a[id_][field], 'r2': b[id_][field],
                 'equal': a[id_][field] == b[id_][field]} for id_ in sorted(a)]
        result[field] = {'matches': sum(r['equal'] for r in rows), 'total': len(rows), 'rows': rows}
    pres = [{'id': id_, 'precondition': p, 'r1': a[id_]['preconditions'][p],
             'r2': b[id_]['preconditions'][p],
             'equal': a[id_]['preconditions'][p] == b[id_]['preconditions'][p]}
            for id_ in sorted(a) for p in a[id_]['preconditions']]
    result['precondition_status'] = {'matches': sum(r['equal'] for r in pres), 'total': len(pres), 'rows': pres}
    return result


def quote_block(items, key):
    if not items:
        return ['Нет цитаты операции.']
    lines = []
    for e in items:
        lines.append(f"Источник `{e[key]}`:")
        lines.extend('> ' + line for line in e['quote'].splitlines())
        lines.append('')
    return lines


def markdown_cards(cards, registry):
    lines = ['# Восемь карточек v0.2', '',
             'Определения ниже буквально перенесены из [raw/cards-v02.json](raw/cards-v02.json). '
             'Изменений карты по итогам применений нет. Это кандидаты, не установленная структура освоения.', '',
             'Назначения и ограничения: [реестр свидетельств](evidence-registry.md). '
             'Отсутствие назначения не означает отсутствие умения.', '']
    fields = [('core_operation', 'Действие'), ('input_representation', 'Вход'),
              ('result', 'Результат'), ('observable_product', 'Наблюдаемый продукт'),
              ('evidence_rule', 'Правило свидетельства'), ('open_boundary', 'Открытая граница')]
    for c in cards.values():
        lines += [f"## {c['candidate_id']}: {c['name']}", '']
        for field, title in fields[:3]:
            lines += [f"**{title}.** {c[field]}", '']
        lines += ['**Предусловия входа:**', '']
        for p in c['preconditions']:
            lines += [f"- `{p['id']}` {p['predicate']} Основание: {p['why_needed']}"]
        lines.append('')
        for field, title in [('algorithm_notes', 'Алгоритм и ветви'), ('includes', 'Включает'), ('excludes', 'Не включает')]:
            lines += [f'**{title}:**', ''] + ['- ' + t for t in c[field]] + ['']
        for field, title in fields[3:]:
            lines += [f"**{title}.** {c[field]}", '']
        lines += ['**Связи с ФИПИ — интерпретации проекта:**', '']
        lines += [f"- `{l['kind']}:{l['code']}` — {l['anchor']}" for l in c['official_links']]
        ids = [r['evidence_id'] for r in registry if r['candidate_id'] == c['candidate_id']]
        lines += ['', '**Применения в этой пробе:** ' + (', '.join(f'`{id_}`' for id_ in ids) if ids else 'Назначений нет.')
                  + ' Положительных синтетических примеров в этом опыте нет.', '']
    return '\n'.join(lines)


def markdown_evidence(registry, transfer_tasks, reviews, legacy):
    lines = ['# Реестр свидетельств', '',
             'Автоматически собран из сохранённых ответов; их смысловые оценки принадлежат агентам. '
             'Буквальная цитата подтверждает происхождение текста, а не истинность оценки.', '',
             'Входы: [контекст и происхождение](inputs/context-cases.json), [учебные трассы](inputs/transfer.json), '
             '[приватный источник](inputs/legacy-sample.json). Проверки: [technical.json](derived/technical.json).', '',
             'Имеются 12 назначенных проверок текущего шага и два положительных сопоставления поддействий готовой трассы. '
             'Это сохранённые LLM-разборы, не попытки учеников. Новых предметных синтетических примеров нет.', '']
    for r in registry:
        lines += [f"## {r['evidence_id']}", '',
                  f"Карточка `{r['candidate_id']}`; случай `{r['case_id']}`; тип: {r['probe_type']}. "
                  f"Источник ответа: [{r['raw_path']}]({r['raw_path']}).", '',
                  f"Операция: `{r['operation']}`. Вход: `{r['input_state']}`. Итог агента: `{r['support']}`.", '',
                  'Предусловия: ' + ', '.join(f'`{p}={s}`' for p, s in r['preconditions'].items()) + '.', '']
        if 'coverage' in r:
            lines += [f"Охват всего текущего шага: `{r['coverage']}`; это отдельная оценка от завершённости операции.", '']
        if 'provenance' in r:
            p = r['provenance']
            lines += [f"Происхождение current: `{p['path']}#{p['json_pointer']}`, SHA-256 `{p['sha256']}`.", '']
        if 'legacy_provenance' in r:
            p = r['legacy_provenance']
            lines += [f"Старая репа, commit `{legacy['ref']}`; `{p['path']}`, task `{p['source_task_id']}`, "
                      f"строки {p['start_line']}–{p['end_line']}, blob `{p['blob_sha']}`.", '']
        lines += ['**Свидетельство текущей операции:**', '']
        lines += quote_block(r['operation_evidence'], r['source_key'])
        lines += ['', '**Свидетельство входа:**', '']
        lines += quote_block(r['input_evidence'], r['source_key'])
        lines += ['', r['note'], '']
    lines += ['## Все шесть трасс второго источника', '',
              '| Трасса | Назначения | Предложения о непокрытых действиях |', '|---|---|---|']
    for t in transfer_tasks:
        lines += [f"| {t['id']} | {', '.join(a['candidate_id'] for a in t['assignments']) or 'нет'} | "
                  '; '.join(m['description'] for m in t['missing_families']) + ' |']
    lines += ['', 'Пустое назначение — отчёт агента об отсутствии подходящего наблюдаемого применения. '
              'Это не независимая оценка всех возможных способов решения и не полный список арифметических действий.', '',
              '## Отдельный просмотр результатов', '',
              'Следующие замечания записаны после просмотра ответов в [review-notes.json](review-notes.json); '
              'это интерпретации анализирующего агента, не замороженный эталон и не результаты автоматического парсинга.', '']
    for note in reviews['notes']:
        lines += [f"- **{note['id']}.** {note['finding']}"]
    return '\n'.join(lines) + '\n'


def main():
    # All original files are read-only; only derived reports are written below.
    captures = capture_checks(read(HERE / 'captures.json'), HERE)
    frozen = hash_checks(read(HERE / 'frozen.json'), HERE)
    frozen += hash_checks(read(HERE / 'transfer-frozen.json'), HERE)
    require(all(c['match'] for c in frozen), 'Frozen inputs changed')
    cards = unique(read(HERE / 'raw/cards-v02.json')['cards'], 'candidate_id', CARD_IDS, 'cards')
    official = read(HERE / 'inputs/official.json')
    official_source_checks = []
    for kind in ('requirements', 'content'):
        d = official[kind]
        p = ROOT / d['source']
        official_source_checks.append({'kind': kind, 'source': d['source'], 'match': sha(p) == d['sha256']})
    require(all(c['match'] for c in official_source_checks), 'Official source changed')
    for card in cards.values():
        unique(card['preconditions'], 'id', [p['id'] for p in card['preconditions']], card['candidate_id'])
        for link in card['official_links']:
            lookup = {e['code']: e['text'] for e in official[link['kind']]['entries']}
            require(link['code'] in lookup and link['anchor'] in lookup[link['code']], 'Official anchor mismatch')
    full_cases = unique(read(HERE / 'inputs/context-cases.json')['cases'], 'id', {'Q01', 'Q02', 'Q03'}, 'cases')
    provenance_count = 0
    for c in full_cases.values():
        obj = provenance(c)
        require(c['current'] == obj['action'] + '\n' + obj['result'], 'Current provenance')
        provenance_count += 1
        for ctx in c['context']:
            provenance(ctx, ctx['text'])
            provenance_count += 1
    quotes, registry, context, all_raw = [], [], {}, []
    for arm in ('plain', 'state'):
        context[arm] = {}
        for repeat in (1, 2):
            name = f'context-{arm}-r{repeat}'
            incoming_list = read(HERE / f'inputs/{name}.json')['cases']
            expected_order = list(full_cases) if repeat == 1 else list(reversed(full_cases))
            require([c['id'] for c in incoming_list] == expected_order, name + ': input order')
            incoming = unique(incoming_list, 'id', full_cases, name)
            output = unique(read(HERE / f'raw/{name}.json')['rows'], 'id', incoming, name + ': output')
            context[arm][repeat] = {}
            all_raw.append(f'raw/{name}.json')
            for id_, row in output.items():
                c = incoming[id_]
                original = full_cases[id_]
                require(c['candidate'] == cards[c['candidate']['candidate_id']] == original['candidate'], name + ': card')
                require(c['current'] == original['current'], name + ': current changed')
                expected_context = [{'id': t['id'], 'text': t['text']} for t in original['context']] if arm == 'state' else []
                require(c['context'] == expected_context, name + ': context changed')
                sources = {'current': c['current'], **{t['id']: t['text'] for t in c['context']}}
                label = f'{name}/{id_}'
                checked = validate_application(row, c['candidate'], sources, label, quotes)
                checked['coverage'] = row['coverage']
                checked['checked_in_current'] = {p['id']: p['checked_in_current'] for p in row['preconditions']}
                context[arm][repeat][id_] = checked
                registry.append({'evidence_id': label, 'case_id': id_, 'candidate_id': c['candidate']['candidate_id'],
                                 'probe_type': 'текущий шаг без контекста' if arm == 'plain' else 'текущий шаг с прежним состоянием',
                                 'raw_path': f'raw/{name}.json', **checked, 'source_key': 'source',
                                 'operation_evidence': row['operation_evidence'], 'input_evidence': row['input_evidence'],
                                 'precondition_details': row['preconditions'], 'provenance': original['provenance'],
                                 'context_provenance': original['context'] if arm == 'state' else [],
                                 'note': row['note']})
    transfer_input = read(HERE / 'inputs/transfer.json')
    require(transfer_input['cards'] == list(cards.values()), 'Transfer cards changed')
    tasks = unique(transfer_input['tasks'], 'id', {f'L{i:02d}' for i in range(1, 7)}, 'transfer input')
    legacy = read(HERE / 'inputs/legacy-sample.json')
    legacy_provenance = {}
    for file in legacy['files']:
        for task in file['tasks']:
            id_ = task['id']
            expected = [{'id': 'question', 'text': task['question']}]
            expected += [{'id': f"s{s['index']}", 'text': s['text']} for s in task['steps']]
            expected += [{'id': 'answer', 'text': task['answer']}]
            require(tasks[id_]['segments'] == expected, f'{id_}: legacy trace extraction')
            legacy_provenance[id_] = {k: task[k] for k in ('source_task_id', 'start_line', 'end_line')}
            legacy_provenance[id_].update({k: file[k] for k in ('path', 'blob_sha')})
    transfer = unique(read(HERE / 'raw/transfer.json')['tasks'], 'id', tasks, 'transfer output')
    all_raw += ['raw/cards-v02.json', 'raw/transfer.json']
    for id_, row in transfer.items():
        sources = {s['id']: s['text'] for s in tasks[id_]['segments']}
        seen = set()
        for a in row['assignments']:
            cid = a['candidate_id']
            require(cid in cards and cid not in seen, f'{id_}: unexpected assignment')
            seen.add(cid)
            label = f'transfer/{id_}/{cid}'
            checked = validate_application(a, cards[cid], sources, label, quotes, transfer=True)
            registry.append({'evidence_id': label, 'case_id': id_, 'candidate_id': cid,
                             'probe_type': 'готовая трасса другого источника; поддействие',
                             'raw_path': 'raw/transfer.json', **checked, 'source_key': 'segment',
                             'operation_evidence': a['operation_evidence'], 'input_evidence': a['input_evidence'],
                             'precondition_details': a['preconditions'], 'legacy_provenance': legacy_provenance[id_],
                             'note': a['scope_note']})
        for j, missing in enumerate(row['missing_families']):
            quotes += quote_checks([missing], sources, 'segment', f'transfer/{id_}/missing/{j}', set(sources) - {'question'})
    literal_failures = [q for q in quotes if not q['literal_match']]
    require(not literal_failures, f'Nonliteral/invalid quotes: {literal_failures}')
    math_check = read(HERE / 'legacy-math-check.json')
    require(math_check['source_sha256'] == sha(HERE / 'inputs/legacy-sample.json'), 'Math check source stale')
    require(math_check['code_sha256'] == sha(HERE / 'check_legacy_math.py'), 'Math check code stale')
    # Snapshot comparison is broader than this task: concurrent edits outside this
    # folder are reported, never overwritten or silently called a failed probe.
    baseline = hash_checks(read(HERE / 'baseline-files.json'), ROOT)
    for entry in baseline:
        documentary = (entry['path'] == 'AGENTS.md' or
                       (entry['path'].startswith('docs/eda/') and entry['path'].endswith('/README.md')))
        entry['comparison_scope'] = 'historical_snapshot_outside_frozen_probe'
        entry['difference_category'] = (None if entry['match'] else
                                       'historical_document_change' if documentary else
                                       'historical_file_change_needs_separate_review')
    reviews = read(HERE / 'review-notes.json')
    context_records = [r for r in registry if r['probe_type'].startswith('текущий')]
    transfer_records = [r for r in registry if not r['probe_type'].startswith('текущий')]
    saved_source = read(HERE / 'source-verification.json')
    unique(saved_source['checks'], 'task', tasks, 'saved source verification')
    for record in saved_source['checks']:
        p = legacy_provenance[record['task']]
        require(all(record[k] == p[k] for k in ('path', 'blob_sha', 'start_line', 'end_line')),
                'Saved source verification metadata mismatch')
        require(all(record[k] is True for k in ('exact_block', 'question_found', 'steps_found')),
                'Saved source verification recorded a failure')
    technical = {'capture_checks': captures, 'all_captures_match': all(c['match'] for c in captures),
                 'capture_manifest_sha256': sha(HERE / 'captures.json'),
                 'frozen_checks': frozen, 'all_frozen_match': all(c['match'] for c in frozen),
                 'official_source_checks': official_source_checks, 'context_provenance_records': provenance_count,
                 'legacy_trace_extractions': len(tasks), 'support_rule_rows': len(registry),
                 'literal_quote_count': len(quotes), 'literal_quote_failures': literal_failures,
                 'literal_quote_checks': quotes, 'baseline_snapshot_checks': baseline,
                 'baseline_snapshot_matches': sum(c['match'] for c in baseline),
                 'baseline_snapshot_total': len(baseline),
                 'baseline_mismatches': [c for c in baseline if not c['match']],
                 'baseline_scope_note': 'Historical 348-file snapshot is broader than frozen probe inputs. '
                    'Changes to AGENTS.md and stage README files are documentary changes, not probe failures. '
                    'The historical snapshot is never refreshed by this analyzer.',
                 'raw_files_at_analysis': [{'path': p, 'sha256': sha(HERE / p)} for p in all_raw],
                 'analyzer_sha256': sha(Path(__file__)), 'review_notes_sha256': sha(HERE / 'review-notes.json'),
                 'limitations': ['Exact textual matching and mechanical rule checks only; no semantic or expert validation.',
                                'Saved source-verification.json records an earlier remote check, not a fresh network verification.',
                                'No additional sources, solutions, model calls or synthetic subject examples.']}
    repeat_agreement = {arm: agreement(context[arm][1], context[arm][2],
                                    ['operation', 'input_state', 'coverage', 'support', 'checked_in_current'])
                        for arm in context}
    transitions = []
    for repeat in (1, 2):
        for id_ in sorted(full_cases):
            a, b = context['plain'][repeat][id_], context['state'][repeat][id_]
            transitions.append({'repeat': repeat, 'id': id_, 'without_context': a, 'with_context': b,
                                'support_changed': a['support'] != b['support']})
    summary = {'context': context, 'context_decisions': len(context_records), 'repeat_agreement': repeat_agreement,
               'context_transitions': transitions,
               'support_counts': dict(Counter(r['support'] for r in context_records)),
               'transfer': {'tasks': len(tasks), 'assignments': len(transfer_records),
                            'tasks_with_assignments': [id_ for id_, t in transfer.items() if t['assignments']],
                            'missing_family_mentions': sum(len(t['missing_families']) for t in transfer.values()),
                            'by_task': [{'id': id_, 'assignments': [a['candidate_id'] for a in t['assignments']],
                                         'missing_families': t['missing_families']} for id_, t in transfer.items()]},
               'card_count': len(cards), 'official_content_points': len(official['content']['entries']),
               'official_link_codes': sorted({l['code'] for c in cards.values() for l in c['official_links']}),
               'synthetic_subject_examples': 0, 'review_notes': reviews,
               'limitations': 'Small known cases, agent judgments, no learner observations, external gold standard or causal learning comparison.'}
    dump(HERE / 'derived/technical.json', technical)
    dump(HERE / 'derived/summary.json', summary)
    dump(HERE / 'derived/evidence-registry.json', {'records': registry, 'synthetic_subject_examples': []})
    (HERE / 'cards.md').write_text(markdown_cards(cards, registry), encoding='utf-8')
    (HERE / 'evidence-registry.md').write_text(markdown_evidence(registry, list(transfer.values()), reviews, legacy), encoding='utf-8')
    print(json.dumps({'frozen': f"{len(frozen)}/{len(frozen)}", 'literal_quotes': len(quotes),
                      'raw_captures': f"{len(captures)}/{len(captures)}",
                      'support_rule_rows': len(registry), 'baseline_snapshot': f"{sum(c['match'] for c in baseline)}/{len(baseline)}",
                      'context_decisions': len(context_records), 'transfer_assignments': len(transfer_records)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
