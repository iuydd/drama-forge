"""Synthetic spatial/state regressions. No real user footage, inference or API calls."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import sequence_continuity as q
import brain_handoff as brain
import production_gates as g


def fixture():
    facts = {'CAR.heading':'A_to_B', 'CAR.location':'STREET',
             'NOTICE.anchor':'WALL_A/seam2', 'NOTICE.face':'front',
             'NOTICE.state':'attached_old', 'PEN.hand':'right', 'DOOR.layout':'WEST_WALL'}
    def scene(plate):
        return {'layout_revision':'1','coordinate_frame':'A_to_B = +X; up = +Z',
                'landmarks':['A','B'], 'views':{'V1':{'axis_side':'SIDE_A',
                'plate_asset_id':plate,'orientation_basis':'Synthetic camera north of action axis.',
                'screen_landmarks':['A','B']}, 'V2':{'axis_side':'SIDE_B',
                'plate_asset_id':plate+'-B','orientation_basis':'Synthetic opposite-side camera.',
                'screen_landmarks':['B','A']}}}
    bindings=[{'key':k,'entity_id':k.split('.')[0],'path':['state',k.split('.')[1]]} for k in facts]
    def shot(sid, sceneid, a, b, relation):
        return {'shot_id':sid,'scene_id':sceneid,'view_id':'V1','state_in':a,'state_out':b,
          'relation':relation,'transition_basis':'Synthetic authored transition.',
          'approval_ref':'SYNTHETIC-APPROVAL','orientation_cue':'Recognisable established location.',
          'state_keys':list(facts),'visible_start_keys':list(facts) if sceneid=='STREET' else [],
          'visible_end_keys':list(facts) if sceneid=='STREET' else [],
          'screen_start':{'car_heading':'right'} if sceneid=='STREET' else {},
          'screen_end':{'car_heading':'right'} if sceneid=='STREET' else {},
          'ensemble_bindings':deepcopy(bindings),'reference_policy':'same_view_plate',
          'continuity_clause':'SYNTHETIC LOCK: keep the authored world, not a generation request.',
          'adopted_clip_ids':[sid+'-clip']}
    return {'schema_version':'sequence-continuity-1','status':'LOCKED','example_only':False,
      'episode_id':'EP001','revision':'1','initial':{'state_id':'T0','facts':facts},
      'fixed_keys':['DOOR.layout'], 'states':[{'state_id':'T1','parent_state_id':'T0','changes':[
        {'key':'NOTICE.state','before':'attached_old','after':'detached_old','event_id':'REMOVE',
         'cause_ref':'SYNTHETIC-SCRIPT','approval_ref':'SYNTHETIC-APPROVAL','mode':'on_screen'}]}],
      'scenes':{'STREET':scene('PLATE-A'),'ROOM':scene('PLATE-B')},
      'shots':[shot('S1','STREET','T0','T1','opening'),shot('S2','ROOM','T1','T1','new_scene'),
               shot('S3','STREET','T1','T1','return')],
      'note':'SYNTHETIC FIXTURE ONLY. No real approval, image or observation.'}


def context(plan, media_sha='a'*64):
    ctx, errors = q.resolve(plan)
    if errors: raise ValueError(errors)
    return {sid:{**ctx,'plan':plan,'record':{'path':'plan.json','sha256':q.digest(plan)},
             'media':{'path':'media.bin','sha256':media_sha}} for sid in ctx['shots']}


def timeline(plan):
    return {'episode_id':plan['episode_id'],'duration_frames':len(plan['shots'])*10,
            'video':[{'id':s['adopted_clip_ids'][0],'shot_id':s['shot_id'],'dst_in':i*10,'src_in':0,'src_out':10}
                     for i,s in enumerate(plan['shots'])]}


def review(ctx, stage='final', evidence=None, t=None):
    media=next(iter(ctx.values()))['media']['sha256']
    rows=[]
    for i,(sid,c) in enumerate(ctx.items()):
        rows.append({'shot_id':sid,'plan_sha256':c['record']['sha256'],'media_sha256':media,
          'reviewer_id':'synthetic-test-only','full_interval_viewed':True,'moments':[
          {'id':m,'result':'PASS','values':q.expected_values(c,sid,m),
           'observation':'Synthetic test record, NOT a media inspection.',
           'locator':({'kind':'image','region':'full'} if stage=='start_frame' else
                      {'kind':'frames','start':i*10,'end':(i+1)*10,'clock':'subject'}),
           'media_sha256':media,'evidence':[evidence or {'path':'proof.md','sha256':'b'*64}]}
          for m in (['in'] if stage=='start_frame' else ['in','out'])]})
    result={'schema_version':'sequence-review-1','stage':stage,'subject_sha256':media,'shots':rows,
      'revisits':[{'link_id':r['link_id'],'binding_digest':q.digest(r),'paired_context_viewed':True,
          'result':'PASS','observation':'Synthetic nonadjacent pair check.',
          'evidence_moments':[r['from_shot']+'/out',r['to_shot']+'/in']}
          for r in q.expected_revisits(ctx)]}
    if t is not None: result['timeline_digest']=q.digest(t)
    return result


class SequenceStateTests(unittest.TestCase):
    def setUp(self): self.p=fixture()
    def bad(self): self.assertTrue(q.resolve(self.p)[1])
    def test_valid_return_inherits_latest_state(self):
        ctx,e=q.resolve(self.p);self.assertFalse(e);self.assertEqual(ctx['states']['T1']['NOTICE.state'],'detached_old')
    def test_return_cannot_reset_torn_paper(self):
        self.p['shots'][2].update(state_in='T0',state_out='T0');self.bad()
    def test_camera_only_cannot_move_car(self):
        s=self.p['shots'][1];s.update(scene_id='STREET',relation='camera_only',state_in='T0');self.bad()
    def test_noop_new_snapshot_is_not_state_reset_escape(self):
        self.p['states'][0]['changes'][0]['after']='attached_old';self.bad()
    def test_unknown_fact_cannot_appear(self): self.p['states'][0]['changes'][0]['key']='NEW_PROP';self.bad()
    def test_immutable_layout_does_not_flip(self):
        self.p['states'][0]['changes'][0].update(key='DOOR.layout',before='WEST_WALL',after='EAST_WALL');self.bad()
    def test_change_requires_matching_before(self): self.p['states'][0]['changes'][0]['before']='NEW_PAPER';self.bad()
    def test_state_change_requires_event_cause_and_approval(self):
        for key in ('event_id','cause_ref','approval_ref','mode'):
            with self.subTest(key=key):
                p=deepcopy(self.p);del p['states'][0]['changes'][0][key];self.assertTrue(q.resolve(p)[1])
    def test_event_cannot_be_applied_twice(self):
        node=deepcopy(self.p['states'][0]);node.update(state_id='T2',parent_state_id='T1')
        node['changes'][0].update(before='detached_old',after='attached_new');self.p['states'].append(node);self.bad()
    def test_two_fields_one_event_are_allowed(self):
        c=deepcopy(self.p['states'][0]['changes'][0]);c.update(key='NOTICE.face',before='front',after='back')
        self.p['states'][0]['changes'].append(c);self.assertFalse(q.resolve(self.p)[1])
    def test_state_graph_cannot_cycle(self): self.p['states'][0]['parent_state_id']='T1';self.bad()
    def test_duplicate_state_key_is_blocked(self):self.p['states']*=2;self.bad()
    def test_no_reopening_world_in_middle(self): self.p['shots'][2]['relation']='opening';self.bad()
    def test_registered_camera_required(self): self.p['shots'][2]['view_id']='GUESS';self.bad()
    def test_no_unexplained_axis_flip(self):
        self.p['shots']=self.p['shots'][:1]+[deepcopy(self.p['shots'][2])]
        self.p['shots'][1].update(view_id='V2',relation='camera_only');self.bad()
    def test_legal_screen_reversal_with_axis_establishment(self):
        self.p['shots']=self.p['shots'][:1]+[deepcopy(self.p['shots'][2])]
        s=self.p['shots'][1];s.update(view_id='V2',relation='camera_only',axis_change_approval='APPROVED-TEST',
          screen_start={'car_heading':'left'},screen_end={'car_heading':'left'})
        self.assertFalse(q.resolve(self.p)[1])
    def test_independent_new_location_need_not_copy_screen_heading(self):
        self.p['shots'][1].update(screen_start={'direction':'into_room'},screen_end={'direction':'still'})
        self.assertFalse(q.resolve(self.p)[1])
    def test_unknown_backside_cannot_be_unregistered_landmark(self):
        self.p['scenes']['STREET']['views']['V1']['screen_landmarks']=['INVENTED_WINDOW'];self.bad()
    def test_hidden_prop_state_is_still_inherited(self):
        self.p['shots'][2]['visible_start_keys']=[]
        ctx,e=q.resolve(self.p);self.assertFalse(e);self.assertEqual(ctx['states']['T1']['NOTICE.anchor'],'WALL_A/seam2')
    def test_visibility_cannot_invent_untracked_object(self):
        self.p['shots'][2]['visible_start_keys'].append('NEW');self.bad()
    def test_partial_tracking_must_still_bind_all_declared_facts(self):
        self.p['shots'][0]['ensemble_bindings'].pop();self.bad()
    def test_skipped_visible_action_blocks(self):
        self.p['shots'][0]['state_out']='T0';self.bad()
    def test_approved_offscreen_ellipsis_is_not_forced_reenactment(self):
        self.p['shots'][0]['state_out']='T0';self.p['states'][0]['changes'][0]['mode']='offscreen_ellipsis'
        self.assertFalse(q.resolve(self.p)[1])
    def test_flashback_and_resume_do_not_erase_present(self):
        back=deepcopy(self.p['shots'][2]);back.update(shot_id='PAST',relation='flashback',state_in='T0',state_out='T0')
        self.p['shots'].insert(2,back);self.p['shots'][-1]['relation']='resume'
        self.assertFalse(q.resolve(self.p)[1])
    def test_resume_to_wrong_past_blocks(self):
        back=deepcopy(self.p['shots'][2]);back.update(shot_id='PAST',relation='flashback',state_in='T0',state_out='T0')
        self.p['shots'].insert(2,back);self.p['shots'][-1].update(relation='resume',state_in='T0',state_out='T0');self.bad()
    def test_unapproved_flashback_blocks(self):
        self.p['shots'][2].update(relation='flashback',approval_ref='');self.bad()
    def test_parallel_coverage_of_same_event_allowed(self):
        self.p['shots']=self.p['shots'][:1]+[deepcopy(self.p['shots'][0])]
        self.p['shots'][1].update(shot_id='ALT',relation='parallel');self.assertFalse(q.resolve(self.p)[1])
    def test_nonfinite_change_fails_closed(self):self.p['states'][0]['changes'][0]['after']=float('nan');self.bad()
    def test_malformed_types_fail_closed(self):
        for key,val in [('scenes',[]),('shots',None),('states',[]),('fixed_keys',{}),('initial',{})]:
            with self.subTest(key=key):
                p=deepcopy(self.p);p[key]=val;self.assertTrue(q.resolve(p)[1])
    def test_example_cannot_pass_production(self):self.p['example_only']=True;self.bad()
    def test_draft_cannot_pass_production(self):self.p['status']='DRAFT';self.bad()
    def test_known_empty_holder_is_not_confused_with_missing_fact(self):
        self.p['initial']['facts']['PEN.hand']=None;self.p['known_empty_keys']=['PEN.hand']
        self.assertFalse(q.resolve(self.p)[1])
    def test_unresolved_null_is_blocked(self):
        self.p['initial']['facts']['PEN.hand']=None;self.bad()
    def test_missing_after_is_not_a_known_empty_change(self):
        self.p['known_empty_keys']=['NOTICE.state'];del self.p['states'][0]['changes'][0]['after'];self.bad()
    def test_existing_world_fact_values_are_not_mutated_by_resolve(self):
        old=deepcopy(self.p);q.resolve(self.p);self.assertEqual(self.p,old)


class SequenceObservationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        (self.root/'proof.md').write_text('Synthetic file; no actual footage.')
        self.ev={'path':'proof.md','sha256':hashlib.sha256((self.root/'proof.md').read_bytes()).hexdigest()}
        self.p=fixture();self.t=timeline(self.p);self.p['timeline_digest']=q.digest(self.t)
        self.ctx=context(self.p);self.r=review(self.ctx,evidence=self.ev,t=self.t)
    def tearDown(self): self.tmp.cleanup()
    def check(self):
        return q.check_review(self.r,self.ctx,'final','a'*64,self.root,brain.verify_record,self.t)
    def test_actual_fields_and_pair_records_pass_integrity_only(self):self.assertEqual(self.check(),([],[]))
    def test_return_requires_nonadjacent_check(self):
        self.assertEqual(len(q.expected_revisits(self.ctx)),1);self.r['revisits']=[];self.assertTrue(self.check()[0])
    def test_revisit_groups_location_and_prop_facts(self):
        pair=q.expected_revisits(self.ctx)[0];self.assertIn('scene:STREET',pair['keys']);self.assertIn('world:NOTICE.face',pair['keys'])
    def test_looking_only_at_adjacent_frames_cannot_pass_return(self):
        self.r['revisits'][0]['evidence_moments']=['S2/out','S3/in'];self.assertTrue(self.check()[0])
    def test_old_bound_pair_cannot_approve_new_return(self):
        self.r['revisits'][0]['binding_digest']='x';self.assertTrue(self.check()[0])
    def test_fail_directions_reject_even_summary_pass(self):
        self.r['shots'][2]['moments'][0]['values']['screen:car_heading']='left';self.assertTrue(self.check()[1])
    def test_wrong_poster_side_anchor_or_hand_rejects(self):
        for key in ('world:NOTICE.face','world:NOTICE.anchor','world:PEN.hand'):
            with self.subTest(key=key):
                old=deepcopy(self.r);self.r['shots'][2]['moments'][0]['values'][key]='WRONG'
                self.assertTrue(self.check()[1]);self.r=old
    def test_omitted_fact_cannot_hide_a_missing_prop(self):
        del self.r['shots'][2]['moments'][0]['values']['world:NOTICE.anchor'];self.assertTrue(self.check()[1])
    def test_unknown_is_not_pass(self):
        self.r['shots'][2]['moments'][0]['result']='UNKNOWN';self.assertTrue(self.check()[0])
    def test_no_actual_media_evidence_blocks(self):
        self.r['shots'][0]['moments'][0]['evidence']=[];self.assertTrue(self.check()[0])
    def test_stale_media_hash_blocks(self):
        self.r['shots'][0]['media_sha256']='b'*64;self.assertTrue(self.check()[0])
    def test_stale_world_plan_blocks(self):
        self.r['shots'][0]['plan_sha256']='b'*64;self.assertTrue(self.check()[0])
    def test_two_stills_do_not_prove_dynamic_continuity(self):
        self.r['shots'][0]['full_interval_viewed']=False;self.assertTrue(self.check()[0])
    def test_adopted_exit_frame_must_be_covered(self):
        self.r['shots'][0]['moments'][1]['locator'].update(start=0,end=9);self.assertTrue(self.check()[0])
    def test_adopted_entry_frame_must_be_covered(self):
        self.r['shots'][2]['moments'][0]['locator'].update(start=21,end=30);self.assertTrue(self.check()[0])
    def test_wrong_timeline_revision_blocks(self):
        self.t['revision']='NEW';self.assertTrue(self.check()[0])
    def test_actual_clip_coverage_cannot_be_omitted(self):
        self.ctx['S3']['shots']['S3']['adopted_clip_ids']=[];self.assertTrue(self.check()[0])
    def test_plan_itself_must_freeze_actual_timeline(self):
        self.p['timeline_digest']='wrong';self.assertTrue(self.check()[0])
    def test_clip_id_cannot_be_rebound_to_other_shot(self):
        self.t['video'][0]['shot_id']='WRONG';self.p['timeline_digest']=q.digest(self.t)
        self.r['timeline_digest']=q.digest(self.t);self.assertTrue(self.check()[0])
    def test_revisit_must_be_viewed_not_just_hashed(self):
        self.r['revisits'][0]['paired_context_viewed']=False;self.assertTrue(self.check()[0])
    def test_revisit_fail_rejects(self):
        self.r['revisits'][0]['result']='FAIL';self.assertTrue(self.check()[1])
    def test_startframe_only_uses_in_and_reuses_evidence(self):
        ctx={'S1':self.ctx['S1']};r=review(ctx,'start_frame',self.ev)
        self.assertEqual(q.check_review(r,ctx,'start_frame','a'*64,self.root,brain.verify_record),([],[]))
    def test_video_uses_both_endpoints(self):
        ctx={'S1':self.ctx['S1']};r=review(ctx,'video',self.ev);r['shots'][0]['moments'].pop()
        self.assertTrue(q.check_review(r,ctx,'video','a'*64,self.root,brain.verify_record)[0])


def plan_for_gate(parent):
    """Use existing ensemble truth; do not manually create a contradictory ledger."""
    shot=parent.parent.shot
    key='PROP_CUP.world_anchor';value=shot['ensemble']['start_state']['entities']['PROP_CUP']['state']['world_anchor']
    p=fixture();row=deepcopy(p['shots'][0]);row.update(shot_id='S1',scene_id=shot['scene_id'],view_id=shot['view_id'],
      state_in='T0',state_out='T0',state_keys=[key],visible_start_keys=[key],visible_end_keys=[key],
      screen_start={'cup_side':'character_right'},screen_end={'cup_side':'character_right'},
      ensemble_bindings=[{'key':key,'entity_id':'PROP_CUP','path':['state','world_anchor']}],
      continuity_clause=parent.x.request['prompt'])
    view=deepcopy(p['scenes']['STREET']['views']['V1']);view['plate_asset_id']='SYNTHETIC-PLATE'
    scene=deepcopy(p['scenes']['STREET']);scene['views']={shot['view_id']:view}
    p.update(initial={'state_id':'T0','facts':{key:value}},fixed_keys=[],states=[],
             scenes={shot['scene_id']:scene},shots=[row])
    return p


class SequenceGateIntegrationTests(unittest.TestCase):
    def setUp(self):
        import test_v4_integration as old
        self.parent=old.V4GateTests('test_full_v4_prevideo_records_accept');self.parent.setUp()
        self.root=self.parent.root;self.x=self.parent.x;self.s=self.parent.s;self.r=self.parent.r
        self.p=plan_for_gate(self.parent)
        # The old ensemble fixture is synthetic and lacks production references; attach explicit lineage.
        shot=self.parent.parent.shot
        shot.update(episode_id='EP001')
        shot['references'][0]['scene_anchor_asset_id']='SYNTHETIC-PLATE'
        self.x.put('shot.json',shot);self.s['ensemble_bindings'][0]['shot_contract']=self.x.record('shot.json')
        self.s.update(policy_version='4.1.0',continuity_required=True)
        self.parent.package['policy_version']='4.1.0';self.x.packet['policy_version']='4.1.0'
        self.save()
    def save(self):
        self.x.put('sequence.json',self.p);rec=self.x.record('sequence.json')
        self.x.packet['tasks'][0]['continuity_plan']=rec;self.x.save_packet()
        self.parent.package.update(brain_binding=self.x.binding,continuity_plan=rec)
        self.s['fidelity_bindings'][0]['brain_binding']=self.x.binding
        self.s['continuity_bindings']=[{'shot_id':'S1','plan':rec,'media':self.x.record('subject.bin'),'brain_binding':self.x.binding}]
        ctx=context(self.p,self.x.record('subject.bin')['sha256'])
        ctx['S1']['record']=rec
        self.parent.find('start_frame_gate')['details']['continuity_review']=review(ctx,'start_frame',self.x.record('proof.md'))
        self.parent.save()
    def tearDown(self):self.parent.tearDown()
    def result(self):return g.gate(self.s,self.r,self.root)
    def test_full_v41_prevideo_integrates_with_all_existing_gates(self):
        self.assertEqual(self.result()['status'],'ACCEPTED',self.result())
    def test_cannot_disable_new_gate_in_v41(self):
        self.s['continuity_required']=False;self.parent.save();self.assertEqual(self.result()['status'],'BLOCKED')
    def test_missing_sequence_binding_cannot_use_old_pass(self):
        self.s['continuity_bindings']=[];self.parent.save();self.assertEqual(self.result()['status'],'BLOCKED')
    def test_missing_actual_observation_blocks(self):
        del self.parent.find('start_frame_gate')['details']['continuity_review']
        self.assertEqual(self.result()['status'],'BLOCKED')
    def test_wrong_world_fact_rejects_stage(self):
        r=self.parent.find('start_frame_gate')['details']['continuity_review']
        r['shots'][0]['moments'][0]['values']['world:PROP_CUP.world_anchor']='CHAR_A-LEFT-HAND'
        self.assertEqual(self.result()['status'],'REJECTED')
    def test_plan_cannot_disagree_with_frozen_ensemble(self):
        self.p['initial']['facts']['PROP_CUP.world_anchor']='CHAR_A-LEFT-HAND';self.save()
        self.assertEqual(self.result()['status'],'BLOCKED')
    def test_wrong_prompt_spatial_clause_blocks(self):
        self.p['shots'][0]['continuity_clause']='NEW UNSENT SPATIAL DESIGN';self.save()
        self.assertEqual(self.result()['status'],'BLOCKED')
    def test_target_camera_reference_is_required(self):
        self.p['scenes']['ROOM1']['views']['CAM_B']['plate_asset_id']='UNKNOWN-PLATE';self.save()
        self.assertEqual(self.result()['status'],'BLOCKED')
    def test_legacy_packet_cannot_approve_v41(self):
        self.x.packet['policy_version']='4.0.0';self.save();self.assertEqual(self.result()['status'],'BLOCKED')
    def test_stale_sequence_file_not_silently_reapproved(self):
        self.p['revision']='2';self.x.put('sequence.json',self.p)
        self.assertEqual(self.result()['status'],'BLOCKED')
    def test_mixed_media_binding_blocks(self):
        self.s['continuity_bindings'][0]['media']=self.x.record('proof.md');self.parent.save()
        self.assertEqual(self.result()['status'],'BLOCKED')
    def test_gate_does_not_claim_vision(self):self.assertFalse(self.result()['guarantees_zero_errors'])


if __name__=='__main__':unittest.main()
