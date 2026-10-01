"""Return capsule integrity, duplicate recovery and signed acceptance tests."""
from copy import deepcopy
from pathlib import Path
import json
import tempfile
import unittest
import zipfile
import brain_handoff as b
import brain_exchange as e
from fixtures_v42 import seed_return,keys,signed


class Exchange42Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.ret,self.packet=seed_return(self.root);self.raw,self.keys=keys()
        (self.root/'review.json').write_text('{"synthetic_only":true,"result":"PASS"}')
        self.review=e.file_record(self.root,'review.json')
        self.db=e.WorkflowStore(self.root/'state.sqlite')
        auth=signed(self.raw,'creative',scope={'packet':self.ret['base_packet'],'packet_id':'P','episode_id':'EP001'})
        self.db.register_packet(self.packet,self.ret['base_packet'],auth,self.keys)
    def tearDown(self):self.db.close();self.tmp.cleanup()
    def test_complete_return_valid(self):self.assertEqual(e.validate_return(self.ret,self.root),[])
    def test_import_does_not_accept_candidate(self):
        out=self.db.ingest(self.ret,self.root);self.assertFalse(out['accepted']);self.assertEqual(self.db.db.execute('SELECT status FROM candidates').fetchone()[0],'PENDING')
    def test_repeat_return_is_idempotent(self):
        self.db.ingest(self.ret,self.root);self.assertEqual(self.db.ingest(self.ret,self.root)['status'],'ALREADY_IMPORTED')
    def test_same_return_id_cannot_change_contents(self):
        self.db.ingest(self.ret,self.root);self.ret['issues'].append('new issue')
        with self.assertRaises(ValueError):self.db.ingest(self.ret,self.root)
    def test_stale_base_blocks(self):
        self.db.db.execute("UPDATE active SET packet_sha=?",('0'*64,))
        with self.assertRaises(ValueError):self.db.ingest(self.ret,self.root)
    def test_actual_request_cannot_change_prompt(self):
        self.ret['actual_requests'][0]['request']=deepcopy(self.ret['actual_requests'][0]['request']);self.ret['actual_requests'][0]['request']['prompt']='changed'
        self.assertTrue(e.validate_return(self.ret,self.root))
    def test_return_cannot_declare_accepted(self):
        self.ret['outputs'][0]['status']='ACCEPTED';self.assertTrue(e.validate_return(self.ret,self.root))
    def test_new_output_requires_actual_job(self):
        self.ret['actual_requests']=[];self.assertTrue(e.validate_return(self.ret,self.root))
    def test_wrong_observed_media_blocks(self):
        self.ret['observations']=[{'subject_sha256':'0'*64,'result':'PASS','observation':'TEST','evidence':[self.ret['base_packet']]}]
        self.assertTrue(e.validate_return(self.ret,self.root))
    def test_nonmedia_bytes_cannot_pass_as_picture(self):
        (self.root/'image.png').write_bytes(b'not an image');self.ret['outputs'][0]['file']=e.file_record(self.root,'image.png')
        self.assertTrue(e.validate_return(self.ret,self.root))
    def test_pack_unpack_preserves_real_bytes(self):
        target=self.root/'out';target.mkdir();cap=self.root/'return.zip';e.export_return(self.ret,self.root,cap)
        unpacked=e.unpack_return(cap,target)
        self.assertEqual(unpacked,self.ret);self.assertEqual((target/'image.png').read_bytes(),(self.root/'image.png').read_bytes())
    def test_capsule_does_not_overwrite_existing_file(self):
        target=self.root/'out';target.mkdir();(target/'image.png').write_bytes(b'existing original')
        cap=self.root/'return.zip';e.export_return(self.ret,self.root,cap)
        with self.assertRaises(FileExistsError):e.unpack_return(cap,target)
        self.assertEqual((target/'image.png').read_bytes(),b'existing original')
    def test_capsule_transport_limit(self):
        target=self.root/'out';target.mkdir();cap=self.root/'return.zip';e.export_return(self.ret,self.root,cap)
        with self.assertRaises(ValueError):e.unpack_return(cap,target,max_uncompressed_bytes=1)
    def test_capsule_rejects_undeclared_or_path_traversal_member(self):
        target=self.root/'out';target.mkdir();cap=self.root/'return.zip';e.export_return(self.ret,self.root,cap)
        with zipfile.ZipFile(cap,'a') as z:z.writestr('../escape.txt','bad')
        with self.assertRaises(ValueError):e.unpack_return(cap,target)
    def test_signed_acceptance_is_separate(self):
        self.db.ingest(self.ret,self.root)
        scope={'return_id':'R','return_sha256':b.digest(self.ret),'accepted':[{'asset_id':'A','sha256':self.ret['outputs'][0]['file']['sha256']}]}
        d=signed(self.raw,'creative',operation='accept_return_outputs',scope=scope,review_evidence=[self.review],reviewed_subjects=scope['accepted'])
        self.assertEqual(self.db.apply_decision(d,self.keys)['status'],'ACCEPTED_BY_SIGNED_DECISION')
    def test_budget_key_role_cannot_accept_media(self):
        self.db.ingest(self.ret,self.root)
        d=signed(self.raw,'budget',operation='accept_return_outputs',scope={})
        with self.assertRaises(ValueError):self.db.apply_decision(d,self.keys)
    def test_acceptance_of_unreturned_hash_rejected(self):
        self.db.ingest(self.ret,self.root)
        d=signed(self.raw,'creative',operation='accept_return_outputs',scope={'return_id':'R','return_sha256':b.digest(self.ret),'accepted':[{'asset_id':'A','sha256':'0'*64}]})
        with self.assertRaises(ValueError):self.db.apply_decision(d,self.keys)
    def test_accepted_decision_replay_is_idempotent(self):
        self.db.ingest(self.ret,self.root)
        scope={'return_id':'R','return_sha256':b.digest(self.ret),'accepted':[{'asset_id':'A','sha256':self.ret['outputs'][0]['file']['sha256']}]}
        d=signed(self.raw,'creative',operation='accept_return_outputs',scope=scope,review_evidence=[self.review],reviewed_subjects=scope['accepted'])
        self.db.apply_decision(d,self.keys);self.assertEqual(self.db.apply_decision(d,self.keys)['status'],'ALREADY_APPLIED')
    def test_signed_acceptance_still_requires_actual_observation(self):
        self.db.ingest(self.ret,self.root)
        scope={'return_id':'R','return_sha256':b.digest(self.ret),'accepted':[{'asset_id':'A','sha256':self.ret['outputs'][0]['file']['sha256']}]}
        d=signed(self.raw,'creative',operation='accept_return_outputs',scope=scope)
        with self.assertRaises(ValueError):self.db.apply_decision(d,self.keys)
    def test_registration_checks_the_real_packet(self):
        altered=deepcopy(self.packet);altered['phase']='video'
        auth=signed(self.raw,'creative',scope={'packet':self.ret['base_packet'],'packet_id':'P','episode_id':'EP001'})
        with self.assertRaises(ValueError):self.db.register_packet(altered,self.ret['base_packet'],auth,self.keys)
    def test_conflicting_record_path_blocked(self):
        with self.assertRaises(ValueError):e.records_in([{'path':'a','sha256':'0'*64},{'path':'a','sha256':'1'*64}])


if __name__=='__main__':unittest.main()
