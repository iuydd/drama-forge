"""Planning defaults only; no claim to assess acting or story quality."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
import drama_tools as d
try:
    import jsonschema
except ImportError:
    jsonschema = None
ROOT = Path(__file__).resolve().parents[1]


class ContextFirstTests(unittest.TestCase):
    def setUp(self):
        self.brief = json.loads((ROOT / 'assets/templates/brief.json').read_text())
        self.schema = json.loads((ROOT / 'assets/schemas/brief.schema.json').read_text())

    def test_new_planning_duration_unset(self):
        self.assertIsNone(self.brief['episode_seconds'])
        self.assertEqual(self.brief['timing_policy']['mode'], 'context_first')

    def test_single_episode_template_preserved(self):
        self.assertEqual(self.brief['delivery']['full_episodes'], 1)

    def test_initialization_does_not_expand_three_episodes(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)/'show'; d.init_project(project, '测试', 24)
            b = json.loads((project/'brief.json').read_text())
            self.assertEqual(b['delivery']['full_episodes'], 1)
            self.assertIsNone(b['episode_seconds'])

    @unittest.skipIf(jsonschema is None, 'Optional jsonschema is not installed')
    def test_new_brief_schema_allows_planning_null(self):
        jsonschema.validate(self.brief, self.schema)

    @unittest.skipIf(jsonschema is None, 'Optional jsonschema is not installed')
    def test_old_numeric_brief_remains_compatible(self):
        b = deepcopy(self.brief); b.pop('timing_policy'); b['episode_seconds'] = 75
        jsonschema.validate(b, self.schema)

    @unittest.skipIf(jsonschema is None, 'Optional jsonschema is not installed')
    def test_zero_is_not_a_planning_duration(self):
        b = deepcopy(self.brief); b['episode_seconds'] = 0
        with self.assertRaises(jsonschema.ValidationError): jsonschema.validate(b, self.schema)

    def test_cards_are_draft_not_media(self):
        for p in ('performance-scene-card.json', 'story-context-ledger.json'):
            b = json.loads((ROOT/'assets/templates'/p).read_text())
            self.assertEqual(b['status'], 'DRAFT')
            self.assertIsNone(b['source_script']['sha256'])

    def test_demo_not_claimed_generated(self):
        b = json.loads((ROOT/'examples/performance-context-demo.json').read_text())
        self.assertTrue(b['fictional']); self.assertIsNone(b['actual_media'])
        self.assertEqual(b['status'], 'PLANNED_EXAMPLE_NOT_GENERATED')


if __name__ == '__main__': unittest.main()
