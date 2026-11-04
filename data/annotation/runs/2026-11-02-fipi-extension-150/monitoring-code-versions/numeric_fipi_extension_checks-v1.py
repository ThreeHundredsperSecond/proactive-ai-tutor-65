"""Reproduce independent numeric spot expectations; never modifies author/audit JSON."""
import argparse
import ast
import math
from decimal import Decimal
from fractions import Fraction

from fipi_extension import RUN, freeze, read
from health_fipi_extension import active, sample

VALUES = {
    'F3F0DF': float(Decimal('0.9')*Decimal('0.1')**2),
    '68Ac00': 5*3,
    'F2CCA3': math.sqrt(1+143),
    '16C715': math.sqrt(4*6**2/(2*3)-2*3),
    '2F945c': (50-20)/3/50,
    'D6F31D': (170*11+160*8)/(170-160),
    'B73557': 10*math.cos(-2*math.pi/3)+36*(-2*math.pi/3)/math.pi-6,
    '80631B': 60/4,
    'B05656': 3+2,
    '659A4A': (29-math.sqrt(29**2-4*7*30))/(2*7),
    'AD5F64': (180-114)/2,
    '23C8BB': 4*math.sqrt(2)-8*math.sqrt(2)*math.sin(7*math.pi/8)**2,
    '018816': abs(90-2*9),
    '91Be4D': 48/2,
    '6532cc': float(Decimal('0.4')*Decimal('0.6')**3),
    'F3Fc26': 144/8,
    'FE4362': (-70+math.sqrt(70**2+4*8*123))/(2*8)*60,
    '47447E': Fraction(2,4),
    '4A073e': 8*4+9*(-3),
}


def safe_numeric(s):
    """Parse numeric-only answers; refuse prose, symbols or executable expressions."""
    s=s.strip().replace(',','.').replace('−','-').replace(' ','').rstrip('.')
    if len(s)>100: raise ValueError('Not numeric-only')
    node=ast.parse(s,mode='eval').body
    def val(n):
        if isinstance(n,ast.Constant) and type(n.value) in (int,float):return n.value
        if isinstance(n,ast.UnaryOp) and isinstance(n.op,(ast.UAdd,ast.USub)):
            return val(n.operand)*(1 if isinstance(n.op,ast.UAdd) else -1)
        if isinstance(n,ast.BinOp) and isinstance(n.op,(ast.Add,ast.Sub,ast.Mult,ast.Div)):
            a,b=val(n.left),val(n.right)
            if isinstance(n.op,ast.Add):return a+b
            if isinstance(n.op,ast.Sub):return a-b
            if isinstance(n.op,ast.Mult):return a*b
            return a/b
        raise ValueError('Not numeric-only')
    return float(val(node))


def main():
    p=argparse.ArgumentParser();p.add_argument('--batch',type=int,required=True)
    a=p.parse_args();b=a.batch
    expected=read(RUN/'checks'/f'batch-{b:02}-math-expected.json')
    records=[];mismatch=False
    for x in expected['checks']:
        tid=x['task_id'];record=dict(x)
        if tid in VALUES:
            value=float(VALUES[tid]);record['recomputed_value']=value
            try:
                answer=read(active(tid,'author'))['answer'];actual=safe_numeric(answer)
                ok=math.isclose(value,actual,rel_tol=1e-9,abs_tol=1e-9)
                record.update(status='numeric_match' if ok else 'numeric_mismatch',author_answer=answer)
                mismatch |= not ok
            except (ValueError,SyntaxError):
                record.update(status='comparison_needs_review',reason='Answer not numeric-only; no automated verdict')
        records.append(record)
    if b==1:
        assert Fraction(143,11)-Fraction(143,13)==2
    freeze(RUN/'checks'/f'batch-{b:02}-math-comparison.json',{'batch':b,'checks':records,'numeric_mismatch':mismatch,
        'scope':'Independent primary-assistant spot calculations; no full expert validation; not KC mapping'})
    print('Recorded comparisons; numeric_mismatch=',mismatch)


if __name__=='__main__':main()
