#!/usr/bin/env python3
"""审片：接触表、ASR 比对、自动选 take、记录取用区间。只读素材，不提交任何生成任务。

  review_tool.py sheets <项目> <EP> [SID ...]          每个 take 一张 2fps 接触表 审查/<EP>-sheets/<sid>_t<n>.jpg
  review_tool.py asr    <项目> <EP> [SID ...]          全部 take 跑 ASR，比对台词，结果写 审查/<EP>-asr.json 和 review.json；每 take 另记
                                                       extra_vocal_segments（speech_window 外识别到的人声 [[起, 止, 文本]]）与 voice_mismatch
                                                       （基频粗筛：refs.json 身份图 voice 的性别与中位基频明显不符，男 >200Hz / 女 <150Hz；只提醒去听）
  review_tool.py motion <项目> <EP> [SID ...]          全部 take 算运动能量（8fps、160px 灰度帧差，每 0.25s 一格），写 review.json 的
                                                       video_takes[n].motion / action_peak / action_start / action_end / cuts（镜内跳切）
  review_tool.py animatic <项目> <EP> [--no-tts]      阶段 G2 预演：按 cut_order 把通过的起始帧各放 seconds 秒，叠说话人与台词、镜号、
                                                       动作起止（planned_action_window，动作中高亮）、反应拍；铺临时对白音轨：配音/<sid>_<n>.wav
                                                       （单句镜也认 配音/<sid>.wav）→ 本地 TTS（macOS say，文件在 审查/<EP>-预演-temp/，名字带 temp）
                                                       → 按估算时长留静音并在画面标「[台词 x.x 秒]」。输出 审查/<EP>-预演.mp4、1fps 接触表
                                                       审查/<EP>-预演.jpg、审查/<EP>-预演.md（首行「结论：待填」+ 逐镜自动统计；审查者改首行为
                                                       PASS/REVISE）。预演内容没变时不动已填结论；变了把旧 md 挪成 <EP>-预演.prev.md。
                                                       环境变量 ANIMATIC_TTS=0 等同 --no-tts
  review_tool.py auto   <项目> <EP>                    按规则自动选 take、给 verdict（不改已由人/模型 mark 过的镜）
  review_tool.py report <项目> <EP>                    汇总 审查/<EP>-审片.md
  review_tool.py mark   <项目> <EP> <SID> [--video-take N] [--frame-take N] [--in S] [--out S] [--listener NAME]
                        [--mode after_last_word|to_end|fixed|full|action] [--verdict ok|weak|retake|drop|mute] [--speed X] [--note ...]
                        [--asr-ok true|false|null] [--listen-ok true|false|null] [--sync-ok true|false|null] [--must-show MS1=pass|fail|unverified]
    声音结论三分项写进 video_takes[n].assessment：asr_ok 识别正确、listen_ok 听感自然、sync_ok 口型/音画同步；null = 未验证，报告里显示「未验证」。
    旧 --audio pass 只等于 asr_ok=true。入剪要求 asr_ok=true，listen_ok/sync_ok 为 false 时拦下，null 放行但处处显示未验证。
    --must-show 写 video_takes[n].must_show_check（并镜像到镜级 must_show_check）；有 fail 时不许 ok/weak，auto 给 retake；
    承担 must_show 的镜要逐条 pass 才能 ok（unverified/缺项 = 没核），承担镜不许 weak。
    --speaker-face-ok true|false|null（纯视觉，代理可签，要带 --evidence）：本句说话人的嘴在动、其他人嘴不动；有镜内台词的镜入正式剪辑要求 true。
    --listen-ok true/false 必须带 --listener <真人>（用户或用户指定的母语者；model/claude/agent/ai/self 等一律拒绝）。
    --asr-ok true（或旧 --audio pass）要求当前文件、当前镜头跑过 ASR（asr_media_sha256/asr_shot_sha256 对得上）且没判「语种疑似不符」。
    --frame-take N --evidence "目检九项…"：起始帧目检，写 shots[sid].frame_review {take, sha256, evidence, time}（并追加 frame_review_log）；
    produce.py videos/all 拒绝没有目检记录或记录后帧文件已变的起始帧。--frame-take 必须指向已存在的 take。
    每次 mark 的 evidence 追加到 video_takes[n].evidence_log（时间、文件 sha、镜头 sha），不覆盖旧证据。
    批准 ok/weak/mute 还要求账本来源：脚本/jobs.jsonl 里有收回这个文件的 collected 记录，提示词与起始帧没在生成后改过。

ASR 用 faster-whisper：优先环境变量 ASR_PY 指向装了它的 python；否则依次试当前 python 和 ~/.venvs/*/bin/python。
模型 ASR_MODEL（默认 medium），语言取 drama.json 的 dialogue_lang。词级时间戳缓存在 脚本/asr_cache.json。
"""
from __future__ import annotations

import argparse
import time
import json
import re
import math
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import Project, ffprobe_duration, norm, speech_seconds  # noqa: E402
from review_quality import (AUDIO_KEYS, CHECKS, EDIT_KEYS, MUST_SHOW_VALUES, animatic_inputs_fp, audio_status, coverage_warnings, fmt_audio,
                            media_digest, must_show_approval_issues, must_show_failed, must_show_facts, must_show_state,
                            provenance_issues, shot_digest, speech_diff, take_quality, valid_window, asr_currency_issues)

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

    def words(self, paths: list[Path], fresh: bool = False) -> dict[str, list]:
        """fresh=True 不读缓存（成片终验用：缓存文件在项目里，谁都能写）。"""
        todo = [p for p in paths if fresh or self.key(p) not in self.cache]
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
    # 台词窗口外的人声（ASR 词在窗口外 → 多出来的话、乱语、别人开口）；窗口 = 已审的 speech_window，没审过按期望台词的词时间
    old_rec = ((project.load_review(ep).get("shots") or {}).get(sid) or {}).get("video_takes", {}).get(str(take)) or {}
    win = (old_rec.get("assessment") or {}).get("speech_window")
    if not (isinstance(win, list) and len(win) == 2):
        win = [ws[0][0], ws[-1][1]] if (ws and want) else None
    rec["extra_vocal_segments"] = extra_vocal_segments(ws, win)
    rec["voice_mismatch"] = voice_mismatch(project, sh, path, win)
    review = project.load_review(ep)
    entry = review.setdefault("shots", {}).setdefault(sid, {})
    entry.setdefault("video_takes", {}).setdefault(str(take), {}).update(rec)  # 保留 motion 等其他字段
    project.save_review(ep, review)
    return rec


def extra_vocal_segments(words: list, window) -> list[list[float]]:
    """speech_window 外被识别出来的人声片段（相邻 0.6s 内合并），[[start, end, text], …]。无台词镜的窗口为 None：全部都算多出来的。"""
    outside = [w for w in words if not window or (w[1] <= window[0] - 0.15 or w[0] >= window[1] + 0.15)]
    runs: list[list] = []
    for w in outside:
        if runs and w[0] - runs[-1][1] < 0.6:
            runs[-1][1] = w[1]
            runs[-1][2] += str(w[2])
        else:
            runs.append([w[0], w[1], str(w[2])])
    return [r for r in runs if len(norm(r[2])) >= 1]


VOICE_SEX = (("female", re.compile(r"\b(?:woman|woman's|girl|female|lady)\b|女", re.I)),
             ("male", re.compile(r"\b(?:man|man's|boy|male|guy)\b|男", re.I)))


def voice_mismatch(project: Project, sh: dict, path: Path, window) -> dict | None:
    """基频粗筛：说话人身份图 refs.json voice 写的性别与台词段中位基频明显不符（男 >200Hz、女 <150Hz）时返回说明；判不了返回 None。
    只是提醒去听，不是听审结论。"""
    dlg = [d for d in sh.get("dialogue") or [] if d.get("text") and not d.get("vo")]
    if not dlg or sh.get("audio_from") or not window:
        return None
    speaker = dlg[0].get("speaker")
    voice = next((str(r.get("voice") or "") for r in project.load_refs().values() if r.get("subject") == speaker and r.get("voice")), "")
    sex = next((k for k, rx in VOICE_SEX if rx.search(voice)), None)
    if not sex:
        return None
    try:
        import numpy as np
        raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{max(0.0, window[0]):.2f}", "-t", f"{max(0.3, window[1] - window[0]):.2f}",
                              "-i", str(path), "-ac", "1", "-ar", "16000", "-f", "s16le", "-"], capture_output=True).stdout
        x = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        f0s = []
        for i in range(0, len(x) - 640, 320):   # 40ms 帧、20ms 步长的自相关基频
            fr = x[i:i + 640] - x[i:i + 640].mean()
            if np.sqrt((fr ** 2).mean()) < 0.02:
                continue
            ac = np.correlate(fr, fr, "full")[639:]
            lo, hi = 16000 // 400, 16000 // 70
            k = lo + int(np.argmax(ac[lo:hi]))
            if ac[k] > 0.3 * ac[0]:
                f0s.append(16000 / k)
        if len(f0s) < 5:
            return None
        med = float(np.median(f0s))
    except Exception:  # noqa: BLE001  粗筛失败不影响 ASR 主流程
        return None
    if (sex == "male" and med > 200) or (sex == "female" and med < 150):
        return {"speaker": speaker, "expected": sex, "f0_median_hz": round(med, 1), "voice": voice[:60],
                "note": "中位基频和身份图 voice 设定的性别不符：听审确认是不是换了人声/口音严重不像"}
    return None


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
        ms_fail = bool(must_show_failed(entry, take))
        failed = (current and any(value == "fail" for value in (rec.get("assessment", {}).get("checks") or {}).values())) or ms_fail
        approved = not issues and not ms_fail and rec.get("verdict") in ("ok", "weak", "mute")
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


ANIMATIC_W, ANIMATIC_FPS = 1280, 25
AUDIO_EXTS = (".wav", ".mp3", ".m4a", ".aiff", ".flac")
TTS_PREFERRED = {"ja": ["Kyoko", "Otoya"], "zh": ["Tingting", "Ting-Ting", "Meijia"], "en": ["Samantha", "Alex"], "ko": ["Yuna"]}


def _dub_file(project: Project, ep: str, sid: str, n: int, total: int) -> Path | None:
    """已有配音：配音/<sid>_<n>.wav（n 从 1 起；也认 -<n>）；本镜只有一句时也认 配音/<sid>.wav。"""
    d = project.ep_dir(ep) / "配音"
    names = [f"{sid}_{n}", f"{sid}-{n}"] + ([sid] if total == 1 else [])
    for name in names:
        for ext in AUDIO_EXTS:
            if (d / (name + ext)).is_file():
                return d / (name + ext)
    return None


def _tts_voice(lang: str) -> str | None:
    """macOS say 里与台词语言匹配的声音；没有 say 或没有该语言返回 None。"""
    import shutil
    if not shutil.which("say"):
        return None
    try:
        out = subprocess.run(["say", "-v", "?"], capture_output=True, text=True, timeout=20).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    code = (lang or "").split("-")[0].lower()
    voices = []
    for line in out.splitlines():
        m = re.match(r"^(.+?)\s{2,}([a-z]{2})_[A-Z]{2}\b", line)
        if m and m.group(2) == code:
            voices.append(m.group(1).strip())
    for pref in TTS_PREFERRED.get(code, []):
        if pref in voices:
            return pref
    plain = [v for v in voices if "(" not in v]
    return (plain or voices or [None])[0]


def _tts(text: str, voice: str, out: Path) -> Path | None:
    if out.is_file() and out.stat().st_size > 0:
        return out
    out.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(["say", "-v", voice, "-o", str(out), text], capture_output=True, text=True)
    return out if r.returncode == 0 and out.is_file() and out.stat().st_size > 0 else None


def animatic_plan(project: Project, ep: str, tts: bool = True) -> dict:
    """预演的逐镜时间表：计划时长、每句台词的起止与来源（配音 dub / 本地 TTS 临时读稿 tts / 估算 estimate）、
    动作起止（planned_action_window，仅计划）、反应拍、能否装下、必须拍清楚与能力解释标记。"""
    data = project.load_shots(ep)
    shots = data.get("shots") or []
    order = data.get("cut_order") if data.get("cut_order") is not None else [s["id"] for s in shots]
    by_id = {s["id"]: s for s in shots}
    if len(order) != len(set(order)) or any(sid not in by_id for sid in order):
        raise ValueError("invalid cut_order for animatic")
    pace = project.sub("pace")
    rates = project.get("speech_rates")
    lang = str(project.get("dialogue_lang") or "ja")
    voice = _tts_voice(lang) if tts and os.environ.get("ANIMATIC_TTS", "1") != "0" else None
    tts_dir = project.review_dir / f"{ep}-预演-temp"
    rows, t_global = [], 0
    for sid in order:
        sh = by_id[sid]
        sec = float(sh.get("seconds") or 5)
        n_frames = max(1, round(sec * ANIMATIC_FPS))
        dlg = [d for d in sh.get("dialogue") or [] if d.get("text")] if not sh.get("audio_from") else []
        lines, t = [], 0.0
        for n, d in enumerate(dlg, 1):
            at = float(d["at"]) if d.get("at") is not None else (0.5 if n == 1 else t + 0.15)
            at = max(at, t + (0.1 if n > 1 else 0.0))
            src, path = "estimate", _dub_file(project, ep, sid, n, len(dlg))
            dur = ffprobe_duration(path) if path else 0.0
            if path and dur > 0:
                src = "dub"
            elif voice:
                from common import crc
                path = _tts(d["text"], voice, tts_dir / f"{sid}_{n}_{crc(voice + d['text']) % 100000:05d}_temp.aiff")
                dur = ffprobe_duration(path) if path else 0.0
                src = "tts" if path and dur > 0 else "estimate"
            if src == "estimate":
                path, dur = None, speech_seconds(d["text"], str(d.get("lang") or lang), rates)
            lines.append({"n": n, "speaker": d.get("speaker", ""), "text": d["text"], "subtitle": d.get("subtitle") or d["text"],
                          "at": round(at, 3), "dur": round(dur, 3), "end": round(at + dur, 3), "source": src, "path": str(path) if path else None})
            t = at + dur
        tail_need = float(pace["dialogue_tail"])
        fits = (not lines) or lines[-1]["end"] + tail_need <= sec + 1e-6
        kind = sh.get("kind", "person")
        reaction = []
        if kind == "person" and not lines and not sh.get("audio_from"):
            reaction.append([0.0, sec])                        # 无台词人物镜 = 反应镜
        elif lines:
            if sec - lines[-1]["end"] >= tail_need:
                reaction.append([round(lines[-1]["end"], 3), sec])   # 说完后的反应拍
            if (sh.get("reaction_first") or lines[0]["at"] >= float(pace["reaction_min"])) and lines[0]["at"] > 0.3:
                reaction.insert(0, [0.0, lines[0]["at"]])       # 先反应后开口
        act = sh.get("planned_action_window") or sh.get("action_window")
        act = [float(act[0]), float(act[1])] if isinstance(act, (list, tuple)) and len(act) == 2 else None
        rows.append({"shot": sid, "scene": sh.get("scene") or "", "kind": kind, "title": sh.get("title", ""), "seconds": sec,
                     "frames": n_frames, "start_frame": t_global, "lines": lines, "fits": fits, "reaction": reaction, "action": act,
                     "must_show_ids": list(sh.get("must_show_ids") or []), "explains_ability": bool(sh.get("explains_ability")),
                     "audio_from": bool(sh.get("audio_from")), "has_dialogue": bool(sh.get("dialogue"))})
        t_global += n_frames
    return {"episode": ep, "rows": rows, "total_frames": t_global, "fps": ANIMATIC_FPS, "voice": voice,
            "must_show": must_show_facts(data), "order": order}


def _animatic_card(frame: Path | None, row: dict, W: int, H: int, now: tuple[float, float], fonts: dict):
    """一张预演画面：起始帧 + 左上镜号/时长 + 右上动作起止（动作中高亮）+ 反应拍标记 + 底部说话人与台词。"""
    from PIL import Image, ImageDraw, ImageFont
    import cut as cut_mod
    if frame and frame.is_file():
        im = Image.open(frame).convert("RGB")
        scale = max(W / im.width, H / im.height)
        im = im.resize((max(W, round(im.width * scale)), max(H, round(im.height * scale))))
        left, top = (im.width - W) // 2, (im.height - H) // 2
        im = im.crop((left, top, left + W, top + H))
    else:
        im = Image.new("RGB", (W, H), (40, 40, 44))
    d = ImageDraw.Draw(im, "RGBA")
    t_mid = (now[0] + now[1]) / 2
    lab = fonts.get("label")
    if not lab:
        if not frame or not frame.is_file():
            d.rectangle([W // 3, H // 3, W * 2 // 3, H * 2 // 3], outline=(255, 80, 80), width=6)
        return im
    f_lab = ImageFont.truetype(lab, 24)
    f_big = ImageFont.truetype(lab, 30)

    def box(xy, text, font, fill, color=(255, 255, 255), anchor_right=False):
        bb = d.multiline_textbbox((0, 0), text, font=font, spacing=6)
        w, h = bb[2] - bb[0] + 20, bb[3] - bb[1] + 16
        x, y = (xy[0] - w, xy[1]) if anchor_right else xy
        d.rounded_rectangle([x, y, x + w, y + h], radius=8, fill=fill)
        d.multiline_text((x + 10 - bb[0], y + 8 - bb[1]), text, font=font, fill=color, spacing=6)
        return h

    head = f"{row['shot']}  {row['seconds']:.1f}s  {row['kind']}"
    tags = []
    if row["must_show_ids"]:
        tags.append("必须拍清楚 " + ",".join(row["must_show_ids"]))
    if row["explains_ability"]:
        tags.append("解释能力")
    if not frame or not frame.is_file():
        tags.append("缺起始帧")
    box((16, 16), head + ("\n" + " · ".join(tags) if tags else ""), f_lab, (0, 0, 0, 170))
    y_r = 16
    if row["action"]:
        a0, a1 = row["action"]
        active = a0 <= t_mid < a1
        y_r += box((W - 16, y_r), f"{'动作中 ' if active else '动作 '}{a0:.1f}–{a1:.1f}s", f_big if active else f_lab,
                   (210, 30, 30, 220) if active else (0, 0, 0, 170), anchor_right=True) + 8
    if any(r0 <= t_mid < r1 for r0, r1 in row["reaction"]):
        box((W - 16, y_r), "反应拍", f_big, (240, 190, 20, 230), color=(20, 20, 20), anchor_right=True)
    if not row["fits"]:
        box((16, 110), "台词装不下", f_big, (210, 30, 30, 220))
    line = next((ln for ln in row["lines"] if ln["at"] <= t_mid < ln["end"]), None)
    if line:
        tag = {"dub": "[配音]", "tts": f"[临时读稿 {line['dur']:.1f} 秒]", "estimate": f"[台词 {line['dur']:.1f} 秒]"}[line["source"]]
        text = f"{line['speaker']}：{line['subtitle']}"
        sub_font = cut_mod.find_font(cut_mod._panel_fonts(text, False) + cut_mod.FONT_DEFAULTS["sub"]) or lab
        f_sub = ImageFont.truetype(sub_font, 34)
        wrapped = cut_mod.wrap(text, f_sub, W - 160, fonts.get("terms") or ())
        bb = d.multiline_textbbox((0, 0), wrapped, font=f_sub, spacing=8, align="center")
        tw, th = bb[2] - bb[0], bb[3] - bb[1]
        x, y = (W - tw) // 2, H - th - 64
        d.rounded_rectangle([x - 16, y - 12, x + tw + 16, y + th + 14], radius=10, fill=(0, 0, 0, 150))
        d.multiline_text((x - bb[0], y - bb[1]), wrapped, font=f_sub, fill=(255, 255, 255), spacing=8, align="center",
                         stroke_width=2, stroke_fill=(0, 0, 0))
        d.text((W // 2, H - 30), tag, font=f_lab, fill=(255, 230, 120), anchor="mm")
    return im


def animatic(project: Project, ep: str, tts: bool = True) -> tuple[Path, Path, list[str]]:
    """预演（视频提交前）：按 cut_order 与计划时长把通过的起始帧拼成视频，叠说话人与台词、镜号、动作起止与反应拍，
    铺临时对白音轨（已有配音 → 本地 TTS 临时读稿 → 按估算时长留静音并标「[台词 x.x 秒]」）。
    输出 审查/<EP>-预演.mp4、1fps 接触表 审查/<EP>-预演.jpg、逐镜统计 + 结论待填的 审查/<EP>-预演.md。"""
    import hashlib
    import tempfile
    import cut as cut_mod
    plan = animatic_plan(project, ep, tts)
    review = project.load_review(ep)
    out_dir = project.review_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    mp4, jpg = out_dir / f"{ep}-预演.mp4", out_dir / f"{ep}-预演.jpg"
    W = ANIMATIC_W
    H = int(round(W * int(project.get("height")) / int(project.get("width")) / 2)) * 2
    fps = ANIMATIC_FPS
    label = cut_mod.find_font(cut_mod.PANEL_FONTS["zh"] + cut_mod.PANEL_FONTS["any"] + cut_mod.FONT_DEFAULTS["sub"])
    fonts = {"label": label, "terms": cut_mod.text_terms(project, project.load_shots(ep))}
    missing, frames_used = [], []
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        seg_list = []
        for row in plan["rows"]:
            sid = row["shot"]
            ft = project.chosen_take(ep, sid, "frame", review)
            frame = project.frame_path(ep, sid, ft) if ft else None
            if not ft:
                missing.append(sid)
            frames_used.append([sid, ft, media_digest(frame) if frame and frame.is_file() else None])
            sec = row["seconds"]
            cuts = {0.0, sec}
            for ln in row["lines"]:
                cuts.update((ln["at"], ln["end"]))
            for r0, r1 in row["reaction"]:
                cuts.update((r0, r1))
            if row["action"]:
                cuts.update(row["action"])
            fr = sorted({min(row["frames"], max(0, round(c * fps))) for c in cuts})
            for f0, f1 in zip(fr, fr[1:]):
                if f1 <= f0:
                    continue
                png = tdp / f"c{len(seg_list):04d}.png"
                _animatic_card(frame, row, W, H, (f0 / fps, f1 / fps), fonts).save(png)
                seg = tdp / f"c{len(seg_list):04d}.mp4"
                subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-loop", "1", "-framerate", str(fps), "-i", str(png),
                                "-frames:v", str(f1 - f0), "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-r", str(fps),
                                str(seg)], check=True)
                seg_list.append(seg)
        if not seg_list:
            raise SystemExit(f"{ep} 没有任何镜头，先写 shots.json")
        lst = tdp / "list.txt"
        lst.write_text("".join(f"file '{p.name}'\n" for p in seg_list), encoding="utf-8")
        video = tdp / "video.mp4"
        subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(video)], check=True)
        total = plan["total_frames"] / fps
        inputs, filt, mix = ["-f", "lavfi", "-t", f"{total:.3f}", "-i", "anullsrc=r=48000:cl=stereo"], [], ["[0:a]"]
        for row in plan["rows"]:
            base = row["start_frame"] / fps
            for ln in row["lines"]:
                if not ln["path"]:
                    continue
                keep = max(0.05, min(ln["dur"], row["seconds"] - ln["at"]))   # 装不下的读稿在镜尾截断（节奏问题照实暴露）
                inputs += ["-i", ln["path"]]
                k = len(mix)
                filt.append(f"[{k}:a]aresample=48000,aformat=channel_layouts=stereo,atrim=0:{keep:.3f},asetpts=PTS-STARTPTS,"
                            f"adelay={int(round((base + ln['at']) * 1000))}:all=1[l{k}]")
                mix.append(f"[l{k}]")
        filt.append(f"{''.join(mix)}amix=inputs={len(mix)}:normalize=0:duration=first[aout]" if len(mix) > 1 else "[0:a]anull[aout]")
        audio = tdp / "audio.wav"
        subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", *inputs, "-filter_complex", ";".join(filt), "-map", "[aout]",
                        "-t", f"{total:.3f}", str(audio)], check=True)
        subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(video), "-i", str(audio), "-map", "0:v", "-map", "1:a",
                        "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-t", f"{total:.3f}", "-movflags", "+faststart", str(mp4)], check=True)
    n = max(1, math.ceil(plan["total_frames"] / fps))
    cols = 6
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(mp4), "-vf", f"fps=1,scale=320:-1,tile={cols}x{max(1, math.ceil(n / cols))}",
                    "-frames:v", "1", str(jpg)], check=False)
    fingerprint = hashlib.sha256(json.dumps([[{k: r[k] for k in ("shot", "frames", "lines", "action", "reaction")} for r in plan["rows"]], frames_used],
                                            ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]
    write_animatic_md(project, ep, plan, missing, fingerprint, bool(label), animatic_inputs_fp(project, ep, review))
    return mp4, jpg, missing


def animatic_stats(project: Project, plan: dict) -> dict:
    rows = plan["rows"]
    person = [r for r in rows if r["kind"] == "person"]
    talk = [r for r in person if r["has_dialogue"]]
    scenes: dict[str, dict] = {}
    for r in rows:
        sc = scenes.setdefault(r["scene"], {"dialogue": 0, "reaction": 0})
        sc["dialogue"] += 1 if r["lines"] else 0
        sc["reaction"] += 1 if r["reaction"] else 0
    runs, cur = [], []
    for r in rows:
        if r["explains_ability"]:
            cur.append(r["shot"])
        else:
            if len(cur) >= 2:
                runs.append(cur)
            cur = []
    if len(cur) >= 2:
        runs.append(cur)
    in_cut = set(plan["order"])
    ms = [{**f, "in_cut": [s for s in f["shots"] if s in in_cut]} for f in plan["must_show"]]
    src = {"dub": 0, "tts": 0, "estimate": 0}
    for r in rows:
        for ln in r["lines"]:
            src[ln["source"]] += 1
    return {"total": plan["total_frames"] / plan["fps"], "target": project.get("target_seconds"),
            "not_fit": [r["shot"] for r in rows if not r["fits"]],
            "no_reaction_scenes": [sc for sc, v in scenes.items() if v["dialogue"] >= 2 and v["reaction"] == 0],
            "person": len(person), "talk": len(talk), "explains": [r["shot"] for r in rows if r["explains_ability"]],
            "explain_runs": runs, "must_show": ms, "sources": src,
            "no_action_mark": [r["shot"] for r in rows if r["kind"] in ("person", "hands") and not r["action"] and not r["lines"]]}


def write_animatic_md(project: Project, ep: str, plan: dict, missing: list[str], fingerprint: str, has_font: bool,
                      inputs_fp: str | None = None) -> Path:
    """写 审查/<EP>-预演.md：首行结论待填；已有人填过结论且预演内容没变就不动（只补/更新「预演输入指纹」行），
    内容变了把旧文件挪成 .prev.md。放行判定见 common.Project.animatic_problems。"""
    p = project.review_dir / f"{ep}-预演.md"
    inputs_line = f"预演输入指纹：{inputs_fp}（shots.json 与所选起始帧的指纹；放行时脚本重算比对，这一行不要改）" if inputs_fp else ""
    if p.exists():
        old = p.read_text(encoding="utf-8")
        first = next((ln.strip() for ln in old.splitlines() if ln.strip()), "")
        filled = re.match(r"^结论\s*[：:]\s*(PASS|REVISE)\b", first, re.I)
        if filled and f"预演指纹：{fingerprint}" in old:
            if inputs_line:   # 预演内容没变：旧文件升级，补上输入指纹行（旧版脚本生成的 md 没有这一行）
                new = re.sub(r"^预演输入指纹[：:].*$", inputs_line, old, flags=re.M) if re.search(r"^预演输入指纹[：:]", old, re.M) \
                    else re.sub(r"^(预演指纹[：:].*)$", lambda m: m.group(1) + "\n\n" + inputs_line, old, count=1, flags=re.M)
                if new != old:
                    p.write_text(new, encoding="utf-8")
            return p
        if filled:
            p.with_name(f"{ep}-预演.prev.md").write_text(old, encoding="utf-8")
    st = animatic_stats(project, plan)
    names = {"dub": "配音", "tts": "临时读稿", "estimate": "估算静音"}
    L = ["结论：待填（看完预演片后把这一行改成「结论：PASS」或「结论：REVISE」；有一条不过就写 REVISE。PASS 还要：下面「必拍事实」表逐条填「镜号 · 预演第几秒」和"
         "「看得到」、模板方括号全部填掉、预演输入指纹行不改——project_tool next 与 produce.py videos/all 逐项核对）", "",
         f"# {ep} 预演", "",
         f"预演指纹：{fingerprint}（预演内容变了会重出模板，旧结论挪到 {ep}-预演.prev.md）", "",
         *([inputs_line, ""] if inputs_line else []),
         f"预演片：审查/{ep}-预演.mp4；接触表：审查/{ep}-预演.jpg。临时对白：配音 {st['sources']['dub']} 句、"
         f"本地 TTS 临时读稿 {st['sources']['tts']} 句（{plan.get('voice') or '无'}，只作节奏参考，文件名带 temp）、按估算时长留静音 {st['sources']['estimate']} 句。"
         + ("" if has_font else "⚠ 没找到中日文字体，画面上没有字幕和标记，只能对照本表看。"), "",
         "## 自动统计", "",
         f"- 总时长 {st['total']:.1f}s，目标 {st['target']}s，差 {st['total'] - float(st['target'] or 0):+.1f}s。",
         f"- 台词装不下（最后一句说完 + {project.sub('pace')['dialogue_tail']}s 超过计划时长）：{'、'.join(st['not_fit']) or '无'}。",
         f"- 有两个以上对白镜却没有任何反应拍的场：{'、'.join(st['no_reaction_scenes']) or '无'}。",
         f"- 人物镜 {st['person']} 个，其中带台词 {st['talk']} 个（{(st['talk'] / st['person'] if st['person'] else 0):.0%}）；比例高本身不算错，"
         "但要确认有对方的反应和改变局面的动作，不是轮流说明情况。",
         f"- 解释/确认能力规则的镜（explains_ability）：{'、'.join(st['explains']) or '无'}；连续解释：{'；'.join('→'.join(r) for r in st['explain_runs']) or '无'}。",
         f"- 缺起始帧（用灰卡占位）：{'、'.join(missing) or '无'}。"]
    if st["must_show"]:
        L.append("- 必须拍清楚的事实：" + "；".join(
            f"{f['id']}「{f['fact']}」→ {'、'.join(f['in_cut']) if f['in_cut'] else '✗ 没有承担镜在片中'}" for f in st["must_show"]) + "。")
    else:
        L.append("- 必须拍清楚的事实：shots.json 没写 scenes[].must_show。")
    L += ["", "## 逐镜", "", "| # | 镜 | 场 | 计划 | 台词（起止·来源） | 装得下 | 动作窗（计划） | 反应拍 | 必须拍清楚 | 解释能力 |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    for i, r in enumerate(plan["rows"], 1):
        lines = "；".join(f"{ln['speaker']} {ln['at']:.1f}–{ln['end']:.1f}s·{names[ln['source']]}" for ln in r["lines"]) or ("垫录音" if r["audio_from"] else "无")
        act = f"{r['action'][0]:.1f}–{r['action'][1]:.1f}s" if r["action"] else "-"
        rb = "；".join(f"{a:.1f}–{b:.1f}s" for a, b in r["reaction"]) or "无"
        L.append(f"| {i} | {r['shot']} | {r['scene']} | {r['seconds']:.1f}s | {lines} | {'是' if r['fits'] else '✗ 否'} | {act} | {rb} | "
                 f"{','.join(r['must_show_ids']) or '-'} | {'是' if r['explains_ability'] else '-'} |")
    if st["must_show"]:
        L += ["", "## 必拍事实", "", "| ID | 事实 | 承担镜 · 预演第几秒 | 结果（看得到 / 看不到 / 只靠台词；数量类写逐个数的结果） |", "|---|---|---|---|"]
        L += [f"| {f['id']} | {f['fact']} | 【{(f['in_cut'] or ['镜号'])[0]} · X.Xs】 | 【看得到 / 看不到 / 只靠台词】 |" for f in st["must_show"]]
    L += ["", "## 审查逐条回答（production-and-review §3b）", "",
          "1. 只看画面、听临时对白，能不能复述每场发生了什么、谁赢谁输？",
          "2. 每条必须拍清楚的事实（数量、谁做了什么、反派具体损失）在哪一镜、第几秒让观众看清？",
          "3. 对白之间有没有对方的反应拍；有没有人物轮流说明情况、重复解释观众刚看过的能力？",
          "4. 台词装不下的镜：删字、拆镜，还是加长计划时长？",
          "5. 动作起止落在计划时长里吗？动作会不会被剪点切掉？",
          "6. 总时长与目标的差怎么处理？", ""]
    p.write_text("\n".join(L), encoding="utf-8")
    return p


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
    data = project.load_shots(ep)
    for sh in data.get("shots") or []:
        sid = sh["id"]
        entry = review.setdefault("shots", {}).setdefault(sid, {})
        if entry.get("verdict") == "drop" and entry.get("note"):
            continue
        best = choose_best(project, ep, sid, review, save=False)
        if best is None:
            entry["verdict"] = "missing"
            continue
        rec = (entry.get("video_takes") or {}).get(str(best)) or {}
        issues = take_quality(project.video_path(ep, sid, best), sh, rec) + provenance_issues(project, ep, sid, best, sh, review)
        issues += must_show_approval_issues(data, sid, entry, best, rec.get("verdict"))
        ms_fail = must_show_failed(entry, best)
        if ms_fail:   # 必须拍清楚的事实没拍出来：不许给 ok/weak，只能重拍或回剧本/分镜改
            issues = issues + [f"must_show_failed:{','.join(ms_fail)}"]
            entry["verdict"] = "retake"
            entry["locked"] = False
        elif not issues and rec.get("verdict") in ("ok", "weak", "mute"):
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
    facts = {f["id"]: f for f in must_show_facts(data)}
    L = [f"# {ep} 审片", "", "声音结论分三项：识别（asr_ok，ASR 与台词一致）、听审（listen_ok，人听过、听感自然）、同步（sync_ok，口型/音画同步）。"
         "「未验证」表示没人做过这一项，不等于通过。", "",
         "| 镜 | 标题 | take | 时长 | ASR 命中 | 听到 | 声音 | 必须拍清楚 | 结论 | 取用 | 备注 |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    ms_rows: dict[str, list[str]] = {}
    cover: list[str] = []
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
        if diff.get("critical_changes"):
            heard += "；⚠ 关键词识别分歧（需母语者确认）：" + "、".join(diff["critical_changes"])
        if rec.get("extra_vocal_segments"):
            heard += "；⚠ 台词窗口外人声：" + "、".join(f"{a:.1f}–{b:.1f}s「{t}」" for a, b, t in rec["extra_vocal_segments"])
        if rec.get("voice_mismatch"):
            heard += f"；[warn] 声线疑似不符（中位基频 {rec['voice_mismatch']['f0_median_hz']}Hz，设定 {rec['voice_mismatch']['expected']}），听审确认"
        audio = fmt_audio(audio_status(rec.get("assessment"))) if sh.get("dialogue") else "-"
        cover += [f"- {sid}/t{t}：{w}" for w in coverage_warnings(sh, rec, project.root)] if t else []
        state = must_show_state(e, t) if t else {}
        ids = list(dict.fromkeys(list(sh.get("must_show_ids") or []) + list(state)))
        ms = "；".join(f"{mid} {({'pass': '通过', 'fail': '✗ 没拍出来', 'unverified': '未验证'}).get(state.get(mid), '未验证')}" for mid in ids) or "-"
        for mid in ids:
            ms_rows.setdefault(mid, []).append(f"{sid}：{({'pass': '通过', 'fail': '没拍出来', 'unverified': '未验证'}).get(state.get(mid), '未验证')}")
        L.append(f"| {sid} | {sh.get('title', '')} | {t or '-'}/{len(project.takes(ep, sid, 'video'))} | {rec.get('duration', 0):.1f}s | {hit} | {heard} | "
                 f"{audio} | {ms} | {e.get('verdict', '')} | {rng} | {e.get('note', '')} |")
    if facts:
        L += ["", "## 必须拍清楚的事实", ""]
        for mid, f in facts.items():
            rows = ms_rows.get(mid) or [f"{x}：未验证" for x in f["shots"]] or ["✗ 没有任何镜承担"]
            L.append(f"- {mid}（{f.get('kind') or '-'}）「{f['fact']}」：{'；'.join(rows)}")
    if cover:
        L += ["", "## 审片覆盖提醒（L30，warn）", ""] + cover
    L += ["", f"接触表：审查/{ep}-sheets/<镜>_t<take>.jpg（2 帧/秒）。模型看图后用 `review_tool.py mark` 记录取用区间与结论。"]
    project.review_dir.mkdir(parents=True, exist_ok=True)
    p = project.review_dir / f"{ep}-审片.md"
    p.write_text("\n".join(L), encoding="utf-8")
    return p


BAD_LISTENERS = ("model", "claude", "agent", "ai", "self", "llm", "gpt", "assistant", "bot", "opus", "sonnet", "haiku", "fable",
                 "whisper", "asr", "subagent", "reviewer", "代理", "模型", "自己", "本人", "子代理", "助手", "机器")


def valid_listener(name) -> bool:
    """listen_ok 只能由真人签（用户或用户指定的母语者）；执行代理、子代理、模型名一律拒绝（SKILL 防钻空子总则第 5 条）。"""
    n = str(name or "").strip().lower()
    if len(n) < 2 or n in ("-", "无", "none", "null"):
        return False
    return not any(b == n or (b.isascii() and len(b) > 2 and b in n) or (not b.isascii() and b in n) for b in BAD_LISTENERS)


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def mark(project: Project, ep: str, sid: str, **kw) -> dict:
    review = project.load_review(ep)
    data = project.load_shots(ep)
    sh = next((s for s in data.get("shots") or [] if s["id"] == sid), None)
    if sh is None:
        raise ValueError("unknown shot")
    entry = review.setdefault("shots", {}).setdefault(sid, {})
    frame_mark = kw.get("frame_take") is not None
    if frame_mark:
        ft = int(kw["frame_take"])
        fpath = project.frame_path(ep, sid, ft)
        if not fpath.is_file():
            raise ValueError(f"起始帧 {fpath.name} 不存在；--frame-take 只能选已生成的 take")
        entry["frame_take"] = ft
        ev = str(kw.get("evidence") or "").strip()
        if ev:   # 起始帧目检：证据绑定这张帧文件的 sha256；重出/换帧后自动失效，produce.py videos 拒绝提交
            fr = {"take": ft, "sha256": media_digest(fpath), "evidence": ev, "time": _now()}
            entry["frame_review"] = fr
            entry.setdefault("frame_review_log", []).append(fr)
    video_keys = set(EDIT_KEYS) | set(CHECKS) | set(AUDIO_KEYS) | {"video_take", "verdict", "evidence", "action_window", "speech_window",
                                                                   "acceptance_reason", "must_show"}
    if kw.get("speaker_face_ok", "unset") == "unset":
        kw.pop("speaker_face_ok", None)
    else:
        video_keys.add("speaker_face_ok")
    if frame_mark:
        video_keys.discard("evidence")   # 带 --frame-take 时 --evidence 是起始帧目检证据
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
    audio_given = {k: kw[k] for k in AUDIO_KEYS if k in kw and kw[k] != "unset"}   # None（null）也是有效写入：写成未验证
    has_review = any(kw.get(k) is not None for k in (*CHECKS, "action_window", "speech_window", "must_show")) or bool(audio_given) \
        or "speaker_face_ok" in kw
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
        for key, val in audio_given.items():
            if val not in (True, False, None):
                raise ValueError(f"{key} must be true/false/null")
            assessment[key] = val
        if "speaker_face_ok" in kw:
            if kw["speaker_face_ok"] not in (True, False, None):
                raise ValueError("speaker_face_ok must be true/false/null")
            assessment["speaker_face_ok"] = kw["speaker_face_ok"]   # 绑定本 take：assessment 带 media_sha256，换文件自动失效
        if "listen_ok" in audio_given:
            if audio_given["listen_ok"] is None:
                assessment.pop("listener", None)
            elif not valid_listener(kw.get("listener")):
                raise ValueError("listen_ok 只能由真人签：--listener 写听的人（用户或用户指定的母语者），"
                                 f"不接受模型/代理/自己（收到 {kw.get('listener')!r}）；没人听就写 --listen-ok null，汇报「未听审」")
            else:
                assessment["listener"] = str(kw["listener"]).strip()
        if "asr_ok" in audio_given and kw.get("audio") is None and audio_given["asr_ok"] is not None:
            checks["audio"] = "pass" if audio_given["asr_ok"] else "fail"   # 旧字段跟着新字段走，旧读者不至于误读
        if kw.get("audio") is not None and "asr_ok" not in audio_given:
            assessment["asr_ok"] = {"pass": True, "fail": False}.get(kw["audio"])   # 旧 --audio pass 只等于识别通过
        if assessment.get("asr_ok") is True and ("asr_ok" in audio_given or kw.get("audio") is not None):
            bad = [x for x in asr_currency_issues(path, sh, rec)]
            if bad:
                raise ValueError("不能写 asr_ok=true：" + "；".join(bad))
        if kw.get("must_show"):
            ms = dict(rec.get("must_show_check") or {})
            for mid, val in kw["must_show"].items():
                if val not in MUST_SHOW_VALUES:
                    raise ValueError(f"must_show_check {mid} must be pass/fail/unverified")
                ms[mid] = val
            rec["must_show_check"] = ms
            entry["must_show_check"] = dict(ms)
        assessment.update(media_sha256=md, shot_sha256=sd, checks=checks,
                          evidence=kw["evidence"].strip(), reviewed_at=_now())
        # 证据只追加不覆盖：每条带时间和被审文件 sha，改结论也留得下旧证据
        rec.setdefault("evidence_log", []).append({"time": assessment["reviewed_at"], "evidence": kw["evidence"].strip(),
                                                   "media_sha256": md, "shot_sha256": sd, "verdict": kw.get("verdict")})
        if kw.get("audio") is not None or audio_given:
            assessment["speed"] = float(edit.get("speed") or 1.0)
        rec["assessment"] = assessment
    if kw.get("acceptance_reason"):
        assessment["acceptance_reason"] = kw["acceptance_reason"]
        if current or has_review:
            rec["assessment"] = assessment
    verdict = kw.get("verdict") or rec.get("verdict") or "pending_review"
    issues = take_quality(path, sh, rec) + provenance_issues(project, ep, sid, take, sh, review)
    issues += [x for x in must_show_approval_issues(data, sid, entry, take, verdict) if not must_show_failed(entry, take)]
    if float(edit.get("speed") or 1.0) != float(assessment.get("speed") or 1.0):
        issues.append("changed speed needs listening review")
    if verdict in ("ok", "weak", "mute") and issues:
        if kw.get("verdict") in ("ok", "weak", "mute"):
            raise ValueError("cannot approve: " + ", ".join(issues))
        verdict = "pending_review"
    if verdict == "weak" and not assessment.get("acceptance_reason"):
        raise ValueError("weak requires acceptance_reason for the noncritical defect")
    ms_fail = must_show_failed(entry, take)
    if verdict in ("ok", "weak") and ms_fail:
        if kw.get("verdict") in ("ok", "weak"):
            raise ValueError(f"cannot approve: must_show fail {','.join(ms_fail)}；必须拍清楚的事实没拍出来，只能 retake 或回剧本/分镜改")
        verdict = "retake"
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
        if name == "animatic":
            s.add_argument("--no-tts", action="store_true", help="不用本地 TTS，台词按估算时长留静音")
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
    for key in AUDIO_KEYS:
        m.add_argument("--" + key.replace("_", "-"), choices=["true", "false", "null"],
                       help={"asr_ok": "识别正确（ASR 与台词一致）", "listen_ok": "听感自然（人听过）", "sync_ok": "口型/音画同步"}[key])
    m.add_argument("--must-show", action="append", default=[], metavar="MS1=pass|fail|unverified",
                   help="本 take 对必须拍清楚事实的核验结果，可重复")
    m.add_argument("--speaker-face-ok", choices=["true", "false", "null"],
                   help="纯视觉：本句说话人的嘴在动、其他人嘴不动（要带 --evidence 写看到的时间码）；有台词的镜入剪要求 true")
    m.add_argument("--listener", help="listen_ok 非 null 时必填：听的真人（用户或用户指定的母语者）；模型/代理/自己一律拒绝")
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
            extra = f" ⚠台词窗口外人声 {v['extra_vocal_segments']}" if v.get("extra_vocal_segments") else ""
            vm = f" ⚠[warn] 声线疑似不符（中位基频 {v['voice_mismatch']['f0_median_hz']}Hz，设定 {v['voice_mismatch']['expected']}）" if v.get("voice_mismatch") else ""
            print(f"{k}: {v['duration']:.1f}s heard「{v['heard']}」{flag}{stray}{extra}{vm}")
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
        mp4, jpg, missing = animatic(pr, a.episode, tts=not a.no_tts)
        print("animatic", mp4, round(ffprobe_duration(mp4), 2), "s; sheet", jpg, f"; target {pr.get('target_seconds')}s")
        if missing:
            print("⚠没有起始帧的镜（预演不完整）：", " ".join(missing))
        print(f"下一步：看 {mp4.name}（带临时对白）和 {jpg.name}，按 production-and-review §3b 在 审查/{a.episode}-预演.md 回答逐条问题，"
              "把首行「结论：待填…」改成「结论：PASS」或「结论：REVISE」，PASS 才进入阶段 H")
    elif a.cmd == "mark":
        e = mark(pr, a.episode, a.sid, video_take=a.video_take, frame_take=a.frame_take, **{"in": a.in_}, out=a.out,
                 mode=a.mode, verdict=a.verdict, speed=a.speed, note=a.note,
                 visual=a.visual, audio=a.audio, continuity=a.continuity, evidence=a.evidence,
                 action_window=a.action_window, speech_window=a.speech_window, acceptance_reason=a.acceptance_reason,
                 must_show=dict(x.split("=", 1) for x in a.must_show) or None, listener=a.listener,
                 speaker_face_ok={"true": True, "false": False, "null": None}[a.speaker_face_ok] if a.speaker_face_ok else "unset",
                 **{k: ({"true": True, "false": False, "null": None}[getattr(a, k)] if getattr(a, k) else "unset") for k in AUDIO_KEYS})
        print(json.dumps(e, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
