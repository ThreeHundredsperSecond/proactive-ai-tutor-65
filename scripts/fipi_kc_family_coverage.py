"""Offline KC support by conservative numeric-template family; no inference."""
import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
import shutil
import fipi_team_checkpoint250 as checkpoint
import fipi_domain_quality as domain

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'data/annotation/analyses/2026-11-09-kc-families-v1'
LAYERS = ['historical_editorial50','historical_independent50','sol50','Opus100']

def dump(p, value):
    p.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')

def csvout(p, rows):
    with p.open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)

def analyze(data):
    assignments = {(a['task_id'], a['local_id']): a['canonical_id'] for a in data['catalog']['assignments']}
    catalog = {n['id']:n for n in data['catalog']['nodes']}
    tasks, links = [], []
    for r in data['baseline']+data['new']:
        m = checkpoint.rep.mapping(r, assignments)
        family = domain.task_template(r['input'], mask=True)
        candidates = r['author']['kc_candidates']
        actions = r['author']['steps']
        matched_steps = sum(all(k in m for k in s['kc_ids']) and bool(s['kc_ids']) for s in actions)
        tasks.append(dict(task_id=r['task_id'], origin=r['origin'], included=r['included'],
            source_policy_included=r['source_policy_included'], template_family=family,
            primary_kes=r['primary_kes'], coarse_kes=r['primary_kes'].split('.')[0],
            catalog_nodes=';'.join(sorted(set(m.values()))), local_candidates=len(candidates),
            matched_candidates=len(m), unmatched_candidates=len(candidates)-len(m),
            steps=len(actions), fully_mapped_steps=matched_steps,
            source_run=r['source_run'], has_images=bool(r['input']['assets'])))
        if r['included']:
            for k in sorted(set(m.values())):
                links.append(dict(task_id=r['task_id'], origin=r['origin'], catalog_kc_id=k,
                    template_family=family, primary_kes=r['primary_kes'], coarse_kes=r['primary_kes'].split('.')[0]))
    rows, summaries = [], {}
    for population in ['mixed247','audited198',*LAYERS]:
        selected = [t for t in tasks if t['included'] and (population=='mixed247' or
            population=='audited198' and t['origin']!='historical_editorial50' or t['origin']==population)]
        ids = {t['task_id'] for t in selected}
        evidence = [l for l in links if l['task_id'] in ids]
        for k,n in catalog.items():
            support = [l for l in evidence if l['catalog_kc_id']==k]
            fam = Counter(l['template_family'] for l in support)
            rows.append(dict(population=population, catalog_kc_id=k, name=n['name'],
                task_frequency=len(support), family_frequency=len(fam),
                coarse_kes_count=len({l['coarse_kes'] for l in support}),
                largest_family_tasks=max(fam.values(), default=0),
                repeat_tasks=len(support)-len(fam),
                task_ids=';'.join(sorted(l['task_id'] for l in support)),
                family_ids=';'.join(sorted(fam))))
        current = rows[-len(catalog):]
        summaries[population] = dict(included_tasks=len(selected), families=len({t['template_family'] for t in selected}),
            catalog_nodes=len(catalog), support_bins={b:sum((r['family_frequency']==int(b) if b in ('0','1','2') else r['family_frequency']>=3) for r in current) for b in ('0','1','2','>=3')},
            tasks_with_unmatched_candidates=sum(t['unmatched_candidates']>0 for t in selected),
            local_candidates=sum(t['local_candidates'] for t in selected), unmatched_candidates=sum(t['unmatched_candidates'] for t in selected),
            steps=sum(t['steps'] for t in selected), fully_mapped_steps=sum(t['fully_mapped_steps'] for t in selected))
    assert len(tasks)==250 and sum(t['included'] for t in tasks)==247
    assert sum(t['source_policy_included'] for t in tasks)==248
    assert all(0<=r['family_frequency']<=r['task_frequency'] for r in rows)
    assert len(links)==len({(l['task_id'],l['catalog_kc_id']) for l in links})
    assert all(sum(s['support_bins'].values())==len(catalog) for s in summaries.values())
    assert summaries['sol50']['tasks_with_unmatched_candidates']==44
    return summaries, rows, tasks, links

def build():
    data = checkpoint.collect(strict=True)
    summary, rows, tasks, links = analyze(data)
    OUT.mkdir(parents=True, exist_ok=True)
    csvout(OUT/'kc-family-frequency.csv', rows); csvout(OUT/'tasks.csv', tasks); csvout(OUT/'kc-task-family-links.csv', links)
    dump(OUT/'summary.json', dict(policy='harmonized complete solved nonblocking; historical exclusions preserved', source_selected=250, source_policy_included=248, harmonized_included=247, populations=summary))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,ax=plt.subplots(figsize=(9,6))
    for pop, label in [('historical_editorial50','Редакторские 49'),('audited198','Аудированные 198'),('mixed247','Смешанные 247')]:
        rs=[r for r in rows if r['population']==pop and r['task_frequency']]
        ax.scatter([r['task_frequency'] for r in rs],[r['family_frequency'] for r in rs],label=label,alpha=.65)
    upper=max(r['task_frequency'] for r in rows)
    ax.plot([0,upper],[0,upper],'k--',alpha=.3);ax.set(xlabel='Число задач с KC',ylabel='Число числовых шаблонных семейств',title='Повторные задачи и разнообразие шаблонов');ax.legend();fig.tight_layout();fig.savefig(OUT/'task-vs-family.png',dpi=160);plt.close(fig)
    fig,ax=plt.subplots(figsize=(11,5)); pops=['historical_editorial50','historical_independent50','sol50','Opus100','mixed247']
    bottom=[0]*len(pops)
    for b in ('0','1','2','>=3'):
        vals=[summary[p]['support_bins'][b] for p in pops]
        ax.bar(pops,vals,bottom=bottom,label=b+' семейств');bottom=[a+c for a,c in zip(bottom,vals)]
    ax.set(ylabel='Узлов фиксированного каталога',title='Обеспеченность KC по источникам; нулевое покрытие сохранено');ax.tick_params(axis='x',rotation=15);ax.legend();fig.tight_layout();fig.savefig(OUT/'family-support-layers.png',dpi=160);plt.close(fig)
    mixed=[r for r in rows if r['population']=='mixed247']
    examples=sorted([r for r in mixed if r['repeat_tasks']>0], key=lambda r:(-r['repeat_tasks'],-r['largest_family_tasks'],r['catalog_kc_id']))[:5]
    lines=['# Обеспеченность KC шаблонными семействами','',
        'Вопрос: сколькими разными числовыми шаблонами поддержано действие, уже сопоставленное фиксированному каталогу? Единица частоты — уникальная задача; семейство — SHA нормализованного DOM/MathML, instruction и SHA рисунков после маскирования числовых токенов. Один KC считается один раз на задачу и семейство.',
        '', 'Основная выборка: 247 из 250 сохранённых задач. Исходные политики дают 248; 321FCD с raw partial исключена общей политикой. Редакторские назначения и независимые аудиты разделены. Наблюдение KC означает предварительное сопоставление, а не внешнюю математическую валидацию.', '',
        '| Слой | Задач | Семейств | KC: 0 | 1 | 2 | ≥3 | Задач с несопоставленными кандидатами |','|---|---:|---:|---:|---:|---:|---:|---:|']
    for p,s in summary.items():
        b=s['support_bins'];lines.append(f"| {p} | {s['included_tasks']} | {s['families']} | {b['0']} | {b['1']} | {b['2']} | {b['>=3']} | {s['tasks_with_unmatched_candidates']} |")
    lines+=['','![Частоты](task-vs-family.png)','', '## Повторы, видимые в сохранённых данных','', '| KC | Действие | Задач | Семейств | Задач в крупнейшем семействе |','|---|---|---:|---:|---:|']
    for r in examples:
        lines.append(f"| {r['catalog_kc_id']} | {r['name']} | {r['task_frequency']} | {r['family_frequency']} | {r['largest_family_tasks']} |")
    lines += ['', 'В этой выборке повторов немного: 247 задач образуют 239 групп. Здесь нет наблюдения «10 задач в одном числовом шаблоне»; максимальные повторные группы в приведённых KC содержат две задачи. Основной наблюдаемый дефицит — малая поддержка многих KC, а не массовое дублирование.', '']
    for r in examples:
        support=[l for l in links if l['catalog_kc_id']==r['catalog_kc_id']]
        fam=Counter(l['template_family'] for l in support)
        top=sorted(fam,key=lambda k:(-fam[k],k))[0]
        lines.append(r['catalog_kc_id']+': пример повторного семейства '+', '.join(sorted(l['task_id'] for l in support if l['template_family']==top))+'. Все ID приведены в CSV.')
        lines.append('')
    sol=summary['sol50'];mix=summary['mixed247']
    lines+=['','![Поддержка по слоям](family-support-layers.png)','', '## Покрытие действий и ограничения','',
        f"В Sol50 у 44 из 50 задач есть хотя бы один несопоставленный локальный кандидат. Полностью сопоставлены все KC лишь у {50-44} задач; {sol['unmatched_candidates']} из {sol['local_candidates']} локальных кандидатов остаются вне сопоставления. По явным kc_ids шагов полностью сопоставлены {sol['fully_mapped_steps']} из {sol['steps']} шагов. Это техническая полнота связи, а не оценка содержательной полноты действия.",
        f"В смешанных 247 полностью сопоставлены {mix['fully_mapped_steps']} из {mix['steps']} шагов. Частоты семейств описывают только сопоставленную часть; новые кандидаты не сливаются с каталогом.", '',
        'Разные семейства не означают независимые методы или разные когнитивные действия. Маскирование чисел может объединить задачи с разными математическими случаями; разные формулировки и рисунки могут разделить один метод. SHA рисунков сохраняется в ключе: даже близкие изображения остаются разными группами. Без предметной проверки число семейств не является числом независимых упражнений.', '',
        'Для будущего тьютора KC с одной-двумя группами — кандидаты на проверку разнообразия условий и поиск других шаблонов в сохранённом банке. Высокая частота задач при повторении группы обосновывает проверку дефицита переноса, но не доказывает его. Даже ≥3 семейства не гарантируют пригодность упражнений. Нужны предметная проверка групп и проверенные решения; данные не измеряют освоение ученика, трудность или эффект подсказок.', '',
        'Полные частоты, ID задач/семейств и крупные разделы КЭС находятся в kc-family-frequency.csv; связи — в kc-task-family-links.csv; полнота сопоставления и происхождение — в tasks.csv. КЭС — метка источника, не KC. Скрипт запускается из корня: `.venv/Scripts/python.exe scripts/fipi_kc_family_coverage.py report`; `smoke` повторяет инварианты без записи.']
    (OUT/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    (OUT/'code').mkdir(exist_ok=True)
    hashes=dict(data['input_hashes'])
    for name in ('fipi_kc_family_coverage.py','fipi_domain_quality.py'):
        p=ROOT/'scripts'/name;hashes[p.relative_to(ROOT).as_posix()]=domain.sha(p)
    for path in sorted(hashes):
        if path.startswith('scripts/'):
            shutil.copyfile(ROOT/path,OUT/'code'/Path(path).name)
    dump(OUT/'provenance.json', dict(input_hashes=hashes,input_digest=hashlib.sha256(json.dumps(hashes,sort_keys=True).encode()).hexdigest(),collector_digest=data['input_digest'],method='numeric DOM/MathML/image SHA families; mapping report.mapping; harmonized247',code_snapshot='code/'))
    dump(OUT/'smoke.json',dict(unique_selected=250,harmonized_included=247,source_policy_included=248,sol_unmatched_tasks=44,frequency_bounds=True,unique_task_kc_edges=True,catalog_bins_sum=True))
    dump(OUT/'output-hashes.json',{p.relative_to(OUT).as_posix():domain.sha(p) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='output-hashes.json'})
    print(json.dumps(summary,ensure_ascii=False,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=['report','smoke']);a=p.parse_args()
    if a.command=='report':build()
    else:
        summary,*_=analyze(checkpoint.collect(strict=True));print(json.dumps(summary,ensure_ascii=False,indent=2))
