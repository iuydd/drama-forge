#!/usr/bin/env python3
"""项目初始化、状态、下一步。

  project_tool.py init <目录> --title T [--episodes 6] [--dialogue-lang ja] [--genre 智斗复仇] [--target-seconds 120] [--style "..."] [--aspect 16:9]
  project_tool.py status <目录> [--json]
  project_tool.py next <目录>
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import DRAMA_SCHEMA, Project  # noqa: E402

SKILL = Path(__file__).resolve().parents[1]
ASSETS = SKILL / "assets"
STAGES = ["系列简报", "情绪集纲", "剧本", "视觉设定", "shots.json", "门", "参考图", "起始帧", "视频", "审片", "成片"]


def init(root: Path, title: str, episodes: int, dialogue_lang: str, genre: str, target_seconds: int, style: str | None,
         aspect: str) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    cfg = json.loads((ASSETS / "drama.template.json").read_text(encoding="utf-8"))
    cfg.update({"title": title, "created": time.strftime("%Y-%m-%d"), "episodes": episodes, "dialogue_lang": dialogue_lang,
                "genre": genre, "target_seconds": target_seconds, "aspect": aspect})
    if aspect == "9:16":
        cfg["width"], cfg["height"] = 768, 1344
    if style:
        cfg["style"] = style
    (root / "drama.json").write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    for d in ("项目开发", "参考图", "审查", "脚本"):
        (root / d).mkdir(exist_ok=True)
    for i in range(1, episodes + 1):
        for sub in ("", "起始帧", "视频", "成片", "配音"):
            (root / f"EP{i:03d}" / sub).mkdir(parents=True, exist_ok=True)
    for name in ("系列简报.md", "情绪集纲.md", "决策记录.md"):
        dst = root / "项目开发" / name
        if not dst.exists():
            shutil.copy(ASSETS / "templates" / name, dst)
    if not (root / "参考图" / "refs.json").exists():
        shutil.copy(ASSETS / "refs.template.json", root / "参考图" / "refs.json")
    (root / ".gitignore").write_text("脚本/asr_cache.json\n脚本/_staging/\n*.part\n", encoding="utf-8")
    return root


def status(project: Project) -> dict:
    from shots_tool import check
    out = {"title": project.title, "episodes": {}}
    dev = project.root / "项目开发"
    out["系列简报"] = (dev / "系列简报.md").exists() and "【" not in (dev / "系列简报.md").read_text(encoding="utf-8")[:400]
    out["情绪集纲"] = (dev / "情绪集纲.md").exists() and "EP001 |" in (dev / "情绪集纲.md").read_text(encoding="utf-8")
    refs = project.load_refs()
    out["参考图"] = {rid: project.ref_png(rid).exists() for rid in refs}
    for ep in project.episodes:
        e = {}
        e["剧本"] = project.script_path(ep).exists()
        e["视觉设定"] = project.visual_path(ep).exists()
        e["shots.json"] = project.shots_path(ep).exists()
        if e["shots.json"] and e["剧本"]:
            F = check(project, ep)
            e["门"] = {"errors": len(F.errors()), "warns": len(F.warns())}
            data = project.load_shots(ep)
            sids = [s["id"] for s in data.get("shots") or []]
            e["镜数"] = len(sids)
            e["起始帧"] = sum(1 for s in sids if project.takes(ep, s, "frame"))
            e["视频"] = sum(1 for s in sids if project.takes(ep, s, "video"))
            rv = project.load_review(ep)
            e["审片"] = sum(1 for s in sids if ((rv.get("shots") or {}).get(s) or {}).get("verdict"))
        e["成片"] = project.final_path(ep).exists()
        out["episodes"][ep] = e
    return out


def next_step(project: Project) -> str:
    st = status(project)
    if not st["系列简报"]:
        return "阶段 A：写 项目开发/系列简报.md（主爽点类型、四问、人物、能力规则、分集走向）"
    if not st["情绪集纲"]:
        return "阶段 B：填 项目开发/情绪集纲.md（每集一行：受气/底牌/行动/反派失去/兑现/新问题/交接）"
    for ep, e in st["episodes"].items():
        if not e["剧本"]:
            return f"阶段 C：写 {ep}/剧本.md"
        if not e["视觉设定"]:
            return f"阶段 D：写 {ep}/视觉设定.md 并把新人物/地点写进 参考图/refs.json"
        if not e["shots.json"]:
            return f"阶段 E：写 {ep}/shots.json（分镜 + 冻结关键帧 + 起始帧提示词 + 视频提示词）"
        if e.get("门", {}).get("errors"):
            return f"阶段 E：修 {ep} 的门：python3 scripts/shots_tool.py check <项目> {ep}"
        missing_refs = [r for r, ok in st["参考图"].items() if not ok]
        if missing_refs:
            return f"阶段 F：生成参考图 {missing_refs}：python3 scripts/produce.py refs <项目>"
        if e.get("起始帧", 0) < e.get("镜数", 0):
            return f"阶段 G：生成 {ep} 起始帧并逐张目检：python3 scripts/produce.py frames <项目> {ep}"
        if e.get("视频", 0) < e.get("镜数", 0):
            return f"阶段 H：生成 {ep} 视频（带 ASR 自动重拍）：python3 scripts/produce.py videos <项目> {ep} --asr"
        if e.get("审片", 0) < e.get("镜数", 0):
            return f"阶段 I：审片 {ep}：review_tool.py sheets/asr/auto，模型看接触表后 mark"
        if not e["成片"]:
            return f"阶段 J：剪 {ep}：python3 scripts/cut.py <项目> {ep}"
    return "全部集已出成片；可做终审或开新一季"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("init")
    i.add_argument("dir")
    i.add_argument("--title", required=True)
    i.add_argument("--episodes", type=int, default=6)
    i.add_argument("--dialogue-lang", default="ja")
    i.add_argument("--genre", default="")
    i.add_argument("--target-seconds", type=int, default=120)
    i.add_argument("--style")
    i.add_argument("--aspect", default="16:9")
    s = sub.add_parser("status")
    s.add_argument("dir")
    s.add_argument("--json", action="store_true")
    n = sub.add_parser("next")
    n.add_argument("dir")
    a = ap.parse_args(argv)
    if a.cmd == "init":
        root = init(Path(a.dir), a.title, a.episodes, a.dialogue_lang, a.genre, a.target_seconds, a.style, a.aspect)
        print("initialized", root)
        (root / "drama.json").exists() and print(json.dumps({"schema": DRAMA_SCHEMA, "title": a.title}, ensure_ascii=False))
        return 0
    pr = Project(a.dir)
    if a.cmd == "status":
        st = status(pr)
        if a.json:
            print(json.dumps(st, ensure_ascii=False, indent=2))
        else:
            print(f"{st['title']}  系列简报:{'✓' if st['系列简报'] else '✗'} 情绪集纲:{'✓' if st['情绪集纲'] else '✗'} "
                  f"参考图:{sum(st['参考图'].values())}/{len(st['参考图'])}")
            for ep, e in st["episodes"].items():
                g = e.get("门")
                print(f"  {ep} 剧本:{'✓' if e['剧本'] else '✗'} 视觉:{'✓' if e['视觉设定'] else '✗'} shots:{'✓' if e['shots.json'] else '✗'} "
                      f"门:{(str(g['errors']) + 'E/' + str(g['warns']) + 'W') if g else '-'} 镜:{e.get('镜数', '-')} "
                      f"帧:{e.get('起始帧', '-')} 视频:{e.get('视频', '-')} 审片:{e.get('审片', '-')} 成片:{'✓' if e['成片'] else '✗'}")
    elif a.cmd == "next":
        print(next_step(pr))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
