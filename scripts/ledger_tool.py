#!/usr/bin/env python3
"""账本补记：让后处理过的视频仍能对上来源（审片门 provenance 认 collected / upscaled / derived 三种记录）。

  ledger_tool.py derive <项目> --src EP001/视频/V_X_t1.mp4 --out EP001/视频/V_X_t2.mp4 --note "底部烧进的字幕模糊"
      记一条 derived：新文件由哪个已收回文件后处理而来（模糊、裁切、调色）。沿用源文件的任务号，提示词与起始帧校验照旧。
  ledger_tool.py rehash-upscaled <项目>
      给旧版 fal 超分记录（缺 sha256）补上当前文件指纹。只在确认超分后没再改过文件时用。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def load(led: Path) -> list[dict]:
    return [json.loads(x) for x in led.read_text(encoding="utf-8").splitlines() if x.strip()] if led.exists() else []


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("derive")
    d.add_argument("project")
    d.add_argument("--src", required=True)
    d.add_argument("--out", required=True)
    d.add_argument("--note", required=True)
    r = sub.add_parser("rehash-upscaled")
    r.add_argument("project")
    a = ap.parse_args()
    root = Path(a.project).resolve()
    led = root / "脚本" / "jobs.jsonl"
    jobs = load(led)
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    new = []
    if a.cmd == "derive":
        src, out = (root / a.src).resolve(), (root / a.out).resolve()
        if not out.is_file() or not src.is_file():
            raise SystemExit("src/out 文件不存在")
        want = src.parts[-3:]
        base = next((j for j in reversed(jobs) if j.get("status") in ("collected", "upscaled", "derived")
                     and j.get("out") and Path(j["out"]).parts[-3:] == want), None)
        if not base:
            raise SystemExit("源文件在账本里没有收回记录，不能补记")
        job = base.get("job") or next((j.get("job") for j in reversed(jobs) if j.get("status") == "collected"
                                       and j.get("out") and Path(j["out"]).parts[-3:] == want), None)
        new.append({"time": now, "status": "derived", "name": out.stem, "kind": "video", "job": job,
                    "src": str(src), "out": str(out), "sha256": sha(out), "note": a.note})
    else:
        for j in jobs:
            if j.get("status") == "upscaled" and not j.get("sha256") and j.get("out") and Path(j["out"]).is_file():
                new.append({**j, "time": now, "sha256": sha(Path(j["out"])), "note": "rehash-upscaled 补指纹"})
    with led.open("a", encoding="utf-8") as f:
        for n in new:
            f.write(json.dumps(n, ensure_ascii=False) + "\n")
    print(f"补记 {len(new)} 条")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
