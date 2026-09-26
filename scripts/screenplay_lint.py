#!/usr/bin/env python3
"""剧本格式检查（screenplay.md §1）：只读，不改剧本。

用法：
  screenplay_lint.py <项目目录> <EP>            读 <项目>/<EP>/剧本.md，说话人清单取 <EP>/视觉设定.md 的人物
  screenplay_lint.py <剧本.md> [--speaker 名]... 直接查一个文件
  加 --json 输出机器可读结果。有 error 时退出码 1。

它补 shots_tool.py 看不见的格式问题：parse_screenplay 会把行首"短语：""<!-- 注释：-->"读成对白，
会静默丢掉第一个场次标头之前的正文，也不查场次标头三槽、未知标签和情绪标签。
只证明"格式没写错"，不证明戏好。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import parse_visual  # noqa: E402

TITLE_RE = re.compile(r"^#\s+(?P<ep>EP\d{3,4})(?:\s+.*)?$")
SCENE_LOOSE_RE = re.compile(r"^##\s+(?P<id>EP\d{3,4}-SC\d{3})\b")
SCENE_RE = re.compile(r"^##\s+(?P<id>EP\d{3,4}-SC\d{3}) (?P<space>内外|内|外) · (?P<loc>\S(?:.*?\S)?) · (?P<time>\S.*)$")
SUPPORTED_TAGS = ("VO", "OS", "SFX", "画面文字", "连续性", "转场")
TAG_RE = re.compile(r"^\[(?P<tag>[^\]\r\n]+)\]\s*(?P<body>.*)$")
MALFORMED_TAG_RE = re.compile(r"^\[(?:VO|OS|SFX|画面文字|连续性|转场)(?:\s|：|:)")
VOICE_BODY_RE = re.compile(r"^[^\s：:（）()\[\]#]{1,40}：\S")
DIALECT_RE = re.compile(r"^(?:【[^】]+】|[△▲◆◇])")
DIALOGUE_RE = re.compile(r"^(?P<sp>[^\s：:（）()\[\]#<>【】△▲]{1,24})(?:（(?P<hint>[^（）]*)）)?：(?P<text>\S.*)$")
ASCII_DIALOGUE_RE = re.compile(r"^(?P<sp>[^\s：:（）()\[\]#<>【】]{1,24})(?:（[^（）]*）)?:\s*\S")
EMOTION_RE = re.compile(r"^(?P<emo>[^·\s｜]+)·(?P<i>[^·\s]+)·(?P<s>[^·\s]+)·(?P<v>[^·\s]+)$")
EMOTION_VALUES = ({"弱", "中", "强"}, {"慢", "中", "快"}, {"小", "中", "大"})
READING_RE = re.compile(r"^读音\s*\S+?=\S+(?:[、,，\s]+\S+?=\S+)*$")
CAMERA_RE = re.compile(r"特写|近景|中景|远景|全景|景别|机位|运镜|推镜|拉镜|摇镜|镜头运动|close[- ]?up|wide shot|dolly|\bpan\b", re.I)


def lint_text(text: str, speakers: set[str] | None = None) -> list[dict]:
    """返回 findings：{code, level, line, scene, msg}。speakers=None 时用"只出现一次"推断歧义行。"""
    out: list[dict] = []
    add = lambda code, level, ln, scene, msg: out.append(  # noqa: E731
        {"code": code, "level": level, "line": ln, "scene": scene, "msg": msg})
    lines = text.splitlines()
    title_ep, scene, seen_scenes = None, None, Counter()
    scene_body: dict[str, int] = {}
    dialogues: list[tuple[int, str | None, str, str | None]] = []  # (行, 场, 说话人, 提示)；[VO]/[OS] 不进这张表
    in_comment = None
    for i, raw in enumerate(lines, 1):
        s = raw.strip()
        if in_comment is not None:
            if "-->" in s:
                in_comment = None
            continue
        if not s:
            continue
        if s.startswith("<!--"):
            add("SP04", "warn", i, scene, "剧本里有 HTML 注释；含冒号时会被 parse_screenplay 读成对白。备注移到 项目开发/决策记录.md")
            if "-->" not in s:
                in_comment = i
            continue
        m = TITLE_RE.match(s)
        if m and not s.startswith("##"):
            if title_ep is None:
                title_ep = m["ep"]
            else:
                add("SP01", "error", i, scene, "出现第二个集标题")
            continue
        if s.startswith("#") and not s.startswith("##"):
            add("SP01", "error", i, scene, "集标题须为 `# EP001 集名`")
            continue
        if s.startswith("##"):
            lm = SCENE_LOOSE_RE.match(s)
            if not lm:
                add("SP02", "error", i, scene, "场次标头须为 `## EP001-SC001 内/外/内外 · 地点 · 时间`")
                scene = None
                continue
            scene = lm["id"]
            seen_scenes[scene] += 1
            scene_body.setdefault(scene, 0)
            if seen_scenes[scene] == 2:
                add("SP02", "error", i, scene, f"场次 ID {scene} 重复")
            if not SCENE_RE.match(s):
                add("SP02", "warn", i, scene, "场次标头缺槽：应为 `内/外/内外 · 地点 · 时间`（缺的槽不要按上下文补）")
            if title_ep and not scene.startswith(title_ep + "-"):
                add("SP02", "error", i, scene, f"场次 {scene} 与集标题 {title_ep} 不一致")
            continue
        if scene is None:
            add("SP03", "error", i, None, "正文在第一个场次标头之前（parse_screenplay 会静默丢掉这一行）")
            continue
        scene_body[scene] += 1
        tm = TAG_RE.match(s)
        if tm:
            tag = tm["tag"]
            if tag not in SUPPORTED_TAGS:
                add("SP05", "error", i, scene, f"不支持的标签 [{tag}]；只用 {' '.join('['+t+']' for t in SUPPORTED_TAGS)}")
            elif tag in ("VO", "OS") and not VOICE_BODY_RE.match(tm["body"]):
                add("SP05", "error", i, scene, f"[{tag}] 须写成 `[{tag}] 角色：台词`（全角冒号）")
            continue
        if MALFORMED_TAG_RE.match(s):
            add("SP05", "error", i, scene, "生产标签缺少闭合的 ]")
            continue
        if DIALECT_RE.match(s):
            add("SP06", "warn", i, scene, "制作稿方言（【】/△/▲）：按 screenplay §1b 规范化成本格式")
            continue
        m = DIALOGUE_RE.match(s)
        if m:
            dialogues.append((i, scene, m["sp"], m["hint"]))
            continue
        am = ASCII_DIALOGUE_RE.match(s)
        if am:
            add("SP07", "warn", i, scene, f"「{am['sp']}」后用了半角冒号；对白统一用全角 ：")
            continue
        if CAMERA_RE.search(s):
            add("SP12", "warn", i, scene, "动作行出现镜头术语；剧本不写景别、机位、运镜，画面方案归分镜")

    if in_comment is not None:
        add("SP04", "error", in_comment, None, "HTML 注释没有闭合 -->")
    if title_ep is None:
        add("SP01", "error", 1, None, "缺集标题 `# EP001 集名`")
    for sc, n in scene_body.items():
        if n == 0:
            add("SP11", "warn", None, sc, "场次没有任何正文")

    counts = Counter(sp for _, _, sp, _ in dialogues)
    for ln, sc, sp, hint in dialogues:
        if speakers is not None:
            ambiguous = sp not in speakers
        else:
            ambiguous = counts[sp] == 1 and hint is None
        if ambiguous:
            add("SP08", "warn", ln, sc, f"「{sp}：」不在说话人清单里：是动作行就把行首冒号改成破折号、逗号或动词；是新人物就加进视觉设定")
            continue
        if hint is None:
            add("SP09", "warn", ln, sc, f"{sp} 的台词没有情绪标签（`策略｜情绪·强度·语速·音量`，screenplay §4b）")
            continue
        segs = [x.strip() for x in hint.split("｜") if x.strip()]
        emo = [x for x in segs if EMOTION_RE.match(x)]
        if not emo:
            add("SP09", "warn", ln, sc, f"{sp} 的表演提示里没有 `情绪·强度·语速·音量`（screenplay §4b）")
        for x in emo:
            e = EMOTION_RE.match(x)
            bad = [v for v, ok in zip((e["i"], e["s"], e["v"]), EMOTION_VALUES) if v not in ok]
            if bad:
                add("SP09", "warn", ln, sc, f"情绪标签「{x}」取值不对：强度 弱/中/强，语速 慢/中/快，音量 小/中/大")
        for x in segs:
            if x.startswith("读音") and not READING_RE.match(x):
                add("SP10", "warn", ln, sc, f"读音写法「{x}」应为 `读音 原文=读法`，多个用顿号隔开")
    out.sort(key=lambda f: (f["line"] or 0, f["code"]))
    return out


def project_speakers(project: Path, ep: str) -> set[str] | None:
    names: set[str] = set()
    vis = project / ep / "视觉设定.md"
    if vis.exists():
        names |= set(parse_visual(vis.read_text(encoding="utf-8"))["characters"])
    dj = project / "drama.json"
    if dj.exists():
        try:
            names |= set((json.loads(dj.read_text(encoding="utf-8")).get("readings") or {}).keys())
        except (json.JSONDecodeError, AttributeError):
            pass
    return names or None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("target", help="项目目录，或 剧本.md 路径")
    ap.add_argument("ep", nargs="?", help="集号，如 EP001（target 是项目目录时必填）")
    ap.add_argument("--speaker", action="append", default=[], help="补充说话人（可重复）")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    target = Path(a.target)
    if target.is_dir():
        if not a.ep:
            ap.error("target 是项目目录时要给 EP")
        path, speakers = target / a.ep / "剧本.md", project_speakers(target, a.ep)
    else:
        path, speakers = target, None
    if not path.exists():
        print(f"找不到 {path}", file=sys.stderr)
        return 1
    if a.speaker:
        speakers = (speakers or set()) | set(a.speaker)
    findings = lint_text(path.read_text(encoding="utf-8"), speakers)
    errors = sum(f["level"] == "error" for f in findings)
    if a.json:
        print(json.dumps({"file": str(path), "errors": errors, "findings": findings}, ensure_ascii=False, indent=2))
    else:
        if speakers is None:
            print("（没有说话人清单：歧义冒号行按「只出现一次且无表演提示」推断；给 --speaker 或视觉设定可更准）")
        for f in findings:
            loc = f"L{f['line']}" if f["line"] else "-"
            print(f"{f['code']} {f['level']:5} {loc:>5} {f['scene'] or '':14} {f['msg']}")
        print(f"{path.name}: {errors} error, {len(findings) - errors} warn")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
