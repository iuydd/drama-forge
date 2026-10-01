"""Review-scheduling and contract tests. No real video or visual model is tested."""
import copy
import unittest
import review_efficiency as r
import continuity_tools as t
import test_continuity_tools as legacy


class PlanTests(unittest.TestCase):
    def test_low_risk_five_points_include_middle(self):
        p=r.make_video_plan(120,[],[])
        self.assertEqual(p['required_semantic_frame_count'],5)
        self.assertTrue(r.covers(p['required_semantic_ranges'],[[0,0],[60,60],[119,119]]))
    def test_medium_nine_points(self):
        self.assertEqual(r.make_video_plan(120,['routine_motion'],[])['required_semantic_frame_count'],9)
    def test_high_without_localization_full(self):
        p=r.make_video_plan(120,['handoff'],[])
        self.assertEqual(p['required_semantic_ranges'],[[0,119]])
    def test_high_localized_contact_has_complete_interval(self):
        p=r.make_video_plan(120,['handoff'],[[50,58]])
        self.assertTrue(r.covers(p['required_semantic_ranges'],[[48,60]]))
        self.assertLess(p['required_semantic_frame_count'],120)
    def test_one_frame_no_duplicates(self):
        self.assertEqual(r.make_video_plan(1,[],[])['required_semantic_ranges'],[[0,0]])
    def test_event_at_clip_edge(self):
        p=r.make_video_plan(10,['occlusion'],[[0,1],[8,9]])
        self.assertTrue(r.covers(p['required_semantic_ranges'],[[0,3],[6,9]]))
    def test_disjoint_ranges_not_false_full_coverage(self):
        self.assertFalse(r.covers([[0,2],[4,8]],[[0,8]]))
    def test_adjacent_ranges_merge(self):
        self.assertEqual(r.merge_ranges([[4,7],[0,3],[6,9]]),[[0,9]])
    def test_invalid_frame_counts(self):
        for x in (0,-1,True,3.5,10_000_001):
            with self.subTest(x=x),self.assertRaises(ValueError): r.make_video_plan(x,[],[])
    def test_unknown_flag_is_not_low(self):
        with self.assertRaises(ValueError):r.make_video_plan(120,['spelling-error'],[])
    def test_invalid_events(self):
        for events in ([[2,1]], [[0,120]], [[True,5]],None):
            with self.subTest(events=events),self.assertRaises(ValueError):r.make_video_plan(120,[],events)
    def test_invalid_padding(self):
        with self.assertRaises(ValueError):r.make_video_plan(10,[],[],-1)
    def test_tampered_plan_blocked(self):
        p=r.make_video_plan(120,['handoff'],[[50,58]])
        p['required_semantic_ranges']=[[0,0],[119,119]]
        self.assertTrue(r.validate_plan(p))
    def test_plan_roundtrip(self):
        self.assertEqual(r.validate_plan(r.make_video_plan(120,['reflection'],[[50,58]])),[])
    def test_unknown_policy_mode(self):
        self.assertTrue(r.check_policy({'review_mode':'fast_ignore'},'image'))
    def test_video_balanced_requires_plan(self):
        self.assertTrue(r.check_policy({'review_mode':'balanced'},'video'))
    def test_legacy_policy_still_valid(self):
        self.assertEqual(r.check_policy(None,'video'),[])
    def test_spotcheck_nonempty_at_least_one(self):
        self.assertEqual(len(r.pick_spot_checks(['a','b'],'fixed',0)),1)
    def test_spotcheck_ten_percent(self):
        self.assertEqual(len(r.pick_spot_checks([str(i) for i in range(100)],'fixed')),10)
    def test_spotcheck_empty_batch(self):
        self.assertEqual(r.pick_spot_checks([],'fixed'),[])
    def test_spotcheck_order_independent(self):
        self.assertEqual(r.pick_spot_checks(['a','b','c'],'fixed'),r.pick_spot_checks(['c','a','b'],'fixed'))
    def test_spotcheck_rejects_duplicate_ids(self):
        with self.assertRaises(ValueError):r.pick_spot_checks(['a','a'],'fixed')
    def test_spotcheck_invalid_rate(self):
        for rate in (float('nan'),True,-0.1,1.1):
            with self.subTest(rate=rate),self.assertRaises(ValueError):r.pick_spot_checks(['a'],'fixed',rate)
    def test_verified_cache_matches(self):
        old={k:('scene_structure' if k=='check_id' else 'a'*64) for k in r.CACHE_FIELDS}
        old.update(result='PASS',evidence_verified=True)
        self.assertTrue(r.cache_reusable(old,copy.deepcopy(old)))
    def test_missing_or_changed_cache_not_reused(self):
        self.assertFalse(r.cache_reusable({},{}))
        old={k:('scene_structure' if k=='check_id' else 'a'*64) for k in r.CACHE_FIELDS}
        old.update(result='PASS',evidence_verified=True)
        new=copy.deepcopy(old);new['dependency_sha256']='b'*64
        self.assertFalse(r.cache_reusable(old,new))
    def test_unknown_cache_not_pass(self):
        old={k:('scene_structure' if k=='check_id' else 'a'*64) for k in r.CACHE_FIELDS}
        old.update(result='UNKNOWN',evidence_verified=True)
        self.assertFalse(r.cache_reusable(old,old))


class BalancedGateTests(unittest.TestCase):
    def setUp(self):
        # Reuse the old SYNTHETIC evidence fixture, without duplicating its tests.
        self.f=legacy.ContractTests('test_gate_passes_complete_synthetic_report')
        self.f.setUp()
        self.f.shot['quality_policy']={'review_mode':'balanced','allow_minor_findings':True,
            'allowed_minor_categories':['noncritical_texture_variation','noncritical_edge_noise']}
    def tearDown(self):self.f.tearDown()
    def gate(self):return self.f.gate(refresh=True)
    def video(self):
        f=self.f; f.shot['mode']='video_i2v';f.shot['output']['media_kind']='video'
        f.shot['video']=t.load_json(legacy.ROOT/'examples/video-shot.json')['video']
        f.shot['qa_required']=sorted(t.VIDEO_CHECKS)
        f.shot['references'][0]['role']='start_frame'
        f.shot['references'][0]['scene_anchor_sha256']=f.scene['views'][0]['sha256']
        f.report['stage']='video'
        e=f.record('video-evidence.json',b'{"synthetic":true,"not_real_video":true}')
        f.report['checks']=[{'id':cid,'result':'PASS','observation':'Synthetic fixture only.',
                             'evidence':[copy.deepcopy(e)]} for cid in f.shot['qa_required']]
        plan=r.make_video_plan(120,['handoff'],[[50,58]])
        f.shot['quality_policy']['video_review_plan']=plan
        f.report['coverage']={'kind':'video','basis':'risk_based','total_frames':120,
            'decoded_frame_ranges':[[0,119]],'semantic_frame_ranges':copy.deepcopy(plan['required_semantic_ranges']),
            'temporal_reviewed':True,'temporal_overview_scope':'entire_clip','temporal_method':'native_video',
            'sampling_disclosure':'Synthetic report, no actual video reviewed.',
            'decode_evidence':copy.deepcopy(e),'temporal_evidence':copy.deepcopy(e),'sampling_evidence':copy.deepcopy(e)}
    def minor(self):
        e=self.f.record('tolerance.json',b'{"synthetic":true}')
        f={'severity':'minor','resolved':False,'description':'Synthetic noncritical texture variation.',
           'check_id':'cosmetic_optional','category':'noncritical_texture_variation',
           'normal_playback_noticeable':False,'violates_lock':False,'affects_narrative':False,
           'affects_identity_or_geometry':False,'waiver_evidence':e}
        self.f.report['findings']=[f];return f
    def test_balanced_image_does_not_need_video_plan(self):
        self.assertEqual(self.gate()['status'],'ACCEPTED')
    def test_risk_based_video_complete_contract(self):
        self.video();result=self.gate()
        self.assertEqual(result['status'],'ACCEPTED',result)
        self.assertEqual(result['coverage_basis'],'risk_based')
    def test_missing_mid_action_frames_block(self):
        self.video();self.f.report['coverage']['semantic_frame_ranges']=[[0,0],[119,119]]
        self.assertEqual(self.gate()['status'],'BLOCKED')
    def test_decode_gap_blocks(self):
        self.video();self.f.report['coverage']['decoded_frame_ranges']=[[0,50],[52,119]]
        self.assertEqual(self.gate()['status'],'BLOCKED')
    def test_temporal_review_missing_blocks(self):
        self.video();self.f.report['coverage']['temporal_reviewed']=False
        self.assertEqual(self.gate()['status'],'BLOCKED')
    def test_sampling_method_not_disclosed_blocks(self):
        self.video();self.f.report['coverage']['sampling_disclosure']=''
        self.assertEqual(self.gate()['status'],'BLOCKED')
    def test_stale_sampling_evidence_blocks(self):
        self.video();self.f.report['coverage']['sampling_evidence']['sha256']='0'*64
        self.assertEqual(self.gate()['status'],'BLOCKED')
    def test_true_minor_with_evidence_accepts_warning(self):
        self.minor();result=self.gate();self.assertEqual(result['status'],'ACCEPTED',result)
        self.assertTrue(result['warnings'])
    def test_minor_on_hard_check_cannot_be_waived(self):
        self.minor()['check_id']='subject_integrity';self.assertEqual(self.gate()['status'],'REJECTED')
    def test_noticeable_minor_cannot_be_waived(self):
        self.minor()['normal_playback_noticeable']=True;self.assertEqual(self.gate()['status'],'REJECTED')
    def test_locked_texture_cannot_be_waived(self):
        self.minor()['violates_lock']=True;self.assertEqual(self.gate()['status'],'REJECTED')
    def test_wrong_geometry_cannot_be_waived(self):
        self.minor()['affects_identity_or_geometry']=True;self.assertEqual(self.gate()['status'],'REJECTED')
    def test_unclassified_minor_cannot_be_waived(self):
        self.minor().pop('category');self.assertEqual(self.gate()['status'],'REJECTED')
    def test_malformed_category_does_not_crash(self):
        self.minor()['category']=[];self.assertEqual(self.gate()['status'],'REJECTED')
    def test_missing_tolerance_evidence_blocks(self):
        self.minor()['waiver_evidence']={'path':'absent.json','sha256':'a'*64}
        self.assertEqual(self.gate()['status'],'BLOCKED')
    def test_major_still_rejected(self):
        self.minor()['severity']='major';self.assertEqual(self.gate()['status'],'REJECTED')
    def test_unknown_check_not_turned_into_pass(self):
        self.f.report['checks'][0]['result']='UNKNOWN';self.assertEqual(self.gate()['status'],'BLOCKED')
    def test_old_sparse_report_not_accepted_as_risk_based(self):
        self.video();self.f.report['coverage']['basis']='sampled'
        self.assertEqual(self.gate()['status'],'BLOCKED')
    def test_unknown_risk_flag_blocks_gate(self):
        self.video();self.f.shot['quality_policy']['video_review_plan']['risk_flags']=['invented']
        self.assertEqual(self.gate()['status'],'BLOCKED')

if __name__=='__main__':unittest.main()
