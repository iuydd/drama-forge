"""Synthetic structural fixtures only; these tests do not watch user media."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
import cut_bridges as b
import edit_timeline as edit
import production_gates as g
import test_edit_timeline as et
import test_edit_gates as eg


def fixture(t=None):
    t = et.fixture() if t is None else t
    cuts = b.context_plan(t)
    for c in cuts:
        c.update(relation='continuous', category='reaction',
                 connection='The listener receives the preceding event.',
                 left_action_state='Gesture completed; same world state.',
                 right_action_state='Listener continues listening, then reacts.',
                 attention_emotion_link='Neutral interest becomes cautious attention.',
                 sound_link='The preceding line ends over the listener.',
                 linked_event_ids=['EV1','EV2'])
    return {'schema_version':'cut-bridges-1','status':'LOCKED','episode_id':t['episode_id'],
            'timeline_digest':b.digest(t),'cuts':cuts,
            'character_cues':[{'cue_id':'C1','character_id':'CHAR1','choice':'Ask before accepting.',
                              'observable_behavior':'Pauses the reaching hand.','protect':True,
                              'event_ids':['EV1']}],
            'note':'SYNTHETIC ENGINEERING FIXTURE; not actual footage or observation.'}


def report(bundle, evidence):
    return {'schema_version':'cut-bridges-review-1','bundle_digest':b.digest(bundle),
            'reviewer_id':'synthetic-fixture-not-real-viewer',
            'cuts':[{'cut_id':c['cut_id'],'binding_digest':b.digest(c),
                     'paired_context_viewed':True,'viewed_context':c['context'],
                     'checks':{k:{'result':'PASS','observation':'Synthetic coverage declaration only.'}
                               for k in b.ASPECTS}, 'evidence':[evidence]} for c in bundle['cuts']],
            'character_cues':[{'cue_id':c['cue_id'],'result':'PASS','evidence':[evidence],
                              'observation':'Synthetic cue observation only.'}
                             for c in bundle['character_cues'] if c['protect']]}


class BridgeDataTests(unittest.TestCase):
    def setUp(self): self.t=et.fixture(); self.b=fixture(self.t)
    def bad(self): self.assertTrue(b.validate_bundle(self.b,self.t))
    def test_valid_bundle(self): self.assertEqual(b.validate_bundle(self.b,self.t),[])
    def test_outgoing_edge_is_last_adopted_not_source_last(self):
        self.assertEqual(self.b['cuts'][0]['left']['edge_frame'],29)
    def test_incoming_edge_uses_adopted_in(self): self.assertEqual(self.b['cuts'][0]['right']['edge_frame'],12)
    def test_missing_cut(self): self.b['cuts']=[];self.bad()
    def test_duplicate_cut(self): self.b['cuts']*=2;self.bad()
    def test_added_cut(self):
        c=deepcopy(self.b['cuts'][0]);c['cut_id']='V2__V3';self.b['cuts'].append(c);self.bad()
    def test_stale_timeline(self): self.t['revision']='2';self.bad()
    def test_source_hash_changed(self): self.t['sources'][0]['sha256']='1'*64;self.bad()
    def test_old_source_adopted_range(self): self.b['cuts'][0]['left']['src_out']=29;self.bad()
    def test_source_last_frame_is_not_adopted_last(self): self.b['cuts'][0]['left']['edge_frame']=47;self.bad()
    def test_wrong_episode(self): self.b['episode_id']='EP-OTHER';self.bad()
    def test_no_locked_scope(self): self.b['status']='DRAFT';self.bad()
    def test_context_must_include_both_sides(self): self.b['cuts'][0]['context']=[24,42];self.bad()
    def test_context_out_of_bounds(self): self.b['cuts'][0]['context']=[-1,50];self.bad()
    def test_bool_frame_not_allowed(self): self.b['cuts'][0]['context']=[True,42];self.bad()
    def test_linked_event_requires_full_context(self): self.b['cuts'][0]['context']=[23,25];self.bad()
    def test_audio_event_mapping(self):
        self.assertEqual(b.event_windows(self.t,'EL1'),[[15,24]])
    def test_unknown_event(self): self.b['cuts'][0]['linked_event_ids']=['NO'];self.bad()
    def test_duplicate_linked_event(self): self.b['cuts'][0]['linked_event_ids']=['EV1','EV1'];self.bad()
    def test_unapproved_ellipsis(self): self.b['cuts'][0]['relation']='ellipsis';self.bad()
    def test_approved_ellipsis_supported(self):
        self.b['cuts'][0].update(relation='ellipsis',approved_transition_ref='PLAN-DRAFT-EXAMPLE',orientation_cue='Later, after the task.')
        self.assertEqual(b.validate_bundle(self.b,self.t),[])
    def test_no_extra_mandatory_character_detail(self): self.b['character_cues']=[];self.assertFalse(b.validate_bundle(self.b,self.t))
    def test_optional_character_detail_not_required(self):
        self.b['character_cues'][0].update(protect=False,event_ids=[]);self.assertFalse(b.validate_bundle(self.b,self.t))
    def test_protected_cue_must_map_to_event(self): self.b['character_cues'][0]['event_ids']=[];self.bad()
    def test_unknown_cue_event(self): self.b['character_cues'][0]['event_ids']=['NO'];self.bad()
    def test_protected_cue_cannot_map_to_optional_event(self):
        self.t['events'][0]['required']=False;self.b['timeline_digest']=b.digest(self.t);self.bad()
    def test_no_cuts_single_long_take(self):
        self.t['video']=self.t['video'][:1];self.t['duration_frames']=24
        self.t['audio']=[];self.t['audio_intent']='silent';self.t['video'][0]['visible_dialogue']=False
        self.t['sync_links']=[];self.t['event_orders']=[];self.t['events']=self.t['events'][:1]
        self.b=fixture(self.t);self.assertEqual(self.b['cuts'],[]);self.assertFalse(b.validate_bundle(self.b,self.t))
    def test_invalid_context_count(self):
        with self.assertRaises(ValueError):b.context_plan(self.t,True)
    def test_draft_context_is_plan_not_vision(self):
        self.t['status']='DRAFT';self.assertEqual(len(b.context_plan(self.t)),1)


class BridgeGateTests(unittest.TestCase):
    def setUp(self):
        self.old=eg.EditGateTests('test_complete_new_gate');self.old.setUp()
        self.root=self.old.root;self.s=self.old.s;self.r=self.old.r
        self.t=json.loads((self.root/'timeline.json').read_text())
        self.s['episode_id']=self.t['episode_id'];self.bundle=fixture(self.t)
        self.s['bridges_required']=True;self.save()
    def save(self):
        (self.root/'bridges.json').write_text(json.dumps(self.bundle))
        self.s['cut_bridges']=self.old.old.record('bridges.json')
        self.details=self.old.find('edit_cut_review')['details']
        self.details['bridge_review']=report(self.bundle,self.old.old.record('evidence.json'))
        self.old.refresh()
    def tearDown(self): self.old.tearDown()
    def run_gate(self): return g.gate(self.s,self.r,self.root)
    def test_valid_in_existing_review(self): self.assertEqual(self.run_gate()['status'],'ACCEPTED')
    def test_missing_binding(self): self.s.pop('cut_bridges');self.old.refresh();self.assertEqual(self.run_gate()['status'],'BLOCKED')
    def test_missing_pair_review(self): self.details.pop('bridge_review');self.assertEqual(self.run_gate()['status'],'BLOCKED')
    def test_two_stills_not_playback(self):
        self.details['bridge_review']['cuts'][0]['paired_context_viewed']=False
        self.assertEqual(self.run_gate()['status'],'BLOCKED')
    def test_wrong_adopted_pair(self):
        self.details['bridge_review']['cuts'][0]['binding_digest']='f'*64
        self.assertEqual(self.run_gate()['status'],'BLOCKED')
    def test_review_context_too_small(self):
        self.details['bridge_review']['cuts'][0]['viewed_context']=[23,25]
        self.assertEqual(self.run_gate()['status'],'BLOCKED')
    def test_unknown_is_blocked(self):
        self.details['bridge_review']['cuts'][0]['checks']['action']['result']='UNKNOWN'
        self.assertEqual(self.run_gate()['status'],'BLOCKED')
    def test_failure_not_averaged_away(self):
        self.details['bridge_review']['cuts'][0]['checks']['action']['result']='FAIL'
        self.assertEqual(self.run_gate()['status'],'REJECTED')
    def test_missing_aspect(self):
        self.details['bridge_review']['cuts'][0]['checks'].pop('sound')
        self.assertEqual(self.run_gate()['status'],'BLOCKED')
    def test_na_needs_reason(self):
        self.details['bridge_review']['cuts'][0]['checks']['sound']['result']='NOT_APPLICABLE'
        self.assertEqual(self.run_gate()['status'],'BLOCKED')
    def test_na_with_reason_allowed(self):
        self.details['bridge_review']['cuts'][0]['checks']['sound'].update(result='NOT_APPLICABLE',reason='Explicitly silent test scope.')
        self.assertEqual(self.run_gate()['status'],'ACCEPTED')
    def test_no_evidence(self):
        self.details['bridge_review']['cuts'][0]['evidence']=[]
        self.assertEqual(self.run_gate()['status'],'BLOCKED')
    def test_path_traversal_rejected(self):
        self.details['bridge_review']['cuts'][0]['evidence']=[{'path':'../evidence.json','sha256':'0'*64}]
        self.assertEqual(self.run_gate()['status'],'BLOCKED')
    def test_missing_cue_observation(self):
        self.details['bridge_review']['character_cues']=[]
        self.assertEqual(self.run_gate()['status'],'BLOCKED')
    def test_cue_failure_blocks(self):
        self.details['bridge_review']['character_cues'][0]['result']='FAIL'
        self.assertEqual(self.run_gate()['status'],'REJECTED')
    def test_cue_evidence_missing(self):
        self.details['bridge_review']['character_cues'][0]['evidence']=[]
        self.assertEqual(self.run_gate()['status'],'BLOCKED')
    def test_changed_file_report_stale(self):
        (self.root/'bridges.json').write_text('{}')
        self.assertEqual(self.run_gate()['status'],'BLOCKED')
    def test_bridge_policy_requires_edit_gate(self):
        self.s['editing_required']=False;self.old.refresh()
        self.assertEqual(self.run_gate()['status'],'BLOCKED')
    def test_no_unrequested_second_model_required(self):
        self.r.append({'check_id':'personality_beauty_review','status':'FAIL'})
        self.assertEqual(self.run_gate()['status'],'ACCEPTED')
    def test_legacy_unchanged(self):
        self.s.pop('bridges_required');self.s.pop('cut_bridges');self.details.pop('bridge_review');self.old.refresh()
        self.assertEqual(self.run_gate()['status'],'ACCEPTED')
    def test_does_not_claim_model_success(self):self.assertFalse(self.run_gate()['guarantees_zero_errors'])


if __name__=='__main__':unittest.main()
