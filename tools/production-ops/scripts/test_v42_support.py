"""Scope reuse, honest metrics, clock conventions and declared spatial math."""
from copy import deepcopy
import tempfile
from pathlib import Path
import unittest
import evaluation_tools as e
import spatial_math as s
import workflow_support as w
import test_sequence_continuity as seq


class Spatial42Tests(unittest.TestCase):
    def test_closed_single_frame_becomes_nonempty_half_open(self):self.assertEqual(s.half_open(4,4,'closed',5),(4,5))
    def test_last_frame_boundary(self):self.assertEqual(s.half_open(99,99,'closed',100),(99,100))
    def test_already_half_open_not_shifted(self):self.assertEqual(s.half_open(0,10,'half_open',10),(0,10))
    def test_missing_interval_convention_blocked(self):
        with self.assertRaises(ValueError):s.half_open(0,10,'guess')
    def test_outside_media_range_blocked(self):
        with self.assertRaises(ValueError):s.half_open(99,100,'closed',100)
    def test_rational_cfr_no_float_rounding(self):self.assertEqual(s.frame_from_time(1001,1000,30000,1001),30)
    def test_boolean_not_frame(self):
        with self.assertRaises(ValueError):s.half_open(True,5,'half_open')
    def test_recursive_bool_is_not_integer(self):self.assertFalse(s.equal_value({'n':[True]},{'n':[1]}))
    def test_approved_numeric_tolerance(self):
        t={'mode':'absolute','max_error':0.5,'unit':'pixel','reference_frame':'target_frame'}
        self.assertTrue(s.equal_value(10,10.2,t));self.assertFalse(s.equal_value(10,11,t))
    def test_tolerance_cannot_excuse_wrong_identity(self):
        with self.assertRaises(ValueError):s.equal_value('A','B',{'mode':'absolute','max_error':1,'unit':'m','reference_frame':'world'})
    def test_same_geometry_legal_opposite_camera_reverses_screen(self):
        c={'position':[0,-5,0],'target':[0,0,0],'up':[0,0,1],'width':640,'height':480,'vertical_fov_deg':45}
        self.assertEqual(s.projected_heading([-1,0,0],[1,0,0],c,1),'right')
        c['position']=[0,5,0];self.assertEqual(s.projected_heading([-1,0,0],[1,0,0],c,1),'left')
    def test_behind_camera_not_projected(self):
        c={'position':[0,-5,0],'target':[0,0,0],'width':640,'height':480,'vertical_fov_deg':45}
        self.assertFalse(s.project_point([0,-6,0],c)['projectable'])
    def test_degenerate_camera_rejected(self):
        c={'position':[0,0,0],'target':[0,0,0],'width':640,'height':480,'vertical_fov_deg':45}
        with self.assertRaises(ValueError):s.project_point([1,0,0],c)


class Workflow42Tests(unittest.TestCase):
    def test_only_revision_metadata_change_preserves_media_scopes(self):
        a=seq.fixture();b=deepcopy(a);b['revision']='2';r=w.diff_scopes(a,b)
        self.assertEqual(r['changed_shots'],[]);self.assertEqual(len(r['unchanged_shots']),3);self.assertTrue(r['requires_new_packet_approval'])
    def test_unrelated_new_camera_does_not_invalidate_existing_view(self):
        a=seq.fixture();b=deepcopy(a);b['scenes']['STREET']['views']['OTHER']=deepcopy(b['scenes']['STREET']['views']['V1'])
        self.assertEqual(w.diff_scopes(a,b)['changed_shots'],[])
    def test_changed_used_camera_invalidates_only_its_scene(self):
        a=seq.fixture();b=deepcopy(a);b['scenes']['STREET']['views']['V1']['orientation_basis']='different camera'
        self.assertEqual(w.diff_scopes(a,b)['changed_shots'],['S1','S3'])
    def test_changed_prompt_invalidates_shot_and_neighbor_cut(self):
        a=seq.fixture();b=deepcopy(a);b['shots'][1]['continuity_clause']='different authored visibility'
        result=w.diff_scopes(a,b);self.assertEqual(result['changed_shots'],['S2']);self.assertEqual(len(result['cuts_to_review']),2)
    def test_critical_chain_prioritized(self):
        tasks=[{'job_id':'A','depends_on':[],'priority':0,'queue_order':2},{'job_id':'B','depends_on':['A'],'priority':0,'queue_order':3},{'job_id':'C','depends_on':[],'priority':0,'queue_order':0}]
        self.assertEqual(w.critical_path_order(tasks)[0],'A')
    def test_critical_cycle_rejected(self):
        with self.assertRaises(ValueError):w.critical_path_order([{'job_id':'A','depends_on':['B']},{'job_id':'B','depends_on':['A']}])
    def test_user_priority_preserved(self):
        tasks=[{'job_id':'A','depends_on':[],'priority':0},{'job_id':'B','depends_on':['A'],'priority':3}]
        self.assertEqual(w.critical_path_order(tasks)[0],'B')
    def test_technical_lossless_alternative_allowed(self):
        policy={'approval_ref':'TEST','allowed_values':{'decoder':['a','b']},'immutable_keys':['codec']}
        self.assertEqual(w.technical_patch({'decoder':'a','steps':50},{'decoder':'b','steps':50},policy),[])
    def test_quality_reduction_not_technical_freedom(self):
        policy={'approval_ref':'TEST','allowed_values':{'steps':[25,50]},'immutable_keys':[]}
        self.assertTrue(w.technical_patch({'steps':50},{'steps':25},policy))
    def test_agent_cannot_rephrase_prompt(self):
        self.assertTrue(w.technical_patch({'prompt':'one'},{'prompt':'two'},{'approval_ref':'TEST','allowed_values':{}}))


class Evaluation42Tests(unittest.TestCase):
    def rows(self):
        return [{'run_id':'R','case_id':str(i),'attempt':1,'data_kind':'synthetic','ground_truth_defect':bad,'decision':result,'cost_minor':10,'accepted_seconds':2 if result=='PASS' else 0,
                 'input_tokens':None,'output_tokens':None,'variant':'A','currency':'TEST','runtime_config_sha256':'test-only'} for i,(bad,result) in enumerate([(True,'FAIL'),(True,'PASS'),(False,'FAIL'),(False,'PASS'),(False,'UNKNOWN')])]
    def test_reports_false_positive_and_false_negative(self):
        r=e.summarize(self.rows())['groups'][0];self.assertEqual((r['false_positive'],r['false_negative'],r['unknown']),(1,1,1))
    def test_unknown_not_silently_treated_as_pass(self):self.assertEqual(e.summarize(self.rows())['groups'][0]['known_decisions'],4)
    def test_missing_tokens_not_estimated(self):
        r=e.summarize(self.rows())['groups'][0]['actual_counters']['input_tokens'];self.assertFalse(r['complete']);self.assertEqual(r['missing_rows'],5)
    def test_real_claim_without_media_rejected(self):
        rows=self.rows();rows[0]['data_kind']='real'
        with self.assertRaises(ValueError):e.summarize(rows)
    def test_duplicate_experiment_identity_rejected(self):
        rows=self.rows();rows.append(deepcopy(rows[0]))
        with self.assertRaises(ValueError):e.summarize(rows)
    def test_no_real_samples_produces_zero_real_runs(self):self.assertEqual(e.summarize(self.rows())['real_runs'],0)
    def test_missing_cost_prevents_unit_cost_claim(self):
        rows=self.rows();rows[0]['cost_minor']=None;self.assertIsNone(e.summarize(rows)['groups'][0]['cost_minor_per_accepted_second'])
    def test_synthetic_and_real_not_pooled(self):self.assertEqual(e.summarize(self.rows())['groups'][0]['data_kind'],'synthetic')
    def test_empty_sample_has_no_success_interval(self):self.assertIsNone(e.wilson(0,0))
    def test_ab_coverage_must_match(self):
        rows=self.rows();other=deepcopy(rows[0]);other.update(run_id='R2',variant='B');rows.append(other)
        self.assertFalse(e.paired_comparison(rows)['paired_case_coverage'])
    def test_known_failure_cannot_claim_accepted_seconds(self):
        rows=self.rows();rows[0]['accepted_seconds']=5
        with self.assertRaises(ValueError):e.summarize(rows)


if __name__=='__main__':unittest.main()
