#!/usr/bin/env python3
"""Offline regressions for semantic screening, take review, cut admission and scene state."""
from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from common import Project, SHOTS_SCHEMA
from project_tool import init
from review_quality import speech_diff, cut_issues, protect_interval, verified_action
from review_tool import auto, mark, choose_best, ASR
from shots_tool import scene_state_issues


class QualityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = init(Path(self.tmp.name)/"project", "test", 1, "zh", "test", 5, None, "16:9")
        self.project = Project(root)
        self.shot = {"id":"EP001-S01", "scene":"EP001-SC001", "motion":"hands over document",
                     "action_required":True, "seconds":5, "dialogue":[{"speaker":"甲", "text":"我没有拿走合同"}]}
        self.data = {"schema":SHOTS_SCHEMA, "shots":[self.shot]}
        self.write_shots()
        self.path = self.project.video_path("EP001", "EP001-S01", 1)
        self.path.write_bytes(b"fixture-take-one")

    def write_shots(self):
        self.project.shots_path("EP001").write_text(json.dumps(self.data))

    def approve(self, take=1, **kw):
        args = dict(video_take=take, visual="pass", audio="pass", continuity="pass", verdict="ok",
                    action_window=[1, 3], speech_window=[0.5, 2], evidence="offline fixture: action and speech verified")
        args.update(kw)
        return mark(self.project, "EP001", "EP001-S01", **args)

    def issues(self):
        return cut_issues(self.project, "EP001", self.project.load_shots("EP001"), self.project.load_review("EP001"))

    def test_negation_and_numbers_require_listening(self):
        diff = speech_diff("我没有拿走合同", "我有拿走合同")
        self.assertEqual(diff["status"], "needs_listening")
        self.assertIn("没", diff["critical_changes"])
        self.assertEqual(speech_diff("转账100元", "转账1000元")["status"], "needs_listening")

    def test_added_words_are_not_perfect_match(self):
        diff = speech_diff("把合同给我", "把合同给我我已经杀了他")
        self.assertLess(diff["precision"], 1)
        self.assertLess(diff["similarity"], 1)
        self.assertEqual(diff["edits"][0]["operation"], "insert")

    def test_allowed_readings_and_punctuation(self):
        self.assertEqual(speech_diff("拓海、来て。", "たくみ来て", {"拓海":"たくみ"})["status"], "exact")
        self.assertEqual(speech_diff("I did not go", "I did go")["status"], "needs_listening")

    def test_no_asr_or_visual_is_pending(self):
        self.assertEqual(auto(self.project, "EP001")["shots"]["EP001-S01"]["verdict"], "pending_review")
        self.assertTrue(self.issues())

    def test_bare_ok_cannot_approve(self):
        with self.assertRaises(ValueError):
            mark(self.project, "EP001", "EP001-S01", video_take=1, verdict="ok")

    def test_evidence_is_required(self):
        with self.assertRaises(ValueError):
            self.approve(evidence="")

    def test_complete_review_allows_final(self):
        self.approve()
        self.assertFalse(self.issues())
        self.assertEqual(auto(self.project, "EP001")["shots"]["EP001-S01"]["verdict"], "ok")

    def test_replaced_bytes_invalidate_review(self):
        self.approve()
        self.path.write_bytes(b"new bytes")
        self.assertTrue(self.issues())
        self.assertEqual(auto(self.project, "EP001")["shots"]["EP001-S01"]["verdict"], "pending_review")

    def test_changed_script_invalidates_review(self):
        self.approve()
        self.shot["dialogue"][0]["text"] = "换一句话"
        self.write_shots()
        self.assertTrue(self.issues())

    def test_switching_take_does_not_inherit_trim_or_review(self):
        self.approve(**{"in":1}, out=3)
        self.project.video_path("EP001", "EP001-S01", 2).write_bytes(b"second")
        mark(self.project, "EP001", "EP001-S01", video_take=2)
        entry = self.project.load_review("EP001")["shots"]["EP001-S01"]
        self.assertEqual(entry["verdict"], "pending_review")
        self.assertFalse(entry["video_takes"]["2"]["edit"])
        self.assertFalse(verified_action(entry["video_takes"]["2"]))
        self.assertTrue(self.issues())

    def test_reviewed_take_preferred_over_higher_asr(self):
        self.approve()
        self.project.video_path("EP001", "EP001-S01", 2).write_bytes(b"second")
        review = self.project.load_review("EP001")
        review["shots"]["EP001-S01"]["locked"] = False
        review["shots"]["EP001-S01"]["video_takes"]["2"] = {"hit":1, "speech_diff":{"similarity":1}}
        self.project.save_review("EP001", review)
        self.assertEqual(choose_best(self.project, "EP001", "EP001-S01"), 1)

    def test_action_plan_and_motion_candidate_are_not_verified(self):
        rec = {"action_start":1, "action_end":3, "motion":[0,9,0]}
        self.assertIsNone(verified_action(rec))
        self.shot["action_window"] = [0,1]
        self.write_shots()
        self.assertTrue(self.issues())

    def test_verified_windows_protect_both_cut_ends(self):
        self.assertEqual(protect_interval(2, 4, 5, (1,3,"reviewed_take")), (1,4))
        self.assertEqual(protect_interval(2, 2.2, 5, (1,3,"reviewed_take"), [0.5,4.9]), (0.5,5))
        with self.assertRaises(ValueError):
            protect_interval(0,3,5,(1,6,"reviewed_take"))

    def test_action_and_speech_windows_required(self):
        with self.assertRaises(ValueError):
            self.approve(action_window=None)
        with self.assertRaises(ValueError):
            self.approve(speech_window=None)

    def test_speed_change_requires_listening_again(self):
        self.approve()
        mark(self.project, "EP001", "EP001-S01", speed=1.2)
        self.assertTrue(self.issues())
        mark(self.project, "EP001", "EP001-S01", audio="pass", evidence="listened to adjusted speed", verdict="ok")
        self.assertFalse(self.issues())

    def test_retakes_cannot_enter_final(self):
        self.approve()
        mark(self.project, "EP001", "EP001-S01", verdict="retake")
        self.assertTrue(self.issues())

    def test_weak_needs_reason_and_cannot_waive_core_failure(self):
        with self.assertRaises(ValueError):
            self.approve(verdict="weak")
        self.approve(verdict="weak", acceptance_reason="cosmetic background softness accepted")
        self.assertFalse(self.issues())
        with self.assertRaises(ValueError):
            self.approve(verdict="weak", visual="fail", acceptance_reason="try to bypass")

    def test_muting_required_dialogue_is_blocked(self):
        self.approve(verdict="mute")
        self.assertTrue(self.issues())

    def test_audio_source_must_be_reviewed(self):
        source = {"id":"EP001-S02", "dialogue":[{"text":"replacement"}]}
        self.shot["audio_from"] = [{"shot":"EP001-S02"}]
        self.data["shots"].append(source)
        self.data["cut_order"] = ["EP001-S01"]
        self.write_shots()
        self.approve()
        self.assertTrue(any("audio source" in issue for issue in self.issues()))

    def test_omitted_shot_requires_reason(self):
        self.approve()
        self.data["shots"].append({"id":"EP001-S02"})
        self.data["cut_order"] = ["EP001-S01"]
        self.write_shots()
        self.assertTrue(any("omitted" in issue for issue in self.issues()))

    def test_scene_state_survives_reverse_shot(self):
        shots=[{"id":"A1","scene":"SC1","scene_state":{"end":{"PROP":{"holder":"A"}}}},
               {"id":"B1","scene":"SC1"},
               {"id":"A2","scene":"SC1","scene_state":{"start":{"PROP":{"holder":"B"}}}}]
        self.assertEqual(scene_state_issues(shots)[0]["shot"], "A2")
        shots[1]["scene_state"]={"end":{"PROP":{"holder":"B"}}}
        self.assertFalse(scene_state_issues(shots))

    def test_failed_asr_process_does_not_report_silence(self):
        with patch("review_tool.asr_python", return_value="fake-python"):
            reader=ASR(self.project)
        with patch("review_tool.subprocess.run", return_value=Mock(returncode=1,stdout="")):
            with self.assertRaises(RuntimeError):
                reader.words([self.path])

    def test_missing_asr_row_does_not_report_silence(self):
        with patch("review_tool.asr_python", return_value="fake-python"):
            reader=ASR(self.project)
        with patch("review_tool.subprocess.run", return_value=Mock(returncode=0,stdout="")):
            with self.assertRaises(RuntimeError):
                reader.words([self.path])

    def test_final_preflight_runs_before_media_commands(self):
        from cut import cut
        with patch("cut.subprocess.run") as command:
            with self.assertRaises(ValueError):
                cut(self.project,"EP001",dry=True)
            command.assert_not_called()

    def test_draft_sheet_is_separate(self):
        from cut import cut
        with patch("cut.ffprobe_duration",return_value=5), patch("review_tool.asr_python",return_value=None), contextlib.redirect_stdout(io.StringIO()):
            cut(self.project,"EP001",dry=True,draft=True)
        self.assertTrue((self.project.ep_dir("EP001")/"草剪单.md").exists())
        self.assertFalse((self.project.ep_dir("EP001")/"剪辑单.md").exists())
        with self.assertRaises(ValueError):
            cut(self.project,"EP001",out=self.project.final_path("EP001"),dry=True,draft=True)

    def test_auto_preserves_intentional_drop(self):
        mark(self.project, "EP001", "EP001-S01", verdict="drop", note="scene revised explicitly")
        self.assertEqual(auto(self.project,"EP001")["shots"]["EP001-S01"]["verdict"],"drop")

    def test_acceptance_reason_added_to_current_review_is_saved(self):
        self.approve()
        mark(self.project,"EP001","EP001-S01",verdict="weak",acceptance_reason="minor background texture")
        self.assertFalse(self.issues())

    def test_static_prompt_is_not_an_environment_error(self):
        from shots_tool import check
        self.shot["video_prompt"] = "A motionless wall is out of focus."
        self.write_shots()
        self.assertFalse(any(x["code"] == "G35" for x in check(self.project,"EP001").warns()))
        self.shot["environment_motion_required"] = True
        self.write_shots()
        self.assertTrue(any(x["code"] == "G35" for x in check(self.project,"EP001").warns()))
        self.shot["environment_motion"] = "Curtain moves in the open window breeze."
        self.write_shots()
        self.assertFalse(any(x["code"] == "G35" for x in check(self.project,"EP001").warns()))

    def test_general_profile_allows_deliberate_late_speech(self):
        from shots_tool import check
        self.shot["dialogue"][0]["at"] = 2
        self.write_shots()
        self.assertFalse(any(x["code"] == "G05" for x in check(self.project,"EP001").warns()))
        self.project.cfg["craft_profile"] = "commercial_fast"
        self.assertTrue(any(x["code"] == "G05" for x in check(self.project,"EP001").warns()))


def run_tests():
    result=unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.loadTestsFromTestCase(QualityTests))
    if not result.wasSuccessful():
        raise SystemExit(1)


if __name__ == "__main__":
    run_tests()
