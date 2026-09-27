#!/usr/bin/env python3
"""送审前自检：派 C/E reviewer 之前先把"流程账"清掉，避免 reviewer 一轮轮只报账目问题。

检查项（任一不满足退出码 1，逐条列出）：
- C：screenplay_lint 0 error。
- E：shots_tool check 0 error；高风险镜（adversary_plan.py 判定）最新一轮攻防清单都有「判断」一节；
      已出起始帧的镜，最新一张都有主会话目检记录（review.json frame_review 的 sha256 等于当前文件）。
这些是作者/主会话的活，不算审查轮次；全部满足后再派 reviewer。它不签发 PASS，也不替代 reviewer 的任何判断。

  review_ready.py <项目> <EP> --stage C|E [--no-frames]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import adversary_plan  # noqa: E402


def _errors(out: str) -> int:
    m = re.search(r"(\d+) errors?", out)
    return int(m.group(1)) if m else 0


def check(project: Path, ep: str, stage: str, frames: bool = True) -> list[str]:
    miss = []
    if stage == "C":
        out = subprocess.run([sys.executable, str(HERE / "screenplay_lint.py"), str(project), ep], capture_output=True, text=True)
        n = _errors(out.stdout + out.stderr)
        if n:
            miss.append(f"screenplay_lint {n} error")
        return miss
    out = subprocess.run([sys.executable, str(HERE / "shots_tool.py"), "check", str(project), ep], capture_output=True, text=True)
    n = _errors(out.stdout + out.stderr)
    if n:
        miss.append(f"shots_tool check {n} error")
    nojudge = adversary_plan.status(project, ep)
    if nojudge:
        miss.append("攻防清单缺判断栏：" + " ".join(nojudge))
    if frames:
        rv_p = project / "审查" / f"{ep}-review.json"
        rv = json.loads(rv_p.read_text(encoding="utf-8")).get("shots", {}) if rv_p.exists() else {}
        unseen = []
        for sh in json.loads((project / ep / "shots.json").read_text(encoding="utf-8")).get("shots") or []:
            f = adversary_plan.latest_frame(project, ep, sh["id"])
            if f is None:
                continue
            h = hashlib.sha256(f.read_bytes()).hexdigest()
            fr = (rv.get(sh["id"]) or {}).get("frame_review") or {}
            if str(fr.get("sha256") or "") != h:
                unseen.append(f.name)
        if unseen:
            miss.append(f"起始帧未目检 {len(unseen)} 张：" + " ".join(unseen))
    return miss


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("project")
    ap.add_argument("episode")
    ap.add_argument("--stage", required=True, choices=("C", "E"))
    ap.add_argument("--no-frames", action="store_true", help="起始帧还没出时跳过目检项")
    a = ap.parse_args(argv)
    miss = check(Path(a.project).resolve(), a.episode, a.stage, not a.no_frames)
    for m in miss:
        print("未就绪", m)
    print("可以送审" if not miss else f"{len(miss)} 项未就绪：先补齐再派 reviewer（不算审查轮次）")
    return 1 if miss else 0


if __name__ == "__main__":
    raise SystemExit(main())
