"""Historical prose is preserved without freezing active production rules."""
from pathlib import Path
import hashlib
import importlib.util
import json
import re
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/production-ops/scripts'))
import preproduction
spec = importlib.util.spec_from_file_location('legacy_builder', ROOT / 'scripts/build_brain_skill.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class TheoryRestorationTests(unittest.TestCase):
    def request(self):
        return {'project_id':'SYNTHETIC', 'request_id':'TEST', 'user_brief':'仅测试文本交接',
                'episode_ids':['EP001'], 'source_texts':[], 'existing_assets':[],
                'media_profiles':{}, 'quality_limits':{}}

    def test_original_integrated_source_is_exact_upload_baseline(self):
        data = (ROOT/'assets/legacy-integrated-3.1.2-public.md').read_bytes()
        self.assertEqual(hashlib.sha256(data).hexdigest(), 'c954bf7a6315e73885324b81c4b60d27a3bdf792f0ea511142346c7b8694ef8d')

    def test_all_ten_historical_chapters_and_blind_brief_are_unabridged(self):
        data = builder.original_theory(ROOT)
        self.assertEqual(data, (ROOT/'assets/legacy-theory-3.1.2-public.md').read_bytes())
        self.assertEqual(len(data), 40669)
        self.assertEqual(set(re.findall(rb'<a id="([^"]+)"></a>', data)), {x.encode() for x in builder.THEORY_KEYS})

    def test_legacy_export_is_self_contained_and_clearly_marked(self):
        brain = (ROOT/'assets/brain-skill.md').read_bytes()
        self.assertTrue(brain.startswith(builder.LEGACY_NOTICE))
        self.assertEqual(brain, builder.expected(ROOT))
        self.assertEqual(brain.count(builder.original_theory(ROOT)), 1)
        self.assertIsNone(re.search(rb'\]\((?!https?://|#)[^)]+\)', brain))

    def test_default_prepare_refuses_outdated_brain_transport(self):
        with self.assertRaisesRegex(ValueError, 'explicit legacy_brain_compatibility'):
            preproduction.prepare(self.request())
        for value in ('true', 1, False):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'explicit legacy'):
                preproduction.prepare({**self.request(), 'legacy_brain_compatibility':value})

    def test_explicit_legacy_request_preserves_transport_contract(self):
        request = {**self.request(), 'legacy_brain_compatibility':True}
        message = preproduction.prepare(request)
        self.assertTrue(message['instructions'].startswith(builder.LEGACY_NOTICE.decode()))
        self.assertIn(builder.original_theory(ROOT).decode(), message['instructions'])
        self.assertIn(json.dumps(request, ensure_ascii=False, indent=2), message['input'])
        self.assertEqual(message['tools'], [])
        self.assertFalse(message['production_started'])

    def test_builder_rejects_tampered_historical_baseline(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root/'assets').mkdir()
            shutil.copy2(ROOT/'THEORY_PROVENANCE.json', root/'THEORY_PROVENANCE.json')
            (root/'assets/legacy-integrated-3.1.2-public.md').write_bytes(
                (ROOT/'assets/legacy-integrated-3.1.2-public.md').read_bytes() + b'changed')
            with self.assertRaisesRegex(ValueError, 'original integrated source'):
                builder.original_theory(root)

    def test_current_chapter_changes_do_not_rewrite_legacy_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(ROOT/'assets', root/'assets')
            shutil.copy2(ROOT/'THEORY_PROVENANCE.json', root/'THEORY_PROVENANCE.json')
            (root/'references').mkdir()
            (root/'references/01-story.md').write_text('Current creative rules may evolve.')
            self.assertEqual(builder.expected(root), builder.expected(ROOT))


if __name__ == '__main__': unittest.main()
