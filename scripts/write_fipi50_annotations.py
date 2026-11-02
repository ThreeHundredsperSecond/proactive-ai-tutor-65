"""Losslessly serialize annotations authored by the primary assistant; no inference."""
from datetime import datetime, timezone
from fipi_eda50 import RUN, digest, read, write, validate_one


def save(tid, answer, steps, kcs, methods=None, warnings=None, status='solved'):
    """Steps: (action,result,[local KC aliases],[input refs]); KC tuples are explicit."""
    aliases={key:f'k{i}' for i,(key,_,_) in enumerate(kcs,1)}
    d=dict(task_id=tid,solution_status=status,answer=answer,
           steps=[dict(id=f's{i}',action=a,result=b,kc_ids=[aliases[k] for k in keys],input_refs=refs)
                  for i,(a,b,keys,refs) in enumerate(steps,1)],
           kc_candidates=[dict(id=aliases[key],name=name,description=description) for key,name,description in kcs],
           methods=[dict(id=f'm{i}',name=name,step_ids=[f's{n}' for n in indices])
                    for i,(name,indices) in enumerate(methods or [('Последовательно выполнить преобразования и обосновать ответ',list(range(1,len(steps)+1)))],1)],
           warnings=warnings or [])
    validate_one(d)
    path=RUN/'raw'/f'{tid}.json'
    if path.exists():
        assert read(path)==d,'Do not replace saved raw: '+tid
        return
    write(path,d)
    provenance=read(RUN/'captures.json') if (RUN/'captures.json').exists() else {}
    provenance[tid]=dict(saved_at=datetime.now(timezone.utc).isoformat(),sha256=digest(path.read_bytes()),
                         author='Primary assistant in current shared conversation',
                         capture='Explicit authored mathematical text serialized to JSON; not an isolated API/model response')
    write(RUN/'captures.json',provenance)
    print('Saved',tid,len(steps),'steps',len(kcs),'candidate KCs')
