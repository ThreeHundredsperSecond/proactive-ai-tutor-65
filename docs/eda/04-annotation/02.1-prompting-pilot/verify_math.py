"""Independent finite and analytic checks. No generation model uses this file."""
import json, math
from pathlib import Path
from collections import defaultdict

root=Path(__file__).parent
digit_sum=lambda n:sum(map(int,str(n)))
checks={}
checks['1']={'angle_A':2*30,'angle_B':180-2*30-54}
x=(.2*90-.1*90)/(.6+.1-.4)
checks['4']={'probability':.2+.12}
checks['10']={'mass_1':round(x,10),'mass_2':round(x+90,10),'total':round(2*x+90,10),'copper':round(.6*x+.1*(x+90),10)}
# For A=(0,0,0), C=(2,2sqrt3,0), K=(2,0,4),
# normal=(2sqrt3,-2,-sqrt3), squared norm=19.
checks['14']={'plane':'2sqrt(3)x-2y-sqrt(3)z=0','normal_squared_norm':12+4+3,'distance':8*math.sqrt(3)/math.sqrt(19),'C1_plane_value':-4*math.sqrt(3),'general_proof':'Let side a>0 and height h>0. The line through K parallel to AC meets B1C1 at its midpoint M. These are the parallel-base traces of alpha. Section AKMC has parallel bases AC,KM and AK^2=CM^2=h^2+a^2/4, so it is an isosceles trapezoid without imposing a=h.'}
checks['19a']={'pair':[1008,1035],'sum':2043,'digit_sums':[digit_sum(1008),digit_sum(1035)]}
pairs=[(a,599-a) for a in range(1,300) if digit_sum(a)==digit_sum(599-a)]
checks['19b']={'all_299_unordered_pairs_checked':True,'equal_digit_sum_pairs':pairs,'proof':'In adding to 599, a carry from units would need digits summing to 19, impossible. Hence no carry to tens. A carry from tens likewise would need 19, impossible. Thus digit sums of both addends sum to 23, an odd number, and cannot be equal.'}
# If a positive sum were <231, each summand would be <=230.
# Exhausting digit-sum groups of those 230 integers is therefore a finite proof
# of the absence of a smaller candidate, not an arbitrary unbounded search.
groups=defaultdict(list)
for n in range(1,231):groups[digit_sum(n)].append(n)
groups_with_7=[{'digit_sum':s,'first_7':v[:7],'sum':sum(v[:7])} for s,v in groups.items() if len(v)>=7]
best=min(groups_with_7,key=lambda x:x['sum'])
assert best['sum']==231 and not pairs
checks['19c']={'bounded_search_proof':'Any smaller sum has every summand <=230. All digit-sum classes on 1..230 enumerated. Their seven smallest values yield minimum 231.','groups':sorted(groups_with_7,key=lambda x:x['digit_sum']),'minimum':best,'analytic_tail_bound':'For common digit sum d>=7, each number >=d, all share residue mod9, distinct sorted numbers differ by >=9; sum >=7d+9*21 >=238. For d=1..6 list seven minima explicitly.'}
(root/'evaluation/math_checks.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2))
print(json.dumps({k:v for k,v in checks.items() if k!='19c'},ensure_ascii=False,indent=2))
print('19c minimum',best)
