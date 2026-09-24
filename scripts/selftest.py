#!/usr/bin/env python3
"""离线自测：起一个假的 H3 中转，把 init → 门 → 渲染 → 参考图/起始帧/视频 → 审片 → 剪辑 整条链跑一遍。
不联网、不用真 token。需要 ffmpeg/ffprobe 与 Pillow；有 faster-whisper 环境时顺带测 ASR（ASR_MODEL=tiny）。"""
from __future__ import annotations

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


# ---- 假中转 --------------------------------------------------------------------
class Mock:
    def __init__(self, tmp: Path):
        from PIL import Image
        buf = io.BytesIO()
        Image.new("RGB", (64, 36), (30, 60, 120)).save(buf, "PNG")
        self.png = buf.getvalue()
        vid = tmp / "mock.mp4"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=0x203050:s=336x192:d=3:r=24", "-f", "lavfi",
                        "-i", "sine=frequency=440:duration=3", "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(vid)],
                       check=True)
        self.mp4 = vid.read_bytes()
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
                return self._json({"profiles": {"image": ["qwen21", "krea2_turbo"], "video": ["fasth3"]}})
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
    tmp = Path(tempfile.mkdtemp(prefix="sda_selftest_"))
    mock = Mock(tmp)
    srv = HTTPServer(("127.0.0.1", 0), make_handler(mock))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    os.environ["H3_API"] = f"http://127.0.0.1:{srv.server_port}"
    os.environ["H3_STUDIO_TOKEN"] = "test-token"
    os.environ.pop("SEED_OFF", None)
    os.environ.pop("DEADLINE", None)
    passed = 0

    from project_tool import init, next_step, status
    from common import Project
    from shots_tool import check, coverage, render
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
    require(next_step(pr).startswith("阶段 A"), "系列简报还是模板时 next 指向阶段 A")
    passed += 1

    F = check(pr, "EP001")
    require(not F.errors(), f"示例 shots.json 应无 error：{F.errors()}")
    codes = {f["code"] for f in F.warns()}
    require("G11" not in codes or all("对白" in f["msg"] for f in F.warns() if f["code"] == "G11"), "示例覆盖了全部场景")
    passed += 1

    broken = json.loads((root / "EP001/shots.json").read_text(encoding="utf-8"))
    broken["shots"][0]["video_prompt"] = broken["shots"][0]["video_prompt"].replace("承認は、あなたがどうぞ。", "承認はどうぞ。")
    broken["shots"][2]["facing"] = "left"
    broken["shots"][3]["seconds"] = 3
    broken["shots"][3]["dialogue"][0]["text"] = "承認料、先週お振込みでしたよね。承認料、先週お振込みでしたよね。承認料、先週お振込みでしたよね。"
    broken["shots"][2]["frame_prompt"] += " He grins or maybe smirks."
    broken["shots"][3]["frame_prompt"] = broken["shots"][3]["frame_prompt"].replace("charcoal grey blazer", "grey blazer")
    broken["shots"][3]["end_state"] = "同上，遥等答案。"
    broken["shots"][3]["scene"] = "EP001-SC001"
    broken["shots"][3]["framing"] = broken["shots"][0]["framing"]
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
    require(("G24", "EP001-S04") in ecodes, "回指词要报 G24")
    require(("G26", "EP001-S04") in ecodes, f"边界链不接要报 G26：{ecodes}")
    require(("G27", "EP001-S04") in wcodes, "同景别跳切要报 G27")
    require(any(c == "G25" for c, _ in wcodes), "同场朝向不互补要报 G25")
    require(("G21", "EP001-S03") in wcodes, "音色描述缺失要报 G21")
    require(("G04", "EP001-S04") in ecodes, "台词装不下要报 G04")
    require(("G10", "EP001-S04") in ecodes, "台词不在剧本里要报 G10")
    require(not any(c == "G08" for c, _ in ecodes), "三上只出现一次，改朝向不构成轴线冲突")
    bp.write_text(good, encoding="utf-8")
    passed += 1

    from shots_tool import check_refs, build_video_prompt
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

    done = produce.produce_videos(pr, "EP001")
    require(len(done) == 4 and pr.video_path("EP001", "EP001-S03", 1).exists(), "视频 take1")
    posts_before = mock.posts
    require(not produce.produce_videos(pr, "EP001") and mock.posts == posts_before, "已有视频不重复提交")
    log = (pr.scripts_dir / "ids.log").read_text(encoding="utf-8").splitlines()
    require(len(log) == 3 + 5 + 4, f"ids.log 每次提交一行：{len(log)}")
    jobs = [json.loads(x) for x in (pr.scripts_dir / "jobs.jsonl").read_text(encoding="utf-8").splitlines()]
    require(sum(1 for j in jobs if j.get("status") == "collected") == 12, "每个任务都有 collected 记录")
    frame_job = next(j for j in mock.jobs.values() if j["kind"] == "image" and j["payload"]["res"] == "1K")
    require(len(frame_job["payload"]["images"]) == 2, "起始帧带底板+身份图两张参考")
    passed += 1

    # 先收回再重投：手动提交一个起始帧任务但不下载，再跑 produce → 应收回而不是重新 POST
    sh5 = json.loads((root / "EP001/shots.json").read_text(encoding="utf-8"))["shots"][0]
    posts_before = mock.posts
    jid_pending = c.submit_image(sh5["frame_prompt"], pr.frame_path("EP001", "EP001-S01", 3), profile="qwen21", res="1K",
                                 seed=1, refs=[pr.ref_png(r) for r in sh5["frame_refs"]], name="F_EP001-S01_t3")
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

    made = review_tool.sheets(pr, "EP001")
    require(len(made) == 4 and made[0].suffix == ".jpg", "接触表")
    asr_py = review_tool.asr_python()
    if asr_py:
        os.environ["ASR_MODEL"] = os.environ.get("ASR_MODEL", "tiny")
        res = review_tool.asr_all(pr, "EP001")
        require("EP001-S01_t1" in res and "hit" in res["EP001-S01_t1"], "ASR 记录结构")
        require(res["EP001-S02_t1"]["hit"] is None, "无台词镜 hit 为空")
        print("  ASR 用", asr_py, "模型", os.environ["ASR_MODEL"])
    else:
        print("  ASR 跳过（没有 faster-whisper 环境）")
    rv = review_tool.auto(pr, "EP001")
    require(all("verdict" in e for e in rv["shots"].values()), "auto 给每镜 verdict")
    review_tool.mark(pr, "EP001", "EP001-S02", **{"in": 0.5}, out=2.5, mode="fixed", verdict="ok", note="取中段")
    require(pr.load_review("EP001")["shots"]["EP001-S02"]["locked"], "mark 锁定")
    rp = review_tool.report(pr, "EP001")
    require(rp.exists() and "EP001-S02" in rp.read_text(encoding="utf-8"), "审片报告")
    passed += 1

    for sid in ("EP001-S01", "EP001-S03", "EP001-S04"):
        review_tool.mark(pr, "EP001", sid, verdict="ok", mode="full")
    out = cut_mod.cut(pr, "EP001")
    require(out is not None and out.exists(), "成片输出")
    from common import ffprobe_duration
    d = ffprobe_duration(out)
    require(9.5 < d < 11.5, f"成片时长 ≈ 3×2.8 + 2.0 = 10.4，实际 {d:.2f}")
    require((root / "EP001/剪辑单.md").exists(), "剪辑单")
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
    require("全部集已出成片" in next_step(pr) or "阶段" in next_step(pr), "next 可运行")
    passed += 1

    srv.shutdown()
    shutil.rmtree(tmp, ignore_errors=True)
    print(f"{passed} self-tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
