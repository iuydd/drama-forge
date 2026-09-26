#!/usr/bin/env python3
"""合并进 drama-forge 的新功能的离线自测。每个 lane 一个独立的 test_* 函数，互不依赖。

  python3 scripts/merged_selftest.py            跑全部 test_*
  python3 scripts/merged_selftest.py hub_tool   只跑名字里含 hub_tool 的
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


def require(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


def _raises_exit(fn, *a, **kw) -> str:
    try:
        fn(*a, **kw)
    except SystemExit as e:
        return str(e)
    raise AssertionError(f"{fn.__name__} 应该拒绝，却成功了")


# ---- 剪辑交付与总控 lane：hub_tool.py -------------------------------------------------
def test_hub_tool() -> None:
    import hub_tool
    from common import Project
    from project_tool import init

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        root = init(tmp / "ws" / "剧A", "测试剧", 1, "ja", "智斗复仇", 30, None, "16:9")
        cfg = json.loads((root / "drama.json").read_text(encoding="utf-8"))
        cfg["api_base"] = "https://relay.example.invalid"
        (root / "drama.json").write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
        (root / "参考图" / "IMG-A.png").write_bytes(b"png")
        (root / "参考图" / "素材-a").mkdir()
        (root / "参考图" / "素材-a" / "raw.png").write_bytes(b"private")
        (root / "脚本" / "jobs.jsonl").write_text("{}\n", encoding="utf-8")
        (root / "EP001" / "剧本.md").write_text("# EP001 测试\n", encoding="utf-8")
        (root / "EP001" / "api_token.txt").write_text("x", encoding="utf-8")

        # overview：扫描工作区、HTML 快照
        rows = hub_tool.overview([str(tmp / "ws")])
        require(len(rows) == 1 and rows[0]["title"] == "测试剧" and "EP001" in rows[0]["episodes"], f"overview: {rows}")
        page = hub_tool.overview_html(rows)
        require("<title>短剧进度总览</title>" in page and "测试剧" in page and "prefers-color-scheme" in page, "overview html")

        # export：排除私有与账本，manifest 不声称审批
        pr = Project(root)
        out = hub_tool.export(pr, tmp / "out")
        man = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        paths = {r["path"] for r in man["files"]}
        require(man["asserts_approval"] is False and man["tool"] == hub_tool.EXPORT_TOOL, "manifest")
        require("EP001/剧本.md" in paths and "参考图/IMG-A.png" in paths and "参考图/refs.json" in paths, f"export 缺文件: {paths}")
        require(not any(p.startswith("脚本/") or "素材-a" in p or "token" in p for p in paths), f"export 带出了私有文件: {paths}")
        require(json.loads((out / "drama.json").read_text(encoding="utf-8"))["api_base"] is None, "api_base 未清空")
        require(len((out / "checksums.sha256").read_text(encoding="utf-8").splitlines()) == len(man["files"]), "checksums 行数")
        nomedia = hub_tool.export(pr, tmp / "out2", media="none")
        require(not (nomedia / "参考图" / "IMG-A.png").exists(), "--media none 仍带了图片")
        require("已存在" in _raises_exit(hub_tool.export, pr, tmp / "out"), "重复导出未要求 --overwrite")
        hub_tool.export(pr, tmp / "out", overwrite=True)
        (tmp / "foreign").mkdir()
        (tmp / "foreign" / "keep.txt").write_text("x", encoding="utf-8")
        require("拒绝覆盖" in _raises_exit(hub_tool.export, pr, tmp / "foreign", overwrite=True), "覆盖了非导出目录")
        require((tmp / "foreign" / "keep.txt").exists(), "非导出目录被删")
        require("项目之外" in _raises_exit(hub_tool.export, pr, root / "导出"), "允许导出到项目内")

        # 剪辑单解析 + grade 滤镜
        (root / "EP001" / "剪辑单.md").write_text(
            "# EP001 剪辑单\n\n| # | 镜 | take | 取用 | 时长 | 成片位置 | 字幕 | 叠加 | 结论 |\n|---|---|---|---|---|---|---|---|---|\n"
            "| 1 | EP001-S01 | 1 | 0.00–1.50（after_last_word） | 1.50s | 0.0–1.5s | 你好 | 无 | ok |\n"
            "| 2 | EP001-S02 | 2 | 0.20–1.70（full） | 1.50s过短：反应镜下限 1.5 s | 1.5–3.0s | 无 | 无 | ok |\n", encoding="utf-8")
        cr = hub_tool.cut_rows(pr, "EP001")
        require([(r["shot"], r["start"], r["end"]) for r in cr] == [("EP001-S01", 0.0, 1.5), ("EP001-S02", 1.5, 3.0)], f"cut_rows: {cr}")
        grade_path = root / "审查" / "EP001-grade.json"
        grade_path.write_text(json.dumps({"shots": {"EP001-S02": {"brightness": 0.06, "warmth": -6}}, "grain": 6}), encoding="utf-8")
        vf = hub_tool.grade(pr, "EP001", dry=True)
        require("eq=brightness=0.06:enable='between(t,1.500,2.999)'" in vf and "colorbalance=rm=-0.0600:bm=0.0600" in vf
                and "noise=alls=6" in vf, f"grade filter: {vf}")
        grade_path.write_text(json.dumps({"shots": {"EP001-S02": {"brightness": 0.5}}}), encoding="utf-8")
        require("超出" in _raises_exit(hub_tool.grade, pr, "EP001", dry=True), "越界校正未拒绝")
        grade_path.write_text(json.dumps({"shots": {"EP001-S09": {"brightness": 0.1}}}), encoding="utf-8")
        require("不在当前剪辑单" in _raises_exit(hub_tool.grade, pr, "EP001", dry=True), "未知镜号未拒绝")

        # 有 ffmpeg 时：真测量、真调色
        if shutil.which("ffmpeg") and shutil.which("ffprobe"):
            film = pr.final_path("EP001")
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=0x406080:s=1344x768:d=3:r=24", "-f", "lavfi",
                            "-i", "sine=frequency=440:duration=3", "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
                            str(film)], check=True)
            res = hub_tool.measure(pr, "EP001")
            require(abs(res["实测时长"] - 3.0) < 0.2 and res["画幅是否等于项目设定"] is True, f"measure 基本项: {res}")
            require(isinstance(res["实测响度 LUFS"], float) and len(res["逐镜色彩"]) == 2 and "平均亮度" in res["逐镜色彩"][0], f"measure: {res}")
            require(res["台词完整性"].startswith("未测"), "未测项被写成通过")
            grade_path.write_text(json.dumps({"shots": {"EP001-S02": {"brightness": 0.1}}}), encoding="utf-8")
            dst = hub_tool.grade(pr, "EP001")
            require(dst.exists() and dst.name == "EP001_graded.mp4" and film.exists(), "grade 输出")
        else:
            print("  (跳过 measure/grade 实跑：没有 ffmpeg)")


# ---- 视觉资产 / 图片提示词 / 分镜 lane：visual_lint.py ------------------------------------
def test_visual_lint() -> None:
    """visual_lint.py：转面板误挂（V01）、派生保留句（V02）、改写动词（V03）、锁面粘词（V04）、质量套话（V05）、转面板来源（V06）。失败时抛 AssertionError。"""
    import json
    import visual_lint
    from common import DRAMA_SCHEMA, REFS_SCHEMA, SHOTS_SCHEMA, Project

    def need(cond: bool, msg: str) -> None:
        if not cond:
            raise AssertionError(msg)

    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "剧V"
        (root / "参考图").mkdir(parents=True)
        (root / "EP001").mkdir()
        (root / "drama.json").write_text(json.dumps({"schema": DRAMA_SCHEMA, "title": "V", "episodes": 1}, ensure_ascii=False), encoding="utf-8")
        refs = {"schema": REFS_SCHEMA, "refs": {
            "IMG-A": {"kind": "identity", "subject": "甲", "refs": [], "prompt": "Photorealistic full-body photo of one woman about 160 cm tall, no text."},
            "IMG-A-FACE": {"kind": "identity", "subject": "甲", "refs": ["IMG-A"],
                           "prompt": "Keep the same person from Picture 1: same face, hairline, skin tone and build. Head-and-shoulders framing, no text."},
            "IMG-A-RAIN": {"kind": "identity", "subject": "甲", "refs": ["IMG-A"],
                           "prompt": "Transform her into a rain-soaked version wearing an orange raincoat. Masterpiece, 8K, no text."},
            "IMG-A-SHEET": {"kind": "identity", "subject": "甲", "layout": "multi_view", "refs": [],
                            "prompt": "Character turnaround of one woman, five views, no labels, no text."},
            "IMG-A-BACK": {"kind": "identity", "subject": "甲", "refs": ["IMG-A-SHEET"], "crop_from": "IMG-A-SHEET",
                           "prompt": "Back view cropped from the turnaround sheet, no text."},
            "IMG-PLATE-A": {"kind": "plate", "refs": [], "prompt": "Photorealistic empty location plate of a corridor. No people, no text."},
            "IMG-PROP-CAR": {"kind": "prop", "refs": [], "prompt": "A red sports car, no hands, no text."},
            "IMG-PLATE-D": {"kind": "plate", "refs": ["IMG-PROP-CAR"],
                            "prompt": "Photorealistic empty showroom plate with the red car of Picture 1 on the left. No people, no text."},
            "IMG-PLATE-B": {"kind": "plate", "refs": ["IMG-PLATE-A"],
                            "prompt": "Photorealistic empty location plate. Turn the camera around 180 degrees inside the same place as Picture 1. No people, no text."},
            "IMG-PLATE-C": {"kind": "plate", "refs": ["IMG-PLATE-A"],
                            "prompt": "A corridor seen from the east end. Dim light. No people, no text."},
        }}
        (root / "参考图" / "refs.json").write_text(json.dumps(refs, ensure_ascii=False), encoding="utf-8")
        shots = {"schema": SHOTS_SCHEMA, "locks": [
            {"id": "LOCK-MUG", "phrase": "chipped white enamel mug", "subject": "甲", "shots": "all"},
            {"id": "LOCK-COAT", "phrase": "orange raincoat", "subject": "甲", "shots": ["EP001-S02"]}],
            "shots": [
                {"id": "EP001-S01", "frame_refs": ["IMG-PLATE-B", "IMG-A-SHEET"],
                 "frame_prompt": "Medium shot. She holds an unchipped white enamel mug, best quality, no text."},
                {"id": "EP001-S02", "frame_refs": ["IMG-PLATE-B", "IMG-A-BACK"],
                 "frame_prompt": "Medium shot. She holds a chipped white enamel mug and wears an orange raincoat, no text."},
            ]}
        (root / "EP001" / "shots.json").write_text(json.dumps(shots, ensure_ascii=False), encoding="utf-8")

        got = {(i["code"], i["where"]) for i in visual_lint.lint(Project(root))}
        want = {("V01", "EP001-S01"), ("V04", "EP001-S01"), ("V05", "EP001-S01"),
                ("V02", "IMG-A-RAIN"), ("V03", "IMG-A-RAIN"), ("V05", "IMG-A-RAIN"),
                ("V06", "IMG-A-SHEET"), ("V02", "IMG-PLATE-C")}
        need(want <= got, f"缺少应报的项：{sorted(want - got)}；实际 {sorted(got)}")
        for bad in [("V02", "IMG-A-FACE"), ("V02", "IMG-PLATE-B"), ("V02", "IMG-A-BACK"), ("V02", "IMG-PLATE-D"),
                    ("V04", "EP001-S02"), ("V01", "EP001-S02")]:
            need(bad not in got, f"误报 {bad}")
        need(visual_lint._clean_hit("orange raincoat", "no orange raincoat here") == "none", "否定语境不算命中")
        need(visual_lint._clean_hit("pale blue knit", "a pale blue knitwear-print fleece") == "glued", "粘词判定")
        need(visual_lint.main([str(root)]) == 1, "有 error 时 CLI 应返回 1")


# ---- 剧本与审查 lane：screenplay_lint.py、review_md_check.py ------------------------------
_SP_GOOD = """# EP001 测试

## EP001-SC001 内 · 三楼走廊 · 日

[连续性] 在场：夏樹（楼梯口）、鬼塚（走廊中间）；画外：先生（楼梯下方）

夏樹抱着钱箱走到楼梯口。鬼塚的运动包拉链半开，露出同款钱箱的角。

鬼塚（拦路要钱｜威胁·中·慢·小）：売上、渡せよ。

夏樹（顶回去｜强装镇定·弱·中·中｜读音 売上=うりあげ）：無理。これ、先生に届けんだよ。

[OS] 先生：何してる！

[SFX] 楼梯下方传来上楼的脚步声。

[连续性] 钱箱在夏樹左臂；鬼塚包里有假箱，老师正上楼。必拍：①鬼塚包里露出同款钱箱的角 ②夏樹把钱箱换到左臂护住 ③鬼塚听到脚步声回头看楼梯
"""

_SP_BAD = """开场白
# EP001 测试
## EP001-SC001 内 · 走廊 · 日
<!-- 待确认：年份 -->
他写下两个字：军宣。
鬼塚：おい。
鬼塚（威胁｜愤怒·超强·快·大）：返せ！
鬼塚: 待て
[OS] 先生何してる
[BGM] 音乐
【特写】钱箱
夏樹推门，近景看钱箱。
## EP001-SC001 内 · 走廊
## EP002-SC003 外 · 楼梯 · 日
"""


def test_screenplay_lint() -> None:
    """screenplay_lint.py：标头前正文、注释、行首冒号歧义、情绪标签、半角冒号、未知标签、方言、镜头术语、场次标头、空场。"""
    import subprocess
    import tempfile
    from screenplay_lint import lint_text

    here = Path(__file__).resolve().parent
    f = lint_text(_SP_GOOD, {"夏樹", "鬼塚"})
    require(not f, f"合格剧本应 0 finding，实际 {[x['code'] for x in f]}")
    f = lint_text(_SP_BAD, {"夏樹", "鬼塚"})
    got = {x["code"] for x in f}
    for code in ("SP02", "SP03", "SP04", "SP05", "SP06", "SP07", "SP08", "SP09", "SP11", "SP12", "SP13", "SP14"):
        require(code in got, f"坏剧本应报 {code}，实际 {sorted(got)}")
    require(len([x for x in f if x["code"] == "SP02" and x["level"] == "error"]) == 2, "SP02 error 应为重复 ID + 集号不一致两条")
    amb = [x for x in f if x["code"] == "SP08"]
    require(len(amb) == 1 and "他写下两个字" in amb[0]["msg"], "只应把「他写下两个字：」当歧义行")
    require(len([x for x in f if x["code"] == "SP09" and "取值不对" in x["msg"]]) == 1, "情绪取值「超强」应被指出")
    f = lint_text("# EP001 t\n\n## EP001-SC001 内 · 屋 · 夜\n\n第二格：一只手把杯子推过去。\n\n"
                  "甲（问｜平静·弱·中·中）：你来了。\n\n甲（问｜平静·弱·中·中）：坐。\n", None)
    require([x["code"] for x in f if x["code"] not in ("SP13", "SP14")] == ["SP08"], f"无清单推断应只报行首冒号行，实际 {[x['code'] for x in f]}")
    ex = here.parent / "assets" / "example"
    if (ex / "EP001" / "剧本.md").exists():
        r = subprocess.run([sys.executable, str(here / "screenplay_lint.py"), str(ex), "EP001"], capture_output=True, text=True)
        require(r.returncode == 0, f"示例项目剧本应 0 error：{r.stdout[-300:]}")
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "剧本.md"
        p.write_text(_SP_BAD, encoding="utf-8")
        r = subprocess.run([sys.executable, str(here / "screenplay_lint.py"), str(p), "--json"], capture_output=True, text=True)
        require(r.returncode == 1 and '"errors"' in r.stdout, "CLI 有 error 时应退出码 1 且输出 JSON")


_RV_OK = """# EP001 审查（阶段 C）

- 范围：EP001/剧本.md
- 结论：REVISE
- 复核方式：独立 reviewer

## Major · R-001 · 空箱凭空出现
- 位置：剧本.md / EP001-SC003
- 证据：SC003 之前没有交代第二个箱子。
- 影响：调包读不出来。
- 最小修复：SC001 加一拍露出假箱。
- 责任阶段：C（编剧）
- 状态：open

## Minor · R-002 · 单句超长
- 位置：剧本.md / EP001-SC002
- 证据：「……」24 字。
- 影响：口型装不下。
- 最小修复：拆成两句。
- 责任阶段：C（编剧）
- 状态：closed

## 母语审读

| 位置 | 原句 | 问题类型 | 改写 |
|---|---|---|---|

keep:
- EP001-SC002 让开那四拍
"""


def test_review_md_check() -> None:
    """review_md_check.py：结论与未关闭问题一致、Blocker/Major 字段齐全、编号不重复、复核方式与 keep、模板未填。"""
    from review_md_check import check_text

    def codes(r, level):
        return {x["code"] for x in r["issues"] if x["level"] == level}

    r = check_text(_RV_OK)
    require(r["errors"] == 0 and r["verdict"] == "REVISE" and r["open"]["Major"] == 1, f"合格审查应 0 error：{r['issues']}")
    require("RV06" in codes(check_text(_RV_OK.replace("结论：REVISE", "结论：PASS")), "error"), "未关闭 Major 写 PASS 应报 RV06")
    deferred = _RV_OK.replace("- 状态：open", "- 状态：未决")
    require("RV09" in codes(check_text(deferred.replace("结论：REVISE", "结论：PASS")), "error"), "首轮就记未决（没写轮次和决策记录）应报 RV09")
    deferred = deferred.replace("- 状态：未决", "- 轮次：2\n- 决策记录：D-004\n- 状态：未决")
    require("RV06" in codes(check_text(deferred), "error"), "Major 未决后仍写 REVISE 应报 RV06")
    require("RV09" in codes(check_text(deferred.replace("结论：REVISE", "结论：PASS")), "error"), "有未决 Major 却只写 PASS（不写未决 N）应报 RV09")
    require(check_text(deferred.replace("结论：REVISE", "结论：PASS（未决 1）"))["errors"] == 0, "两轮未过、记了决策的非剧情 Major 可以 PASS（未决 1）")
    plot = deferred.replace("空箱凭空出现", "必拍事实：空箱凭空出现").replace("结论：REVISE", "结论：PASS（未决 1）")
    require("RV09" in codes(check_text(plot), "error"), "剧情事实类 Major 不能记未决")
    blk = _RV_OK.replace("## Major · R-001", "## Blocker · R-001").replace("- 状态：open", "- 轮次：3\n- 决策记录：D-004\n- 状态：未决")
    require("RV09" in codes(check_text(blk.replace("结论：REVISE", "结论：PASS")), "error"), "Blocker 不能记未决")
    require("RV04" in codes(check_text(_RV_OK.replace("- 证据：SC003 之前没有交代第二个箱子。", "- 证据：-")), "error"), "Major 字段只写 - 应报 RV04")
    require("RV11" in codes(check_text(_RV_OK + "\n### Major · R-003 · 藏起来的问题\n| R-004 | Major | 表格里的问题 |\n"), "error"), "非标准问题格式应报 RV11")
    require("RV06" in codes(check_text(_RV_OK.replace("## Major · R-001", "## Blocker · R-001")), "error"), "未关闭 Blocker 应要求 BLOCKED")
    require("RV04" in codes(check_text(_RV_OK.replace("- 证据：SC003 之前没有交代第二个箱子。\n", "")), "error"), "Major 缺证据应报 RV04")
    require("RV05" in codes(check_text(_RV_OK.replace("R-002", "R-001")), "error"), "编号重复应报 RV05")
    r2 = check_text(_RV_OK.replace("keep:\n", "").replace("- 复核方式：独立 reviewer\n", ""))
    require("RV02" in codes(r2, "error") and "RV07" in codes(r2, "warn"), "缺复核方式应报 error、缺 keep 应 warn")
    require("RV01" in codes(check_text(_RV_OK.replace("结论：REVISE", "结论：APPROVE")), "error"), "非 PASS/REVISE/BLOCKED 应报 RV01")
    tpl = Path(__file__).resolve().parent.parent / "assets" / "templates" / "审查.md"
    if tpl.exists():
        require("RV08" in codes(check_text(tpl.read_text(encoding="utf-8")), "error"), "未填模板应被 RV08 拦下")
    # 项目上下文：剧本指纹过期 → RV12；reviewer 交稿后被主会话改过 → RV10
    import hashlib
    import tempfile
    from common import Project
    from project_tool import init
    from review_md_check import check_file
    with tempfile.TemporaryDirectory() as td:
        root = init(Path(td) / "p", "审查指纹", 1, "ja", "测试", 30, None, "16:9")
        (root / "EP001" / "剧本.md").write_text(_SP_GOOD, encoding="utf-8")
        fp = Project(root).fingerprints("EP001")["剧本"]
        rv = root / "审查" / "EP001-审查.md"
        rv.write_text(_RV_OK.replace("- 复核方式：独立 reviewer", f"- 复核方式：独立 reviewer\n- 剧本指纹：{fp}"), encoding="utf-8")
        require(check_file(rv)["errors"] == 0, "指纹对得上的审查 0 error")
        (root / "EP001" / "剧本.md").write_text(_SP_GOOD + "\n夏樹转身下楼。\n", encoding="utf-8")
        require("RV12" in codes(check_file(rv), "error"), "剧本改过、审查指纹过期应报 RV12")
        (root / "EP001" / "剧本.md").write_text(_SP_GOOD, encoding="utf-8")
        ag = root / "审查" / "agents" / "20260926T000000Z-reviewer-1"
        ag.mkdir(parents=True)
        (ag / "written.sha256").write_text(f"{hashlib.sha256(rv.read_bytes()).hexdigest()}  审查/EP001-审查.md\n", encoding="utf-8")
        require(check_file(rv)["errors"] == 0, "reviewer 原稿未改 0 error")
        rv.write_text(rv.read_text(encoding="utf-8").replace("- 状态：open", "- 状态：closed").replace("结论：REVISE", "结论：PASS"), encoding="utf-8")
        require("RV10" in codes(check_file(rv), "error"), "主会话改了 reviewer 原稿应报 RV10")


# ---- 子代理任务包 lane：task_pack.py 与 isolated_agent.sh 的包校验（用例在 test_task_pack.py） --------------------
def test_task_pack() -> None:
    import io
    import unittest
    import test_task_pack
    r = unittest.TextTestRunner(stream=io.StringIO()).run(unittest.defaultTestLoader.loadTestsFromModule(test_task_pack))
    require(r.wasSuccessful(), f"{len(r.failures)} failure / {len(r.errors)} error（python3 scripts/test_task_pack.py 看详情）")


def main(argv: list[str]) -> int:
    # 兼容两种写法：merged_selftest.py NAME 与 merged_selftest.py -k NAME（references/providers.md 用后者）
    only = argv[argv.index("-k") + 1] if "-k" in argv[:-1] else (argv[1] if len(argv) > 1 else "")
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f) and only in n]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"ok   {name}")
        except Exception as e:  # noqa: BLE001  每个 lane 独立报告
            failed += 1
            print(f"FAIL {name}: {e}")
    print(f"{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0



def test_video_produce_providers() -> None:
    """providers.py：各官方通道的请求体编译、硬条件拒绝、参考编号、账本纪律（先入账、收回不重投、拒绝记 not_submitted）。"""
    import base64
    import json
    import os
    import tempfile

    import providers as P
    from h3_client import SubmissionUnknown

    def must_fail(fn, text):
        try:
            fn()
        except (ValueError, P.ProviderError) as exc:
            assert text in str(exc), f"expected {text!r} in {exc}"
        else:
            raise AssertionError(f"expected failure: {text}")

    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
    mp4 = b"\x00\x00\x00\x18ftypisom" + b"\x00" * 24
    ref = {"path": "起始帧/F_S01_t1.png", "role": "first_frame", "label": "S01 起始帧",
           "may_control": ["开场构图"], "must_not_control": ["终点姿态"]}
    face = {**ref, "path": "参考图/IMG-A.png", "role": "reference_image", "label": "女主身份图",
            "may_control": ["长相"], "must_not_control": ["构图"]}
    video = {"kind": "video", "model": "user-chosen-model", "prompt": "integrated_multimodal_description: [Shot 1] x",
             "out": "视频/V_S01_t1.mp4", "references": [ref], "parameters": {"duration": 6, "resolution": "768P"}}

    # H3 官方：时长/分辨率按开通范围；首帧与参考互斥；文生必须显式 ratio；参考约束按 <Picture N> 追加
    body = P.compile_minimax_video(video, ["data:image/png;base64,AA=="], durations=(4, 15), resolutions={"768P", "2K"})
    assert body["duration"] == 6 and body["content"][1]["role"] == "first_frame" and "<Picture 1>" in body["content"][0]["text"]
    must_fail(lambda: P.compile_minimax_video({**video, "parameters": {"duration": 16, "resolution": "768P"}}, ["u"],
                                              durations=(4, 15), resolutions={"768P"}), "duration")
    must_fail(lambda: P.compile_minimax_video({**video, "references": [ref, face]}, ["u", "u"],
                                              durations=(4, 15), resolutions={"768P"}), "互斥")
    must_fail(lambda: P.compile_minimax_video({**video, "references": []}, [], durations=(4, 15), resolutions={"768P"}), "ratio")
    must_fail(lambda: P.compile_minimax_video({**video, "model": ""}, ["u"], durations=(4, 15), resolutions={"768P"}), "模型")
    full = P.compile_minimax_video({**video, "references": [{**ref, "role": "reference_image"}, face]}, ["u", "u"],
                                   durations=(4, 15), resolutions={"768P"})
    assert "<Picture 2> (女主身份图)" in full["content"][0]["text"]

    # Seedance：编号 @图片N（首帧也占号）；edit/extend 硬条件
    sd = {**video, "references": [ref, face], "parameters": {"duration": 8, "prompt_language": "zh"}}
    sbody = P.compile_seedance(sd, ["u", "u"], durations=(4, 30))
    assert "@图片2（女主身份图）" in sbody["content"][0]["text"] and sbody["duration"] == 8
    vref = {**ref, "path": "视频/V_S00_t1.mp4", "role": "reference_video", "label": "上一镜实际视频"}
    must_fail(lambda: P.compile_seedance({**sd, "references": [vref], "parameters": {"omni_reference_task_type": "edit", "ratio": "9:16"}},
                                         ["u"], durations=(4, 30)), "adaptive")
    must_fail(lambda: P.compile_seedance({**sd, "parameters": {"omni_reference_task_type": "extend", "ratio": "adaptive"}},
                                         ["u", "u"], durations=(4, 30)), "参考视频")
    assert P.compile_seedance({**sd, "references": [vref], "parameters": {"omni_reference_task_type": "edit", "ratio": "adaptive",
                                                                          "duration": -1}}, ["u"], durations=(4, 30))["duration"] == -1

    # MiniMax 语音：语言必须显式、读音词必须在句内、emotion 白名单
    tts = {"kind": "tts", "model": "user-chosen-tts", "prompt": "売上は夏樹のおかげです。", "out": "配音/L01.mp3",
           "parameters": {"voice_id": "voice_x", "language_boost": "Japanese", "emotion": "surprised",
                          "pronunciation": {"売上": "うりあげ", "夏樹": "なつき"}}}
    tb = P.compile_minimax_speech(tts)
    assert tb["language_boost"] == "Japanese" and tb["pronunciation_dict"]["tone"] == ["売上/うりあげ", "夏樹/なつき"]
    must_fail(lambda: P.compile_minimax_speech({**tts, "parameters": {**tts["parameters"], "language_boost": "auto"}}), "language_boost")
    must_fail(lambda: P.compile_minimax_speech({**tts, "parameters": {**tts["parameters"], "pronunciation": {"社長": "しゃちょう"}}}), "不在")
    must_fail(lambda: P.compile_minimax_speech({**tts, "parameters": {**tts["parameters"], "emotion": "neutral"}}), "emotion")

    # 配乐：歌词只来自用户，lyrics_optimizer 拒绝
    music = {"kind": "music", "prompt": "restrained tension, sparse piano", "out": "配乐/cue.mp3", "parameters": {"is_instrumental": True}}
    assert P.compile_minimax_music(music)["model"] == "music-3.0"
    must_fail(lambda: P.compile_minimax_music({**music, "parameters": {"is_instrumental": False}}), "歌词")
    must_fail(lambda: P.compile_minimax_music({**music, "parameters": {"is_instrumental": True, "lyrics_optimizer": True}}), "lyrics_optimizer")

    # GPT Image 2：尺寸约束、不收透明背景
    img = {"kind": "image", "prompt": "plate", "out": "参考图/x.png", "parameters": {"size": "1536x1024"}}
    ib = P.compile_gpt_image(img)
    assert ib["model"] == "gpt-image-2" and ib["output_format"] == "png" and "prompt_language" not in ib
    must_fail(lambda: P.compile_gpt_image({**img, "parameters": {"size": "1000x1000"}}), "16")
    must_fail(lambda: P.compile_gpt_image({**img, "parameters": {"background": "transparent"}}), "background")

    # 文件头校验
    P.check_media("a.png", png)
    must_fail(lambda: P.check_media("a.mp4", png), "不符")

    # 运行时：假传输层走完整条账本
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "起始帧").mkdir()
        (root / "起始帧/F_S01_t1.png").write_bytes(png)
        env = {"MINIMAX_API_KEY": "test-only", "MINIMAX_VIDEO_RESOLUTIONS": "768P",
               "MINIMAX_VIDEO_MIN_DURATION": "4", "MINIMAX_VIDEO_MAX_DURATION": "15"}
        saved = {k: os.environ.get(k) for k in env}
        os.environ.update(env)
        calls = []
        state = {"post_status": 200, "polls": 0}

        def transport(method, url, data, headers):
            calls.append((method, url))
            if method == "POST":
                if state["post_status"] != 200:
                    return state["post_status"], b""
                return 200, json.dumps({"task_id": "T1", "base_resp": {"status_code": 0}}).encode()
            if "/query/" in url:
                state["polls"] += 1
                st = "processing" if state["polls"] == 1 else "succeeded"
                return 200, json.dumps({"task": {"status": st, "content": {"url": "https://cdn.example/v.mp4"}}}).encode()
            return 200, mp4

        try:
            job = {**video, "provider": "minimax-video", "name": "EP001-S01-t1"}
            job.pop("kind")
            runner = P.Runner(root, transport=transport, poll=0, get_wait=0)
            out = runner.run(job)
            assert out.read_bytes() == mp4
            ledger = [json.loads(x) for x in (root / "脚本/jobs.jsonl").read_text(encoding="utf-8").splitlines()]
            statuses = [r["status"] for r in ledger]
            assert statuses == ["submission_intent", "submitted", "collected"], statuses
            assert "test-only" not in (root / "脚本/jobs.jsonl").read_text(encoding="utf-8")
            posts = sum(1 for m, _ in calls if m == "POST")
            must_fail(lambda: runner.run(job), "已存在")  # 不覆盖旧产物
            assert sum(1 for m, _ in calls if m == "POST") == posts

            # 服务端明确拒绝：记 not_submitted，不阻塞后续
            state["post_status"] = 400
            job2 = {**job, "name": "EP001-S01-t2", "out": "视频/V_S01_t2.mp4"}
            must_fail(lambda: runner.run(job2), "HTTP 400")
            assert json.loads((root / "脚本/jobs.jsonl").read_text(encoding="utf-8").splitlines()[-1])["status"] == "not_submitted"
            assert runner.client.unresolved() == []

            # 网络断开：submission_unknown，之后任何提交都被挡住，直到对账
            def broken(method, url, data, headers):
                raise OSError("down")
            job3 = {**job, "name": "EP001-S01-t3", "out": "视频/V_S01_t3.mp4"}
            try:
                P.Runner(root, transport=broken, poll=0, get_wait=0).run(job3)
            except SubmissionUnknown:
                pass
            else:
                raise AssertionError("network failure after intent must be submission_unknown")
            state["post_status"] = 200
            try:
                runner.run({**job, "name": "EP001-S02-t1", "out": "视频/V_S02_t1.mp4"})
            except SubmissionUnknown as exc:
                assert "对账" in str(exc)
            else:
                raise AssertionError("unresolved intent must block new submissions")

            # HTTP 5xx 可能是网关超时而后端已受理：记 submission_unknown，不当作没提交
            other = root / "gateway"
            (other / "起始帧").mkdir(parents=True)
            (other / "起始帧/F_S01_t1.png").write_bytes(png)
            try:
                P.Runner(other, transport=lambda m, u, d, h: (502, b""), poll=0, get_wait=0).run(job)
            except SubmissionUnknown:
                pass
            else:
                raise AssertionError("HTTP 5xx on POST must be submission_unknown")
            assert P.Runner(other).client.unresolved(), "5xx must leave an unresolved intent"
        finally:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v


# ---- 总装：改编入口脚本 novel_index.py / episode_intake.py（adaptation §4.1、§5.2） ----
def test_novel_index() -> None:
    from novel_index import build_index, sample_chapters, verify_index

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        source = root / "novel.txt"
        index_path = root / "index.json"
        source.write_text(
            "第一章 起势\n" + "人物做出选择，代价随之发生，旧关系因此失衡，新的目标也被迫提前。" * 4
            + "\n第二章 反转\n" + "旧承诺被新的证据推翻，人物必须在名誉与家人之间付出不可逆的代价。" * 4 + "\n",
            encoding="utf-8",
        )
        index = build_index(source)
        require(index["chapter_count"] == 2, "chapter count")
        require(index["problems"] == [], "valid chapter index")
        index_path.write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")
        require(verify_index(index_path, source)["verified"] is True, "fresh index")
        require(sample_chapters(index_path, 2)["sampled_count"] == 2, "sample count")
        source.write_text(source.read_text(encoding="utf-8") + "变化\n", encoding="utf-8")
        require(verify_index(index_path, source)["verified"] is False, "source drift")


def test_episode_intake() -> None:
    from episode_intake import build_index, slice_episode, verify_index, write_index

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        source = root / "episodes.md"
        index = root / "index.json"
        source.write_text("第1集 开端\n行动一。\n第2集 反转\n行动二。\n", encoding="utf-8")
        document = build_index(source, source_ref="输入/episodes.md")
        require(document["episode_count"] == 2, "episode count")
        require(document["problems"] == [], "valid episode index")
        write_index(index, document)
        require(verify_index(index, source)["verified"] is True, "fresh index")
        require(slice_episode(index, source, "EP002").startswith("第2集".encode()), "verified episode slice")
        source.write_text(source.read_text(encoding="utf-8") + "变更。\n", encoding="utf-8")
        require(verify_index(index, source)["verified"] is False, "source drift")


# ---- 导演执行与成片验收 lane：预演、文字排版避脸、台词边界、成片终验 ------------------------------------
def test_final_acceptance() -> None:
    """cut.py 金额/专名不断行、长文字分屏、叠字避脸（注入人脸框）、入点保护、字幕按取用区间裁剪、片尾不拖尾、overlays.json；
    review_quality 声音三分项与 must_show；review_tool 预演（临时对白、镜号、动作起止、反应拍、结论待填）；final_qa 终验产物。"""
    import os
    from unittest.mock import patch
    from PIL import Image, ImageFont
    import cut as cut_mod
    import final_qa
    import review_tool
    from common import SHOTS_SCHEMA, Project
    from project_tool import init
    from review_quality import audio_status, cut_issues, fmt_audio, take_quality

    # 金额/数字/专名不断行（纯函数）
    font_path = cut_mod.find_font(cut_mod.FONT_DEFAULTS["sub"])
    if font_path:
        f = ImageFont.truetype(font_path, 50)
        text = "今月の売上は¥3,000,000を超えて夏樹が一位になった"
        for maxw in (260, 330, 420, 520):
            lines = cut_mod.wrap_lines(text, f, maxw, ["夏樹"])
            require(any("¥3,000,000" in ln for ln in lines), f"金额被拆行（{maxw}px）：{lines}")
            require(any("夏樹" in ln for ln in lines), f"专名被拆行（{maxw}px）：{lines}")
            require("".join(lines) == text, "折行丢字")
            require(not any(ln[:1] in "、。！？」" for ln in lines[1:]), f"行首是句读：{lines}")
        require(cut_mod.protected_tokens("三百万円と¥3,000,000、十件", []) == ["三百万円", "¥3,000,000", "十件"],
                f"不可拆词：{cut_mod.protected_tokens('三百万円と¥3,000,000、十件', [])}")
        require(len(cut_mod.paginate(["a", "b", "c", "d", "e"])) == 3, "超过两行按两行一屏分屏")
    else:
        print("  (跳过折行断言：没有中日文字体)")

    # 入点保护：入点切进句首语气词 / 落在词中间 → 前移到词前 0.1s；出点落在词中间 → 后移；杂音不保护
    words = [(0.2, 0.45, "あれ？"), (0.6, 1.5, "その金額は"), (1.5, 2.4, "三百万です")]
    a, b, notes = cut_mod.guard_word_edges(words, 0.5, 2.0, 3.0, "あれその金額は三百万です")
    require(abs(a - 0.1) < 1e-6 and abs(b - 2.5) < 1e-6 and len(notes) == 2, f"入点/出点保护：{a} {b} {notes}")
    a2, _, n2 = cut_mod.guard_word_edges([(0.3, 0.5, "えーと")], 0.55, 2.0, 3.0, "その金額は")
    require(a2 == 0.55 and not n2, "不属于本镜台词的杂音不去保护")
    lines_, warns = cut_mod.trim_subtitles(words, [{"sub": "あれ？その金額は三百万です", "text": "あれ？その金額は三百万です"}], 0.55, 3.0)
    require(lines_[0]["sub"] == "その金額は三百万です" and warns and "句首" in warns[0], f"字幕去掉不在区间内的句首：{lines_} {warns}")
    lines_, warns = cut_mod.trim_subtitles(words, [{"sub": "What? That amount", "text": "あれ？その金額は三百万です"}], 0.55, 3.0)
    require(lines_[0]["sub"] == "What? That amount" and "人工" in warns[0], "字幕是译文时不硬删，记警告要人工改")

    # 声音三分项：旧 audio pass 只算识别通过；null 显示未验证
    st = audio_status({"checks": {"audio": "pass"}})
    require(st == {"asr_ok": True, "listen_ok": None, "sync_ok": None}, f"旧字段兼容：{st}")
    require(fmt_audio(st) == "识别 通过；听审 未验证；同步 未验证", fmt_audio(st))
    require(audio_status({"asr_ok": True, "listen_ok": False})["listen_ok"] is False, "listen_ok 人工写入")

    if not (shutil.which("ffmpeg") and shutil.which("ffprobe")):
        print("  (跳过剪辑/预演/终验实跑：没有 ffmpeg)")
        return
    with tempfile.TemporaryDirectory() as td:
        root = init(Path(td) / "剧Q", "终验", 1, "ja", "测试", 10, None, "16:9")
        cfg = json.loads((root / "drama.json").read_text(encoding="utf-8"))
        cfg.update(readings={"夏樹": "なつき"}, ai_label=None, room_tone_db=None)
        (root / "drama.json").write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
        pr = Project(root)
        W, H = int(pr.get("width")), int(pr.get("height"))
        line = "あれ？その金額は¥3,000,000です。"
        long_text = "规则说明：每挨一拳到账一百万，到账金额¥3,000,000会实时显示在屏幕右上角，夏樹必须在三秒内确认否则作废，此规则全剧有效"
        shots = {"schema": SHOTS_SCHEMA, "episode": "EP001",
                 "scenes": [{"id": "EP001-SC001", "must_show": [{"id": "MS1", "fact": "屏幕上金额 ¥3,000,000 完整可读", "shots": ["EP001-S01"], "kind": "count"}]}],
                 "shots": [{"id": "EP001-S01", "scene": "EP001-SC001", "kind": "person", "subject": "夏樹", "seconds": 3, "must_show_ids": ["MS1"],
                            "planned_action_window": [1.0, 2.0], "dialogue": [{"speaker": "夏樹", "text": line, "at": 0.2, "reading": {"夏樹": "なつき"}}],
                            "overlay": [{"kind": "text", "text": "到账 ¥3,000,000", "at": 0.5, "until": 2.5}]},
                           {"id": "EP001-S02", "scene": "EP001-SC001", "kind": "person", "subject": "夏樹", "seconds": 3, "explains_ability": True,
                            "overlay": [{"kind": "text", "text": long_text, "at": 0.2, "until": 2.8}]}]}
        pr.shots_path("EP001").write_text(json.dumps(shots, ensure_ascii=False), encoding="utf-8")
        from review_quality import media_digest, shot_digest, text_digest

        def fake_ledger(sid, take=1):   # 等同 h3_client 收回时写的账本，让来源校验对得上
            vp_ = pr.video_path("EP001", sid, take)
            pr.scripts_dir.mkdir(parents=True, exist_ok=True)
            with open(pr.scripts_dir / "jobs.jsonl", "a", encoding="utf-8") as fh:
                fh.write(json.dumps({"status": "submitted", "job": f"j-{sid}", "out": str(vp_.resolve()), "source_prompt_sha256": text_digest("")}) + "\n")
                fh.write(json.dumps({"status": "collected", "job": f"j-{sid}", "out": str(vp_.resolve()), "sha256": media_digest(vp_)}) + "\n")

        def fake_asr(sid, take=1):      # 等同 review_tool.asr 对当前文件、当前镜头跑过
            rv_ = pr.load_review("EP001")
            sh_ = next(x for x in pr.load_shots("EP001")["shots"] if x["id"] == sid)
            rec_ = rv_.setdefault("shots", {}).setdefault(sid, {}).setdefault("video_takes", {}).setdefault(str(take), {"take": take})
            rec_.update(asr_media_sha256=media_digest(pr.video_path("EP001", sid, take)), asr_shot_sha256=shot_digest(sh_),
                        speech_diff={"status": "exact", "critical_changes": [], "similarity": 1.0})
            pr.save_review("EP001", rv_)

        for sid in ("EP001-S01", "EP001-S02"):
            fp = pr.frame_path("EP001", sid, 1)
            fp.parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGB", (W, H), (90, 110, 140)).save(fp)
            vp = pr.video_path("EP001", sid, 1)
            vp.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc2=s={W}x{H}:r=24:d=3", "-f", "lavfi",
                            "-i", "sine=frequency=330:duration=3:sample_rate=48000", "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                            "-c:a", "aac", str(vp)], check=True)
            fake_ledger(sid)

        # 预演：无 TTS 时按估算留静音、画面标台词秒数；md 首行结论待填、不放行；有统计
        with patch.dict(os.environ, {"ANIMATIC_TTS": "0"}):
            amp4, ajpg, amiss = review_tool.animatic(pr, "EP001")
        from common import ffprobe_duration
        md = (pr.review_dir / "EP001-预演.md").read_text(encoding="utf-8")
        require(not amiss and abs(ffprobe_duration(amp4) - 6.0) < 0.15 and ajpg.exists(), f"预演时长 ≈ 6s：{ffprobe_duration(amp4)}")
        streams = final_qa.stream_durations(amp4)
        require("audio" in streams and abs(streams["audio"] - 6.0) < 0.2, f"预演带临时对白音轨：{streams}")
        require(md.startswith("结论：待填") and not pr.animatic_passed("EP001"), "预演.md 首行结论待填，不放行")
        require("按估算时长留静音 1 句" in md and "EP001-S02" in md and "反应拍" in md and "MS1" in md and "解释能力" in md, md[:900])
        (pr.review_dir / "EP001-预演.md").write_text(md.replace("结论：待填", "结论：PASS", 1), encoding="utf-8")
        probs = pr.animatic_problems("EP001")
        require(any("MS1" in x for x in probs) and any("【" in x for x in probs), f"只改首行 PASS 不放行（必拍表没填）：{probs}")
        filled = md.replace("结论：待填", "结论：PASS", 1).replace("【EP001-S01 · X.Xs】", "EP001-S01 · 1.5s").replace("【看得到 / 看不到 / 只靠台词】", "看得到 · 金额完整一行")
        (pr.review_dir / "EP001-预演.md").write_text(filled, encoding="utf-8")
        require(pr.animatic_passed("EP001"), f"首行 PASS、必拍表填齐、指纹对得上才放行：{pr.animatic_problems('EP001')}")
        with patch.dict(os.environ, {"ANIMATIC_TTS": "0"}):
            review_tool.animatic(pr, "EP001")
        require(pr.animatic_passed("EP001"), "预演内容没变时不覆盖已填结论")
        # 旧版预演.md（没有输入指纹行）：不放行；重跑 animatic 内容没变时只补指纹行、保留结论
        (pr.review_dir / "EP001-预演.md").write_text(re.sub(r"^预演输入指纹.*\n", "", filled, flags=re.M), encoding="utf-8")
        require(any("预演输入指纹" in x for x in pr.animatic_problems("EP001")), "缺输入指纹的旧预演不放行并提示重跑")
        with patch.dict(os.environ, {"ANIMATIC_TTS": "0"}):
            review_tool.animatic(pr, "EP001")
        require(pr.animatic_passed("EP001"), f"重跑 animatic 补上指纹行后放行：{pr.animatic_problems('EP001')}")
        # 分镜改了（旧 PASS 过期）
        stale = json.loads(pr.shots_path("EP001").read_text(encoding="utf-8"))
        stale["shots"][1]["seconds"] = 4
        pr.shots_path("EP001").write_text(json.dumps(stale, ensure_ascii=False), encoding="utf-8")
        require(any("过期" in x for x in pr.animatic_problems("EP001")), "shots.json 改过后旧预演 PASS 过期")
        pr.shots_path("EP001").write_text(json.dumps(shots, ensure_ascii=False), encoding="utf-8")
        fake_asr("EP001-S01")

        # 审片：must_show fail 不许 ok/weak，auto 给 retake，cut_issues 拦下
        opts = dict(video_take=1, visual="pass", audio="pass", continuity="pass", evidence="synthetic fixture: offline contract", verdict="ok")
        review_tool.mark(pr, "EP001", "EP001-S02", **opts)
        opts["speaker_face_ok"] = True   # S01 有台词：说话人口型要看过（S02 无台词不需要）
        try:
            review_tool.mark(pr, "EP001", "EP001-S01", speech_window=[0.6, 2.4], action_window=[1.0, 2.0], must_show={"MS1": "fail"}, **opts)
            raise AssertionError("must_show fail 仍被批准 ok")
        except ValueError as err:
            require("must_show" in str(err), str(err))
        review_tool.mark(pr, "EP001", "EP001-S01", **{**opts, "verdict": "retake"}, speech_window=[0.6, 2.4], action_window=[1.0, 2.0], must_show={"MS1": "fail"})
        require(review_tool.auto(pr, "EP001")["shots"]["EP001-S01"]["verdict"] == "retake", "auto 在 must_show fail 时给 retake")
        require(any("must_show fail" in x for x in cut_issues(pr, "EP001", pr.load_shots("EP001"), pr.load_review("EP001"))), "cut_issues 拦 must_show fail")
        review_tool.mark(pr, "EP001", "EP001-S01", speech_window=[0.6, 2.4], action_window=[1.0, 2.0], must_show={"MS1": "pass"}, listen_ok=None, **opts)
        rec = pr.load_review("EP001")["shots"]["EP001-S01"]["video_takes"]["1"]
        require(not take_quality(pr.video_path("EP001", "EP001-S01", 1), pr.load_shots("EP001")["shots"][0], rec), "识别通过、听审未验证可以入剪")
        require(audio_status(rec["assessment"]) == {"asr_ok": True, "listen_ok": None, "sync_ok": None}, f"mark 写三分项：{rec['assessment']}")
        rp = review_tool.report(pr, "EP001").read_text(encoding="utf-8")
        require("听审 未验证" in rp and "MS1 通过" in rp, "审片报告显示三分项与 must_show")
        edit_rev = pr.load_review("EP001")
        edit_rev["shots"]["EP001-S01"]["video_takes"]["1"]["edit"] = {"in": 0.5, "out": 2.8, "mode": "fixed"}
        pr.save_review("EP001", edit_rev)

        # 剪辑：注入 ASR 词级时间与人脸框（字幕默认位置压脸 → 换位）
        v1 = pr.video_path("EP001", "EP001-S01", 1)
        fake_words = {v1.name: [(0.2, 0.45, "あれ？"), (0.6, 1.4, "その金額は"), (1.4, 2.4, "300万です")]}

        class FakeASR:
            py = "fake"

            def __init__(self, project):
                pass

            def words(self, paths, fresh=False):
                return {str(p): fake_words.get(Path(p).name, []) for p in paths}

        face = [W // 2 - 150, H - 230, 300, 220]
        with patch("review_tool.ASR", FakeASR), patch.object(cut_mod, "FACE_HOOK", lambda v, ts: [face]):
            out = cut_mod.cut(pr, "EP001")
        sheet = (pr.ep_dir("EP001") / "剪辑单.md").read_text(encoding="utf-8")
        require("入点 0.50→0.10（保住句首「あれ？」）" in sheet, f"入点保护写进剪辑单：{sheet[:1200]}")
        require("识别 通过；听审 未验证；同步 未验证" in sheet and "MS1「" in sheet, "剪辑单显示三分项与必须拍清楚")
        require("能力解释镜（explains_ability）：1 镜" in sheet and "避脸结果：" in sheet, "剪辑单统计能力解释镜与避脸结果")
        meta = json.loads(cut_mod.overlays_path(out).read_text(encoding="utf-8"))
        subs = [o for o in meta["overlays"] if o["kind"] == "sub"]
        require(subs and subs[0]["position"] != "bottom" and subs[0]["face_overlap"] is False, f"字幕避开人脸：{subs}")
        money = [o for o in meta["overlays"] if o["kind"] == "text" and "¥3,000,000" in o["full_text"]]
        require(all(any("¥3,000,000" in ln for ln in o["lines"]) for o in money if "¥3,000,000" in "".join(o["lines"])), f"金额不断行：{money}")
        pages = [o for o in meta["overlays"] if o["kind"] == "text" and o["full_text"] == long_text]
        require(len(pages) >= 2 and all(len(o["lines"]) <= 2 for o in pages) and pages[0]["page"] == [1, len(pages)], f"长文字分屏：{pages}")
        require(meta["segments"][0]["in"] == 0.1 and meta["segments"][0]["boundary_notes"], f"segments 记切点：{meta['segments'][0]}")
        real = ffprobe_duration(out)
        require(real <= meta["duration"] + 0.1, f"片尾不拖尾：实长 {real}，剪辑 {meta['duration']}")

        # 终验：成片 ASR 只识别到后半句 → 字幕多于声音 / 疑似裁词；listen/sync 为 null；首行 REVISE
        fake_words[out.name] = [(1.0, 1.8, "その金額は")]
        with patch("review_tool.ASR", FakeASR), patch.object(cut_mod, "FACE_HOOK", lambda v, ts: [face]):
            rep = final_qa.final_qa(pr, "EP001")
        jq = json.loads((pr.review_dir / "EP001-final-qa.json").read_text(encoding="utf-8"))
        mdq = (pr.review_dir / "EP001-final-qa.md").read_text(encoding="utf-8")
        require(jq["listen_ok"] is None and jq["sync_ok"] is None and jq["asr_ok"] is False, f"三分项：{jq['asr_ok']} {jq['listen_ok']} {jq['sync_ok']}")
        require(mdq.startswith("结论：REVISE") and "未验证，需人工" in mdq, mdq[:400])
        types = {i["type"] for i in rep["issues"]}
        require({"字幕多于声音", "疑似裁词"} <= types and "片尾静止拖尾" not in types and "叠字压脸" not in types, f"终验问题类型：{types}")
        require((pr.review_dir / "EP001-final-qa" / "contact.jpg").exists() and any(i.get("evidence") for i in rep["issues"]), "接触表与证据帧")
        # 人工写入听审/同步：要 evidence + 真人 listener + 当前成片 sha；asr_ok 人工值不能替代没跑的 ASR；把人脸放到全画面 → 终验报压脸
        rv = pr.load_review("EP001")
        rv["final_qa"] = {"listen_ok": True, "asr_ok": True, "evidence": "selftest: pretend a native speaker listened 0–6s"}
        pr.save_review("EP001", rv)
        with patch("review_tool.ASR", FakeASR), patch.object(cut_mod, "FACE_HOOK", lambda v, ts: [[0, 0, W, H]]):
            rep2 = final_qa.final_qa(pr, "EP001", use_asr=False)
        require(rep2["listen_ok"] is None and rep2["asr_ok"] is None and rep2["conclusion"] == "REVISE", f"没绑成片 sha 的人工值不采用：{rep2['listen_ok']} {rep2['asr_ok']}")
        rv["final_qa"].update(video_sha256=media_digest(out), listener="claude")
        pr.save_review("EP001", rv)
        with patch("review_tool.ASR", FakeASR), patch.object(cut_mod, "FACE_HOOK", lambda v, ts: [[0, 0, W, H]]):
            rep2 = final_qa.final_qa(pr, "EP001", use_asr=False)
        require(rep2["listen_ok"] is None and rep2["asr_ok"] is None, f"模型签的听审不采用、asr_ok 人工值不替代 ASR：{rep2['listen_ok']} {rep2['asr_ok']}")
        rv["final_qa"]["listener"] = "佐藤（用户指定的母语者）"
        pr.save_review("EP001", rv)
        with patch("review_tool.ASR", FakeASR), patch.object(cut_mod, "FACE_HOOK", lambda v, ts: [[0, 0, W, H]]):
            rep2 = final_qa.final_qa(pr, "EP001", use_asr=False)
        require(rep2["listen_ok"] is True and rep2["sync_ok"] is None and rep2["asr_ok"] is None, f"人工值：{rep2['listen_ok']} {rep2['sync_ok']}")
        require(any(i["type"] == "叠字压脸" for i in rep2["issues"]), "全画面人脸时终验报叠字压脸")
        # 草剪冒充成片、删字幕条目藏台词：都拦下
        mp = cut_mod.overlays_path(out)
        meta0 = mp.read_text(encoding="utf-8")
        m1 = json.loads(meta0); m1["draft"] = True
        mp.write_text(json.dumps(m1, ensure_ascii=False), encoding="utf-8")
        with patch("review_tool.ASR", FakeASR), patch.object(cut_mod, "FACE_HOOK", lambda v, ts: []):
            rep3 = final_qa.final_qa(pr, "EP001", use_asr=False)
        require(rep3["conclusion"] == "REVISE" and any(i["type"] == "草剪冒充成片" for i in rep3["issues"]), "draft 元数据一律 REVISE")
        m1["draft"] = False; m1["overlays"] = [o for o in m1["overlays"] if o["kind"] != "sub"]
        mp.write_text(json.dumps(m1, ensure_ascii=False), encoding="utf-8")
        with patch("review_tool.ASR", FakeASR), patch.object(cut_mod, "FACE_HOOK", lambda v, ts: []):
            rep3 = final_qa.final_qa(pr, "EP001", use_asr=False)
        require(any(i["type"] == "元数据缺台词字幕" for i in rep3["issues"]) and rep3["conclusion"] == "REVISE", "删掉字幕条目仍按 shots.json 期望台词查")
        mp.write_text(meta0, encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
