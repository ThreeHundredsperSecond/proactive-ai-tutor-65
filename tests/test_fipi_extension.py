"""Meaningful safeguards: immutable inputs, literal evidence and blocking decisions."""
import json
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import fipi_extension as ext


class ExtensionSafeguards(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1])
        self.root = Path(self.temp.name)
        self.run = self.root / 'run'
        self.patches = [patch.object(ext, 'ROOT', self.root), patch.object(ext, 'RUN', self.run)]
        for p in self.patches: p.start()
        ext.freeze(self.run/'inputs/tasks/T.json', {'statement_html':'<p>x+1=2</p>','assets':[]})
        ext.freeze(self.run/'catalog-for-auditor.json', {'catalog_version':'v1','nodes':[{'id':'linear'}]})
        ext.freeze(self.run/'raw/author/T.json', {'task_id':'T','steps':[{'id':'s1','action':'Solve equation','result':'x=1'}],
                                               'kc_candidates':[{'id':'k1'}]})
        self.audit = {'task_id':'T','catalog_version':'v1','decisions':[{
            'local_kc_id':'k1','status':'match','catalog_kc_id':'linear','evidence':[{'ref':'step:s1:result','quote':'x=1'}],
            'context_refs':['condition'],'alternatives_checked':[],'rationale':'Matching action with numeric coefficients',
            'proposal':None,'blocking':False,'issue_ids':[]}], 'issues':[]}

    def tearDown(self):
        for p in reversed(self.patches): p.stop()
        self.temp.cleanup()

    def check(self, a):
        p=self.run/'audit.json';p.write_text(json.dumps(a),encoding='utf-8')
        return ext.validate_audit('T',p)

    def test_freeze_refuses_replacement(self):
        p=self.run/'frozen';ext.freeze(p,b'original\r\n')
        with self.assertRaises(AssertionError):ext.freeze(p,b'original\n')
        self.assertEqual(p.read_bytes(),b'original\r\n')

    def test_literal_supported_match(self):
        self.assertEqual(self.check(self.audit)['status'],'technical_pass')

    def test_rejects_invented_evidence_and_unknown_catalog(self):
        for field,value in [('quote','x=2'),('catalog_kc_id','missing')]:
            a=deepcopy(self.audit)
            if field=='quote':a['decisions'][0]['evidence'][0][field]=value
            else:a['decisions'][0][field]=value
            with self.subTest(field=field),self.assertRaises(AssertionError):self.check(a)

    def test_blocking_issue_cannot_leave_match(self):
        a=deepcopy(self.audit)
        a['issues']=[{'id':'i1','kind':'math','refs':['step:s1:result'],'description':'Root fails substitution',
                      'blocking':True,'affected_local_kc_ids':['k1']}]
        with self.assertRaises(AssertionError):self.check(a)
        a['decisions'][0].update(status='uncertain',catalog_kc_id=None,blocking=True,issue_ids=['i1'])
        self.assertEqual(self.check(a)['status'],'technical_pass')

    def test_each_candidate_exactly_once(self):
        for decisions in [[],self.audit['decisions']*2]:
            a=deepcopy(self.audit);a['decisions']=decisions
            with self.assertRaises(AssertionError):self.check(a)


if __name__=='__main__':unittest.main()
