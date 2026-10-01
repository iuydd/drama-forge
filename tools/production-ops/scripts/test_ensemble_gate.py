from copy import deepcopy
import json
from pathlib import Path
import unittest
import production_gates as g
import ensemble_gate as eg
import test_production_ops as old

ROOT=Path(__file__).resolve().parents[2]


class EnsembleGateTests(unittest.TestCase):
    def setUp(self):
        self.old=old.GateTests('test_pre_video_record_integrity');self.old.setUp();self.root=self.old.root
        self.s,self.r=self.old.fixture('pre_video')
        self.b=json.loads((ROOT/'visual-continuity-prompter/examples/ensemble-demo.json').read_text())
        self.b['example_only']=False;self.b['scope']['shot_id']='S1'
        self.shot={'shot_id':'S1','scene_id':'ROOM1','scene_version':'1','view_id':'CAM_B','mode':'video_i2v','video':{'duration_s':4},'ensemble_required':True,'ensemble':self.b,
            'references':[dict(self.old.record('subject.bin'),role='start_frame',primary=True)]}
        self.put('shot.json',self.shot);self.put('previous.json',self.b['previous_state'])
        self.binding={'shot_id':'S1','shot_contract':self.old.record('shot.json'),'media':self.old.record('subject.bin'),'previous_state':self.old.record('previous.json'),
            'view_evidence':self.old.record('evidence.json'),'inventory_evidence':self.old.record('evidence.json')}
        self.s.update(episode_id='EP001',ensemble_required=True,ensemble_bindings=[self.binding])
        self.ob={'shot_id':'S1','media_sha256':self.binding['media']['sha256'],'ensemble_sha256':g.digest(self.b),'temporal_basis':'Synthetic test report, not visual evidence',
            'windows':[{'window_id':'W01','full_frame_result':'PASS','unexpected_visible_entities':[],
                        'entities':{i:{'result':'PASS','observation':'Synthetic test only'} for i in self.b['start_state']['entities']}}]}
        self.r.append({'check_id':'ensemble_continuity','status':'PASS','subject_sha256':self.s['subject']['sha256'],'evidence':[self.old.record('evidence.json')],
            'observation':'Synthetic ensemble report, no actual media inspected','details':{'shots':[self.ob]}})
        self.refresh()
    def put(self,name,value):(self.root/name).write_text(json.dumps(value,ensure_ascii=False))
    def refresh(self):
        self.put('shot.json',self.shot);self.binding['shot_contract']=self.old.record('shot.json')
        for r in self.r:r['snapshot_sha256']=g.digest(self.s)
    def tearDown(self):self.old.tearDown()
    def gate(self):return g.gate(self.s,self.r,self.root)
    def test_complete_record_integrity_only(self):self.assertEqual(self.gate()['status'],'ACCEPTED')
    def test_missing_binding_blocked(self):
        self.s['ensemble_bindings']=[];self.refresh();self.assertEqual(self.gate()['status'],'BLOCKED')
    def test_missing_observation_blocked(self):
        self.r=[r for r in self.r if r['check_id']!='ensemble_continuity'];self.assertEqual(self.gate()['status'],'BLOCKED')
    def test_supporting_actor_fail_not_overridden_by_pass(self):
        self.ob['windows'][0]['entities']['CHAR_B']['result']='FAIL';self.assertEqual(self.gate()['status'],'REJECTED')
    def test_absent_observation_row_blocks(self):
        del self.ob['windows'][0]['entities']['CHAR_B'];self.assertEqual(self.gate()['status'],'BLOCKED')
    def test_unknown_visibility_blocks_even_report_says_pass(self):
        self.b['view_plan']['windows'][0]['entities'][1]['visibility']='unknown';self.refresh();self.assertEqual(self.gate()['status'],'BLOCKED')
    def test_wrong_predecessor_file_not_new_canon(self):
        self.put('previous.json',{'snapshot_id':'another','entities':{}});self.binding['previous_state']=self.old.record('previous.json');self.refresh();self.assertEqual(self.gate()['status'],'BLOCKED')
    def test_empty_scene_not_validated_full_start_frame(self):
        self.shot['references'][0]['role']='scene_base';self.refresh();self.assertEqual(self.gate()['status'],'BLOCKED')
    def test_wrong_media_hash_cannot_reuse_report(self):
        self.ob['media_sha256']='0'*64;self.assertEqual(self.gate()['status'],'BLOCKED')
    def test_demo_cannot_be_called_production(self):
        self.b['example_only']=True;self.refresh();self.assertEqual(self.gate()['status'],'BLOCKED')
    def test_missing_inventory_evidence(self):
        self.binding['inventory_evidence']=None;self.refresh();self.assertEqual(self.gate()['status'],'BLOCKED')
    def test_wrong_episode_scope(self):
        self.b['scope']['episode_id']='EP002';self.refresh();self.assertEqual(self.gate()['status'],'BLOCKED')
    def test_extra_person_rejected(self):
        self.ob['windows'][0]['unexpected_visible_entities']=['unplanned human'];self.assertEqual(self.gate()['status'],'REJECTED')
    def test_legacy_not_silently_upgraded(self):
        self.s['ensemble_required']=False;self.refresh();self.r=[r for r in self.r if r['check_id']!='ensemble_continuity'];self.assertEqual(self.gate()['status'],'ACCEPTED')


if __name__=='__main__':unittest.main()
