#!/usr/bin/env python3
"""Offline helpers for short-drama-writer. Python 3.10+, standard library only.

No model calls, network requests, package installation or automatic publishing.
Shape validation supports only the schema keywords used by the bundled schemas;
it is not a general JSON Schema engine. Editorial merit remains a human/model task.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from copy import deepcopy
import json
import math
import os
from pathlib import Path
import re
import sys
import tempfile
import unicodedata
from typing import Any, Iterator

ROOT = Path(__file__).resolve().parents[1]
AXES = {"desire": .08, "advantage": .17, "operation": .22,
        "obstacle": .13, "relationship": .07, "reveal": .08,
        "reward": .08, "growth": .12, "arena": .05}
EPS = .01
Issue = dict[str, str]


def no_constants(value: str) -> None:
    raise ValueError(f"Non-finite JSON number is not allowed: {value}")


def unique_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON object key: {key}")
        result[key] = value
    return result


def parse_json(text: str) -> Any:
    return json.loads(text, parse_constant=no_constants, object_pairs_hook=unique_keys)


def load_json(path: Path) -> Any:
    return parse_json(path.read_text(encoding="utf-8-sig"))


def issue(items: list[Issue], code: str, path: str, message: str,
          severity: str = "error") -> None:
    items.append({"severity": severity, "code": code, "path": path, "message": message})


def matches_type(value: Any, typ: str) -> bool:
    if typ == "object": return isinstance(value, dict)
    if typ == "array": return isinstance(value, list)
    if typ == "string": return isinstance(value, str)
    if typ == "boolean": return isinstance(value, bool)
    if typ == "null": return value is None
    if typ == "integer": return isinstance(value, int) and not isinstance(value, bool)
    if typ == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
    raise ValueError(f"Unsupported schema type: {typ}")


def validate_shape(value: Any, spec: dict[str, Any], path: str = "$",
                   issues: list[Issue] | None = None) -> list[Issue]:
    """Validate the subset of JSON Schema used in this package, not arbitrary schemas."""
    out = [] if issues is None else issues
    types = spec.get("type")
    if isinstance(types, str): types = [types]
    if types and not any(matches_type(value, t) for t in types):
        issue(out, "TYPE", path, f"Expected {'/'.join(types)}, got {type(value).__name__}")
        return out
    if "const" in spec and value != spec["const"]:
        issue(out, "CONST", path, "Value does not match required constant")
    if "enum" in spec and value not in spec["enum"]:
        issue(out, "ENUM", path, f"Allowed values: {spec['enum']}")
    if isinstance(value, str):
        if len(value.strip()) < spec.get("minLength", 0):
            issue(out, "EMPTY", path, "String is missing or blank")
        if "pattern" in spec and not re.search(spec["pattern"], value):
            issue(out, "PATTERN", path, f"String does not match {spec['pattern']}")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if not math.isfinite(value):
            issue(out, "NON_FINITE", path, "Number must be finite")
        if "minimum" in spec and value < spec["minimum"]:
            issue(out, "MINIMUM", path, f"Must be >= {spec['minimum']}")
        if "maximum" in spec and value > spec["maximum"]:
            issue(out, "MAXIMUM", path, f"Must be <= {spec['maximum']}")
    if isinstance(value, list):
        if len(value) < spec.get("minItems", 0):
            issue(out, "MIN_ITEMS", path, f"Needs at least {spec['minItems']} items")
        for index, item in enumerate(value):
            validate_shape(item, spec.get("items", {}), f"{path}[{index}]", out)
    if isinstance(value, dict):
        props = spec.get("properties", {})
        for key in spec.get("required", []):
            if key not in value:
                issue(out, "REQUIRED", f"{path}.{key}", "Required field is missing")
        extra = spec.get("additionalProperties", True)
        for key, item in value.items():
            if key in props:
                validate_shape(item, props[key], f"{path}.{key}", out)
            elif extra is False:
                issue(out, "UNEXPECTED", f"{path}.{key}", "Unknown field for schema v1.0")
            elif isinstance(extra, dict):
                validate_shape(item, extra, f"{path}.{key}", out)
    return out


def schema_check(value: Any, name: str) -> list[Issue]:
    return validate_shape(value, load_json(ROOT / "assets" / "schemas" / f"{name}.schema.json"))


def has_errors(issues: list[Issue]) -> bool:
    return any(x["severity"] == "error" for x in issues)


def unique(values: list[str], path: str, issues: list[Issue]) -> None:
    seen: set[str] = set()
    for value in values:
        if value in seen:
            issue(issues, "DUPLICATE_ID", path, f"Duplicate: {value}")
        seen.add(value)


def speech_seconds(text: str, cps: float = 4, wps: float = 2.5) -> float:
    """Rough screen-for-overload only; Chinese characters plus non-CJK word runs."""
    chars = re.findall(r"[\u3400-\u4dbf\u4e00-\u9fff\U00020000-\U0002fa1f]", text)
    rest = re.sub(r"[\u3400-\u4dbf\u4e00-\u9fff\U00020000-\U0002fa1f]", " ", text)
    words = re.findall(r"[^\W_]+(?:['’-][^\W_]+)*", rest, flags=re.UNICODE)
    return len(chars) / cps + len(words) / wps


def check_episode(data: Any, cps: float = 4, wps: float = 2.5) -> list[Issue]:
    out = schema_check(data, "episode")
    if has_errors(out): return out
    ep = data["episode_id"]
    number = data["episode_number"]
    if ep != f"EP{number:02d}":
        issue(out, "EPISODE_ID", "$.episode_id", "ID must agree with episode_number, e.g. EP01")
    groups = {k: {x["id"] for x in data[k]} for k in ("characters", "locations", "props")}
    assets = set().union(*groups.values())
    unique([x["id"] for k in groups for x in data[k]], "$.assets", out)
    unique(data["rules_used"], "$.rules_used", out)
    scenes = {s["id"] for s in data["scenes"]}
    unique([s["id"] for s in data["scenes"]], "$.scenes", out)

    def ref(value: str, allowed: set[str], path: str) -> None:
        if value not in allowed:
            issue(out, "UNKNOWN_REF", path, f"Unknown reference: {value}")

    previous = 0.0
    for i, scene in enumerate(data["scenes"]):
        p = f"$.scenes[{i}]"
        if not re.fullmatch(re.escape(ep) + r"-S\d{2,}", scene["id"]):
            issue(out, "SCENE_ID", p + ".id", "Expected episode-prefixed scene ID, e.g. EP01-S01")
        ref(scene["location_id"], groups["locations"], p + ".location_id")
        for field, table in (("character_ids", "characters"), ("prop_ids", "props")):
            unique(scene[field], p + "." + field, out)
            for value in scene[field]: ref(value, groups[table], p + "." + field)
        start, end = scene["start_seconds"], scene["end_seconds"]
        if abs(start - previous) > EPS:
            issue(out, "TIMELINE_GAP_OR_OVERLAP", p, f"Scene must begin at {previous:g}s")
        if end <= start:
            issue(out, "SCENE_DURATION", p, "Scene end must be after start")
        length = end - start
        extra = scene["non_overlapping_action_seconds"]
        if extra > length + EPS:
            issue(out, "ACTION_OVERLOAD", p, "Non-overlapping action exceeds scene duration")
        previous = end
        speech = 0.0
        for j, line in enumerate(scene["dialogue"]):
            ref(line["speaker_id"], groups["characters"] | {"NARRATOR", "SYSTEM"}, p + f".dialogue[{j}]")
            if (line["kind"] == "spoken" and line["speaker_id"] not in {"NARRATOR", "SYSTEM"}
                    and line["speaker_id"] not in scene["character_ids"]):
                issue(out, "SPEAKER_NOT_PRESENT", p + f".dialogue[{j}]", "On-screen speaker is not in this scene")
            speech += speech_seconds(line["text"], cps, wps)
        measured = scene.get("measured_audio_seconds")
        if measured is not None:
            if measured + extra > length + EPS:
                issue(out, "MEASURED_AUDIO_OVERLOAD", p, "Measured audio plus extra action exceeds duration")
        elif speech + extra > max(0, length) * 1.10 + EPS:
            issue(out, "DIALOGUE_OVERLOAD_ESTIMATE", p,
                  f"Rough speech {speech:.1f}s + extra action {extra:g}s vs scene {length:g}s; measure or revise", "warning")
    if abs(previous - data["duration_seconds"]) > EPS:
        issue(out, "TOTAL_DURATION", "$.duration_seconds", f"Last scene ends at {previous:g}s")
    if abs(data["duration_seconds"] / data["target_duration_seconds"] - 1) > .20:
        issue(out, "TARGET_DURATION", "$.duration_seconds", "Differs from requested duration by more than 20%", "warning")
    if data["timing_status"] == "measured" and not data.get("timing_evidence"):
        issue(out, "TIMING_EVIDENCE", "$.timing_evidence", "Measured timing requires a recorded measurement source")
    unique([p["id"] for p in data["payoffs"]], "$.payoffs", out)
    for i, payoff in enumerate(data["payoffs"]):
        ref(payoff["scene_id"], scenes, f"$.payoffs[{i}].scene_id")
    ending = data["ending"]
    ref(ending["cause_scene_id"], scenes, "$.ending.cause_scene_id")
    resolution = ending["planned_resolution_episode"]
    if ending["type"] not in {"closure", "open_ending"} and not ending["question"].strip():
        issue(out, "EMPTY_HOOK", "$.ending.question", "Non-closure ending needs a concrete next question")
    if resolution is not None and resolution <= number:
        issue(out, "HOOK_RESOLUTION", "$.ending.planned_resolution_episode", "Future hook must resolve in a later episode")
    if not ending["is_finale"] and ending["type"] not in {"closure", "open_ending"} and resolution is None:
        issue(out, "HOOK_PLAN", "$.ending", "A continuing hook needs a planned resolution episode")
    continuity = data["continuity"]
    unique(continuity["requires"], "$.continuity.requires", out)
    unique([f["id"] for f in continuity["establishes"]], "$.continuity.establishes", out)
    for i, fact in enumerate(continuity["establishes"]):
        ref(fact["source_scene_id"], scenes, f"$.continuity.establishes[{i}]")
        for person in fact["known_by"]:
            ref(person, groups["characters"] | {"PUBLIC"}, f"$.continuity.establishes[{i}].known_by")
    for i, change in enumerate(continuity["state_changes"]):
        ref(change["entity_id"], assets | {"WORLD", "PROJECT"}, f"$.continuity.state_changes[{i}]")
        ref(change["cause_scene_id"], scenes, f"$.continuity.state_changes[{i}].cause_scene_id")
        if change["before"] == change["after"]:
            issue(out, "NO_STATE_CHANGE", f"$.continuity.state_changes[{i}]", "Before and after are identical", "warning")
    unique([p["id"] for p in continuity["promises"]], "$.continuity.promises", out)
    for i, promise in enumerate(continuity["promises"]):
        p = f"$.continuity.promises[{i}]"
        if promise["opened_episode"] > number or promise["due_episode"] < promise["opened_episode"]:
            issue(out, "PROMISE_DATES", p, "Promise opening/due episode is inconsistent")
        if promise["status"] == "resolved":
            if promise["resolved_episode"] != number:
                issue(out, "PROMISE_RESOLUTION", p, "Episode delta must resolve in the current episode")
            ref(promise["evidence_scene_id"], scenes, p + ".evidence_scene_id")
        elif promise["resolved_episode"] is not None:
            issue(out, "PROMISE_STATUS", p, "Unresolved promise cannot have a resolved_episode")
    for i, item in enumerate(data["production_handoff"]["critical_visuals"]):
        ref(item["scene_id"], scenes, f"$.production_handoff.critical_visuals[{i}]")
    review = data["review"]
    # Legacy scores remain readable, but never certify editorial quality.
    unique([s["criterion"] for s in review.get("scores", [])], "$.review.scores", out)
    for i, score in enumerate(review.get("scores", [])):
        for scene_id in score["evidence_scene_ids"]:
            ref(scene_id, scenes, f"$.review.scores[{i}].evidence_scene_ids")
    blind_read = review.get("blind_read")
    if blind_read is not None:
        scene_by_id = {s["id"]: s for s in data["scenes"]}
        for i, evidence in enumerate(blind_read["evidence"]):
            path = f"$.review.blind_read.evidence[{i}]"
            ref(evidence["scene_id"], scenes, path + ".scene_id")
            scene = scene_by_id.get(evidence["scene_id"])
            if scene is not None:
                # Only material presented to the viewer counts; author labels do not.
                visible_text = [scene["action"], *scene["on_screen_text"],
                                *(line["text"] for line in scene["dialogue"])]
                if not any(evidence["quote"] in text for text in visible_text):
                    issue(out, "REVIEW_QUOTE_MISMATCH", path + ".quote",
                          "Quote must occur in this scene's action, dialogue or on-screen text")
    if data["status"] == "accepted" and review["status"] != "accepted":
        issue(out, "REVIEW_MISSING", "$.review.status", "Accepted episode needs an accepted editorial review")
    if review["status"] == "accepted":
        if review["hard_failures"]:
            issue(out, "HARD_FAILURES", "$.review.hard_failures", "Accepted review still has hard failures")
        if blind_read is None:
            issue(out, "BLIND_READ_MISSING", "$.review.blind_read",
                  "Acceptance requires an independent screenplay read with actual textual evidence")
        else:
            if not blind_read["independent"]:
                issue(out, "REVIEW_NOT_INDEPENDENT", "$.review.blind_read.independent",
                      "Author self-review does not satisfy independent reading")
            if blind_read["verdict"] == "revise":
                issue(out, "REVIEW_REQUIRES_REVISION", "$.review.blind_read.verdict",
                      "Resolve the reader's revision request before accepting")
            if blind_read["verdict"] == "closure_satisfied" and not ending["is_finale"]:
                issue(out, "REVIEW_CLOSURE_MISMATCH", "$.review.blind_read.verdict",
                      "Closure-only acceptance is for a finale")
            if not ending["is_finale"] and not blind_read["next_expectation"].strip():
                issue(out, "REVIEW_EXPECTATION_MISSING", "$.review.blind_read.next_expectation",
                      "Record what the reader actually wants to see next")
    return out


def check_reveal(data: Any) -> list[Issue]:
    """Check explicit reveal-arc fields, not the persuasiveness of prose evidence."""
    out = schema_check(data, "reveal-arc")
    if has_errors(out):
        return out
    actors = {a["id"]: a for a in data["actors"]}
    facts = {f["id"]: f for f in data["facts"]}
    beats = {b["id"]: i for i, b in enumerate(data["beats"])}
    unique([a["id"] for a in data["actors"]], "$.actors", out)
    unique([f["id"] for f in data["facts"]], "$.facts", out)
    unique([b["id"] for b in data["beats"]], "$.beats", out)
    if not any(a["role"] == "protagonist" for a in data["actors"]):
        issue(out, "MISSING_PROTAGONIST", "$.actors", "At least one protagonist is required")
    if data["due_episode"] < data["start_episode"]:
        issue(out, "REVEAL_RANGE", "$.due_episode", "Deadline precedes arc start")
    for i, fact in enumerate(data["facts"]):
        if fact["introduced_at_beat"] not in beats:
            issue(out, "UNKNOWN_BEAT", f"$.facts[{i}]", "Fact introduction references an unknown beat")

    belief = {a["id"]: a["initial_belief"] for a in data["actors"]}
    stance = {a["id"]: a["initial_stance"] for a in data["actors"]}
    earned: set[str] = set()
    all_payoff_ids: list[str] = []
    last_episode = data["start_episode"]
    setbacks = 0

    def evidence_refs(values: list[str], index: int, path: str) -> None:
        unique(values, path, out)
        for value in values:
            if value not in facts:
                issue(out, "UNKNOWN_FACT", path, f"Unknown fact: {value}")
            elif facts[value]["introduced_at_beat"] in beats:
                if beats[facts[value]["introduced_at_beat"]] > index:
                    issue(out, "FUTURE_EVIDENCE", path, f"Fact not yet introduced: {value}")

    for index, beat in enumerate(data["beats"]):
        path = f"$.beats[{index}]"
        number = beat["episode_number"]
        if not data["start_episode"] <= number <= data["due_episode"]:
            issue(out, "REVEAL_RANGE", path, "Beat is outside the planned arc range")
        if number < last_episode:
            issue(out, "REVEAL_ORDER", path, "Beats must be listed in episode order")
        last_episode = number
        if not re.fullmatch(rf"EP{number:02d}-S\d{{2,}}", beat["scene_id"]):
            issue(out, "REVEAL_SCENE_ID", path + ".scene_id", "Scene ID disagrees with episode number")
        evidence_refs(beat["evidence_fact_ids"], index, path + ".evidence_fact_ids")
        carry = set(beat["carry_forward_payoff_ids"])
        unique(beat["carry_forward_payoff_ids"], path + ".carry_forward_payoff_ids", out)
        for missing in sorted(earned - carry):
            issue(out, "PAYOFF_RESET", path, f"Previously earned payoff is not preserved: {missing}")
        for unknown in sorted(carry - earned):
            issue(out, "UNKNOWN_PAYOFF", path, f"Cannot carry payoff not yet earned: {unknown}")
        for field, state in (("belief_updates", belief), ("public_moves", stance)):
            updates = beat[field]
            unique([u["actor_id"] for u in updates], path + "." + field, out)
            for j, update in enumerate(updates):
                subpath = f"{path}.{field}[{j}]"
                evidence_refs(update["basis_fact_ids"], index, subpath + ".basis_fact_ids")
                if not update["basis_fact_ids"]:
                    issue(out, "UNSUPPORTED_TURN", subpath, "Record evidence underlying the change", "warning")
                actor_id = update["actor_id"]
                if actor_id not in actors:
                    issue(out, "UNKNOWN_ACTOR", subpath, f"Unknown actor: {actor_id}")
                    continue
                if update["before"] != state[actor_id]:
                    issue(out, "BELIEF_DISCONTINUITY" if field == "belief_updates" else "STANCE_DISCONTINUITY",
                          subpath, "Before value does not match this actor's previous state")
                state[actor_id] = update["after"]
        for payoff in beat["earned_payoffs"]:
            all_payoff_ids.append(payoff["id"])
            earned.add(payoff["id"])
        if beat["kind"] == "countermove":
            setbacks += 1
            if not beat["setback_reason"] or not beat["setback_reason"].strip():
                issue(out, "UNEXPLAINED_SETBACK", path, "A countermove requires its causal reason")
            if not beat["new_information"].strip():
                issue(out, "STALL_RISK", path, "Countermove has no recorded new information; review for empty delay", "warning")
    unique(all_payoff_ids, "$.beats.earned_payoffs", out)
    if setbacks > data["setback_budget"]:
        issue(out, "SETBACK_BUDGET", "$.beats", "Setback budget exceeded; justify progress or revise the plan", "warning")

    scene_positions: dict[str, int] = {}
    for i, beat in enumerate(data["beats"]):
        scene_positions[beat["scene_id"]] = i
    anchor = data["audience_anchor"]["scene_id"]
    if anchor not in scene_positions:
        issue(out, "UNKNOWN_ANCHOR", "$.audience_anchor", "Anchor scene must appear in the arc")
    elif data["mode"] in {"known_truth", "partial_truth"}:
        first_countermove = next((i for i, b in enumerate(data["beats"]) if b["kind"] == "countermove"), None)
        if first_countermove is not None and scene_positions[anchor] > first_countermove:
            issue(out, "LATE_AUDIENCE_ANCHOR", "$.audience_anchor", "Known-truth anchor occurs after the initial countermove")
    cashout = data["final_cashout"]
    if not data["start_episode"] <= cashout["episode_number"] <= data["due_episode"]:
        issue(out, "CASHOUT_DEADLINE", "$.final_cashout", "Cashout is outside the arc's promised range")
    if cashout["scene_id"] not in scene_positions:
        issue(out, "UNKNOWN_CASHOUT_SCENE", "$.final_cashout", "Cashout scene must appear in the arc")
    else:
        index = scene_positions[cashout["scene_id"]]
        if data["beats"][index]["episode_number"] != cashout["episode_number"]:
            issue(out, "CASHOUT_EPISODE", "$.final_cashout", "Cashout episode does not match its scene")
        evidence_refs(cashout["evidence_fact_ids"], index, "$.final_cashout.evidence_fact_ids")
        if data["status"] == "resolved" and not any(
            b["earned_payoffs"] for b in data["beats"] if b["scene_id"] == cashout["scene_id"]
        ):
            issue(out, "EMPTY_CASHOUT", "$.final_cashout", "Resolved arc needs an earned payoff in the cashout scene")
    if data["status"] == "resolved" and not cashout["old_question_closed"]:
        issue(out, "UNRESOLVED_REVEAL", "$.final_cashout", "Resolved arc must close the old question")
    return out


def check_concepts(data: Any) -> list[Issue]:
    out = schema_check(data, "concepts")
    if not has_errors(out):
        unique([c["id"] for c in data], "$", out)
        for i, c in enumerate(data):
            if c["variant_of"] == c["id"]:
                issue(out, "SELF_VARIANT", f"$[{i}].variant_of", "A concept cannot be its own variant")
    return out


def normalize(value: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKC", value).lower() if c.isalnum())


def grams(value: str) -> set[str]:
    value = normalize(value)
    if not value: return set()
    if len(value) < 3: return {value}
    return {value[i:i+3] for i in range(len(value)-2)}


def jaccard(a: set[str], b: set[str]) -> float:
    return len(a & b) / len(a | b) if a or b else 0.0


def similarity(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    axis_scores = {k: jaccard({normalize(t) for t in a["fingerprint"][k]},
                              {normalize(t) for t in b["fingerprint"][k]}) for k in AXES}
    tag_score = sum(axis_scores[k] * weight for k, weight in AXES.items())
    wording = jaccard(grams(a["mechanism_summary"]), grams(b["mechanism_summary"]))
    core_match = all(axis_scores[k] >= .8 for k in ("advantage", "operation", "obstacle"))
    return {"a": a["id"], "b": b["id"], "heuristic_score": round(max(tag_score, .9 * wording), 4),
            "tag_score": round(tag_score, 4), "wording_score": round(wording, 4),
            "core_axes_match": core_match,
            "shared_axes": [k for k, score in axis_scores.items() if score >= .8],
            "declared_variant": a.get("variant_of") == b["id"] or b.get("variant_of") == a["id"]}


def load_archive(path: Path) -> list[dict[str, Any]]:
    if not path.exists(): return []
    cards = []
    for n, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        if line.strip():
            try: cards.append(parse_json(line))
            except ValueError as exc: raise ValueError(f"Archive line {n}: {exc}") from exc
    if cards:
        errors = check_concepts(cards)
        if has_errors(errors): raise ValueError(f"Archive validation failed: {errors[:3]}")
    return cards


def compare_concepts(cards: list[dict[str, Any]], history: list[dict[str, Any]],
                     threshold: float = .68) -> dict[str, Any]:
    count = len(cards) * (len(cards)-1) // 2 + len(cards) * len(history)
    if count > 100000:
        raise ValueError("More than 100,000 comparisons; split input/archive into smaller batches")
    results = []
    for i, a in enumerate(cards):
        for b in cards[i+1:] + history:
            score = similarity(a, b)
            if score["heuristic_score"] >= threshold or score["core_axes_match"] or a["id"] == b["id"]:
                results.append(score)
    results.sort(key=lambda x: x["heuristic_score"], reverse=True)
    return {"status": "review_needed" if results else "no_heuristic_match", "comparisons": count,
            "threshold": threshold, "matches": results,
            "limitation": "Tag/wording heuristic only; not semantic or global originality verification."}


def safe_project_path(project: Path, relative: str) -> Path:
    if Path(relative).is_absolute(): raise ValueError("Episode file path must be project-relative")
    path = (project / relative).resolve()
    if not path.is_relative_to(project.resolve()):
        raise ValueError("Episode file path escapes project directory")
    return path


def check_project(project: Path) -> list[Issue]:
    out: list[Issue] = []
    docs: dict[str, Any] = {}
    for name in ("brief", "bible", "series-plan", "project-state"):
        path = project / f"{name}.json"
        if not path.is_file():
            issue(out, "MISSING_FILE", str(path), "Required project file is missing")
            continue
        try:
            docs[name] = load_json(path)
            out.extend(schema_check(docs[name], name))
        except (OSError, ValueError) as exc:
            issue(out, "FILE_READ", str(path), str(exc))
    if has_errors(out): return out
    brief, bible, plan, state = (docs[k] for k in ("brief", "bible", "series-plan", "project-state"))
    pid = brief["project_id"]
    for name, doc in docs.items():
        if doc["project_id"] != pid: issue(out, "PROJECT_ID", name, "Inconsistent project_id")
    for name in ("series-plan", "project-state"):
        if docs[name]["total_episodes"] != brief["total_episodes"]:
            issue(out, "EPISODE_COUNT", name, "Total episode count disagrees with brief")
    if state["canon_version"] != bible["canon_version"]:
        issue(out, "CANON_VERSION", "project-state", "State and bible canon versions disagree")
    if len(plan["episodes"]) != plan["total_episodes"]:
        issue(out, "PLAN_INCOMPLETE", "series-plan", "Outline does not yet contain every planned episode", "warning")
    unique(state["completed_episodes"], "project-state.completed_episodes", out)
    if set(state["completed_episodes"]) != set(state["episode_files"]):
        issue(out, "COMPLETION_INDEX", "project-state", "Completed list and accepted file index disagree")
    unique([a["id"] for kind in ("characters", "locations", "props") for a in bible[kind]], "bible.assets", out)
    unique([r["id"] for r in bible["rules"]], "bible.rules", out)
    known_assets = {kind: {a["id"] for a in bible[kind]} for kind in ("characters", "locations", "props")}
    known_rules = {r["id"] for r in bible["rules"]}
    known_facts = set(bible["initial_fact_ids"])
    evolving_states: dict[tuple[str, str], str] = {}
    promises: dict[str, dict[str, Any]] = {}
    accepted = []
    for ep, rel in state["episode_files"].items():
        try:
            path = safe_project_path(project, rel)
            data = load_json(path)
            result = check_episode(data)
            for item in result: item["path"] = f"{rel}:{item['path']}"
            out.extend(result)
            if has_errors(result): continue
            if data["episode_id"] != ep or data["project_id"] != pid:
                issue(out, "EPISODE_IDENTITY", rel, "Episode identity does not match project index")
            if data["status"] != "accepted": issue(out, "NOT_ACCEPTED", rel, "Draft cannot be listed as completed")
            if data["episode_number"] > brief["total_episodes"]:
                issue(out, "EPISODE_RANGE", rel, "Episode exceeds planned total")
            accepted.append((data["episode_number"], rel, data))
        except (OSError, ValueError) as exc:
            issue(out, "EPISODE_FILE", rel, str(exc))
    accepted.sort(key=lambda x: x[0])
    numbers = [x[0] for x in accepted]
    if numbers and numbers != list(range(1, max(numbers)+1)):
        issue(out, "NONCONTIGUOUS", "project-state", "Accepted episodes are not a contiguous prefix; verify omitted context", "warning")
    for _, rel, data in accepted:
        for kind in known_assets:
            for asset in data[kind]:
                if asset["id"] not in known_assets[kind]:
                    issue(out, "BIBLE_ASSET", rel, f"Asset not registered in bible: {asset['id']}")
        for rule in data["rules_used"]:
            if rule not in known_rules: issue(out, "BIBLE_RULE", rel, f"Rule not registered: {rule}")
        for fact in data["continuity"]["requires"]:
            if fact not in known_facts: issue(out, "FUTURE_OR_MISSING_FACT", rel, f"Required fact not established: {fact}")
        for fact in data["continuity"]["establishes"]:
            if fact["id"] in known_facts:
                issue(out, "FACT_REDEFINED", rel, f"Existing fact redefined: {fact['id']}")
            known_facts.add(fact["id"])
        for change in data["continuity"]["state_changes"]:
            key = (change["entity_id"], change["field"])
            if key in evolving_states and evolving_states[key] != change["before"]:
                issue(out, "STATE_DISCONTINUITY", rel, f"{key}: previous after != current before")
            evolving_states[key] = change["after"]
        for promise in data["continuity"]["promises"]:
            promises[promise["id"]] = promise
    last = max(numbers, default=0)
    state_promises = {p["id"]: p for p in state["promises"]}
    unique([p["id"] for p in state["promises"]], "project-state.promises", out)
    for key, promise in promises.items():
        if promise["status"] != "resolved" and promise["due_episode"] <= last:
            issue(out, "OVERDUE_PROMISE", "project-state.promises", f"{key} was due by episode {promise['due_episode']}", "warning")
        if key not in state_promises or state_promises[key] != promise:
            issue(out, "STALE_PROMISE_LEDGER", "project-state.promises", f"Ledger does not reflect latest {key}", "warning")
    for ep, rel in state["draft_episode_files"].items():
        try:
            if ep in state["episode_files"]:
                issue(out, "DRAFT_ACCEPTED_COLLISION", ep, "Same ID listed as both draft and accepted")
            if not safe_project_path(project, rel).is_file():
                issue(out, "DRAFT_FILE_MISSING", rel, "Registered draft file is missing")
        except ValueError as exc: issue(out, "DRAFT_FILE", rel, str(exc))
    if not accepted:
        issue(out, "NO_COMPLETED_EPISODES", "project-state", "Scaffold/plan only; no completed screenplay episodes", "warning")
    return out


def init_project(project: Path, title: str, episodes: int) -> dict[str, Any]:
    if episodes < 1: raise ValueError("episodes must be >= 1")
    if project.exists() and (not project.is_dir() or any(project.iterdir())):
        raise ValueError("Refusing to initialize a non-empty path; choose a new project directory")
    project.mkdir(parents=True, exist_ok=True)
    pid = re.sub(r"[^a-z0-9-]+", "-", project.name.lower()).strip("-") or "drama-project"
    for name in ("brief", "bible", "series-plan", "project-state"):
        data = deepcopy(load_json(ROOT / "assets" / "templates" / f"{name}.json"))
        data["project_id"] = pid
        if "total_episodes" in data: data["total_episodes"] = episodes
        if name == "brief":
            data["title"] = title
            data["delivery"]["full_episodes"] = min(data["delivery"]["full_episodes"], episodes)
        (project / f"{name}.json").write_text(json.dumps(data, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    for name in ("concepts", "episodes", "reviews", "handoff"): (project / name).mkdir()
    (project / "archive.jsonl").write_text("", encoding="utf-8")
    (project / "run-log.md").write_text("# Run log\n\nInitialized scaffold only; no screenplay generated.\n", encoding="utf-8")
    return {"status": "scaffold_created", "project": str(project.resolve()), "project_id": pid,
            "total_episodes": episodes, "completed_episodes": 0}


@contextmanager
def exclusive_lock(path: Path) -> Iterator[None]:
    lock = path.with_name(path.name + ".lock")
    try: fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise ValueError(f"Archive is locked: {lock}. Check for a running writer before removing a stale lock.") from exc
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream: stream.write(str(os.getpid()))
        yield
    finally:
        lock.unlink(missing_ok=True)


def archive_concepts(cards: list[dict[str, Any]], path: Path) -> dict[str, Any]:
    errors = check_concepts(cards)
    if has_errors(errors): raise ValueError(f"Concept validation failed: {errors[:3]}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with exclusive_lock(path):
        old = load_archive(path)
        existing = {c["id"] for c in old}
        duplicates = existing & {c["id"] for c in cards}
        if duplicates: raise ValueError(f"Refusing duplicate archive IDs: {sorted(duplicates)}")
        temporary: str | None = None
        try:
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent,
                                             prefix=path.name+".", suffix=".tmp", delete=False) as stream:
                temporary = stream.name
                for card in old + cards: stream.write(json.dumps(card, ensure_ascii=False, allow_nan=False)+"\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
            temporary = None
        finally:
            if temporary: Path(temporary).unlink(missing_ok=True)
    return {"status": "appended", "added": len(cards), "total": len(old)+len(cards), "archive": str(path.resolve())}


def report_issues(issues: list[Issue]) -> dict[str, Any]:
    return {"status": "fail" if has_errors(issues) else ("pass_with_warnings" if issues else "pass"),
            "errors": sum(i["severity"] == "error" for i in issues),
            "warnings": sum(i["severity"] == "warning" for i in issues), "issues": issues,
            "scope": "Structural/editorial-field checks only, not audience or originality validation."}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("init", help="Create empty project scaffold; never overwrite content")
    p.add_argument("--project", type=Path, required=True)
    p.add_argument("--title", required=True)
    p.add_argument("--episodes", type=int, default=24)
    p = sub.add_parser("check", help="Validate one episode JSON")
    p.add_argument("file", type=Path)
    p.add_argument("--cps", type=float, default=4, help="Estimated Chinese characters per second")
    p.add_argument("--wps", type=float, default=2.5, help="Estimated other-language words per second")
    p = sub.add_parser("check-reveal", help="Validate a reveal arc without interpreting prose credibility")
    p.add_argument("file", type=Path)
    p = sub.add_parser("check-project", help="Check a local project and its accepted episode index")
    p.add_argument("project", type=Path)
    p = sub.add_parser("compare", help="Heuristic near-duplicate reminder; no semantic or web search")
    p.add_argument("file", type=Path)
    p.add_argument("--archive", type=Path)
    p.add_argument("--threshold", type=float, default=.68)
    p = sub.add_parser("archive", help="Append validated cards to an explicit local archive")
    p.add_argument("file", type=Path)
    p.add_argument("--archive", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        code = 0
        if args.command == "init":
            result = init_project(args.project, args.title, args.episodes)
        elif args.command == "check":
            if not all(math.isfinite(v) and v > 0 for v in (args.cps, args.wps)):
                raise ValueError("--cps and --wps must be positive finite numbers")
            issues = check_episode(load_json(args.file), args.cps, args.wps)
            result = report_issues(issues); code = 1 if has_errors(issues) else 0
        elif args.command == "check-reveal":
            issues = check_reveal(load_json(args.file))
            result = report_issues(issues); code = 1 if has_errors(issues) else 0
        elif args.command == "check-project":
            issues = check_project(args.project)
            result = report_issues(issues); code = 1 if has_errors(issues) else 0
        else:
            cards = load_json(args.file)
            issues = check_concepts(cards)
            if has_errors(issues):
                result = report_issues(issues); code = 1
            elif args.command == "archive":
                result = archive_concepts(cards, args.archive)
            else:
                if not math.isfinite(args.threshold) or not 0 <= args.threshold <= 1:
                    raise ValueError("--threshold must be between 0 and 1")
                history = load_archive(args.archive) if args.archive else []
                result = compare_concepts(cards, history, args.threshold)
                if args.archive and not args.archive.exists():
                    result["archive_note"] = "Archive did not exist; only this batch was checked."
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        return code
    except (OSError, ValueError) as exc:
        print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
