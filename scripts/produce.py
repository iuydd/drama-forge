#!/usr/bin/env python3
"""按 shots.json 生产：参考图 → 起始帧 → 视频（h3studio 按服务端槽位并发，fal/kling 默认逐镜）。已有产物自动跳过，中断后重跑即可。

  produce.py refs   <项目> [IMG-ID ...] [--retake]
  produce.py frames <项目> <EP> [SID ...] [--retake]
  produce.py videos <项目> <EP> [SID ...] [--retake] [--asr]
  produce.py all    <项目> <EP> [--asr]          起始帧之后预演（阶段 G2）没放行就停下，不提交视频

提交前的共用预检（frames / videos / all 都走，不满足就拒绝提交并说明怎么补）：
- 子代理（环境变量 DF_SUBAGENT=1）不提交任何生成任务；
- 该集 shots_tool.py check 的 error = 0；
- 镜头级 frame_profile / video_profile、refs.json 里的 profile / res 与 drama.json profiles 不同 → 拒绝（档位由用户定，写进 profiles 或删掉镜头级值）；
  drama.json 有 profiles 但没写 profiles_source（决策记录编号）→ warn；
- 视频：预演放行（common.Project.animatic_problems 为空：首行 PASS、输入指纹未过期、必拍表填齐）；金丝雀例外——本次只提交一镜、
  且本集别的镜都还没有视频；每个要提交的镜，所选起始帧有 review_tool.py mark --frame-take N --evidence 的目检记录且 sha 等于当前文件。

- 每个镜头的起始帧/视频都带 take 编号（F_<sid>_t1.png、V_<sid>_t1.mp4）；--retake 在已有 take 之后新开一个，种子随 take 变化。
- --asr：生成后记录逐字差异并选择待审候选；识别差异需听审，不按分数自动花费重拍。
- h3studio 同时在飞的任务不超过槽位数；STOP 文件 / DEADLINE 到点就停；token 只从 H3_STUDIO_TOKEN 读。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import Project  # noqa: E402
from h3_client import Client, Stop  # noqa: E402


def _preflight(project: Project, ep: str | None, kind: str, sids: list[str] | None = None) -> None:
    """共用提交预检（见模块说明）。不满足直接 SystemExit，错误信息写明补救命令。"""
    import os
    if os.environ.get("DF_SUBAGENT"):
        raise SystemExit("子代理（DF_SUBAGENT=1）不提交生成任务（硬约束 9）：把要生成的内容交回主会话")
    prof = project.sub("profiles")
    if any(prof.get(k) for k in ("ref", "frame", "video")) and not project.cfg.get("profiles_source"):
        print("[warn] drama.json 有 profiles 但没写 profiles_source（决策记录里用户指定档位那一行的编号，如 \"D-003\"）；"
              "档位只能由用户定（SKILL 硬约束 1b）")
    bad = []
    def _adv_missing(items) -> bool:   # G52：提交前恶意执行预演 ≥3 条（格式错误由 shots_tool check 报 error）
        return len([x for x in (items if isinstance(items, list) else []) if isinstance(x, dict) and str(x.get("worst") or "").strip()]) < 3
    if kind == "refs":
        refs_all = project.load_refs()
        todo = [rid for rid in (sids or [r for r in refs_all if not project.ref_png(r).exists()]) if rid in refs_all]
        adv = [rid for rid in todo if _adv_missing(refs_all[rid].get("adversarial_preflight"))]
        if adv:
            raise SystemExit("这些参考图没写恶意执行预演 adversarial_preflight（≥3 条 {worst, blocked_by}），不提交：" + "、".join(adv)
                             + "（video-prompts-general §2b 第五部分；写完跑 shots_tool.py check-refs <项目> 看 G52）")
        for rid, r in refs_all.items():
            if r.get("profile") and r["profile"] not in (prof.get("ref"), prof.get("frame")):
                bad.append(f"refs.json {rid}.profile={r['profile']}")
            if r.get("res") and r["res"] != prof.get("ref_res"):
                bad.append(f"refs.json {rid}.res={r['res']}")
    if ep is None:
        if bad:
            raise SystemExit("镜头级/参考图级档位与 drama.json profiles 不同，需用户授权：写进 profiles（并记 profiles_source）或删掉这些值：" + "；".join(bad))
        return
    from shots_tool import check
    errs = check(project, ep).errors()
    if errs:
        raise SystemExit(f"{ep} 的门还有 {len(errs)} 个 error（{errs[0]['code']} {errs[0].get('shot') or ''} {errs[0]['msg'][:60]}…），"
                         f"先修再提交：python3 scripts/shots_tool.py check <项目> {ep}")
    data = project.load_shots(ep)
    shots = data.get("shots") or []
    want = [sh for sh in shots if not sids or sh["id"] in sids]
    for sh in want:
        key = "frame_profile" if kind == "frames" else "video_profile"
        if sh.get(key) and sh[key] != prof.get("frame" if kind == "frames" else "video"):
            bad.append(f"{sh['id']}.{key}={sh[key]}")
    if bad:
        raise SystemExit("镜头级档位与 drama.json profiles 不同，需用户授权：写进 profiles（并记 profiles_source）或删掉镜头级值：" + "；".join(bad))
    adv = [sh["id"] for sh in want if _adv_missing(sh.get("adversarial_preflight"))]
    if adv:
        raise SystemExit("这些镜没写恶意执行预演 adversarial_preflight（≥3 条 {worst, blocked_by}，blocked_by 引当前提示词原句或「验收：…」），不提交：" + "、".join(adv)
                         + f"（video-prompts-general §2b 第五部分；写完跑 shots_tool.py check <项目> {ep} 看 G52）")
    if kind != "videos":
        return
    have = {sh["id"] for sh in shots if project.takes(ep, sh["id"], "video")}
    target = {sh["id"] for sh in want}
    canary = len(target) == 1 and have <= target
    probs = project.animatic_problems(ep)
    if probs and not canary:
        raise SystemExit(f"{ep} 阶段 G2 预演没放行，不提交视频（金丝雀只允许本集第一条视频、一次一镜）：\n- " + "\n- ".join(probs))
    review = project.load_review(ep)
    from review_quality import media_digest
    unreviewed = []
    for sh in want:
        sid = sh["id"]
        ft = project.chosen_take(ep, sid, "frame", review)
        if not ft:
            continue   # 没有起始帧的镜 produce_videos 自己会跳过
        fr = ((review.get("shots") or {}).get(sid) or {}).get("frame_review") or {}
        if fr.get("take") != ft or fr.get("sha256") != media_digest(project.frame_path(ep, sid, ft)):
            unreviewed.append(f"{sid}（F_{sid}_t{ft}）")
    if unreviewed:
        raise SystemExit("这些镜的起始帧没有目检记录，或记录之后帧文件变了，不提交视频：" + "、".join(unreviewed)
                         + f"\n看过原图后逐镜记录：python3 scripts/review_tool.py mark <项目> {ep} <SID> --frame-take N --evidence \"九项清单逐项：看到……\"")


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
        from fal_client import FalClient, upscale_config
        return FalClient(project.sub("profiles")["video"], root=project.root, log_dir=project.scripts_dir,
                         upscale=upscale_config(project.get("video_upscale")))
    if project.get("video_provider") == "kling":
        from kling_client import KlingClient
        return KlingClient(project.sub("profiles")["video"], root=project.root, log_dir=project.scripts_dir,
                           sound=project.get("kling_sound") or "off")
    return _client(project)


def _ref_client(project: Project, has_refs: bool) -> Client:
    """drama.json ref_provider=fal 时参考图走 fal：无参考 → profiles.ref（文生图端点），有参考（派生底板）→ profiles.frame（编辑端点）。"""
    if project.get("ref_provider") == "fal":
        from fal_client import FalImageClient
        prof = project.sub("profiles")
        return FalImageClient(prof["frame"] if has_refs else prof["ref"], root=project.root, log_dir=project.scripts_dir)
    return _client(project)


def produce_refs(project: Project, ids: list[str] | None = None, retake: bool = False) -> list[str]:
    _preflight(project, None, "refs", ids if (ids and retake) else [r for r in (ids or project.load_refs()) if not project.ref_png(r).exists()])
    refs = project.load_refs()
    prof = project.sub("profiles")
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
        c = _ref_client(project, bool(ref_imgs))
        rprof = (prof["frame"] if ref_imgs else prof["ref"]) if project.get("ref_provider") == "fal" else (r.get("profile") or prof["ref"])
        jid, path = c.image(r["prompt"], out, profile=rprof, res=r.get("res") or prof["ref_res"],   # 与 profiles 不同的值已被 _preflight 拒绝
                            seed=seed, refs=ref_imgs, aspect=r.get("aspect") or project.get("aspect"), name=rid)
        print("OK", rid, jid, path)
        done.append(rid)
    return done


def produce_frames(project: Project, ep: str, sids: list[str] | None = None, retake: bool = False) -> list[str]:
    _preflight(project, ep, "frames", sids)
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
    _preflight(project, ep, "videos", sids)
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
            extra = {}
            if project.get("video_provider") == "kling":
                # 可灵原生音频逐镜开关：镜头写 kling_sound 就用它；否则有在镜台词（不含 vo:true 的画外/心声）开，没有关
                spoken = [d for d in sh.get("dialogue") or [] if not d.get("vo")]
                extra["sound"] = sh.get("kling_sound") or ("on" if spoken else "off")
            jid, path = c.video(sh["video_prompt"], out, frame, seconds=float(sh["seconds"]), **extra,
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


def _jobs(project: Project, kind: str, requested: int | None) -> int:
    """并发镜数。h3studio（{kind}_provider 没写）：默认用服务端槽位数 capacity.slots_total，--jobs 只能调小；
    fal / kling：默认 1，--jobs N 要用户单独授权（SKILL 硬约束 2）。"""
    if project.get(f"{kind}_provider") in ("fal", "kling"):
        return max(1, requested or 1)
    slots = _client(project).slots()
    return max(1, min(requested or slots, slots))


def _parallel(jobs: int, first: list[str], later: list[str], fn) -> None:
    """先并发跑 first，全部完成再并发跑 later（派生图要等母图）。某镜出错：已在飞的跑完，再把第一个错误抛出。"""
    from concurrent.futures import ThreadPoolExecutor
    for batch in (first, later):
        if not batch:
            continue
        with ThreadPoolExecutor(max_workers=jobs) as ex:
            futs = [ex.submit(fn, x) for x in batch]
        errs = [f.exception() for f in futs if f.exception()]
        if errs:
            raise errs[0]


def _refs_parallel(pr: Project, ids: list[str] | None, retake: bool, jobs: int) -> None:
    refs = pr.load_refs()
    ids = ids or list(refs)
    if jobs <= 1:
        produce_refs(pr, ids, retake)
        return
    todo = [r for r in ids if r in refs and (retake or not pr.ref_png(r).exists())]
    _preflight(pr, None, "refs", todo)
    later = [r for r in todo if set(refs[r].get("refs") or []) & set(todo)]
    _parallel(jobs, [r for r in todo if r not in later], later, lambda r: produce_refs(pr, [r], retake))


def _frames_parallel(pr: Project, ep: str, sids: list[str] | None, retake: bool, jobs: int) -> None:
    if jobs <= 1:
        produce_frames(pr, ep, sids, retake)
        return
    shots = [sh for sh in pr.load_shots(ep).get("shots") or [] if not sids or sh["id"] in sids]
    ids = [sh["id"] for sh in shots]
    _preflight(pr, ep, "frames", ids)
    later = [sh["id"] for sh in shots if sh.get("frame_parent") in ids]   # 同机位派生镜等父镜出完
    _parallel(jobs, [x for x in ids if x not in later], later, lambda sid: produce_frames(pr, ep, [sid], retake))


def _videos_parallel(pr: Project, ep: str, sids: list[str] | None, retake: bool, asr: bool, jobs: int) -> None:
    if jobs <= 1:
        produce_videos(pr, ep, sids, retake, asr)
        return
    ids = sids or [sh["id"] for sh in pr.load_shots(ep).get("shots") or []]
    _preflight(pr, ep, "videos", ids)   # 整批预检（金丝雀按整批判断，不按单线程判断）
    # 每镜一个线程：提交经账本锁逐条记账，等待与下载并行；ASR 放到全部完成后串行跑
    _parallel(jobs, ids, [], lambda sid: produce_videos(pr, ep, [sid], retake, False))
    if asr:
        import review_tool  # 全部生成完再串行跑 ASR（等同 review_tool.py asr）
        review_tool.main(["asr", str(pr.root), ep, *ids])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    jobs_help = "并发镜数：h3studio 默认等于服务端槽位数（/api/status capacity.slots_total），只能调小；fal/kling 默认 1，大于 1 要用户授权"
    r = sub.add_parser("refs")
    r.add_argument("project")
    r.add_argument("ids", nargs="*")
    r.add_argument("--retake", action="store_true")
    r.add_argument("--jobs", type=int, default=None, help=jobs_help)
    for name in ("frames", "videos", "all"):
        s = sub.add_parser(name)
        s.add_argument("project")
        s.add_argument("episode")
        s.add_argument("sids", nargs="*")
        s.add_argument("--retake", action="store_true")
        s.add_argument("--asr", action="store_true")
        s.add_argument("--jobs", type=int, default=None, help=jobs_help)
    a = ap.parse_args(argv)
    pr = Project(a.project)
    try:
        if a.cmd == "refs":
            _refs_parallel(pr, a.ids or None, a.retake, _jobs(pr, "ref", a.jobs))
        elif a.cmd == "frames":
            _frames_parallel(pr, a.episode, a.sids or None, a.retake, _jobs(pr, "frame", a.jobs))
        elif a.cmd == "videos":
            _videos_parallel(pr, a.episode, a.sids or None, a.retake, a.asr, _jobs(pr, "video", a.jobs))
        elif a.cmd == "all":
            data = pr.load_shots(a.episode)
            used = sorted({x for sh in data.get("shots") or [] for x in sh.get("frame_refs") or []})
            _refs_parallel(pr, used, False, _jobs(pr, "ref", a.jobs))
            _frames_parallel(pr, a.episode, a.sids or None, False, _jobs(pr, "frame", a.jobs))
            probs = pr.animatic_problems(a.episode)
            if probs:   # 阶段 G2 静帧预演没放行（首行、指纹、必拍表任一项不符）不提交视频
                print(f"起始帧已齐；先逐张目检起始帧（review_tool.py mark --frame-take N --evidence …），再跑 review_tool.py animatic {a.project} {a.episode}，"
                      f"看预演写 审查/{a.episode}-预演.md，放行后再跑 videos。未放行原因：\n- " + "\n- ".join(probs))
                return 0
            produce_videos(pr, a.episode, a.sids or None, False, a.asr)
    except Stop as e:
        print(str(e))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
