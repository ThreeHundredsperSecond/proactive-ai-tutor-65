"""Readable views and plots made only from saved inputs and derived tables."""
import csv
import html
import json
from pathlib import Path

from annotation_pipeline import read, sha, write


def rows(run, name):
    with (Path(run) / 'derived' / f'{name}.csv').open(encoding='utf-8', newline='') as f:
        return list(csv.DictReader(f))


def html_table(records, columns=None):
    if not records:
        return '<p>Данных пока нет.</p>'
    columns = columns or list(records[0])
    cell = lambda v: html.escape(str(v))
    return '<table><thead><tr>' + ''.join(f'<th>{cell(c)}</th>' for c in columns) + '</tr></thead><tbody>' + ''.join(
        '<tr>' + ''.join(f'<td>{cell(r.get(c, ""))}</td>' for c in columns) + '</tr>' for r in records) + '</tbody></table>'


def compare_html(run, position):
    run=Path(run); manifest=read(run/'manifest.json')
    task=next(t for t in manifest['tasks'] if t['position']==position)
    contents=[]
    for job in manifest['jobs']:
        if job['task_id']!=task['task_id']: continue
        raw=run/job['raw_path']; chunks=[f'<h3>Повтор {job["repeat"]}</h3>']
        if not raw.exists(): chunks.append('<p>Ответ ещё не сохранён.</p>')
        else:
            try: d=read(raw)
            except (ValueError,UnicodeError): chunks.append('<pre>'+html.escape(raw.read_text(encoding='utf-8',errors='replace'))+'</pre>')
            else:
                if not isinstance(d,dict): chunks.append('<p>JSON не является объектом.</p>')
                else:
                    chunks.append('<p>Статус агента: '+html.escape(str(d.get('solution_status')))+'; это самооценка.</p>')
                    for title,field in [('Шаги','steps'),('KC','kc_candidates'),('Методы','methods')]:
                        chunks.append('<h4>'+title+'</h4>')
                        value=d.get(field,[])
                        chunks.append(html_table(value) if isinstance(value,list) and all(isinstance(v,dict) for v in value) else '<p>Повреждённая структура.</p>')
                    chunks.append('<p>Warnings: '+html.escape(str(d.get('warnings',[])))+'</p>')
        chunks.append('<p>Источник: '+html.escape(job['raw_path'])+'</p>')
        contents.append('<td style="vertical-align:top;width:33%;padding:12px">'+''.join(chunks)+'</td>')
    return '<div style="overflow:auto"><table><tr>'+''.join(contents)+'</tr></table></div>'


def plots(run):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams['svg.hashsalt']='annotation-report'
    run=Path(run); out=run/'derived'; status=rows(run,'status'); summary=read(out/'summary.json')
    created=[]
    def save(fig,name,source):
        fig.tight_layout(); path=out/f'{name}.svg'
        fig.savefig(path,metadata={'Date':None})
        png=out/f'{name}.png'; fig.savefig(png,dpi=140,metadata={'Software':'annotation_report.py'})
        plt.close(fig)
        created.append({'file':path.name,'sha256':sha(path),'source':source,
                        'png_file':png.name,'png_sha256':sha(png),
                        'source_sha256':sha(out/source),'report_code_sha256':sha(__file__)})
    fig,ax=plt.subplots(figsize=(8,4))
    names=['Ожидается','Сохранено','JSON','Структура','Просмотр\nматематики']
    values=[summary[k] for k in ['expected','present','json_valid','structure_valid','math_reviewed']]
    ax.bar(names,values); ax.set_ylim(0,max(values+[1])*1.15); ax.set_ylabel('Ответы')
    ax.set_title('Полнота запуска и предварительная проверка')
    save(fig,'run-status','summary.json')
    valid=[s for s in status if s['structure_valid']=='True']
    positions={t['task_id']:t['position'] for t in read(run/'manifest.json')['tasks']}
    fig,axes=plt.subplots(1,3,figsize=(13,4))
    for ax,key in zip(axes,['steps','kcs','methods']):
        grouped={tid:[int(s[key]) for s in valid if s['task_id']==tid] for tid in dict.fromkeys(s['task_id'] for s in status)}
        labels=[tid for tid,values in grouped.items() if values]
        if labels:
            ax.boxplot([grouped[t] for t in labels],tick_labels=[positions[t] for t in labels])
            ax.tick_params(axis='x',rotation=90,labelsize=7)
        ax.set_title(key+' на ответ'); ax.set_ylabel('Количество'); ax.set_xlabel('Позиция задачи')
    save(fig,'response-structure','status.csv')
    stability=[s for s in rows(run,'stability_summary') if s['mean_jaccard']!='']
    if stability:
        fig,ax=plt.subplots(figsize=(10,4))
        ax.bar([str(s['position']) for s in stability],[float(s['mean_jaccard']) for s in stability])
        ax.set_ylim(0,1.05); ax.set_ylabel('Средний попарный Jaccard'); ax.set_xlabel('Позиция задачи')
        ax.set_title('Сходство KC при черновом сопоставлении; статусы проверки — в CSV')
        save(fig,'kc-stability','stability_summary.csv')
    elif (out/'kc-stability.svg').exists(): (out/'kc-stability.svg').unlink()
    frequency=rows(run,'kc_frequency')
    if frequency:
        frequency=sorted(frequency,key=lambda r:int(r['distinct_tasks_any_accepted_repeat']),reverse=True)[:25]
        import textwrap
        fig,ax=plt.subplots(figsize=(13,max(5,len(frequency)*.52)))
        labels=[textwrap.fill(r['name'],width=55) for r in frequency]
        ax.barh(list(range(len(frequency))),[int(r['distinct_tasks_any_accepted_repeat']) for r in frequency][::-1])
        ax.set_yticks(list(range(len(frequency))),labels[::-1],fontsize=8)
        ax.set_xlabel('Разные задачи, объединение принятых повторов'); ax.set_title('Частоты черновых кандидатов KC (первые 25)')
        ax.set_xticks(range(max(int(r['distinct_tasks_any_accepted_repeat']) for r in frequency)+1))
        save(fig,'kc-frequency','kc_frequency.csv')
    elif (out/'kc-frequency.svg').exists():
        (out/'kc-frequency.svg').unlink()
    write(out/'figures.json',created)
    return created


def report(run):
    """Portable HTML with all statements and all repeats; no remote resources."""
    import base64
    run=Path(run); m=read(run/'manifest.json')
    body=['<h1>19 задач × 3 повтора: исходные разборы</h1>',
          '<p>Условия и ответы агентов. Самооценка solved не означает математическую проверку. '
          'Рецензии и семантическое сопоставление KC сохраняются отдельно.</p>',
          html_table(rows(run,'status'),['task_id','repeat','structure_valid','steps','kcs','methods','math_status','annotation_status'])]
    for task in m['tasks']:
        payload=read(run/'inputs'/f'{task["task_id"]}.json')
        body.append(f'<h2 id="task-{task["position"]}">Задача {task["position"]} · {task["task_id"]}</h2>')
        body.append('<p>'+html.escape(payload['statement'])+'</p>')
        for image in task['images']:
            encoded=base64.b64encode((run/image['path']).read_bytes()).decode('ascii')
            body.append('<img style="max-width:100%;max-height:400px" alt="Изображение условия" src="data:image/png;base64,'+encoded+'">')
        body.append(compare_html(run,task['position']))
        review=run/'reviews'/f'{task["task_id"]}.json'
        if review.exists():
            body.append('<details><summary>Рецензия</summary><pre>'+html.escape(review.read_text(encoding='utf-8'))+'</pre></details>')
        else: body.append('<p>Содержательная проверка: рецензия ещё не сохранена.</p>')
    content='<!doctype html><html lang="ru"><meta charset="utf-8"><title>Разбор задач</title><style>body{font:16px/1.5 system-ui;max-width:1700px;margin:32px auto;padding:20px}table{border-collapse:collapse;width:100%}td,th{border:1px solid #ddd;padding:6px;text-align:left;overflow-wrap:anywhere}h2{border-top:3px solid #aaa;padding-top:25px}pre{white-space:pre-wrap}</style>'+''.join(body)+'</html>'
    target=run/'derived/review.html'; target.write_bytes(content.encode('utf-8'))
    write(run/'derived/report-provenance.json',{'report_sha256':sha(target),'report_code_sha256':sha(__file__),
          'analysis_provenance_sha256':sha(run/'derived/provenance.json')})
    return target
