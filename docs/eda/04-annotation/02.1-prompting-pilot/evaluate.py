import json, hashlib, difflib, itertools, statistics
from pathlib import Path

ROOT = Path(__file__).parent
RAW = ROOT / 'raw'
OUT = ROOT / 'evaluation'
OUT.mkdir(exist_ok=True)
(ROOT / 'resolved_prompts').mkdir(exist_ok=True)

# Manual semantic matching by mathematical operation, never by numerical answer.
# Compound candidates are retained as compounds rather than silently split.
semantic = {}
for v in 'ABC':
    for r in range(1, 4):
        semantic[f'{v}_1_{r}'] = ['BISECTOR', 'TRIANGLE_ANGLES']
        semantic[f'{v}_4_{r}'] = ['DISJOINT_PROBABILITY']
semantic.update({
 'A_10_1':['VARIABLE_RELATION','MASS_BALANCE','LINEAR_EQUATION','TOTAL_MASS'],
 'A_10_2':['VARIABLE_RELATION','MASS_BALANCE','LINEAR_EQUATION','TOTAL_MASS'],
 'A_10_3':['MASS_BALANCE','LINEAR_EQUATION','TOTAL_MASS'],
 'B_10_1':['MASS_BALANCE','LINEAR_EQUATION','TOTAL_MASS'],
 'B_10_2':['MASS_BALANCE','LINEAR_EQUATION','TOTAL_MASS'],
 'B_10_3':['MASS_BALANCE','LINEAR_EQUATION','TOTAL_MASS'],
 'C_10_1':['FRACTION_MASS','MASS_BALANCE','LINEAR_EQUATION','TOTAL_MASS'],
 'C_10_2':['VARIABLE_RELATION','MASS_BALANCE','LINEAR_EQUATION','TOTAL_MASS','VERIFY_MODEL'],
 'C_10_3':['VARIABLE_RELATION','MASS_BALANCE','LINEAR_EQUATION','TOTAL_MASS','VERIFY_MODEL'],
 'A_14_1':['MIDLINE','SECTION','PYTHAGORAS','PLANE','DISTANCE'],
 'A_14_2':['COORDINATES','PLANE','SECTION','TRAPEZOID','DISTANCE'],
 'A_14_3':['COORDINATES','PLANE','SECTION','PARALLEL','LENGTH','DISTANCE'],
 'B_14_1':['COORDINATES_AND_PLANE','SECTION','PARALLEL','LENGTH','DISTANCE'],
 'B_14_2':['COORDINATES_AND_PLANE','SECTION','PARALLEL_AND_LENGTH','DISTANCE'],
 'B_14_3':['COORDINATES_AND_PLANE','SECTION','TRAPEZOID','DISTANCE'],
 'C_14_1':['COORDINATES','PLANE','SECTION','LENGTH','DISTANCE'],
 'C_14_2':['COORDINATES','PLANE','SECTION','TRAPEZOID','DISTANCE'],
 'C_14_3':['COORDINATES','PARALLEL','DISTANCE'],
 'A_19_1':['CONSTRUCT','DIGIT_SUM','MOD9_AND_DIGIT_BOUND','CARRY','LOWER_BOUND','ATTAIN'],
 'A_19_2':['CONSTRUCT','MOD9','CARRY','ENUMERATE','SUM'],
 'A_19_3':['CONSTRUCT','MOD9','CARRY','ENUMERATE','COMPARE_CASES'],
 'B_19_1':['CONSTRUCT','DIGIT_SUM','DIGIT_SUM_CARRIES','CARRY','ENUMERATE','COMPARE_CASES'],
 'B_19_2':['DIGIT_SUM','CARRY','ENUMERATE','COMPARE_CASES'],
 'B_19_3':['CONSTRUCT','MOD9','ENUMERATE','GAP_LOWER_BOUND'],
 'C_19_1':['CONSTRUCT','MOD9','ENUMERATE','COMPARE_CASES'],
 'C_19_2':['CONSTRUCT','MOD9','CARRY','ENUMERATE','COMPARE_CASES'],
 'C_19_3':['CONSTRUCT','MOD9','ENUMERATE','GAP_LOWER_BOUND'],
})

notes = {}
def add(run, kind, text):
    notes.setdefault(run, []).append({'kind':kind, 'note':text})

for run in ['A_19_1','A_19_2']:
    add(run,'math_wrong_final','Пункт в: 1111111 вместо 231; минимум суммы цифр подменяет минимум суммы чисел.')
add('A_14_3','math_wrong_final','Пункт б: знаменатель sqrt(19) заменён на sqrt(76) без изменения числителя; ответ уменьшен вдвое.')
add('C_14_3','math_wrong_final','Ложно утверждается C1∈α: подстановка даёт -4√3, а не 0; неверное сечение и ложное объявление опечатки.')
for run in ['A_14_2','A_14_3','B_14_1','B_14_2','B_14_3','C_14_2','C_14_3']:
    add(run,'math_scope_gap','Пункт а доказывается только при a=h=4; условие о длине 4 относится к пункту б. Произвольные размеры не рассмотрены.')
add('A_19_1','math_proof_gap','Пункт б: обещанный разбор единственного переноса не выполнен; в формулировках допускается сумма двух цифр 19.')
add('A_19_2','math_false_reasoning','Пункт б: утверждение о необходимом переносе из десятков неверно; вместо него нужно исключить такой перенос.')
add('B_19_1','math_proof_gap','Пункт в: нижняя оценка для всех d>=9 объявлена без обоснования; warning второго этапа замечает пробел, но статус остаётся solved.')
add('B_19_2','math_false_reasoning','Пункт в: минимум при d=5 указан как 309 вместо 269; общее утверждение о монотонности списков не доказано.')
add('B_19_2','math_proof_gap','Пункт в: значения для d<=5 не раскрыты списками; нижняя оценка для d>=7 не доказана.')
add('B_19_3','math_false_reasoning','Пункт б: 599 приписана сумма цифр 25 (на деле 23); чисел <=599 с суммой цифр 25 нет.')
add('B_19_3','math_proof_gap','Пункт б: отсутствие пары при d=16 объявлено итогом просмотра без полного списка или доказательства.')
add('C_19_1','math_proof_gap','Пункт б не доведён до ответа; пункт в не даёт убедительного полного доказательства нижней оценки.')
add('C_19_2','math_false_reasoning','Пункт в: пропущено 200 в семи минимальных числах с d=2, ошибочно получено 2255; множество чисел с d>=10 перечислено неверно. В б пропущены двузначные числа с суммой цифр 16.')
add('C_19_3','math_false_reasoning','Пункт б: удвоенный остаток по модулю 9 ошибочно назван всегда чётным; например, 2*7≡5 (mod 9).')

# Granularity: count per result, not per individual merged operation.
# Introducing a variable as part of building a model is accepted. Combining
# coordinate setup with plane construction is counted because each is a
# separately reusable geometric operation in this pilot.
for v in 'ABC':
    for r in range(1,4):
        add(f'{v}_19_{r}','step_merged','По одному Step на пункт: несколько содержательных действий (ограничение, перебор, оценка, конструкция) слиты.')
for v in 'AB':
    for r in range(1,4):
        add(f'{v}_14_{r}','step_merged','Введение координат и вывод уравнения плоскости слиты; в части ответов также слиты построение сечения и доказательство свойств.')
add('C_14_3','step_merged','В один Step слиты координаты, плоскость, сечение и проверка параллельности.')
add('B_10_1','step_merged','Решение уравнения и вычисление искомой общей массы слиты в s2.')
add('C_10_3','step_merged','Вычисление массы и самостоятельная проверка концентрации слиты в s3.')
for r in range(1,4):
    add(f'B_14_{r}','kc_compound','Один KC объединяет выбор координат и построение уравнения плоскости; в B_14_2 дополнительно слиты параллельность и длина.')
add('A_14_2','kc_name_unspecific','Пять названий KC состоят из одного глагола: Задавать, Определять, Исследовать, Доказывать, Вычислять; описания содержательнее названий.')
add('C_10_1','kc_name_mismatch','k1 назван выражением массы смеси, но описывает массу вещества как доля×масса компонента.')
add('C_14_3','kc_missing','В s1 есть вывод уравнения плоскости и построение сечения, но соответствующих KC нет; это независимо от неправильного сечения.')
add('A_10_1','method_fragment','Метод сложения масс выделен отдельно как элементарная операция вместо завершения метода материального баланса.')
for r in range(1,4):
    add(f'B_14_{r}','method_dependency','Method расстояния ссылается только на вычисление, не включает Step, задающий используемую плоскость; зависимость остаётся неявной.')
for run in ['A_19_1','B_19_1']:
    add(run,'status_overconfident','solved при warnings о незавершённом доказательстве.')

borderline = {
 'A_14_1':'Общий аргумент через равные катеты восстанавливается из текста и свойств правильной призмы; затем автор лишне подставляет 4. Принято с оговоркой, не включено в строгие пропуски общности.',
 'A_19_3':'Пункт в верен, но оценку d>=10 лучше раскрыть через минимальное число >=19 и шаг >=9. Принято как краткий верный аргумент; при максимально строгом требовании явного вывода это minor proof gap.',
 'C_14_1':'Один Method на оба пункта принят: это общий координатный способ с общей подготовкой, а не случайное объединение независимых действий.',
 'C_10_2':'Проверка концентрации необязательна после равносильного решения, но содержательна и проверяема; избыточностью не штрафуется.',
}

def parse_for_review(f):
    try: return json.loads(f.read_text()), None
    except json.JSONDecodeError as exc:
        if f.stem == 'C_19_2':
            # Evaluation-only view; raw file is never overwritten.
            fixed=f.read_text().replace('нельзя."\n      "kc_ids"', 'нельзя.",\n      "kc_ids"')
            (OUT/'C_19_2.review_only.json').write_text(fixed)
            return json.loads(fixed),str(exc)
        raise

records=[]
prompt_audit=[]
for v,p,r in itertools.product('ABC',[1,4,10,14,19],range(1,4)):
    run=f'{v}_{p}_{r}'
    f=RAW/f'{run}.txt'
    d,parse_error=parse_for_review(f)
    structural=[]
    if not isinstance(d['task_id'],str):structural.append('task_id type')
    for field in ['steps','kc_candidates','methods','warnings']:
        if not isinstance(d[field],list):structural.append(field+' type')
    if set(d)!=set(['task_id','solution_status','steps','kc_candidates','methods','warnings']): structural.append('root keys')
    if d['task_id']!=json.loads((ROOT/'inputs'/f'{p}.json').read_text())['task_id']:structural.append('task_id')
    if d['solution_status'] not in ['solved','partial','unsolved']:structural.append('status enum')
    for field,keys in [('steps',{'id','action','result','kc_ids'}),('kc_candidates',{'id','name','description'}),('methods',{'id','name','step_ids'})]:
        ids=[x['id'] for x in d[field]]
        if len(ids)!=len(set(ids)):structural.append('duplicate '+field)
        if any(set(x)!=keys for x in d[field]):structural.append('keys '+field)
        for obj in d[field]:
            for key in keys:
                if key in ['kc_ids','step_ids']:
                    if not isinstance(obj[key],list) or not all(isinstance(value,str) for value in obj[key]):structural.append(field+'.'+key+' type')
                elif not isinstance(obj[key],str) or not obj[key].strip():structural.append(field+'.'+key+' type')
    kset={k['id'] for k in d['kc_candidates']};sset={s['id'] for s in d['steps']}
    if any(not s['kc_ids'] or not set(s['kc_ids'])<=kset for s in d['steps']):structural.append('KC links')
    if any(not m['step_ids'] or not set(m['step_ids'])<=sset for m in d['methods']):structural.append('Step links')
    if set(k for s in d['steps'] for k in s['kc_ids'])!=kset:structural.append('unused KCs')
    si={s['id']:i for i,s in enumerate(d['steps'])}
    if any([si[s] for s in m['step_ids']]!=sorted(si[s] for s in m['step_ids']) for m in d['methods']):structural.append('Method order')
    if set(s for m in d['methods'] for s in m['step_ids'])!=sset:structural.append('uncovered steps')
    if not all(isinstance(w,str) for w in d['warnings']):structural.append('warning types')
    if v=='B':
        first=json.loads((RAW/f'{run}.stage1.txt').read_text())
        if [{k:s[k] for k in ['id','action','result']} for s in first['steps']] != [{k:s[k] for k in ['id','action','result']} for s in d['steps']]:structural.append('B mutated steps')
    if parse_error:add(run,'json_invalid',parse_error)
    assert len(semantic[run])==len(d['kc_candidates']),run
    mapping=[{'id':k['id'],'name':k['name'],'canonical':label} for k,label in zip(d['kc_candidates'],semantic[run])]
    for stage,filename in ((['B1',run+'.stage1'],['B2',run]) if v=='B' else [(v,run)]):
        expected=(ROOT/'prompts'/f'{stage}.txt').read_text().replace('{task_json}',(ROOT/'inputs'/f'{p}.json').read_text())
        if stage=='B2':expected=expected.replace('{stage1_raw}',(RAW/f'{run}.stage1.txt').read_text())
        (ROOT/'resolved_prompts'/f'{filename}.txt').write_text(expected)
        logged=(RAW/f'{filename}.prompt.txt').read_text()
        diff=''.join(difflib.unified_diff(expected.splitlines(True),logged.splitlines(True),fromfile='resolved',tofile='agent_written_log'))
        prompt_audit.append({'name':filename,'stage':stage,'equal':expected==logged,'diff':diff})
    ns=notes.get(run,[])
    rec={'run_id':run,'variant':v,'position':p,'repeat':r,'raw_sha256':hashlib.sha256(f.read_bytes()).hexdigest(),'json_valid':not parse_error,'structural_errors':structural,'steps':len(d['steps']),'kcs':len(d['kc_candidates']),'methods':len(d['methods']),'status':d['solution_status'],'math_acceptable':not any(n['kind'].startswith('math_') for n in ns),'notes':ns,'borderline':borderline.get(run),'kc_mapping':mapping}
    records.append(rec)

(OUT/'reviews.json').write_text(json.dumps(records,ensure_ascii=False,indent=2))
(OUT/'prompt_log_audit.json').write_text(json.dumps(prompt_audit,ensure_ascii=False,indent=2))
stability=[]
for v,p in itertools.product('ABC',[1,4,10,14,19]):
    rs=[x for x in records if x['variant']==v and x['position']==p]
    valid=[x for x in rs if x['json_valid']]
    pairs=[]
    for a,b in itertools.combinations(valid,2):
        ka=set(semantic[a['run_id']]);kb=set(semantic[b['run_id']]);pairs.append({'a':a['run_id'],'b':b['run_id'],'jaccard':len(ka&kb)/len(ka|kb)})
    stability.append({'variant':v,'position':p,'steps':[x['steps'] for x in rs],'kcs':[x['kcs'] for x in rs],'method_counts':[x['methods'] for x in rs],'valid_pairs':pairs,'mean_jaccard':statistics.mean(x['jaccard'] for x in pairs)})
(OUT/'stability.json').write_text(json.dumps(stability,ensure_ascii=False,indent=2))
summary=[]
for v in 'ABC':
    rs=[x for x in records if x['variant']==v]
    kinds=sorted({n['kind'] for x in rs for n in x['notes']})
    summary.append({'variant':v,'completed':len(rs),'json_valid':sum(x['json_valid'] for x in rs),'structurally_valid_raw':sum(x['json_valid'] and not x['structural_errors'] for x in rs),'math_acceptable':sum(x['math_acceptable'] for x in rs),'error_counts':{k:sum(any(n['kind']==k for n in x['notes']) for x in rs) for k in kinds},'mean_steps':statistics.mean(x['steps'] for x in rs),'mean_kcs':statistics.mean(x['kcs'] for x in rs),'jaccard_macro_mean':statistics.mean(s['mean_jaccard'] for s in stability if s['variant']==v)})
(OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
print(json.dumps(summary,ensure_ascii=False,indent=2))
print('Structural errors:',[(x['run_id'],x['structural_errors']) for x in records if x['structural_errors']])
print('Prompt logs differing:',sum(not x['equal'] for x in prompt_audit),'of',len(prompt_audit))
print('Stability:',[(s['variant'],s['position'],round(s['mean_jaccard'],3),s['steps'],s['kcs']) for s in stability])
