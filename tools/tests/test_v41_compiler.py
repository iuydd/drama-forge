"""4.1 compiler integration: synthetic assets, no actual generation or semantic claims."""
from copy import deepcopy
import sys
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'production-ops/scripts'))
import brain_handoff as b
import test_v4_compiler as old
import test_sequence_continuity as seqtests
import test_ensemble_gate as ensemble_tests


class SequenceCompilerTests(unittest.TestCase):
    def setUp(self):
        self.old=old.CompilerBindingTests('test_complete_compiler_can_be_ready');self.old.setUp()
        self.root=self.old.root;self.x=self.old.x;self.shot=self.old.shot
        e=ensemble_tests.EnsembleGateTests('test_complete_record_integrity_only');e.setUp()
        try: bundle=deepcopy(e.b)
        finally:e.tearDown()
        bundle['scope'].update(shot_id=self.shot['shot_id'],scene_id=self.shot['scene_id'],
          scene_version=self.shot['scene_version'],view_id=self.shot['view_id'])
        self.shot.update(policy_version='4.1.0',ensemble=bundle,ensemble_required=True,continuity_required=True)
        # This shared 4.1/4.2 fixture now freezes the actual visible inventory,
        # rather than calling a generic synthetic sentence a complete prompt.
        self.shot['locked_prompt'] += '\n' + ensemble_tests.eg.module().render_clauses(bundle, image=True)
        p=seqtests.fixture();row=p['shots'][0];key='PROP_CUP.world_anchor'
        value=bundle['start_state']['entities']['PROP_CUP']['state']['world_anchor']
        row.update(shot_id=self.shot['shot_id'],scene_id=self.shot['scene_id'],view_id=self.shot['view_id'],
          state_in='T0',state_out='T0',state_keys=[key],visible_start_keys=[key],visible_end_keys=[key],
          ensemble_bindings=[{'key':key,'entity_id':'PROP_CUP','path':['state','world_anchor']}],
          continuity_clause=self.shot['locked_prompt'])
        scene=p['scenes']['STREET'];view=scene['views']['V1'];view['plate_asset_id']=self.shot['references'][0]['asset_id']
        scene['views']={self.shot['view_id']:view}
        p.update(initial={'state_id':'T0','facts':{key:value}},fixed_keys=[],states=[],
           scenes={self.shot['scene_id']:scene},shots=[row])
        self.p=p;self.x.packet['policy_version']='4.1.0';self.save()
    def save(self):
        self.x.put('sequence.json',self.p);self.shot['continuity_plan']=self.x.record('sequence.json')
        self.x.packet['tasks'][0]['continuity_plan']=self.shot['continuity_plan']
        self.x.request=b.request_snapshot(self.old.scene,self.shot,self.old.profile,self.shot['locked_prompt'])
        self.x.sync_request();self.shot['brain_binding']=self.x.binding
    def tearDown(self):self.old.tearDown()
    def compile(self):return self.old.compile()
    def test_complete_v41_compiler_ready(self):self.assertEqual(self.compile()['status'],'READY',self.compile())
    def test_refrozen_prompt_cannot_omit_visible_inventory(self):
        self.shot['locked_prompt'] = 'SYNTHETIC empty room, no visible people or objects.'
        self.p['shots'][0]['continuity_clause'] = self.shot['locked_prompt']
        self.save()
        result = self.compile()
        self.assertEqual(result['status'], 'DRAFT')
        self.assertTrue(any('frozen visible block' in error for error in result['blockers']))
    def test_missing_sequence_plan_draft(self):
        self.shot['continuity_plan']=None;self.assertEqual(self.compile()['status'],'DRAFT')
    def test_cannot_disable_sequence_flag(self):
        self.shot['continuity_required']=False;self.assertEqual(self.compile()['status'],'DRAFT')
    def test_changed_state_binding_blocks(self):
        self.p['initial']['facts']['PROP_CUP.world_anchor']='OTHER_HAND';self.save()
        self.assertEqual(self.compile()['status'],'DRAFT')
    def test_new_unregistered_view_blocks(self):
        self.p['shots'][0]['view_id']='MADE_UP';self.save();self.assertEqual(self.compile()['status'],'DRAFT')
    def test_exact_spatial_clause_required_even_when_other_prompt_good(self):
        self.p['shots'][0]['continuity_clause']='NEW UNSENT CLAUSE';self.save();self.assertEqual(self.compile()['status'],'DRAFT')
    def test_packet_policy_cannot_lag_behind_shot(self):
        self.x.packet['policy_version']='4.0.0';self.save();self.assertEqual(self.compile()['status'],'DRAFT')
    def test_frozen_plan_cannot_be_swapped_after_approval(self):
        self.p['revision']='2';self.x.put('sequence.json',self.p);self.assertEqual(self.compile()['status'],'DRAFT')
    def test_actual_plan_record_is_emitted(self):self.assertEqual(self.compile()['continuity_plan'],self.shot['continuity_plan'])
    def test_input_readiness_never_claims_media_quality(self):
        self.assertFalse(self.compile()['visual_quality_verified']);self.assertFalse(self.compile()['executed'])


if __name__=='__main__':unittest.main()
