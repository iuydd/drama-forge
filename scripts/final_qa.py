#!/usr/bin/env python3
"""成片终验：原素材过检不代表成片没问题。直接从最终 MP4 重新验收文字、台词、切点和声音。

  final_qa.py <项目> <EP> [--video PATH] [--no-asr] [--asr-min 0.8]

输入：成片/<EP>.mp4 与 cut.py 写的 成片/<EP>.overlays.json（叠字文本、渲染行拆分、位置、逐段切点）。
输出：审查/<EP>-final-qa.json、审查/<EP>-final-qa.md、证据帧与接触表 审查/<EP>-final-qa/。
检查：
- 文字：金额/数字/专名是否被断行、是否超过两行没分屏、叠字框是否压到人脸（有 OpenCV 时逐条抽帧检测）。
- 台词：成片整段 ASR，逐句与字幕原文比对——字幕有而声音识别不到列「字幕多于声音」，切点附近首尾缺失列「疑似裁词」，
  关键词（readings、dialogue[].reading、critical_terms）识别分歧单列「需母语者确认」，有人声却没字幕列「有声无字幕」。
- 声音：削波、整体响度（EBU R128）与目标差、镜间响度跳变、片尾静止/静音拖尾、画面比声音长。
结论三分项：asr_ok 只由本次对成片真跑的 ASR 给（不读 脚本/asr_cache.json 缓存）；listen_ok、sync_ok 脚本无法听审、判口型，一律 null，
除非 review.json 的 final_qa 里有人工写入的值：必须带 evidence、listener（真人，模型/代理一律拒绝）和 video_sha256（等于当前成片，
重剪后自动失效），且只能填脚本给 null 的项——asr_ok 的人工值只能把「关键词识别分歧（需母语者确认）」确认掉，不能替代没跑的 ASR。
期望台词从 shots.json 取（cut_order 里没 drop 的镜的镜内台词），元数据里缺字幕的台词报 error；草剪（overlays draft=true）一律 REVISE；
成片还要重过一次剪辑准入（review_quality.cut_issues）。识别召回下限不低于 0.8（drama.json 或 --asr-min 更低也按 0.8）。
首行结论：没有 error 级问题且 asr_ok 为 true（或全片无台词）才写 PASS，否则 REVISE。只有对交付文件（成片/<EP>.mp4）跑的报告
delivery=true，project_tool next 只认它。
"""
from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import Project, ffprobe_duration, norm  # noqa: E402
from review_quality import AUDIO_KEYS, fmt_audio, media_digest, speech_diff  # noqa: E402

import cut as cut_mod  # noqa: E402

SCHEMA = "drama-forge/final-qa/v1"
ASR_FLOOR = 0.8
SPEECH_TYPES = ("字幕多于声音", "疑似裁词", "否定词/数字差异", "元数据缺台词字幕")


def expected_lines(data: dict, review: dict) -> list[tuple[str, str]]:
    """成片应当说出的台词：cut_order 里没 drop 的镜的镜内台词（vo 与垫录音的镜也算，字幕照样要有）。"""
    shots = {sh["id"]: sh for sh in data.get("shots") or []}
    order = data.get("cut_order") if data.get("cut_order") is not None else list(shots)
    out = []
    for sid in order:
        if ((review.get("shots") or {}).get(sid) or {}).get("verdict") == "drop" or sid not in shots:
            continue
        out += [(sid, d["text"]) for d in shots[sid].get("dialogue") or [] if d.get("text")]
    return out


def expected_line_issues(data: dict, review: dict, meta: dict) -> list[dict]:
    """期望台词逐句要在成片字幕里：删字幕条目、删带台词的镜都藏不住。"""
    subs = [norm(g["speech"]) + "|" + norm(g["full_text"]) for g in sub_groups(meta)]
    blob = "\n".join(subs)
    out = []
    for sid, text in expected_lines(data, review):
        if norm(text) and norm(text) not in blob:
            out.append({"t": None, "end": None, "type": "元数据缺台词字幕", "severity": "error", "shot": sid,
                        "detail": f"shots.json 里 {sid} 的台词「{text}」在成片字幕里找不到：台词被裁掉、字幕被删，或元数据被改过；重剪（cut.py）"})
    return out


def tc(t: float | None) -> str:
    if t is None:
        return "-"
    return f"{int(t // 60):02d}:{t % 60:05.2f}"


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True)


def stream_durations(video: Path) -> dict:
    r = _run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,duration", "-of", "json", str(video)])
    out = {}
    try:
        for st in json.loads(r.stdout or "{}").get("streams", []):
            if st.get("duration") not in (None, "N/A"):
                out.setdefault(st.get("codec_type"), float(st["duration"]))
    except (ValueError, TypeError):
        pass
    return out


def grab(video: Path, t: float, out: Path, rects: list | None = None, faces: list | None = None) -> Path | None:
    """抽一帧做证据；给了叠字框（黄）和人脸框（红）就画上去。"""
    out.parent.mkdir(parents=True, exist_ok=True)
    r = _run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-ss", f"{max(0.0, t):.3f}", "-i", str(video), "-frames:v", "1", "-q:v", "3", str(out)])
    if r.returncode != 0 or not out.exists():
        return None
    if rects or faces:
        from PIL import Image, ImageDraw
        im = Image.open(out).convert("RGB")
        d = ImageDraw.Draw(im)
        for x, y, w, h in rects or []:
            d.rectangle([x, y, x + w, y + h], outline=(255, 220, 0), width=4)
        for x, y, w, h in faces or []:
            d.rectangle([x, y, x + w, y + h], outline=(255, 40, 40), width=4)
        im.save(out, quality=88)
    return out


def contact_sheet(video: Path, out: Path, duration: float) -> Path | None:
    n = max(1, math.ceil(duration))
    cols = 6
    out.parent.mkdir(parents=True, exist_ok=True)
    r = _run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(video), "-vf",
              f"fps=1,scale=320:-1,tile={cols}x{max(1, math.ceil(n / cols))}", "-frames:v", "1", str(out)])
    return out if r.returncode == 0 and out.exists() else None


# ---- 文字 -------------------------------------------------------------------------------------------
def check_text(meta: dict, video: Path, qa_dir: Path, issues: list) -> dict:
    """断行、行数、压脸。返回统计。"""
    overlays = [o for o in meta.get("overlays") or [] if o.get("kind") in ("sub", "text", "panel")]
    face_name = cut_mod.face_detector_name()
    broken = over2 = faced = 0
    for o in overlays:
        lines = [str(x) for x in o.get("lines") or []]
        mid = (float(o["start"]) + float(o["end"])) / 2
        for tok in o.get("protected") or cut_mod.protected_tokens(o.get("full_text") or o.get("text") or "", meta.get("terms") or []):
            present = tok in "".join(lines).replace("\n", "")
            if present and not any(tok in ln for ln in lines):
                broken += 1
                issues.append({"t": mid, "end": o["end"], "type": "金额/数字/专名断行", "severity": "error", "shot": o.get("shot"),
                               "detail": f"「{tok}」被拆到两行：{' / '.join(lines)}", "_grab": {"rects": [o.get("rect")] if o.get("rect") else []}})
        if o.get("kind") in ("sub", "text") and len(lines) > 2:
            over2 += 1
            issues.append({"t": mid, "end": o["end"], "type": "文字超过两行", "severity": "error", "shot": o.get("shot"),
                           "detail": f"{len(lines)} 行没有分屏：{' / '.join(lines)}", "_grab": {"rects": [o.get("rect")] if o.get("rect") else []}})
        for w in o.get("warnings") or []:
            issues.append({"t": mid, "end": o["end"], "type": "排版警告", "severity": "warn", "shot": o.get("shot"), "detail": w})
        rect = o.get("rect")
        faces = None
        if face_name and rect:
            faces = cut_mod.detect_faces(video, [float(o["start"]) + (float(o["end"]) - float(o["start"])) * q for q in (0.3, 0.5, 0.7)])
        o["_final_faces"] = faces
        hit = (cut_mod.face_overlap(rect, faces) > 0) if (faces and rect) else (bool(o.get("face_overlap")) if faces is None else False)
        if hit:
            faced += 1
            issues.append({"t": mid, "end": o["end"], "type": "叠字压脸", "severity": "error", "shot": o.get("shot"),
                           "detail": f"{o.get('kind')}「{(o.get('text') or '').replace(chr(10), '')[:24]}」与人脸框相交（位置 {o.get('position')}）",
                           "_grab": {"rects": [rect], "faces": faces or o.get("faces") or []}})
    return {"overlays": len(overlays), "broken": broken, "over_two_lines": over2, "face_overlap": faced,
            "face_check": "done" if face_name else "未验证（环境没有 OpenCV，需人工看证据帧与接触表）"}


# ---- 台词 -------------------------------------------------------------------------------------------
def sub_groups(meta: dict) -> list[dict]:
    """把分屏的字幕合回一句：同镜、同一原句的相邻页。"""
    out: list[dict] = []
    for o in sorted((o for o in meta.get("overlays") or [] if o.get("kind") == "sub"), key=lambda x: x["start"]):
        full = o.get("full_text") or o.get("text") or ""
        if out and out[-1]["shot"] == o.get("shot") and out[-1]["full_text"] == full and (o.get("page") or [1])[0] > 1:
            out[-1]["end"] = o["end"]
            continue
        out.append({"shot": o.get("shot"), "start": float(o["start"]), "end": float(o["end"]), "full_text": full,
                    "speech": o.get("speech") or full, "audio_from": o.get("audio_from")})
    return out


def check_speech(project: Project, ep: str, meta: dict, video: Path, issues: list, asr_min: float, use_asr: bool) -> dict:
    groups = sub_groups(meta)
    if not groups:
        return {"available": True, "subs": 0, "rows": [], "asr_ok": True, "note": "全片没有字幕台词"}
    words = None
    note = ""
    if use_asr:
        try:
            from review_tool import ASR
            asr = ASR(project)
            if asr.py:
                words = [tuple(w) for w in asr.words([video], fresh=True)[str(video)]]   # 终验不读缓存：缓存文件谁都能写
            else:
                note = "没有 faster-whisper 环境（设 ASR_PY）"
        except (RuntimeError, SystemExit) as err:
            note = f"ASR 失败：{err}"
    else:
        note = "--no-asr"
    if words is None:
        return {"available": False, "subs": len(groups), "rows": [], "asr_ok": None, "note": note or "ASR 不可用"}
    shots = {}
    try:
        shots = {sh["id"]: sh for sh in project.load_shots(ep).get("shots") or []}
    except SystemExit:
        pass
    segs = meta.get("segments") or []
    base_readings = project.get("readings") or {}
    rows, bad = [], False
    covered = []
    for g in groups:
        s0, s1 = g["start"] - 0.25, g["end"] + 0.25
        heard_w = [w for w in words if w[1] > s0 and w[0] < s1]
        covered.append((s0, s1))
        heard = "".join(str(w[2]) for w in heard_w).replace(" ", "")
        sh = shots.get(g["shot"]) or {}
        line_readings = {k: v for d in sh.get("dialogue") or [] if isinstance(d.get("reading"), dict) for k, v in d["reading"].items()}
        readings = {**base_readings, **line_readings}
        key_terms = sorted({t for t in list(sh.get("critical_terms") or []) + list(readings) if t and t in g["speech"]})
        diff = speech_diff(g["speech"], heard, readings, key_terms)
        seg = next((s for s in segs if s["shot"] == g["shot"] and s["start"] - 0.05 <= g["start"] <= s["end"] + 0.05), None)
        row = {"shot": g["shot"], "start": g["start"], "end": g["end"], "subtitle": g["full_text"], "speech": g["speech"], "heard": heard,
               "recall": diff["recall"], "precision": diff["precision"], "critical_changes": diff["critical_changes"], "problems": []}
        missing = [e["expected"] for e in diff["edits"] if e["operation"] in ("delete", "replace") and e["expected"]]
        want_len = len(norm(g["speech"]))
        if diff["recall"] < asr_min:
            row["problems"].append("字幕多于声音")
            issues.append({"t": g["start"], "end": g["end"], "type": "字幕多于声音", "severity": "error", "shot": g["shot"],
                           "detail": f"字幕「{g['full_text']}」识别只对上 {diff['recall']:.0%}；声音里没有：{'、'.join(missing) or '-'}（听到「{heard}」）"})
        if seg and not g.get("audio_from"):
            head = next((e for e in diff["edits"] if e["operation"] in ("delete", "replace") and e["expected_span"][0] == 0), None)
            tail = next((e for e in diff["edits"] if e["operation"] in ("delete", "replace") and e["expected_span"][1] >= want_len), None)
            if head and g["start"] - seg["start"] < 0.5:
                row["problems"].append("疑似裁词（句首）")
                issues.append({"t": seg["start"], "end": g["end"], "type": "疑似裁词", "severity": "error", "shot": g["shot"],
                               "detail": f"切点 {tc(seg['start'])} 后句首「{head['expected']}」没听到（入点可能切进了语气词）；字幕仍是「{g['full_text']}」"})
            if tail and seg["end"] - g["end"] < 0.6:
                row["problems"].append("疑似裁词（句尾）")
                issues.append({"t": g["end"], "end": seg["end"], "type": "疑似裁词", "severity": "error", "shot": g["shot"],
                               "detail": f"切点 {tc(seg['end'])} 前句尾「{tail['expected']}」没听到"})
        key_hits = [c for c in diff["critical_changes"] if c in key_terms or c == "语种疑似不符"]
        if key_hits:
            row["problems"].append("关键词识别分歧")
            issues.append({"t": g["start"], "end": g["end"], "type": "关键词识别分歧", "severity": "confirm", "shot": g["shot"],
                           "detail": f"「{'、'.join(key_hits)}」在识别结果里对不上（听到「{heard}」）；需母语者确认，确认后在 review.json final_qa 写 asr_ok 与 evidence"})
        other = [c for c in diff["critical_changes"] if c not in key_hits]
        if other:
            row["problems"].append("否定词/数字差异")
            issues.append({"t": g["start"], "end": g["end"], "type": "否定词/数字差异", "severity": "error", "shot": g["shot"],
                           "detail": f"「{'、'.join(other)}」在字幕与识别之间数量不同（听到「{heard}」）；听审确认"})
        bad = bad or bool(row["problems"])
        rows.append(row)
    stray = [w for w in words if not any(a <= (w[0] + w[1]) / 2 <= b for a, b in covered) and norm(str(w[2]))]
    runs: list[list] = []
    for w in stray:
        if runs and w[0] - runs[-1][-1][1] < 0.6:
            runs[-1].append(w)
        else:
            runs.append([w])
    for r in runs:
        text = "".join(str(w[2]) for w in r).strip()
        if len(norm(text)) >= 2:
            issues.append({"t": r[0][0], "end": r[-1][1], "type": "有声无字幕", "severity": "warn", "shot": None,
                           "detail": f"识别到「{text}」但这段没有字幕（可能是杂音、串音或漏字幕）"})
    return {"available": True, "subs": len(groups), "rows": rows, "asr_ok": not bad, "note": note}


# ---- 声音 -------------------------------------------------------------------------------------------
def audio_checks(project: Project, meta: dict, video: Path, qa_dir: Path, issues: list, duration: float) -> dict:
    res: dict = {}
    r = _run(["ffmpeg", "-nostdin", "-v", "info", "-i", str(video), "-map", "0:a:0?", "-af", "ebur128=peak=sample", "-f", "null", "-"])
    tail_txt = r.stderr[r.stderr.rfind("Summary:"):] if "Summary:" in r.stderr else ""
    m_i = re.search(r"I:\s+(-?[0-9.]+|-inf) LUFS", tail_txt)
    m_lra = re.search(r"LRA:\s+(-?[0-9.]+) LU", tail_txt)
    m_pk = re.search(r"Peak:\s+(-?[0-9.]+|-inf) dBFS", tail_txt)
    if not m_i:
        issues.append({"t": None, "end": None, "type": "没有音轨", "severity": "error", "detail": "成片测不到响度（没有音轨或音轨损坏）"})
        return {"available": False}
    lufs = float(m_i.group(1)) if m_i.group(1) != "-inf" else -99.0
    peak = float(m_pk.group(1)) if m_pk and m_pk.group(1) != "-inf" else None
    target = float(project.get("loudness") or -16.0)
    res.update(integrated_lufs=lufs, lra=float(m_lra.group(1)) if m_lra else None, sample_peak_dbfs=peak, target_lufs=target)
    if abs(lufs - target) > 1.5:
        issues.append({"t": None, "end": None, "type": "整体响度偏离", "severity": "warn",
                       "detail": f"整体响度 {lufs:.1f} LUFS，目标 {target:.1f}（差 {lufs - target:+.1f}）"})
    ast = _run(["ffmpeg", "-nostdin", "-v", "info", "-i", str(video), "-map", "0:a:0?", "-af", "astats=measure_perchannel=none", "-f", "null", "-"]).stderr
    m_pc = re.findall(r"Peak count:\s+([0-9.]+)", ast)
    m_pl = re.findall(r"Peak level dB:\s+(-?[0-9.]+|-inf)", ast)
    pl = float(m_pl[-1]) if m_pl and m_pl[-1] != "-inf" else None
    pc = float(m_pc[-1]) if m_pc else 0.0
    res.update(astats_peak_db=pl, peak_count=pc)
    clipped = pl is not None and pl >= -0.1 and pc >= 3
    res["clipping"] = clipped
    if clipped:
        issues.append({"t": None, "end": None, "type": "削波", "severity": "error", "detail": f"样本峰值 {pl:.2f} dBFS 触顶 {int(pc)} 次"})
    # 逐镜响度：momentary 每 100ms 一个值，按剪辑段取中位数
    mfile = qa_dir / "momentary.txt"
    _run(["ffmpeg", "-nostdin", "-v", "error", "-i", str(video), "-map", "0:a:0?", "-af",
          "ebur128=metadata=1,ametadata=mode=print:key=lavfi.r128.M:file=" + str(mfile).replace("\\", "/").replace(":", "\\:"), "-f", "null", "-"])
    pts, vals = [], []
    if mfile.exists():
        cur = None
        for ln in mfile.read_text(encoding="utf-8", errors="ignore").splitlines():
            m = re.search(r"pts_time:([0-9.]+)", ln)
            if m:
                cur = float(m.group(1))
                continue
            m = re.search(r"lavfi\.r128\.M=(-?[0-9.]+|-inf)", ln)
            if m and cur is not None and m.group(1) != "-inf":
                pts.append(cur)
                vals.append(float(m.group(1)))
    # 只比对白镜之间：对白镜与无台词反应镜本来就差十几 LU，不算跳变。每段取 momentary 第 90 百分位（说话时的电平），
    # 与同场上一个对白镜比，差 > 8 LU 报跳变
    talk = {o.get("shot") for o in meta.get("overlays") or [] if o.get("kind") == "sub" and not o.get("audio_from")}
    seg_loud = []
    for s in meta.get("segments") or []:
        v = sorted(x for p, x in zip(pts, vals) if s["start"] + 0.4 <= p <= s["end"] and x > -60)
        seg_loud.append({"shot": s["shot"], "scene": s.get("scene"), "start": s["start"], "dialogue": s["shot"] in talk,
                         "p90_lufs": round(v[int(0.9 * (len(v) - 1))], 1) if v else None})
    prev: dict = {}
    for b in seg_loud:
        if not b["dialogue"] or b["p90_lufs"] is None:
            continue
        a = prev.get(b.get("scene"))
        prev[b.get("scene")] = b
        if a is None:
            continue
        jump = b["p90_lufs"] - a["p90_lufs"]
        if abs(jump) > 8.0:
            issues.append({"t": b["start"], "end": None, "type": "镜间响度跳变", "severity": "warn", "shot": b["shot"],
                           "detail": f"同场对白镜 {a['shot']}→{b['shot']} 说话电平 {a['p90_lufs']}→{b['p90_lufs']} LUFS（{jump:+.1f} LU，上限 8）"})
    res["segments"] = seg_loud
    # 片尾：静止画面 + 静音拖尾；画面比声音长
    fz = _run(["ffmpeg", "-nostdin", "-v", "info", "-i", str(video), "-map", "0:v:0", "-vf", "freezedetect=n=0.002:d=0.3", "-f", "null", "-"]).stderr
    starts = [float(x) for x in re.findall(r"freeze_start:\s*([0-9.]+)", fz)]
    ends = [float(x) for x in re.findall(r"freeze_end:\s*([0-9.]+)", fz)]
    tail_freeze = 0.0
    if starts and (len(ends) < len(starts) or ends[-1] >= duration - 0.06):
        tail_freeze = max(0.0, duration - starts[-1])
    sl = _run(["ffmpeg", "-nostdin", "-v", "info", "-i", str(video), "-map", "0:a:0?", "-af", "silencedetect=noise=-55dB:d=0.3", "-f", "null", "-"]).stderr
    s_st = [float(x) for x in re.findall(r"silence_start:\s*(-?[0-9.]+)", sl)]
    s_en = [float(x) for x in re.findall(r"silence_end:\s*([0-9.]+)", sl)]
    tail_silence = 0.0
    if s_st and (len(s_en) < len(s_st) or s_en[-1] >= duration - 0.06):
        tail_silence = max(0.0, duration - s_st[-1])
    streams = stream_durations(video)
    res.update(tail_freeze=round(tail_freeze, 2), tail_silence=round(tail_silence, 2), streams=streams)
    if tail_freeze > 0.3:
        issues.append({"t": duration - tail_freeze, "end": duration, "type": "片尾静止拖尾", "severity": "error",
                       "detail": f"最后 {tail_freeze:.2f}s 画面静止" + (f"且静音 {tail_silence:.2f}s" if tail_silence > 0.3 else "")
                       + "（上限 0.3 秒；多为字幕/叠字合成拖尾或尾帧定格）"})
    v_d, a_d = streams.get("video"), streams.get("audio")
    if v_d and a_d and v_d - a_d > 0.3:
        issues.append({"t": a_d, "end": v_d, "type": "画面比声音长", "severity": "error", "detail": f"视频 {v_d:.2f}s、音频 {a_d:.2f}s，片尾 {v_d - a_d:.2f}s 无声"})
    return res


# ---- 汇总 -------------------------------------------------------------------------------------------
def final_qa(project: Project, ep: str, video: Path | None = None, use_asr: bool = True, asr_min: float | None = None) -> dict:
    video = Path(video) if video else project.final_path(ep)
    if not video.is_file():
        raise SystemExit(f"没有成片 {video}；先运行 cut.py")
    qa_dir = project.review_dir / f"{ep}-final-qa"
    qa_dir.mkdir(parents=True, exist_ok=True)
    cfg = project.cfg.get("final_qa") or {}
    asr_min = max(float(asr_min if asr_min is not None else cfg.get("asr_min", ASR_FLOOR)), ASR_FLOOR)   # 门槛只能收紧
    delivery = video.resolve() == project.final_path(ep).resolve()
    duration = ffprobe_duration(video)
    issues: list[dict] = []
    meta_path = cut_mod.overlays_path(video)
    meta = {}
    if meta_path.is_file():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if abs(float(meta.get("duration") or 0) - duration) > 0.5:
            issues.append({"t": None, "end": None, "type": "元数据与成片不符", "severity": "error",
                           "detail": f"{meta_path.name} 记录片长 {meta.get('duration')}s，成片 {duration:.2f}s；成片可能被改过，重跑 cut.py"})
    else:
        issues.append({"t": None, "end": None, "type": "缺叠字元数据", "severity": "error",
                       "detail": f"没有 {meta_path.name}（旧版 cut.py 剪的）；断行、压脸、字幕与声音比对都做不了，用新版 cut.py 重剪"})
    if meta.get("draft"):
        issues.append({"t": None, "end": None, "type": "草剪冒充成片", "severity": "error",
                       "detail": f"{meta_path.name} 标着 draft=true：这是 cut.py --draft 的草剪，不能当成片交付；审片过准入后用 cut.py 正式剪"})
    try:
        data = project.load_shots(ep)
        from review_quality import cut_issues
        for x in cut_issues(project, ep, data, project.load_review(ep)):
            issues.append({"t": None, "end": None, "type": "剪辑准入不过", "severity": "error", "detail": x})
        missing = expected_line_issues(data, project.load_review(ep), meta) if meta else []
        issues.extend(missing)
    except SystemExit as err:
        data = {}
        issues.append({"t": None, "end": None, "type": "缺 shots.json", "severity": "error", "detail": str(err)})
    text = check_text(meta, video, qa_dir, issues) if meta else {"face_check": "未验证（缺元数据）"}
    speech = check_speech(project, ep, meta, video, issues, asr_min, use_asr) if meta else {"available": False, "asr_ok": None, "rows": [], "note": "缺元数据"}
    audio = audio_checks(project, meta, video, qa_dir, issues, duration)
    sheet = contact_sheet(video, qa_dir / "contact.jpg", duration)
    # 三分项：脚本只能给 asr_ok；听审、同步一律 null，除非 review.json final_qa 有人工写入（必须带 evidence）
    status = {"asr_ok": speech.get("asr_ok"), "listen_ok": None, "sync_ok": None}
    manual = (project.load_review(ep).get("final_qa") or {})
    manual_used, manual_ignored = {}, []
    vsha = media_digest(video)
    if str(manual.get("evidence") or "").strip():
        from review_tool import valid_listener
        if manual.get("video_sha256") != vsha:
            manual_ignored.append("人工补验没带 video_sha256 或不是当前成片（重剪后旧人工结论作废）")
        else:
            confirm_only = speech.get("available") and not any(i["severity"] == "error" and i["type"] in SPEECH_TYPES for i in issues)
            for k in AUDIO_KEYS:
                if manual.get(k) is None:
                    continue
                if k == "asr_ok":
                    if speech.get("asr_ok") is False and confirm_only:   # 只剩「需母语者确认」的关键词分歧时，人工确认能放行
                        status[k] = bool(manual[k]); manual_used[k] = status[k]
                    elif speech.get("asr_ok") is None:
                        manual_ignored.append("asr_ok 人工值不能替代没跑的 ASR")
                    continue
                if status[k] is not None:
                    continue
                if not valid_listener(manual.get("listener")):
                    manual_ignored.append(f"{k} 人工值没写真人 listener（模型/代理不能签听审与同步）")
                    continue
                status[k] = bool(manual[k]); manual_used[k] = status[k]
    for m in manual_ignored:
        issues.append({"t": None, "end": None, "type": "人工补验不采用", "severity": "warn", "detail": m})
    # 证据帧
    for n, it in enumerate(issues, 1):
        g = it.pop("_grab", None) or {}
        if it.get("t") is not None and n <= 80:
            t_ = min(max(0.0, float(it["t"]) + (0.05 if it["type"] not in ("片尾静止拖尾",) else 0.1)), max(0.0, duration - 0.05))
            p = grab(video, t_, qa_dir / f"{n:02d}_{re.sub(r'[^0-9A-Za-z一-鿿]+', '', it['type'])}.jpg", g.get("rects"), g.get("faces"))
            if p:
                it["evidence"] = str(p.relative_to(project.root)) if p.is_relative_to(project.root) else str(p)
    errors = [i for i in issues if i["severity"] == "error"]
    has_dialogue = bool(expected_lines(data, project.load_review(ep))) or ((bool(speech.get("rows")) or bool(sub_groups(meta))) if meta else True)
    conclusion = "PASS" if not errors and (status["asr_ok"] is True or not has_dialogue) else "REVISE"
    report = {"schema": SCHEMA, "episode": ep, "video": str(video.relative_to(project.root)) if video.is_relative_to(project.root) else str(video),
              "video_sha256": vsha, "duration": round(duration, 3), "conclusion": conclusion, "delivery": delivery,
              "draft": bool(meta.get("draft")),
              "asr_ok": status["asr_ok"], "listen_ok": status["listen_ok"], "sync_ok": status["sync_ok"], "manual": manual_used,
              "asr_min": asr_min, "issues": issues, "text": text, "speech": speech, "audio": audio,
              "contact_sheet": str(sheet.relative_to(project.root)) if sheet and sheet.is_relative_to(project.root) else (str(sheet) if sheet else None),
              "overlays_meta": meta_path.name if meta else None}
    jp = project.review_dir / f"{ep}-final-qa.json"
    jp.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    write_md(project, ep, report)
    return report


def write_md(project: Project, ep: str, rep: dict) -> Path:
    unver = "未验证，需人工"
    st = {k: rep[k] for k in AUDIO_KEYS}
    reasons = []
    if any(i["severity"] == "error" for i in rep["issues"]):
        reasons.append(f"{sum(1 for i in rep['issues'] if i['severity'] == 'error')} 个 error 级问题")
    if st["asr_ok"] is None and rep["speech"].get("rows") is not None and rep["conclusion"] == "REVISE":
        reasons.append("台词识别未验证（" + (rep["speech"].get("note") or "ASR 不可用") + "）")
    if st["asr_ok"] is False:
        reasons.append("台词识别不过或有关键词待母语者确认")
    L = [f"结论：{rep['conclusion']}" + (f"（{'；'.join(reasons)}）" if reasons and rep["conclusion"] == "REVISE" else ""), "",
         f"# {ep} 成片终验", "",
         f"成片：{rep['video']}（{rep['duration']:.2f}s，sha256 {rep['video_sha256'][:12]}）；接触表：{rep.get('contact_sheet') or '无'}。", "",
         "## 声音三分项", "",
         f"- 识别正确（asr_ok）：{ {True: '通过', False: '不过', None: '未验证'}[st['asr_ok']] }（字幕原文与成片 ASR 逐句比对，阈值 {rep['asr_min']:.0%}）",
         f"- 听感自然（listen_ok）：{ {True: '通过（人工）', False: '不过（人工）', None: unver}[st['listen_ok']] }",
         f"- 同步正确（sync_ok）：{ {True: '通过（人工）', False: '不过（人工）', None: unver}[st['sync_ok']] }",
         f"- 汇总：{fmt_audio(st)}。脚本不能听审、不能判口型；这两项只有人听过、看过后在 review.json 的 final_qa 写 listen_ok / sync_ok 和 evidence 才会变。", "",
         "## 问题清单", ""]
    if rep["issues"]:
        L += ["| # | 时间码 | 类型 | 严重度 | 说明 | 证据帧 |", "|---|---|---|---|---|---|"]
        sev = {"error": "必须改", "warn": "看一下", "confirm": "需母语者确认"}
        for n, it in enumerate(rep["issues"], 1):
            span = tc(it.get("t")) + (f"–{tc(it['end'])}" if it.get("end") is not None else "")
            L.append(f"| {n} | {span} | {it['type']} | {sev.get(it['severity'], it['severity'])} | {it['detail'].replace('|', '/').replace(chr(10), ' / ')} | {it.get('evidence', '-')} |")
    else:
        L.append("无。")
    tx = rep.get("text") or {}
    L += ["", "## 文字", "",
          f"- 叠字 {tx.get('overlays', 0)} 条；金额/数字/专名断行 {tx.get('broken', 0)}；超过两行未分屏 {tx.get('over_two_lines', 0)}；压脸 {tx.get('face_overlap', 0)}。",
          f"- 人脸检查：{tx.get('face_check')}。"]
    sp = rep.get("speech") or {}
    L += ["", "## 台词", ""]
    if not sp.get("available"):
        L.append(f"- ASR 未做：{sp.get('note') or '不可用'}；台词是否完整、有没有被切词只能人工听。")
    else:
        L.append(f"- 字幕句 {sp.get('subs', 0)}；有问题的句：{sum(1 for r in sp.get('rows') or [] if r['problems'])}。")
        for r in sp.get("rows") or []:
            if r["problems"]:
                L.append(f"  - {tc(r['start'])} {r['shot']}：字幕「{r['subtitle']}」/ 听到「{r['heard']}」→ {'、'.join(r['problems'])}")
    au = rep.get("audio") or {}
    if au.get("available", True) and "integrated_lufs" in au:
        L += ["", "## 声音测量", "",
              f"- 整体响度 {au['integrated_lufs']:.1f} LUFS（目标 {au['target_lufs']:.1f}），LRA {au.get('lra')}，样本峰值 {au.get('sample_peak_dbfs')} dBFS，削波 {'有' if au.get('clipping') else '无'}。",
              f"- 片尾静止 {au.get('tail_freeze', 0):.2f}s、片尾静音 {au.get('tail_silence', 0):.2f}s；流时长 {au.get('streams')}。"]
    L += ["", "人工补验后写进 审查/<EP>-review.json：`\"final_qa\": {\"listen_ok\": true, \"sync_ok\": true, \"evidence\": \"谁、在哪几秒听/看了什么\"}`，再跑一次 final_qa.py。"]
    p = project.review_dir / f"{ep}-final-qa.md"
    p.write_text("\n".join(L) + "\n", encoding="utf-8")
    return p


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("project")
    ap.add_argument("episode")
    ap.add_argument("--video", help="默认 <EP>/成片/<EP>.mp4")
    ap.add_argument("--no-asr", action="store_true", help="不跑 ASR（asr_ok 记为未验证）")
    ap.add_argument("--asr-min", type=float, help="逐句识别召回下限，默认 drama.json final_qa.asr_min 或 0.8")
    a = ap.parse_args(argv)
    pr = Project(a.project)
    rep = final_qa(pr, a.episode, Path(a.video) if a.video else None, not a.no_asr, a.asr_min)
    print(f"{a.episode} 终验：{rep['conclusion']}；{fmt_audio({k: rep[k] for k in AUDIO_KEYS})}；问题 {len(rep['issues'])} 条")
    print("写入", pr.review_dir / f"{a.episode}-final-qa.md", pr.review_dir / f"{a.episode}-final-qa.json")
    return 0 if rep["conclusion"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
