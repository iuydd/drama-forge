"""Cross-schema / actual production compiler v4.2 wiring, synthetic approvals."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest
import json
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'production-ops/scripts'))
import brain_handoff as b
import prompt_contract as p
from fixtures_v42 import intent
import test_v41_compiler as old


class Compiler42Tests(unittest.TestCase):
    def setUp(self):
        self.o=old.SequenceCompilerTests('test_complete_v41_compiler_ready');self.o.setUp()
        self.shot=self.o.shot;self.profile=self.o.old.profile;self.x=self.o.x;self.root=self.o.root
        self.shot['policy_version']='4.2.0';self.x.packet['policy_version']='4.2.0';self.o.p['policy_version']='4.2.0'
        row=self.o.p['shots'][0];row['screen_start']={'cup_side':'left'};row['screen_end']={'cup_side':'left'}
        row['projection_dependencies']={'cup_side':row['state_keys'][:]}
        ir,backend=intent('image_edit');ir['clauses'][0]['reference_asset_id']=self.shot['references'][0]['asset_id']
        ir['clauses'][1]['text']=self.shot['locked_prompt'];ir['clauses'][1]['read_keys']=row['state_keys'][:];ir['invariant_keys']=row['state_keys'][:]
        self.shot['prompt_ir']=ir;self.profile['prompt_backend']=backend;self.freeze()
    def freeze(self):
        self.x.contract['policy_version']='4.2.0';self.x.save_contract();self.shot['fidelity_contract']=self.x.record('fidelity.json')
        self.shot['locked_prompt']=p.compile_ir(self.shot['prompt_ir'],self.profile['prompt_backend'])['prompt']
        self.o.p['shots'][0]['continuity_clause']=self.shot['prompt_ir']['clauses'][1]['text'];self.o.save()
        task=self.x.packet['tasks'][0]
        task['semantic_review']={'request_sha256':task['request_sha256'],'result':'PASS','reviewer_id':'SYNTHETIC_REVIEWER','observation':'SYNTHETIC structure test, not actual semantic/media inspection',
                                 'coverage':sorted(p.SEMANTIC_COVERAGE),'evidence':self.x.record('proof.md')}
        self.x.save_packet();self.shot['brain_binding']=self.x.binding
    def tearDown(self):self.o.tearDown()
    def compile(self):return self.o.compile()
    def test_v42_frozen_ir_semantic_record_ready(self):self.assertEqual(self.compile()['status'],'READY',self.compile())
    def test_v42_schema_and_compiler_agree(self):
        import jsonschema
        schema=json.loads((ROOT/'visual-continuity-prompter/schemas/shot.schema.json').read_text())
        self.assertEqual(list(jsonschema.Draft202012Validator(schema).iter_errors(self.shot)),[])
        self.assertEqual(self.compile()['status'],'READY',self.compile())
    def test_v41_schema_is_backward_compatible(self):
        import jsonschema
        self.shot['policy_version']='4.1.0'
        schema=json.loads((ROOT/'visual-continuity-prompter/schemas/shot.schema.json').read_text())
        self.assertEqual(list(jsonschema.Draft202012Validator(schema).iter_errors(self.shot)),[])
    def test_schema_runtime_supported_versions_equal(self):
        schema=json.loads((ROOT/'visual-continuity-prompter/schemas/shot.schema.json').read_text())
        self.assertEqual(set(schema['properties']['policy_version']['enum']),b.SUPPORTED_POLICIES)
    def test_missing_ir_not_ready(self):
        self.shot.pop('prompt_ir');self.assertEqual(self.compile()['status'],'DRAFT')
    def test_frozen_prompt_mismatch_not_ready(self):
        self.shot['locked_prompt']+=' extra';self.assertEqual(self.compile()['status'],'DRAFT')
    def test_semantic_stamp_cannot_refer_to_previous_request(self):
        self.x.packet['tasks'][0]['semantic_review']['request_sha256']='0'*64;self.x.save_packet();self.shot['brain_binding']=self.x.binding
        self.assertEqual(self.compile()['status'],'DRAFT')
    def test_missing_semantic_review_not_ready(self):
        self.x.packet['tasks'][0].pop('semantic_review');self.x.save_packet();self.shot['brain_binding']=self.x.binding
        self.assertEqual(self.compile()['status'],'DRAFT')
    def test_optional_context_needs_actual_uploaded_reference(self):
        self.shot['prompt_ir']['clauses'][0]['reference_asset_id']='NOT_UPLOADED';self.freeze();self.assertEqual(self.compile()['status'],'DRAFT')
    def test_visible_cup_cannot_clear_boundary_coverage(self):
        row=self.o.p['shots'][0];row.update(visible_start_keys=[],visible_end_keys=[],screen_start={},screen_end={});self.freeze()
        self.assertEqual(self.compile()['status'],'DRAFT')
    def test_cannot_override_all_hard_invariants_to_soft(self):
        self.shot['prompt_ir']['priority']['hard']=[];self.assertEqual(self.compile()['status'],'DRAFT')
    def test_moving_camera_cannot_hide_in_fixed_sequence_plan(self):
        self.shot['camera_motion']='orbit';self.freeze();self.assertEqual(self.compile()['status'],'DRAFT')
    def test_v42_readiness_never_claims_media_pass(self):
        out=self.compile();self.assertEqual(out['readiness']['media'],'NOT_REVIEWED');self.assertFalse(out['executed'])
    def test_original_contradictory_prompt_blocks_without_exception(self):
        self.shot['policy_version']='4.1.0';self.shot['locked_prompt']='杯子保持在桌面左侧，位置不变。同时把同一个杯子移到桌面右侧。'
        self.assertEqual(self.compile()['status'],'DRAFT')


if __name__=='__main__':unittest.main()
