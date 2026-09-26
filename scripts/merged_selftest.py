#!/usr/bin/env python3
"""合并进 drama-forge 的新功能的离线自测。每个 lane 一个独立的 test_* 函数，互不依赖。

  python3 scripts/merged_selftest.py            跑全部 test_*
  python3 scripts/merged_selftest.py hub_tool   只跑名字里含 hub_tool 的
"""
from __future__ import annotations

import json
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

夏樹抱着钱箱走到楼梯口。鬼塚的运动包拉链半开，露出同款钱箱的角。

鬼塚（拦路要钱｜威胁·中·慢·小）：売上、渡せよ。

夏樹（顶回去｜强装镇定·弱·中·中｜读音 売上=うりあげ）：無理。これ、先生に届けんだよ。

[OS] 先生：何してる！

[SFX] 楼梯下方传来上楼的脚步声。

[连续性] 钱箱在夏樹左臂；鬼塚包里有假箱，老师正上楼。
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
    for code in ("SP02", "SP03", "SP04", "SP05", "SP06", "SP07", "SP08", "SP09", "SP11", "SP12"):
        require(code in got, f"坏剧本应报 {code}，实际 {sorted(got)}")
    require(len([x for x in f if x["code"] == "SP02" and x["level"] == "error"]) == 2, "SP02 error 应为重复 ID + 集号不一致两条")
    amb = [x for x in f if x["code"] == "SP08"]
    require(len(amb) == 1 and "他写下两个字" in amb[0]["msg"], "只应把「他写下两个字：」当歧义行")
    require(len([x for x in f if x["code"] == "SP09" and "取值不对" in x["msg"]]) == 1, "情绪取值「超强」应被指出")
    f = lint_text("# EP001 t\n\n## EP001-SC001 内 · 屋 · 夜\n\n第二格：一只手把杯子推过去。\n\n"
                  "甲（问｜平静·弱·中·中）：你来了。\n\n甲（问｜平静·弱·中·中）：坐。\n", None)
    require([x["code"] for x in f] == ["SP08"], f"无清单推断应只报行首冒号行，实际 {[x['code'] for x in f]}")
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
    require("RV06" in codes(check_text(deferred), "error"), "Major 未决后仍写 REVISE 应报 RV06")
    require(check_text(deferred.replace("结论：REVISE", "结论：PASS"))["errors"] == 0, "未决 Major 不计入未关闭，PASS 合法")
    require("RV06" in codes(check_text(_RV_OK.replace("## Major · R-001", "## Blocker · R-001")), "error"), "未关闭 Blocker 应要求 BLOCKED")
    require("RV04" in codes(check_text(_RV_OK.replace("- 证据：SC003 之前没有交代第二个箱子。\n", "")), "error"), "Major 缺证据应报 RV04")
    require("RV05" in codes(check_text(_RV_OK.replace("R-002", "R-001")), "error"), "编号重复应报 RV05")
    require({"RV02", "RV07"} <= codes(check_text(_RV_OK.replace("keep:\n", "").replace("- 复核方式：独立 reviewer\n", "")), "warn"),
            "缺复核方式、缺 keep 应 warn")
    require("RV01" in codes(check_text(_RV_OK.replace("结论：REVISE", "结论：APPROVE")), "error"), "非 PASS/REVISE/BLOCKED 应报 RV01")
    tpl = Path(__file__).resolve().parent.parent / "assets" / "templates" / "审查.md"
    if tpl.exists():
        require("RV08" in codes(check_text(tpl.read_text(encoding="utf-8")), "error"), "未填模板应被 RV08 拦下")


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


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
