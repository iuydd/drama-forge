#!/usr/bin/env python3
"""Offline submission/recovery regression tests; requests required, no network or media tools."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import requests
from h3_client import Client, Stop, SubmissionUnknown, main


class ClientTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.client = Client(api="https://invalid.example", token="test-only", root=self.root, poll=0.001)
        self.client.s = Mock()
        self.client.s.post.return_value.json.return_value = {"id": "job-1"}
        self.client.wait_idle = Mock()
        self.out = self.root / "test.png"
        self.env = patch.dict(os.environ, {}, clear=False)
        self.env.start()
        self.addCleanup(self.env.stop)
        os.environ.pop("DEADLINE", None)

    def submit(self, **kwargs):
        values = {"profile": "chosen-image", "res": "1K", "name": "shot-1"}
        values.update(kwargs)
        return self.client.submit_image("prompt", self.out, **values)

    def test_timeout_blocks_restart_and_renamed_task(self):
        self.client.s.post.side_effect = requests.Timeout("response lost")
        with self.assertRaises(SubmissionUnknown):
            self.submit()
        restarted = Client(api="https://invalid.example", token="test-only", root=self.root)
        restarted.s = Mock()
        with self.assertRaises(SubmissionUnknown):
            restarted.submit_image("changed", self.out, profile="chosen", res="1K", name="renamed")
        restarted.s.post.assert_not_called()
        self.assertEqual(self.client.s.post.call_count, 1)
        self.assertEqual(len(restarted.unresolved()), 1)

    def test_intent_is_durable_before_post(self):
        def accepted(*args, **kwargs):
            self.assertEqual(len(self.client.unresolved()), 1)
            raise KeyboardInterrupt()
        self.client.s.post.side_effect = accepted
        with self.assertRaises(KeyboardInterrupt):
            self.submit()
        self.assertEqual(len(self.client.unresolved()), 1)
        with self.assertRaises(SubmissionUnknown):
            self.submit()
        self.assertEqual(self.client.s.post.call_count, 1)

    def test_job_id_is_recovered_without_repost(self):
        self.client.s.post.side_effect = requests.Timeout()
        with self.assertRaises(SubmissionUnknown):
            self.submit()
        request_id = self.client.unresolved()[0]["request_id"]
        self.client.reconcile(request_id, job="accepted-job", not_submitted=False, evidence="provider history matches request")
        self.assertEqual(self.submit(), "accepted-job")
        self.assertEqual(self.client.s.post.call_count, 1)
        self.assertEqual(self.client.unresolved(), [])

    def test_proven_not_submitted_allows_new_attempt(self):
        self.client.s.post.side_effect = requests.Timeout()
        with self.assertRaises(SubmissionUnknown):
            self.submit()
        request_id = self.client.unresolved()[0]["request_id"]
        self.client.reconcile(request_id, job=None, not_submitted=True, evidence="provider support verified absence")
        self.client.s.post.side_effect = None
        self.assertEqual(self.submit(), "job-1")
        self.assertEqual(self.client.s.post.call_count, 2)

    def test_reconcile_requires_evidence(self):
        with self.assertRaises(ValueError):
            self.client.reconcile("unknown", job=None, not_submitted=True, evidence=" ")

    def test_stop_after_idle_prevents_post(self):
        self.client.wait_idle.side_effect = lambda: (self.root / "STOP").touch()
        with self.assertRaises(Stop):
            self.submit()
        self.client.s.post.assert_not_called()
        self.assertEqual(self.client.ledger(), [])

    def test_deadline_after_idle_prevents_post(self):
        self.client.wait_idle.side_effect = lambda: os.environ.__setitem__("DEADLINE", "200001010000")
        with self.assertRaises(Stop):
            self.submit()
        self.client.s.post.assert_not_called()

    def test_busy_wait_observes_stop(self):
        self.client.status = Mock(side_effect=lambda **kw: ((self.root / "STOP").touch() or {"running": 1}))
        with self.assertRaises(Stop):
            Client.wait_idle(self.client)
        self.client.status.assert_called_once()

    def test_status_network_retry_observes_stop(self):
        def failed(*args, **kwargs):
            (self.root / "STOP").touch()
            raise requests.ConnectionError()
        self.client.s.get.side_effect = failed
        with patch("h3_client.time.sleep"), self.assertRaises(Stop):
            self.client.rget("/api/status", before_submit=True, tries=2)
        self.assertEqual(self.client.s.get.call_count, 1)

    def test_pending_task_is_not_resubmitted(self):
        self.assertEqual(self.submit(), "job-1")
        self.assertEqual(self.submit(), "job-1")
        self.assertEqual(self.client.s.post.call_count, 1)
        with self.assertRaises(SubmissionUnknown):
            self.submit(profile="changed")

    def test_empty_job_id_blocks_retry(self):
        self.client.s.post.return_value.json.return_value = {"id": ""}
        with self.assertRaises(SubmissionUnknown):
            self.submit()
        with self.assertRaises(SubmissionUnknown):
            self.submit()
        self.assertEqual(self.client.s.post.call_count, 1)

    def test_ledger_write_failure_prevents_post(self):
        with patch.object(self.client, "_append", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                self.submit()
        self.client.s.post.assert_not_called()

    def test_corrupt_ledger_blocks_post(self):
        self.client.log_dir.mkdir()
        (self.client.log_dir / "jobs.jsonl").write_text('{"unfinished":')
        with self.assertRaises(SubmissionUnknown):
            self.submit()
        self.client.s.post.assert_not_called()

    def test_download_failure_does_not_turn_into_generation_failure(self):
        self.submit()
        self.client.rget = Mock(return_value=Mock(content=b"not media"))
        with self.assertRaises(RuntimeError):
            self.client.download({"id": "job-1"}, "image", self.out)
        self.assertEqual(self.submit(), "job-1")
        self.assertEqual(self.client.s.post.call_count, 1)

    def test_collect_can_finish_after_stop(self):
        (self.root / "STOP").touch()
        self.client.wait_job = Mock(return_value={"id": "job-1"})
        self.client.rget = Mock(return_value=Mock(content=b"\x89PNGfixture"))
        self.assertEqual(self.client.collect("job-1", "image", self.out), self.out)
        self.assertEqual(self.out.read_bytes(), b"\x89PNGfixture")

    def test_missing_profile_and_resolution_never_post(self):
        for overrides in ({"profile": None}, {"res": None}):
            with self.assertRaises(ValueError):
                self.submit(**overrides)
        self.client.s.post.assert_not_called()

    def test_cli_requires_explicit_profile(self):
        import contextlib
        import io
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
            main(["image", "--prompt-file", "unused", "--out", "unused"])
        self.assertEqual(caught.exception.code, 2)

    def test_new_project_has_no_implicit_production_profiles(self):
        from common import Project
        from project_tool import init
        project = init(self.root / "project", "test", 1, "zh", "test", 30, None, "16:9")
        current = Project(project)
        self.assertTrue(all(value is None for value in current.sub("profiles").values()))
        self.assertTrue(all(ref.get("profile") is None and ref.get("res") is None
                            for ref in current.load_refs().values()))
        current.cfg["profiles"] = {"video": "user-video", "video_res": "user-size"}
        self.assertEqual(current.sub("profiles")["video"], "user-video")
        self.assertIsNone(current.sub("profiles")["frame"])

    def test_payload_uses_explicit_values(self):
        self.submit(profile="custom-profile", res="custom-size")
        payload = self.client.s.post.call_args.kwargs["json"]
        self.assertEqual((payload["profile"], payload["res"]), ("custom-profile", "custom-size"))
        self.assertFalse(self.client.unresolved())


def run_tests():
    result = unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.loadTestsFromTestCase(ClientTests))
    if not result.wasSuccessful():
        raise SystemExit(1)


if __name__ == "__main__":
    run_tests()
