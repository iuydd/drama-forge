#!/usr/bin/env python3
"""离线自测：起一个假的 H3 中转，把 init → 门 → 渲染 → 参考图/起始帧/视频 → 审片 → 剪辑 整条链跑一遍。
不联网、不用真 token。需要 ffmpeg/ffprobe 与 Pillow；显式设 SELFTEST_ASR=1 时才测 ASR（需已缓存 ASR_MODEL=tiny）。"""
from __future__ import annotations

import argparse
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
ASSETS = HERE.parent / "assets"

MINIMUM_PYTHON = (3, 10)
if sys.version_info < MINIMUM_PYTHON:
    raise SystemExit("selftest.py requires Python 3.10 or newer")


def require(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


def expect_exit(fn, word: str, msg: str) -> None:
    try:
        fn()
    except SystemExit as e:
        require(word in str(e), f"{msg}：{e}")
        return
    raise AssertionError(f"{msg}：没有拒绝")


def review_frames(pr, ep: str = "EP001") -> None:
    """合成夹具：每镜当前所选起始帧记一条目检（绑定帧文件 sha），produce.py videos 才肯提交。"""
    import review_tool
    for sh in pr.load_shots(ep)["shots"]:
        ft = pr.chosen_take(ep, sh["id"], "frame")
        if ft:
            review_tool.mark(pr, ep, sh["id"], frame_take=ft, evidence="synthetic selftest fixture: 九项清单逐项核过")


def pass_animatic(pr, ep: str = "EP001", media: bool = True) -> None:
    """合成夹具：预演放行（有 ffmpeg 就真跑 animatic；首行 PASS、必拍表逐条填「镜号 · 秒 · 看得到」）。"""
    import re as _re
    import review_tool
    from review_quality import animatic_inputs_fp, must_show_facts
    p = pr.review_dir / f"{ep}-预演.md"
    if media:
        if p.exists():
            p.unlink()
        review_tool.animatic(pr, ep, tts=False)
        md = p.read_text(encoding="utf-8").replace("结论：待填", "结论：PASS", 1)
        md = _re.sub(r"【([^】·]*?) · X\.Xs】", r"\1 · 1.0s", md).replace("【看得到 / 看不到 / 只靠台词】", "看得到")
        md = md.replace("【镜号 · 1.0s】", "镜号 · 1.0s")
    else:
        pr.review_dir.mkdir(parents=True, exist_ok=True)
        (pr.review_dir / f"{ep}-预演.mp4").write_bytes(b"fixture")
        rows = [f"| {f['id']} | {f['fact']} | {(f['shots'] or ['?'])[0]} · 1.0s | 看得到 |" for f in must_show_facts(pr.load_shots(ep))]
        md = "\n".join(["结论：PASS", "", f"预演输入指纹：{animatic_inputs_fp(pr, ep)}", "", "- 缺起始帧（用灰卡占位）：无。", "", "## 必拍事实", ""] + rows) + "\n"
    p.write_text(md, encoding="utf-8")
    require(pr.animatic_passed(ep), f"夹具预演应放行：{pr.animatic_problems(ep)}")


def pass_reviews(pr, ep: str = "EP001") -> None:
    """合成夹具：C/E 审查文件（review_md_check 0 error、结论 PASS、指纹绑定当前剧本/分镜）。"""
    fps = pr.fingerprints(ep)
    for name, label in (("审查", "剧本"), ("分镜审查", "分镜")):
        (pr.review_dir / f"{ep}-{name}.md").write_text(
            f"# {ep} {name}\n\n- 结论：PASS\n- 复核方式：独立 reviewer\n- {label}指纹：{fps[label]}\n\nkeep:\n- 全部\n", encoding="utf-8")


# ---- 假中转 --------------------------------------------------------------------
class Mock:
    def __init__(self, tmp: Path, media: bool = True):
        from PIL import Image
        buf = io.BytesIO()
        Image.new("RGB", (64, 36), (30, 60, 120)).save(buf, "PNG")
        self.png = buf.getvalue()
        if media:
            vid = tmp / "mock.mp4"
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=0x203050:s=336x192:d=3:r=24", "-f", "lavfi",
                            "-i", "sine=frequency=440:duration=3", "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(vid)],
                           check=True)
            self.mp4 = vid.read_bytes()
        else:
            # Header-only fixture for transport tests; never decode or claim it is playable media.
            self.mp4 = b"\x00\x00\x00\x18ftypmp42" + b"transport-fixture"
        self.jobs: dict[str, dict] = {}
        self.n = 0
        self.posts = 0


def make_handler(mock: Mock):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):  # 安静
            pass

        def _json(self, obj, code=200):
            body = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _bytes(self, data, ctype):
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.headers.get("Authorization") != "Bearer test-token":
                return self._json({"error": "unauthorized"}, 401)
            p = self.path
            if p == "/api/status":
                return self._json({"running": 0, "queued": 0})
            if p == "/api/config":
                return self._json({"profiles": {"image": ["qwen21", "krea2_turbo"], "video": ["base50_sol"]}})
            if p.startswith("/api/jobs/"):
                parts = p.split("/")
                jid = parts[3]
                job = mock.jobs.get(jid)
                if not job:
                    return self._json({"error": "no such job"}, 404)
                if len(parts) == 4:
                    return self._json({"id": jid, "status": "done"})
                if parts[4] == "image":
                    return self._bytes(mock.png, "image/png")
                if parts[4] == "video":
                    return self._bytes(mock.mp4, "video/mp4")
            return self._json({"error": "not found"}, 404)

        def do_POST(self):
            if self.headers.get("Authorization") != "Bearer test-token":
                return self._json({"error": "unauthorized"}, 401)
            n = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(n) or b"{}")
            mock.posts += 1
            mock.n += 1
            kind = "image" if self.path.endswith("/image") else "video"
            require(payload.get("prompt"), "POST 必须带 prompt")
            require(isinstance(payload.get("images"), list), "POST 必须带 images 列表")
            if kind == "video":
                require(payload.get("image_mode") == "keyframe" and len(payload["images"]) == 1, "视频必须 keyframe + 一张起始帧")
            jid = f"{kind}-{mock.n}"
            mock.jobs[jid] = {"kind": kind, "payload": payload}
            return self._json({"id": jid})

    return H


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-media", action="store_true", help="run contracts/transport/recovery only; skip video decoding, ASR and cutting")
    args = parser.parse_args()
    from client_selftest import run_tests
    run_tests()
    import unittest
    from quality_selftest import QualityTests
    quality = unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromTestCase(QualityTests))
    require(quality.wasSuccessful(), "quality regressions")
    tmp = Path(tempfile.mkdtemp(prefix="sda_selftest_"))
    mock = Mock(tmp, media=not args.no_media)
    srv = HTTPServer(("127.0.0.1", 0), make_handler(mock))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    os.environ["H3_API"] = f"http://127.0.0.1:{srv.server_port}"
    os.environ["H3_STUDIO_TOKEN"] = "test-token"
    os.environ.pop("SEED_OFF", None)
    os.environ.pop("DEADLINE", None)
    passed = 0

    from project_tool import init, next_step, status
    from common import Project, ffprobe_duration
    from shots_tool import check, check_refs, coverage, render
    import produce
    import review_tool
    import cut as cut_mod
    from h3_client import Client

    root = init(tmp / "demo", "自测剧", 1, "ja", "智斗复仇", 30, None, "16:9")
    require((root / "drama.json").exists() and (root / "项目开发/系列简报.md").exists(), "init 建目录与模板")
    passed += 1
    shutil.copy(ASSETS / "example/refs.json", root / "参考图/refs.json")
    for f in ("剧本.md", "视觉设定.md", "shots.json"):
        shutil.copy(ASSETS / "example/EP001" / f, root / "EP001" / f)
    pr = Project(root)
    require(all(value is None for value in pr.cfg["profiles"].values()), "新项目不能继承旧项目生产档位")
    pr.cfg["profiles"] = {"ref": "krea2_turbo", "frame": "qwen21", "video": "base50_sol",
                          "ref_res": "2K", "frame_res": "1K", "video_res": "768p"}
    (root / "drama.json").write_text(json.dumps(pr.cfg, ensure_ascii=False), encoding="utf-8")
    pr.cfg["line_max"] = {"zh": 15, "ja": 20, "en": 10}  # explicit test fixture preference
    require(next_step(pr).startswith("阶段 A"), "系列简报还是模板时 next 指向阶段 A")
    passed += 1
    # 立项新颖度：系列简报填了但没有 ≥6 候选 / 爽感打分 → next 带 warn（不拦）；补齐后 warn 消失
    brief = root / "项目开发/系列简报.md"
    tmpl = brief.read_text(encoding="utf-8")
    brief.write_text("# 系列简报\n\n## 一句话\n\n主角能看见谁在说谎。\n", encoding="utf-8")
    nx = next_step(pr)
    require(not nx.startswith("阶段 A") and nx.count("[warn] 立项") == 3, f"缺候选、缺打分、用了饱和设定各一条 warn：{nx}")
    require("新在哪里" in nx and "本质区别" not in nx, f"饱和设定只提示写清新在哪里，不因关键词判不合格：{nx}")
    rows = "".join(f"| {i} | 钩子{i} | 画面 | 兑现 | 秘密/时钟/见证者 | 区别 | 法 {i} | 12 |\n" for i in range(1, 7))
    brief.write_text("# 系列简报\n\n## 一句话\n\n杂役睡了三百年，醒来辈分压全宗。\n\n## 立项候选\n\n"
                     "| # | 钩子 | 画面 | 兑现 | 三件套 | 区别 | 生成法 | 分 |\n|---|---|---|---|---|---|---|---|\n" + rows +
                     "\n## 爽感打分\n\n| 项 | 分 | 依据 |\n|---|---|---|\n| A1★ | 2 | EP001 |\n| **总分** | 38/50 | 开工 |\n", encoding="utf-8")
    require("[warn] 立项" not in next_step(pr), f"≥6 候选且有打分时不再 warn：{next_step(pr)}")
    brief.write_text(tmpl, encoding="utf-8")
    require(next_step(pr).startswith("阶段 A"), "恢复模板后 next 回到阶段 A")
    passed += 1

    F = check(pr, "EP001")
    require(not F.errors(), f"示例 shots.json 应无 error：{F.errors()}")
    codes = {f["code"] for f in F.warns()}
    require("G11" not in codes or all("对白" in f["msg"] for f in F.warns() if f["code"] == "G11"), "示例覆盖了全部场景")
    require(not codes & {"G31", "G32", "G33", "G34", "G35"}, f"示例应不触发 G31–G35：{codes}")
    require("G23" not in codes, f"示例视频提示词已带锁面，不应报 G23 warn：{[f for f in F.warns() if f['code'] == 'G23']}")
    passed += 1

    # G31 台词情绪 / G32 因果铺垫 / G33 风格锁定 / G34 尺度锚点 / G35 环境动态
    sp = root / "EP001/shots.json"
    good_sp = sp.read_text(encoding="utf-8")
    nb = json.loads(good_sp)
    nb["cut_order"] = [sh["id"] for sh in nb["shots"]]  # explicit dependency-order fixture
    nb["shots"][0]["dialogue"][0].pop("emotion", None)
    nb["shots"][1]["requires_setup"] = ["空箱"]
    nb["shots"][3]["setup_for"] = ["空箱"]
    nb["shots"][2]["requires_setup"] = ["EP001-S09", "红笔"]
    nb["shots"][1]["environment_motion_required"] = True
    nb["shots"][1]["video_prompt"] = nb["shots"][1]["video_prompt"].replace(" Dust drifts slowly in the window light above the table.", "")
    nb["shots"][2]["framing"] = "中景，主位，三上一人，面朝画右"
    nb["shots"][2]["frame_prompt"] = nb["shots"][2]["frame_prompt"].replace(" Seated, the table top is level with his waist; he is about a head taller than her.", "")
    sp.write_text(json.dumps(nb, ensure_ascii=False), encoding="utf-8")
    old_preset = pr.cfg.get("style_preset")
    pr.cfg["style_preset"] = "watercolor"
    Fn = check(pr, "EP001")
    w = {(f["code"], f["shot"]) for f in Fn.warns()}
    msgs = [f["msg"] for f in Fn.warns() if f["code"] == "G32"]
    require(("G31", "EP001-S01") in w, "台词没写 emotion 要报 G31")
    require(("G32", "EP001-S02") in w and any("之后" in m for m in msgs), f"铺垫镜在本镜之后要报 G32：{msgs}")
    require(sum(1 for c, s in w if c == "G32" and s == "EP001-S03") == 1 and any("不存在" in m for m in msgs) and any("凭空" in m for m in msgs),
            f"铺垫镜不存在、铺垫名字没人 setup 要报 G32：{msgs}")
    require(("G33", None) in w, "style_preset 不在风格库要报 G33")
    require(("G34", "EP001-S03") in w, "中景起始帧没写尺度锚点要报 G34")
    require(("G35", "EP001-S02") in w, "视频提示词没有环境动态要报 G35")
    nb["shots"][2]["frame_prompt"] += " The table top is at his mid-thigh height, the door frame is about a head taller than him."
    nb["shots"][3].pop("setup_for"); nb["shots"][0]["setup_for"] = ["空箱"]
    sp.write_text(json.dumps(nb, ensure_ascii=False), encoding="utf-8")
    pr.cfg.pop("style_preset", None)
    w2 = {(f["code"], f["shot"]) for f in check(pr, "EP001").warns()}
    require(("G34", "EP001-S03") not in w2 and ("G32", "EP001-S02") not in w2, f"写了尺度锚点、铺垫在前就不报：{w2}")
    require(("G33", None) in w2, "没写 style_preset 要报 G33")
    if old_preset is not None:
        pr.cfg["style_preset"] = old_preset
    sp.write_text(good_sp, encoding="utf-8")
    passed += 1

    # G36 画风漂移词 / G37 单句超长 / G38 参考图数量与头肩图 / G39 AI 标识 / G40 同机位父帧
    require(not {f["code"] for f in check(pr, "EP001").warns()} & {"G36", "G37", "G38", "G39", "G40"}, "示例应不触发 G36–G40")
    nb = json.loads(good_sp)
    nb["shots"][0]["frame_prompt"] += " 85mm, bokeh, no volumetric haze."
    nb["shots"][1]["frame_refs"] = ["IMG-PLATE-MEETING", "IMG-HARUKA", "IMG-MIKAMI", "IMG-HARUKA-FACE"]
    nb["shots"][2]["frame_parent"] = "EP001-S04"
    nb["shots"][3]["frame_parent"] = "EP001-S01"
    sp.write_text(json.dumps(nb, ensure_ascii=False), encoding="utf-8")
    rp0 = root / "参考图/refs.json"; refs_before = rp0.read_text(encoding="utf-8")
    rj = json.loads(refs_before)
    hk = rj["refs"]["IMG-HARUKA"]
    rj["refs"]["IMG-HARUKA-FACE"] = {**hk, "refs": ["IMG-HARUKA"], "voice": None,
                                     "prompt": hk["prompt"].replace("full-body", "head-and-shoulders").replace("Full-body", "Head-and-shoulders")}
    rp0.write_text(json.dumps(rj, ensure_ascii=False), encoding="utf-8")
    saved = {k: pr.cfg.get(k) for k in ("style_preset", "ai_label", "line_max", "video_prompt_head")}
    pr.cfg["style_preset"] = "anime_cel"; pr.cfg.pop("ai_label", None); pr.cfg["line_max"] = {"ja": 5}
    pr.cfg["video_prompt_head"] = "Handheld camera with small natural breathing sway, realistic human behaviour, drifting particles."   # 旧版真人头句
    Fg = check(pr, "EP001")
    wg = [(f["code"], f["shot"], f["msg"]) for f in Fg.warns()]
    eg = {(f["code"], f["shot"]) for f in Fg.errors()}
    g36 = [m for c, s_, m in wg if c == "G36" and s_ == "EP001-S01"]
    require(g36 and "85mm" in g36[0] and "bokeh" in g36[0] and "volumetric" not in g36[0], f"动漫画风起始帧摄影词报 G36、否定式不算：{g36}")
    require(any(c == "G36" and s_ is None and "handheld" in m.lower() for c, s_, m in wg), "动漫画风沿用真人视频头句要报 G36")
    require(any(c == "G36" and s_ is None and "particles" in m for c, s_, m in wg), "视频头句含运镜/特效词（handheld、particles…）要报 G36")
    require(any(c == "G37" for c, _, _ in wg), "单句超过 line_max 要报 G37")
    g38 = [m for c, s_, m in wg if c == "G38" and s_ == "EP001-S02"]
    require(any("4 张" in m for m in g38) and any("职责重叠" in m for m in g38), f"参考图超 3 张、全身图和头肩图同绑要报 G38：{g38}")
    require(any(c == "G39" for c, _, _ in wg), "drama.json 没写 ai_label 要报 G39")
    require(("G40", "EP001-S03") in eg, "frame_parent 指向后面的镜要报 G40 error")
    require(any(c == "G40" and s_ == "EP001-S04" for c, s_, _ in wg), "frame_parent 不同主体要报 G40 warn")
    Frf = check_refs(pr)
    require(not any(f["code"] == "G20" for f in Frf.errors()), "同一人物的全身图和头肩图不报 G20")
    require(not any(f["shot"] == "IMG-HARUKA-FACE" and ("全身" in f["msg"] or f["code"] == "G34") for f in Frf.warns()), "头肩图免全身、身高 warn")
    for k, v in saved.items():
        if v is None:
            pr.cfg.pop(k, None)
        else:
            pr.cfg[k] = v
    rp0.write_text(refs_before, encoding="utf-8")
    sp.write_text(good_sp, encoding="utf-8")
    passed += 1

    # G42 节奏下限 / G43 视线 / G44 台词语种与读音 / G45 同人相邻不拆 / G32 事件起因
    require(not {f["code"] for f in check(pr, "EP001").warns()} & {"G42", "G43", "G44", "G45"}, "示例应不触发 G42–G45")
    nb = json.loads(good_sp)
    by = {s_["id"]: s_ for s_ in nb["shots"]}
    by["EP001-S02"]["motion"] += "取用约 1.0s。"
    by["EP001-S04"]["motion"] += "取用约 1.2s。"
    by["EP001-S01"].pop("gaze")
    by["EP001-S01"]["frame_prompt"] += " She looks straight into the camera."
    by["EP001-S03"]["gaze"] = {"target": "遥", "direction": "left"}
    by["EP001-S03"]["frame_prompt"] += " Nobody looks at the camera."
    by["EP001-S04"]["gaze"] = {"target": "三上", "direction": "right"}
    by["EP001-S01"]["dialogue"][0]["lang"] = "zh"
    by["EP001-S03"]["video_prompt"] = by["EP001-S03"]["video_prompt"].replace("[Japanese]", "[Chinese]", 1)
    by["EP001-S04"]["dialogue"][0]["text"] = "三上さん、承認料は？"
    by["EP001-S03"]["title"] = "三上撞翻杯子"
    sp.write_text(json.dumps(nb, ensure_ascii=False), encoding="utf-8")
    Fp = check(pr, "EP001")
    wp = [(f["code"], f["shot"], f["msg"]) for f in Fp.warns()]
    has = lambda c, s_, word="": any(c == c_ and s_ == sh_ and word in m for c_, sh_, m in wp)
    require(has("G42", "EP001-S02", "fast_cut_reason") and has("G42", "EP001-S04", "对白镜") and has("G42", None, "EP001-SC002"),
            f"插入镜过短无理由、对白镜过短、同场平均镜长过短要报 G42：{[x for x in wp if x[0] == 'G42']}")
    require(has("G43", "EP001-S01", "没写 gaze") and has("G43", "EP001-S03", "同一侧") and has("G43", "EP001-S04", "facing") and has("G43", "EP001-S04", "不一致"),
            f"缺 gaze、视线与 facing 矛盾、与对手看同一侧要报 G43：{[x for x in wp if x[0] == 'G43']}")
    require(not has("G43", "EP001-S03", "看镜头"), "否定式 nobody looks at the camera 不算看镜头")
    by["EP001-S01"]["gaze"] = {"target": "三上", "direction": "left"}
    sp.write_text(json.dumps(nb, ensure_ascii=False), encoding="utf-8")
    require(any(f["code"] == "G43" and f["shot"] == "EP001-S01" and "看镜头" in f["msg"] for f in check(pr, "EP001").warns()), "提示词让人物看镜头要报 G43")
    require(has("G44", "EP001-S01", "lang=zh") and has("G44", "EP001-S03", "chinese") and has("G44", "EP001-S04", "三上"),
            f"lang 不一致、语种标签错、专名缺读音要报 G44：{[x for x in wp if x[0] == 'G44']}")
    require(has("G32", "EP001-S03", "起因"), "事件镜没写起因要报 G32")
    by["EP001-S02"]["fast_cut_reason"] = "冲击剪辑：红笔划下那一下的重音"
    by["EP001-S04"]["dialogue"][0]["reading"] = {"三上": "みかみ"}
    by["EP001-S03"]["requires_setup"] = ["EP001-S03"]   # 起因就在本镜里先发生
    nb["cut_order"] = ["EP001-S02", "EP001-S03", "EP001-S01", "EP001-S04"]
    by["EP001-S04"]["scene"] = "EP001-SC001"
    sp.write_text(json.dumps(nb, ensure_ascii=False), encoding="utf-8")
    wp = [(f["code"], f["shot"], f["msg"]) for f in check(pr, "EP001").warns()]
    require(not has("G42", "EP001-S02") and not has("G44", "EP001-S04", "三上") and not has("G32", "EP001-S03"),
            f"写了 fast_cut_reason、reading、镜内起因就不报：{[x for x in wp if x[0] in ('G42', 'G44', 'G32')]}")
    require(has("G45", "EP001-S04", "长镜头") and not has("G27", "EP001-S04"), f"同场同人相邻要报 G45（不再重复报 G27）：{[x for x in wp if x[0] in ('G45', 'G27')]}")
    by["EP001-S04"]["split_reason"] = "从中近景切到近景，强调她放下杯子的那一刻"
    sp.write_text(json.dumps(nb, ensure_ascii=False), encoding="utf-8")
    require(not any(c == "G45" for c, _, _ in [(f["code"], f["shot"], f["msg"]) for f in check(pr, "EP001").warns()]), "写了 split_reason 不报 G45")
    sp.write_text(good_sp, encoding="utf-8")
    from review_quality import speech_diff
    require("语种疑似不符" in speech_diff("売上、渡せよ。", "卖上交出来")["critical_changes"], "日语台词被整句识别成中文要标语种疑似不符")
    passed += 1

    # G46 必拍事实覆盖 / G47 数量写进起始帧 / G48 能力重复解释 / G49 只说不做
    F0 = check(pr, "EP001")
    require(not {f["code"] for f in F0.items} & {"G46", "G47", "G48", "G49"}, f"示例应不触发 G46–G49：{[f for f in F0.items if f['code'] in ('G46', 'G47', 'G48', 'G49')]}")
    nb = json.loads(good_sp)
    by = {s_["id"]: s_ for s_ in nb["shots"]}
    scn = {s_["id"]: s_ for s_ in nb["scenes"]}
    by["EP001-S02"]["must_show_ids"] = []                                   # MS1 没有镜承担
    scn["EP001-SC002"]["must_show"][0]["shots"] = ["EP001-S09"]             # 指向不存在的镜
    by["EP001-S03"]["must_show_ids"] = ["MS3", "MS9"]                       # 未登记的事实
    scn["EP001-SC002"]["must_show"].append({"id": "MS5", "fact": "桌上正好十份文件，左五份右五份", "shots": ["EP001-S04"], "kind": "count"})
    by["EP001-S04"]["must_show_ids"] = ["MS4", "MS5"]
    sp.write_text(json.dumps(nb, ensure_ascii=False), encoding="utf-8")
    Fm = check(pr, "EP001")
    em = [(f["shot"], f["msg"]) for f in Fm.errors() if f["code"] == "G46"]
    require(any("MS1" in m and "没有任何镜头" in m for _, m in em) and any("EP001-S09" in m for _, m in em) and any(s_ == "EP001-S03" and "MS9" in m for s_, m in em),
            f"必拍事实无镜承担、shots 指向不存在的镜、must_show_ids 未登记要报 G46 error：{em}")
    g47 = [f["msg"] for f in Fm.warns() if f["code"] == "G47" and f["shot"] == "EP001-S04"]
    require(g47 and "10" in g47[0] and "5" in g47[0], f"数量事实的承担镜 frame_prompt 没写出数字要报 G47（年龄 28 不算）：{g47}")
    by["EP001-S04"]["frame_prompt"] += " Exactly ten folders lie on the table, five on the left and five on the right."
    by["EP001-S02"]["must_show_ids"] = ["MS1"]
    nb["cut_order"] = ["EP001-S03", "EP001-S01", "EP001-S04"]               # 删掉 S02：MS1 的唯一承担镜被删
    sp.write_text(json.dumps(nb, ensure_ascii=False), encoding="utf-8")
    Fm = check(pr, "EP001")
    require(not any(f["code"] == "G47" for f in Fm.warns()), "数字写进起始帧后不报 G47")
    require(any(f["code"] == "G46" and "cut_order" in f["msg"] and "MS1" in f["msg"] for f in Fm.errors()), "承担镜被删出 cut_order 要报 G46 error（删镜删掉因果证据）")
    nb = json.loads(good_sp)
    by = {s_["id"]: s_ for s_ in nb["shots"]}
    for k in ("EP001-S01", "EP001-S03", "EP001-S04"):
        by[k]["explains_ability"] = True
    by["EP001-S04"]["scene"] = "EP001-SC001"
    by["EP001-S03"]["motion"] = "约 0.5 秒开口嘲讽，笑出声；约 3.2 秒再说第二句；说完笑容不变。"
    by["EP001-S04"]["motion"] = "约 0.6 秒开口，语气像随口一问；说完看着画左等答案。"
    sp.write_text(json.dumps(nb, ensure_ascii=False), encoding="utf-8")
    Fa = check(pr, "EP001")
    require(any(f["code"] == "G48" and "3 镜" in f["msg"] for f in Fa.warns()), f"同集解释能力超过 2 镜要报 G48：{[f for f in Fa.warns() if f['code'] == 'G48']}")
    require(not any(f["code"] == "G48" and "开头" in f["msg"] for f in Fa.warns()), "第一集不查跨集开头回顾")
    require(any(f["code"] == "G49" and "EP001-SC001" in f["msg"] and "3/3" in f["msg"] for f in Fa.warns()), f"场内对白镜都只说不做要报 G49：{[f for f in Fa.warns() if f['code'] == 'G49']}")
    by["EP001-S04"]["motion"] = "她把杯子推回三上面前；约 0.6 秒开口；说完看着画左等答案。"
    by["EP001-S03"]["waive"] = ["G49"]
    sp.write_text(json.dumps(nb, ensure_ascii=False), encoding="utf-8")
    Fw = check(pr, "EP001")
    require(any(f["code"] == "G49" for f in Fw.warns()) and any(f["code"] == "G51" and "旧写法" in f["msg"] for f in Fw.warns()),
            "旧写法 waive [\"G49\"]（无理由、无决策号）不生效并报 G51")
    (pr.root / "项目开发" / "决策记录.md").write_text("| 编号 | 日期 | 阶段 | 拍板人 |\n|---|---|---|---|\n| D-001 | 2026-09-26 | E | 代理 | — | 豁免 G49 |\n", encoding="utf-8")
    by["EP001-S03"]["waive"] = [{"gate": "G49", "reason": "三上这镜的嘲笑本身就是改变局面的反应，笑声压住遥", "decision": "D-001"}]
    sp.write_text(json.dumps(nb, ensure_ascii=False), encoding="utf-8")
    require(not any(f["code"] == "G49" for f in check(pr, "EP001").warns()), "补了承接动作或完整豁免（门号+理由+决策号）后不报 G49")
    sp.write_text(good_sp, encoding="utf-8")

    # 红队回归（scratchpad/rt harness T2–T4、kind 逃门、G47/G52/G53）：每条都应被拦下
    nb = json.loads(good_sp)
    by = {s_["id"]: s_ for s_ in nb["shots"]}
    scn = {s_["id"]: s_ for s_ in nb["scenes"]}
    by["EP001-S01"]["kind"] = "object"                                       # 有台词的人物镜改成物件镜
    by["EP001-S01"]["frame_prompt"] = by["EP001-S01"]["frame_prompt"].replace("Exactly two people in the frame, each appearing once. ", "")
    by["EP001-S03"]["dialogue"][0]["text"] += "ぜんぜん違う"
    by["EP001-S03"]["waive"] = [{"gate": "G10", "reason": "自测：想用豁免把台词漂移压下去", "decision": "D-001"}, "G06"]
    by["EP001-S04"]["frame_prompt"] = by["EP001-S04"]["frame_prompt"].replace("no text, ", "")
    by["EP001-S04"]["waive"] = ["G06"]
    scn["EP001-SC001"]["must_show"] = scn["EP001-SC001"]["must_show"][:2]      # 剧本 3 条必拍，只抄 2 条
    scn["EP001-SC001"]["must_show"][1]["fact"] = "有"                         # 空话
    by["EP001-S03"]["must_show_ids"] = []
    scn["EP001-SC002"]["must_show"][0].update(fact="桌上正好十份文件", kind="state")   # 改 kind 逃 G47
    by["EP001-S02"]["adversarial_preflight"][0]["blocked_by"] = "a sentence that is not in any prompt"
    by["EP001-S02"]["adversarial_preflight"][2]["worst"] = by["EP001-S02"]["adversarial_preflight"][1]["worst"]
    by["EP001-S03"].pop("adversarial_preflight")
    sp.write_text(json.dumps(nb, ensure_ascii=False), encoding="utf-8")
    saved = {k: pr.cfg.get(k) for k in ("one_person_clause", "no_text_clause", "gate_limits", "final_qa")}
    pr.cfg.update(one_person_clause="", no_text_clause="", gate_limits={"talk_only_ratio": 1.0}, final_qa={"asr_min": 0.0})
    Fr_ = check(pr, "EP001")
    e_ = {(f["code"], f["shot"]) for f in Fr_.errors()}
    w_ = {(f["code"], f["shot"]) for f in Fr_.warns()}
    em_ = [f["msg"] for f in Fr_.errors()]
    require(("G02", "EP001-S01") in e_ and ("G01", "EP001-S01") in w_, f"kind 改成 object 逃不掉人物镜的人数句门：{e_}")
    require(("G10", "EP001-S03") in e_ and ("G06", "EP001-S04") in e_, f"error 门写 waive 也照样 error：{e_}")
    require(("G51", "EP001-S03") in w_ and ("G51", "EP001-S04") in w_, "失效的豁免报 G51")
    require(sum(1 for f in Fr_.errors() if f["code"] == "G50") >= 2 and ("G50", None) in w_, f"阈值调松报 G50 error、固定句置空报 G50 warn：{em_}")
    require(any(f["code"] == "G46" and "只有 2 条" in f["msg"] for f in Fr_.errors()) and any(f["code"] == "G46" and "没照抄" in f["msg"] for f in Fr_.errors()),
            f"剧本必拍与 must_show 对账（条数、照抄）：{[m for m in em_ if '必拍' in m]}")
    require(any(f["code"] == "G47" for f in Fr_.warns()), "写了数量的事实改 kind 也按数量查 G47")
    require(("G52", "EP001-S02") in e_ and ("G52", "EP001-S03") in w_, f"恶意预演 blocked_by 不在提示词里/worst 重复报 error、缺预演报 warn：{e_}")
    pr.cfg.update(saved)
    nb = json.loads(good_sp)
    by = {s_["id"]: s_ for s_ in nb["shots"]}
    by["EP001-S01"].pop("multi_person")
    by["EP001-S01"]["frame_prompt"] = by["EP001-S01"]["frame_prompt"].replace("Exactly two people in the frame, each appearing once.", "Only one person in the frame.")
    sp.write_text(json.dumps(nb, ensure_ascii=False), encoding="utf-8")
    require(("G53", "EP001-S01") in {(f["code"], f["shot"]) for f in check(pr, "EP001").errors()}, "台词镜只有一人入画、没写 single_reason 报 G53 error")
    by["EP001-S01"]["single_reason"] = "遥在 S01 是对满桌人宣布放弃署名（剧本「名前は消していいです」），上一镜 S02 已建立全桌站位"
    sp.write_text(json.dumps(nb, ensure_ascii=False), encoding="utf-8")
    require(("G53", "EP001-S01") not in {(f["code"], f["shot"]) for f in check(pr, "EP001").errors()}, "写了具体 single_reason 不报 G53")
    sp.write_text(good_sp, encoding="utf-8")
    ep2 = root / "EP002"
    ep2.mkdir(exist_ok=True)
    for f_ in ("剧本.md", "视觉设定.md", "shots.json"):
        (ep2 / f_).write_text((root / "EP001" / f_).read_text(encoding="utf-8").replace("EP001", "EP002"), encoding="utf-8")
    n2 = json.loads((ep2 / "shots.json").read_text(encoding="utf-8"))
    for s_ in n2["shots"]:
        s_["explains_ability"] = s_["id"] in ("EP002-S03", "EP002-S01")   # cut_order 里第 2、3 镜，都在开头 30 秒内
    (ep2 / "shots.json").write_text(json.dumps(n2, ensure_ascii=False), encoding="utf-8")
    w48 = [f["msg"] for f in check(pr, "EP002").warns() if f["code"] == "G48"]
    require(len(w48) == 1 and "开头" in w48[0], f"第二集起开头 30 秒内解释能力超过 1 镜要报 G48（总量未超不另报）：{w48}")
    shutil.rmtree(ep2)
    passed += 1

    broken = json.loads((root / "EP001/shots.json").read_text(encoding="utf-8"))
    broken["shots"][0]["video_prompt"] = broken["shots"][0]["video_prompt"].replace("承認は、あなたがどうぞ。", "承認はどうぞ。")
    broken["shots"][2]["facing"] = "left"
    broken["shots"][3]["seconds"] = 3
    broken["shots"][3]["dialogue"][0]["text"] = "承認料、先週お振込みでしたよね。承認料、先週お振込みでしたよね。承認料、先週お振込みでしたよね。"
    broken["shots"][2]["frame_prompt"] += " He grins or maybe smirks."
    broken["shots"][3]["frame_prompt"] = broken["shots"][3]["frame_prompt"].replace("charcoal grey blazer", "grey blazer")
    broken["shots"][0]["video_prompt"] = broken["shots"][0]["video_prompt"].replace(" in a charcoal grey blazer", "")
    broken["shots"][3]["end_state"] = "同上，遥等答案。"
    broken["shots"][3]["scene"] = "EP001-SC001"
    broken["shots"][3]["framing"] = broken["shots"][0]["framing"]
    broken["shots"][3]["split_reason"] = "自测：写了拆镜理由但景别没变，仍是跳切（G27）"
    broken["shots"][0]["boundary"] = {"end": {"hands": "右手离开笔", "held": "无", "facing": "left"}}
    broken["shots"][3]["boundary"] = {"start": {"hands": "右手端咖啡杯", "held": "咖啡杯", "facing": "left"}}
    broken["shots"][2]["facing"] = "left"
    refs_v = json.loads((root / "参考图/refs.json").read_text(encoding="utf-8"))
    refs_v["refs"]["IMG-MIKAMI"]["voice"] = "a smooth condescending voice"
    (root / "参考图/refs.json").write_text(json.dumps(refs_v, ensure_ascii=False), encoding="utf-8")
    broken["shots"][2]["video_prompt"] = broken["shots"][2]["video_prompt"].replace("with a smooth condescending voice, ", "")
    bp = root / "EP001/shots.json"
    good = bp.read_text(encoding="utf-8")
    bp.write_text(json.dumps(broken, ensure_ascii=False), encoding="utf-8")
    Fb = check(pr, "EP001")
    ecodes = {(f["code"], f["shot"]) for f in Fb.errors()}
    require(("G09", "EP001-S01") in ecodes, "台词没逐字进视频提示词要报 G09")
    wcodes = {(f["code"], f["shot"]) for f in Fb.warns()}
    require(("G22", "EP001-S03") in wcodes, "分支词要报 G22")
    require(("G23", "EP001-S04") in ecodes, "锁面缺失要报 G23")
    require(("G23", "EP001-S01") in wcodes and ("G23", "EP001-S01") not in ecodes, "视频提示词缺锁面要报 G23 warn（不升 error）")
    require(("G24", "EP001-S04") in ecodes, "回指词要报 G24")
    require(("G26", "EP001-S04") in ecodes, f"边界链不接要报 G26：{ecodes}")
    require(("G27", "EP001-S04") in wcodes and ("G45", "EP001-S04") not in wcodes, "写了 split_reason 却同景别，报 G27 跳切、不报 G45")
    require(any(c == "G25" for c, _ in wcodes), "同场朝向不互补要报 G25")
    require(("G21", "EP001-S03") in wcodes, "音色描述缺失要报 G21")
    require(("G04", "EP001-S04") in ecodes, "台词装不下要报 G04")
    require(("G10", "EP001-S04") in ecodes, "台词不在剧本里要报 G10")
    require(not any(c == "G08" for c, _ in ecodes), "三上只出现一次，改朝向不构成轴线冲突")
    bp.write_text(good, encoding="utf-8")
    passed += 1

    from shots_tool import build_video_prompt
    Fr = check_refs(pr)
    require(not Fr.errors(), f"示例 refs.json 应无 error：{Fr.errors()}")
    bad_refs = json.loads((root / "参考图/refs.json").read_text(encoding="utf-8"))
    bad_refs["refs"]["IMG-MIKAMI"]["prompt"] = bad_refs["refs"]["IMG-HARUKA"]["prompt"]
    bad_refs["refs"]["IMG-PLATE-MEETING"]["prompt"] = "A quiet meeting room, no text."
    rp_ = root / "参考图/refs.json"; good_refs = rp_.read_text(encoding="utf-8")
    rp_.write_text(json.dumps(bad_refs, ensure_ascii=False), encoding="utf-8")
    Frb = check_refs(pr)
    rcodes = {f["code"] for f in Frb.errors()}
    require("G20" in rcodes and "G19" in rcodes, f"雷同身份图报 G20、底板没写 No people 报 G19：{rcodes}")
    require(("G34", "IMG-PLATE-MEETING") in {(f["code"], f["shot"]) for f in Frb.warns()}, "底板没写尺度参照要报 G34")
    require(not any(f["code"] == "G34" for f in Fr.warns()), "示例参考图写了身高和尺度，不报 G34")
    rp_.write_text(good_refs, encoding="utf-8")
    vp = build_video_prompt(pr, {"video_body": "He nods. <d>[Japanese] はい。</d>", "soundscape": "rain"})
    require(vp.startswith("integrated_multimodal_description:") and "\noverall_soundscape: rain\nnon_diegetic_music: N/A" in vp, "骨架拼装")
    passed += 1

    outs = render(pr, "EP001")
    require(len(outs) == 3 and all(p.exists() for p in outs), "渲染三份文档")
    require("SHOT-EP001-S03" in (root / "EP001/分镜.md").read_text(encoding="utf-8"), "分镜.md 含镜头块")
    require((pr.prompts_dir("EP001") / "video_EP001-S01.txt").exists(), "导出提示词文件")
    cov = coverage(pr, "EP001")
    require(all(s["covered"] for s in cov["scenes"]), "覆盖：每场都有镜头")
    passed += 1

    c = Client(root=root, log_dir=pr.scripts_dir)
    require(c.status()["queued"] == 0, "status")
    passed += 1

    done = produce.produce_refs(pr)
    require(set(done) == {"IMG-HARUKA", "IMG-MIKAMI", "IMG-PLATE-MEETING"}, f"参考图全部生成：{done}")
    require(all(pr.ref_png(r).exists() for r in done), "参考图落盘")
    require(not produce.produce_refs(pr), "已有参考图跳过")
    passed += 1

    done = produce.produce_frames(pr, "EP001")
    require(len(done) == 4 and pr.frame_path("EP001", "EP001-S01", 1).exists(), "起始帧 take1")
    require(not produce.produce_frames(pr, "EP001"), "已有起始帧跳过")
    produce.produce_frames(pr, "EP001", ["EP001-S02"], retake=True)
    require(pr.takes("EP001", "EP001-S02", "frame") == [1, 2], "retake 新开 take2")
    require(pr.chosen_take("EP001", "EP001-S02", "frame") == 2, "默认选最新 take")
    passed += 1

    # 视频提交预检（红队 T12）：起始帧没目检、预演没放行时拒绝；金丝雀只放一镜
    expect_exit(lambda: produce.produce_videos(pr, "EP001"), "预演", "预演没放行时 produce videos 拒绝整批提交")
    expect_exit(lambda: produce.produce_videos(pr, "EP001", ["EP001-S01"]), "目检", "金丝雀镜的起始帧没目检也拒绝")
    review_frames(pr)
    done = produce.produce_videos(pr, "EP001", ["EP001-S01"])
    require(done == ["EP001-S01"], f"金丝雀一镜可以在预演前提交：{done}")
    expect_exit(lambda: produce.produce_videos(pr, "EP001", ["EP001-S02"]), "预演", "已有金丝雀视频后，第二镜仍要等预演放行")
    lg = [json.loads(x) for x in (pr.scripts_dir / "jobs.jsonl").read_text(encoding="utf-8").splitlines()]
    sub_v = next(j for j in lg if j.get("status") == "submitted" and j.get("name") == "V_EP001-S01_t1")
    col_v = next(j for j in lg if j.get("status") == "collected" and j.get("out", "").endswith("V_EP001-S01_t1.mp4"))
    from review_quality import media_digest as _md
    require(sub_v.get("frame_sha256") == _md(pr.frame_path("EP001", "EP001-S01", 1)) and sub_v.get("source_prompt_sha256")
            and col_v.get("sha256") == _md(pr.video_path("EP001", "EP001-S01", 1)), "账本记起始帧 sha、完整提示词 sha 与产物 sha")
    pass_animatic(pr, media=not args.no_media)
    os.environ["DF_SUBAGENT"] = "1"
    expect_exit(lambda: produce.produce_videos(pr, "EP001"), "子代理", "DF_SUBAGENT=1 时拒绝提交")
    try:
        Client(root=root, log_dir=pr.scripts_dir).submit_image("x", pr.frame_path("EP001", "EP001-S01", 9), profile="qwen21", res="1K", name="F_sub")
        require(False, "子代理直接调 h3_client 也要被拒")
    except SystemExit as e:
        require("子代理" in str(e), str(e))
    os.environ.pop("DF_SUBAGENT")
    done = produce.produce_videos(pr, "EP001")
    require(len(done) == 3 and pr.video_path("EP001", "EP001-S03", 1).exists(), "视频 take1（金丝雀之外的三镜）")
    posts_before = mock.posts
    require(not produce.produce_videos(pr, "EP001") and mock.posts == posts_before, "已有视频不重复提交")
    log = (pr.scripts_dir / "ids.log").read_text(encoding="utf-8").splitlines()
    require(len(log) == 3 + 5 + 4, f"ids.log 每次提交一行：{len(log)}")
    jobs = [json.loads(x) for x in (pr.scripts_dir / "jobs.jsonl").read_text(encoding="utf-8").splitlines()]
    require(sum(1 for j in jobs if j.get("status") == "collected") == 12, "每个任务都有 collected 记录")
    frame_job = next(j for j in mock.jobs.values() if j["kind"] == "image" and j["payload"]["res"] == "1K")
    require(len(frame_job["payload"]["images"]) == 2, "起始帧带底板+身份图两张参考")
    passed += 1

    # 同机位父帧：frame_parent 的通过帧作 Picture 1，frame_refs 顺延
    fp_sp = json.loads(bp.read_text(encoding="utf-8"))
    fp_sp["shots"][3]["frame_parent"] = "EP001-S01"
    bp.write_text(json.dumps(fp_sp, ensure_ascii=False), encoding="utf-8")
    n_before = mock.n
    produce.produce_frames(pr, "EP001", ["EP001-S04"], retake=True)
    job = mock.jobs[f"image-{mock.n}"]
    require(mock.n == n_before + 1 and len(job["payload"]["images"]) == 1 + len(fp_sp["shots"][3].get("frame_refs") or []),
            f"frame_parent 多挂一张父帧：{len(job['payload']['images'])}")
    bp.write_text(good, encoding="utf-8")

    if not args.no_media:
        # 阶段 G2 静帧预演：起始帧齐了但没写 预演.md 时 next 指向 G2；animatic 出预演片与接触表
        dev = root / "项目开发"
        brief_bak, beat_bak = (dev / "系列简报.md").read_text(encoding="utf-8"), (dev / "情绪集纲.md").read_text(encoding="utf-8")
        (dev / "系列简报.md").write_text("# 系列简报\n\n自测已填。\n", encoding="utf-8")
        (dev / "情绪集纲.md").write_text("| 集 | 行 |\n|---|---|\nEP001 | 自测 |\n", encoding="utf-8")
        for v in pr.ep_dir("EP001").joinpath("视频").glob("*.mp4"):
            v.rename(v.with_suffix(".bak"))
        require(next_step(pr).startswith("阶段 C") and "审查" in next_step(pr), f"没有 C 审查时 next 停在 C（红队 T10）：{next_step(pr)}")
        pass_reviews(pr)
        require(next_step(pr).startswith("阶段 G") and "目检" in next_step(pr), f"S04 起始帧重出后没目检，next 指向 G：{next_step(pr)}")
        review_frames(pr)
        (pr.review_dir / "EP001-预演.md").unlink()
        require(next_step(pr).startswith("阶段 G2"), f"起始帧齐、没有预演记录时 next 指向 G2：{next_step(pr)}")
        amp4, ajpg, amiss = review_tool.animatic(pr, "EP001")
        want = sum(float(x["seconds"]) for x in json.loads(bp.read_text(encoding="utf-8"))["shots"])
        require(not amiss and abs(ffprobe_duration(amp4) - want) < 0.3 and ajpg.exists(), f"预演片时长 ≈ 各镜 seconds 之和 {want}：{ffprobe_duration(amp4)}")
        (pr.review_dir / "EP001-预演.md").write_text("结论：REVISE\n情节点 3 看不到\n", encoding="utf-8")
        require(next_step(pr).startswith("阶段 G2"), f"预演结论不是 PASS 时 next 仍停在 G2：{next_step(pr)}")
        require(not pr.animatic_passed("EP001"), "预演结论 REVISE 不放行")
        (pr.review_dir / "EP001-预演.md").write_text("\n结论：PASS\n情节点全部看得到\n", encoding="utf-8")
        require(next_step(pr).startswith("阶段 G2"), f"手写一行 PASS（没跑 animatic、没指纹、必拍没答）不放行（红队 T5）：{next_step(pr)}")
        pass_animatic(pr)
        require(next_step(pr).startswith("阶段 H"), f"预演放行后 next 指向 H：{next_step(pr)}")
        sp_txt = bp.read_text(encoding="utf-8")
        chg = json.loads(sp_txt); chg["shots"][0]["seconds"] = float(chg["shots"][0]["seconds"]) + 1
        bp.write_text(json.dumps(chg, ensure_ascii=False), encoding="utf-8")
        require(not pr.animatic_passed("EP001") and next_step(pr).startswith("阶段"), "PASS 之后改了 shots.json，旧预演过期（红队 T5b）")
        bp.write_text(sp_txt, encoding="utf-8")
        for v in pr.ep_dir("EP001").joinpath("视频").glob("*.bak"):
            v.rename(v.with_suffix(".mp4"))
        (dev / "系列简报.md").write_text(brief_bak, encoding="utf-8"); (dev / "情绪集纲.md").write_text(beat_bak, encoding="utf-8")
        passed += 1


    # 先收回再重投：手动提交一个起始帧任务但不下载，再跑 produce → 应收回而不是重新 POST
    sh5 = json.loads((root / "EP001/shots.json").read_text(encoding="utf-8"))["shots"][0]
    posts_before = mock.posts
    jid_pending = c.submit_image(sh5["frame_prompt"], pr.frame_path("EP001", "EP001-S01", 3), profile="qwen21", res="1K",
                                 seed=pr.seed("EP001-S01", "frame", 3), refs=[pr.ref_png(r) for r in sh5["frame_refs"]], name="F_EP001-S01_t3")
    require(c.pending("F_EP001-S01_t3")["job"] == jid_pending, "账本能找到未收回的任务")
    # 让 S01 的 take 序号走到 3：先造 take2 占位文件
    pr.frame_path("EP001", "EP001-S01", 2).write_bytes(mock.png)
    produce.produce_frames(pr, "EP001", ["EP001-S01"], retake=True)
    require(mock.posts == posts_before + 1, "有未收回任务时不重新 POST（只多了手动那一次）")
    require(pr.frame_path("EP001", "EP001-S01", 3).exists() and c.pending("F_EP001-S01_t3") is None, "收回落盘并标记 collected")
    passed += 1

    (root / "STOP").write_text("")
    try:
        produce.produce_frames(pr, "EP001", ["EP001-S04"], retake=True)
        require(False, "STOP 应当中止")
    except SystemExit as e:
        require(str(e) == "STOP", "STOP 触发")
    (root / "STOP").unlink()
    passed += 1

    if args.no_media:
        srv.shutdown()
        srv.server_close()
        shutil.rmtree(tmp, ignore_errors=True)
        print(f"{passed} contract/transport self-tests passed (media/ASR/edit skipped)")
        return 0

    made = review_tool.sheets(pr, "EP001")
    require(len(made) == 4 and made[0].suffix == ".jpg", "接触表")
    asr_py = review_tool.asr_python() if os.environ.get("SELFTEST_ASR") == "1" else None
    if asr_py:
        os.environ["ASR_MODEL"] = os.environ.get("ASR_MODEL", "tiny")
        res = review_tool.asr_all(pr, "EP001")
        require("EP001-S01_t1" in res and "hit" in res["EP001-S01_t1"], "ASR 记录结构")
        require(res["EP001-S02_t1"]["hit"] is None, "无台词镜 hit 为空")
        print("  ASR 用", asr_py, "模型", os.environ["ASR_MODEL"])
    else:
        print("  ASR 跳过（未设置 SELFTEST_ASR=1 或没有 faster-whisper 环境）")
    rv = review_tool.auto(pr, "EP001")
    require(all("verdict" in e for e in rv["shots"].values()), "auto 给每镜 verdict")
    def approve_fixture(sid, **kw):
        # Synthetic media contract fixture, not a claim of human/artistic approval.
        opts = dict(visual="pass", audio="pass", continuity="pass",
                    evidence="synthetic selftest fixture: injected approval for cut contract", verdict="ok")
        shot = next(x for x in pr.load_shots("EP001")["shots"] if x["id"] == sid)
        take = kw.get("video_take") or pr.chosen_take("EP001", sid, "video")
        if shot.get("dialogue"):
            opts["speech_window"] = [0.3, 2.5]
            opts["speaker_face_ok"] = True
            if not asr_py:   # 没跑真 ASR 时注入一条"对当前文件跑过 ASR"的记录（等同 review_tool.asr_shot 的产物）
                from review_quality import media_digest, shot_digest
                rv_ = pr.load_review("EP001")
                rec_ = rv_.setdefault("shots", {}).setdefault(sid, {}).setdefault("video_takes", {}).setdefault(str(take), {"take": take})
                rec_.update(asr_media_sha256=media_digest(pr.video_path("EP001", sid, take)), asr_shot_sha256=shot_digest(shot),
                            speech_diff={"status": "exact", "critical_changes": [], "similarity": 1.0})
                pr.save_review("EP001", rv_)
        if shot.get("must_show_ids"):
            opts["must_show"] = {m: "pass" for m in shot["must_show_ids"]}
        opts.update(kw)
        return review_tool.mark(pr, "EP001", sid, **opts)
    approve_fixture("EP001-S02", **{"in": 0.5}, out=2.5, mode="fixed", note="取中段")
    require(pr.load_review("EP001")["shots"]["EP001-S02"]["locked"], "mark 锁定")
    rp = review_tool.report(pr, "EP001")
    require(rp.exists() and "EP001-S02" in rp.read_text(encoding="utf-8"), "审片报告")
    passed += 1

    for sid in ("EP001-S01", "EP001-S03", "EP001-S04"):
        approve_fixture(sid, mode="full")
    shots_v = json.loads(bp.read_text(encoding="utf-8"))
    (root / "音效").mkdir(exist_ok=True)
    shutil.copy(tmp / "mock.mp4", root / "音效/click.mp4")
    shots_v["shots"][0]["sfx"] = [{"file": "音效/click.mp4", "at": 0.5, "gain_db": -6}]
    bp.write_text(json.dumps(shots_v, ensure_ascii=False), encoding="utf-8")
    approve_fixture("EP001-S01", mode="full")  # shot sfx edit invalidates its prior evidence
    out = cut_mod.cut(pr, "EP001")
    require(out is not None and out.exists(), "成片输出")
    d = ffprobe_duration(out)
    require(9.5 < d < 11.5, f"成片时长 ≈ 3×2.8 + 2.0 = 10.4，实际 {d:.2f}")
    require((root / "EP001/剪辑单.md").exists(), "剪辑单")
    sheet_txt = (root / "EP001/剪辑单.md").read_text(encoding="utf-8")
    require("房间音 -48 dBFS 整片" in sheet_txt and "音效 1 个" in sheet_txt, "没有 beds 时整片垫房间音、sfx 叠进去")
    want_label = "AI 标识：无" if pr.cfg.get("ai_label") is None else "AI 标识：有"   # 模板默认 ai_label: null（用户 2026-09-26：没让加就不加）
    require(want_label in sheet_txt or "找不到字体" in sheet_txt, f"剪辑单按 ai_label 记 AI 标识（期望「{want_label}」）：{sheet_txt[-200:]}")
    require("节奏：平均镜长" in sheet_txt and "面板：1 个，主题 tech" in sheet_txt, f"剪辑单记节奏统计与面板：{sheet_txt[-400:]}")
    passed += 1

    # 面板渲染：合成背景上叠一条面板；面板前后像素不同（面板存在），入场帧与中间帧不同（有动画）
    pd = cut_mod.panel_demo(tmp / "panel_test.png", "tech")
    require(pd["frame"].exists() and pd["before_vs_mid"] > 1.0 and pd["enter_vs_mid"] > 0.5,
            f"面板帧存在且有入场动画：前/中 {pd['before_vs_mid']:.2f}，入场/中 {pd['enter_vs_mid']:.2f}")
    for th in ("xianxia", "scroll"):
        pd2 = cut_mod.panel_demo(tmp / f"panel_{th}.png", th)
        require(pd2["before_vs_mid"] > 1.0, f"{th} 面板主题能渲染：{pd2['before_vs_mid']:.2f}")
    require(cut_mod.panel_sfx(cut_mod.panel_cfg({}), tmp) is not None, "面板入场音效能程序生成")
    passed += 1

    # 运动能量：前 1s 静止、1–3s 方块移动、3–4s 静止
    syn = pr.video_path("EP001", "EP001-S02", 3)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=black:s=320x180:d=4:r=24", "-f", "lavfi",
                    "-i", "color=c=white:s=60x60:d=4:r=24", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
                    "-filter_complex", "[0][1]overlay=x='if(lt(t,1),20,if(lt(t,3),20+(t-1)*110,240))':y=60:shortest=1[v]",
                    "-map", "[v]", "-map", "2:a", "-t", "4", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(syn)], check=True)
    from review_quality import media_digest as _md2, text_digest as _td
    with open(pr.scripts_dir / "jobs.jsonl", "a", encoding="utf-8") as fh:   # 合成 take 的账本记录（等同生成通道收回时写的）
        sh2 = next(x for x in pr.load_shots("EP001")["shots"] if x["id"] == "EP001-S02")
        fh.write(json.dumps({"status": "submitted", "job": "syn-3", "out": str(syn.resolve()), "source_prompt_sha256": _td(sh2["video_prompt"])}) + "\n")
        fh.write(json.dumps({"status": "collected", "job": "syn-3", "out": str(syn.resolve()), "sha256": _md2(syn)}) + "\n")
    mv = review_tool.motion_all(pr, "EP001", ["EP001-S02"])["EP001-S02_t3"]
    require(len(mv["motion"]) == 16 and max(mv["motion"][:3]) < 0.2 and min(mv["motion"][5:11]) > 1.0, f"运动曲线每 0.25s 一格、静止段近零：{mv['motion']}")
    require(abs(mv["action_start"] - 1.0) <= 0.25 and abs(mv["action_end"] - 3.0) <= 0.25 and 1.0 <= mv["action_peak"] <= 3.0,
            f"动作起止 ≈ 1.0–3.0s：{mv}")
    rv3 = pr.load_review("EP001")["shots"]["EP001-S02"]["video_takes"]["3"]
    require(rv3.get("action_end") == mv["action_end"] and rv3.get("motion"), "motion 写进 review.json 的 video_takes")
    orig_curve = review_tool.motion_curve
    review_tool.motion_curve = lambda *a, **k: (_ for _ in ()).throw(AssertionError("缓存未命中"))
    try:
        review_tool.motion_all(pr, "EP001", ["EP001-S02"])
    finally:
        review_tool.motion_curve = orig_curve
    passed += 1

    # 动作保护：固定区间保护已审 take 的动作；修改计划后须重审；mode=action
    approve_fixture("EP001-S02", video_take=3, **{"in": 0.0}, out=0.8, mode="fixed", action_window=[mv["action_start"], mv["action_end"]])
    cut_mod.cut(pr, "EP001", dry=True)
    row = next(x for x in (root / "EP001/剪辑单.md").read_text(encoding="utf-8").splitlines() if "| EP001-S02 |" in x)
    want_out = min(ffprobe_duration(syn) - 0.1, mv["action_end"] + 0.2)
    require(f"0.00–{want_out:.2f}（fixed）" in row and "取用因已审动作/对白保护" in row, f"fixed 出点因动作延长：{row}")
    shots_v["shots"][1]["planned_action_window"] = [1.0, 2.0]
    bp.write_text(json.dumps(shots_v, ensure_ascii=False), encoding="utf-8")
    approve_fixture("EP001-S02", video_take=3, action_window=[1.0, 2.0])
    cut_mod.cut(pr, "EP001", dry=True)
    row = next(x for x in (root / "EP001/剪辑单.md").read_text(encoding="utf-8").splitlines() if "| EP001-S02 |" in x)
    require("0.00–2.20（fixed）" in row and "reviewed_take" in row, f"仅使用本 take 实测区间：{row}")
    review_tool.mark(pr, "EP001", "EP001-S02", out=None, mode="action")
    cut_mod.cut(pr, "EP001", dry=True)
    row = next(x for x in (root / "EP001/剪辑单.md").read_text(encoding="utf-8").splitlines() if "| EP001-S02 |" in x)
    require("0.00–2.20（action）" in row, f"mode=action 出点 = 动作结束 + 0.2：{row}")
    passed += 1

    from cut import align_phrases
    words = [(0.5, 0.8, "名前は"), (0.9, 1.4, "消して"), (1.4, 1.9, "いいです"), (2.2, 2.6, "承認は"), (2.6, 3.2, "あなたが")]
    al = align_phrases(words, ["名前は消していいです。", "承認はあなたが。"])
    require(al[0] == (0.5, 1.9) and al[1] == (2.2, 3.2), f"按句对齐 ASR 词：{al}")
    require(align_phrases(words, ["消していいです"])[0] == (0.9, 1.9), "短语对齐落在那一小句结束的那个词")
    require(align_phrases(words, ["全然違う台詞"])[0] is None, "对不上返回 None")
    passed += 1

    st = status(pr)
    require(st["episodes"]["EP001"]["成片"] and st["episodes"]["EP001"]["视频"] == 4, "status 统计")
    from project_tool import delivery_problems
    dp = delivery_problems(pr, "EP001")
    require(not st["episodes"]["EP001"]["终验"] and any("final-qa" in x for x in dp) and any("成片终验" in x for x in dp),
            f"成片在但没跑 final_qa、没写成片终验.md 时 J 未完成（红队 T9）：{dp}")
    require("全部集已出成片" in next_step(pr) or "阶段" in next_step(pr), "next 可运行")
    passed += 1

    srv.shutdown()
    srv.server_close()
    shutil.rmtree(tmp, ignore_errors=True)
    print(f"{passed} self-tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
