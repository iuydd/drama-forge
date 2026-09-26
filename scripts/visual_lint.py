#!/usr/bin/env python3
"""参考图与起始帧提示词的补充检查（离线，只读，不改任何文件）。

  visual_lint.py <项目> [EP001 ...] [--json]     不写集号就查全部已有 shots.json 的集

补 shots_tool.py 的 G 门没覆盖到的几条（references/image-prompts.md、visual-assets.md §6b）：
  V01 error  转面板（refs.json 里 "layout": "multi_view"）直接挂进了起始帧 frame_refs
  V02 warn   派生参考图（refs 非空）第一句没有点名保留 Picture 1 的身份/地点
  V03 warn   派生参考图用了整体改写动词（transform / turn into / make it look like …）
  V04 warn   锁面只以"粘在别的词上"的形式出现在 frame_prompt 里（unchipped … 不算 chipped …）
  V05 warn   参考图或起始帧提示词堆了质量套话（masterpiece / 8K / best quality …）
  V06 warn   转面板不是从已确认的身份图派生的（refs 为空）
有 error 时退出码 1。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import Project  # noqa: E402

REWRITE_RE = re.compile(r"\b(transform(?:s|ed|ing)?|turn(?:s|ed|ing)?\s+(?:\w+\s+){0,2}into|make\s+(?:it|him|her|them)\s+look\s+like|convert(?:s|ed)?\s+(?:\w+\s+){0,2}into|reimagine[sd]?)\b", re.I)
FILLER_RE = re.compile(r"\b(masterpiece|best quality|high(?:est)? quality|ultra[- ]detailed|highly detailed|[48]k(?: resolution)?|award[- ]winning|trending on artstation)\b", re.I)
NEG_BEFORE = re.compile(r"\b(no|not|without|avoid)\s+$", re.I)


def _first_sentences(text: str, n: int = 1) -> str:
    return " ".join(re.split(r"(?<=[.!?])\s+", text.strip())[:n])


def _keeps_picture1(sentence: str) -> bool:
    s = sentence.lower()
    return "picture 1" in s and bool(re.search(r"\b(keep|same)\b", s))


def _clean_hit(phrase: str, text: str) -> str:
    """返回锁面在 text 里的命中类型：clean / glued / none（否定语境里的命中不算）。"""
    p, t = phrase.lower().strip(), text.lower()
    if not p:
        return "none"
    kinds = set()
    for m in re.finditer(re.escape(p), t):
        before = t[:m.start()]
        if NEG_BEFORE.search(before[-12:]):
            continue
        prev_c = t[m.start() - 1] if m.start() > 0 else " "
        next_c = t[m.end()] if m.end() < len(t) else " "
        glued = (p[0].isalnum() and (prev_c.isalnum() or prev_c == "-")) or \
                (p[-1].isalnum() and (next_c.isalnum() or next_c == "-"))
        kinds.add("glued" if glued else "clean")
    if "clean" in kinds:
        return "clean"
    return "glued" if kinds else "none"


def lint(project: Project, episodes: list[str] | None = None) -> list[dict]:
    out: list[dict] = []

    def add(code: str, level: str, where: str, msg: str) -> None:
        out.append({"code": code, "level": level, "where": where, "msg": msg})

    refs = project.load_refs()
    sheets = {rid for rid, r in refs.items() if isinstance(r, dict) and r.get("layout") == "multi_view"}

    for rid, r in refs.items():
        if not isinstance(r, dict):
            continue
        prompt = r.get("prompt") or ""
        deps = r.get("refs") or []
        if rid in sheets and not deps:
            add("V06", "warn", rid, "转面板应以已确认的全身身份图为参考图派生（refs: [\"IMG-<NAME>\"]），不要用文字重新生成一个人（image-prompts §3.3）")
        # 身份/道具变体：保留句在第一句；底板：允许先一句"Photorealistic empty location plate."再写相机操作句
        # 只查"同类派生"（底板派生底板、身份派生身份、道具派生道具）；底板挂道具图当参考不算派生
        head = _first_sentences(prompt, 2 if r.get("kind") == "plate" else 1)
        same_kind = any((refs.get(d) or {}).get("kind") == r.get("kind") for d in deps)
        if same_kind and not r.get("crop_from") and r.get("kind") in ("identity", "prop", "plate") and not _keeps_picture1(head):
            add("V02", "warn", rid, "派生参考图第一句要先点名保留 Picture 1（Keep the same person from Picture 1: … / The same place as Picture 1 …），再写变化（image-prompts §3.4）")
        if deps and REWRITE_RE.search(prompt):
            add("V03", "warn", rid, f"派生参考图用了整体改写动词「{REWRITE_RE.search(prompt).group(0)}」；改用 change only / replace / remove（image-prompts §3.4）")
        if FILLER_RE.search(prompt):
            add("V05", "warn", rid, f"参考图提示词有质量套话「{FILLER_RE.search(prompt).group(0)}」；它不提供识别信息，会挤掉锚点（image-prompts §2）")

    eps = episodes or [ep for ep in project.episodes if project.shots_path(ep).exists()]
    for ep in eps:
        if not project.shots_path(ep).exists():
            add("V00", "warn", ep, "没有 shots.json，跳过")
            continue
        data = json.loads(project.shots_path(ep).read_text(encoding="utf-8"))
        locks = data.get("locks") or []
        for sh in data.get("shots") or []:
            sid = sh.get("id", "?")
            fp = sh.get("frame_prompt") or ""
            for r in sh.get("frame_refs") or []:
                if r in sheets:
                    add("V01", "error", sid, f"{r} 是转面板（multi_view），直接挂进起始帧会把多格版式或分身复制进画面；裁出单格另登记（例如 IMG-<NAME>-BACK）再绑（image-prompts §3.3）")
            for lk in locks:
                scope = lk.get("shots", "all")
                if scope != "all" and sid not in (scope or []):
                    continue
                if _clean_hit(lk.get("phrase") or "", fp) == "glued":
                    add("V04", "warn", sid, f"锁 {lk.get('id')} 的锁面「{lk.get('phrase')}」只以粘在别的词上的形式出现，不算携带；锁面要作为完整词组出现（visual-assets §6b）")
            if FILLER_RE.search(fp):
                add("V05", "warn", sid, f"起始帧提示词有质量套话「{FILLER_RE.search(fp).group(0)}」（storyboard-keyframes §6b）")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("project")
    ap.add_argument("episodes", nargs="*")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    items = lint(Project(a.project), a.episodes or None)
    errors = [i for i in items if i["level"] == "error"]
    if a.json:
        print(json.dumps({"errors": errors, "warns": [i for i in items if i["level"] != "error"]}, ensure_ascii=False, indent=2))
    else:
        for i in items:
            print(f"[{i['level']}] {i['code']} {i['where']}: {i['msg']}")
        print(f"{len(errors)} errors, {len(items) - len(errors)} warnings")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
