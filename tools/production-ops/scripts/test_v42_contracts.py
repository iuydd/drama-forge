"""Counterexamples and legal near-misses; fixtures never represent watched media."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
import brain_handoff as b
import fidelity_contract as f
import sequence_continuity as s
import prompt_contract as p
from fixtures_v4 import Fixture
from fixtures_v42 import intent
import test_sequence_continuity as legacy


class Regression42Tests(unittest.TestCase):
    def test_direction_without_optional_equals_rejects_contradiction(self):
        with tempfile.TemporaryDirectory() as d:
            x=Fixture(d,['direction']);x.contract['requirements'][0].pop('equals');x.save_contract();r=x.review()
            x.point(r,'direction')['values']={'screen_heading':'left','world_heading':'-X'}
            self.assertTrue(f.check_review(r,x.context(),'video',x.record(x.media_name)['sha256'],x.root,b.verify_record)[1])
    def test_missing_direction_observations_is_blocked_in_v42(self):
        with tempfile.TemporaryDirectory() as d:
            x=Fixture(d,['direction']);x.contract['policy_version']='4.2.0';x.save_contract();r=x.review()
            self.assertTrue(f.check_review(r,x.context(),'video',x.record(x.media_name)['sha256'],x.root,b.verify_record)[0])
    def test_complete_v42_direction_values_accept(self):
        with tempfile.TemporaryDirectory() as d:
            x=Fixture(d,['direction']);x.contract['policy_version']='4.2.0';x.save_contract();r=x.review()
            q=x.contract['requirements'][0];x.point(r,'direction')['values']=f.derived_assertions(q,'video','observed_state')
            self.assertEqual(f.check_review(r,x.context(),'video',x.record(x.media_name)['sha256'],x.root,b.verify_record),([],[]))
    def test_reversed_performance_windows_fail(self):
        with tempfile.TemporaryDirectory() as d:
            x=Fixture(d,['performance']);r=x.review()
            for name,at in [('before',80),('trigger',60),('after',20)]:x.point(r,'performance',name)['locator'].update(start=at,end=at+10)
            self.assertTrue(f.check_review(r,x.context(),'video',x.record(x.media_name)['sha256'],x.root,b.verify_record)[1])
    def test_performance_contrast_can_span_trigger(self):
        with tempfile.TemporaryDirectory() as d:
            x=Fixture(d,['performance']);r=x.review()
            for name,at in [('before',10),('trigger',20),('after',30)]:x.point(r,'performance',name)['locator'].update(start=at,end=at+10)
            self.assertEqual(f.check_review(r,x.context(),'video',x.record(x.media_name)['sha256'],x.root,b.verify_record),([],[]))
    def test_unchanged_world_view_return_projection_fail(self):
        plan=legacy.fixture();plan['shots'][2]['screen_start']['car_heading']='left'
        self.assertTrue(any('contradictory screen' in e for e in s.resolve(plan)[1]))
    def test_approved_other_view_projection_can_reverse(self):
        plan=legacy.fixture();row=plan['shots'][2];row.update(view_id='V2',axis_change_approval='TEST_ONLY')
        row['screen_start']['car_heading']='left';row['screen_end']['car_heading']='left'
        self.assertEqual(s.resolve(plan)[1],[])
    def test_unknown_projection_dependency_rejected(self):
        plan=legacy.fixture();plan['policy_version']='4.2.0';plan['shots'][0]['projection_dependencies']={'car_heading':['NOT_REGISTERED']}
        self.assertTrue(s.resolve(plan)[1])
    def test_specific_contradictory_prompt(self):
        self.assertTrue(p.obvious_contradictions('杯子保持在桌面左侧，位置不变。同时把同一个杯子移到桌面右侧。'))
    def test_successive_movement_not_contradiction(self):
        self.assertEqual(p.obvious_contradictions('杯子暂时停在左侧，然后拿起放到右侧。'),[])
    def test_new_object_invariant_conflict_uses_fact_keys(self):
        ir,bk=intent();ir['invariant_keys']=['SUITCASE.handle'];ir['clauses'][1]['write_keys']=['SUITCASE.handle']
        self.assertTrue(p.validate_ir(ir,bk))


class Prompt42Tests(unittest.TestCase):
    def test_motion_route_omits_only_reference_covered_optional_context(self):
        ir,bk=intent();r=p.compile_ir(ir,bk)
        self.assertNotIn('scene context',r['prompt']);self.assertIn('cup position',r['prompt']);self.assertEqual(len(r['omitted']),1)
    def test_text_to_video_keeps_context(self):
        ir,bk=intent('video_t2v');self.assertIn('scene context',p.compile_ir(ir,bk)['prompt'])
    def test_new_image_keeps_context(self):
        ir,bk=intent('image_new');self.assertIn('scene context',p.compile_ir(ir,bk)['prompt'])
    def test_required_context_never_dropped(self):
        ir,bk=intent();ir['clauses'][0]['required']=True;ir['priority']['hard'].append('context');ir['priority']['soft']=[]
        self.assertIn('scene context',p.compile_ir(ir,bk)['prompt'])
    def test_unknown_adapter_blocks(self):
        ir,bk=intent();bk['profile_id']='OTHER';self.assertTrue(p.validate_ir(ir,bk))
    def test_no_silent_prompt_truncation(self):
        ir,bk=intent();bk['max_prompt_bytes']=4
        with self.assertRaises(ValueError):p.compile_ir(ir,bk)
    def test_priority_must_cover_all_hard_clauses(self):
        ir,bk=intent();ir['priority']['hard'].remove('lock');self.assertTrue(p.validate_ir(ir,bk))
    def test_conflicting_unresolved_constraints_block(self):
        ir,bk=intent();ir['unresolved_conflicts']=['face and full text cannot both fit'];self.assertTrue(p.validate_ir(ir,bk))
    def test_still_cannot_contain_temporal_operation(self):
        ir,bk=intent('image_edit');ir['clauses'][1]['kind']='action';self.assertTrue(p.validate_ir(ir,bk))
    def test_speech_adapter_preserves_words(self):
        ir,bk=intent();bk['speech_format']='colon'
        ir['clauses'].append({'id':'line','kind':'speech','text':'只说：我跟他说什么早上好。','text_spoken':'我跟他说什么早上好。','speaker':'大爷','delivery':'confused self-question, not a greeting','required':True})
        ir['priority']['hard'].append('line');self.assertIn('大爷 says: 我跟他说什么早上好。',p.compile_ir(ir,bk)['prompt'])
    def speech_intent(self, speech_format='literal'):
        ir,bk=intent();bk['speech_format']=speech_format
        clause={'id':'line','kind':'speech','text':'只说：先把名单给我。',
            'text_spoken':'先把名单给我。','speaker':'灰衣成年人',
            'delivery':'Lower the voice after noticing the correction.','required':True}
        ir['clauses'].append(clause);ir['priority']['hard'].append('line')
        return ir,bk,clause
    def test_colon_rejects_unbound_guidance_without_changing_literal(self):
        for wrapper in ('声线偏低，略带沙哑；只说：{}', '只说：{}\n短语自然连读。',
                        '只说：{}\nDelivery, not spoken: Lower the voice after noticing the correction. Then pause.'):
            with self.subTest(wrapper=wrapper):
                ir,bk,line=self.speech_intent('colon')
                line['text'] = wrapper.format(line['text_spoken'])
                original=deepcopy(ir)
                self.assertTrue(any('colon speech requires an exact supported wrapper' in e
                                    for e in p.validate_ir(ir,bk)))
                with self.assertRaisesRegex(ValueError, 'move extra guidance to speaker/delivery or separate clauses'):
                    p.compile_ir(ir,bk)
                self.assertEqual(ir,original)
                bk['speech_format']='literal'
                self.assertIn(line['text'],p.compile_ir(ir,bk)['prompt'])
                self.assertEqual(ir,original)
    def test_colon_standard_wrappers_preserve_bound_voice_and_single_speech(self):
        for wrapper in ('{}', '只说：{}', '灰衣成年人说：{}', '灰衣成年人 says: {}'):
            for serialized_delivery in (False,True):
                with self.subTest(wrapper=wrapper,serialized_delivery=serialized_delivery):
                    ir,bk,line=self.speech_intent('colon')
                    line['delivery']='音色偏低，略带沙哑；短语自然连读，重音落在名单。'
                    directive='Delivery, not spoken: '+line['delivery']
                    line['text']=wrapper.format(line['text_spoken'])
                    if serialized_delivery: line['text']+='\n'+directive
                    prompt=p.compile_ir(ir,bk)['prompt']
                    self.assertIn(line['speaker']+' says: '+line['text_spoken']+'\n'+directive,prompt)
                    self.assertEqual(prompt.count(line['text_spoken']),1)
                    self.assertEqual(prompt.count(directive),1)
    def test_colon_rejects_mismatched_speaker_and_repeated_speech_wrappers(self):
        for wrapper in ('另一人说：{}', '灰衣成年人 says: {}\n{}'):
            with self.subTest(wrapper=wrapper):
                ir,bk,line=self.speech_intent('colon')
                line['text']=wrapper.format(line['text_spoken'],line['text_spoken'])
                with self.assertRaisesRegex(ValueError, 'colon speech requires an exact supported wrapper'):
                    p.compile_ir(ir,bk)
    def test_both_speech_formats_keep_delivery_and_exact_spoken_text(self):
        for speech_format in ('literal','colon'):
            with self.subTest(speech_format=speech_format):
                ir,bk,line=self.speech_intent(speech_format)
                original=deepcopy(ir)
                prompt=p.compile_ir(ir,bk)['prompt']
                self.assertIn(line['text_spoken'],prompt)
                self.assertEqual(prompt.count('Delivery, not spoken: '+line['delivery']),1)
                self.assertEqual(ir,original)
    def test_existing_exact_delivery_block_is_not_duplicated(self):
        for speech_format in ('literal','colon'):
            with self.subTest(speech_format=speech_format):
                ir,bk,line=self.speech_intent(speech_format)
                line['delivery']='Start softly.\nEnd firmly.'
                directive='Delivery, not spoken: '+line['delivery']
                line['text']+='\n'+directive
                self.assertEqual(p.compile_ir(ir,bk)['prompt'].count(directive),1)
    def test_partial_delivery_match_does_not_suppress_the_authored_note(self):
        ir,bk,line=self.speech_intent()
        line['delivery']='Speak softly.'
        line['text']+='\nDelivery, not spoken: Speak softly. Then pause.'
        prompt=p.compile_ir(ir,bk)['prompt']
        self.assertIn('\nDelivery, not spoken: Speak softly.\n',prompt+'\n')
        self.assertIn('Delivery, not spoken: Speak softly. Then pause.',prompt)
    def test_spoken_delivery_text_does_not_replace_unspoken_guidance(self):
        for speech_format in ('literal','colon'):
            with self.subTest(speech_format=speech_format):
                ir,bk,line=self.speech_intent(speech_format)
                line['delivery']='Stay calm.'
                directive='Delivery, not spoken: '+line['delivery']
                line['text_spoken']='Read this label:\n'+directive+'\nThat is the label.'
                line['text']='只说：'+line['text_spoken']
                prompt=p.compile_ir(ir,bk)['prompt']
                self.assertIn(line['text_spoken'],prompt)
                self.assertEqual(prompt.count(directive),2)
    def test_unsupported_native_speech_blocks(self):
        ir,bk=intent();bk['native_audio']=False
        ir['clauses'].append({'id':'line','kind':'speech','text':'Hi','text_spoken':'Hi','speaker':'A','required':False});self.assertTrue(p.validate_ir(ir,bk))
    def test_parallel_hand_operations_conflict(self):
        a={'actor_id':'A','effector':'right_hand','action_id':'write','start':0,'end':1,'exclusive':True};c=dict(a,action_id='hold_cup')
        self.assertTrue(p.resource_conflicts([a,c]))
    def test_adjacent_hand_operations_do_not_conflict(self):
        a={'actor_id':'A','effector':'right_hand','action_id':'write','start':0,'end':1,'exclusive':True};c=dict(a,action_id='hold_cup',start=1,end=2)
        self.assertEqual(p.resource_conflicts([a,c]),[])
    def test_approved_joint_grip_allowed(self):
        a={'actor_id':'A','effector':'right_hand','action_id':'grip','start':0,'end':1,'exclusive':True,'shared_group':'assembly','shared_approval':'TEST'}
        self.assertEqual(p.resource_conflicts([a,dict(a,action_id='press')]),[])
    def test_exact_readiness_is_not_semantic_model_claim(self):
        ir,bk=intent();self.assertFalse(p.compile_ir(ir,bk)['semantic_quality_verified'])


if __name__=='__main__':unittest.main()
