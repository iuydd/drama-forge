#!/usr/bin/env python3
"""项目布局、配置、剧本/视觉设定解析、种子与 take 编号——各脚本共用。"""
from __future__ import annotations

import json
import os
import re
import subprocess
import zlib
from pathlib import Path

SHOTS_SCHEMA = "short-drama-autopilot/shots/v1"
DRAMA_SCHEMA = "short-drama-autopilot/drama/v1"
REFS_SCHEMA = "short-drama-autopilot/refs/v1"

DEFAULTS = {
    "language": "zh-CN",
    "dialogue_lang": "ja",
    "prompt_lang": "en",
    "aspect": "16:9",
    "width": 1344,
    "height": 768,
    "fps": 24,
    "episodes": 6,
    "target_seconds": 120,
    "shot_seconds": {"default": 5, "min": 4, "max": 10},
    "profiles": {"ref": "krea2_turbo", "frame": "qwen21", "video": "fasth3",
                 "ref_res": "2K", "frame_res": "1K", "video_res": "768p"},
    "one_person_clause": "Only one person in the frame.",
    "no_text_clause": "no text",
    "forbidden_words": [],
    "speech_rates": {"ja": 5.0, "zh": 4.0, "en": 2.5, "ko": 4.5},
    "dialogue_start_max": 1.0,
    "video_dialect": "minimax-h3",
    "video_prompt_keys": ["integrated_multimodal_description", "overall_soundscape", "non_diegetic_music"],
    "loudness": -16.0,
    "subtitle": {"size": 50, "size_long": 40, "long_threshold": 16, "max_width": 1200},
    "budget": {"max_takes": 3, "asr_pass": 0.6},
    "overlays": {},
    "fonts": {},
    "beds": {},
}

# 剧本行：`角色（提示）：台词` / `角色：台词`；生产标签 `[SFX] …`
DIALOGUE_RE = re.compile(r"^(?P<speaker>[^\s：:（(\[\]#>-][^：:（(]{0,15}?)(?P<hint>（[^）]*）)?[：:]\s*(?P<text>.+)$")
SCENE_RE = re.compile(r"^##\s+(?P<id>EP\d{3}-SC\d{3})\b(?P<rest>.*)$")
TAG_RE = re.compile(r"^\[(?P<tag>[A-Za-z一-鿿]+)\]\s*(?P<text>.*)$")
TITLE_RE = re.compile(r"^#\s+(?P<ep>EP\d{3})\s*(?P<title>.*)$")
PUNCT_RE = re.compile(r"[\s、。，,．.！!？?…—‐-「」『』“”\"'（）()《》〈〉:：;；·・]+")


def norm(text: str) -> str:
    return PUNCT_RE.sub("", text or "")


def crc(s: str) -> int:
    return zlib.crc32(s.encode("utf-8")) & 0xFFFFFFFF


def ffprobe_duration(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True).stdout.strip()
    try:
        return float(out)
    except ValueError:
        return 0.0


def speech_seconds(text: str, lang: str, rates: dict) -> float:
    """按语言的每秒字数（英文按词）估台词时长；只是容量检查，不是精确秒表。"""
    rate = float(rates.get(lang, rates.get("zh", 4.0)))
    if lang.startswith("en"):
        n = len([w for w in re.split(r"\s+", text.strip()) if w])
    else:
        n = len(norm(text))
    return n / max(rate, 0.1)


class Project:
    def __init__(self, root: str | os.PathLike):
        self.root = Path(root).resolve()
        cfg_path = self.root / "drama.json"
        if not cfg_path.exists():
            raise SystemExit(f"不是短剧项目（缺 drama.json）：{self.root}")
        self.cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        if self.cfg.get("schema") != DRAMA_SCHEMA:
            raise SystemExit(f"drama.json schema 不是 {DRAMA_SCHEMA}")

    # ---- 配置 ----------------------------------------------------------------
    def get(self, key: str, default=None):
        if key in self.cfg:
            return self.cfg[key]
        if key in DEFAULTS:
            return DEFAULTS[key]
        return default

    def sub(self, key: str) -> dict:
        d = dict(DEFAULTS.get(key, {}))
        d.update(self.cfg.get(key, {}) or {})
        return d

    @property
    def title(self) -> str:
        return self.cfg.get("title", self.root.name)

    @property
    def episodes(self) -> list[str]:
        n = int(self.get("episodes", 6))
        return [f"EP{i:03d}" for i in range(1, n + 1)]

    # ---- 路径 ----------------------------------------------------------------
    def ep_dir(self, ep: str) -> Path:
        return self.root / ep

    def script_path(self, ep: str) -> Path:
        return self.ep_dir(ep) / "剧本.md"

    def visual_path(self, ep: str) -> Path:
        return self.ep_dir(ep) / "视觉设定.md"

    def shots_path(self, ep: str) -> Path:
        return self.ep_dir(ep) / "shots.json"

    @property
    def refs_dir(self) -> Path:
        return self.root / "参考图"

    @property
    def refs_path(self) -> Path:
        return self.refs_dir / "refs.json"

    @property
    def scripts_dir(self) -> Path:
        return self.root / "脚本"

    @property
    def review_dir(self) -> Path:
        return self.root / "审查"

    def review_path(self, ep: str) -> Path:
        return self.review_dir / f"{ep}-review.json"

    def sheets_dir(self, ep: str) -> Path:
        return self.review_dir / f"{ep}-sheets"

    def prompts_dir(self, ep: str) -> Path:
        return self.scripts_dir / "prompts" / ep

    def ref_png(self, ref_id: str) -> Path:
        return self.refs_dir / f"{ref_id}.png"

    def frame_path(self, ep: str, sid: str, take: int) -> Path:
        return self.ep_dir(ep) / "起始帧" / f"F_{sid}_t{take}.png"

    def video_path(self, ep: str, sid: str, take: int) -> Path:
        return self.ep_dir(ep) / "视频" / f"V_{sid}_t{take}.mp4"

    def final_path(self, ep: str) -> Path:
        return self.ep_dir(ep) / "成片" / f"{ep}.mp4"

    # ---- 数据 ----------------------------------------------------------------
    def load_refs(self) -> dict:
        if not self.refs_path.exists():
            return {}
        data = json.loads(self.refs_path.read_text(encoding="utf-8"))
        return data.get("refs", data) if isinstance(data, dict) else {}

    def load_shots(self, ep: str) -> dict:
        p = self.shots_path(ep)
        if not p.exists():
            raise SystemExit(f"缺 {p}")
        data = json.loads(p.read_text(encoding="utf-8"))
        if data.get("schema") != SHOTS_SCHEMA:
            raise SystemExit(f"{p}: schema 不是 {SHOTS_SCHEMA}")
        return data

    def load_review(self, ep: str) -> dict:
        p = self.review_path(ep)
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
        return {"episode": ep, "shots": {}}

    def save_review(self, ep: str, data: dict) -> None:
        self.review_dir.mkdir(parents=True, exist_ok=True)
        self.review_path(ep).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    # ---- take 与种子 ------------------------------------------------------------
    def takes(self, ep: str, sid: str, kind: str) -> list[int]:
        d = self.ep_dir(ep) / ("起始帧" if kind == "frame" else "视频")
        pre = ("F_" if kind == "frame" else "V_") + sid + "_t"
        suf = ".png" if kind == "frame" else ".mp4"
        out = []
        if d.exists():
            for p in d.iterdir():
                if p.name.startswith(pre) and p.name.endswith(suf):
                    try:
                        out.append(int(p.name[len(pre):-len(suf)]))
                    except ValueError:
                        pass
        return sorted(out)

    def chosen_take(self, ep: str, sid: str, kind: str, review: dict | None = None) -> int | None:
        review = review if review is not None else self.load_review(ep)
        rec = (review.get("shots") or {}).get(sid) or {}
        t = rec.get(f"{kind}_take")
        existing = self.takes(ep, sid, kind)
        if t in existing:
            return int(t)
        return existing[-1] if existing else None

    def seed(self, sid: str, kind: str, take: int) -> int:
        base = crc(f"{self.title}:{sid}:{kind}") % 90000 + 10000
        return base + (take - 1) * 1000 + int(os.environ.get("SEED_OFF", "0")) + int(self.get("seed_offset", 0))


# ---- 剧本与视觉设定解析 --------------------------------------------------------------

def parse_screenplay(text: str) -> dict:
    """解析五文档剧本：`# EP001 集名`、`## EP001-SC001 内 · 地点 · 时间`、对白行、标签行、动作段。"""
    doc = {"episode": None, "title": "", "scenes": []}
    cur = None
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
        m = TITLE_RE.match(line)
        if m and doc["episode"] is None:
            doc["episode"], doc["title"] = m["ep"], m["title"].strip()
            continue
        m = SCENE_RE.match(line)
        if m:
            cur = {"id": m["id"], "header": (m["id"] + m["rest"]).strip(), "lines": []}
            doc["scenes"].append(cur)
            continue
        if cur is None:
            continue
        s = line.strip()
        m = TAG_RE.match(s)
        if m:
            cur["lines"].append({"type": "tag", "tag": m["tag"], "text": m["text"], "raw": s})
            continue
        m = DIALOGUE_RE.match(s)
        if m and not s.startswith(("-", "*", ">", "#")):
            cur["lines"].append({"type": "dialogue", "speaker": m["speaker"].strip(), "hint": (m["hint"] or "")[1:-1],
                                 "text": m["text"].strip(), "raw": s})
            continue
        cur["lines"].append({"type": "action", "text": s, "raw": s})
    return doc


def parse_visual(text: str) -> dict:
    out = {"characters": [], "locations": [], "props": [], "sections": {}}
    for m in re.finditer(r"^##\s+(人物|地点|道具)\s*[·・]\s*(.+?)\s*$", text, re.M):
        kind, name = m.group(1), m.group(2).strip()
        key = {"人物": "characters", "地点": "locations", "道具": "props"}[kind]
        out[key].append(name)
        out["sections"][name] = kind
    return out


def dialogue_lines(doc: dict) -> list[dict]:
    """剧本里所有对白，附场景 ID。"""
    out = []
    for sc in doc["scenes"]:
        for ln in sc["lines"]:
            if ln["type"] == "dialogue":
                out.append({"scene": sc["id"], **ln})
    return out


def speakers(doc: dict, visual: dict | None = None) -> set[str]:
    names = {ln["speaker"] for ln in dialogue_lines(doc)}
    if visual:
        names |= set(visual.get("characters", []))
    return names
