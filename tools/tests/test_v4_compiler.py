"""Actual local compiler binding using synthetic reference fixture images."""
from copy import deepcopy
import sys
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'production-ops/scripts'))
sys.path.insert(0,str(ROOT/'visual-continuity-prompter/scripts'))
import brain_handoff as b
import prompt_nine as n
from fixtures_v4 import Fixture
import test_integration as old
c=old.continuity


class CompilerBindingTests(unittest.TestCase):
    def setUp(self):
        self.parent=old.SuiteIntegrationTests('test_reference_export_compiles_in_existing_tool');self.parent.setUp()
        self.scene,self.shot,self.profile=self.parent.build();self.root=self.parent.f.root
        self.x=Fixture(self.root,[])
        self.x.contract.update(shot_id=self.shot['shot_id'],scene_id=self.shot['scene_id'],view_id=self.shot['view_id'])
        self.x.save_contract()
        self.shot.update(policy_version='4.0.0',episode_id='EP001',brain_required=True,fidelity_required=True,
            fidelity_contract=self.x.record('fidelity.json'),locked_prompt='SYNTHETIC TEST PROMPT, NOT A PRODUCTION IMAGE REQUEST.')
        self.x.request=b.request_snapshot(self.scene,self.shot,self.profile,self.shot['locked_prompt'])
        self.x.packet['phase']='start_frames';self.x.sync_request();self.shot['brain_binding']=self.x.binding
    def tearDown(self):self.parent.tearDown()
    def compile(self):return c.compile_package(self.scene,self.shot,self.profile,self.root,production=True)
    def test_complete_compiler_can_be_ready(self):self.assertEqual(self.compile()['status'],'READY',self.compile())
    def test_missing_brain_binding_is_draft(self):self.shot['brain_binding']=None;self.assertEqual(self.compile()['status'],'DRAFT')
    def test_gaze_change_invalidates_frozen_configuration(self):self.shot['gaze_target']='CAMERA';self.assertEqual(self.compile()['status'],'DRAFT')
    def test_locked_prompt_change_is_blocked(self):self.shot['locked_prompt']='rewrite';self.assertEqual(self.compile()['status'],'DRAFT')
    def test_quality_parameter_change_blocked(self):self.profile['test_steps']=5;self.assertEqual(self.compile()['status'],'DRAFT')
    def test_wrong_fidelity_view_blocked(self):
        self.x.contract['view_id']='OTHER';self.x.save_contract();self.shot['fidelity_contract']=self.x.record('fidelity.json')
        self.assertEqual(self.compile()['status'],'DRAFT')
    def test_flags_cannot_be_disabled(self):
        for flag in ('brain_required','fidelity_required'):
            with self.subTest(flag=flag):
                oldvalue=self.shot[flag];self.shot[flag]=False;self.assertEqual(self.compile()['status'],'DRAFT');self.shot[flag]=oldvalue
    def test_publication_does_not_happen(self):self.assertFalse(self.compile()['executed'])
    def test_nine_digest_avoids_external_approval_cycle(self):
        a=n.source_digest(self.shot);self.shot['brain_binding']={'new':'binding'};self.assertEqual(a,n.source_digest(self.shot))
    def test_nine_digest_still_binds_real_content(self):
        a=n.source_digest(self.shot);self.shot['change_request']='different action';self.assertNotEqual(a,n.source_digest(self.shot))
    def test_new_view_is_asset_not_populated_start_frame(self):
        self.shot['mode']='new_view';self.assertEqual(b.request_snapshot(self.scene,self.shot,self.profile,'test')['kind'],'asset_image')


if __name__=='__main__':unittest.main()
