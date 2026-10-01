"""Synthetic timing/geometry/record tests. Not a re-audit of user media or model calls."""
from copy import deepcopy
from fractions import Fraction
import json
from pathlib import Path
import unittest
import edit_timeline as edit
import presentation_checks as pc
import production_gates as gates
import test_edit_timeline as oldedit
import test_edit_gates as oldgate


def a(eid,edge='start',offset=0):
    return {'event_id':eid,'edge':edge,'offset_frames':offset}


def fixture():
    t=oldedit.fixture()
    t['events'][0].update(story_phase='effective',perceivers=['C1'])
    t['events'][2]['perceivers']=['C1']
    t['presentation']={'schema_version':'presentation-1','status':'LOCKED',
        'policy':{'max_subtitle_lead_frames':0,'max_subtitle_tail_frames':0},
        'cues':[
            {'id':'OFFER','kind':'ui','text':'报价：100元','start':a('EV1','start',-10),
             'duration_frames':25,'readable_after_frames':2,'phase':'quote','visibility':'public',
             'visible_to':['C1'],'unit':'CNY','rect':[0.05,0.02,0.9,0.15]},
            {'id':'SUB1','kind':'subtitle','event_id':'EL1','text':'这么多？',
             'lead_frames':0,'tail_frames':0,'rect':[0.05,0.85,0.9,0.1]},
            {'id':'SUB2','kind':'subtitle','event_id':'EL2','text':'这才只是报价。',
             'lead_frames':0,'tail_frames':0,'rect':[0.05,0.85,0.9,0.1]}],
        'orders':[{'id':'O1','before':{'ref':'cue:OFFER','point':'readable'},
                   'after':{'ref':'event:EL1','point':'start'},'min_gap_frames':2,'perceivers':['C1']}],
        'protected_regions':[{'id':'FACE','start':a('EV1','start',-12),
            'end':a('EL2','end'),'rect':[0.2,0.3,0.6,0.4],'purpose':'face-and-mouth'}]}
    return t


class PresentationStructureTests(unittest.TestCase):
    def setUp(self): self.t=fixture();self.p=self.t['presentation']
    def assertBlocked(self,word=None):
        result=edit.validate(self.t)
        self.assertEqual(result['status'],'BLOCKED',result)
        if word:self.assertIn(word,' '.join(result['errors']))
    def test_valid(self):self.assertEqual(edit.validate(self.t)['status'],'STRUCTURE_OK')
    def test_subtitles_map_actual_audio_samples(self):
        r=pc.resolve(self.t);self.assertEqual([(c['start'],c['end']) for c in r['cues'][1:]],[(15,24),(36,48)])
    def test_audio_crop_and_destination_not_picture_start(self):
        self.t['audio'][0].update(src_in=24000,src_out=60000,dst_in=0)
        self.t['video'][0]['visible_dialogue']=False;self.t['sync_links']=[]
        self.p['orders']=[]
        r=pc.resolve(self.t);self.assertEqual(r['cues'][1]['start'],3)
    def test_subtitles_retime_when_audio_moves(self):
        self.t['audio'][1]['dst_in']=68000
        r=pc.resolve(self.t);self.assertEqual(r['cues'][2]['start'],34)
    def test_fractional_onset_conservative_quantization(self):
        self.t['events'][2]['src_in']=30001
        self.assertEqual(pc.resolve(self.t)['cues'][1]['start'],16)
    def test_manual_absolute_time_not_supported(self):self.p['cues'][1]['start_s']=0;self.assertBlocked('subtitle needs')
    def test_excessive_subtitle_lead(self):self.p['cues'][1]['lead_frames']=12;self.assertBlocked('exceeds')
    def test_late_subtitle_tail(self):self.p['cues'][1]['tail_frames']=2;self.assertBlocked('exceeds')
    def test_allowed_small_tail(self):
        self.p['policy']['max_subtitle_tail_frames']=1;self.p['cues'][1]['tail_frames']=1
        self.assertEqual(edit.validate(self.t)['status'],'STRUCTURE_OK')
    def test_price_after_reaction(self):self.p['cues'][0]['start']['offset_frames']=6;self.assertBlocked('dependency')
    def test_panel_start_not_readable_time(self):self.p['cues'][0]['readable_after_frames']=14;self.assertBlocked('dependency')
    def test_invalid_readable_window(self):self.p['cues'][0]['readable_after_frames']=25;self.assertBlocked('readable')
    def test_private_hud_cannot_inform_other_actor(self):
        self.p['cues'][0].update(visibility='private',visible_to=['C2']);self.assertBlocked('perception')
    def test_viewer_only_does_not_inform_character(self):
        self.p['cues'][0].update(visibility='viewer_only',visible_to=[]);self.assertBlocked('perception')
    def test_viewer_only_cannot_claim_recipients(self):self.p['cues'][0]['visibility']='viewer_only';self.assertBlocked('viewer-only')
    def test_subtitles_cannot_source_character_knowledge(self):
        self.p['orders'][0].update(before={'ref':'cue:SUB1','point':'end'},after={'ref':'event:EL2','point':'start'})
        self.assertBlocked('knowledge')
    def test_spoken_information_with_actual_listener(self):
        self.p['orders'][0].update(before={'ref':'event:EL1','point':'end'},after={'ref':'event:EL2','point':'start'})
        self.assertEqual(edit.validate(self.t)['status'],'STRUCTURE_OK')
    def test_result_cannot_show_before_effect(self):
        self.p['cues'][0].update(phase='result',state_event_id='EV1');self.assertBlocked('effect completed')
    def test_result_requires_effective_event(self):
        self.p['cues'][0].update(phase='result',state_event_id='EL1');self.assertBlocked('effective-state')
    def test_valid_result_after_completion(self):
        self.p['orders']=[]
        self.p['cues'][0].update(phase='result',state_event_id='EV1',start=a('EV1','end'))
        self.assertEqual(edit.validate(self.t)['status'],'STRUCTURE_OK')
    def test_no_currency_unit(self):self.p['cues'][0]['unit']='';self.assertBlocked('unit')
    def test_rect_over_face(self):self.p['cues'][0]['rect']=[0.1,0.35,0.7,0.25];self.assertBlocked('protected region')
    def test_text_cues_overlap(self):self.p['cues'][0]['rect']=[0.05,0.85,0.9,0.1];self.assertBlocked('text cue')
    def test_rect_overlap_outside_active_time_allowed(self):
        self.p['cues'][0]['rect']=[0.2,0.3,0.6,0.4]
        self.p['protected_regions'][0]['start']=a('EL2')
        self.assertEqual(edit.validate(self.t)['status'],'STRUCTURE_OK')
    def test_rect_edge_touch_not_overlap(self):
        self.assertFalse(pc.intersects([0,0,0.5,0.5],[0.5,0,0.5,0.5]))
    def test_unknown_ui_anchor(self):self.p['cues'][0]['start']['event_id']='GHOST';self.assertBlocked('anchor')
    def test_unknown_order(self):self.p['orders'][0]['after']['ref']='event:GHOST';self.assertBlocked('endpoint')
    def test_cue_outside_actual_timeline(self):self.p['cues'][0]['duration_frames']=100;self.assertBlocked('outside')
    def test_invalid_rect_and_nan(self):self.p['cues'][0]['rect']=[0.1,float('nan'),0.2,0.2];self.assertBlocked('rect')
    def test_duplicate_cue_id(self):self.p['cues'].append(deepcopy(self.p['cues'][0]));self.assertBlocked('duplicate')
    def test_no_ui_is_legal_not_fake_work(self):
        self.p.update(cues=[],orders=[],protected_regions=[])
        self.assertEqual(edit.validate(self.t)['status'],'STRUCTURE_OK')
    def test_new_fields_do_not_validate_semantics(self):self.assertFalse(pc.resolve(self.t)['semantics_verified'])
    def test_event_review_covers_full_cause_and_response(self):
        r=pc.resolve(self.t);self.assertEqual(r['orders'][0],{'id':'O1','start':2,'end':27})


class PresentationGateTests(unittest.TestCase):
    def setUp(self):
        self.parent=oldgate.EditGateTests('test_complete_new_gate');self.parent.setUp()
        self.root=self.parent.root;self.s=self.parent.s;self.reports=self.parent.r
        self.t=fixture();self.s.update(presentation_required=True,
            presentation_cue_ids=['OFFER','SUB1','SUB2'],presentation_order_ids=['O1'])
        self.save()
    def tearDown(self):self.parent.tearDown()
    def report(self):return self.parent.find('edit_cut_review')['details']['presentation_review']
    def save(self):
        (self.root/'timeline.json').write_text(json.dumps(self.t))
        self.s['edit_timeline']=self.parent.old.record('timeline.json')
        resolved=pc.resolve(self.t)
        ev=self.parent.old.record('evidence.json')
        def rows(items):
            return [{'id':x['id'],'result':'PASS','range_frames':[x['start'],x['end']],
                'observation':'SYNTHETIC TEST ONLY: no real media reviewed.','evidence':[ev]} for x in items]
        d={'subject_sha256':self.s['subject']['sha256'],'presentation_sha256':resolved.get('presentation_sha256'),
           'renderer_consumed_resolved_cues':True,'render_inputs':[self.s['edit_timeline']],
           'cue_checks':rows(resolved['cues']),'event_checks':rows(resolved['orders']),'unresolved_ids':[]}
        self.parent.find('edit_cut_review')['details']['presentation_review']=d
        for cid in ('edit_timeline','edit_cut_review'):
            self.parent.find(cid)['details']['timeline_sha256']=self.s['edit_timeline']['sha256']
        self.parent.refresh()
    def status(self):return gates.gate(self.s,self.reports,self.root)
    def test_new_gate_same_g3_record(self):self.assertEqual(self.status()['status'],'ACCEPTED')
    def test_missing_joint_observation(self):
        del self.parent.find('edit_cut_review')['details']['presentation_review']
        self.assertEqual(self.status()['status'],'BLOCKED')
    def test_old_final_version_rejected(self):
        self.report()['subject_sha256']='0'*64
        self.assertIn('another final artifact',' '.join(self.status()['blockers']))
    def test_render_input_changed(self):
        self.report()['render_inputs']=[{'path':'evidence.json','sha256':'0'*64}]
        self.assertEqual(self.status()['status'],'BLOCKED')
    def test_old_presentation_version_rejected(self):
        self.report()['presentation_sha256']='0'*64
        self.assertEqual(self.status()['status'],'BLOCKED')
    def test_renderer_ignored_ui(self):
        self.report()['renderer_consumed_resolved_cues']=False
        self.assertEqual(self.status()['status'],'BLOCKED')
    def test_aggregate_only_not_enough(self):
        self.report()['event_checks']=[];self.assertEqual(self.status()['status'],'BLOCKED')
    def test_short_cut_strip_insufficient(self):
        self.report()['event_checks'][0]['range_frames']=[13,17]
        self.assertEqual(self.status()['status'],'BLOCKED')
    def test_actual_failure_blocks_despite_outer_pass(self):
        self.report()['event_checks'][0]['result']='FAIL'
        self.assertEqual(self.status()['status'],'REJECTED')
    def test_unknown_not_pass(self):
        self.report()['cue_checks'][0]['result']='UNKNOWN'
        self.assertEqual(self.status()['status'],'BLOCKED')
    def test_draft_not_final(self):
        self.t['presentation']['status']='DRAFT';self.save()
        self.assertEqual(self.status()['status'],'BLOCKED')
    def test_removed_cue_not_hidden_from_locked_scope(self):
        self.s['presentation_cue_ids']=['OFFER'];self.parent.refresh()
        self.assertEqual(self.status()['status'],'BLOCKED')
    def test_not_separate_model_gate(self):
        self.assertNotIn('presentation_review',self.status()['required_checks'])
    def test_missing_evidence(self):
        self.report()['cue_checks'][0]['evidence']=[]
        self.assertEqual(self.status()['status'],'BLOCKED')
    def test_legacy_gate_still_explicitly_legacy(self):
        self.s.pop('presentation_required');self.parent.refresh()
        del self.parent.find('edit_cut_review')['details']['presentation_review']
        self.assertEqual(self.status()['status'],'ACCEPTED')


if __name__=='__main__':unittest.main(verbosity=2)
