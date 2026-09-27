#!/usr/bin/env python3
"""审查文件结构检查（6-审片与剪辑.md §0.3–0.4）：只读。

用法：review_md_check.py 审查/EP001-审查.md [--json]；有 error 时退出码 1。

查的是"结论和问题对得上"，不查问题本身对不对：
- 有 `结论：PASS / REVISE / BLOCKED`；
- 每条问题标题 `## <Blocker|Major|Minor|Note> · <编号> · <标题>`，编号不重复；
- Blocker/Major 必须写全 位置、证据、影响、最小修复、责任阶段（Minor/Note 缺了只 warn）；
- 状态 open / closed / 未决；
- 结论与未关闭问题一致：有未关闭 Blocker → BLOCKED；否则有未关闭 Major → REVISE；否则 PASS；
- 有 `复核方式：`（缺了是 error）、有 `keep:` 清单、模板方括号【】已清掉；
- Blocker/Major 的字段不能只写「-」「无」「同上」这类占位（RV04）；
- 未决（RV09）：Blocker 不能记未决；剧情事实类 Major（标题/类型/影响里有 剧情、事实、必拍、因果、逻辑、情节、动机、设定）不能记未决；
  其余 Major 记未决要写 `轮次：2` 以上和 `决策记录：D-xxx`，结论写 `PASS（未决 N）`，N 等于未决条数；
- 非标准问题格式（`### Major …`、`## Major：R-001`、表格里的 Major 行）脚本看不见，报 RV11 error；
- 文件在项目的 审查/ 下时（按路径找 drama.json）：`剧本指纹：` / `分镜指纹：` 行要等于当前 剧本.md / shots.json（RV12，
  指纹算法见 common.Project.fingerprints，`project_tool.py fingerprint <项目> <EP>` 打印）；审查/agents/*reviewer*/written.sha256
  记过这份文件时，当前 sha 必须和 reviewer 交稿时一致（RV10：主会话不改 reviewer 原稿）。
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
PLACEHOLDERS = ("-", "—", "–", "无", "同上", "见上", "略", "n/a", "N/A", "待定", "TBD", "暂无")
PLOT_RE = re.compile(r"剧情|事实|必拍|因果|逻辑|情节|动机|设定")
NONSTD_HEAD_RE = re.compile(r"^\s*#{1,6}\s*[*_【\[]*\s*(?:Blocker|Major)\b", re.I)
NONSTD_ROW_RE = re.compile(r"^\s*\|(?:[^|\n]*\|)*?\s*[*_]*(?:Blocker|Major)[*_]*\s*\|", re.I)


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
        add("RV02", "error", "缺 `复核方式：独立 reviewer / 自检`（SKILL 硬约束 7：自检要说明）")
    elif not re.search(r"独立|自检|reviewer|self", mm["v"], re.I):
        add("RV02", "warn", f"复核方式「{mm['v']}」应写 独立 reviewer 或 自检")

    findings: list[dict] = []
    cur = None
    for line in body.splitlines():
        if (NONSTD_HEAD_RE.match(line) and not (HEADING_RE.match(line) and FINDING_RE.match(HEADING_RE.match(line)["body"]))) \
                or NONSTD_ROW_RE.match(line):
            add("RV11", "error", f"问题写成了脚本看不见的格式：「{line.strip()[:40]}」；统一写 `## <Blocker|Major|Minor|Note> · <编号> · <标题>` 加字段列表")
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
    deferred_major = 0
    for fd in findings:
        fid, sev, fields = fd["id"], fd["sev"], fd["fields"]
        if fid in seen:
            add("RV05", "error", f"问题编号 {fid} 重复", fid)
        seen.add(fid)
        missing = [k for k in REQUIRED if not (
            any(_filled(fields.get(a)) for a in FIX_ALIASES) if k == "最小修复" else _filled(fields.get(k)))]
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
        if status == "deferred":
            plot = PLOT_RE.search(" ".join([fd["title"], fields.get("类型", ""), fields.get("类别", ""), fields.get("影响", "")]))
            rounds = re.search(r"\d+", fields.get("轮次", "") or "")
            if sev == "Blocker":
                add("RV09", "error", f"Blocker {fid} 不能记未决：修掉或结论写 BLOCKED", fid)
                open_by_sev[sev] += 1
            elif sev == "Major" and plot:
                add("RV09", "error", f"Major {fid} 是剧情事实类缺陷（{plot.group(0)}），不能记未决：修掉或结论写 REVISE", fid)
                open_by_sev[sev] += 1
            elif sev == "Major" and (not rounds or int(rounds.group(0)) < 2 or not re.search(r"D-\d+", " ".join(fields.values()))):
                add("RV09", "error", f"Major {fid} 记未决要写 `轮次：2` 以上和 `决策记录：D-xxx`（两轮没过、已记决策）", fid)
                open_by_sev[sev] += 1
            elif sev == "Major":
                deferred_major += 1
    if verdict:
        if open_by_sev["Blocker"]:
            expect = "BLOCKED"
        elif open_by_sev["Major"]:
            expect = "REVISE"
        else:
            expect = "PASS"
        if verdict != expect:
            add("RV06", "error", f"结论写 {verdict}，但未关闭 Blocker {open_by_sev['Blocker']} 条、Major {open_by_sev['Major']} 条，应为 {expect}")
        vline = vm.group(0) + body[vm.end():].split("\n", 1)[0]
        if verdict == "PASS" and deferred_major:
            n = re.search(r"未决\s*(\d+)", vline)
            if not n or int(n.group(1)) != deferred_major:
                add("RV09", "error", f"有 {deferred_major} 条 Major 记未决，结论要写 `PASS（未决 {deferred_major}）`")
    if not re.search(r"^\s*keep\s*[:：]", body, re.M | re.I):
        add("RV07", "warn", "缺 `keep:` 清单（writer 改完要对它做字面比对）")
    errors = sum(x["level"] == "error" for x in out)
    method = mm["v"].strip() if mm else None
    return {"verdict": verdict, "findings": len(findings), "open": open_by_sev, "deferred_major": deferred_major, "method": method,
            "errors": errors, "issues": out}


def _filled(v) -> bool:
    v = str(v or "").strip()
    return bool(v) and v not in PLACEHOLDERS and len(v) >= 4


def check_file(p: Path) -> dict:
    """check_text 加上项目上下文：输入指纹（RV12）与 reviewer 原稿未被改动（RV10）。"""
    import hashlib
    text = p.read_text(encoding="utf-8")
    r = check_text(text)
    add = lambda code, level, msg: r["issues"].append({"code": code, "level": level, "finding": None, "msg": msg})  # noqa: E731
    root = p.resolve().parent.parent
    m = re.match(r"(EP\d{3})", p.name)
    if (root / "drama.json").exists() and m:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from common import Project
        fps = Project(root).fingerprints(m.group(1))
        for label in ("剧本", "分镜"):
            fm = re.search(rf"{label}指纹\s*[：:]\s*([0-9a-f]{{12}})", text)
            if fm and fps.get(label) and fm.group(1) != fps[label]:
                add("RV12", "error", f"{label}指纹 {fm.group(1)} 不是当前 {label}（{fps[label]}）：{label}在审查之后改过，结论已过期，重新派 reviewer 审")
        cur = hashlib.sha256(p.read_bytes()).hexdigest()
        rel = str(p.resolve().relative_to(root))
        recs = []
        for w in sorted((root / "审查" / "agents").glob("*reviewer*/written.sha256")):
            for ln in w.read_text(encoding="utf-8").splitlines():
                parts = ln.split(None, 1)
                if len(parts) == 2 and parts[1].strip().lstrip("./") == rel:
                    recs.append(parts[0])
        if recs and recs[-1] != cur:
            add("RV10", "error", "这份审查在 reviewer 交稿之后被改过（和 审查/agents/ 里的 written.sha256 不一致）；主会话不改 reviewer 原稿，要改就再派一轮 reviewer")
        elif not recs and r.get("method") and re.search(r"独立|reviewer", r["method"], re.I):
            add("RV10", "warn", "复核方式写独立 reviewer，但 审查/agents/ 里没有这份文件的 reviewer 留档（isolated_agent.sh … reviewer 会自动留档）")
    r["errors"] = sum(x["level"] == "error" for x in r["issues"])
    return r


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("path")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    p = Path(a.path)
    if not p.exists():
        print(f"找不到 {p}", file=sys.stderr)
        return 1
    r = check_file(p)
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
