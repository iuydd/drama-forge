"""Full local v4 pre-video wiring over synthetic original-gate fixtures."""
from copy import deepcopy
import json
import unittest
import brain_handoff as brain
import execution_control as execution
import production_gates as g
import test_ensemble_gate as ensemble
import test_production_ops as old
from fixtures_v4 import Fixture


class V4GateTests(unittest.TestCase):
    def setUp(self):
        self.parent=ensemble.EnsembleGateTests('test_complete_record_integrity_only');self.parent.setUp()
        self.root=self.parent.root;self.s=self.parent.s;self.r=self.parent.r
        self.x=Fixture(self.root,['direction'],media_name='subject.bin')
        self.x.contract.update(scene_id=self.parent.shot['scene_id'],view_id=self.parent.shot['view_id'])
        self.x.contract['requirements'][0]['expected']['view_id']=self.parent.shot['view_id']
        self.x.save_contract();self.x.sync_request()
        self.s.update(policy_version='4.0.0',brain_required=True,fidelity_required=True,execution_required=True,
            fidelity_bindings=[{'shot_id':'S1','contract':self.x.record('fidelity.json'),
                'media':self.x.record('subject.bin'),'brain_binding':self.x.binding}])
        self.find('start_frame_gate')['details']['fidelity_review']=self.x.review('start_frame')
        (self.root/'skill.md').write_text('<a id="rules"></a>\nSynthetic test instructions only.\n')
        routes={'schema_version':'reading-map-1','stages':{'dispatch':['rules']}}
        self.x.put('routes.json',routes)
        receipt=execution.reading_pack(self.root/'skill.md',routes,'dispatch','main','EP001')['receipt']
        receipt.update(status='ACKNOWLEDGED',applied_rules=['SYNTHETIC TEST ONLY'])
        self.x.put('receipt.json',receipt)
        self.package={'status':'READY','shot_id':'S1','prompt9_used':True,'prompt':self.x.request['prompt'],
            'policy_version':'4.0.0','brain_binding':self.x.binding,'brain_request':deepcopy(self.x.request),
            'fidelity_contract':self.x.record('fidelity.json'),'input_order':deepcopy(self.x.request['inputs']),
            'output_spec':deepcopy(self.x.request['output_spec']),'mode':'video_i2v',
            'ensemble_used':True,'ensemble_sha256':g.digest(self.parent.b)}
        self.execution={'schema_version':'execution-binding-1','actor_id':'main','actor_role':'coordinator',
            'active_episode':'EP001','target_episode':'EP001','stage':'dispatch','task_scope':'EP001',
            'skill':self.x.record('skill.md'),'routes':self.x.record('routes.json'),
            'reading_receipt':self.x.record('receipt.json')}
        self.save()
    def find(self,cid):return next(r for r in self.r if r['check_id']==cid)
    def save(self):
        self.x.put('prompt.json',self.package)
        self.execution['video_prompt_packages']=[self.x.record('prompt.json')]
        self.x.put('execution.json',self.execution)
        self.s['execution_binding']=self.x.record('execution.json')
        self.parent.refresh()
    def tearDown(self):self.parent.tearDown()
    def result(self):return g.gate(self.s,self.r,self.root)
    def test_full_v4_prevideo_records_accept(self):self.assertEqual(self.result()['status'],'ACCEPTED',self.result())
    def test_policy_is_not_legacy(self):self.assertEqual(self.result()['policy_version'],'4.0.0')
    def test_prompt_changed_after_freeze(self):self.package['prompt']='agent rewrite';self.save();self.assertEqual(self.result()['status'],'BLOCKED')
    def test_input_order_changed_after_freeze(self):self.package['input_order'][0]['role']='identity';self.save();self.assertEqual(self.result()['status'],'BLOCKED')
    def test_output_spec_changed_after_freeze(self):self.package['output_spec']['width']=32;self.save();self.assertEqual(self.result()['status'],'BLOCKED')
    def test_brain_package_cannot_be_legacy(self):self.package['policy_version']='legacy';self.save();self.assertEqual(self.result()['status'],'BLOCKED')
    def test_fidelity_missing_blocks_existing_summary_pass(self):
        del self.find('start_frame_gate')['details']['fidelity_review'];self.assertEqual(self.result()['status'],'BLOCKED')
    def test_wrong_current_frame_blocked(self):
        self.s['fidelity_bindings'][0]['media']=self.x.record('proof.md');self.save();self.assertEqual(self.result()['status'],'BLOCKED')
    def test_detail_fail_rejects_whole_stage(self):
        self.find('start_frame_gate')['details']['fidelity_review']['shots'][0]['requirements'][0]['points'][0]['result']='FAIL'
        self.assertEqual(self.result()['status'],'REJECTED')
    def test_v4_flags_cannot_silently_disable(self):
        for flag in ('brain_required','fidelity_required','execution_required','ensemble_required'):
            with self.subTest(flag=flag):
                value=self.s[flag];self.s[flag]=False;self.save()
                self.assertEqual(self.result()['status'],'BLOCKED');self.s[flag]=value;self.save()
    def test_changed_packet_requires_actual_new_binding(self):
        self.x.packet['revision']='2';self.x.put('packet.json',self.x.packet)
        self.assertEqual(self.result()['status'],'BLOCKED')
    def test_production_gate_is_not_a_media_recognizer(self):self.assertFalse(self.result()['guarantees_zero_errors'])


class FidelityVideoIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.parent=old.GateTests('test_final_record_integrity');self.parent.setUp()
        self.root=self.parent.root;self.s,self.r=self.parent.fixture('shot_edit')
        self.x=Fixture(self.root,media_name='subject.bin')
        self.s.update(episode_id='EP001',fidelity_required=True,
            fidelity_bindings=[{'shot_id':'S1','contract':self.x.record('fidelity.json'),
                'media':self.x.record('subject.bin'),'brain_binding':self.x.binding}])
        next(r for r in self.r if r['check_id']=='visual_video')['details']['fidelity_review']=self.x.review()
        for r in self.r:r['snapshot_sha256']=g.digest(self.s)
    def tearDown(self):self.parent.tearDown()
    def test_original_and_new_evidence_both_accept(self):self.assertEqual(g.gate(self.s,self.r,self.root)['status'],'ACCEPTED')
    def test_no_contact_observation_does_not_accept(self):
        review=next(r for r in self.r if r['check_id']=='visual_video')['details']['fidelity_review']
        self.x.point(review,'action','contact')['result']='UNKNOWN'
        self.assertEqual(g.gate(self.s,self.r,self.root)['status'],'BLOCKED')
    def test_wrong_direction_rejects_even_visual_video_says_pass(self):
        review=next(r for r in self.r if r['check_id']=='visual_video')['details']['fidelity_review']
        self.x.point(review,'direction')['values']['screen_heading']='left'
        self.assertEqual(g.gate(self.s,self.r,self.root)['status'],'REJECTED')


if __name__=='__main__':unittest.main()
