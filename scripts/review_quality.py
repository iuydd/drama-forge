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
AUDIO_KEYS = ("asr_ok", "listen_ok", "sync_ok")
MUST_SHOW_VALUES = ("pass", "fail", "unverified")


def audio_status(assessment: dict | None) -> dict:
    """声音结论三分项：asr_ok（识别正确）、listen_ok（听感自然）、sync_ok（口型/音画同步）；None = 未验证。
    旧字段兼容：只有 checks.audio 时，pass 只算 asr_ok=True（旧 audio pass 实际只是 ASR 通过），fail 算 asr_ok=False；
    listen_ok / sync_ok 没有人工写入就是 None，绝不从旧字段推成通过。"""
    a = assessment or {}
    legacy = (a.get("checks") or {}).get("audio")
    out = {"asr_ok": {"pass": True, "fail": False}.get(legacy), "listen_ok": None, "sync_ok": None}
    for key in AUDIO_KEYS:
        if a.get(key) is not None:
            out[key] = bool(a[key])
    return out


def fmt_audio(status: dict) -> str:
    """null 如实显示为「未验证」，不汇总成「通过」。"""
    names = {"asr_ok": "识别", "listen_ok": "听审", "sync_ok": "同步"}
    val = {True: "通过", False: "不过", None: "未验证"}
    return "；".join(f"{names[k]} {val[status.get(k)]}" for k in AUDIO_KEYS)


def must_show_facts(data: dict) -> list[dict]:
    """shots.json scenes[].must_show 的事实，附上承担镜：fact.shots 与写了 must_show_ids 的镜取并集。"""
    carriers: dict[str, list[str]] = {}
    for sh in data.get("shots") or []:
        for mid in sh.get("must_show_ids") or []:
            carriers.setdefault(mid, []).append(sh["id"])
    out = []
    for sc in data.get("scenes") or []:
        for fact in sc.get("must_show") or []:
            if not isinstance(fact, dict) or not fact.get("id"):
                continue
            shots = list(dict.fromkeys(list(fact.get("shots") or []) + carriers.get(fact["id"], [])))
            out.append({"id": fact["id"], "fact": fact.get("fact", ""), "kind": fact.get("kind"), "scene": sc.get("id"), "shots": shots})
    return out


def must_show_coverage(data: dict, cut_ids: list[str]) -> list[dict]:
    """每条必须拍清楚的事实，哪些承担镜还在片里。承担镜全被删 = 因果证据被删掉了。"""
    kept = set(cut_ids)
    return [{**f, "in_cut": [s for s in f["shots"] if s in kept]} for f in must_show_facts(data)]


def must_show_state(entry: dict, take) -> dict:
    """某个 take 的 must_show_check：优先 video_takes[n].must_show_check；否则镜级 must_show_check（仅当它属于这个 take）。"""
    rec = (entry.get("video_takes") or {}).get(str(take)) or {}
    if isinstance(rec.get("must_show_check"), dict):
        return dict(rec["must_show_check"])
    if isinstance(entry.get("must_show_check"), dict) and entry.get("video_take") in (take, None):
        return dict(entry["must_show_check"])
    return {}


def must_show_failed(entry: dict, take) -> list[str]:
    return sorted(k for k, v in must_show_state(entry, take).items() if v == "fail")


def media_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def shot_digest(shot: dict) -> str:
    return hashlib.sha256(json.dumps(shot, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


ANIMATIC_KEYS = ("scene", "kind", "subject", "seconds", "dialogue", "keyframe", "frame_prompt", "video_prompt", "video_body", "motion",
                 "end_state", "must_show_ids", "audio_from", "planned_action_window", "action_window", "reaction_first",
                 "explains_ability", "frame_refs", "frame_parent")


def animatic_inputs_fp(project, ep: str, review: dict | None = None) -> str:
    """预演输入指纹：cut_order + 每镜影响预演的字段 + must_show 事实 + 所选起始帧 take 与文件 sha。
    只看输入、不依赖 TTS 时长，放行时可以便宜地重算（common.Project.animatic_problems）。"""
    data = project.load_shots(ep)
    shots = data.get("shots") or []
    by = {s["id"]: s for s in shots}
    order = data.get("cut_order") if data.get("cut_order") is not None else [s["id"] for s in shots]
    review = review if review is not None else project.load_review(ep)
    rows = []
    for sid in order:
        sh = by.get(sid) or {}
        t = project.chosen_take(ep, sid, "frame", review)
        p = project.frame_path(ep, sid, t) if t else None
        rows.append([sid, {k: sh.get(k) for k in ANIMATIC_KEYS}, t, media_digest(p) if p and p.is_file() else None])
    facts = [f for sc in data.get("scenes") or [] for f in sc.get("must_show") or []]
    return hashlib.sha256(json.dumps([rows, facts], ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]


def text_digest(text: str) -> str:
    return hashlib.sha256(text.strip().encode()).hexdigest()


def ledger(project) -> list[dict]:
    p = project.scripts_dir / "jobs.jsonl"
    out = []
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def provenance_issues(project, ep: str, sid: str, take: int, shot: dict, review: dict | None = None, jobs: list | None = None) -> list[str]:
    """视频 take 的来源：账本里要有收回它的 collected 记录（新记录带 sha256，须等于当前文件）；对应 submitted 记录的
    提示词哈希须等于当前 video_prompt、起始帧 sha（新记录才有）须等于当前所选起始帧。旧账本缺字段的项不报，不卡历史项目。"""
    path = project.video_path(ep, sid, take)
    if not path.is_file():
        return []
    jobs = ledger(project) if jobs is None else jobs
    # 按「EPxxx/视频/V_…mp4」尾部比对，纯字符串：项目搬过机器（账本里是旧绝对路径）也对得上，且不对账本路径做文件系统调用
    # （/home/... 这类路径在 macOS 上会触发 autofs，逐条 resolve 会卡住）
    want = Path(path).parts[-3:]
    col = [r for r in jobs if r.get("status") == "collected" and r.get("out") and Path(str(r["out"])).parts[-3:] == want]
    if not col:
        return ["no_ledger_provenance（账本 脚本/jobs.jsonl 里没有收回这个文件的记录：不是本流水线生成的，可能是从别的镜/别的 take 复制来的）"]
    rec = col[-1]
    out = []
    if rec.get("sha256") and rec["sha256"] != media_digest(path):
        out.append("media_changed_since_collect（文件在收回后被替换过）")
    sub = next((r for r in reversed(jobs) if r.get("status") == "submitted" and r.get("job") == rec.get("job")), None)
    if sub:
        cur = text_digest(shot.get("video_prompt") or "")
        if sub.get("source_prompt_sha256"):
            if sub["source_prompt_sha256"] != cur:
                out.append("stale_prompt（生成后 video_prompt 改过：重拍，不能只重新 mark）")
        elif sub.get("prompt_sha256") and not sub.get("provider") and len(str(sub["prompt_sha256"])) == 16 and sub["prompt_sha256"] != cur[:16]:
            out.append("stale_prompt（生成后 video_prompt 改过：重拍，不能只重新 mark）")
        if sub.get("frame_sha256"):
            ft = project.chosen_take(ep, sid, "frame", review)
            fp = project.frame_path(ep, sid, ft) if ft else None
            if not fp or not fp.is_file() or media_digest(fp) != sub["frame_sha256"]:
                out.append("stale_frame（生成这条视频用的起始帧不是当前所选起始帧：换帧后要重拍）")
    return out


def carried_must_show(data: dict, sid: str) -> list[str]:
    return [f["id"] for f in must_show_facts(data) if sid in f["shots"]]


def must_show_approval_issues(data: dict, sid: str, entry: dict, take, verdict) -> list[str]:
    """ok/weak 的前提：本镜承担的每条 must_show 在这个 take 上核成 pass（unverified、缺项都按没核）；承担镜不许 weak。"""
    if verdict not in ("ok", "weak"):
        return []
    carried = carried_must_show(data, sid)
    state = must_show_state(entry, take)
    out = []
    todo = [m for m in carried if state.get(m) != "pass"]
    if todo:
        out.append(f"must_show_unverified {','.join(todo)}（承担镜要逐条核成 pass：mark --must-show {todo[0]}=pass|fail，unverified 在正式剪辑里等同 fail）")
    if verdict == "weak" and carried:
        out.append(f"weak_on_must_show_carrier（本镜承担 {','.join(carried)}，不能 weak：retake、改分镜或回剧本）")
    return out


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


def spoken(shot: dict) -> list[dict]:
    """镜内要开口的台词（vo:true 画外/心声不在本镜音轨里，audio_from 的镜用别镜声音）。"""
    return [] if shot.get("audio_from") else [d for d in shot.get("dialogue") or [] if d.get("text") and not d.get("vo")]


def asr_currency_issues(path: Path, shot: dict, rec: dict) -> list[str]:
    """asr_ok=true 的前提：这个文件、这版镜头跑过 ASR（review_tool.py asr），且没判出语种疑似不符。"""
    if not spoken(shot):
        return []
    if rec.get("asr_media_sha256") != media_digest(path) or rec.get("asr_shot_sha256") != shot_digest(shot):
        return ["asr_not_run_on_current_take（asr_ok=true 但当前文件/当前镜头没跑过 ASR：python3 scripts/review_tool.py asr <项目> <EP> <SID>）"]
    if "语种疑似不符" in ((rec.get("speech_diff") or {}).get("critical_changes") or []):
        return ["asr_language_mismatch（ASR 判语种疑似不符：口音不像母语者，不合格，重拍）"]
    return []


def take_quality(path: Path, shot: dict, rec: dict, *, audio_only: bool = False) -> list[str]:
    assessment = rec.get("assessment") or {}
    if not path.is_file():
        return ["missing_media"]
    if assessment.get("media_sha256") != media_digest(path) or assessment.get("shot_sha256") != shot_digest(shot):
        return ["missing_or_stale_review"]
    problems = []
    audio = audio_status(assessment)
    for key in (("audio",) if audio_only else CHECKS):
        if key == "audio":
            if audio["asr_ok"] is not True:
                problems.append("audio_not_passed")
            else:
                problems.extend(asr_currency_issues(path, shot, rec))
            if audio["listen_ok"] is False:
                problems.append("listen_failed")
            if audio["sync_ok"] is False:
                problems.append("sync_failed")
        elif (assessment.get("checks") or {}).get(key) != "pass":
            problems.append(f"{key}_not_passed")
    if not audio_only and spoken(shot) and assessment.get("speaker_face_ok") is not True:
        # 纯视觉：本句说话人的嘴在动、其他人嘴不动（口型落错人是生成模型常见的"合字面最差成品"）
        problems.append("speaker_face_not_verified（有台词的镜要看过是说话人本人在张嘴、别人闭嘴：mark --speaker-face-ok true --evidence …）"
                        if assessment.get("speaker_face_ok") is None else "speaker_face_failed（口型落在别人脸上或多人同时张嘴：重拍）")
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
    jobs = ledger(project)
    if not order or len(order) != len(set(order)):
        problems.append("cut_order is empty or duplicated")
    audio_sources = {item.get("shot") for sid in order if sid in shots for item in shots[sid].get("audio_from") or []}
    kept = [sid for sid in order if sid in shots and ((review.get("shots") or {}).get(sid) or {}).get("verdict") != "drop"]
    for fact in must_show_coverage(data, kept):
        if fact["shots"] and not fact["in_cut"]:
            problems.append(f"{fact['id']}: 必须拍清楚的事实「{fact['fact']}」的承担镜 {','.join(fact['shots'])} 全部被删，因果证据丢了")
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
        problems.extend(f"{sid}/t{take}: {p}" for p in provenance_issues(project, ep, sid, take, sh, review, jobs))
        failed_ms = must_show_failed(entry, take)
        if failed_ms:
            problems.append(f"{sid}: must_show fail {','.join(failed_ms)}（必须拍清楚的事实没拍出来：retake 或回剧本/分镜改，不能靠台词或延长镜头补）")
        problems.extend(f"{sid}: {p}" for p in must_show_approval_issues(data, sid, entry, take, entry.get("verdict")))
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
