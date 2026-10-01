"""Single-pass validation must preserve draft and production error semantics."""
from pathlib import Path
import unittest
from unittest.mock import patch
import continuity_tools as c

ROOT = Path(__file__).resolve().parents[1]


class CompileValidationTests(unittest.TestCase):
    def setUp(self):
        self.scene = c.load_json(ROOT / 'examples/scene.json')
        self.shot = c.load_json(ROOT / 'examples/shot.json')
        self.profile = c.load_json(ROOT / 'templates/runtime-profile.json')

    def test_compile_checks_scene_once(self):
        with patch.object(c, 'validate_scene', wraps=c.validate_scene) as checked:
            result = c.compile_package(self.scene, self.shot, self.profile)
        self.assertEqual(checked.call_count, 1)
        self.assertEqual(result['status'], 'DRAFT')
        self.assertFalse(result['executed'])
        self.assertTrue(result['prompt'])
        self.assertTrue(result['blockers'])

    def test_early_production_error_does_not_hide_structural_error(self):
        self.shot['style_lock'] = {'style_id': 'S', 'version': '1',
                                  'prompt_sentence': 'natural light', 'status': 'candidate'}
        self.shot['output']['width'] = 0
        errors = c.validate(self.scene, self.shot, self.profile, production=True)
        self.assertLess(errors.index('production: style not locked'),
                        errors.index('shot.output.width: positive integer required'))
        self.assertNotIn('production: style not locked',
                         c.validate(self.scene, self.shot, self.profile))
        self.assertEqual(c.compile_package(self.scene, self.shot, self.profile)['prompt'], '')

    def test_insert_error_still_affects_draft_when_style_unlocked(self):
        self.shot['style_lock'] = {'style_id': 'S', 'version': '1',
                                  'prompt_sentence': 'natural light', 'status': 'candidate'}
        self.shot['insert_policy'] = {'kind': 'object_only', 'visible_entity_ids': ['KEY'],
                                     'offscreen_aliases': [], 'post_audio_separate': True}
        self.shot['references'] = [r for r in self.shot['references'] if r['primary']]
        with patch.object(c, 'render_prompt', side_effect=ValueError('synthetic insert error')):
            result = c.compile_package(self.scene, self.shot, self.profile)
        self.assertEqual(result['prompt'], '')
        self.assertIn('insert prompt validation: synthetic insert error', result['blockers'])
        self.assertIn('production: style not locked', result['blockers'])


if __name__ == '__main__':
    unittest.main()
