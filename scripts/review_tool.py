#!/usr/bin/env python3
"""审片：接触表、ASR 比对、自动选 take、记录取用区间。只读素材，不提交任何生成任务。

  review_tool.py sheets <项目> <EP> [SID ...]          每个 take 一张 2fps 接触表 审查/<EP>-sheets/<sid>_t<n>.jpg
  review_tool.py asr    <项目> <EP> [SID ...]          全部 take 跑 ASR，比对台词，结果写 审查/<EP>-asr.json 和 review.json
  review_tool.py motion <项目> <EP> [SID ...]          全部 take 算运动能量（8fps、160px 灰度帧差，每 0.25s 一格），写 review.json 的
                                                       video_takes[n].motion / action_peak / action_start / action_end / cuts（镜内跳切）
  review_tool.py animatic <项目> <EP>                 阶段 G2 静帧预演：按镜序把通过的起始帧各放 seconds 秒，拼 审查/<EP>-预演.mp4
                                                       和 1fps 接触表 审查/<EP>-预演.jpg；模型看完写 审查/<EP>-预演.md（production-and-review §3b）
  review_tool.py auto   <项目> <EP>                    按规则自动选 take、给 verdict（不改已由人/模型 mark 过的镜）
  review_tool.py report <项目> <EP>                    汇总 审查/<EP>-审片.md
  review_tool.py mark   <项目> <EP> <SID> [--video-take N] [--frame-take N] [--in S] [--out S]
                        [--mode after_last_word|to_end|fixed|full|action] [--verdict ok|weak|retake|drop|mute] [--speed X] [--note ...]

ASR 用 faster-whisper：优先环境变量 ASR_PY 指向装了它的 python；否则依次试当前 python 和 ~/.venvs/*/bin/python。
模型 ASR_MODEL（默认 medium），语言取 drama.json 的 dialogue_lang。词级时间戳缓存在 脚本/asr_cache.json。
"""
from __future__ import annotations

import argparse
import time
import json
import math
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import Project, ffprobe_duration, norm  # noqa: E402
from review_quality import (CHECKS, EDIT_KEYS, media_digest, shot_digest, speech_diff,
                            take_quality, valid_window)

ASR_CODE = (
    "import sys,json\n"
    "from faster_whisper import WhisperModel\n"
    "m=WhisperModel(sys.argv[1],device='cpu',compute_type='int8')\n"
    "for f in sys.argv[3:]:\n"
    " s,_=m.transcribe(f,language=sys.argv[2],word_timestamps=True,vad_filter=True)\n"
    " print(json.dumps([f,[(round(w.start,2),round(w.end,2),w.word) for x in s for w in x.words]],ensure_ascii=False))\n"
)


def asr_python() -> str | None:
    import glob
    cands = [os.environ.get("ASR_PY"), sys.executable] + sorted(glob.glob(str(Path.home() / ".venvs/*/bin/python")))
    for c in cands:
        if not c or not Path(c).exists():
            continue
        r = subprocess.run([c, "-c", "import faster_whisper"], capture_output=True)
        if r.returncode == 0:
            return c
    return None


def lcs_ratio(want: str, got: str) -> float:
    if not want:
        return 1.0
    if not got:
        return 0.0
    prev = [0] * (len(got) + 1)
    for a in want:
        cur = [0]
        for j, b in enumerate(got, 1):
            cur.append(prev[j - 1] + 1 if a == b else max(prev[j], cur[j - 1]))
        prev = cur
    return prev[-1] / len(want)


class ASR:
    def __init__(self, project: Project):
        self.project = project
        self.cache_path = project.scripts_dir / "asr_cache.json"
        self.cache = json.loads(self.cache_path.read_text(encoding="utf-8")) if self.cache_path.exists() else {}
        self.py = asr_python()
        self.lang = project.get("dialogue_lang")
        self.model = os.environ.get("ASR_MODEL", "medium")

    def key(self, path: Path) -> str:
        return f"{path.resolve()}:{media_digest(path)}:{self.model}:{self.lang}"

    def words(self, paths: list[Path]) -> dict[str, list]:
        todo = [p for p in paths if self.key(p) not in self.cache]
        if todo:
            if not self.py:
                raise SystemExit("没有可用的 faster-whisper 环境；设 ASR_PY 指向装了它的 python")
            r = subprocess.run([self.py, "-c", ASR_CODE, self.model, self.lang, *map(str, todo)], capture_output=True, text=True)
            if r.returncode != 0:
                raise RuntimeError("ASR process failed; do not treat it as silence")
            received = set()
            for row in r.stdout.splitlines():
                try:
                    f, ws = json.loads(row)
                except json.JSONDecodeError:
                    continue
                if f not in {str(p) for p in todo} or not isinstance(ws, list):
                    continue
                self.cache[self.key(Path(f))] = ws
                received.add(f)
            if received != {str(p) for p in todo}:
                raise RuntimeError("ASR output incomplete; affected clips need listening review")
            self.project.scripts_dir.mkdir(parents=True, exist_ok=True)
            self.cache_path.write_text(json.dumps(self.cache, ensure_ascii=False), encoding="utf-8")
        return {str(p): self.cache.get(self.key(p), []) for p in paths}


def _expected(sh: dict) -> str:
    return "".join(d.get("text", "") for d in sh.get("dialogue") or [])


def asr_shot(project: Project, ep: str, sh: dict, take: int) -> dict:
    """单个 take 的 ASR 记录，写进 review.json 的 shots[sid].video_takes[str(take)]。"""
    sid = sh["id"]
    path = project.video_path(ep, sid, take)
    ws = ASR(project).words([path])[str(path)]
    heard = "".join(w for _, _, w in ws).replace(" ", "")
    want = _expected(sh)
    rec = {"take": take, "duration": ffprobe_duration(path), "words": ws, "heard": heard,
           "silent_expected": not bool(want), "first_word": ws[0][0] if ws else None, "last_word_end": ws[-1][1] if ws else None}
    # 读音表：drama.json readings + 每句 dialogue[].reading（专名/易错汉字 → 假名/拼音）；有读音的词都算关键词，读错就要重点听
    line_readings = {k: v for d in sh.get("dialogue") or [] if isinstance(d.get("reading"), dict) for k, v in d["reading"].items()}
    readings = {**(project.get("readings") or {}), **line_readings}
    rec["speech_diff"] = speech_diff(want, heard, readings,
                                     list(sh.get("critical_terms") or []) + sorted(line_readings))
    rec["hit"] = rec["speech_diff"]["similarity"] if want else None
    rec["stray_voice"] = bool(heard) and not bool(want)
    rec["asr_media_sha256"] = media_digest(path)
    rec["asr_shot_sha256"] = shot_digest(sh)
    review = project.load_review(ep)
    entry = review.setdefault("shots", {}).setdefault(sid, {})
    entry.setdefault("video_takes", {}).setdefault(str(take), {}).update(rec)  # 保留 motion 等其他字段
    project.save_review(ep, review)
    return rec


def choose_best(project: Project, ep: str, sid: str, review: dict | None = None, save: bool = True) -> int | None:
    """Prefer reviewed usable takes; similarity only ranks candidates still awaiting review."""
    own = review is None
    review = project.load_review(ep) if own else review
    entry = review.setdefault("shots", {}).setdefault(sid, {})
    sh = next(sh for sh in project.load_shots(ep)["shots"] if sh["id"] == sid)
    existing = project.takes(ep, sid, "video")
    if not existing:
        return None
    ranked = []
    for take in existing:
        rec = (entry.get("video_takes") or {}).get(str(take)) or {}
        path = project.video_path(ep, sid, take)
        issues = take_quality(path, sh, rec)
        current = "missing_or_stale_review" not in issues and "missing_media" not in issues
        failed = current and any(value == "fail" for value in (rec.get("assessment", {}).get("checks") or {}).values())
        approved = not issues and rec.get("verdict") in ("ok", "weak", "mute")
        score = (rec.get("speech_diff") or {}).get("similarity", 0.0)
        if rec.get("asr_media_sha256") != media_digest(path) or rec.get("asr_shot_sha256") != shot_digest(sh):
            score = 0.0
        ranked.append(((2 if approved else 0 if failed else 1,
                        1 if approved and rec.get("verdict") == "ok" else 0, score), take))
        if entry.get("locked") and entry.get("video_take") == take and approved:
            return take
    best = max(ranked, key=lambda item: item[0])[1]
    if entry.get("video_take") != best:
        for key in EDIT_KEYS:
            entry.pop(key, None)
        entry["locked"] = False
    entry["video_take"] = best
    if save and own:
        project.save_review(ep, review)
    return best


def sheets(project: Project, ep: str, sids: list[str] | None = None) -> list[Path]:
    data = project.load_shots(ep)
    out_dir = project.sheets_dir(ep)
    out_dir.mkdir(parents=True, exist_ok=True)
    made = []
    for sh in data.get("shots") or []:
        sid = sh["id"]
        if sids and sid not in sids:
            continue
        for t in project.takes(ep, sid, "video"):
            v = project.video_path(ep, sid, t)
            dur = ffprobe_duration(v)
            n = max(1, math.ceil(dur * 2))
            cols = 5
            rows = max(1, math.ceil(n / cols))
            out = out_dir / f"{sid}_t{t}.jpg"
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(v), "-vf", f"fps=2,scale=448:-1,tile={cols}x{rows}",
                            "-frames:v", "1", str(out)], check=False)
            if out.exists():
                made.append(out)
    return made


def animatic(project: Project, ep: str) -> tuple[Path, Path, list[str]]:
    """静帧预演：每镜通过的起始帧先 -loop 1 -t 出一段（PNG 直接 concat 的 duration 行时长会错），再 concat。
    Follow the explicit narrative cut_order; missing frames are reported."""
    import tempfile
    data = project.load_shots(ep)
    shots = data.get("shots") or []
    order = data.get("cut_order") if data.get("cut_order") is not None else [s["id"] for s in shots]
    by_id = {s["id"]: s for s in shots}
    if len(order) != len(set(order)) or any(sid not in by_id for sid in order):
        raise ValueError("invalid cut_order for animatic")
    ordered_shots = [by_id[sid] for sid in order]
    review = project.load_review(ep)
    out_dir = project.review_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    mp4, jpg = out_dir / f"{ep}-预演.mp4", out_dir / f"{ep}-预演.jpg"
    missing, total = [], 0.0
    with tempfile.TemporaryDirectory() as td:
        lst = Path(td) / "list.txt"
        lines = []
        for sh in ordered_shots:
            sid = sh["id"]
            ft = project.chosen_take(ep, sid, "frame", review)
            if not ft:
                missing.append(sid)
                continue
            sec = float(sh.get("seconds") or 5)
            seg = Path(td) / f"{len(lines):03d}.mp4"
            subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-loop", "1", "-t", f"{sec:.2f}", "-i", str(project.frame_path(ep, sid, ft)),
                            "-vf", "scale=1280:-2,fps=25,format=yuv420p", "-c:v", "libx264", str(seg)], check=True)
            lines.append(f"file '{seg.name}'")
            total += sec
        if not lines:
            raise SystemExit(f"{ep} 没有任何起始帧，先跑 produce.py frames")
        lst.write_text("\n".join(lines) + "\n", encoding="utf-8")
        subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(mp4)], check=True)
    n = max(1, math.ceil(total))
    cols = 6
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(mp4), "-vf", f"fps=1,scale=320:-1,tile={cols}x{max(1, math.ceil(n / cols))}",
                    "-frames:v", "1", str(jpg)], check=False)
    return mp4, jpg, missing


MOTION_FPS, MOTION_W, MOTION_H, MOTION_CELL = 8, 160, 90, 0.25


def motion_curve(path: Path, fps: int = MOTION_FPS, cell: float = MOTION_CELL) -> dict:
    """低分辨率灰度帧逐帧差分 → 每 cell 秒一格的运动能量（0–255 灰度的平均绝对差）。
    单帧尖峰（前后帧都低）当作镜内跳切记进 cuts，不计入能量。底 = 第 20 百分位（静止时的呼吸/噪声水平）；
    峰 = 最高格；阈值 = 底 + 0.35×(峰 − 底)；action_start/action_end = 峰所在的连续超阈值段的起止（action_end 即峰后回落到阈值的时刻）。
    峰不明显（< 2.5×底 或 比底只高不到 0.8）时 action_start/action_end 为 None。"""
    w, h = MOTION_W, MOTION_H
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-vf", f"fps={fps},scale={w}:{h},format=gray",
                          "-f", "rawvideo", "-"], capture_output=True).stdout
    n = w * h
    frames = [raw[i:i + n] for i in range(0, len(raw) - n + 1, n)]
    d = [sum(abs(a - b) for a, b in zip(frames[k], frames[k - 1])) / n for k in range(1, len(frames))]
    cuts = []
    for k in range(len(d)):
        nb = [d[j] for j in (k - 1, k + 1) if 0 <= j < len(d)]
        if nb and d[k] > 20 and d[k] > 3 * max(nb):
            cuts.append(round((k + 1) / fps, 2))
            d[k] = sum(nb) / len(nb)
    dur = ffprobe_duration(path) or len(frames) / fps
    cells = [[] for _ in range(max(1, math.ceil(dur / cell)))]
    for k, v in enumerate(d):
        cells[min(len(cells) - 1, int((k + 0.5) / fps / cell))].append(v)  # 帧差 k 落在第 k、k+1 帧的中点
    curve = [round(sum(c) / len(c), 2) if c else None for c in cells]
    for j, v in enumerate(curve):  # 空格（fps 低于格密度时）取前一格
        if v is None:
            curve[j] = curve[j - 1] if j else 0.0
    rec = {"motion": curve, "motion_cell": cell, "cuts": cuts, "action_peak": None, "action_start": None, "action_end": None}
    if not curve:
        return rec
    base = sorted(curve)[len(curve) // 5]
    pk = max(range(len(curve)), key=lambda j: curve[j])
    rec["action_peak"] = round((pk + 0.5) * cell, 2)
    if curve[pk] < 2.5 * base or curve[pk] - base < 0.8:
        return rec
    thr = base + 0.35 * (curve[pk] - base)
    s = e = pk
    while s > 0 and curve[s - 1] >= thr:
        s -= 1
    while e + 1 < len(curve) and curve[e + 1] >= thr:
        e += 1
    rec["action_start"], rec["action_end"] = round(s * cell, 2), round(min(dur, (e + 1) * cell), 2)
    return rec


def motion_all(project: Project, ep: str, sids: list[str] | None = None) -> dict:
    """每个 take 的运动能量写进 review.json 的 video_takes[n]；按 文件名:mtime 缓存在 脚本/motion_cache.json。"""
    data = project.load_shots(ep)
    cache_path = project.scripts_dir / "motion_cache.json"
    cache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
    review = project.load_review(ep)
    results = {}
    for sh in data.get("shots") or []:
        sid = sh["id"]
        if sids and sid not in sids:
            continue
        for t in project.takes(ep, sid, "video"):
            p = project.video_path(ep, sid, t)
            key = f"{p.name}:{p.stat().st_mtime_ns}:{MOTION_FPS}:{MOTION_W}:{MOTION_CELL}"
            if key not in cache:
                cache[key] = motion_curve(p)
            rec = cache[key]
            review.setdefault("shots", {}).setdefault(sid, {}).setdefault("video_takes", {}).setdefault(str(t), {"take": t}).update(rec)
            results[f"{sid}_t{t}"] = rec
    project.scripts_dir.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    project.save_review(ep, review)
    return results


def asr_all(project: Project, ep: str, sids: list[str] | None = None) -> dict:
    data = project.load_shots(ep)
    results = {}
    for sh in data.get("shots") or []:
        sid = sh["id"]
        if sids and sid not in sids:
            continue
        for t in project.takes(ep, sid, "video"):
            results[f"{sid}_t{t}"] = asr_shot(project, ep, sh, t)
    project.review_dir.mkdir(parents=True, exist_ok=True)
    (project.review_dir / f"{ep}-asr.json").write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    return results


def auto(project: Project, ep: str) -> dict:
    """Measurements create pending_review; only current evidence can retain approval."""
    review = project.load_review(ep)
    for sh in project.load_shots(ep).get("shots") or []:
        sid = sh["id"]
        entry = review.setdefault("shots", {}).setdefault(sid, {})
        if entry.get("verdict") == "drop" and entry.get("note"):
            continue
        best = choose_best(project, ep, sid, review, save=False)
        if best is None:
            entry["verdict"] = "missing"
            continue
        rec = (entry.get("video_takes") or {}).get(str(best)) or {}
        issues = take_quality(project.video_path(ep, sid, best), sh, rec)
        if not issues and rec.get("verdict") in ("ok", "weak", "mute"):
            entry["verdict"] = rec["verdict"]
        else:
            entry["verdict"] = "pending_review"
            entry["locked"] = False
        entry["review_issues"] = issues
    project.save_review(ep, review)
    return review


def report(project: Project, ep: str) -> Path:
    data = project.load_shots(ep)
    review = project.load_review(ep)
    L = [f"# {ep} 审片", "", "| 镜 | 标题 | take | 时长 | ASR 命中 | 听到 | 结论 | 取用 | 备注 |", "|---|---|---|---|---|---|---|---|---|"]
    for sh in data.get("shots") or []:
        sid = sh["id"]
        e = (review.get("shots") or {}).get(sid) or {}
        t = e.get("video_take")
        rec = (e.get("video_takes") or {}).get(str(t)) or {}
        hit = "-" if rec.get("hit") is None else f"{rec['hit']:.0%}"
        heard = rec.get("heard", "")
        if rec.get("stray_voice"):
            heard = "⚠ 无台词镜有人声：" + heard
        edit = rec.get("edit") or {}
        rng = f"{edit.get('in', 0)}–{edit.get('out') if edit.get('out') is not None else 'auto'}（{edit.get('mode', 'auto')}）"
        diff = rec.get("speech_diff") or {}
        if diff.get("edits"):
            heard += "；待听审差异：" + json.dumps(diff["edits"], ensure_ascii=False)
        L.append(f"| {sid} | {sh.get('title', '')} | {t or '-'}/{len(project.takes(ep, sid, 'video'))} | {rec.get('duration', 0):.1f}s | {hit} | {heard} | {e.get('verdict', '')} | {rng} | {e.get('note', '')} |")
    L += ["", f"接触表：审查/{ep}-sheets/<镜>_t<take>.jpg（2 帧/秒）。模型看图后用 `review_tool.py mark` 记录取用区间与结论。"]
    project.review_dir.mkdir(parents=True, exist_ok=True)
    p = project.review_dir / f"{ep}-审片.md"
    p.write_text("\n".join(L), encoding="utf-8")
    return p


def mark(project: Project, ep: str, sid: str, **kw) -> dict:
    review = project.load_review(ep)
    sh = next((s for s in project.load_shots(ep).get("shots") or [] if s["id"] == sid), None)
    if sh is None:
        raise ValueError("unknown shot")
    entry = review.setdefault("shots", {}).setdefault(sid, {})
    if kw.get("frame_take") is not None:
        entry["frame_take"] = kw["frame_take"]
    video_keys = set(EDIT_KEYS) | set(CHECKS) | {"video_take", "verdict", "evidence", "action_window", "speech_window", "acceptance_reason"}
    if not any(kw.get(key) is not None for key in video_keys):
        if kw.get("note") is not None:
            entry["note"] = kw["note"]
        project.save_review(ep, review)
        return entry
    if kw.get("verdict") == "drop":
        if not str(kw.get("note") or "").strip():
            raise ValueError("drop requires a reason in note")
        entry.update(verdict="drop", note=kw["note"], locked=True)
        project.save_review(ep, review)
        return entry
    take = kw.get("video_take") or entry.get("video_take") or project.chosen_take(ep, sid, "video", review)
    if not take or not project.video_path(ep, sid, take).is_file():
        raise ValueError("select an existing video take")
    path = project.video_path(ep, sid, take)
    rec = entry.setdefault("video_takes", {}).setdefault(str(take), {"take": take})
    changed_take = entry.get("video_take") != take
    if changed_take:
        for key in EDIT_KEYS:
            entry.pop(key, None)
    entry["video_take"] = take
    edit = rec.setdefault("edit", {})
    for key in EDIT_KEYS:
        if kw.get(key) is not None:
            edit[key] = kw[key]
    if "speed" in edit and (not math.isfinite(float(edit["speed"])) or not 0.5 <= float(edit["speed"]) <= 2):
        raise ValueError("speed must be finite and within [0.5, 2]")
    for key in ("in", "out"):
        if key in edit and (not math.isfinite(float(edit[key])) or float(edit[key]) < 0):
            raise ValueError("trim times must be finite and nonnegative")
    if "in" in edit and "out" in edit and edit["out"] <= edit["in"]:
        raise ValueError("out must follow in")
    md, sd = media_digest(path), shot_digest(sh)
    old = rec.get("assessment") or {}
    current = old.get("media_sha256") == md and old.get("shot_sha256") == sd
    assessment = dict(old) if current else {}
    checks = dict(assessment.get("checks") or {})
    has_review = any(kw.get(k) is not None for k in (*CHECKS, "action_window", "speech_window"))
    if has_review:
        if not str(kw.get("evidence") or "").strip():
            raise ValueError("review changes require evidence (what was seen/heard and where)")
        for key in CHECKS:
            if kw.get(key) is not None:
                if kw[key] not in ("pass", "fail", "pending"):
                    raise ValueError("invalid review check")
                checks[key] = kw[key]
        for key in ("action_window", "speech_window"):
            if kw.get(key) is not None:
                if not valid_window(kw[key]):
                    raise ValueError(f"{key} must be finite 0 <= start < end")
                assessment[key] = list(kw[key])
        assessment.update(media_sha256=md, shot_sha256=sd, checks=checks,
                          evidence=kw["evidence"].strip(), reviewed_at=time.strftime("%Y-%m-%dT%H:%M:%S"))
        if kw.get("audio") is not None:
            assessment["speed"] = float(edit.get("speed") or 1.0)
        rec["assessment"] = assessment
    if kw.get("acceptance_reason"):
        assessment["acceptance_reason"] = kw["acceptance_reason"]
        if current or has_review:
            rec["assessment"] = assessment
    verdict = kw.get("verdict") or rec.get("verdict") or "pending_review"
    issues = take_quality(path, sh, rec)
    if float(edit.get("speed") or 1.0) != float(assessment.get("speed") or 1.0):
        issues.append("changed speed needs listening review")
    if verdict in ("ok", "weak", "mute") and issues:
        if kw.get("verdict") in ("ok", "weak", "mute"):
            raise ValueError("cannot approve: " + ", ".join(issues))
        verdict = "pending_review"
    if verdict == "weak" and not assessment.get("acceptance_reason"):
        raise ValueError("weak requires acceptance_reason for the noncritical defect")
    rec["verdict"] = verdict
    entry.update(verdict=verdict, locked=verdict in ("ok", "weak", "mute"))
    if kw.get("note") is not None:
        entry["note"] = rec["note"] = kw["note"]
    project.save_review(ep, review)
    return entry


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("sheets", "asr", "motion"):
        s = sub.add_parser(name)
        s.add_argument("project")
        s.add_argument("episode")
        s.add_argument("sids", nargs="*")
    for name in ("auto", "report", "animatic"):
        s = sub.add_parser(name)
        s.add_argument("project")
        s.add_argument("episode")
    m = sub.add_parser("mark")
    m.add_argument("project")
    m.add_argument("episode")
    m.add_argument("sid")
    m.add_argument("--video-take", type=int)
    m.add_argument("--frame-take", type=int)
    m.add_argument("--in", dest="in_", type=float)
    m.add_argument("--out", type=float)
    m.add_argument("--mode", choices=["after_last_word", "to_end", "fixed", "full", "action"])
    m.add_argument("--verdict", choices=["ok", "weak", "retake", "drop", "mute", "pending_review"])
    m.add_argument("--speed", type=float)
    m.add_argument("--note")
    for key in CHECKS:
        m.add_argument("--" + key, choices=["pass", "fail", "pending"])
    m.add_argument("--evidence")
    m.add_argument("--action-window", nargs=2, type=float, metavar=("START", "END"))
    m.add_argument("--speech-window", nargs=2, type=float, metavar=("START", "END"))
    m.add_argument("--acceptance-reason")
    a = ap.parse_args(argv)
    pr = Project(a.project)
    if a.cmd == "sheets":
        for p in sheets(pr, a.episode, a.sids or None):
            print("sheet", p)
    elif a.cmd == "asr":
        res = asr_all(pr, a.episode, a.sids or None)
        for k, v in res.items():
            flag = "" if v.get("hit") is None else f" hit {v['hit']:.0%}"
            stray = " ⚠stray voice" if v.get("stray_voice") else ""
            print(f"{k}: {v['duration']:.1f}s heard「{v['heard']}」{flag}{stray}")
    elif a.cmd == "motion":
        for k, v in motion_all(pr, a.episode, a.sids or None).items():
            span = f"{v['action_start']}–{v['action_end']}s" if v.get("action_end") is not None else "无明显动作"
            print(f"{k}: 峰 {v['action_peak']}s（{max(v['motion'] or [0]):.1f}） 动作 {span}" + (f" ⚠镜内跳切 {v['cuts']}" if v.get("cuts") else ""))
    elif a.cmd == "auto":
        rv = auto(pr, a.episode)
        for sid, e in (rv.get("shots") or {}).items():
            print(sid, e.get("verdict"), "take", e.get("video_take"))
    elif a.cmd == "report":
        print("wrote", report(pr, a.episode))
    elif a.cmd == "animatic":
        mp4, jpg, missing = animatic(pr, a.episode)
        print("animatic", mp4, round(ffprobe_duration(mp4), 2), "s; sheet", jpg, f"; target {pr.get('target_seconds')}s")
        if missing:
            print("⚠没有起始帧的镜（预演不完整）：", " ".join(missing))
        print(f"下一步：Read {jpg.name}，按 production-and-review §3b 写 审查/{a.episode}-预演.md，首行写「结论：PASS」或「结论：REVISE」，PASS 才进入阶段 H")
    elif a.cmd == "mark":
        e = mark(pr, a.episode, a.sid, video_take=a.video_take, frame_take=a.frame_take, **{"in": a.in_}, out=a.out,
                 mode=a.mode, verdict=a.verdict, speed=a.speed, note=a.note,
                 visual=a.visual, audio=a.audio, continuity=a.continuity, evidence=a.evidence,
                 action_window=a.action_window, speech_window=a.speech_window, acceptance_reason=a.acceptance_reason)
        print(json.dumps(e, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
