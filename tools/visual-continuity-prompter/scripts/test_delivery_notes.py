"""v2.9 regression: direction transport only, no speech/video synthesis."""
from copy import deepcopy
import json
from pathlib import Path
import unittest
import continuity_tools as c
import prompt_nine as n
ROOT = Path(__file__).resolve().parents[1]


def native():
    return {'line_id': 'L1', 'speaker_description': '画内前景青年',
            'voice_description': '同一青年自然声线', 'text_spoken': '嗯。你拿回去。'}


def fixture():
    shot = json.loads((ROOT / 'examples/video-shot-nine.json').read_text())
    shot['audio_plan']['native_spoken_lines'] = [native()]
    shot['audio_plan']['native_spoken_lines'][0]['delivery_note'] = '简短肯定，句尾放松，等对方说完再回答。'
    shot['prompt9']['source_contract_sha256'] = n.source_digest(shot)
    return shot


class DeliveryNoteTests(unittest.TestCase):
    def test_exact_text_stays_independent(self):
        line = native(); line['delivery_note'] = '轻声确认。'
        out = n.render_native_line(line)
        self.assertEqual(json.loads(out.rsplit('；只说：', 1)[1]), line['text_spoken'])
        self.assertIn('单句语气指导（不朗读）：轻声确认。', out)

    def test_old_line_output_unchanged(self):
        l = native()
        self.assertEqual(n.render_native_line(l), '原生开口对白：' + l['speaker_description'] + '；声线：' + l['voice_description'] + '；只说：' + json.dumps(l['text_spoken'], ensure_ascii=False))

    def test_null_means_inherit(self):
        l = native(); out = n.render_native_line(l); l['delivery_note'] = None
        self.assertEqual(out, n.render_native_line(l))

    def test_empty_note_is_not_silently_ready(self):
        s = fixture(); s['audio_plan']['native_spoken_lines'][0]['delivery_note'] = ''
        self.assertTrue(n.validate_delivery_notes(s))

    def test_whitespace_note_rejected(self):
        l = native(); l['delivery_note'] = '  \n'
        with self.assertRaises(ValueError): n.render_native_line(l)

    def test_nontext_notes_rejected(self):
        for value in (True, 0, ['happy'], {'emotion': 'happy'}):
            with self.subTest(value=value):
                s = fixture(); s['audio_plan']['native_spoken_lines'][0]['delivery_note'] = value
                self.assertTrue(n.validate_delivery_notes(s))

    def test_nine_compiler_includes_note(self):
        s = fixture(); self.assertEqual(n.validate_nine(s), [])
        self.assertIn(s['audio_plan']['native_spoken_lines'][0]['delivery_note'], n.render_nine(s))

    def test_legacy_compiler_also_includes_note(self):
        s = fixture(); s.pop('prompt9')
        scene = json.loads((ROOT / 'examples/scene.json').read_text())
        self.assertIn(s['audio_plan']['native_spoken_lines'][0]['delivery_note'], c.render_prompt(scene, s))

    def test_post_note_not_in_nine_visual_prompt(self):
        s = fixture(); s['audio_plan']['native_spoken_lines'] = []
        s['audio_plan']['post_voices'] = [{'line_id': 'P1', 'source_kind': 'inner', 'speaker_description': '幕后角色', 'text_spoken': '一定要回去。', 'delivery_note': 'PRIVATE_POST_NOTE'}]
        s['prompt9']['source_contract_sha256'] = n.source_digest(s)
        out = n.render_nine(s)
        self.assertNotIn('PRIVATE_POST_NOTE', out)
        self.assertNotIn('一定要回去', out)

    def test_post_cues_preserved_in_compile_package(self):
        s = fixture(); s['audio_plan']['post_voices'] = [{'line_id': 'P1', 'source_kind': 'inner', 'speaker_description': '幕后角色', 'text_spoken': '一定要回去。', 'delivery_note': 'PRIVATE_POST_NOTE'}]
        s['prompt9']['source_contract_sha256'] = n.source_digest(s)
        scene = json.loads((ROOT / 'examples/scene.json').read_text())
        out = c.compile_package(scene, s, {})
        self.assertEqual(out['post_audio_cues'][0]['delivery_note'], 'PRIVATE_POST_NOTE')
        self.assertFalse(out['executed'])
        self.assertNotIn('PRIVATE_POST_NOTE', out['prompt'])

    def test_note_change_invalidates_nine_fingerprint(self):
        s = fixture(); s['audio_plan']['native_spoken_lines'][0]['delivery_note'] = '不要改变台词。'
        self.assertTrue(any('stale' in e for e in n.validate_nine(s)))

    def test_note_change_changes_job_fingerprint(self):
        s = fixture(); scene = json.loads((ROOT / 'examples/scene.json').read_text())
        before = c.digest_job(scene, s, {})
        s['audio_plan']['native_spoken_lines'][0]['delivery_note'] = '先确认，再回答。'
        self.assertNotEqual(before, c.digest_job(scene, s, {}))

    def test_no_mutation(self):
        s = fixture(); before = deepcopy(s); n.render_nine(s)
        self.assertEqual(before, s)

    def test_post_invalid_note_also_rejected(self):
        s = fixture(); s['audio_plan']['post_voices'] = [{'delivery_note': ['wrong type']}]
        self.assertTrue(n.validate_delivery_notes(s))

    def test_optional_note_does_not_require_audio_on_stills(self):
        self.assertEqual(n.validate_delivery_notes({'mode': 'edit_same_view'}), [])

    def test_parent_validator_handles_invalid_note(self):
        s = fixture(); s.pop('prompt9'); s['audio_plan']['native_spoken_lines'][0]['delivery_note'] = 7
        scene = json.loads((ROOT / 'examples/scene.json').read_text())
        self.assertTrue(any('delivery_note' in e for e in c.validate(scene, s, {})))

    def test_insert_guard_still_detects_private_alias(self):
        s = fixture(); s['audio_plan']['native_spoken_lines'] = []
        s['insert_policy'] = {'kind': 'visible_part', 'visible_entity_ids': ['CUP'], 'offscreen_aliases': ['PRIVATE_PERSON'], 'post_audio_separate': True}
        self.assertTrue(n.inspect_insert(s, 'PRIVATE_PERSON is present'))

    def test_generation_duration_still_requires_positive_number(self):
        s = fixture(); s.pop('prompt9'); s['video']['duration_s'] = None
        scene = json.loads((ROOT / 'examples/scene.json').read_text())
        self.assertTrue(any('duration_s' in e for e in c.validate(scene, s, {})))


if __name__ == '__main__': unittest.main()
