#!/usr/bin/env python3
"""集中运行 C/D/E 的现有机械检查；完整保留诊断，失败不短路，不自动签发阶段 PASS。

python3 scripts/stage_checks.py <项目> <EP> --stage C|D|E [--json]
C 阶段 shots 检查仍可能报告尚未完成的分镜门；按原规则区分阶段，不自动豁免。
"""
import argparse
import json
from pathlib import Path
import shlex
import subprocess
import sys

HERE = Path(__file__).resolve().parent


def run_checks(project: str, episode: str, stage: str) -> list[dict]:
    commands = {
        "C": [("screenplay_lint.py", project, episode), ("shots_tool.py", "check", project, episode)],
        "D": [("shots_tool.py", "check-refs", project), ("visual_lint.py", project, episode)],
        "E": [("shots_tool.py", "check", project, episode), ("visual_lint.py", project, episode)],
    }
    results = []
    # shots_tool check 会 build_prompts、写 gates.jsonl；同项目顺序跑，避免共享文件竞争。
    for script, *args in commands[stage]:
        command = [sys.executable, str(HERE / script), *args]
        try:
            result = subprocess.run(command, capture_output=True, text=True)
            results.append({"command": command, "exit": result.returncode,
                            "stdout": result.stdout, "stderr": result.stderr})
        except OSError as exc:
            results.append({"command": command, "exit": 2, "stdout": "", "stderr": str(exc)})
    return results


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project")
    parser.add_argument("episode")
    parser.add_argument("--stage", required=True, choices=("C", "D", "E"))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    results = run_checks(args.project, args.episode, args.stage)
    if args.json:
        print(json.dumps({"stage": args.stage, "checks": results}, ensure_ascii=False, indent=2))
    else:
        for result in results:
            print(f"[{result['exit']}] {shlex.join(result['command'])}")
            for stream in ("stdout", "stderr"):
                if result[stream]:
                    print(result[stream], end="" if result[stream].endswith("\n") else "\n")
        print("全部机械检查已运行；请处理完整问题清单。此结果不代替 reviewer 或阶段放行。")
    return 1 if any(result["exit"] != 0 for result in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
