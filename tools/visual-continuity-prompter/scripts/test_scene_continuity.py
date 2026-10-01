from copy import deepcopy
import json
from pathlib import Path
import unittest
import scene_continuity as e
import prompt_nine as n
import continuity_tools as c
from fixtures_v42 import intent

ROOT = Path(__file__).resolve().parents[1]


class SceneStateTests(unittest.TestCase):
    def setUp(self):
        self.b = json.loads((ROOT/'examples/ensemble-demo.json').read_text())
    def rows(self): return self.b['view_plan']['windows'][0]['entities']
    def row(self, eid): return next(r for r in self.rows() if r['entity_id'] == eid)
    def test_valid_explicit_supporting_character(self): self.assertEqual(e.validate_bundle(self.b), [])
    def test_only_focal_whitelist_is_rejected(self):
        self.b['view_plan']['windows'][0]['expected_visible_ids']=['CHAR_A']; self.assertTrue(e.validate_bundle(self.b))
    def test_silent_character_missing_from_view_rows(self):
        self.b['view_plan']['windows'][0]['entities']=[r for r in self.rows() if r['entity_id']!='CHAR_B']; self.assertTrue(e.validate_bundle(self.b))
    def test_camera_cut_cannot_delete_character(self):
        del self.b['start_state']['entities']['CHAR_B']; self.assertTrue(e.validate_bundle(self.b))
    def test_camera_cut_cannot_close_door(self):
        self.b['start_state']['entities']['DOOR']['state']['open_state']='closed'; self.assertTrue(e.validate_bundle(self.b))
    def test_video_cannot_teleport_prop_without_event(self):
        self.b['end_state']['entities']['PROP_CUP']['state']['world_anchor']='FLOOR'; self.assertTrue(e.validate_bundle(self.b))
    def test_event_without_cause_rejected(self):
        self.b['events'][0]['cause_ref']=''; self.assertTrue(e.validate_bundle(self.b))
    def test_event_without_approval_rejected(self):
        self.b['events'][0]['approval_ref']=''; self.assertTrue(e.validate_bundle(self.b))
    def test_event_before_must_match(self):
        self.b['events'][0]['before']['state']['holding']=None; self.assertTrue(e.validate_bundle(self.b))
    def test_out_of_frame_is_still_present(self):
        self.assertEqual(e.validate_bundle(self.b), []); self.assertEqual(self.b['start_state']['entities']['CHAR_C']['presence'],'present')
    def test_unknown_not_assumed_outside(self):
        self.row('CHAR_B')['visibility']='unknown'; self.assertTrue(e.validate_bundle(self.b))
    def test_occlusion_needs_real_occluder(self):
        r=self.row('CHAR_B');r.update(visibility='occluded',visual_clause='',still_clause='',behavior_clause='');self.b['view_plan']['windows'][0]['expected_visible_ids'].remove('CHAR_B');self.assertTrue(e.validate_bundle(self.b))
    def test_valid_occlusion(self):
        r=self.row('CHAR_B');r.update(visibility='occluded',visual_clause='',still_clause='',behavior_clause='',occluder_id='DOOR');self.b['view_plan']['windows'][0]['expected_visible_ids'].remove('CHAR_B');self.assertEqual(e.validate_bundle(self.b), [])
    def test_partial_is_required_not_deleted(self):
        r=self.row('CHAR_B');r.update(visibility='partial',visible_parts='head and near shoulder');self.assertEqual(e.validate_bundle(self.b), []);self.assertIn('CHAR_B',e.visible_ids(self.b))
    def test_over_shoulder_extent_is_compiled_without_forbidding_authored_crop(self):
        self.row('CHAR_B').update(visibility='partial', visible_parts='左前景仅露出已声明人物的后脑和右肩')
        for image in (False, True):
            prompt = e.render_clauses(self.b, image=image)
            self.assertIn('可见范围仅限：左前景仅露出已声明人物的后脑和右肩', prompt)
            self.assertIn('保留已声明的局部、反射和正常构图裁切', prompt)
            self.assertIn('未声明的额外人物', prompt)
    def test_partial_needs_extent(self):
        self.row('CHAR_B')['visibility']='partial';self.assertTrue(e.validate_bundle(self.b))
    def test_reflection_is_one_entity_manifestation(self):
        self.row('CHAR_B').update(visibility='reflection_only',visible_parts='reflection in established mirror');self.assertEqual(e.validate_bundle(self.b), [])
        self.assertIn('可见范围仅限：reflection in established mirror', e.render_clauses(self.b))
    def test_present_cannot_be_marked_absent_to_pass(self):
        self.row('CHAR_B').update(visibility='absent',visual_clause='',still_clause='',behavior_clause='');self.b['view_plan']['windows'][0]['expected_visible_ids'].remove('CHAR_B');self.assertTrue(e.validate_bundle(self.b))
    def test_absent_requires_actual_exit_event(self):
        before=deepcopy(self.b['previous_state']['entities']['CHAR_B']);after=deepcopy(before);after['presence']='absent'
        self.b['cut']={'kind':'continuous','events':[{'event_id':'EXIT','entity_id':'CHAR_B','before':before,'after':after,'cause_ref':'script exit','approval_ref':'board approved'}]}
        self.b['start_state']['entities']['CHAR_B']=deepcopy(after);self.b['end_state']['entities']['CHAR_B']=deepcopy(after)
        self.row('CHAR_B').update(visibility='absent',visual_clause='',still_clause='',behavior_clause='');self.b['view_plan']['windows'][0]['expected_visible_ids'].remove('CHAR_B');self.assertEqual(e.validate_bundle(self.b), [])
    def test_no_invisible_details_emitted(self):
        p=e.render_clauses(self.b);self.assertIn('灰衣男子',p);self.assertNotIn('旁听丙',p);self.assertNotIn('BEHIND-CAMERA',p)
    def test_image_clause_is_start_state_not_motion(self):
        p=e.render_clauses(self.b,image=True);self.assertIn('双手自然下垂',p);self.assertNotIn('平稳抬杯至胸前',p)
    def test_video_preserves_window_start_state_before_its_action(self):
        row=self.row('CHAR_A')
        prompt=e.render_clauses(self.b)
        self.assertIn(row['still_clause'],prompt)
        self.assertLess(prompt.index(row['still_clause']),prompt.index(row['behavior_clause']))
        self.assertIn('门扇开启',prompt)
        self.assertIn('本段起始状态：',prompt)
        self.assertIn('本段动作：',prompt)
    def test_photo_content_is_separate_from_live_cast_and_keeps_pose(self):
        for snap in ('previous_state','start_state','end_state'):
            self.b[snap]['entities']['DOOR']['kind']='prop'
        self.row('DOOR').update(visual_clause='墙屏边框内的一张单人平面照片',
            still_clause='照片中青年双手自然下垂，穿灰色上衣',
            behavior_clause='全段保持同一张照片和原有姿势')
        prompt=e.render_clauses(self.b)
        self.assertIn('物件与画内内容：墙屏边框内的一张单人平面照片',prompt)
        self.assertIn('照片中青年双手自然下垂',prompt)
        self.assertIn('现场人物：',prompt)
        self.assertNotIn('现场人物：墙屏',prompt)
    def test_duplicate_row_rejected(self):
        self.rows().append(deepcopy(self.rows()[0]));self.assertTrue(e.validate_bundle(self.b))
    def test_window_gaps_rejected(self):
        self.b['view_plan']['windows'][0]['end_s']=2;self.assertTrue(e.validate_bundle(self.b))
    def test_invalid_duration_rejected(self):
        for value in (float('nan'),float('inf'),-1,True,'4'):
            with self.subTest(value=value):
                b=deepcopy(self.b);b['duration_s']=value;self.assertTrue(e.validate_bundle(b))
    def test_inventory_scope_must_be_reviewed(self):
        self.b['view_plan']['inventory_basis_ref']=None;self.assertTrue(e.validate_bundle(self.b))
    def observation(self):
        return {'ensemble_sha256':e.digest(self.b),'temporal_basis':'synthetic full interval report; not real video', 'windows':[{'window_id':'W01','full_frame_result':'PASS','unexpected_visible_entities':[], 'entities':{i:{'result':'PASS','observation':'synthetic check'} for i in self.b['start_state']['entities']}}]}
    def test_complete_observation(self): self.assertEqual(e.check_observation(self.b,self.observation()),[])
    def test_observation_missing_support(self):
        o=self.observation();del o['windows'][0]['entities']['CHAR_B'];self.assertTrue(e.check_observation(self.b,o))
    def test_observed_disappearance_fails(self):
        o=self.observation();o['windows'][0]['entities']['CHAR_B']['result']='FAIL';self.assertTrue(e.check_observation(self.b,o))
    def test_unexpected_extra_character_fails(self):
        o=self.observation();o['windows'][0]['unexpected_visible_entities']=['unexpected figure'];self.assertTrue(e.check_observation(self.b,o))
    def test_observation_version_stale(self):
        o=self.observation();self.b['focus_ids']=['CHAR_B'];self.assertTrue(e.check_observation(self.b,o))
    def test_no_temporal_claim_from_only_first_frame(self):
        o=self.observation();o.pop('temporal_basis');self.assertTrue(e.check_observation(self.b,o));self.assertEqual(e.check_observation(self.b,o,True),[])
    def test_presence_change_needs_window_boundary(self):
        before=deepcopy(self.b['start_state']['entities']['CHAR_B']);after=deepcopy(before);after['presence']='absent'
        self.b['events'].insert(0,{'event_id':'EXIT','entity_id':'CHAR_B','at_s':2,'before':before,'after':after,'cause_ref':'exit','approval_ref':'approved'})
        self.b['end_state']['entities']['CHAR_B']=deepcopy(after);self.assertTrue(e.validate_bundle(self.b))
    def test_ordered_windows_support_reappearance(self):
        w=deepcopy(self.b['view_plan']['windows'][0]);w['end_s']=2
        r=next(r for r in w['entities'] if r['entity_id']=='CHAR_B');r.update(visibility='occluded',occluder_id='DOOR',visual_clause='',still_clause='',behavior_clause='');w['expected_visible_ids'].remove('CHAR_B')
        w2=deepcopy(self.b['view_plan']['windows'][0]);w2.update(window_id='W02',start_s=2)
        self.b['view_plan']['windows']=[w,w2];self.assertEqual(e.validate_bundle(self.b),[]);self.assertIn('灰衣男子',e.render_clauses(self.b))


class CompilerIntegration(unittest.TestCase):
    def setUp(self):
        self.s=json.loads((ROOT/'examples/video-shot-nine.json').read_text())
        self.b=json.loads((ROOT/'examples/ensemble-demo.json').read_text());self.b['duration_s']=self.s['video']['duration_s'];self.b['view_plan']['windows'][0]['end_s']=self.b['duration_s']
        for k in ('shot_id','scene_id','scene_version','view_id'):self.b['scope'][k]=self.s[k]
        self.s['ensemble']=self.b;self.s['ensemble_required']=True;self.bind()
    def bind(self):self.s['prompt9']['source_contract_sha256']=n.source_digest(self.s)
    def test_compiler_mentions_background_actor(self):self.assertIn('灰衣男子',n.render_nine(self.s))
    def test_original_render_routes_support(self):self.assertIn('灰衣男子',c.render_prompt({},self.s))
    def test_legacy_non_nine_can_use_bundle(self):
        self.s.pop('prompt9');self.assertIn('灰衣男子',c.render_prompt({},self.s))
    def test_changed_bundle_invalidates_prompt(self):
        self.b['focus_ids']=['CHAR_B'];self.assertTrue(n.validate_nine(self.s))
    def test_missing_required_bundle_rejected(self):
        self.s.pop('ensemble');self.bind();self.assertTrue(n.validate_nine(self.s))
    def test_scope_mismatch_rejected(self):
        self.b['scope']['view_id']='another camera';self.bind();self.assertTrue(n.validate_nine(self.s))
    def test_object_only_cannot_hide_visible_background_actor(self):
        self.s['insert_policy']={'kind':'object_only','visible_entity_ids':['PROP_CUP'],'offscreen_aliases':['旁听丙'],'post_audio_separate':True};self.bind();self.assertTrue(n.validate_nine(self.s))
    def test_wrong_duration_rejected(self):
        self.s['video']['duration_s']+=1;self.bind();self.assertTrue(n.validate_nine(self.s))
    def test_locked_prompt_cannot_drop_visible_inventory_or_behavior(self):
        complete = e.render_clauses(self.b)
        row = next(r for r in self.b['view_plan']['windows'][0]['entities'] if r['entity_id'] == 'CHAR_B')
        prop = next(r for r in self.b['view_plan']['windows'][0]['entities'] if r['entity_id'] == 'PROP_CUP')
        for prompt in ('A quiet empty room.',
                        complete.replace(e.render_entity_clause(row), ''),
                        complete.replace(e.render_entity_clause(prop), ''),
                        complete.replace(row['still_clause'], ''),
                        complete.replace(row['behavior_clause'], '')):
            with self.subTest(prompt=prompt):
                self.s['locked_prompt'] = prompt
                with self.assertRaisesRegex(ValueError, 'frozen visible block'):
                    c.render_prompt({}, self.s)
        self.s['locked_prompt'] = complete
        self.assertEqual(c.render_prompt({}, self.s), complete)
    def test_frozen_partial_and_reflected_extents_are_preserved(self):
        row = next(r for r in self.b['view_plan']['windows'][0]['entities'] if r['entity_id'] == 'CHAR_B')
        for visibility in ('partial', 'reflection_only'):
            with self.subTest(visibility=visibility):
                row.update(visibility=visibility, visible_parts='仅保留已声明的左肩局部')
                complete = e.render_clauses(self.b)
                self.s['locked_prompt'] = complete
                self.assertEqual(c.render_prompt({}, self.s), complete)
                self.assertTrue(c.inspect_final_prompt(self.s, complete.replace(row['visible_parts'], '')))
    def test_locked_windows_keep_contents_times_and_order(self):
        first = self.b['view_plan']['windows'][0]
        second = deepcopy(first)
        first['end_s'] = 2
        second.update(window_id='W02', start_s=2)
        self.b['view_plan']['windows'].append(second)
        complete = e.render_clauses(self.b)
        marker = f'2–{self.b["duration_s"]}秒画内延续'
        left, _, right = complete.partition(marker)
        for prompt in (left, complete.replace(marker, '0–2秒画内延续'), marker + right + left):
            with self.subTest(prompt=prompt):
                self.assertTrue(n.inspect_prompt(self.s, prompt))
        self.assertEqual(n.inspect_prompt(self.s, left + '\n镜头保持原位。\n' + marker + right), [])
    def test_spoken_frozen_block_is_not_visual_coverage(self):
        block = e.render_clauses(self.b)
        self.s['audio_plan']['native_spoken_lines'] = [
            {'line_id': 'L1', 'speaker_description': '青衣青年',
             'voice_description': '平稳男声', 'text_spoken': block}]
        self.assertTrue(n.inspect_prompt(self.s, '只说：' + json.dumps(block, ensure_ascii=False)))
        for speech_format in ('literal', 'colon'):
            with self.subTest(speech_format=speech_format):
                clause, backend = self.ir_speech(speech_format)
                clause.update(text='青衣青年说：' + block, text_spoken=block)
                self.s['prompt_ir'].update(clauses=[clause], priority={'hard': ['line'], 'soft': []}, must_show=['line'])
                self.s['locked_prompt'] = c._prompt_contract.compile_ir(self.s['prompt_ir'], backend)['prompt']
                self.assertTrue(c.inspect_final_prompt(self.s, self.s['locked_prompt'], {'prompt_backend': backend}))
    def test_image_block_uses_only_first_window_and_still_state(self):
        first = self.b['view_plan']['windows'][0]
        second = deepcopy(first)
        first['end_s'] = 2
        second.update(window_id='W02', start_s=2)
        self.b['view_plan']['windows'].append(second)
        self.s.update(mode='edit_same_view', locked_prompt=e.render_clauses(self.b, image=True))
        self.assertEqual(c.render_prompt({}, self.s), self.s['locked_prompt'])
    def test_all_hidden_and_legacy_shots_do_not_require_visible_block(self):
        for row in self.b['view_plan']['windows'][0]['entities']:
            row.update(visibility='out_of_frame', visual_clause='', still_clause='', behavior_clause='')
        self.b['view_plan']['windows'][0]['expected_visible_ids'] = []
        self.b['focus_ids'] = []
        self.s['locked_prompt'] = '镜头只拍天花板。'
        self.assertEqual(c.render_prompt({}, self.s), self.s['locked_prompt'])
        self.s.pop('ensemble'); self.s.pop('ensemble_required')
        self.assertEqual(c.render_prompt({}, self.s), self.s['locked_prompt'])
    def test_ordinary_dialogue_shot_blocks_offscreen_identity_in_all_compilers(self):
        for snap in ('previous_state', 'start_state', 'end_state'):
            self.b[snap]['entities']['CHAR_C']['aliases'] = ['韦立成', '韦薇', '父女俩']
        for leak in ('父女俩就在画外', '不要画出韦立成', '参考图中的韦薇在镜头外'):
            with self.subTest(leak=leak):
                self.s['prompt9']['dimensions']['space']['text'] = leak
                self.bind()
                with self.assertRaisesRegex(ValueError, 'private invisible alias'):
                    c.render_prompt({}, self.s)
                legacy = deepcopy(self.s)
                legacy.pop('prompt9')
                legacy['change_request'] = leak
                with self.assertRaisesRegex(ValueError, 'private invisible alias'):
                    c.render_prompt({}, legacy)
                locked = deepcopy(self.s)
                locked['locked_prompt'] = leak
                with self.assertRaisesRegex(ValueError, 'private invisible alias'):
                    c.render_prompt({}, locked)
    def test_gaze_towards_offscreen_position_does_not_invent_a_person(self):
        self.s['prompt9']['dimensions']['space']['text'] = '中景，头向画右偏，眼睛看镜头右侧的画外某处'
        self.bind()
        self.assertIn('眼睛看镜头右侧', c.render_prompt({}, self.s))
    def test_english_alias_next_to_chinese_direction_is_blocked(self):
        for snap in ('previous_state', 'start_state', 'end_state'):
            self.b[snap]['entities']['CHAR_C']['aliases'] = ['Ann']
        for prompt in ('Ann站在画外', '不要画出Ann', '不要画出Ann和其他人'):
            with self.subTest(prompt=prompt):
                self.assertTrue(n.inspect_prompt(self.s, prompt))
    def test_english_alias_does_not_match_longer_english_identifier(self):
        for snap in ('previous_state', 'start_state', 'end_state'):
            self.b[snap]['entities']['CHAR_C']['aliases'] = ['Ann']
        for prompt in ('Anna站在门边', 'Annabelle说话', '演员编号Ann_2', 'JoAnn在左边'):
            with self.subTest(prompt=prompt):
                self.assertEqual(n.inspect_prompt(self.s, e.render_clauses(self.b) + '\n' + prompt), [])
    def test_exact_spoken_name_allowed_but_visual_directions_still_checked(self):
        line = {'line_id': 'L1', 'speaker_description': '青衣青年', 'voice_description': '平稳男声',
                'text_spoken': '旁听丙，你承诺的奖金呢？'}
        self.s['audio_plan']['native_spoken_lines'] = [line]
        self.bind()
        prompt = c.render_prompt({}, self.s)
        self.assertIn('旁听丙，你承诺的奖金呢？', prompt)
        self.assertEqual(n.inspect_prompt(self.s, prompt), [])
        # Rewrites pass through this same guard; quoting a spoken name does not
        # exempt an additional visual instruction about that invisible person.
        self.assertTrue(n.inspect_prompt(self.s, prompt + '\n旁听丙站在镜头外。'))
    def ir_speech(self, speech_format):
        ir, backend = intent()
        backend['speech_format'] = speech_format
        spoken = '旁听丙，你承诺的奖金呢？'
        clause = {'id': 'line', 'kind': 'speech', 'text': '青衣青年说：' + spoken,
                  'text_spoken': spoken, 'speaker': '青衣青年', 'required': True}
        visual = {'id': 'visible', 'kind': 'evidence', 'text': e.render_clauses(self.b), 'required': True}
        ir.update(clauses=[visual, clause], priority={'hard': ['visible', 'line'], 'soft': []}, must_show=['visible'])
        self.s.update(policy_version='4.2.0', prompt_ir=ir,
                      locked_prompt=c._prompt_contract.compile_ir(ir, backend)['prompt'])
        return clause, backend
    def test_backend_speech_formats_allow_exact_name_only_in_spoken_payload(self):
        for speech_format in ('colon', 'literal'):
            with self.subTest(speech_format=speech_format):
                _, backend = self.ir_speech(speech_format)
                profile = {'prompt_backend': backend}
                prompt = c.render_prompt({}, self.s, profile)
                self.assertIn('旁听丙，你承诺的奖金呢？', prompt)
                self.assertEqual(c.inspect_final_prompt(self.s, prompt, profile), [])
                self.assertTrue(c.inspect_final_prompt(self.s, prompt + '\n旁听丙站在镜头外。', profile))
    def test_backend_speech_formats_do_not_exempt_speaker_or_delivery(self):
        for speech_format in ('colon', 'literal'):
            for field, value in (('speaker', '旁听丙'), ('delivery', '想着旁听丙，放低声音')):
                with self.subTest(speech_format=speech_format, field=field):
                    clause, backend = self.ir_speech(speech_format)
                    clause[field] = value
                    if speech_format == 'colon' and field == 'speaker':
                        with self.assertRaisesRegex(ValueError, 'colon speech requires an exact supported wrapper'):
                            c._prompt_contract.compile_ir(self.s['prompt_ir'], backend)
                        continue
                    self.s['locked_prompt'] = c._prompt_contract.compile_ir(self.s['prompt_ir'], backend)['prompt']
                    with self.assertRaisesRegex(ValueError, 'private invisible alias'):
                        c.render_prompt({}, self.s, {'prompt_backend': backend})
    def test_visible_reflection_and_photo_aliases_remain_allowed(self):
        row = next(r for r in self.b['view_plan']['windows'][0]['entities'] if r['entity_id'] == 'CHAR_C')
        row.update(visibility='reflection_only', visible_parts='屏幕中固定照片里的脸',
                   visual_clause='屏幕显示旁听丙的固定照片', still_clause='保持同一照片', behavior_clause='全程保持同一照片')
        self.b['view_plan']['windows'][0]['expected_visible_ids'].append('CHAR_C')
        self.bind()
        self.assertIn('屏幕显示旁听丙的固定照片', c.render_prompt({}, self.s))
    def test_visible_photo_alias_can_refer_to_an_invisible_real_person(self):
        # A visible photo is a prop; its subject need not physically enter shot.
        for snap in ('previous_state', 'start_state', 'end_state'):
            self.b[snap]['entities']['DOOR']['aliases'] = ['旁听丙']
        row = next(r for r in self.b['view_plan']['windows'][0]['entities'] if r['entity_id'] == 'DOOR')
        row['visual_clause'] = '保留背景门上的旁听丙照片'
        self.bind()
        prompt = c.render_prompt({}, self.s)
        self.assertIn('旁听丙照片', prompt)
        self.assertTrue(n.inspect_prompt(self.s, prompt + '\n旁听丙站在镜头外。'))
    def test_visible_alias_without_bound_description_cannot_whitelist_a_person(self):
        for snap in ('previous_state', 'start_state', 'end_state'):
            self.b[snap]['entities']['DOOR']['aliases'] = ['旁听丙']
        self.assertTrue(n.inspect_prompt(self.s, '旁听丙站在镜头外。'))


if __name__=='__main__':unittest.main()
