"""Offline regression tests. Synthetic reader records are not audience evidence."""
from __future__ import annotations
from contextlib import redirect_stdout, redirect_stderr
from copy import deepcopy
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import drama_tools as tools


def dump(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def accepted_fixture() -> dict:
    data = deepcopy(tools.load_json(tools.ROOT / "examples/pilot.json"))
    data["status"] = "accepted"
    data["review"] = {
        "status": "accepted", "hard_failures": [], "open_issues": [],
        "blind_read": {
            "reader_id": "synthetic-test-reader-not-an-actual-review",
            "independent": True, "input_scope": "screenplay_only", "verdict": "continue",
            "understood_goal": "Restore water supply.",
            "keep_watching_reason": "Synthetic fixture only: the drawing becomes a usable object.",
            "next_expectation": "A different application of the demonstrated ability.",
            "first_drop_point": None,
            "evidence": [{"scene_id": "EP01-S02",
                          "quote": data["scenes"][1]["dialogue"][0]["text"],
                          "observation": "Synthetic structural-test record; not an actual editorial judgement."}]
        }
    }
    return data


class EpisodeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.data = deepcopy(tools.load_json(tools.ROOT / "examples/pilot.json"))

    def codes(self, data=None) -> set[str]:
        return {x["code"] for x in tools.check_episode(self.data if data is None else data)}

    def test_original_pilot_has_no_structural_issues(self):
        self.assertEqual(tools.check_episode(self.data), [])

    def test_missing_field_is_reported_not_crash(self):
        del self.data["scenes"][0]["dialogue"]
        self.assertIn("REQUIRED", self.codes())

    def test_wrong_root_type(self):
        self.assertIn("TYPE", self.codes([]))

    def test_boolean_cannot_be_integer(self):
        self.data["episode_number"] = True
        self.assertIn("TYPE", self.codes())

    def test_timeline_gap(self):
        self.data["scenes"][1]["start_seconds"] += 2
        self.assertIn("TIMELINE_GAP_OR_OVERLAP", self.codes())

    def test_timeline_overlap(self):
        self.data["scenes"][1]["start_seconds"] -= 2
        self.assertIn("TIMELINE_GAP_OR_OVERLAP", self.codes())

    def test_zero_length_scene(self):
        self.data["scenes"][0]["end_seconds"] = 0
        self.assertIn("SCENE_DURATION", self.codes())

    def test_wrong_total_duration(self):
        self.data["duration_seconds"] = 77
        self.assertIn("TOTAL_DURATION", self.codes())

    def test_duplicate_scene_id(self):
        self.data["scenes"][1]["id"] = self.data["scenes"][0]["id"]
        self.assertIn("DUPLICATE_ID", self.codes())

    def test_unknown_speaker(self):
        self.data["scenes"][0]["dialogue"][0]["speaker_id"] = "CHAR-999"
        self.assertIn("UNKNOWN_REF", self.codes())

    def test_on_screen_speaker_must_be_present(self):
        self.data["scenes"][0]["character_ids"].remove("CHAR-002")
        self.assertIn("SPEAKER_NOT_PRESENT", self.codes())

    def test_voiceover_may_be_offscreen(self):
        self.data["scenes"][0]["character_ids"].remove("CHAR-002")
        for line in self.data["scenes"][0]["dialogue"]:
            if line["speaker_id"] == "CHAR-002": line["kind"] = "voiceover"
        self.assertNotIn("SPEAKER_NOT_PRESENT", self.codes())

    def test_unknown_payoff_scene(self):
        self.data["payoffs"][0]["scene_id"] = "EP01-S99"
        self.assertIn("UNKNOWN_REF", self.codes())

    def test_future_hook_cannot_resolve_in_same_episode(self):
        self.data["ending"]["planned_resolution_episode"] = 1
        self.assertIn("HOOK_RESOLUTION", self.codes())

    def test_finale_can_close_without_hook(self):
        self.data["ending"].update(type="closure", is_finale=True,
                                   question="", planned_resolution_episode=None)
        self.assertFalse(tools.has_errors(tools.check_episode(self.data)))

    def test_dense_dialogue_is_estimate_warning(self):
        self.data["scenes"][0]["dialogue"][0]["text"] = "中文对白" * 250
        issues = tools.check_episode(self.data)
        match = [x for x in issues if x["code"] == "DIALOGUE_OVERLOAD_ESTIMATE"]
        self.assertEqual(match[0]["severity"], "warning")

    def test_measured_audio_overload_is_error(self):
        self.data["scenes"][0]["measured_audio_seconds"] = 50
        self.assertIn("MEASURED_AUDIO_OVERLOAD", self.codes())

    def test_measured_timing_needs_source(self):
        self.data["timing_status"] = "measured"
        self.assertIn("TIMING_EVIDENCE", self.codes())

    def test_accepted_needs_review(self):
        self.data["status"] = "accepted"
        self.assertIn("REVIEW_MISSING", self.codes())

    def test_complete_review_fixture_passes_structure(self):
        self.assertFalse(tools.has_errors(tools.check_episode(accepted_fixture())))

    def test_legacy_scores_cannot_replace_independent_read(self):
        data = accepted_fixture()
        data["review"].pop("blind_read")
        data["review"]["scores"] = [{"criterion": "payoff", "score": 5,
                                    "evidence_scene_ids": ["EP01-S02"], "reason": "Self-rating"}]
        self.assertIn("BLIND_READ_MISSING", self.codes(data))

    def test_legacy_score_does_not_override_actual_read(self):
        data = accepted_fixture()
        data["review"]["scores"] = [{"criterion": "payoff", "score": 0,
                                    "evidence_scene_ids": ["EP01-S02"], "reason": "Old rating"}]
        self.assertFalse(tools.has_errors(tools.check_episode(data)))

    def test_self_review_does_not_count_as_independent(self):
        data = accepted_fixture()
        data["review"]["blind_read"]["independent"] = False
        self.assertIn("REVIEW_NOT_INDEPENDENT", self.codes(data))

    def test_invented_quote_cannot_certify_review(self):
        data = accepted_fixture()
        data["review"]["blind_read"]["evidence"][0]["quote"] = "An invented line absent from the script"
        self.assertIn("REVIEW_QUOTE_MISMATCH", self.codes(data))

    def test_author_goal_label_is_not_screenplay_evidence(self):
        data = accepted_fixture()
        data["review"]["blind_read"]["evidence"][0]["quote"] = data["scenes"][1]["goal"]
        self.assertIn("REVIEW_QUOTE_MISMATCH", self.codes(data))

    def test_reader_revision_verdict_blocks_acceptance(self):
        data = accepted_fixture()
        data["review"]["blind_read"]["verdict"] = "revise"
        self.assertIn("REVIEW_REQUIRES_REVISION", self.codes(data))

    def test_finale_may_end_without_next_episode_expectation(self):
        data = accepted_fixture()
        data["ending"].update(type="closure", is_finale=True,
                              question="", planned_resolution_episode=None)
        data["review"]["blind_read"].update(verdict="closure_satisfied", next_expectation="")
        self.assertFalse(tools.has_errors(tools.check_episode(data)))

    def test_nonfinal_episode_needs_reader_expectation(self):
        data = accepted_fixture()
        data["review"]["blind_read"]["next_expectation"] = ""
        self.assertIn("REVIEW_EXPECTATION_MISSING", self.codes(data))

    def test_review_hard_failure_blocks_acceptance(self):
        data = accepted_fixture()
        data["review"]["hard_failures"] = ["Fixture failure"]
        self.assertIn("HARD_FAILURES", self.codes(data))

    def test_promise_resolution_needs_evidence(self):
        self.data["continuity"]["promises"][0].update(status="resolved", resolved_episode=1)
        self.assertIn("UNKNOWN_REF", self.codes())

    def test_speech_estimate_is_configurable(self):
        self.assertEqual(tools.speech_seconds("你好世界", cps=2), 2)
        self.assertEqual(tools.speech_seconds("one two three", wps=3), 1)


class ConceptTests(unittest.TestCase):
    def setUp(self):
        self.cards = deepcopy(tools.load_json(tools.ROOT / "examples/concepts.json"))

    def test_example_cards_valid(self):
        self.assertEqual(tools.check_concepts(self.cards), [])

    def test_duplicate_ids_rejected(self):
        self.cards[1]["id"] = self.cards[0]["id"]
        self.assertTrue(tools.has_errors(tools.check_concepts(self.cards)))

    def test_cosmetic_rename_is_flagged(self):
        data = tools.load_json(tools.ROOT / "evals/near-duplicate-fixture.json")
        result = tools.compare_concepts(data, [])
        self.assertEqual(result["status"], "review_needed")
        self.assertTrue(result["matches"][0]["core_axes_match"])

    def test_different_examples_are_not_flagged_by_default_heuristic(self):
        result = tools.compare_concepts(self.cards, [])
        self.assertEqual(result["comparisons"], 66)
        self.assertEqual(result["matches"], [])

    def test_normalization_handles_full_width(self):
        self.assertEqual(tools.normalize("ＡＢＣ， 123!"), "abc123")

    def test_archive_refuses_duplicate_without_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "history.jsonl"
            tools.archive_concepts(self.cards[:2], path)
            before = path.read_bytes()
            with self.assertRaises(ValueError): tools.archive_concepts(self.cards[:1], path)
            self.assertEqual(path.read_bytes(), before)
            self.assertFalse(path.with_name(path.name + ".lock").exists())

    def test_archive_lock_is_respected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "history.jsonl"
            lock = path.with_name(path.name + ".lock")
            lock.write_text("fixture")
            with self.assertRaises(ValueError): tools.archive_concepts(self.cards[:1], path)
            self.assertTrue(lock.exists())
            self.assertFalse(path.exists())

    def test_corrupt_archive_not_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "history.jsonl"
            path.write_text("{malformed}\n")
            before = path.read_bytes()
            with self.assertRaises(ValueError): tools.archive_concepts(self.cards[:1], path)
            self.assertEqual(before, path.read_bytes())


class ProjectTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.project = Path(self.tmp.name) / "demo"
        tools.init_project(self.project, "Test", 24)

    def tearDown(self):
        self.tmp.cleanup()

    def make_accepted_project(self):
        data = accepted_fixture()
        data["project_id"] = "demo"
        bible = tools.load_json(tools.ROOT / "examples/bible.json")
        bible["project_id"] = "demo"
        dump(self.project / "bible.json", bible)
        dump(self.project / "episodes/EP01.json", data)
        state = tools.load_json(self.project / "project-state.json")
        state.update(completed_episodes=["EP01"], episode_files={"EP01": "episodes/EP01.json"},
                     promises=deepcopy(data["continuity"]["promises"]))
        dump(self.project / "project-state.json", state)
        return data, state

    def test_scaffold_has_warnings_not_errors(self):
        result = tools.check_project(self.project)
        self.assertFalse(tools.has_errors(result))
        self.assertIn("NO_COMPLETED_EPISODES", {x["code"] for x in result})

    def test_init_refuses_overwrite(self):
        before = (self.project / "brief.json").read_bytes()
        with self.assertRaises(ValueError): tools.init_project(self.project, "Changed", 3)
        self.assertEqual(before, (self.project / "brief.json").read_bytes())

    def test_missing_project_file(self):
        (self.project / "bible.json").unlink()
        self.assertIn("MISSING_FILE", {x["code"] for x in tools.check_project(self.project)})

    def test_valid_accepted_fixture_project(self):
        self.make_accepted_project()
        self.assertFalse(tools.has_errors(tools.check_project(self.project)))

    def test_future_fact_rejected(self):
        data, _ = self.make_accepted_project()
        data["continuity"]["requires"] = ["FACT-NOT-YET"]
        dump(self.project / "episodes/EP01.json", data)
        self.assertIn("FUTURE_OR_MISSING_FACT", {x["code"] for x in tools.check_project(self.project)})

    def test_unregistered_asset_rejected(self):
        self.make_accepted_project()
        bible = tools.load_json(self.project / "bible.json")
        bible["props"] = []
        dump(self.project / "bible.json", bible)
        self.assertIn("BIBLE_ASSET", {x["code"] for x in tools.check_project(self.project)})

    def test_project_path_escape_rejected(self):
        with self.assertRaises(ValueError): tools.safe_project_path(self.project, "../../outside.json")

    def test_draft_not_counted_as_complete(self):
        data, _ = self.make_accepted_project()
        data["status"] = "draft"
        data["review"]["status"] = "not_reviewed"
        dump(self.project / "episodes/EP01.json", data)
        self.assertIn("NOT_ACCEPTED", {x["code"] for x in tools.check_project(self.project)})

    def test_state_discontinuity_detected(self):
        data, _ = self.make_accepted_project()
        data["continuity"]["state_changes"].append({
            "entity_id": "PROP-005", "field": "holder", "before": "WRONG-HOLDER",
            "after": "CHAR-002", "cause_scene_id": "EP01-S04"})
        dump(self.project / "episodes/EP01.json", data)
        self.assertIn("STATE_DISCONTINUITY", {x["code"] for x in tools.check_project(self.project)})

    def test_invalid_episode_count(self):
        with self.assertRaises(ValueError): tools.init_project(Path(self.tmp.name)/"zero", "T", 0)


class JsonAndCliTests(unittest.TestCase):
    def test_non_finite_json_rejected(self):
        with self.assertRaises(ValueError): tools.parse_json('{"n":NaN}')

    def test_duplicate_json_keys_rejected(self):
        with self.assertRaises(ValueError): tools.parse_json('{"n":1,"n":2}')

    def test_cli_valid_pilot(self):
        output = io.StringIO()
        with redirect_stdout(output):
            code = tools.main(["check", str(tools.ROOT/"examples/pilot.json")])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output.getvalue())["status"], "pass")

    def test_cli_missing_file_is_controlled_error(self):
        with redirect_stderr(io.StringIO()):
            code = tools.main(["check", "/definitely-missing/episode.json"])
        self.assertEqual(code, 2)

    def test_cli_invalid_speed_is_controlled_error(self):
        with redirect_stderr(io.StringIO()):
            code = tools.main(["check", str(tools.ROOT/"examples/pilot.json"), "--cps", "0"])
        self.assertEqual(code, 2)

    def test_cli_invalid_json_returns_two(self):
        with tempfile.TemporaryDirectory() as tmp:
            file = Path(tmp)/"broken.json"
            file.write_text("{")
            with redirect_stderr(io.StringIO()): code = tools.main(["check", str(file)])
            self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
