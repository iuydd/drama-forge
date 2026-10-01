"""Local synthetic bridge: upfront recipes -> accepted media -> existing gates.
No real content approval, no model call, no generation or spending.
"""
from copy import deepcopy
from pathlib import Path
import json
import tempfile
import unittest
import brain_handoff as b
import preproduction as p
import prompt_contract as pc
from fixtures_v4 import Fixture
from test_v43_preproduction import fixture, modify, media_registry


class Delegation43Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.reg,self.record=media_registry(self.root)
        self.fx=Fixture(self.root,media_name='ref.bin')
        self.fx.request['video_input']='keyframe'
        self.fx.sync_request()
        self.req,self.part=fixture()
        modify(self.part,'T2',lambda x:x.update(request_template={**deepcopy(self.fx.request),'inputs':[{'asset_id':'REF','role':'start_frame','upload_index':1,'file':{'$asset':'REF','field':'file'}}]}))
        self.plan=p.assemble([self.part],self.req)
        self.fx.put('plan.json',self.plan);self.fx.put('registry.json',self.reg)
        self.fx.put('sequence.json',{'synthetic':True,'note':'File-binding test only; not a valid real continuity plan'})
        packet=self.fx.packet
        packet.update(schema_version='execution-packet-1',policy_version='4.2.0',workflow_version='4.3.0',workflow_mode='upfront_only',episode_id='EP1',decision_owner='production_supervisor',brain_media_review_performed=False,preproduction_plan=self.record('plan.json'),asset_registry=self.record('registry.json'))
        self.task=packet['tasks'][0]
        self.task.update(plan_task_id='T2',continuity_plan=self.record('sequence.json'))
        self.task['semantic_review']={'request_sha256':self.task['request_sha256'],'result':'PASS','reviewer_id':'SYNTHETIC_LOCAL_CONFORMITY_REVIEWER','observation':'Synthetic exact recipe conformity; not brain media viewing','coverage':sorted(pc.SEMANTIC_COVERAGE),'evidence':self.fx.record('proof.md')}
        self.fx.save_packet()
    def tearDown(self):self.tmp.cleanup()
    def errors(self):
        self.fx.save_packet();return b.load_task(self.fx.binding,self.root)[2]
    def test_local_acceptance_advances_without_brain_media_review(self):
        self.assertEqual(self.errors(),[])
        out=b.check_request(self.fx.binding,self.fx.request,self.root)
        self.assertEqual(out['status'],'INPUT_READY');self.assertFalse(out['media_quality_verified']);self.assertFalse(out['authority_authenticated'])
    def test_no_brain_impersonation(self):self.fx.packet['decision_owner']='chatgpt_brain';self.assertTrue(self.errors())
    def test_no_fake_brain_media_view(self):self.fx.packet['brain_media_review_performed']=True;self.assertTrue(self.errors())
    def test_cannot_change_frozen_prompt_locally(self):
        self.task['request']['prompt']='Different synthetic instruction'
        self.task['request_sha256']=b.digest(self.task['request'])
        self.task['semantic_review']['request_sha256']=self.task['request_sha256']
        self.assertTrue(any('recipe' in x for x in self.errors()))
    def test_cannot_omit_accepted_registry(self):self.fx.packet.pop('asset_registry');self.assertTrue(self.errors())
    def test_candidate_cannot_advance(self):
        report=b.read_json(self.root/'review.json');report['status']='CANDIDATE';self.fx.put('review.json',report)
        self.reg['assets'][0]['review']=self.record('review.json');self.fx.put('registry.json',self.reg);self.fx.packet['asset_registry']=self.record('registry.json')
        self.assertTrue(self.errors())
    def test_no_downgrade_media_policy(self):self.fx.packet['policy_version']='4.1.0';self.assertTrue(self.errors())
    def test_runtime_episode_must_be_in_complete_plan(self):self.fx.packet['episode_id']='OTHER';self.assertTrue(self.errors())
    def test_semantic_check_still_required(self):self.task.pop('semantic_review');self.assertTrue(self.errors())
    def test_original_fidelity_and_continuity_binding_still_required(self):self.task.pop('fidelity_contract');self.task.pop('continuity_plan');self.assertTrue(self.errors())
    def test_unknown_recipe_is_not_an_automatic_repair(self):self.task['plan_task_id']='INVENTED';self.assertTrue(self.errors())
    def test_input_file_mutation_still_rejected(self):(self.root/'ref.bin').write_bytes(b'MUTATION');self.assertTrue(self.errors())


class AssembledPlan43Tests(unittest.TestCase):
    def setUp(self):
        self.req,self.part=fixture();self.plan=p.assemble([self.part],self.req)
    def test_added_unmanifested_record_blocks(self):self.plan['records']['HIDDEN']={};self.assertTrue(p.plan_errors(self.plan))
    def test_mutated_scope_blocks(self):self.plan['episode_ids']=['EP2'];self.assertTrue(p.plan_errors(self.plan))
    def test_duplicated_manifest_blocks(self):self.plan['manifest'].append(self.plan['manifest'][0]);self.assertTrue(p.plan_errors(self.plan))
    def test_unknown_record_kind_blocks(self):self.plan['manifest'][0]['kind']='shell';self.assertTrue(p.plan_errors(self.plan))
    def test_compute_runtime_hash_only_after_binding(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);reg,record=media_registry(root)
            symbolic={'asset_id':'REF','role':'identity','upload_index':1,'path':{'$asset':'REF','field':'path'},'sha256':{'$asset':'REF','field':'sha256'}}
            execution={'scene':{'id':'ROOM'},'shot':{'mode':'edit_same_view','shot_id':'S1','references':[symbolic],'output':{'width':8,'height':6}},'runtime_profile':{'backend':'SYNTHETIC_ONLY'}}
            t=self.plan['records']['T1'];t['execution_template']=execution
            t['request_template']['configuration_sha256']='COMPUTE_FROM_EXECUTION_TEMPLATE';t['request_template']['mode']='edit_same_view'
            out=p.bind_task(self.plan,'T1',reg,root)
            self.assertEqual(out['request'],b.request_snapshot(out['execution_inputs']['scene'],out['execution_inputs']['shot'],out['execution_inputs']['runtime_profile'],t['request_template']['prompt']))
            self.assertFalse(out['brain_media_review_performed']);self.assertFalse(out['ready_for_submission'])
    def test_inconsistent_execution_template_blocks(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);reg,_=media_registry(root);t=self.plan['records']['T1'];t['request_template']['configuration_sha256']='COMPUTE_FROM_EXECUTION_TEMPLATE'
            t['execution_template']={'scene':{},'shot':{'mode':'video_i2v','references':[],'output':{}},'runtime_profile':{}}
            self.assertRaises(ValueError,p.bind_task,self.plan,'T1',reg,root)

if __name__=='__main__':unittest.main()
