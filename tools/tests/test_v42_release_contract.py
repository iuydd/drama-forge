"""Release interface coherence and current-template fail-closed behavior."""
from pathlib import Path
import json
import re
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/production-ops/scripts'))
import brain_handoff as b
import prompt_contract as p
import brain_exchange as e

class ReleaseContract42Tests(unittest.TestCase):
    def test_entry_source_brain_use_runtime_policy(self):
        for name in ('assets/brain-intro.md','assets/brain-skill.md'):
            with self.subTest(name=name):
                version=re.search(r'version:\s*"([0-9.]+)"',(ROOT/name).read_text())[1]
                self.assertEqual(version,b.POLICY)
        source=(ROOT/'assets/source.md').read_text()
        current=json.loads((ROOT/'config/role-reading-map.json').read_text())
        self.assertIn('version: "'+current['content_version']+'"',source)
        self.assertEqual(current['workflow_mode'],'upfront_self')
    def test_active_packet_gate_sequence_template_policy_matches(self):
        for name in ('brain-packet.json','production-gate-spec.json','continuity-plan.json'):
            self.assertEqual(json.loads((ROOT/'tools/production-ops/templates'/name).read_text())['policy_version'],b.POLICY)
    def test_current_return_template_cannot_be_treated_as_real(self):
        value=json.loads((ROOT/'tools/production-ops/templates/brain-return.json').read_text())
        with tempfile.TemporaryDirectory() as d:self.assertTrue(e.validate_return(value,Path(d)))
    def test_current_ir_backend_placeholders_cannot_compile(self):
        t=ROOT/'tools/production-ops/templates'
        with self.assertRaises(ValueError):p.compile_ir(json.loads((t/'prompt-ir.json').read_text()),json.loads((t/'prompt-backend.json').read_text()))
    def test_live_evaluation_never_has_fictional_authorization_or_results(self):
        plan=json.loads((ROOT/'tools/production-ops/templates/live-eval-plan.json').read_text())
        self.assertEqual(plan['status'],'NOT_RUN');self.assertFalse(plan['authorized_generation'])
        self.assertTrue(all(c['result']=='NOT_RUN' and not c['real_media'] for c in plan['cases']))
    def test_standalone_does_not_rely_on_missing_local_files(self):
        text=(ROOT/'assets/brain-skill.md').read_text()
        self.assertIsNone(re.search(r'\]\((?!https?://|#)[^)]+\)',text))

if __name__=='__main__':unittest.main()
