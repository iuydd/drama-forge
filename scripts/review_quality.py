#!/usr/bin/env python3
"""Pure review contracts: speech differences, take-bound evidence and cut eligibility.

No generation calls. Machine measurements never create visual/listening approval.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from difflib import SequenceMatcher
from pathlib import Path

from common import norm

CHECKS = ("visual", "audio", "continuity")
EDIT_KEYS = ("in", "out", "mode", "speed")


def media_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def shot_digest(shot: dict) -> str:
    return hashlib.sha256(json.dumps(shot, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


def speech_diff(expected: str, heard: str, readings: dict | None = None,
                critical_terms: list[str] | None = None) -> dict:
    """Report both missing and additional content, never infer correctness from similarity."""
    def canonical(text):
        for source, target in sorted((readings or {}).items(), key=lambda x: -len(x[0])):
            text = text.replace(source, target)
        return norm(text).casefold()
    want, got = canonical(expected), canonical(heard)
    matcher = SequenceMatcher(None, want, got, autojunk=False)
    edits = [{"operation": op, "expected": want[a:b], "heard": got[c:d],
              "expected_span": [a, b], "heard_span": [c, d]}
             for op, a, b, c, d in matcher.get_opcodes() if op != "equal"]
    hits = sum(block.size for block in matcher.get_matching_blocks())
    recall = hits / len(want) if want else (1.0 if not got else 0.0)
    precision = hits / len(got) if got else (1.0 if not want else 0.0)
    # Critical markers prioritise listening; ANY textual difference still requires listening.
    markers = set(critical_terms or []) | set(re.findall(r"\d+(?:[.,]\d+)*|[一二三四五六七八九十百千万亿]+", expected + heard))
    markers.update(("不", "没", "未", "无", "别", "ない", "ません"))
    changed = sorted(term for term in markers if canonical(term) and want.count(canonical(term)) != got.count(canonical(term)))
    for token in ("no", "not", "never", "without", "cannot"):
        if len(re.findall(rf"\b{token}\b", expected, re.I)) != len(re.findall(rf"\b{token}\b", heard, re.I)):
            changed.append(token)
    # 语种疑似不符：台词有假名，ASR 却一个假名都没有（整句被识别成中文/别的语言 = 口音严重不像母语者）
    kana = re.compile(r"[\u3040-\u30ff]")
    if kana.search(expected) and heard and not kana.search(heard):
        changed.append("语种疑似不符")
    return {"status": "exact" if want == got else "needs_listening", "edits": edits,
            "critical_changes": changed, "recall": round(recall, 4), "precision": round(precision, 4),
            "similarity": round(2 * hits / (len(want) + len(got)), 4) if want or got else 1.0}


def valid_window(value) -> bool:
    return (isinstance(value, (list, tuple)) and len(value) == 2
            and all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in value)
            and 0 <= value[0] < value[1])


def action_required(shot: dict) -> bool:
    # Legacy shot-level action_window is a PLAN only; it never supplies actual timing.
    return bool(shot.get("action_required") or shot.get("planned_action_window") or shot.get("action_window"))


def take_quality(path: Path, shot: dict, rec: dict, *, audio_only: bool = False) -> list[str]:
    assessment = rec.get("assessment") or {}
    if not path.is_file():
        return ["missing_media"]
    if assessment.get("media_sha256") != media_digest(path) or assessment.get("shot_sha256") != shot_digest(shot):
        return ["missing_or_stale_review"]
    problems = []
    for key in (("audio",) if audio_only else CHECKS):
        if (assessment.get("checks") or {}).get(key) != "pass":
            problems.append(f"{key}_not_passed")
    if not str(assessment.get("evidence") or "").strip():
        problems.append("missing_evidence")
    if (audio_only or (shot.get("dialogue") and not shot.get("audio_from"))) and not valid_window(assessment.get("speech_window")):
        problems.append("missing_verified_speech_window")
    if not audio_only and action_required(shot) and not valid_window(assessment.get("action_window")):
        problems.append("missing_verified_action_window")
    return problems


def verified_action(rec: dict):
    value = (rec.get("assessment") or {}).get("action_window")
    return (float(value[0]), float(value[1]), "reviewed_take") if valid_window(value) else None


def cut_issues(project, ep: str, data: dict, review: dict) -> list[str]:
    """Preflight the entire final cut before decoding or writing outputs."""
    shots = {sh["id"]: sh for sh in data.get("shots") or []}
    order = data.get("cut_order") if data.get("cut_order") is not None else list(shots)
    problems = []
    if not order or len(order) != len(set(order)):
        problems.append("cut_order is empty or duplicated")
    audio_sources = {item.get("shot") for sid in order if sid in shots for item in shots[sid].get("audio_from") or []}
    for sid in set(shots) - set(order) - audio_sources:
        omission = (review.get("shots") or {}).get(sid) or {}
        if omission.get("verdict") != "drop" or not omission.get("note"):
            problems.append(f"{sid}: omitted shot requires explicit drop and reason")
    for sid in order:
        if sid not in shots:
            problems.append(f"{sid}: unknown shot")
            continue
        sh = shots[sid]
        entry = (review.get("shots") or {}).get(sid) or {}
        if entry.get("verdict") == "drop":
            if not entry.get("note"):
                problems.append(f"{sid}: drop requires a reason")
            continue
        if entry.get("verdict") not in ("ok", "weak", "mute"):
            problems.append(f"{sid}: {entry.get('verdict') or 'pending_review'}")
        take = entry.get("video_take")
        if not isinstance(take, int) or take < 1:
            problems.append(f"{sid}: no explicitly selected take")
            continue
        rec = (entry.get("video_takes") or {}).get(str(take)) or {}
        problems.extend(f"{sid}/t{take}: {problem}" for problem in take_quality(project.video_path(ep, sid, take), sh, rec))
        assessment = rec.get("assessment") or {}
        if rec.get("verdict") != entry.get("verdict"):
            problems.append(f"{sid}: verdict is not bound to selected take")
        if entry.get("verdict") == "weak" and not assessment.get("acceptance_reason"):
            problems.append(f"{sid}: weak needs explicit acceptance of noncritical defect")
        edit = rec.get("edit") or {}
        if not math.isfinite(float(edit.get("speed") or 1.0)) or not 0.5 <= float(edit.get("speed") or 1.0) <= 2:
            problems.append(f"{sid}: invalid speed")
        if float(edit.get("speed") or 1.0) != float(assessment.get("speed") or 1.0):
            problems.append(f"{sid}: changed speed needs listening review")
        if edit.get("mode") == "action" and not verified_action(rec):
            problems.append(f"{sid}: action mode needs verified timing")
        if entry.get("verdict") == "mute" and sh.get("dialogue") and not sh.get("audio_from"):
            problems.append(f"{sid}: cannot mute required dialogue without reviewed replacement audio")
        for binding in sh.get("audio_from") or []:
            source = binding.get("shot")
            other = (review.get("shots") or {}).get(source) or {}
            audio_take = other.get("video_take")
            if source not in shots or not isinstance(audio_take, int):
                problems.append(f"{sid}: missing audio source {source}")
                continue
            other_rec = (other.get("video_takes") or {}).get(str(audio_take)) or {}
            problems.extend(f"{sid} audio {source}/t{audio_take}: {problem}"
                            for problem in take_quality(project.video_path(ep, source, audio_take), shots[source], other_rec, audio_only=True))
    return problems


def protect_interval(start: float, end: float, duration: float, action=None, speech=None) -> tuple[float, float]:
    """Preserve verified source intervals irrespective of trim mode; never reuse another take."""
    for window in (action[:2] if action else None, speech):
        if window is None:
            continue
        if not valid_window(window) or window[1] > duration + 0.001:
            raise ValueError("verified action/speech window falls outside selected media")
        start = min(start, window[0])
        end = max(end, min(duration, window[1] + 0.2))
    start, end = max(0.0, start), min(duration, end)
    if not all(math.isfinite(v) for v in (start, end, duration)) or end <= start:
        raise ValueError("invalid cut interval")
    return start, end
