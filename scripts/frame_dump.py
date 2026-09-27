#!/usr/bin/env python3
"""审片取帧：把每条所选视频按每秒 1 帧导出成单张原尺寸图（不拼网格），审片逐张看。

  frame_dump.py <项目> <EP> [SID ...] [--fps 1]
输出 审查/<EP>-frames/<SID>_t<N>/f_00.jpg …，并打印每镜帧数。网格接触表缩得太小，
三只手、同一人出现两次、身体穿过桌子都看不出来（2026-09-27 EP001 实测漏审），放行只认这里的单张帧。
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("project")
    ap.add_argument("episode")
    ap.add_argument("sids", nargs="*")
    ap.add_argument("--fps", type=float, default=1.0)
    a = ap.parse_args()
    root = Path(a.project).resolve()
    ep = a.episode
    shots = json.loads((root / ep / "shots.json").read_text(encoding="utf-8"))["shots"]
    rv = root / "审查" / f"{ep}-review.json"
    chosen = {}
    if rv.exists():
        for sid, e in (json.loads(rv.read_text(encoding="utf-8")).get("shots") or {}).items():
            if e.get("video_take"):
                chosen[sid] = int(e["video_take"])
    for sh in shots:
        sid = sh["id"]
        if a.sids and sid not in a.sids:
            continue
        takes = sorted(int(re.search(r"_t(\d+)\.mp4$", p.name).group(1)) for p in (root / ep / "视频").glob(f"V_{sid}_t*.mp4"))
        if not takes:
            print(sid, "无视频")
            continue
        t = chosen.get(sid) or takes[-1]
        src = root / ep / "视频" / f"V_{sid}_t{t}.mp4"
        out = root / "审查" / f"{ep}-frames" / f"{sid}_t{t}"
        out.mkdir(parents=True, exist_ok=True)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-vf", f"fps={a.fps},scale=960:-2",
                        "-q:v", "3", str(out / "f_%02d.jpg")], check=True)
        print(sid, f"t{t}", len(list(out.glob("f_*.jpg"))), "帧", out.relative_to(root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
