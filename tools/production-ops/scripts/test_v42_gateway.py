"""Mock gateway exercises one-send/recovery; NO external generation calls."""
from copy import deepcopy
from datetime import datetime,timedelta,timezone
from pathlib import Path
import hashlib
import tempfile
import unittest
import brain_handoff as b
import prompt_contract as p
from job_ledger import Ledger
from trusted_runtime import Gateway,RegisteredAdapter,verify,protected_path_errors
from fixtures_v4 import Fixture
from fixtures_v42 import keys,signed


class MockAdapter:
    def __init__(self):self.calls=0;self.fail=False
    def submit(self,request,idempotency_key):
        self.calls+=1
        if self.fail:raise TimeoutError('test interruption')
        return {'task_id':'MOCK_TASK_'+str(self.calls),'synthetic':True}


class Gateway42Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.x=Fixture(self.root,[])
        self.raw,self.keys=keys();self.ledger=Ledger(self.root/'jobs.sqlite')
        self.x.packet['policy_version']='4.2.0';self.x.put('sequence.json',{'test_only':True});task=self.x.packet['tasks'][0]
        task['continuity_plan']=self.x.record('sequence.json')
        task['semantic_review']={'request_sha256':task['request_sha256'],'result':'PASS','reviewer_id':'SYNTHETIC','observation':'SYNTHETIC semantic fixture',
                                'coverage':sorted(p.SEMANTIC_COVERAGE),'evidence':self.x.record('proof.md')}
        self.x.save_packet();self.adapter=MockAdapter()
        req={'provider':'MOCK','account_scope':'TEST','model_id':'TEST_ONLY','project_id':'TEST','shot_id':'S1','stage':'video','parameters':{'steps':50},'input_hashes':[],
             'prompt_sha256':hashlib.sha256(self.x.request['prompt'].encode()).hexdigest(),'brain_request_sha256':task['request_sha256'],'adapter_sha256':'a'*64}
        task['native_request_sha256']=b.digest(req);self.x.save_packet()
        self.scope={'batch_id':'B','currency':'TEST','expires_at':(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat(),'quote_source':'SYNTHETIC NO CHARGE',
                    'mode':'local_no_api_charge','cap_minor':0,'items':[{'logical_id':'L','attempt':1,'request':req,'ceiling_minor':0}]}
        prepared=self.ledger.prepare(self.scope);self.job=prepared['job_ids'][0]
        self.creative=signed(self.raw,'creative',scope={'packet':self.x.binding['packet'],'task_id':'TASK1','request_sha256':task['request_sha256']})
        self.budget=signed(self.raw,'budget',scope_sha256=prepared['scope_sha256'],source_ref='SYNTHETIC user authorization')
        self.good_gate=lambda t,r:{'status':'PASS','brain_request_sha256':t['request_sha256'],'native_request_sha256':b.digest(r),'synthetic':True}
        self.g=Gateway(self.root,self.ledger,self.keys,{'M':RegisteredAdapter(self.adapter,'a'*64,'MOCK','TEST')},self.good_gate)
    def tearDown(self):self.ledger.close();self.tmp.cleanup()
    def dispatch(self):return self.g.dispatch(job_id=self.job,binding=self.x.binding,creative_approval=self.creative,cost_approval=self.budget,adapter_id='M')
    def test_mock_submission_once(self):
        self.assertEqual(self.dispatch()['action'],'SUBMITTED');self.assertEqual(self.adapter.calls,1)
    def test_repeat_calls_reconcile_not_resend(self):
        self.dispatch();self.assertEqual(self.dispatch()['action'],'RECONCILE_ONLY');self.assertEqual(self.adapter.calls,1)
    def test_timeout_remains_unknown(self):
        self.adapter.fail=True;self.assertEqual(self.dispatch()['state'],'SUBMISSION_UNKNOWN');self.dispatch();self.assertEqual(self.adapter.calls,1)
    def test_tampered_signature_blocks_before_send(self):
        self.creative['payload']['scope']['request_sha256']='0'*64
        with self.assertRaises(ValueError):self.dispatch()
        self.assertEqual(self.adapter.calls,0)
    def test_wrong_approval_role_blocks(self):
        self.creative=self.budget
        with self.assertRaises(ValueError):self.dispatch()
    def test_unapproved_task_blocks(self):
        self.creative=signed(self.raw,'creative',scope={})
        with self.assertRaises(ValueError):self.dispatch()
    def test_changed_budget_scope_blocks(self):
        self.budget=signed(self.raw,'budget',scope_sha256='0'*64,source_ref='TEST')
        with self.assertRaises(ValueError):self.dispatch()
    def test_media_gate_must_be_current(self):
        self.g.validator=lambda t,r:{'status':'PASS','brain_request_sha256':'0'*64,'native_request_sha256':b.digest(r)}
        with self.assertRaises(ValueError):self.dispatch()
    def test_legacy_downgrade_blocked(self):
        self.x.packet['policy_version']='4.1.0';self.x.save_packet()
        with self.assertRaises(ValueError):self.dispatch()
    def test_untrusted_key_blocked(self):
        self.g.keys={}
        with self.assertRaises(ValueError):self.dispatch()
    def test_expired_approval_blocked(self):
        future=datetime.now(timezone.utc)+timedelta(days=2)
        with self.assertRaises(ValueError):verify(self.creative,self.keys,'creative',future)
    def test_adapter_hash_cannot_change(self):
        self.g.adapters['M']=RegisteredAdapter(self.adapter,'b'*64,'MOCK','TEST')
        with self.assertRaises(ValueError):self.dispatch()
    def test_prompt_mapping_cannot_change(self):
        import json
        row=self.ledger._job(self.job);request=json.loads(row['request_json']);request['prompt_sha256']='0'*64
        self.ledger.db.execute('UPDATE jobs SET request_json=? WHERE job_id=?',(json.dumps(request),self.job))
        with self.assertRaises(ValueError):self.dispatch()
    def test_shared_uid_is_not_reported_protected(self):
        uid=(self.root/'proof.md').stat().st_uid
        self.assertTrue(protected_path_errors(self.root/'proof.md',worker_uid=uid,host_uid=uid))
    def test_native_parameters_are_frozen_beyond_prompt(self):
        self.x.packet['tasks'][0]['native_request_sha256']='0'*64;self.x.save_packet()
        self.creative=signed(self.raw,'creative',scope={'packet':self.x.binding['packet'],'task_id':'TASK1','request_sha256':self.x.packet['tasks'][0]['request_sha256']})
        with self.assertRaises(ValueError):self.dispatch()
        self.assertEqual(self.adapter.calls,0)
    def test_submission_produces_a_real_safe_receipt(self):
        out=self.dispatch();rec=out['receipt'];self.assertEqual(b.verify_record(rec,self.root),[])
        value=b.read_json(self.root/rec['path']);self.assertEqual(value['remote_task_id'],out['remote_task_id'])
        self.assertNotIn('credentials',value)
    def test_gateway_never_claims_video_quality(self):self.assertFalse(self.dispatch()['media_quality_verified'])


if __name__=='__main__':unittest.main()
