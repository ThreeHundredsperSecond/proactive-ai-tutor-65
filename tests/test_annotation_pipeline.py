import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from annotation_pipeline import build, sha, validate, write


def response():
    return {'task_id':'t','solution_status':'solved','steps':[{'id':'s','action':'Act','result':'Result','kc_ids':['k']}],
            'kc_candidates':[{'id':'k','name':'Apply','description':'Operation'}],
            'methods':[{'id':'m','name':'Method','step_ids':['s']}],'warnings':[]}


class PipelineTests(unittest.TestCase):
    def test_invalid_references_and_types(self):
        d=response(); self.assertEqual(validate(d,'t'),[])
        d['steps'][0]['kc_ids']=['missing']; self.assertIn('unknown or unused KCs',validate(d,'t'))
        d['steps']=None; self.assertTrue(validate(d,'t'))
        self.assertTrue(validate([], 't'))

    def test_counts_mapping_and_review_gate(self):
        with tempfile.TemporaryDirectory() as folder:
            run=Path(folder); (run/'reviews').mkdir(); (run/'requests').mkdir()
            (run/'prompt-A.txt').write_text('A',encoding='utf-8'); (run/'requests/t.txt').write_text('request',encoding='utf-8')
            jobs=[{'job_id':f't_r{r}','task_id':'t','repeat':r,'raw_path':f'raw/t_r{r}.txt'} for r in (1,2,3)]
            write(run/'manifest.json',{'prompt_sha256':sha(run/'prompt-A.txt'),'tasks':[{'task_id':'t','images':[],'request_sha256':sha(run/'requests/t.txt')}],'jobs':jobs})
            write(run/'raw/t_r1.txt',response()); write(run/'raw/t_r2.txt',response())
            s=build(run)
            self.assertEqual((s['expected'],s['present'],s['structure_valid']),(3,2,2))
            self.assertEqual(s['available_jaccard_pairs'],0)
            write(run/'catalog.json',[{'id':'c','name':'Apply'}])
            write(run/'kc_mapping.json',[{'job_id':j['job_id'],'kc_id':'k','canonical_id':'c','raw_sha256':sha(run/j['raw_path'])} for j in jobs[:2]])
            s=build(run); self.assertEqual(s['available_jaccard_pairs'],1)
            self.assertEqual(s['eligible_corpus_responses'],0)
            write(run/'reviews/t.json',{'results':[{'job_id':j['job_id'],'raw_sha256':sha(run/j['raw_path']),'math_status':'passed','annotation_status':'accepted'} for j in jobs[:2]]})
            s=build(run)
            self.assertEqual(s['eligible_corpus_responses'],2)
            self.assertEqual(s['eligible_distinct_tasks'],1)
            self.assertEqual(s['singleton_fraction'],1)
            # Two alternative repeats with disjoint KC sets must not create a co-occurrence.
            write(run/'catalog.json',[{'id':'c','name':'Apply'},{'id':'d','name':'Other'}])
            write(run/'kc_mapping.json',[{'job_id':j['job_id'],'kc_id':'k','canonical_id':c,'raw_sha256':sha(run/j['raw_path'])} for j,c in zip(jobs[:2],['c','d'])])
            build(run)
            self.assertEqual(len((run/'derived/cooccurrence.csv').read_text(encoding='utf-8').splitlines()),1)
            (run/'raw/t_r1.txt').write_text('{}',encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'Review hash mismatch'): build(run)


if __name__=='__main__': unittest.main()
