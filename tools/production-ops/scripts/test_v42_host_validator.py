"""Host composition tests with explicit mocked lower gates, no actual provider."""
from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import brain_handoff as b
import host_validator as h
VIS=Path(__file__).resolve().parents[2]/'visual-continuity-prompter/scripts'
if str(VIS) not in sys.path:sys.path.insert(0,str(VIS))
import continuity_tools

class HostValidator42Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.inputs={'scene':{},'shot':{'shot_id':'S','mode':'video_i2v','policy_version':'4.2.0'},'runtime_profile':{},'gate_spec':{'policy_version':'4.2.0','action':'pre_video'},'gate_reports':[]}
        self.request=b.request_snapshot(self.inputs['scene'],self.inputs['shot'],{},'SYNTHETIC')
        self.task={'request':self.request,'request_sha256':b.digest(self.request)};self.native={'SYNTHETIC':'native'}
        self.validator=h.BoundProductionValidator(self.root,lambda t:deepcopy(self.inputs),lambda t,i:deepcopy(self.native))
        self.compile=patch.object(continuity_tools,'compile_package',return_value={'status':'READY','prompt':'SYNTHETIC'});self.c=self.compile.start()
        self.gate=patch.object(h,'gate',return_value={'status':'ACCEPTED','snapshot_sha256':'TEST_ONLY'});self.g=self.gate.start()
    def tearDown(self):self.compile.stop();self.gate.stop();self.tmp.cleanup()
    def test_exact_composition_binds_both_digests(self):
        out=self.validator(self.task,self.native);self.assertEqual(out['brain_request_sha256'],b.digest(self.request));self.assertEqual(out['native_request_sha256'],b.digest(self.native));self.c.assert_called_once();self.g.assert_called_once()
    def test_current_not_prior_compiler_required(self):
        self.c.return_value['status']='DRAFT'
        with self.assertRaises(ValueError):self.validator(self.task,self.native)
    def test_real_gate_failure_not_replaced_by_compiler_ready(self):
        self.g.return_value['status']='REJECTED'
        with self.assertRaises(ValueError):self.validator(self.task,self.native)
    def test_changed_native_field_blocks(self):
        with self.assertRaises(ValueError):self.validator(self.task,{'different':True})
    def test_wrong_source_mapping_blocks(self):
        self.inputs['scene']={'unexpected':'scene'}
        with self.assertRaises(ValueError):self.validator(self.task,self.native)
    def test_no_invented_generic_preimage_action(self):
        self.task['request']['kind']='start_frame';self.inputs['shot']['mode']='edit_same_view'
        self.task['request']=b.request_snapshot({},self.inputs['shot'],{},'SYNTHETIC');self.inputs['gate_spec']['action']='pre_image'
        with self.assertRaisesRegex(ValueError,'video/pre_video only'):self.validator(self.task,self.native)

if __name__=='__main__':unittest.main()
