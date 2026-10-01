"""Current policy across all existing pre-video gates; observations are SYNTHETIC."""
import unittest
import test_sequence_continuity as old
import prompt_contract as p
import fidelity_contract as f

class Gate42Tests(unittest.TestCase):
    def setUp(self):
        self.o=old.SequenceGateIntegrationTests('test_full_v41_prevideo_integrates_with_all_existing_gates');self.o.setUp()
        self.x=self.o.x;self.s=self.o.s;self.root=self.o.root
        self.s['policy_version']='4.2.0';self.o.p['policy_version']='4.2.0'
        self.o.p['shots'][0]['projection_dependencies']={'cup_side':['PROP_CUP.world_anchor']}
        self.o.parent.package['policy_version']='4.2.0';self.o.parent.package['prompt_ir_used']=True
        self.o.parent.package['prompt9_used']=False
        self.x.packet['policy_version']='4.2.0';self.x.contract['policy_version']='4.2.0';self.x.save_contract()
        self.s['fidelity_bindings'][0]['contract']=self.x.record('fidelity.json')
        self.x.packet['tasks'][0]['fidelity_contract']=self.x.record('fidelity.json')
        self.o.parent.package['fidelity_contract']=self.x.record('fidelity.json')
        task=self.x.packet['tasks'][0]
        task['semantic_review']={'request_sha256':task['request_sha256'],'result':'PASS','reviewer_id':'SYNTHETIC',
             'observation':'SYNTHETIC current gate fixture only','coverage':sorted(p.SEMANTIC_COVERAGE),'evidence':self.x.record('proof.md')}
        review=self.x.review('start_frame')
        req=self.x.contract['requirements'][0]
        review['shots'][0]['requirements'][0]['points'][0]['values']=f.derived_assertions(req,'start_frame',req['points']['start_frame'][0])
        self.o.parent.find('start_frame_gate')['details']['fidelity_review']=review
        self.o.save()
    def tearDown(self):self.o.tearDown()
    def test_current_policy_integrates_all_existing_checks(self):self.assertEqual(self.o.result()['status'],'ACCEPTED',self.o.result())
    def test_current_policy_requires_current_fidelity_contract(self):
        self.x.contract.pop('policy_version');self.x.save_contract()
        self.s['fidelity_bindings'][0]['contract']=self.x.record('fidelity.json');self.o.save()
        self.assertEqual(self.o.result()['status'],'BLOCKED')
    def test_current_policy_cannot_remove_canonical_observation_values(self):
        self.o.parent.find('start_frame_gate')['details']['fidelity_review']['shots'][0]['requirements'][0]['points'][0]['values']={}
        self.assertEqual(self.o.result()['status'],'BLOCKED')
    def test_current_policy_rejects_actual_opposed_direction_even_pass(self):
        self.o.parent.find('start_frame_gate')['details']['fidelity_review']['shots'][0]['requirements'][0]['points'][0]['values']['screen_heading']='left'
        self.assertEqual(self.o.result()['status'],'REJECTED')
    def test_current_policy_cannot_use_implicit_legacy_world_plan(self):
        self.o.p.pop('policy_version');self.o.save();self.assertEqual(self.o.result()['status'],'BLOCKED')
    def test_current_policy_needs_actual_semantic_record(self):
        self.x.packet['tasks'][0].pop('semantic_review');self.o.save();self.assertEqual(self.o.result()['status'],'BLOCKED')

if __name__=='__main__':unittest.main()
