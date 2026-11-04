"""Execution provenance only; does not make mathematical or KC decisions."""
import sys,json,hashlib,subprocess
from pathlib import Path
from datetime import datetime,timezone
RUN=Path(__file__).resolve().parent
ROOT=RUN.parents[3]
def now(): return datetime.now(timezone.utc).isoformat()
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,d):
 p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
action,role,tid=sys.argv[1:4]
rec=RUN/'executions'/f'{role}-{tid}.json'
req=RUN/'requests'/('author' if role=='author' else 'auditor-v1.1')/(tid+'.txt')
raw=RUN/'raw'/role/(tid+'.json')
if action=='start':
 assert not rec.exists() and not raw.exists()
 inp=json.loads((RUN/'inputs/tasks'/(tid+'.json')).read_text(encoding='utf-8'))
 images=[RUN/'inputs'/a['path'] for a in inp['assets']]
 msg=f"Роль: {role}. Прочитай только запрос {req.as_posix()} и перечисленные в нём image_files; каждое изображение открой через view_image. Следуй полной инструкции запроса. Другие файлы, решения, каталоги вне запроса, история и сеть запрещены. Нельзя запускать агентов. Сохрани ровно один точный JSON без markdown в {raw.as_posix()}; создай родительскую папку при необходимости, файл создавать только если отсутствует, не перезаписывать. После сохранения сообщи путь и фактически просмотренные image_files. Не изменяй иных файлов."
 d={'role':role,'task_id':tid,'spawn_message':msg,'agent_id':None,'start_utc':now(),'end_utc':None,'request':{'path':str(req.relative_to(ROOT)).replace('\\','/'),'sha256':sha(req)},'passed_image_paths':[{'path':str(p),'sha256':sha(p)} for p in images],'raw_path':str(raw.relative_to(ROOT)).replace('\\','/'),'fork_turns':'none','model':'unknown inherited','paid_api':False,'mechanism':'collaboration.spawn_agent; actual context launch, not API log'}
 write(rec,d); print(msg)
elif action=='attach':
 d=json.loads(rec.read_text(encoding='utf-8'));d['agent_id']=sys.argv[4];write(rec,d)
elif action=='finish':
 d=json.loads(rec.read_text(encoding='utf-8'));d['end_utc']=now();d['raw_sha256']=sha(raw) if raw.exists() else None;d['completion_message']=sys.argv[4] if len(sys.argv)>4 else '';write(rec,d)
 if role=='author':
  cmd=[str(ROOT/'.venv/Scripts/python.exe'),'-c',"import sys,json;sys.path.insert(0,'scripts');from fipi_extension import validate_one;d=json.load(open(sys.argv[1],encoding='utf-8'));validate_one(d);assert d['task_id']==sys.argv[2];print(json.dumps({'task_id':d['task_id'],'status':'technical_pass'}))",str(raw),tid]
 else: cmd=[str(ROOT/'.venv/Scripts/python.exe'),'scripts/fipi_extension.py','validate-audit','--task',tid,'--path',str(raw.relative_to(ROOT))]
 p=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True,encoding='utf-8');write(RUN/'validations'/f'{role}-{tid}.json',{'command':cmd,'returncode':p.returncode,'stdout':p.stdout,'stderr':p.stderr,'at_utc':now()}); print(p.stdout or p.stderr);sys.exit(p.returncode)
elif action=='batch':
 ids=json.loads((RUN/'selection.json').read_text(encoding='utf-8'))['batches'][int(tid)-1]['task_ids'];records=[]
 for t in ids:
  for r in ['author','auditor']:
   p=RUN/'executions'/f'{r}-{t}.json';v=RUN/'validations'/f'{r}-{t}.json';assert json.loads(v.read_text(encoding='utf-8'))['returncode']==0;records.append({'execution_path':str(p.relative_to(RUN)),'sha256':sha(p),'execution':json.loads(p.read_text(encoding='utf-8'))})
 active=json.loads((RUN/'active-attempts.json').read_text(encoding='utf-8')) if (RUN/'active-attempts.json').exists() else {}
 corrections=[]
 for t in ids:
  for role in ['author','auditor']:
   if t not in active or role not in active[t]:continue
   raw=RUN/active[t][role];stem=raw.stem;p=RUN/'executions'/(stem+'.json');v=RUN/'validations'/(stem+'.json');assert json.loads(v.read_text(encoding='utf-8'))['returncode']==0;corrections.append({'execution_path':str(p.relative_to(RUN)),'sha256':sha(p),'execution':json.loads(p.read_text(encoding='utf-8'))})
 dest=RUN/f'batch-execution-{int(tid):02d}.json';assert not dest.exists()
 write(dest,{'batch':int(tid),'completed_at':now(),'tasks':ids,'executions':records,'correction_executions':corrections,'active_attempts':{t:active[t] for t in ids if t in active},'technical_validation':'passed','mathematical_correctness':'not established by coordinator','next_batch':'await root health and GO'})
