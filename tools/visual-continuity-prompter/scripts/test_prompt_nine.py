from copy import deepcopy
import json
from pathlib import Path
import unittest
import prompt_nine as n
import continuity_tools as c

ROOT=Path(__file__).resolve().parents[1]


class NineTests(unittest.TestCase):
    def setUp(self):self.s=json.loads((ROOT/'examples/video-shot-nine.json').read_text())
    def bind(self):self.s['prompt9']['source_contract_sha256']=n.source_digest(self.s)
    def insert(self):
        self.s['insert_policy']={'kind':'object_only','visible_entity_ids':['KEY'],
            'offscreen_aliases':['私有角色名'],'post_audio_separate':True}
        self.s['references']=[r for r in self.s['references'] if r['primary']]
        self.s['references'][0]['purpose']='桌面底图'
        self.s['relations']=[];self.s['preserve']=['桌面不变'];self.s['narrative_must_show']=['钥匙缺口']
        self.s['prompt9']['dimensions']['subject']['text']='桌面中央的一把铜钥匙'
        self.s['video']['action_beats']=[{'start_s':0,'end_s':self.s['video']['duration_s'],'action':'钥匙保持稳定'}]
        self.s['video']['end_state_description']='钥匙稳定可见';self.bind()
    def test_valid_nine(self):self.assertEqual(n.validate_nine(self.s),[])
    def test_exact_nine_missing(self):del self.s['prompt9']['dimensions']['space'];self.assertTrue(n.validate_nine(self.s))
    def test_extra_dimension_rejected(self):self.s['prompt9']['dimensions']['extra']={};self.assertTrue(n.validate_nine(self.s))
    def test_stale_action_contract(self):self.s['video']['duration_s']+=1;self.assertTrue(n.validate_nine(self.s))
    def test_derived_action_cannot_drift(self):self.s['prompt9']['dimensions']['choreography']['text']='other action';self.assertTrue(n.validate_nine(self.s))
    def test_style_comes_from_original_sentence(self):self.assertIn(self.s['style_lock']['prompt_sentence'],n.render_nine(self.s))
    def test_missing_source_not_accepted(self):self.s['prompt9']['dimensions']['space']['source']='';self.assertTrue(n.validate_nine(self.s))
    def test_optional_dimension_can_be_inapplicable(self):
        self.s['prompt9']['dimensions']['lighting'].update(state='not_applicable',text=None,reason='approved absence')
        self.assertEqual(n.validate_nine(self.s),[])
    def test_static_image_cannot_use_timeline_expansion(self):self.s['mode']='edit_same_view';self.bind();self.assertTrue(n.validate_nine(self.s))
    def test_render_uses_original_locks(self):
        self.s['preserve']=['EXACT_LOCK_MARKER'];self.bind();self.assertIn('EXACT_LOCK_MARKER',n.render_nine(self.s))
    def test_original_compiler_routes_nine(self):self.assertEqual(c.render_prompt({},self.s),n.render_nine(self.s))
    def test_insert_clean(self):self.insert();self.assertEqual(n.validate_nine(self.s),[])
    def test_alias_in_positive_prompt_blocked(self):
        self.insert();self.s['prompt9']['dimensions']['subject']['text']='私有角色名看着钥匙';self.assertTrue(n.validate_nine(self.s))
    def test_alias_in_negative_prompt_also_blocked(self):
        self.insert();self.s['prompt9']['dimensions']['stability']['text']='不要画私有角色名';self.assertTrue(n.validate_nine(self.s))
    def test_offframe_without_name_blocked(self):
        self.insert();self.s['prompt9']['dimensions']['space']['text']='有人站在画外';self.assertTrue(n.validate_nine(self.s))
    def test_final_rewrite_checked(self):
        self.insert();self.assertTrue(n.inspect_insert(self.s,'门外 off-screen person'))
    def test_reference_caption_checked(self):
        self.insert();self.s['references'][0]['purpose']='私有角色名房间';self.bind();self.assertTrue(n.validate_nine(self.s))
    def test_irrelevant_person_reference_blocked(self):
        self.insert();self.s['references'].append({'role':'identity','primary':False,'upload_index':2,'purpose':'person'});self.bind();self.assertTrue(n.validate_nine(self.s))
    def test_post_voice_preserved_outside_visual_prompt(self):
        self.insert();self.s['audio_plan']['post_voices']=[{'line_id':'L','speaker_description':'私有角色名','source_kind':'inner','text_spoken':'这是正确的心声。'}];self.bind()
        p=c.render_prompt({},self.s);self.assertNotIn('私有角色名',p);self.assertNotIn('这是正确的心声',p)
        self.assertEqual(self.s['audio_plan']['post_voices'][0]['line_id'],'L')
    def test_native_speech_insert_not_silently_dropped(self):
        self.insert();self.s['audio_plan']['native_spoken_lines']=[{'line_id':'L','speaker_description':'人','voice_description':'低声','text_spoken':'保留我'}];self.bind();self.assertTrue(n.validate_nine(self.s))
    def test_actual_camera_derived_not_invented(self):
        self.s['camera_motion']='planned_path';self.s['camera_motion_description']='ONLY_AUTHORIZED_PATH';self.bind();self.assertIn('ONLY_AUTHORIZED_PATH',n.render_nine(self.s))
    def test_legacy_prompt_unchanged_without_extension(self):
        self.s.pop('prompt9');self.assertIn('本次变化',c.render_prompt({},self.s))
    def test_legacy_insert_guard_still_enforced(self):
        self.insert();self.s.pop('prompt9');self.s['change_request']='私有角色名在画外'
        with self.assertRaises(ValueError):c.render_prompt({},self.s)
    def test_malformed_action_returns_errors(self):
        self.s['video']['action_beats']=[{}];self.bind();self.assertTrue(n.validate_nine(self.s))


if __name__=='__main__':unittest.main()
