"""Explicit F416AF correction provenance and packet preparation, no semantic edits."""
import sys,json,hashlib,subprocess
from pathlib import Path
from datetime import datetime,timezone
RUN=Path(__file__).resolve().parent;ROOT=RUN.parents[3]
sys.path.insert(0,str(ROOT/'scripts'))
from fipi_extension import read,freeze,validate_one,validate_audit,condition
from prepare_fipi_audit_packet import WRAPPER
def now():return datetime.now(timezone.utc).isoformat()
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def dump(p,d):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
role=sys.argv[2];tid='F416AF';stem=role+'-'+tid+'-a02';raw=RUN/'attempts'/(stem+'.json');req=RUN/'requests/attempts'/(stem+'.txt');rec=RUN/'executions'/(stem+'.json')
if sys.argv[1]=='prepare':
 inp=read(RUN/'inputs/tasks/F416AF.json');images=[RUN/'inputs'/x['path'] for x in inp['assets']]
 if role=='author':
  zoom=RUN/'checks/source-review/F416AF-condition8-zoom.png';assert zoom.exists();images.append(zoom)
  appendix={'correction_type':'source-reading and mathematical recomputation; aided correction, not independent original attempt','reported_discrepancy':'В исходном изображении условия assets/364ae983ef85201947c85da3.gif root прочитал AM=BN=3; первоначальный авторский s1 использовал AM=BN=1. Сам перепроверь оригинальное изображение и пересчитай решение. Контрольный ответ не передаётся.','original_author_response':read(RUN/'raw/author/F416AF.json'),'additional_image_files':[str(zoom)],'zoom_provenance':{'derived_from':'inputs/assets/364ae983ef85201947c85da3.gif','original_sha256':sha(RUN/'inputs/assets/364ae983ef85201947c85da3.gif'),'derivative_path':str(zoom),'derivative_sha256':sha(zoom),'created_by':'root; enlarged white-background rendering'}}
  body=(RUN/'requests/author/F416AF.txt').read_text(encoding='utf-8')+'\nЯВНАЯ КОРРЕКТИРУЮЩАЯ ПОПЫТКА a02:\n'+json.dumps(appendix,ensure_ascii=False,indent=2)+'\nВерни полный исправленный JSON по исходной схеме, сохрани task_id. Предыдущий raw не изменять.\n'
  freeze(RUN/'failures/F416AF-source-reading-a01.json',{'reported_by':'root','type':'source-reading mathematical error missed by first audit','technical_pass_is_not_semantic_success':True,'original_author':{'path':'raw/author/F416AF.json','sha256':sha(RUN/'raw/author/F416AF.json')},'original_auditor':{'path':'raw/auditor/F416AF.json','sha256':sha(RUN/'raw/auditor/F416AF.json')},'discrepancy':appendix['reported_discrepancy'],'correction_authorized_by':'root explicit message 2026-11-03'})
 else:
  author=read(RUN/'attempts/author-F416AF-a02.json');validate_one(author);assert author['task_id']==tid
  data={'task_id':tid,**condition(inp),'author_response':author,'image_files':[str(x) for x in images],'catalog':read(RUN/'catalog-for-auditor.json')}
  refs=['condition']+[f'step:{s["id"]}:{k}' for s in author['steps'] for k in ['action','result']]+['image:'+x['path'] for x in inp['assets']]
  body=(RUN/'auditor-prompt.txt').read_text(encoding='utf-8')+'\nВХОД:\n'+json.dumps(data,ensure_ascii=False,indent=2)+'\n'+WRAPPER+'\n'+json.dumps({'allowed_refs':refs},ensure_ascii=False,indent=2)+'\n'
 freeze(req,body)
 msg=f'Роль: {role}, отдельная попытка a02. Прочитай только запрос {req.as_posix()}. Открой через view_image все image_files и additional_image_files из запроса. Следуй всем его инструкциям. Другие файлы, история, сеть, агенты запрещены. Сохрани один полный JSON без markdown в {raw.as_posix()}, создавай только отсутствующий файл; исходные raw и другие файлы не изменяй. Сообщи путь результата и фактически просмотренные изображения.'
 freeze(rec,{'role':role,'task_id':tid,'attempt':'a02','spawn_message':msg,'start_utc':now(),'agent_id':None,'request':{'path':str(req.relative_to(ROOT)),'sha256':sha(req)},'passed_image_paths':[{'path':str(p),'sha256':sha(p)} for p in images],'raw_path':str(raw.relative_to(ROOT)),'fork_turns':'none','model':'unknown inherited','paid_api':False,'mechanism':'collaboration.spawn_agent; actual context launch, not API log'})
 print(msg)
elif sys.argv[1]=='attach':
 d=read(rec);d['agent_id']=sys.argv[3];dump(rec,d)
elif sys.argv[1]=='finish':
 d=read(rec);d['end_utc']=now();d['raw_sha256']=sha(raw);d['completion_message']=sys.argv[3];dump(rec,d)
 if role=='author':cmd=[str(ROOT/'.venv/Scripts/python.exe'),'-c',"import sys,json;sys.path.insert(0,'scripts');from fipi_extension import validate_one;d=json.load(open(sys.argv[1],encoding='utf-8'));validate_one(d);assert d['task_id']=='F416AF';print('technical_pass F416AF author a02')",str(raw)]
 else:cmd=[str(ROOT/'.venv/Scripts/python.exe'),'scripts/fipi_extension.py','validate-audit','--task',tid,'--path',str(raw.relative_to(ROOT)),'--author-path',str((RUN/'attempts/author-F416AF-a02.json').relative_to(ROOT))]
 p=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True,encoding='utf-8');dump(RUN/'validations'/(stem+'.json'),{'command':cmd,'returncode':p.returncode,'stdout':p.stdout,'stderr':p.stderr,'at_utc':now()});print(p.stdout or p.stderr);sys.exit(p.returncode)
elif sys.argv[1]=='activate':
 p=RUN/'active-attempts.json';active=read(p) if p.exists() else {};before=active.copy();active[tid]={'author':'attempts/author-F416AF-a02.json','auditor':'attempts/auditor-F416AF-a02.json','author_mode':'source_reading_feedback','feedback_ref':'checks/F416AF-source-discrepancy.json'}
 freeze(RUN/'executions/history/active-attempts-F416AF-before-a02.json',before);dump(p,active);freeze(RUN/'executions/history/active-attempts-F416AF-activation-a02.json',{'at_utc':now(),'before':before,'after':active,'reason':'explicit root-authorized source-reading correction; originals preserved'})
