"""Synthetic approval/request integrity tests, not proof of real authorization."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
import brain_handoff as b
from fixtures_v4 import Fixture


class BrainTests(unittest.TestCase):
    def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.x=Fixture(self.tmp.name)
    def tearDown(self):self.tmp.cleanup()
    def run_gate(self):return b.check_request(self.x.binding,self.x.request,self.x.root)
    def packet_change(self,key,value):self.x.packet[key]=value;self.x.save_packet()
    def test_frozen_request_matches(self):self.assertEqual(self.run_gate()['status'],'INPUT_READY')
    def test_does_not_claim_execution_or_authentication(self):
        r=self.run_gate();self.assertFalse(r['executed']);self.assertFalse(r['authority_authenticated']);self.assertFalse(r['media_quality_verified'])
    def test_prompt_rewrite_rejected(self):self.x.request['prompt']='agent rewrite';self.assertEqual(self.run_gate()['status'],'BLOCKED')
    def test_wrong_output_size_rejected(self):self.x.request['output_spec']['width']=16;self.assertEqual(self.run_gate()['status'],'BLOCKED')
    def test_wrong_configuration_rejected(self):self.x.request['configuration_sha256']='1'*64;self.assertEqual(self.run_gate()['status'],'BLOCKED')
    def test_wrong_reference_rejected(self):self.x.request['inputs'][0]['sha256']='1'*64;self.assertEqual(self.run_gate()['status'],'BLOCKED')
    def test_unlocked_brain_packet(self):self.packet_change('status','DRAFT');self.assertEqual(self.run_gate()['status'],'BLOCKED')
    def test_executor_cannot_self_declare_decision_role(self):self.packet_change('decision_owner','executor');self.assertEqual(self.run_gate()['status'],'BLOCKED')
    def test_missing_reviewed_media(self):self.packet_change('reviewed_inputs',[]);self.assertEqual(self.run_gate()['status'],'BLOCKED')
    def test_unknown_creative_decision_blocks(self):self.packet_change('blocking_questions',['where is poster?']);self.assertEqual(self.run_gate()['status'],'BLOCKED')
    def test_phase_mismatch(self):self.packet_change('phase','assets');self.assertEqual(self.run_gate()['status'],'BLOCKED')
    def test_wrong_policy_version(self):self.packet_change('policy_version','3.1.2');self.assertEqual(self.run_gate()['status'],'BLOCKED')
    def test_not_ready_task(self):self.x.packet['tasks'][0]['status']='WAITING_MEDIA';self.x.save_packet();self.assertEqual(self.run_gate()['status'],'BLOCKED')
    def test_missing_approval_file(self):self.packet_change('approval_evidence',None);self.assertEqual(self.run_gate()['status'],'BLOCKED')
    def test_unknown_task_id(self):self.x.binding['task_id']='OTHER';self.assertEqual(self.run_gate()['status'],'BLOCKED')
    def test_duplicate_task_id(self):self.x.packet['tasks'].append(deepcopy(self.x.packet['tasks'][0]));self.x.save_packet();self.assertEqual(self.run_gate()['status'],'BLOCKED')
    def test_fidelity_file_changed(self):(self.x.root/'fidelity.json').write_text('{}');self.assertEqual(self.run_gate()['status'],'BLOCKED')
    def test_stale_packet_hash(self):self.x.put('packet.json',{});self.assertEqual(self.run_gate()['status'],'BLOCKED')
    def test_escape_path(self):self.x.binding['packet']['path']='../packet.json';self.assertEqual(self.run_gate()['status'],'BLOCKED')
    def test_abs_path(self):self.x.binding['packet']['path']=str(self.x.root/'packet.json');self.assertEqual(self.run_gate()['status'],'BLOCKED')
    def test_symlink(self):(self.x.root/'link.json').symlink_to(self.x.root/'packet.json');self.x.binding['packet']['path']='link.json';self.assertEqual(self.run_gate()['status'],'BLOCKED')
    def test_duplicate_json_key_rejected(self):
        p=self.x.root/'bad.json';p.write_text('{"x":1,"x":2}')
        with self.assertRaises(ValueError):b.read_json(p)
    def test_nonfinite_json_rejected(self):
        p=self.x.root/'bad.json';p.write_text('{"x":NaN}')
        with self.assertRaises(ValueError):b.read_json(p)
    def test_snapshot_avoids_binding_hash_cycle(self):
        shot={'mode':'edit_same_view','shot_id':'S1','references':[],'brain_binding':{'packet':'OLD'}}
        a=b.request_snapshot({},shot,{},'locked');shot['brain_binding']={'packet':'NEW'}
        self.assertEqual(a,b.request_snapshot({},shot,{},'locked'))
    def test_snapshot_still_binds_body_head_eyes(self):
        shot={'mode':'edit_same_view','shot_id':'S1','references':[],'gaze':'paper'}
        a=b.request_snapshot({},shot,{},'locked');shot['gaze']='camera'
        self.assertNotEqual(a,b.request_snapshot({},shot,{},'locked'))
    def test_initial_asset_request_may_have_no_prior_images(self):
        self.x.request.update(kind='asset_image',inputs=[]);self.x.packet['phase']='assets';self.x.sync_request()
        self.assertEqual(self.run_gate()['status'],'INPUT_READY')
    def test_video_without_real_start_frame_blocked(self):
        self.x.request['inputs']=[];self.x.sync_request();self.assertEqual(self.run_gate()['status'],'BLOCKED')
    def test_asset_reference_must_be_returned_and_reviewed(self):
        self.x.request['kind']='asset_image';self.x.packet['phase']='assets';self.x.sync_request()
        self.packet_change('reviewed_inputs',[]);self.assertEqual(self.run_gate()['status'],'BLOCKED')


if __name__=='__main__':unittest.main()
