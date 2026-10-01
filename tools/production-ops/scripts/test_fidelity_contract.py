"""User-reported failure patterns are tested as records, NOT actual videos."""
from copy import deepcopy
import tempfile
from pathlib import Path
import unittest
import brain_handoff as b
import fidelity_contract as f
from fixtures_v4 import Fixture, contract


class FidelityTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.x=Fixture(self.tmp.name)
        self.r=self.x.review()
    def tearDown(self):self.tmp.cleanup()
    def check(self,stage='video',review=None):
        return f.check_review(self.r if review is None else review,self.x.context(),stage,
            self.x.record(self.x.media_name)['sha256'],self.x.root,b.verify_record)
    def test_complete_contract(self):self.assertEqual(f.validate(self.x.contract),[])
    def test_all_stages_have_actual_records(self):
        for stage in f.STAGES:
            with self.subTest(stage=stage):self.assertEqual(self.check(stage,self.x.review(stage)),([],[]))
    def test_blank_environment_does_not_invent_six_risks(self):self.assertEqual(f.validate(contract([])),[])
    def test_missing_risk_family(self):
        del self.x.contract['risks']['gaze'];self.assertTrue(f.validate(self.x.contract))
    def test_unknown_applicability(self):
        self.x.contract['risks']['gaze']['applicable']=None;self.assertTrue(f.validate(self.x.contract))
    def test_false_applicability_cannot_hide_requirements(self):
        self.x.contract['risks']['gaze']['applicable']=False;self.assertTrue(f.validate(self.x.contract))
    def test_missing_risk_basis(self):
        self.x.contract['risks']['gaze']['basis']='';self.assertTrue(f.validate(self.x.contract))
    def test_missing_expected_values(self):
        self.x.contract['requirements'][0]['expected']={};self.assertTrue(f.validate(self.x.contract))
    def test_unknown_release_applicability(self):
        req=next(r for r in self.x.contract['requirements'] if r['category']=='action')
        req['expected']['release_required']=None;self.assertTrue(f.validate(self.x.contract))
    def test_contact_evidence_not_optional(self):
        req=next(r for r in self.x.contract['requirements'] if r['category']=='action')
        req['points']['video'].remove('contact');self.assertTrue(f.validate(self.x.contract))
    def test_final_readability_not_optional(self):
        req=next(r for r in self.x.contract['requirements'] if r['category']=='text')
        req['points']['final']=[];self.assertTrue(f.validate(self.x.contract))
    def test_draft_contract_blocked(self):
        self.x.contract['status']='DRAFT';self.assertTrue(f.validate(self.x.contract))
    def test_example_not_production(self):
        self.x.contract['example_only']=True;self.assertTrue(f.validate(self.x.contract))
    def test_car_nose_reversal_even_if_overall_pass(self):
        self.x.point(self.r,'direction')['values']['screen_heading']='left';self.assertTrue(self.check()[1])
    def test_legal_screen_reversal_can_be_frozen(self):
        req=next(r for r in self.x.contract['requirements'] if r['category']=='direction')
        req['expected'].update(screen_heading='left',axis_side='B',transition_basis='approved re-establishing view')
        req['equals']['video']['observed_state']['screen_heading']='left';self.x.save_contract()
        self.assertEqual(self.check(review=self.x.review()),([],[]))
    def test_prop_gaze_at_camera_rejected(self):
        self.x.point(self.r,'gaze')['values']['target_id']='CAMERA';self.assertTrue(self.check()[1])
    def test_dialogue_gaze_wrong_target_rejected(self):
        req=next(r for r in self.x.contract['requirements'] if r['category']=='gaze')
        req['expected']['target_id']='MOTHER';req['equals']['video']['observed_state']['target_id']='MOTHER'
        self.x.save_contract();r=self.x.review();self.x.point(r,'gaze')['values']['target_id']='WALL'
        self.assertTrue(self.check(review=r)[1])
    def test_writing_without_ink_rejected(self):
        self.x.point(self.r,'action','change')['values']['visible_change']=False;self.assertTrue(self.check()[1])
    def test_tape_waving_without_attachment_rejected(self):
        self.x.point(self.r,'action','after_release')['values']['persistent_result']=False;self.assertTrue(self.check()[1])
    def test_garbled_hanzi_rejected(self):
        r=self.x.review('final');self.x.point(r,'text')['values']['text']='请轻攵'
        self.assertTrue(self.check('final',r)[1])
    def test_blank_text_rejected(self):
        r=self.x.review('final');self.x.point(r,'text')['values']['text']=''
        self.assertTrue(self.check('final',r)[1])
    def test_exact_text_no_homophone_normalization(self):
        r=self.x.review('final');self.x.point(r,'text')['values']['text']='请清放'
        self.assertTrue(self.check('final',r)[1])
    def test_poster_wrong_surface_rejected(self):
        self.x.point(self.r,'placement')['values']['surface_id']='WALL_B';self.assertTrue(self.check()[1])
    def test_poster_drift_rejected(self):
        self.x.point(self.r,'placement')['values']['local_anchor']='OTHER';self.assertTrue(self.check()[1])
    def test_greeting_stays_greeting_rejected(self):
        self.x.point(self.r,'performance','after')['values']['intent']='greeting';self.assertTrue(self.check()[1])
    def test_prosody_cannot_be_verified_by_stills(self):
        self.x.point(self.r,'performance','contrast')['modality']='image';self.assertTrue(self.check()[0])
    def test_unknown_is_not_pass(self):
        self.x.point(self.r,'gaze')['result']='UNKNOWN';self.assertTrue(self.check()[0])
    def test_explicit_fail_not_hidden_in_summary(self):
        self.x.point(self.r,'gaze')['result']='FAIL';self.assertTrue(self.check()[1])
    def test_missing_intermediate_point(self):
        self.r['shots'][0]['requirements'][0]['points'].pop(1);self.assertTrue(self.check()[0])
    def test_missing_actual_observation(self):
        self.x.point(self.r,'gaze')['observation']='';self.assertTrue(self.check()[0])
    def test_missing_actual_event_frame(self):
        del self.x.point(self.r,'action','contact')['event_frame'];self.assertTrue(self.check()[0])
    def test_reverse_action_order(self):
        self.x.point(self.r,'action','contact')['event_frame']=35;self.assertTrue(self.check()[1])
    def test_event_frame_outside_observed_window(self):
        self.x.point(self.r,'action','after_release')['event_frame']=101;self.assertTrue(self.check()[0])
    def test_stale_export_hash(self):
        self.r['subject_sha256']='0'*64;self.assertTrue(self.check()[0])
    def test_stale_point_hash(self):
        self.x.point(self.r,'gaze')['media_sha256']='0'*64;self.assertTrue(self.check()[0])
    def test_stale_contract(self):
        self.r['shots'][0]['contract_sha256']='0'*64;self.assertTrue(self.check()[0])
    def test_evidence_file_changed(self):
        (self.x.root/'proof.md').write_text('changed');self.assertTrue(self.check()[0])
    def test_wrong_stage(self):self.assertTrue(self.check('final')[0])
    def test_missing_equality_observation(self):
        self.x.point(self.r,'gaze')['values']={};self.assertTrue(self.check()[0])
    def test_bool_not_integer_for_frozen_values(self):
        self.x.point(self.r,'action','change')['values']['visible_change']=1;self.assertTrue(self.check()[1])
    def test_duplicate_requirement(self):
        self.x.contract['requirements'].append(deepcopy(self.x.contract['requirements'][0]));self.assertTrue(f.validate(self.x.contract))
    def test_observed_range_must_be_nonempty(self):
        self.x.point(self.r,'gaze')['locator']['end']=0;self.assertTrue(self.check()[0])


if __name__=='__main__':unittest.main()
