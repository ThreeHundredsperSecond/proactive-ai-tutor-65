"""Prepare a frozen, coverage-oriented 50-task pilot; validate saved annotations.

No model/API calls. Annotation is authored by the primary assistant in the current
conversation; requests record intended inputs, not isolated API executions.
"""
import argparse
import hashlib
import json
import shutil
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
BANK=ROOT/'data/fipi/2026-10-31-profile'
RUN=ROOT/'data/annotation/runs/2026-10-31-fipi-50x1'
SEED='2026-10-31-eda50-v1'
BASELINE=ROOT/'docs/eda/04-annotation/02.1-prompting-pilot/prompts/A.txt'


def digest(data):return hashlib.sha256(data).hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def write(p,value):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def metadata(r,label):return [v for m in r['metadata'] if m['label']==label for v in m['values']]
def stratum(r):return metadata(r,'КЭС:')[0].split()[0],metadata(r,'Тип ответа:')[0]
def rank(r):return digest((SEED+'|'+r['id']).encode())


PROMPT='''EDA-50-v1. Самостоятельно реши одну задачу по приложенному условию и изображениям.
Не обращайся к готовым ответам, внешним решениям и чужим разметкам. Не выдумывай
информацию, которую нельзя прочитать на рисунке. Если обоснования не хватает,
сохрани partial/unsolved и конкретную причину. Никаких независимых повторов.

Основа — сохранённый промпт A, с явно отдельной адаптацией к этому пилоту.
Step — содержательное математическое действие с проверяемым результатом.
Не выделяй чтение и запись ответа в шаги. Не дроби арифметику внутри действия.
Решение линейного уравнения с числовыми коэффициентами — одно действие;
построение уравнения по ситуации и приведение нелинейного к линейному — отдельно.
Охвати все пункты; сохраняй ОДЗ, условия теорем, ограничения и полноту ответа.
В input_refs укажи condition и/или более ранние шаги, откуда доступен нужный вход.

KC — кандидат переиспользуемого действия, а не тема и не вся задача. Название
начинается с глагола; описание задаёт вход, операцию и границу применения.
Не включай конкретные числа и имена точек в определение. Один KC может быть
связан с несколькими шагами, шаг — с несколькими KC. Выделяй только использованное.
Не требуется максимальное дробление. Межзадачные соответствия будут отдельной
редакторской операцией после решения, с явными определениями и свидетельствами.

Method — стратегия с упорядоченными шагами, отдельно для независимых пунктов,
если нет общего метода. Не перечисляй неиспользованные альтернативы.

JSON: task_id, solution_status (solved|partial|unsolved), answer (строка),
steps [{id,action,result,kc_ids,input_refs}],
kc_candidates [{id,name,description}], methods [{id,name,step_ids}], warnings [].
Неиспользованных KC, пустых методов и несуществующих ссылок быть не должно.
Это предварительная предметная интерпретация, не эталон и не оценка ученика.
'''


def prepare():
    if (RUN/'manifest.json').exists():raise RuntimeError('Frozen run already exists; do not resample')
    records=[json.loads(x) for x in (BANK/'tasks.jsonl').read_text(encoding='utf-8').splitlines()]
    groups=defaultdict(list)
    for r in records:
        if not r['source_issues']:groups[stratum(r)].append(r)
    quotas={s:1 for s in groups}
    while sum(quotas.values())<50:
        s=max((s for s in groups if quotas[s]<len(groups[s])),key=lambda s:(len(groups[s])/(quotas[s]+1),s))
        quotas[s]+=1
    chosen=[r for s in sorted(groups) for r in sorted(groups[s],key=rank)[:quotas[s]]]
    # First two probes have different representations; chosen set is unchanged.
    first=min((r for r in chosen if r['assets'] and stratum(r)[1]=='Краткий ответ'),key=rank)
    second=next(r for r in chosen if stratum(r)==('2.4','Краткий ответ'))
    rest=sorted((r for r in chosen if r['id'] not in {first['id'],second['id']}),key=rank)
    ordered=[first,second]+rest
    (RUN/'prompt.txt').parent.mkdir(parents=True,exist_ok=True)
    (RUN/'prompt.txt').write_text(PROMPT,encoding='utf-8')
    shutil.copyfile(BASELINE,RUN/'baseline-A.txt')
    entries=[]
    for n,r in enumerate(ordered,1):
        frozen=dict(r)
        for a in frozen['assets']:
            source=BANK/a['path'];dest=RUN/'inputs'/a['path']
            dest.parent.mkdir(parents=True,exist_ok=True)
            if not dest.exists():shutil.copyfile(source,dest)
            assert digest(dest.read_bytes())==a['sha256']
        write(RUN/'inputs/tasks'/f'{r["id"]}.json',frozen)
        body={'task_id':r['id'],'instruction':r['instruction'],'statement_html':r['statement_html'],
              'images':[{'path':str((RUN/'inputs'/a['path']).resolve()),'sha256':a['sha256']} for a in r['assets']]}
        request=PROMPT+'\nВХОД:\n'+json.dumps(body,ensure_ascii=False,indent=2)+'\n'
        req=RUN/'requests'/f'{r["id"]}.txt';req.parent.mkdir(parents=True,exist_ok=True)
        req.write_text(request,encoding='utf-8')
        entries.append(dict(order=n,task_id=r['id'],primary_kes=stratum(r)[0],response_type=stratum(r)[1],
                            all_kes=metadata(r,'КЭС:'),has_images=bool(r['assets']),
                            input_sha256=digest((RUN/'inputs/tasks'/f'{r["id"]}.json').read_bytes()),
                            request_sha256=digest(req.read_bytes()),source_url=r['source_url']))
    m=dict(created_at=datetime.now(timezone.utc).isoformat(),seed=SEED,bank_sha256=digest((BANK/'tasks.jsonl').read_bytes()),
           prompt_sha256=digest((RUN/'prompt.txt').read_bytes()),baseline_sha256=digest(BASELINE.read_bytes()),
           selection='One task per nonempty (primary KES, response type) stratum; extra slots greedily maximize N/(q+1); hash ranking inside stratum.',
           population=len(records),eligible=len(records)-sum(bool(r['source_issues']) for r in records),
           strata=[dict(primary_kes=s[0],response_type=s[1],bank_n=len(groups[s]),sample_n=quotas[s]) for s in sorted(groups)],
           inference_scope='Coverage-oriented development sample; unweighted pilot frequencies do not estimate bank frequencies.',
           execution='Primary assistant, single shared conversation; no isolated contexts, no API client or independent repeats.',
           batches=[list(range(1,3))]+[list(range(s,min(s+8,51))) for s in range(3,51,8)],tasks=entries)
    write(RUN/'manifest.json',m)
    print(json.dumps(m,ensure_ascii=False,indent=2))


def validate_one(d):
    assert set(d)=={'task_id','solution_status','answer','steps','kc_candidates','methods','warnings'}
    assert d['solution_status'] in {'solved','partial','unsolved'} and isinstance(d['answer'],str)
    ss=d['steps'];ks=d['kc_candidates'];ms=d['methods']
    sid=[s['id'] for s in ss];kid=[k['id'] for k in ks]
    assert len(sid)==len(set(sid)) and len(kid)==len(set(kid))
    used=set()
    for i,s in enumerate(ss):
        assert set(s)=={'id','action','result','kc_ids','input_refs'}
        assert s['action'].strip() and s['result'].strip() and s['kc_ids']
        assert set(s['kc_ids'])<=set(kid)
        assert s['input_refs'] and set(s['input_refs'])<=({'condition'}|set(sid[:i]))
        used.update(s['kc_ids'])
    assert used==set(kid)
    for k in ks:
        assert set(k)=={'id','name','description'} and k['name'].strip() and k['description'].strip()
    covered=set()
    for m in ms:
        assert set(m)=={'id','name','step_ids'} and m['name'].strip() and m['step_ids']
        assert set(m['step_ids'])<=set(sid)
        assert [sid.index(x) for x in m['step_ids']]==sorted(sid.index(x) for x in m['step_ids'])
        covered.update(m['step_ids'])
    assert covered==set(sid)
    return True


def validate():
    m=read(RUN/'manifest.json')
    assert digest((RUN/'prompt.txt').read_bytes())==m['prompt_sha256']
    assert digest((BANK/'tasks.jsonl').read_bytes())==m['bank_sha256']
    results=[]
    for t in m['tasks']:
        tid=t['task_id']
        assert digest((RUN/'inputs/tasks'/f'{tid}.json').read_bytes())==t['input_sha256']
        assert digest((RUN/'requests'/f'{tid}.txt').read_bytes())==t['request_sha256']
        r=read(RUN/'inputs/tasks'/f'{tid}.json')
        for a in r['assets']:assert digest((RUN/'inputs'/a['path']).read_bytes())==a['sha256']
        raw=RUN/'raw'/f'{tid}.json'
        if raw.exists():
            d=read(raw);assert d['task_id']==tid;validate_one(d)
            results.append(dict(task_id=tid,sha256=digest(raw.read_bytes()),status='technical_pass',solution_status=d['solution_status']))
    write(RUN/'technical-validation.json',dict(expected=50,present=len(results),responses=results))
    print('Technically valid:',len(results),'/ 50')


def show(start,end):
    from lxml import html
    m=read(RUN/'manifest.json')
    for t in m['tasks'][start-1:end]:
        r=read(RUN/'inputs/tasks'/f'{t["task_id"]}.json')
        print('\nTASK',t['order'],r['id'],stratum(r),r['instruction'])
        print(r['statement_html'])
        print('IMAGES',[str((RUN/'inputs'/a['path']).resolve()) for a in r['assets']])


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('command',choices=['prepare','validate','show'])
    p.add_argument('--start',type=int,default=1);p.add_argument('--end',type=int,default=2)
    a=p.parse_args()
    if a.command=='show':show(a.start,a.end)
    else:globals()[a.command]()
