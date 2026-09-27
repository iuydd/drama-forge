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
from review_quality import speech_diff, cut_issues, protect_interval, verified_action, media_digest, shot_digest, text_digest
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
        self.make_take(1, b"fixture-take-one")

    def write_shots(self):
        self.project.shots_path("EP001").write_text(json.dumps(self.data))

    def make_take(self, take, data, sid="EP001-S01", frame_sha=None):
        """合成素材 + 账本记录（等同 h3_client 下载后写的 submitted/collected），让来源校验能对上。"""
        path = self.project.video_path("EP001", sid, take)
        path.write_bytes(data)
        sh = next(x for x in self.data["shots"] if x["id"] == sid)
        self.project.scripts_dir.mkdir(parents=True, exist_ok=True)
        with open(self.project.scripts_dir / "jobs.jsonl", "a", encoding="utf-8") as f:
            sub = {"status": "submitted", "job": f"job-{sid}-{take}", "name": path.stem, "out": str(path.resolve()),
                   "source_prompt_sha256": text_digest(sh.get("video_prompt") or "")}
            if frame_sha:
                sub["frame_sha256"] = frame_sha
            f.write(json.dumps(sub) + "\n")
            f.write(json.dumps({"status": "collected", "job": f"job-{sid}-{take}", "out": str(path.resolve()), "sha256": media_digest(path)}) + "\n")
        return path

    def fake_asr(self, take=1, sid="EP001-S01", critical=()):
        """合成 ASR 记录（等同 review_tool.asr_shot 对当前文件、当前镜头跑过一次）。"""
        review = self.project.load_review("EP001")
        sh = next(x for x in self.project.load_shots("EP001")["shots"] if x["id"] == sid)
        rec = review.setdefault("shots", {}).setdefault(sid, {}).setdefault("video_takes", {}).setdefault(str(take), {"take": take})
        rec.update(asr_media_sha256=media_digest(self.project.video_path("EP001", sid, take)), asr_shot_sha256=shot_digest(sh),
                   speech_diff={"status": "exact", "critical_changes": list(critical), "similarity": 1.0})
        self.project.save_review("EP001", review)

    def approve(self, take=1, **kw):
        self.fake_asr(take)
        args = dict(video_take=take, visual="pass", audio="pass", continuity="pass", verdict="ok", speaker_face_ok=True,
                    action_window=[1, 3], speech_window=[0.5, 2], evidence="offline fixture: action and speech verified")
        args.update(kw)
        return mark(self.project, "EP001", "EP001-S01", **args)

    def issues(self):
        return cut_issues(self.project, "EP001", self.project.load_shots("EP001"), self.project.load_review("EP001"))

    def test_waive_needs_real_decision_row_and_warn_gate(self):
        from shots_tool import Findings, waive_findings, _waived
        rec = self.project.root / "项目开发" / "决策记录.md"
        rec.write_text("| 编号 | 日期 |\n|---|---|\n| 【D-001】 | 模板占位 |\n| D-002 | 2026-09-26 | E | 代理 | — | 豁免 |\n", encoding="utf-8")
        sh = {"id": "EP001-S01", "waive": [{"gate": "G08", "reason": "本镜是背影远景无朝向可写", "decision": "D-001"},
                                           {"gate": "G05", "reason": "本镜是背影远景无朝向可写", "decision": "D-002"},
                                           {"gate": "G46", "reason": "本镜是背影远景无朝向可写", "decision": "D-002", "_ok": True}]}
        F = Findings()
        waive_findings(F, [sh], [], self.project)
        self.assertFalse(_waived(sh, "G08"))    # 编号只在模板占位里，不算
        self.assertTrue(_waived(sh, "G05"))
        self.assertFalse(_waived(sh, "G46"))    # 非 warn 门，手写 _ok 也被清掉
        self.assertEqual(sum(1 for f in F.warns() if f["code"] == "G51"), 2)

    def test_revise_delivery_needs_user_row(self):
        from project_tool import _user_confirmed
        rec = self.project.root / "项目开发" / "决策记录.md"
        rec.write_text("| D-003 | 2026-09-26 | J | 代理 | — | 接受 |\n| D-004 | 2026-09-26 | J | 用户 | 问题1和2可以接受，先交付 | 接受 |\n", encoding="utf-8")
        self.assertFalse(_user_confirmed(self.project, "结论：REVISE\n用户确认：待确认\n"))
        self.assertFalse(_user_confirmed(self.project, "结论：REVISE\n用户确认：D-003\n"))
        self.assertTrue(_user_confirmed(self.project, "结论：REVISE\n用户确认：D-004\n"))

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

    def test_action_and_speech_windows_optional(self):
        # 2026-09-27 大改：动作/台词区间不再是放行前提
        self.approve(action_window=None, speech_window=None)
        self.assertFalse(self.issues())

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

    # ---- 红队回归（scratchpad/rt harness 场景）：每条都应被拦下 ----
    def test_copied_take_without_ledger_is_rejected(self):
        self.approve()
        other = self.project.video_path("EP001", "EP001-S01", 2)
        other.write_bytes(self.path.read_bytes())          # 复制成新 take，账本里没有它
        self.fake_asr(2)
        with self.assertRaises(ValueError) as cm:
            self.approve(take=2)
        self.assertIn("no_ledger_provenance", str(cm.exception))

    def test_prompt_changed_after_generation_needs_retake(self):
        self.approve()
        self.shot["video_prompt"] = "He slams the table and storms out."
        self.write_shots()
        with self.assertRaises(ValueError) as cm:
            self.approve()
        self.assertIn("stale_prompt", str(cm.exception))

    def test_video_from_old_frame_is_stale(self):
        f1 = self.project.frame_path("EP001", "EP001-S01", 1)
        f1.write_bytes(b"frame-one")
        self.make_take(2, b"take-two", frame_sha=media_digest(f1))
        self.approve(take=2)
        self.assertFalse(self.issues())
        self.project.frame_path("EP001", "EP001-S01", 2).write_bytes(b"frame-two")   # 换了起始帧
        self.assertTrue(any("stale_frame" in x for x in self.issues()))

    def test_asr_ok_requires_current_asr(self):
        args = dict(video_take=1, visual="pass", continuity="pass", verdict="ok", action_window=[1, 3], speech_window=[0.5, 2],
                    evidence="claims asr passed without running it")
        with self.assertRaises(ValueError):
            mark(self.project, "EP001", "EP001-S01", asr_ok=True, **args)
        with self.assertRaises(ValueError):
            mark(self.project, "EP001", "EP001-S01", audio="pass", **args)
        self.fake_asr(1, critical=["语种疑似不符"])
        with self.assertRaises(ValueError) as cm:
            mark(self.project, "EP001", "EP001-S01", asr_ok=True, **args)
        self.assertIn("语种", str(cm.exception))

    def test_listen_ok_needs_human_listener(self):
        self.approve()
        for who in (None, "claude", "self", "Agent", "模型", "子代理"):
            with self.assertRaises(ValueError):
                mark(self.project, "EP001", "EP001-S01", listen_ok=True, listener=who, evidence="heard it")
        e = mark(self.project, "EP001", "EP001-S01", listen_ok=True, listener="用户（母语者 佐藤）", evidence="0.5–2.0s 语调自然")
        rec = self.project.load_review("EP001")["shots"]["EP001-S01"]["video_takes"]["1"]
        self.assertEqual(rec["assessment"]["listener"], "用户（母语者 佐藤）")
        self.assertGreaterEqual(len(rec["evidence_log"]), 2)   # 证据追加，不覆盖
        self.assertEqual(e["verdict"], "ok")

    def test_must_show_carrier_needs_pass_and_no_weak(self):
        self.data["scenes"] = [{"id": "EP001-SC001", "must_show": [{"id": "MS1", "fact": "他把合同递过去", "shots": ["EP001-S01"]}]}]
        self.shot["must_show_ids"] = ["MS1"]
        self.write_shots()
        with self.assertRaises(ValueError):
            self.approve()                                   # 没核 must_show
        with self.assertRaises(ValueError):
            self.approve(must_show={"MS1": "unverified"})    # unverified 等同没核
        with self.assertRaises(ValueError):
            self.approve(verdict="weak", acceptance_reason="background softness only", must_show={"MS1": "pass"})
        self.approve(must_show={"MS1": "pass"})
        self.assertFalse(self.issues())

    def test_frame_take_must_exist_and_binds_sha(self):
        with self.assertRaises(ValueError):
            mark(self.project, "EP001", "EP001-S01", frame_take=9)
        f1 = self.project.frame_path("EP001", "EP001-S01", 1)
        f1.write_bytes(b"frame-one")
        mark(self.project, "EP001", "EP001-S01", frame_take=1, evidence="九项清单：一人、面朝左、手里合同、no text")
        fr = self.project.load_review("EP001")["shots"]["EP001-S01"]["frame_review"]
        self.assertEqual((fr["take"], fr["sha256"]), (1, media_digest(f1)))

    def test_dialogue_take_speaker_face_failed_blocks(self):
        self.approve(speaker_face_ok="unset")      # 没写口型结论不拦（大改后）
        with self.assertRaises(ValueError):
            self.approve(speaker_face_ok=False)
        self.approve()
        self.assertFalse(self.issues())
        self.path.write_bytes(b"swapped")          # 换了文件：口型结论跟着失效
        self.assertTrue(self.issues())

    def test_final_asr_ignores_poisoned_cache(self):
        with patch("review_tool.asr_python", return_value="fake-python"):
            reader = ASR(self.project)
        reader.cache[reader.key(self.path)] = [[0.0, 1.0, "我没有拿走合同"]]    # 投毒：缓存里写成"台词全对"
        row = json.dumps([str(self.path), [[0.2, 0.6, "嗡"]]], ensure_ascii=False)
        with patch("review_tool.subprocess.run", return_value=Mock(returncode=0, stdout=row)):
            got = reader.words([self.path], fresh=True)[str(self.path)]
        self.assertEqual(got, [[0.2, 0.6, "嗡"]])

    def test_extra_vocal_and_voice_mismatch(self):
        import shutil
        import subprocess
        from review_tool import extra_vocal_segments, voice_mismatch
        words = [[0.1, 0.3, "あの"], [0.6, 1.0, "我没有"], [1.0, 1.6, "拿走合同"], [2.4, 2.8, "嘘"]]
        self.assertEqual([r[2] for r in extra_vocal_segments(words, [0.6, 1.6])], ["あの", "嘘"])
        if not shutil.which("ffmpeg"):
            return
        refs = self.project.refs_path
        refs.write_text(json.dumps({"refs": {"IMG-A": {"kind": "identity", "subject": "甲", "voice": "a middle-aged man's low voice"}}}))
        wav = self.project.video_path("EP001", "EP001-S01", 5)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=300:duration=2", str(wav.with_suffix(".wav"))], check=True)
        got = voice_mismatch(self.project, self.shot, wav.with_suffix(".wav"), [0.0, 2.0])
        self.assertTrue(got and got["expected"] == "male" and got["f0_median_hz"] > 200)

    def test_draft_cannot_land_in_final_dir(self):
        from cut import cut
        with self.assertRaises(ValueError):
            cut(self.project, "EP001", out=self.project.final_path("EP001").with_name("x.mp4"), dry=True, draft=True)

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
