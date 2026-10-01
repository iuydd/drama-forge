"""Current chapter synchronization, with historical exports kept separate."""
from pathlib import Path
import importlib.util
import json
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'scripts'))
spec = importlib.util.spec_from_file_location('current_sync', ROOT/'scripts/sync_skill.py')
sync = importlib.util.module_from_spec(spec); spec.loader.exec_module(sync)


class CurrentSourceTests(unittest.TestCase):
    def copied(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        for name in ('references', 'assets', 'config', 'prompts', 'schemas'):
            shutil.copytree(ROOT/name, root/name)
        for name in ('SKILL.md', 'README.md'):
            shutil.copy2(ROOT/name, root/name)
        (root/'tools/production-ops/templates').mkdir(parents=True)
        return root

    def test_sync_derives_versions_from_entrypoint(self):
        root = self.copied()
        entry = root/'SKILL.md'
        entry.write_text('---\nname: ai-drama-production\nmetadata:\n'
                         '  version: "9.2.1"\n  package_version: "9.2.1"\n'
                         '  content_version: "9.2.0"\n---\n\nEntry body.\n')
        readme = root/'README.md'
        readme.write_text('# Skill\n\n当前版本 **1.0.0**。Keep this explanation.\n')
        config_before = json.loads((root/'config/role-reading-map.json').read_text())
        self.assertIn('README.md', sync.synchronize(root))
        sync.synchronize(root, write=True)
        config = json.loads((root/'config/role-reading-map.json').read_text())
        self.assertEqual(config['package_version'], '9.2.1')
        self.assertEqual(config['content_version'], '9.2.0')
        self.assertEqual(config['workflow_mode'], config_before['workflow_mode'])
        self.assertTrue((root/'assets/source.md').read_text().startswith('---\nversion: "9.2.0"\n'))
        self.assertEqual(readme.read_text(), '# Skill\n\n当前版本 **9.2.1**。Keep this explanation.\n')
        self.assertEqual(sync.synchronize(root), [])

    def test_invalid_entry_versions_block_before_writing(self):
        cases = [
            '  version: "9.2.1"\n  package_version: "9.2.1"\n',
            '  version: "9.2.1"\n  package_version: "9.2.0"\n  content_version: "9.2.0"\n',
            '  version: "9.2.1"\n  package_version: "9.2.1"\n  content_version: "9.2.0"\n  content_version: "9.1.0"\n',
        ]
        for metadata in cases:
            with self.subTest(metadata=metadata):
                root = self.copied()
                (root/'SKILL.md').write_text('---\nmetadata:\n'+metadata+'---\n')
                before = {name: (root/name).read_bytes() for name in (
                    'assets/source.md', 'README.md', 'config/role-reading-map.json')}
                with self.assertRaises(ValueError):
                    sync.synchronize(root, write=True)
                self.assertEqual(before, {name: (root/name).read_bytes() for name in before})

    def test_missing_readme_version_blocks_before_writing(self):
        root = self.copied()
        (root/'README.md').write_text('# Skill\nVersion marker is missing.\n')
        source_before = (root/'assets/source.md').read_bytes()
        with self.assertRaises(ValueError):
            sync.synchronize(root, write=True)
        self.assertEqual((root/'assets/source.md').read_bytes(), source_before)

    def test_current_derived_files_are_synchronized(self):
        self.assertEqual(sync.synchronize(ROOT), [])

    def test_current_source_contains_every_complete_current_chapter(self):
        source = sync.expected_files(ROOT)['assets/source.md'].decode()
        sections = sync.parse_sections(source)
        self.assertEqual(set(sections), {anchor for anchor, _, _ in sync.MODULES})
        for anchor, name, _ in sync.MODULES:
            with self.subTest(name=name):
                self.assertEqual(sections[anchor]['text'], (ROOT/'references'/name).read_text())

    def test_sync_propagates_edit_without_reverting_chapter_or_history(self):
        root = self.copied()
        chapter = root/'references/01-story.md'
        chapter.write_text(chapter.read_text()+'\nCurrent rule edit for regression.\n')
        current = chapter.read_bytes()
        historical = (root/'assets/legacy-integrated-3.1.2-public.md').read_bytes()
        outputs = sync.expected_files(root)
        self.assertIn(current, outputs['assets/source.md'])
        self.assertNotIn('references/01-story.md', outputs)
        self.assertIn('assets/source.md', sync.synchronize(root, write=True))
        self.assertEqual(chapter.read_bytes(), current)
        self.assertEqual((root/'assets/legacy-integrated-3.1.2-public.md').read_bytes(), historical)
        self.assertEqual(sync.synchronize(root), [])

    def test_malformed_chapter_blocks_before_any_write(self):
        root = self.copied()
        before = (root/'assets/source.md').read_bytes()
        chapter = root/'references/01-story.md'
        chapter.write_text(chapter.read_text()+'\n<a id="r00"></a>\nextra\n')
        with self.assertRaisesRegex(ValueError, 'sole anchor'):
            sync.synchronize(root, write=True)
        self.assertEqual((root/'assets/source.md').read_bytes(), before)

    def test_sync_refreshes_reading_identity_for_current_changes(self):
        root = self.copied()
        path = root/'references/06-storyboard-prompts.md'
        path.write_text(path.read_text()+'\nCurrent reference prompt update.\n')
        sync.synchronize(root, write=True)
        import role_reading
        self.assertEqual(role_reading.check(root)['status'], 'READING_MAP_OK')
        pack = role_reading.build(root, 'prompt_video')
        self.assertIn('Current reference prompt update.', pack['instruction'])

    def test_independent_blind_route_cannot_mix_creative_rules(self):
        root = self.copied()
        path = root/'config/stage-reading-map.v3.json'
        routes = json.loads(path.read_text()); routes['stages']['blind'].append('r01')
        path.write_text(json.dumps(routes))
        with self.assertRaisesRegex(ValueError, 'only its independent brief'):
            sync.expected_files(root)

    def test_runtime_reading_template_matches_config(self):
        self.assertEqual((ROOT/'config/stage-reading-map.v3.json').read_bytes(),
                         (ROOT/'tools/production-ops/templates/stage-reading-map.json').read_bytes())

    def test_project_template_has_no_prefilled_genre(self):
        request = json.loads((ROOT/'templates/project-request.json').read_text())
        self.assertIsNone(request['user_brief']); self.assertEqual(request['episode_ids'], [])


if __name__ == '__main__': unittest.main()
