"""离线检查：一个检查失败时仍运行后续检查，原始诊断和退出码不丢失。"""
import subprocess
import unittest
from unittest.mock import patch

import stage_checks


class StageChecksTests(unittest.TestCase):
    def test_failure_does_not_short_circuit_or_hide_output(self):
        replies = [subprocess.CompletedProcess([], 1, "G46 error\n", "detail\n"),
                   subprocess.CompletedProcess([], 0, "V01 warn\n", "")]
        with patch.object(stage_checks.subprocess, "run", side_effect=replies) as run:
            results = stage_checks.run_checks("project", "EP001", "E")
        self.assertEqual(run.call_count, 2)
        self.assertEqual([r["exit"] for r in results], [1, 0])
        self.assertEqual(results[0]["stdout"], "G46 error\n")
        self.assertEqual(results[0]["stderr"], "detail\n")
        self.assertEqual(results[1]["stdout"], "V01 warn\n")

    def test_launch_failure_is_reported_and_remaining_checks_run(self):
        with patch.object(stage_checks.subprocess, "run", side_effect=[
            OSError("cannot start"), subprocess.CompletedProcess([], 0, "done\n", "")
        ]) as run:
            results = stage_checks.run_checks("project", "EP001", "D")
        self.assertEqual(run.call_count, 2)
        self.assertNotEqual(results[0]["exit"], 0)
        self.assertIn("cannot start", results[0]["stderr"])
        self.assertEqual(results[1]["exit"], 0)


if __name__ == "__main__":
    unittest.main()
