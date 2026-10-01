"""Reveal-arc structural regression tests; not model or viewer evaluation."""
from copy import deepcopy
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parent))
import drama_tools as tools

class RevealTests(unittest.TestCase):
    def setUp(self):
        self.data = deepcopy(tools.load_json(tools.ROOT / 'examples/reveal-arc.json'))
    def codes(self):
        return {x['code'] for x in tools.check_reveal(self.data)}
    def test_valid_example(self):
        self.assertEqual(tools.check_reveal(self.data), [])
    def test_missing_field(self):
        del self.data['core_truth']
        self.assertIn('REQUIRED', self.codes())
    def test_wrong_root(self):
        self.assertTrue(tools.has_errors(tools.check_reveal([])))
    def test_duplicate_actors(self):
        self.data['actors'].append(deepcopy(self.data['actors'][0]))
        self.assertIn('DUPLICATE_ID', self.codes())
    def test_unknown_fact(self):
        self.data['beats'][0]['evidence_fact_ids'].append('FACT-MISSING')
        self.assertIn('UNKNOWN_FACT', self.codes())
    def test_future_fact(self):
        self.data['beats'][0]['evidence_fact_ids'].append('FACT-010')
        self.assertIn('FUTURE_EVIDENCE', self.codes())
    def test_unknown_introduction(self):
        self.data['facts'][0]['introduced_at_beat']='B-MISSING'
        self.assertIn('UNKNOWN_BEAT', self.codes())
    def test_belief_chain(self):
        self.data['beats'][2]['belief_updates'][0]['before']='Wrong previous belief'
        self.assertIn('BELIEF_DISCONTINUITY', self.codes())
    def test_stance_chain(self):
        self.data['beats'][2]['public_moves'][0]['before']='Wrong previous stance'
        self.assertIn('STANCE_DISCONTINUITY', self.codes())
    def test_unknown_actor(self):
        self.data['beats'][1]['public_moves'][0]['actor_id']='CHAR-MISSING'
        self.assertIn('UNKNOWN_ACTOR', self.codes())
    def test_turn_without_basis_warns(self):
        self.data['beats'][1]['public_moves'][0]['basis_fact_ids']=[]
        self.assertIn('UNSUPPORTED_TURN', self.codes())
        self.assertFalse(tools.has_errors(tools.check_reveal(self.data)))
    def test_payoff_reset(self):
        self.data['beats'][2]['carry_forward_payoff_ids'].remove('PAY-001')
        self.assertIn('PAYOFF_RESET', self.codes())
    def test_unearned_payoff(self):
        self.data['beats'][0]['carry_forward_payoff_ids']=['PAY-001']
        self.assertIn('UNKNOWN_PAYOFF', self.codes())
    def test_duplicate_payoff(self):
        self.data['beats'][-1]['earned_payoffs'][0]['id']='PAY-001'
        self.assertIn('DUPLICATE_ID', self.codes())
    def test_setback_requires_reason(self):
        self.data['beats'][2]['setback_reason']=None
        self.assertIn('UNEXPLAINED_SETBACK', self.codes())
    def test_setback_no_progress_warns(self):
        self.data['beats'][2]['new_information']=''
        self.assertIn('STALL_RISK', self.codes())
    def test_setback_budget_is_not_absolute_ban(self):
        self.data['setback_budget']=0
        self.assertIn('SETBACK_BUDGET', self.codes())
        self.assertFalse(tools.has_errors(tools.check_reveal(self.data)))
    def test_late_anchor(self):
        self.data['audience_anchor']['scene_id']='EP02-S01'
        self.assertIn('LATE_AUDIENCE_ANCHOR', self.codes())
    def test_unknown_anchor(self):
        self.data['audience_anchor']['scene_id']='EP09-S01'
        self.assertIn('UNKNOWN_ANCHOR', self.codes())
    def test_mystery_can_delay_anchor(self):
        self.data['mode']='mystery'
        self.data['audience_anchor']['scene_id']='EP02-S01'
        self.assertNotIn('LATE_AUDIENCE_ANCHOR',self.codes())
    def test_scene_id_wrong_episode(self):
        self.data['beats'][0]['scene_id']='EP02-S01'
        self.assertIn('REVEAL_SCENE_ID',self.codes())
    def test_cashout_deadline(self):
        self.data['final_cashout']['episode_number']=3
        self.assertIn('CASHOUT_DEADLINE',self.codes())
    def test_resolved_cannot_keep_old_question_open(self):
        self.data['status']='resolved'
        self.data['final_cashout']['old_question_closed']=False
        self.assertIn('UNRESOLVED_REVEAL',self.codes())
    def test_cashout_needs_actual_payoff(self):
        self.data['status']='resolved'
        self.data['beats'][-1]['earned_payoffs']=[]
        self.assertIn('EMPTY_CASHOUT',self.codes())
    def test_valid_resolved_structural_fixture(self):
        self.data['status']='resolved'
        self.assertEqual(tools.check_reveal(self.data),[])
    def test_cli(self):
        output=io.StringIO()
        with redirect_stdout(output):
            code=tools.main(['check-reveal',str(tools.ROOT/'examples/reveal-arc.json')])
        self.assertEqual(code,0)
        self.assertEqual(json.loads(output.getvalue())['status'],'pass')

if __name__=='__main__':unittest.main()
