from copy import deepcopy
import json
import unittest
import production_gates as g
import execution_control as e
import test_production_ops as old


class RuntimeGateTests(unittest.TestCase):
    def setUp(self):
        self.old=old.GateTests('test_pre_video_record_integrity');self.old.setUp();self.root=self.old.root
        self.s,self.r=self.old.fixture('pre_video')
        (self.root/'skill.md').write_text('<a id="rules"></a>\nSynthetic applicable instructions.\n')
        self.routes={'schema_version':'reading-map-1','stages':{'dispatch':['rules']}}
        self.put('routes.json',self.routes)
        rec=e.reading_pack(self.root/'skill.md',self.routes,'dispatch','main','EP001')['receipt']
        rec.update(status='ACKNOWLEDGED',applied_rules=['current episode; no duplicate submit'])
        self.put('receipt.json',rec)
        self.put('prompt.json',{'status':'READY','shot_id':'S1','prompt9_used':True,'prompt':'Synthetic prompt, not actual model output.'})
        self.b={'schema_version':'execution-binding-1','actor_id':'main','actor_role':'coordinator',
            'active_episode':'EP001','target_episode':'EP001','stage':'dispatch','task_scope':'EP001',
            'skill':self.old.record('skill.md'),'routes':self.old.record('routes.json'),
            'reading_receipt':self.old.record('receipt.json'),'video_prompt_packages':[self.old.record('prompt.json')]}
        self.s.update(episode_id='EP001',execution_required=True)
        self.refresh()
    def put(self,name,value):(self.root/name).write_text(json.dumps(value))
    def refresh(self):
        self.put('binding.json',self.b);self.s['execution_binding']=self.old.record('binding.json')
        for r in self.r:r['snapshot_sha256']=g.digest(self.s)
    def tearDown(self):self.old.tearDown()
    def gate(self):return g.gate(self.s,self.r,self.root)
    def test_valid_execution_records(self):self.assertEqual(self.gate()['status'],'ACCEPTED')
    def test_missing_binding(self):
        self.s['execution_binding']=None
        for r in self.r:r['snapshot_sha256']=g.digest(self.s)
        self.assertEqual(self.gate()['status'],'BLOCKED')
    def test_subagent_cannot_commit(self):self.b['actor_role']='writer';self.refresh();self.assertEqual(self.gate()['status'],'BLOCKED')
    def test_next_episode_scope_rejected(self):self.b['target_episode']='EP002';self.refresh();self.assertEqual(self.gate()['status'],'BLOCKED')
    def test_wrong_stage_rejected(self):self.b['stage']='blind';self.refresh();self.assertEqual(self.gate()['status'],'BLOCKED')
    def test_missing_acknowledgment_rejected(self):
        rec=json.loads((self.root/'receipt.json').read_text());rec['status']='ISSUED_NOT_ACKNOWLEDGED'
        self.put('receipt.json',rec);self.b['reading_receipt']=self.old.record('receipt.json');self.refresh()
        self.assertEqual(self.gate()['status'],'BLOCKED')
    def test_changed_skill_invalidates_receipt(self):
        (self.root/'skill.md').write_text((self.root/'skill.md').read_text()+'new rule')
        self.b['skill']=self.old.record('skill.md');self.refresh();self.assertEqual(self.gate()['status'],'BLOCKED')
    def test_missing_nine_package_blocks(self):self.b['video_prompt_packages']=[];self.refresh();self.assertEqual(self.gate()['status'],'BLOCKED')
    def test_draft_package_blocks(self):
        self.put('prompt.json',{'status':'DRAFT','shot_id':'S1','prompt9_used':True,'prompt':'test'})
        self.b['video_prompt_packages']=[self.old.record('prompt.json')];self.refresh();self.assertEqual(self.gate()['status'],'BLOCKED')
    def test_legacy_package_not_mislabeled_nine(self):
        self.put('prompt.json',{'status':'READY','shot_id':'S1','prompt9_used':False,'prompt':'test'})
        self.b['video_prompt_packages']=[self.old.record('prompt.json')];self.refresh();self.assertEqual(self.gate()['status'],'BLOCKED')
    def test_wrong_shot_package_blocks(self):
        self.put('prompt.json',{'status':'READY','shot_id':'S2','prompt9_used':True,'prompt':'test'})
        self.b['video_prompt_packages']=[self.old.record('prompt.json')];self.refresh();self.assertEqual(self.gate()['status'],'BLOCKED')
    def test_legacy_interface_still_available_but_not_new_policy(self):
        self.s.pop('execution_required');self.s.pop('execution_binding')
        for r in self.r:r['snapshot_sha256']=g.digest(self.s)
        self.assertEqual(self.gate()['status'],'ACCEPTED')


if __name__=='__main__':unittest.main()
