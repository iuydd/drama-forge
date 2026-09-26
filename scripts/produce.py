#!/usr/bin/env python3
"""按 shots.json 串行生产：参考图 → 起始帧 → 视频。已有产物自动跳过，中断后重跑即可。

  produce.py refs   <项目> [IMG-ID ...] [--retake]
  produce.py frames <项目> <EP> [SID ...] [--retake]
  produce.py videos <项目> <EP> [SID ...] [--retake] [--asr]
  produce.py all    <项目> <EP> [--asr]          起始帧之后若 审查/<EP>-预演.md 不存在或首行不是「结论：PASS」（阶段 G2）就停下，不提交视频

- 每个镜头的起始帧/视频都带 take 编号（F_<sid>_t1.png、V_<sid>_t1.mp4）；--retake 在已有 take 之后新开一个，种子随 take 变化。
- --asr：生成后记录逐字差异并选择待审候选；识别差异需听审，不按分数自动花费重拍。
- 一次只有一个任务在飞；STOP 文件 / DEADLINE 到点就停；token 只从 H3_STUDIO_TOKEN 读。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import Project  # noqa: E402
from h3_client import Client, Stop  # noqa: E402


def _client(project: Project) -> Client:
    return Client(api=project.get("api_base"), root=project.root, log_dir=project.scripts_dir)


def _frame_client(project: Project) -> Client:
    """drama.json frame_provider=fal 时起始帧走 fal 图片编辑端点（profiles.frame = fal 端点 ID）。"""
    if project.get("frame_provider") == "fal":
        from fal_client import FalImageClient
        return FalImageClient(project.sub("profiles")["frame"], root=project.root, log_dir=project.scripts_dir)
    return _client(project)


import threading as _threading
_REVIEW_LOCK = _threading.Lock()   # --jobs 并行时保护 review.json 的读改写


def _video_client(project: Project) -> Client:
    """drama.json video_provider=fal 时视频走 fal 队列（profiles.video = fal 端点 ID），否则走 H3 中转。"""
    if project.get("video_provider") == "fal":
        from fal_client import FalClient
        return FalClient(project.sub("profiles")["video"], root=project.root, log_dir=project.scripts_dir)
    return _client(project)


def produce_refs(project: Project, ids: list[str] | None = None, retake: bool = False) -> list[str]:
    refs = project.load_refs()
    prof = project.sub("profiles")
    c = _client(project)
    done = []
    for rid in ids or list(refs):
        r = refs.get(rid)
        if not r:
            print(rid, "不在 refs.json，跳过")
            continue
        out = project.ref_png(rid)
        if out.exists() and not retake:
            print(rid, "SKIP exists")
            continue
        if out.exists() and retake:
            n = 2
            while (project.refs_dir / f"{rid}_old{n}.png").exists():
                n += 1
            out.rename(project.refs_dir / f"{rid}_old{n}.png")
        ref_imgs = [project.ref_png(x) for x in r.get("refs") or []]
        for p in ref_imgs:
            if not p.exists():
                raise SystemExit(f"{rid} 依赖的参考图 {p.name} 还没生成")
        seed = project.seed(rid, "ref", 1 + (2 if retake else 0))
        jid, path = c.image(r["prompt"], out, profile=r.get("profile") or prof["ref"], res=r.get("res") or prof["ref_res"],
                            seed=seed, refs=ref_imgs, aspect=r.get("aspect") or project.get("aspect"), name=rid)
        print("OK", rid, jid, path)
        done.append(rid)
    return done


def produce_frames(project: Project, ep: str, sids: list[str] | None = None, retake: bool = False) -> list[str]:
    data = project.load_shots(ep)
    prof = project.sub("profiles")
    c = _frame_client(project)
    done = []
    pd = project.prompts_dir(ep)
    pd.mkdir(parents=True, exist_ok=True)
    for sh in data.get("shots") or []:
        sid = sh["id"]
        if sids and sid not in sids:
            continue
        takes = project.takes(ep, sid, "frame")
        if takes and not retake:
            print(sid, "SKIP frame exists", takes)
            continue
        take = (takes[-1] + 1) if takes else 1
        if take > int(project.sub("budget")["max_takes"]):
            print(sid, "take 用尽", takes)
            continue
        refs = [project.ref_png(r) for r in sh.get("frame_refs") or []]
        parent = sh.get("frame_parent")   # 同机位派生：父镜通过的起始帧作 Picture 1，frame_refs 顺延（pipeline-contract §4，G40）
        if parent:
            pt = project.chosen_take(ep, parent, "frame")
            if not pt:
                print(sid, "父帧", parent, "还没有起始帧，跳过")
                continue
            refs = [project.frame_path(ep, parent, pt)] + refs
        missing = [p.name for p in refs if not p.exists()]
        if missing:
            print(sid, "缺参考图", missing, "跳过")
            continue
        out = project.frame_path(ep, sid, take)
        (pd / f"frame_{sid}.txt").write_text(sh["frame_prompt"], encoding="utf-8")
        fprof = prof["frame"] if project.get("frame_provider") == "fal" else (sh.get("frame_profile") or prof["frame"])
        jid, path = c.image(sh["frame_prompt"], out, profile=fprof, res=prof["frame_res"],
                            seed=project.seed(sid, "frame", take), refs=refs, aspect=project.get("aspect"), name=f"F_{sid}_t{take}")
        print("OK", sid, f"take{take}", jid, path)
        # 新起始帧出来后，review.json 里锁定的旧 frame_take 作废（否则重拍视频会继续用旧帧）
        with _REVIEW_LOCK:
            rv = project.load_review(ep)
            rec = (rv.get("shots") or {}).get(sid)
            if rec and rec.get("frame_take") not in (None, take):
                rec["frame_take"] = take
                project.save_review(ep, rv)
        done.append(sid)
    return done


def produce_videos(project: Project, ep: str, sids: list[str] | None = None, retake: bool = False, asr: bool = False) -> list[str]:
    data = project.load_shots(ep)
    prof = project.sub("profiles")
    budget = project.sub("budget")
    c = _video_client(project)
    done = []
    pd = project.prompts_dir(ep)
    pd.mkdir(parents=True, exist_ok=True)
    review = project.load_review(ep)
    if asr:
        from review_tool import asr_shot, choose_best  # 延迟导入：没有 ASR 环境时其余功能不受影响
    for sh in data.get("shots") or []:
        sid = sh["id"]
        if sids and sid not in sids:
            continue
        ft = project.chosen_take(ep, sid, "frame", review)
        if not ft:
            print(sid, "没有起始帧，跳过")
            continue
        frame = project.frame_path(ep, sid, ft)
        takes = project.takes(ep, sid, "video")
        if takes and not retake:
            print(sid, "SKIP video exists", takes)
            continue
        (pd / f"video_{sid}.txt").write_text(sh["video_prompt"], encoding="utf-8")
        attempts = 0
        while True:
            takes = project.takes(ep, sid, "video")
            take = (takes[-1] + 1) if takes else 1
            if take > int(budget["max_takes"]):
                print(sid, "take 用尽", takes)
                break
            out = project.video_path(ep, sid, take)
            jid, path = c.video(sh["video_prompt"], out, frame, seconds=float(sh["seconds"]),
                                profile=sh.get("video_profile") or prof["video"], res=prof["video_res"],
                                seed=project.seed(sid, "video", take), aspect=project.get("aspect"), name=f"V_{sid}_t{take}")
            print("OK", sid, f"take{take}", jid, path)
            done.append(sid)
            attempts += 1
            if not asr:
                break
            rec = asr_shot(project, ep, sh, take)
            review = project.load_review(ep)
            # ASR disagreement may be recognition error or semantic drift: never spend a new take on score alone.
            if (rec.get("speech_diff") or {}).get("status") != "exact":
                print(sid, f"take{take} 台词存在差异，待听审；不按 ASR 分数自动重拍")
            else:
                print(sid, f"take{take} 文本对齐完成，仍需画面、听感与连续性审查")
            break
        if asr:
            choose_best(project, ep, sid)
    return done


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("refs")
    r.add_argument("project")
    r.add_argument("ids", nargs="*")
    r.add_argument("--retake", action="store_true")
    for name in ("frames", "videos", "all"):
        s = sub.add_parser(name)
        s.add_argument("project")
        s.add_argument("episode")
        s.add_argument("sids", nargs="*")
        s.add_argument("--retake", action="store_true")
        s.add_argument("--asr", action="store_true")
        s.add_argument("--jobs", type=int, default=1, help="videos：并行镜头数（只对 fal 等云端队列通道；H3 本地单卡保持 1）")
    a = ap.parse_args(argv)
    pr = Project(a.project)
    try:
        if a.cmd == "refs":
            produce_refs(pr, a.ids or None, a.retake)
        elif a.cmd == "frames":
            if a.jobs > 1:
                if pr.get("frame_provider") != "fal":
                    raise SystemExit("--jobs >1 只用于 fal 等云端队列通道；本地 H3 单卡必须串行")
                from concurrent.futures import ThreadPoolExecutor
                ids = a.sids or [sh["id"] for sh in pr.load_shots(a.episode).get("shots") or []]
                with ThreadPoolExecutor(max_workers=a.jobs) as ex:
                    list(ex.map(lambda sid: produce_frames(pr, a.episode, [sid], a.retake), ids))
            else:
                produce_frames(pr, a.episode, a.sids or None, a.retake)
        elif a.cmd == "videos":
            if a.jobs > 1:
                if pr.get("video_provider") != "fal":
                    raise SystemExit("--jobs >1 只用于 fal 等云端队列通道；本地 H3 单卡必须串行")
                from concurrent.futures import ThreadPoolExecutor
                ids = a.sids or [sh["id"] for sh in pr.load_shots(a.episode).get("shots") or []]
                # 每镜一个线程：提交经账本锁逐条记账，等待与下载并行；ASR 放到全部完成后串行跑
                with ThreadPoolExecutor(max_workers=a.jobs) as ex:
                    list(ex.map(lambda sid: produce_videos(pr, a.episode, [sid], a.retake, False), ids))
                if a.asr:
                    import review_tool  # 全部生成完再串行跑 ASR（等同 review_tool.py asr）
                    review_tool.main(["asr", str(pr.root), a.episode, *ids])
            else:
                produce_videos(pr, a.episode, a.sids or None, a.retake, a.asr)
        elif a.cmd == "all":
            data = pr.load_shots(a.episode)
            used = sorted({x for sh in data.get("shots") or [] for x in sh.get("frame_refs") or []})
            produce_refs(pr, used)
            produce_frames(pr, a.episode, a.sids or None)
            if not pr.animatic_passed(a.episode):   # 阶段 G2 静帧预演没过（无文件或首行不是「结论：PASS」）不放行 H
                print(f"起始帧已齐；先跑 review_tool.py animatic {a.project} {a.episode}，看预演写 审查/{a.episode}-预演.md（首行「结论：PASS」），再跑 videos")
                return 0
            produce_videos(pr, a.episode, a.sids or None, False, a.asr)
    except Stop as e:
        print(str(e))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
