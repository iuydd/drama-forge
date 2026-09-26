#!/usr/bin/env python3
"""审查文件结构检查（review-checklists.md §0.3–0.4）：只读。

用法：review_md_check.py 审查/EP001-审查.md [--json]；有 error 时退出码 1。

查的是"结论和问题对得上"，不查问题本身对不对：
- 有 `结论：PASS / REVISE / BLOCKED`；
- 每条问题标题 `## <Blocker|Major|Minor|Note> · <编号> · <标题>`，编号不重复；
- Blocker/Major 必须写全 位置、证据、影响、最小修复、责任阶段（Minor/Note 缺了只 warn）；
- 状态 open / closed / 未决；
- 结论与未关闭问题一致：有未关闭 Blocker → BLOCKED；否则有未关闭 Major → REVISE；否则 PASS；
- 有 `复核方式：`、有 `keep:` 清单、模板方括号【】已清掉。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

SEVERITIES = ("Blocker", "Major", "Minor", "Note")
VERDICTS = ("PASS", "REVISE", "BLOCKED")
STATUS_ALIASES = {"open": "open", "未关闭": "open", "closed": "closed", "已关闭": "closed",
                  "未决": "deferred", "deferred": "deferred"}
REQUIRED = ("位置", "证据", "影响", "最小修复", "责任阶段")
FIX_ALIASES = ("最小修复", "修订结果", "修复")
COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
VERDICT_RE = re.compile(r"^[-*\s]*\**结论\**\s*[：:]\s*\**\s*(?P<v>[A-Za-z]+)", re.M)
METHOD_RE = re.compile(r"^[-*\s]*\**复核方式\**\s*[：:]\s*(?P<v>\S.*)$", re.M)
HEADING_RE = re.compile(r"^##\s+(?P<body>.+?)\s*$")
FINDING_RE = re.compile(r"^(?P<sev>[A-Za-z]+)\s*·\s*(?P<id>[^·\s]+)\s*·\s*(?P<title>.+)$")
FIELD_RE = re.compile(r"^\s*[-*]\s*(?P<k>[^：:]{1,8})\s*[：:]\s*(?P<v>.*)$")


def check_text(text: str) -> dict:
    out: list[dict] = []
    add = lambda code, level, msg, fid=None: out.append({"code": code, "level": level, "finding": fid, "msg": msg})  # noqa: E731
    body = COMMENT_RE.sub("", text)
    if "【" in body and "】" in body:
        add("RV08", "error", "还有模板方括号【】没填")
    vm = VERDICT_RE.search(body)
    verdict = vm["v"].upper() if vm else None
    if verdict not in VERDICTS:
        add("RV01", "error", f"缺 `结论：PASS / REVISE / BLOCKED`（读到 {vm['v'] if vm else '无'}）")
        verdict = None
    mm = METHOD_RE.search(body)
    if not mm:
        add("RV02", "warn", "缺 `复核方式：独立 reviewer / 自检`（SKILL 硬约束 7：自检要说明）")
    elif not re.search(r"独立|自检|reviewer|self", mm["v"], re.I):
        add("RV02", "warn", f"复核方式「{mm['v']}」应写 独立 reviewer 或 自检")

    findings: list[dict] = []
    cur = None
    for line in body.splitlines():
        h = HEADING_RE.match(line)
        if h:
            fm = FINDING_RE.match(h["body"])
            if fm and fm["sev"] in SEVERITIES:
                cur = {"sev": fm["sev"], "id": fm["id"], "title": fm["title"], "fields": {}}
                findings.append(cur)
            elif fm:
                add("RV03", "error", f"严重程度「{fm['sev']}」不在 {'/'.join(SEVERITIES)} 里", fm["id"])
                cur = None
            else:
                cur = None
            continue
        if cur is not None:
            f = FIELD_RE.match(line)
            if f:
                cur["fields"][f["k"].strip()] = f["v"].strip()

    seen: set[str] = set()
    open_by_sev = {s: 0 for s in SEVERITIES}
    for fd in findings:
        fid, sev, fields = fd["id"], fd["sev"], fd["fields"]
        if fid in seen:
            add("RV05", "error", f"问题编号 {fid} 重复", fid)
        seen.add(fid)
        missing = [k for k in REQUIRED if not (
            any(fields.get(a) for a in FIX_ALIASES) if k == "最小修复" else fields.get(k))]
        if missing:
            add("RV04", "error" if sev in ("Blocker", "Major") else "warn",
                f"{sev} {fid} 缺字段：{'、'.join(missing)}", fid)
        raw = fields.get("状态")
        status = STATUS_ALIASES.get((raw or "").strip().lower()) if raw else None
        if raw is None:
            add("RV04", "warn", f"{fid} 没写状态，按 open 计", fid)
            status = "open"
        elif status is None:
            add("RV04", "error", f"{fid} 状态「{raw}」应为 open / closed / 未决", fid)
            status = "open"
        if status == "open":
            open_by_sev[sev] += 1

    if verdict:
        if open_by_sev["Blocker"]:
            expect = "BLOCKED"
        elif open_by_sev["Major"]:
            expect = "REVISE"
        else:
            expect = "PASS"
        if verdict != expect:
            add("RV06", "error", f"结论写 {verdict}，但未关闭 Blocker {open_by_sev['Blocker']} 条、Major {open_by_sev['Major']} 条，应为 {expect}")
    if not re.search(r"^\s*keep\s*[:：]", body, re.M | re.I):
        add("RV07", "warn", "缺 `keep:` 清单（writer 改完要对它做字面比对）")
    errors = sum(x["level"] == "error" for x in out)
    return {"verdict": verdict, "findings": len(findings), "open": open_by_sev, "errors": errors, "issues": out}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("path")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    p = Path(a.path)
    if not p.exists():
        print(f"找不到 {p}", file=sys.stderr)
        return 1
    r = check_text(p.read_text(encoding="utf-8"))
    if a.json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
    else:
        for x in r["issues"]:
            print(f"{x['code']} {x['level']:5} {x['finding'] or '-':8} {x['msg']}")
        o = r["open"]
        print(f"{p.name}: 结论 {r['verdict']}，问题 {r['findings']} 条（未关闭 Blocker {o['Blocker']} / Major {o['Major']}），{r['errors']} error")
    return 1 if r["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
