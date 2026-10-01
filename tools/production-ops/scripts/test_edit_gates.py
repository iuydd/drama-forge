from copy import deepcopy
import json
import unittest
import production_gates as g
import test_production_ops as old
import test_edit_timeline as ed


class EditGateTests(unittest.TestCase):
    def setUp(self):
        self.old=old.GateTests('test_final_record_integrity');self.old.setUp();self.root=self.old.root
        self.s,self.r=self.old.fixture('final_delivery')
        t=ed.fixture();p=self.root/'timeline.json';p.write_text(json.dumps(t))
        self.s.update(editing_required=True,edit_timeline=self.old.record('timeline.json'),
                      cut_ids=['V1__V2'],required_event_ids=['EV1','EV2','EL1','EL2'])
        for cid in ('edit_timeline','edit_cut_review'):
            self.r.append({'check_id':cid,'status':'PASS','subject_sha256':self.s['subject']['sha256'],
                'evidence':[self.old.record('evidence.json')],'observation':'Synthetic gate fixture; not real editing.',
                'details':{'timeline_sha256':self.s['edit_timeline']['sha256'],'cut_ids':['V1__V2'],
                           'required_event_ids':['EV1','EV2','EL1','EL2'],'unresolved_event_ids':[],
                           'unresolved_cut_ids':[],'av_cut_review':'PASS'}})
        self.refresh()
    def refresh(self):
        for r in self.r:r['snapshot_sha256']=g.digest(self.s)
    def tearDown(self):self.old.tearDown()
    def find(self,cid):return next(x for x in self.r if x['check_id']==cid)
    def test_complete_new_gate(self):self.assertEqual(g.gate(self.s,self.r,self.root)['status'],'ACCEPTED')
    def test_missing_edit_review(self):
        self.r=[x for x in self.r if x['check_id']!='edit_cut_review']
        self.assertEqual(g.gate(self.s,self.r,self.root)['status'],'BLOCKED')
    def test_stale_timeline(self):
        self.find('edit_timeline')['details']['timeline_sha256']='1'*64
        self.assertEqual(g.gate(self.s,self.r,self.root)['status'],'BLOCKED')
    def test_wrong_cut_list(self):
        self.find('edit_cut_review')['details']['cut_ids']=[]
        self.assertEqual(g.gate(self.s,self.r,self.root)['status'],'BLOCKED')
    def test_unreviewed_av_cut(self):
        self.find('edit_cut_review')['details']['av_cut_review']='UNKNOWN'
        self.assertEqual(g.gate(self.s,self.r,self.root)['status'],'BLOCKED')
    def test_unresolved_event(self):
        self.find('edit_timeline')['details']['unresolved_event_ids']=['EL1']
        self.assertEqual(g.gate(self.s,self.r,self.root)['status'],'BLOCKED')
    def test_cut_failure(self):
        self.find('edit_cut_review')['status']='FAIL'
        self.assertEqual(g.gate(self.s,self.r,self.root)['status'],'REJECTED')
    def test_scope_must_match_actual_timeline(self):
        self.s['cut_ids']=[];self.refresh()
        for cid in ('edit_timeline','edit_cut_review'):self.find(cid)['details']['cut_ids']=[]
        self.assertIn('cut/event scope differs from actual frozen timeline',g.gate(self.s,self.r,self.root)['blockers'])
    def test_unlocked_actual_timeline(self):
        p=self.root/'timeline.json';t=json.loads(p.read_text());t['status']='DRAFT';p.write_text(json.dumps(t))
        self.s['edit_timeline']=self.old.record('timeline.json');self.refresh()
        self.assertIn('actual edit timeline invalid or unlocked',g.gate(self.s,self.r,self.root)['blockers'])
    def test_legacy_interface_unchanged(self):
        s,r=self.old.fixture('final_delivery')
        self.assertEqual(g.gate(s,r,self.root)['status'],'ACCEPTED')
    def test_not_extra_model_review_for_optional_suggestions(self):
        self.r.append({'check_id':'more_beautiful_edit','status':'FAIL'})
        self.assertEqual(g.gate(self.s,self.r,self.root)['status'],'ACCEPTED')


if __name__=='__main__':unittest.main()
