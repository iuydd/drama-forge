from __future__ import annotations
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import tempfile
import threading
import unittest
import dialogue_audit as a
import job_ledger as j
import production_gates as g


def dialogue_fixture():
    c = {'lines': [{'line_id': 'L1', 'speaker_id': 'CHAR-A', 'voice_id': 'VOICE-A',
                   'source_kind': 'spoken', 'text_spoken': '这不是我的钥匙。',
                   'lipsync_required': True, 'allowed_window_s': [0, 4]}]}
    o = {'whole_audio_transcribed': True, 'speech_segment_ids': ['seg1'], 'lines': [
        {'line_id': 'L1', 'speaker_id': 'CHAR-A', 'voice_id': 'VOICE-A',
         'source_kind': 'spoken', 'text_observed': '这不是我的钥匙', 'start_s': .2, 'end_s': 3,
         'segment_ids': ['seg1'], 'speaker_verified': True, 'source_verified': True,
         'mouth_review': 'PASS'}]}
    return c, o


class DialogueTests(unittest.TestCase):
    def test_typography(self):
        self.assertTrue(a.compare_text('“你好，世界！”', '你好 世界')['match'])
    def test_decimal_preserved(self):
        self.assertFalse(a.compare_text('3.5元', '35元')['match'])
    def test_negative_preserved(self):
        self.assertFalse(a.compare_text('-3', '3')['match'])
    def test_fullwidth_decimal(self):
        self.assertTrue(a.compare_text('３．５', '3.5')['match'])
    def test_negation_missing(self):
        self.assertFalse(a.compare_text('这不是我的', '这是我的')['match'])
    def test_name_homophone_not_auto_accepted(self):
        self.assertFalse(a.compare_text('林川', '林穿')['match'])
    def test_numeral_not_silently_rewritten(self):
        self.assertFalse(a.compare_text('三个', '3个')['match'])
    def test_match_is_not_audio_approval(self):
        c,o=dialogue_fixture(); r=a.audit(c,o)
        self.assertEqual(r['status'], 'RECORDS_MATCH_NOT_AUDIO_APPROVAL')
        self.assertFalse(r['audio_was_listened_to_by_this_tool'])
    def test_matching_text_cannot_hide_failed_listening_or_unexpected_speech(self):
        for change,issue in [({'review_status':'FAIL'},'listening_review_failed'),
                             ({'unexpected_speech':['unresolved extra syllable']},'unexpected_speech_requires_listen')]:
            with self.subTest(change=change):
                c,o=dialogue_fixture();o.update(change)
                result=a.audit(c,o)
                self.assertEqual(result['status'],'REVIEW_REQUIRED')
                self.assertIn(issue,result['issues'])
    def test_asr_correction_requires_recorded_listening_evidence(self):
        c,o=dialogue_fixture();row=o['lines'][0]
        row['asr_correction_reason']='ASR spelling corrected after targeted listening.'
        for evidence in (None,[],['heard it'],[{'path':'listen.txt','sha256':None}]):
            with self.subTest(evidence=evidence):
                row['targeted_listening_evidence']=evidence
                self.assertIn('asr_correction_listening_evidence_missing',a.audit(c,o)['lines'][0]['issues'])
        row['targeted_listening_evidence']=[{'path':'listen.txt','sha256':'a'*64}]
        result=a.audit(c,o)
        self.assertEqual(result['status'],'RECORDS_MATCH_NOT_AUDIO_APPROVAL')
        self.assertFalse(result['audio_was_listened_to_by_this_tool'])
    def test_wrong_voice_even_with_exact_words(self):
        c,o=dialogue_fixture();o['lines'][0]['voice_id']='VOICE-B'
        self.assertIn('voice_id_mismatch',a.audit(c,o)['lines'][0]['issues'])
    def test_wrong_speaker(self):
        c,o=dialogue_fixture();o['lines'][0]['speaker_id']='CHAR-B'
        self.assertIn('speaker_id_mismatch',a.audit(c,o)['lines'][0]['issues'])
    def test_unknown_speaker(self):
        c,o=dialogue_fixture();o['lines'][0]['speaker_id']=None
        self.assertIn('speaker_id_unknown',a.audit(c,o)['lines'][0]['issues'])
    def test_missing_line(self):
        c,o=dialogue_fixture();o['lines']=[]
        self.assertIn('L1: missing_line',a.audit(c,o)['issues'])
    def test_extra_speech(self):
        c,o=dialogue_fixture();o['speech_segment_ids'].append('seg2')
        self.assertEqual(a.audit(c,o)['unassigned_speech_segments'],['seg2'])
    def test_missing_whole_audio(self):
        c,o=dialogue_fixture();o['whole_audio_transcribed']=False
        self.assertIn('whole_audio_coverage_missing',a.audit(c,o)['issues'])
    def test_two_segments_one_sentence(self):
        c,o=dialogue_fixture();o['speech_segment_ids'].append('seg2');o['lines'][0]['segment_ids'].append('seg2')
        self.assertEqual(a.audit(c,o)['issues'],[])
    def test_reused_segment(self):
        c,o=dialogue_fixture();o['lines'][0]['segment_ids'].append('seg1')
        self.assertIn('alignment_segment_reused',a.audit(c,o)['lines'][0]['issues'])
    def test_lipsync_missing(self):
        c,o=dialogue_fixture();o['lines'][0]['mouth_review']='UNKNOWN'
        self.assertIn('lipsync_not_verified',a.audit(c,o)['lines'][0]['issues'])
    def test_inner_speech_mouth(self):
        c,o=dialogue_fixture();c['lines'][0]['source_kind']='inner';c['lines'][0]['lipsync_required']=False
        o['lines'][0]['source_kind']='inner'
        self.assertIn('inner_mouth_behavior_not_verified',a.audit(c,o)['lines'][0]['issues'])
    def test_inner_with_closed_mouth(self):
        c,o=dialogue_fixture();c['lines'][0]['source_kind']='inner';c['lines'][0]['lipsync_required']=False
        o['lines'][0]['source_kind']='inner';o['lines'][0]['inner_mouth_not_speaking']=True
        self.assertEqual(a.audit(c,o)['issues'],[])
    def test_out_of_time(self):
        c,o=dialogue_fixture();o['lines'][0]['end_s']=5
        self.assertIn('outside_frozen_time_window',a.audit(c,o)['lines'][0]['issues'])
    def test_duplicate_line(self):
        c,o=dialogue_fixture();o['lines'].append(deepcopy(o['lines'][0]))
        with self.assertRaises(ValueError):a.audit(c,o)
    def test_silent_clip_still_requires_coverage(self):
        r=a.audit({'lines':[]},{'lines':[],'speech_segment_ids':[],'whole_audio_transcribed':True})
        self.assertEqual(r['issues'],[])


def scope_fixture(mode='metered',batch='B1',attempt=1):
    cost=100 if mode=='metered' else 0
    return {'batch_id':batch,'currency':'TEST_CENTS','expires_at':'2099-01-01T00:00:00+00:00',
            'quote_source':'SYNTHETIC_TEST_QUOTE_NOT_REAL_PRICE','mode':mode,'cap_minor':cost,
            'items':[{'logical_id':'P1/EP003-S1/video','attempt':attempt,'ceiling_minor':cost,
                      'request':{'project_id':'P1','shot_id':'EP003-S1','stage':'video',
                                 'provider':'FAKE_PROVIDER','account_scope':'test-account',
                                 'model_id':'FAKE_MODEL','parameters':{'steps':50},
                                 'input_hashes':['0'*64],'prompt_sha256':'1'*64}}]}


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.ledger=j.Ledger(self.root/'jobs.sqlite');self.scope=scope_fixture()
        self.info=self.ledger.prepare(self.scope);self.jid=self.info['job_ids'][0]
    def tearDown(self):self.ledger.close();self.temp.cleanup()
    def auth(self):
        self.ledger.record_authorization('B1',{'kind':'user_confirmation',
            'scope_sha256':self.info['scope_sha256'],'source_ref':'TEST_ONLY_NO_REAL_CONSENT',
            'principal':'synthetic-user'})
    def test_unapproved_blocked(self):
        self.assertEqual(self.ledger.claim_submission(self.jid)['action'],'BLOCKED')
    def test_exact_scope_confirmation(self):
        with self.assertRaises(ValueError):self.ledger.record_authorization('B1',{
            'kind':'user_confirmation','scope_sha256':'0'*64,'source_ref':'test','principal':'test'})
    def test_agent_cannot_use_free_proof_for_paid(self):
        with self.assertRaises(ValueError):self.ledger.record_authorization('B1',{
            'kind':'free_channel_verification','scope_sha256':self.info['scope_sha256'],'source_ref':'test','principal':'test'})
    def test_claim_only_once(self):
        self.auth();self.assertEqual(self.ledger.claim_submission(self.jid)['action'],'SEND_ONCE')
        self.assertEqual(self.ledger.claim_submission(self.jid)['action'],'RECONCILE_ONLY')
    def test_lost_process_reopen(self):
        self.auth();self.ledger.claim_submission(self.jid);self.ledger.close();self.ledger=j.Ledger(self.root/'jobs.sqlite')
        self.assertEqual(self.ledger.claim_submission(self.jid)['action'],'RECONCILE_ONLY')
    def test_response_lost(self):
        self.auth();self.ledger.claim_submission(self.jid);self.ledger.mark_unknown(self.jid,'test-timeout')
        self.assertEqual(self.ledger.claim_submission(self.jid)['state'],'SUBMISSION_UNKNOWN')
    def test_download_failure_not_resubmit(self):
        self.auth();self.ledger.claim_submission(self.jid);self.ledger.attach_remote(self.jid,'T1','test-response')
        self.ledger.reconcile(self.jid,'SUCCEEDED','T1','test-query',{'file_id':'F1'})
        self.assertEqual(self.ledger.claim_submission(self.jid)['action'],'RECONCILE_ONLY')
    def test_failure_keeps_cost_commitment(self):
        self.auth();self.ledger.claim_submission(self.jid)
        self.ledger.reconcile(self.jid,'FAILED','T1','test-query')
        self.assertEqual(self.ledger.summary('B1')['unsettled_commitment_minor'],100)
    def test_settled_failed_fee_is_real_amount(self):
        self.auth();self.ledger.claim_submission(self.jid);self.ledger.reconcile(self.jid,'FAILED','T1','test-query')
        self.ledger.settle(self.jid,75,'test-bill')
        r=self.ledger.summary('B1');self.assertEqual(r['settled_actual_minor'],75);self.assertEqual(r['unsettled_commitment_minor'],0)
    def test_unexpected_overcharge_halts(self):
        self.auth();self.ledger.claim_submission(self.jid);self.ledger.reconcile(self.jid,'SUCCEEDED','T1','test-query')
        self.ledger.settle(self.jid,110,'test-bill');self.assertTrue(self.ledger.summary('B1')['halted'])
    def test_stop_does_not_claim_remote_cancel(self):
        self.auth();self.ledger.claim_submission(self.jid);self.ledger.stop_batch('B1','test-stop')
        r=self.ledger.summary('B1');self.assertEqual(r['jobs'][0]['state'],'SUBMITTING');self.assertEqual(r['unsettled_commitment_minor'],100)
    def test_existing_batch_reused(self):self.assertTrue(self.ledger.prepare(self.scope)['reused'])
    def test_immutable_request(self):
        scope=deepcopy(self.scope);scope['items'][0]['request']['parameters']['steps']=30
        with self.assertRaises(ValueError):self.ledger.prepare(scope)
    def test_duplicate_attempt_new_batch_rejected(self):
        with self.assertRaises(ValueError):self.ledger.prepare(scope_fixture(batch='B2'))
    def test_new_candidate_needs_new_approval(self):
        b=self.ledger.prepare(scope_fixture(batch='B2',attempt=2))
        self.assertEqual(self.ledger.claim_submission(b['job_ids'][0])['action'],'BLOCKED')
    def test_unknown_cost_channel(self):
        s=scope_fixture(batch='B2',attempt=2);s['mode']='unknown'
        with self.assertRaises(ValueError):self.ledger.prepare(s)
    def test_quote_totals_bound(self):
        s=scope_fixture(batch='B2',attempt=2);s['cap_minor']=99
        with self.assertRaises(ValueError):self.ledger.prepare(s)
    def test_free_verified_once(self):
        s=scope_fixture(mode='verified_free',batch='FREE',attempt=2);b=self.ledger.prepare(s)
        self.ledger.record_authorization('FREE',{'kind':'free_channel_verification','scope_sha256':b['scope_sha256'],
            'source_ref':'synthetic-free-proof','principal':'test-adapter'})
        self.assertEqual(self.ledger.claim_submission(b['job_ids'][0])['action'],'SEND_ONCE')
    def test_expired_after_approval(self):
        self.auth();self.ledger.db.execute("UPDATE batches SET expires_at='2000-01-01T00:00:00+00:00'")
        self.assertEqual(self.ledger.claim_submission(self.jid)['action'],'BLOCKED')
    def test_conflicting_remote_id(self):
        self.auth();self.ledger.claim_submission(self.jid);self.ledger.attach_remote(self.jid,'T1','e1')
        with self.assertRaises(ValueError):self.ledger.attach_remote(self.jid,'T2','e2')
    def test_cancelled_not_automatically_refunded(self):
        self.auth();self.ledger.claim_submission(self.jid);self.ledger.reconcile(self.jid,'CANCELLED','T1','e1')
        self.assertEqual(self.ledger.summary('B1')['unsettled_commitment_minor'],100)
    def test_not_created_requires_reconciliation_and_no_auto_retry(self):
        self.auth();self.ledger.claim_submission(self.jid)
        self.ledger.reconcile(self.jid,'CONFIRMED_NOT_CREATED',None,'trusted-test-negative-evidence')
        self.assertEqual(self.ledger.claim_submission(self.jid)['action'],'RECONCILE_ONLY')
    def test_concurrent_workers_one_send(self):
        self.auth();barrier=threading.Barrier(2)
        def worker():
            ledger=j.Ledger(self.root/'jobs.sqlite')
            try:barrier.wait();return ledger.claim_submission(self.jid)['action']
            finally:ledger.close()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:worker(),range(2)))
        self.assertEqual(sorted(results),['RECONCILE_ONLY','SEND_ONCE'])


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.src=self.root/'source.bin';self.src.write_bytes(b'new')
    def tearDown(self):self.tmp.cleanup()
    def test_store(self):
        r=j.store_without_overwrite(self.src,self.root,'candidates/v1.bin',j.file_digest(self.src))
        self.assertEqual(r['status'],'STORED_CANDIDATE_NOT_MEDIA_APPROVAL')
    def test_reuse_same(self):
        sha=j.file_digest(self.src);j.store_without_overwrite(self.src,self.root,'out.bin',sha)
        self.assertEqual(j.store_without_overwrite(self.src,self.root,'out.bin',sha)['status'],'REUSED')
    def test_do_not_overwrite(self):
        target=self.root/'out.bin';target.write_bytes(b'accepted-old')
        with self.assertRaises(FileExistsError):j.store_without_overwrite(self.src,self.root,'out.bin',j.file_digest(self.src))
        self.assertEqual(target.read_bytes(),b'accepted-old')
    def test_wrong_hash(self):
        with self.assertRaises(ValueError):j.store_without_overwrite(self.src,self.root,'out.bin','0'*64)
        self.assertFalse((self.root/'out.bin').exists())
    def test_traversal(self):
        with self.assertRaises(ValueError):j.store_without_overwrite(self.src,self.root,'../out.bin',j.file_digest(self.src))
    def test_symlink(self):
        (self.root/'link').symlink_to(self.src)
        with self.assertRaises(ValueError):j.store_without_overwrite(self.src,self.root,'link',j.file_digest(self.src))


class GateTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        for name in ('subject.bin','contract.json','evidence.json'):
            (self.root/name).write_text('SYNTHETIC_TEST_RECORD_NOT_MEDIA',encoding='utf-8')
    def tearDown(self):self.tmp.cleanup()
    def record(self,name):return {'path':name,'sha256':g.file_sha(self.root/name)}
    def fixture(self,action='pre_video'):
        spec={'schema_version':'production-ops-1','action':action,'subject':self.record('subject.bin'),
              'contracts':[self.record('contract.json')],'is_adaptation':False,'uses_upscale':False,
              'line_ids':['L1'],'shot_ids':['S1'],'comprehension_fact_ids':['F1'],
              'audio_targets':{'integrated_lufs':-16,'integrated_tolerance_lu':1,'max_true_peak_dbtp':-1},
              'delivery':{'width':1080,'height':1920}}
        details={'line_ids':['L1'],'unresolved_line_ids':[],'unassigned_speech_segment_ids':[],
                 'shot_ids':['S1'],'blind_context_clean':True,'essential_fact_results':{'F1':'clear'},
                 'retelling':'Synthetic viewer retelling, not an actual viewer test.',
                 'unreconciled_attempt_ids':[],'authorization_verified':True,'source_event_ref':'SYNTHETIC',
                 'integrated_lufs':-16,'true_peak_dbtp':-1.2,'listening_review':'PASS',
                 'width':1080,'height':1920,'av_sync_review':'PASS'}
        reports=[{'check_id':cid,'status':'PASS','snapshot_sha256':g.digest(spec),
                  'subject_sha256':spec['subject']['sha256'],'evidence':[self.record('evidence.json')],
                  'observation':'Synthetic test observation only.','details':deepcopy(details)}
                 for cid in sorted(g.REQUIRED[action])]
        return spec,reports
    def find(self,reports,cid):return next(r for r in reports if r['check_id']==cid)
    def test_pre_video_record_integrity(self):
        s,r=self.fixture();self.assertEqual(g.gate(s,r,self.root)['status'],'ACCEPTED')
    def test_no_animatic_blocks(self):
        s,r=self.fixture();r=[x for x in r if x['check_id']!='animatic'];self.assertEqual(g.gate(s,r,self.root)['status'],'BLOCKED')
    def test_no_blind_comprehension_blocks(self):
        s,r=self.fixture();r=[x for x in r if x['check_id']!='comprehension'];self.assertEqual(g.gate(s,r,self.root)['status'],'BLOCKED')
    def test_viewer_knows_script_blocks(self):
        s,r=self.fixture();self.find(r,'comprehension')['details']['blind_context_clean']=False
        self.assertEqual(g.gate(s,r,self.root)['status'],'BLOCKED')
    def test_misunderstood_cause_rejected(self):
        s,r=self.fixture();self.find(r,'comprehension')['details']['essential_fact_results']['F1']='contradicted'
        self.assertEqual(g.gate(s,r,self.root)['status'],'REJECTED')
    def test_intended_mystery_not_required(self):
        s,r=self.fixture();self.find(r,'comprehension')['details']['essential_fact_results']['FUTURE']='intentionally_unknown'
        self.assertEqual(g.gate(s,r,self.root)['status'],'ACCEPTED')
    def test_unreconciled_task_blocks(self):
        s,r=self.fixture();self.find(r,'recovery_check')['details']['unreconciled_attempt_ids']=['A1']
        self.assertEqual(g.gate(s,r,self.root)['status'],'BLOCKED')
    def test_unconfirmed_batch_blocks(self):
        s,r=self.fixture();self.find(r,'batch_authorization')['details']['authorization_verified']=False
        self.assertEqual(g.gate(s,r,self.root)['status'],'BLOCKED')
    def test_stale_contract_snapshot(self):
        s,r=self.fixture();s['line_ids'].append('L2');self.assertEqual(g.gate(s,r,self.root)['status'],'BLOCKED')
    def test_evidence_changed(self):
        s,r=self.fixture();(self.root/'evidence.json').write_text('different')
        self.assertEqual(g.gate(s,r,self.root)['status'],'BLOCKED')
    def test_wrong_subject_hash(self):
        s,r=self.fixture();r[0]['subject_sha256']='0'*64;self.assertEqual(g.gate(s,r,self.root)['status'],'BLOCKED')
    def test_dialogue_coverage_missing(self):
        s,r=self.fixture('shot_edit');self.find(r,'dialogue')['details']['line_ids']=[]
        self.assertEqual(g.gate(s,r,self.root)['status'],'BLOCKED')
    def test_spoken_lines_need_current_listening_review_not_only_asr(self):
        for action,cid in [('shot_edit','dialogue'),('final_delivery','dialogue_coverage')]:
            for state,status in [(None,'BLOCKED'),('UNKNOWN','BLOCKED'),('FAIL','REJECTED')]:
                with self.subTest(action=action,state=state):
                    s,r=self.fixture(action)
                    details=self.find(r,cid)['details']
                    if state is None:details.pop('listening_review')
                    else:details['listening_review']=state
                    self.assertEqual(g.gate(s,r,self.root)['status'],status)
    def test_no_dialogue_does_not_add_a_spoken_line_listening_requirement(self):
        s,r=self.fixture('shot_edit');s['line_ids']=[]
        for row in r:
            row['snapshot_sha256']=g.digest(s);row['details']['line_ids']=[]
            row['details'].pop('listening_review',None)
        self.assertEqual(g.gate(s,r,self.root)['status'],'ACCEPTED')
    def test_partial_successes_from_different_takes_cannot_combine(self):
        s,r=self.fixture('shot_edit')
        (self.root/'old-take.bin').write_bytes(b'synthetic previous take')
        self.find(r,'visual_video')['subject_sha256']=self.record('old-take.bin')['sha256']
        self.assertEqual(g.gate(s,r,self.root)['status'],'BLOCKED')
    def test_extra_unassigned_speech(self):
        s,r=self.fixture('shot_edit');self.find(r,'dialogue')['details']['unassigned_speech_segment_ids']=['extra']
        self.assertEqual(g.gate(s,r,self.root)['status'],'BLOCKED')
    def test_wrong_speaker_check_failure(self):
        s,r=self.fixture('shot_edit');self.find(r,'speaker_source')['status']='FAIL'
        self.assertEqual(g.gate(s,r,self.root)['status'],'REJECTED')
    def test_final_record_integrity(self):
        s,r=self.fixture('final_delivery');self.assertEqual(g.gate(s,r,self.root)['status'],'ACCEPTED')
    def test_mix_peak(self):
        s,r=self.fixture('final_delivery');self.find(r,'mix')['details']['true_peak_dbtp']=0
        self.assertEqual(g.gate(s,r,self.root)['status'],'REJECTED')
    def test_mix_loudness(self):
        s,r=self.fixture('final_delivery');self.find(r,'mix')['details']['integrated_lufs']=-9
        self.assertEqual(g.gate(s,r,self.root)['status'],'REJECTED')
    def test_mix_not_listened(self):
        s,r=self.fixture('final_delivery');self.find(r,'mix')['details']['listening_review']='UNKNOWN'
        self.assertEqual(g.gate(s,r,self.root)['status'],'BLOCKED')
    def test_no_upscale_report(self):
        s,r=self.fixture('final_delivery');s['uses_upscale']=True
        for x in r:x['snapshot_sha256']=g.digest(s)
        self.assertIn('required report missing: upscale_review',g.gate(s,r,self.root)['blockers'])
    def test_no_adaptation_trace(self):
        s,r=self.fixture();s['is_adaptation']=True
        for x in r:x['snapshot_sha256']=g.digest(s)
        self.assertIn('required report missing: adaptation_trace',g.gate(s,r,self.root)['blockers'])
    def test_delivery_orientation(self):
        s,r=self.fixture('final_delivery');self.find(r,'delivery_spec')['details']['width']=1920
        self.assertEqual(g.gate(s,r,self.root)['status'],'REJECTED')
    def test_unapproved_publish(self):
        s,r=self.fixture('publish');self.find(r,'publication_authorization')['details']['authorization_verified']=False
        self.assertEqual(g.gate(s,r,self.root)['status'],'BLOCKED')
    def test_suggestions_no_overaudit(self):
        s,r=self.fixture();r.append({'check_id':'optional_more_cinematic','status':'FAIL'})
        self.assertEqual(g.gate(s,r,self.root)['status'],'ACCEPTED')
    def test_duplicate_report(self):
        s,r=self.fixture();r.append(deepcopy(r[0]));self.assertEqual(g.gate(s,r,self.root)['status'],'BLOCKED')

if __name__=='__main__':unittest.main()
