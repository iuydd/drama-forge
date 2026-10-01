"""Synthetic file-integrity regression tests; no media approval."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import production_gates as g


class DigestSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.path = self.root / 'evidence.bin'
        self.path.write_bytes(b'synthetic-evidence')
        self.record = {'path': self.path.name, 'sha256': g.file_sha(self.path)}

    def test_reuses_digest_but_checks_every_expected_hash(self):
        cache = g._DigestSnapshot()
        with patch.object(g, 'file_sha', wraps=g.file_sha) as hashed:
            for _ in range(10):
                self.assertEqual(g._verify_record(self.record, self.root, cache), [])
            wrong = dict(self.record, sha256='0' * 64)
            self.assertEqual(g._verify_record(wrong, self.root, cache),
                             ['file hash mismatch: evidence.bin'])
            self.assertEqual(hashed.call_count, 1)

    def test_changed_file_invalidates_same_snapshot(self):
        cache = g._DigestSnapshot()
        cache(self.path)
        self.path.write_bytes(b'changed-evidence')
        with self.assertRaisesRegex(ValueError, 'file changed during gate'):
            cache(self.path)

    def test_final_check_catches_change_after_last_use(self):
        cache = g._DigestSnapshot()
        cache(self.path)
        self.path.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'file changed during gate'):
            cache.check_unchanged()

    def test_change_during_hash_is_rejected(self):
        original = g.file_sha
        def changed(path):
            digest = original(path)
            path.write_bytes(b'changed-during-read')
            return digest
        with patch.object(g, 'file_sha', side_effect=changed):
            with self.assertRaisesRegex(ValueError, 'file changed during gate'):
                g._DigestSnapshot()(self.path)

    def test_new_snapshot_reads_new_bytes(self):
        first = g._DigestSnapshot()(self.path)
        self.path.write_bytes(b'new-evidence')
        self.assertNotEqual(first, g._DigestSnapshot()(self.path))

    def test_cached_digest_does_not_bypass_path_checks(self):
        cache = g._DigestSnapshot()
        cache(self.path)
        bad = dict(self.record, path='../evidence.bin')
        self.assertEqual(g._verify_record(bad, self.root, cache), ['unsafe file path'])
        link = self.root / 'link.bin'
        link.symlink_to(self.path)
        self.assertEqual(g._verify_record(dict(self.record, path=link.name), self.root, cache),
                         ['file path escapes project'])


if __name__ == '__main__':
    unittest.main()

