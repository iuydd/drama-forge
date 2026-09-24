#!/usr/bin/env python3
"""审片：接触表、ASR 比对、自动选 take、记录取用区间。只读素材，不提交任何生成任务。

  review_tool.py sheets <项目> <EP> [SID ...]          每个 take 一张 2fps 接触表 审查/<EP>-sheets/<sid>_t<n>.jpg
  review_tool.py asr    <项目> <EP> [SID ...]          全部 take 跑 ASR，比对台词，结果写 审查/<EP>-asr.json 和 review.json
  review_tool.py auto   <项目> <EP>                    按规则自动选 take、给 verdict（不改已由人/模型 mark 过的镜）
  review_tool.py report <项目> <EP>                    汇总 审查/<EP>-审片.md
  review_tool.py mark   <项目> <EP> <SID> [--video-take N] [--frame-take N] [--in S] [--out S]
                        [--mode after_last_word|to_end|fixed|full] [--verdict ok|weak|retake|drop|mute] [--speed X] [--note ...]

ASR 用 faster-whisper：优先环境变量 ASR_PY 指向装了它的 python；否则依次试当前 python 和 ~/.venvs/*/bin/python。
模型 ASR_MODEL（默认 medium），语言取 drama.json 的 dialogue_lang。词级时间戳缓存在 脚本/asr_cache.json。
"""
from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import Project, ffprobe_duration, norm  # noqa: E402

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
        return f"{path.name}:{path.stat().st_mtime_ns}"

    def words(self, paths: list[Path]) -> dict[str, list]:
        todo = [p for p in paths if self.key(p) not in self.cache]
        if todo:
            if not self.py:
                raise SystemExit("没有可用的 faster-whisper 环境；设 ASR_PY 指向装了它的 python")
            r = subprocess.run([self.py, "-c", ASR_CODE, self.model, self.lang, *map(str, todo)], capture_output=True, text=True)
            for row in r.stdout.splitlines():
                try:
                    f, ws = json.loads(row)
                except json.JSONDecodeError:
                    continue
                self.cache[self.key(Path(f))] = ws
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
    if want:
        rec["hit"] = round(lcs_ratio(norm(want), norm(heard)), 3)
    else:
        rec["hit"] = None
        rec["stray_voice"] = bool(heard)
    review = project.load_review(ep)
    entry = review.setdefault("shots", {}).setdefault(sid, {})
    entry.setdefault("video_takes", {})[str(take)] = rec
    project.save_review(ep, review)
    return rec


def choose_best(project: Project, ep: str, sid: str, review: dict | None = None, save: bool = True) -> int | None:
    """选 ASR 命中最高的 take；无台词镜里有人声的排最后。review 可由调用方传入并统一保存。"""
    own = review is None
    review = project.load_review(ep) if own else review
    entry = review.setdefault("shots", {}).setdefault(sid, {})
    if entry.get("locked"):
        return entry.get("video_take")
    takes = entry.get("video_takes") or {}
    existing = project.takes(ep, sid, "video")
    if not existing:
        return None
    best = None
    for t in existing:
        rec = takes.get(str(t)) or {}
        score = rec.get("hit")
        if score is None:
            score = -1.0 if rec.get("stray_voice") else 0.5
        if best is None or score > best[0]:
            best = (score, t)
    entry["video_take"] = best[1]
    if save and own:
        project.save_review(ep, review)
    return best[1]


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
    """规则：ASR 达标 = ok；不达标且 take 用尽 = weak；无台词镜有人声 = mute；没有素材 = missing。已 locked 的镜不动。"""
    data = project.load_shots(ep)
    budget = project.sub("budget")
    review = project.load_review(ep)
    for sh in data.get("shots") or []:
        sid = sh["id"]
        entry = review.setdefault("shots", {}).setdefault(sid, {})
        if entry.get("locked"):
            continue
        best = choose_best(project, ep, sid, review, save=False)
        if best is None:
            entry["verdict"] = "missing"
            continue
        rec = (entry.get("video_takes") or {}).get(str(best)) or {}
        if rec.get("hit") is not None:
            if rec["hit"] >= float(budget["asr_pass"]):
                entry["verdict"] = "ok"
            elif len(project.takes(ep, sid, "video")) >= int(budget["max_takes"]):
                entry["verdict"] = "weak"
            else:
                entry["verdict"] = "retake"
        elif rec.get("stray_voice"):
            entry["verdict"] = "mute"
        else:
            entry["verdict"] = "ok"
        entry.setdefault("mode", "after_last_word" if sh.get("dialogue") else "full")
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
        rng = f"{e.get('in', 0)}–{e.get('out') if e.get('out') is not None else 'auto'}（{e.get('mode', 'auto')}）"
        L.append(f"| {sid} | {sh.get('title', '')} | {t or '-'}/{len(project.takes(ep, sid, 'video'))} | {rec.get('duration', 0):.1f}s | {hit} | {heard} | {e.get('verdict', '')} | {rng} | {e.get('note', '')} |")
    L += ["", f"接触表：审查/{ep}-sheets/<镜>_t<take>.jpg（2 帧/秒）。模型看图后用 `review_tool.py mark` 记录取用区间与结论。"]
    project.review_dir.mkdir(parents=True, exist_ok=True)
    p = project.review_dir / f"{ep}-审片.md"
    p.write_text("\n".join(L), encoding="utf-8")
    return p


def mark(project: Project, ep: str, sid: str, **kw) -> dict:
    review = project.load_review(ep)
    e = review.setdefault("shots", {}).setdefault(sid, {})
    for k, v in kw.items():
        if v is not None:
            e[k] = v
    e["locked"] = True
    project.save_review(ep, review)
    return e


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("sheets", "asr"):
        s = sub.add_parser(name)
        s.add_argument("project")
        s.add_argument("episode")
        s.add_argument("sids", nargs="*")
    for name in ("auto", "report"):
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
    m.add_argument("--mode", choices=["after_last_word", "to_end", "fixed", "full"])
    m.add_argument("--verdict", choices=["ok", "weak", "retake", "drop", "mute"])
    m.add_argument("--speed", type=float)
    m.add_argument("--note")
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
    elif a.cmd == "auto":
        rv = auto(pr, a.episode)
        for sid, e in (rv.get("shots") or {}).items():
            print(sid, e.get("verdict"), "take", e.get("video_take"))
    elif a.cmd == "report":
        print("wrote", report(pr, a.episode))
    elif a.cmd == "mark":
        e = mark(pr, a.episode, a.sid, video_take=a.video_take, frame_take=a.frame_take, **{"in": a.in_}, out=a.out,
                 mode=a.mode, verdict=a.verdict, speed=a.speed, note=a.note)
        print(json.dumps(e, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
