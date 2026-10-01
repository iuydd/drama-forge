from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import execution_control as e


def dispatch_fixture():
    jobs = []
    for i in range(9):
        jobs.append({'job_id':f'J{i}', 'episode_id':'EP001','actor_role':'coordinator','state':'READY',
          'priority':0,'queue_order':i,'resources':{'gpu':1,'api':1},'output_key':f'out{i}',
          **{k:True for k in ('dependencies_accepted','gates_passed','reading_acknowledged',
             'authorization_verified','permission_preflight_passed','rate_token_available')}})
    return {'schema_version':'dispatch-1','active_episode':'EP001','pools':{
        'gpu':{'capacity':4,'occupied':0,'verified':True,'snapshot_reconciled':True},
        'api':{'capacity':6,'occupied':0,'verified':True,'snapshot_reconciled':True}},'tasks':jobs}


class DispatchTests(unittest.TestCase):
    def setUp(self): self.d=dispatch_fixture()
    def test_fills_authorized_resource_budget(self): self.assertEqual(e.plan_dispatch(self.d)['dispatch_job_ids'],['J0','J1','J2','J3'])
    def test_replenishes_without_waiting_for_batch(self):
        self.d['pools']['gpu']['occupied']=3;self.d['pools']['api']['occupied']=3
        self.d['tasks']=self.d['tasks'][4:]
        self.assertEqual(e.plan_dispatch(self.d)['dispatch_job_ids'],['J4'])
    def test_other_episode_is_outside_call_scope(self):
        for j in self.d['tasks']:j['episode_id']='EP002'
        plan=e.plan_dispatch(self.d)
        self.assertEqual(plan['dispatch_job_ids'],[])
        self.assertIn('outside active_episode scope',plan['blocked_jobs']['J0'])
    def test_one_dependency_does_not_serialize_others(self):
        self.d['tasks'][0]['dependencies_accepted']=False
        self.assertEqual(e.plan_dispatch(self.d)['dispatch_job_ids'],['J1','J2','J3','J4'])
    def test_paid_missing_approval_blocks(self):
        self.d['tasks'][0]['authorization_verified']=False
        self.assertNotIn('J0',e.plan_dispatch(self.d)['dispatch_job_ids'])
    def test_rate_limit_blocks(self):
        self.d['tasks'][0]['rate_token_available']=False
        self.assertNotIn('J0',e.plan_dispatch(self.d)['dispatch_job_ids'])
    def test_reading_missing_blocks(self):
        self.d['tasks'][0]['reading_acknowledged']=False
        self.assertNotIn('J0',e.plan_dispatch(self.d)['dispatch_job_ids'])
    def test_subagents_never_submit(self):
        for role in e.WORKER_ACTIONS:
            with self.subTest(role=role):
                self.d['tasks'][0]['actor_role']=role
                self.assertNotIn('J0',e.plan_dispatch(self.d)['dispatch_job_ids'])
    def test_unknown_submission_not_resubmitted(self):
        self.d['tasks'][0]['state']='SUBMISSION_UNKNOWN'
        self.assertNotIn('J0',e.plan_dispatch(self.d)['dispatch_job_ids'])
    def test_unknown_pool_state_stops_planning(self):
        self.d['pools']['gpu']['snapshot_reconciled']=False
        with self.assertRaises(ValueError):e.plan_dispatch(self.d)
    def test_unknown_capacity_never_assumed_one_or_unlimited(self):
        self.d['pools']['gpu']['capacity']=None
        with self.assertRaises(ValueError):e.plan_dispatch(self.d)
    def test_shared_pool_counted_once_across_types(self):
        self.d['tasks'][0]['resources']={'gpu':3,'api':1}
        self.assertEqual(e.plan_dispatch(self.d)['dispatch_job_ids'],['J0','J1'])
    def test_large_waiting_job_does_not_block_small_jobs(self):
        self.d['tasks'][0]['resources']={'gpu':5,'api':1}
        self.assertEqual(e.plan_dispatch(self.d)['dispatch_job_ids'],['J1','J2','J3','J4'])
    def test_output_single_writer(self):
        self.d['tasks'][1]['output_key']=self.d['tasks'][0]['output_key']
        self.assertNotIn('J1',e.plan_dispatch(self.d)['dispatch_job_ids'])
    def test_existing_output_writer(self):
        self.d['occupied_outputs']=['out0']
        self.assertNotIn('J0',e.plan_dispatch(self.d)['dispatch_job_ids'])
    def test_duplicate_job_invalid(self):
        self.d['tasks'].append(deepcopy(self.d['tasks'][0]))
        with self.assertRaises(ValueError):e.plan_dispatch(self.d)
    def test_negative_resource_invalid(self):
        self.d['tasks'][0]['resources']['gpu']=-1
        with self.assertRaises(ValueError):e.plan_dispatch(self.d)
    def test_no_free_slots_no_new_work(self):
        self.d['pools']['gpu']['occupied']=4
        self.assertEqual(e.plan_dispatch(self.d)['dispatch_job_ids'],[])
    def test_no_mutation_of_snapshot(self):
        before=deepcopy(self.d);e.plan_dispatch(self.d);self.assertEqual(self.d,before)


class SlotTests(unittest.TestCase):
    def test_threads_share_one_atomic_capacity(self):
        p=e.SlotPool({'gpu':3,'ram':6})
        with ThreadPoolExecutor(max_workers=16) as ex:
            r=list(ex.map(lambda i:p.acquire(str(i),{'gpu':1,'ram':2}),range(40)))
        self.assertEqual(sum(r),3);self.assertEqual(len(p.snapshot()['jobs']),3)
    def test_no_partial_resource_acquisition(self):
        p=e.SlotPool({'gpu':2,'ram':1});self.assertFalse(p.acquire('bad',{'gpu':1,'ram':2}))
        self.assertEqual(p.snapshot()['jobs'],{})
    def test_same_job_cannot_acquire_twice(self):
        p=e.SlotPool({'gpu':3});self.assertTrue(p.acquire('J',{'gpu':1}));self.assertFalse(p.acquire('J',{'gpu':1}))
    def test_unknown_terminal_does_not_release(self):
        p=e.SlotPool({'gpu':1});p.acquire('J',{'gpu':1})
        self.assertFalse(p.release('J',terminal_verified=False));self.assertFalse(p.acquire('K',{'gpu':1}))
    def test_verified_completion_releases_then_refills(self):
        p=e.SlotPool({'gpu':1});p.acquire('J',{'gpu':1})
        self.assertTrue(p.release('J',terminal_verified=True));self.assertTrue(p.acquire('K',{'gpu':1}))
    def test_unknown_pool_invalid(self):
        p=e.SlotPool({'gpu':1})
        with self.assertRaises(ValueError):p.acquire('J',{'fake':1})


class ReadingTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.p=Path(self.tmp.name)/'skill.md'
        self.p.write_text('<a id="a"></a>\nA rules\n<a id="runtime-blind-brief"></a>\nBlind only\n<a id="secret"></a>\nEXPECTED ANSWER\n')
        self.routes={'schema_version':'reading-map-1','stages':{'dispatch':['a'],'blind':['runtime-blind-brief']}}
        self.receipt=e.reading_pack(self.p,self.routes,'dispatch','main','EP001')['receipt']
        self.receipt.update(status='ACKNOWLEDGED',applied_rules=['current episode only'])
    def tearDown(self):self.tmp.cleanup()
    def check(self):return e.check_reading(self.p,self.routes,self.receipt,'dispatch','main','EP001')
    def test_acknowledged_matching_receipt(self):self.assertEqual(self.check(),[])
    def test_issue_does_not_pretend_ack(self):self.assertEqual(e.reading_pack(self.p,self.routes,'dispatch','main','EP001')['receipt']['status'],'ISSUED_NOT_ACKNOWLEDGED')
    def test_no_ack_no_pass(self):self.receipt['status']='ISSUED_NOT_ACKNOWLEDGED';self.assertTrue(self.check())
    def test_changed_skill_invalidates(self):self.p.write_text(self.p.read_text()+'Changed');self.assertTrue(self.check())
    def test_missing_chapter_receipt(self):self.receipt['sections']=[];self.assertTrue(self.check())
    def test_other_actor_no_reuse(self):self.receipt['actor_id']='someone';self.assertTrue(self.check())
    def test_other_episode_no_reuse(self):self.receipt['task_scope']='EP002';self.assertTrue(self.check())
    def test_blind_does_not_receive_answers(self):
        pack=e.reading_pack(self.p,self.routes,'blind','viewer','EP001');self.assertNotIn('EXPECTED ANSWER',pack['instruction_text']);self.assertNotIn('A rules',pack['instruction_text'])
    def test_blind_route_cannot_add_script(self):
        self.routes['stages']['blind'].append('secret')
        with self.assertRaises(ValueError):e.reading_pack(self.p,self.routes,'blind','viewer','EP001')
    def test_fake_anchor_in_code_not_chapter(self):
        sections=e.parse_sections('<a id="a"></a>\n```text\n<a id="fake"></a>\n```\n')
        self.assertNotIn('fake',sections)
    def test_missing_required_anchor_rejected(self):
        self.routes['stages']['dispatch']=['no-such']
        with self.assertRaises(ValueError):e.reading_pack(self.p,self.routes,'dispatch','main','EP001')


class PolicyTests(unittest.TestCase):
    def test_worker_cannot_use_generic_submission(self):
        for role in e.WORKER_ACTIONS:
            for action in ('submit_generation','cancel_task','publish_external','shell','http_post','write_queue'):
                self.assertFalse(e.authorize(role,action))
    def test_coordinator_known_action_only(self):
        self.assertTrue(e.authorize('coordinator','submit_generation'));self.assertFalse(e.authorize('coordinator','disable_permissions'))
    def test_route_accepts_project_selected_tier(self):
        for role in e.WORKER_ACTIONS:
            for tier in ('mid','strong','custom',None):
                route={'tier':tier,'model_id':'synthetic','verified':True,'required_modalities':['text'],
                       'verified_modalities':['text'],'context_isolated':True}
                with self.subTest(role=role,tier=tier):self.assertEqual(e.verify_model_route(role,route),[])
    def test_unknown_role_and_unverified_route_blocked(self):
        route={'model_id':'synthetic','verified':True}
        self.assertTrue(e.verify_model_route('unknown',route))
        route['verified']=False
        self.assertTrue(e.verify_model_route('writer',route))
    def test_missing_model_not_fabricated(self):
        self.assertTrue(e.verify_model_route('writer',{'tier':'strong','model_id':None,'verified':True}))
    def test_missing_visual_modality_blocked(self):
        self.assertTrue(e.verify_model_route('reviewer',{'tier':'mid','model_id':'fake','verified':True,'required_modalities':['video'],'verified_modalities':['text']}))
    def test_blind_context_required(self):
        self.assertTrue(e.verify_model_route('blind_viewer',{'tier':'mid','model_id':'fake','verified':True,'context_isolated':False}))
    def test_environment_values_never_returned(self):
        prof={'connection_env':{'base_url':'TEST_URL','token':'TEST_TOKEN'},'unattended_permission_preflight':'VERIFIED'}
        out=e.environment_check(prof,{'TEST_URL':'https://example.invalid','TEST_TOKEN':'FAKE-SECRET-NOT-REAL'})
        self.assertFalse(out['connected']);self.assertNotIn('FAKE-SECRET-NOT-REAL',json.dumps(out));self.assertNotIn('https://example.invalid',json.dumps(out))
    def test_missing_env_is_not_default_endpoint(self):
        out=e.environment_check({'connection_env':{'base_url':'X','token':'Y'}},{})
        self.assertEqual(out['status'],'BLOCKED')
    def test_url_credentials_rejected(self):
        p={'connection_env':{'base_url':'U','token':'T'},'unattended_permission_preflight':'VERIFIED'}
        self.assertEqual(e.environment_check(p,{'U':'https://name:secret@example.invalid','T':'fake'})['status'],'BLOCKED')
    def test_mobile_is_estimate_and_preserves_master(self):
        d=e.mobile_plan(75,25_000_000);self.assertEqual(d['target_bytes'],22_500_000);self.assertFalse(d['encoded']);self.assertFalse(d['master_changed'])
    def test_mobile_limit_must_be_explicit(self):
        with self.assertRaises(TypeError):e.mobile_plan(75)
        result=subprocess.run([sys.executable,str(Path(e.__file__)),'mobile-plan','--duration','75'],capture_output=True,text=True)
        self.assertEqual(result.returncode,2)
        self.assertIn('--max-bytes',result.stderr)
    def test_invalid_mobile_inputs(self):
        for dur in (0,-1,float('nan'),True):
            with self.assertRaises(ValueError):e.mobile_plan(dur,25_000_000)
    def test_audio_cannot_exceed_budget(self):
        with self.assertRaises(ValueError):e.mobile_plan(90000,25_000_000)


class EpisodeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        (self.root/'final.bin').write_bytes(b'SYNTHETIC-NOT-A-VIDEO')
        a={'path':'final.bin','sha256':e.sha((self.root/'final.bin').read_bytes())}
        (self.root/'review.json').write_text(json.dumps({'status':'ACCEPTED','subject_sha256':a['sha256']}))
        self.rec={'status':'EPISODE_DELIVERABLE','final_artifact':a,'final_review':{'path':'review.json','sha256':e.sha((self.root/'review.json').read_bytes())},
            'final_gate_accepted':True,'state_archived':True,'lessons_recorded':True,'costs_reconciled':True,'unknown_submission_ids':[],'mobile_required':False}
    def tearDown(self):self.tmp.cleanup()
    def test_complete_record(self):self.assertEqual(e.episode_ready(self.rec,self.root),[])
    def test_script_done_is_not_episode_done(self):self.rec['status']='SCRIPT_ACCEPTED';self.assertTrue(e.episode_ready(self.rec,self.root))
    def test_missing_final_file(self):(self.root/'final.bin').unlink();self.assertTrue(e.episode_ready(self.rec,self.root))
    def test_stale_final_hash(self):(self.root/'final.bin').write_bytes(b'changed');self.assertTrue(e.episode_ready(self.rec,self.root))
    def test_unrecorded_lessons_block_progress(self):self.rec['lessons_recorded']=False;self.assertTrue(e.episode_ready(self.rec,self.root))
    def test_unknown_submission_blocks(self):self.rec['unknown_submission_ids']=['J'];self.assertTrue(e.episode_ready(self.rec,self.root))
    def test_missing_phone_variant(self):self.rec['mobile_required']=True;self.assertTrue(e.episode_ready(self.rec,self.root))
    def test_pending_known_cost_is_not_unknown_submission(self):self.rec['costs_pending_settlement']=['KNOWN'];self.assertEqual(e.episode_ready(self.rec,self.root),[])


if __name__=='__main__':unittest.main()
