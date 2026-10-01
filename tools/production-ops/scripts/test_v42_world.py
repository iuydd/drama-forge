"""Typed, cross-object constraints and legal continuous camera coverage."""
from copy import deepcopy
import unittest
import world_constraints as w
import sequence_continuity as s
import test_sequence_continuity as old

class World42Tests(unittest.TestCase):
    def test_unheld_unsupported_paper_cannot_claim_persistent_attachment(self):
        rules=[{'id':'support','op':'requires','basis_ref':'TEST','when':{'held':False,'paper_on_wall':True},'then':{'tape_attached':True}}]
        self.assertTrue(w.check_states({'A':{'held':False,'paper_on_wall':True,'tape_attached':False}},rules))
    def test_actual_support_is_legal(self):
        rules=[{'id':'support','op':'requires','basis_ref':'TEST','when':{'held':False,'paper_on_wall':True},'then':{'tape_attached':True}}]
        self.assertEqual(w.check_states({'A':{'held':False,'paper_on_wall':True,'tape_attached':True}},rules),[])
    def test_unique_object_cannot_be_in_two_hands(self):
        rules=[{'id':'single_object','op':'unique_nonempty','keys':['handA','handB'],'basis_ref':'TEST'}]
        self.assertTrue(w.check_states({'S':{'handA':'KEY','handB':'KEY'}},rules))
    def test_two_empty_hands_are_legal(self):
        rules=[{'id':'single_object','op':'unique_nonempty','keys':['handA','handB'],'basis_ref':'TEST'}]
        self.assertEqual(w.check_states({'S':{'handA':None,'handB':None}},rules),[])
    def test_bool_not_interchangeable_with_count(self):
        rules=[{'id':'x','op':'not_all','when':{'value':True},'basis_ref':'TEST'}]
        self.assertEqual(w.check_states({'S':{'value':1}},rules),[])
    def test_missing_registered_fact_fails(self):
        self.assertTrue(w.check_states({'S':{'x':True}},[{'id':'x','op':'not_all','when':{'missing':True},'basis_ref':'TEST'}]))
    def test_moving_camera_not_only_two_endpoints(self):
        self.assertTrue(w.check_camera_path({'camera_pose_start':'A','camera_pose_end':'B'}))
    def test_fixed_camera_needs_no_extra_fields(self):self.assertEqual(w.check_camera_path({}),[])
    def test_full_camera_path_legal(self):
        shot={'camera_pose_start':'A','camera_pose_end':'B','camera_path':{'basis_ref':'TEST','waypoints':[{'id':'in','progress':0,'pose':'A','visibility_basis':'front'}, {'id':'middle','progress':.5,'pose':'M','visibility_basis':'occlusion established'}, {'id':'out','progress':1,'pose':'B','visibility_basis':'back reference'}]}}
        self.assertEqual(w.check_camera_path(shot),[])
    def test_camera_progress_reversal_rejected(self):
        shot={'camera_pose_start':'A','camera_pose_end':'B','camera_path':{'basis_ref':'TEST','waypoints':[{'id':'in','progress':0,'pose':'A','visibility_basis':'front'}, {'id':'middle','progress':1,'pose':'M','visibility_basis':'occlusion'}, {'id':'out','progress':.5,'pose':'B','visibility_basis':'back'}]}}
        self.assertTrue(w.check_camera_path(shot))
    def test_v42_empty_scope_requires_explanation(self):
        plan=old.fixture();plan['policy_version']='4.2.0'
        self.assertTrue(any('empty observation scope' in e for e in s.resolve(plan)[1]))
    def test_v42_all_explicit_dependencies_and_legitimate_offscreen_scope(self):
        plan=old.fixture();plan['policy_version']='4.2.0'
        for row in plan['shots']:
            row['projection_dependencies']={k:list(row['state_keys']) for k in row['screen_start']}
            if not row['visible_start_keys']:row['empty_observation_scope']={'reason':'tracked street props outside indoor camera','basis_ref':'TEST scene view'}
        self.assertEqual(s.resolve(plan)[1],[])

if __name__=='__main__':unittest.main()
