#!/usr/bin/env python3
"""镜头规格（shots.json）的机械质量门与文档渲染。

  shots_tool.py check  <项目> <EP> [--json]      跑全部门；有 error 时退出码 1
  shots_tool.py render <项目> <EP>               生成 分镜.md / 图片提示词.md / 视频提示词.md 和 脚本/prompts/<EP>/*.txt
  shots_tool.py coverage <项目> <EP>             剧本每句对白 / 每场是否有镜头承载

  shots_tool.py check-refs <项目>                 参考图门 G18–G20（身份图/底板/道具图提示词、雷同）
  shots_tool.py build  <项目> <EP>                只写了 video_body/soundscape 的镜头，拼出 H3 三段 video_prompt

门的编号 G00–G27（见 references/pipeline-contract.md §7），分 error / warn 两级；error 必须修，warn 由写作者判断后
可在 shot 里用 "waive": ["G05"] 明确豁免。每次 check 追加一行 脚本/gates.jsonl。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (Project, dialogue_lines, norm, parse_screenplay, parse_visual, speakers, speech_seconds)  # noqa: E402
import json as _json  # noqa: E402
import time as _time  # noqa: E402


def _jaccard(a: str, b: str) -> float:
    A = set(re.findall(r"[a-z]+", a.lower()))
    B = set(re.findall(r"[a-z]+", b.lower()))
    return len(A & B) / max(1, len(A | B))


def log_gates(project: Project, ep: str, findings: "Findings", scope: str) -> None:
    """每次 check 追加一行到 脚本/gates.jsonl：哪些门响了、多少次。无人值守时靠它看哪条规则最常被违反。"""
    try:
        project.scripts_dir.mkdir(parents=True, exist_ok=True)
        with open(project.scripts_dir / "gates.jsonl", "a", encoding="utf-8") as f:
            f.write(_json.dumps({"time": _time.strftime("%Y-%m-%d %H:%M:%S"), "scope": scope, "episode": ep,
                                 "errors": len(findings.errors()), "warns": len(findings.warns()),
                                 "codes": sorted({x["code"] for x in findings.items})}, ensure_ascii=False) + "\n")
    except OSError:
        pass

REQUIRED_SHOT = ("id", "scene", "title", "duty", "keyframe", "frame_prompt", "motion", "video_prompt", "seconds", "end_state")
INSERT_KINDS = {"insert", "hands", "feet", "object", "plate", "empty"}
BACKREF_RE = re.compile(r"同上|与上一镜相同|和上一镜相同|保持不变|同前|same as (?:the )?previous|as before|unchanged from|as in the previous", re.I)
BOUNDARY_KEYS = ("position", "facing", "gaze", "hands", "held", "state")
READABLE_TEXT_RE = re.compile(r"\b(reads?|reading|text says|says ['\"]|written|lettering|letters spell|caption|subtitle|sign(?:board)? (?:that )?says|headline)\b", re.I)


class Findings:
    def __init__(self):
        self.items: list[dict] = []

    def add(self, code: str, level: str, shot: str | None, msg: str):
        self.items.append({"code": code, "level": level, "shot": shot, "msg": msg})

    def errors(self):
        return [f for f in self.items if f["level"] == "error"]

    def warns(self):
        return [f for f in self.items if f["level"] == "warn"]


def _waived(shot: dict, code: str) -> bool:
    return code in (shot.get("waive") or [])


def check(project: Project, ep: str) -> Findings:
    F = Findings()
    data = project.load_shots(ep)
    refs = project.load_refs()
    shots = data.get("shots") or []
    scenes = {s["id"]: s for s in (data.get("scenes") or []) if "id" in s}
    lang = project.get("dialogue_lang")
    rates = project.sub("speech_rates")
    secs = project.sub("shot_seconds")
    one = project.get("one_person_clause")
    notext = project.get("no_text_clause")
    forbidden = [w.lower() for w in project.get("forbidden_words") or []]
    keys = project.get("video_prompt_keys") or []
    start_max = float(project.get("dialogue_start_max"))

    script_doc = None
    visual = None
    if project.script_path(ep).exists():
        script_doc = parse_screenplay(project.script_path(ep).read_text(encoding="utf-8"))
    else:
        F.add("G00", "error", None, f"缺 {project.script_path(ep).name}，镜头无法对照剧本")
    if project.visual_path(ep).exists():
        visual = parse_visual(project.visual_path(ep).read_text(encoding="utf-8"))
    script_scene_ids = {s["id"] for s in (script_doc["scenes"] if script_doc else [])}
    script_dialogue = dialogue_lines(script_doc) if script_doc else []
    script_norm = {norm(d["text"]): d for d in script_dialogue}
    cast = speakers(script_doc, visual) if script_doc else set()

    ids_seen = set()
    locks = data.get("locks") or []
    prev_by_scene_subject: dict[tuple[str, str], dict] = {}
    facings_in_scene: dict[str, dict[str, str]] = {}
    facing_by_scene: dict[tuple[str, str], str] = {}
    covered_dialogue: set[str] = set()
    covered_scenes: set[str] = set()
    planned_total = 0.0

    for sh in shots:
        sid = sh.get("id", "?")
        # G01 必填字段与 ID
        missing = [k for k in REQUIRED_SHOT if not sh.get(k)]
        if missing:
            F.add("G01", "error", sid, f"缺字段 {missing}")
        if sid in ids_seen:
            F.add("G01", "error", sid, "镜头 ID 重复")
        ids_seen.add(sid)
        if not re.match(rf"^{ep}-S\d{{2,3}}$", sid):
            F.add("G01", "error", sid, f"ID 应形如 {ep}-S01")
        scene = sh.get("scene", "")
        if script_doc and scene not in script_scene_ids:
            F.add("G01", "error", sid, f"场景 {scene} 不在剧本里")
        covered_scenes.add(scene)
        kind = sh.get("kind", "person")
        fp, vp = sh.get("frame_prompt", "") or "", sh.get("video_prompt", "") or ""
        seconds = float(sh.get("seconds") or 0)
        planned_total += seconds

        # G02 一镜一人
        if kind not in INSERT_KINDS and not sh.get("multi_person"):
            if one and one.lower() not in fp.lower():
                F.add("G02", "error" if not _waived(sh, "G02") else "warn", sid, f"起始帧提示词缺一镜一人句「{one}」")
        if sh.get("multi_person") and not sh.get("multi_person_reason"):
            F.add("G02", "error", sid, "multi_person 必须写 multi_person_reason（为什么必须两人同框）")

        # G03 参考图存在；人物镜要有身份图
        for r in sh.get("frame_refs") or []:
            if r not in refs:
                F.add("G03", "error", sid, f"参考图 {r} 不在 refs.json")
        if kind not in INSERT_KINDS and sh.get("subject") and not any(refs.get(r, {}).get("kind") == "identity" for r in sh.get("frame_refs") or []):
            if not _waived(sh, "G03"):
                F.add("G03", "warn", sid, f"人物镜没有绑定「{sh.get('subject')}」的身份图（identity ref）")
        sc = scenes.get(scene) or {}
        if sc.get("plates") and not any(r in (sc.get("plates") or []) for r in sh.get("frame_refs") or []) and kind != "plate":
            F.add("G03", "warn", sid, f"场景 {scene} 声明了底板 {sc.get('plates')}，本镜没绑任何一张")

        # G04 时长与台词容量；G05 开口时点
        if seconds < float(secs["min"]) or seconds > float(secs["max"]):
            F.add("G04", "error", sid, f"seconds={seconds} 超出 [{secs['min']}, {secs['max']}]")
        dlg = sh.get("dialogue") or []
        need = 0.0
        for i, d in enumerate(dlg):
            t = d.get("text", "")
            at = float(d.get("at", 0.5))
            est = speech_seconds(t, d.get("lang", lang), rates)
            need = max(need, at + est)
            if i == 0 and at > start_max and not sh.get("reaction_first") and not _waived(sh, "G05"):
                F.add("G05", "warn", sid, f"第一句台词 {at}s 才开口（上限 {start_max}s）；要么提前，要么写 reaction_first 并说明")
            if not d.get("speaker"):
                F.add("G04", "error", sid, "台词缺 speaker")
            elif cast and d["speaker"] not in cast:
                F.add("G15", "warn", sid, f"说话人「{d['speaker']}」不在剧本/视觉设定的人物里")
            # G09 台词逐字进视频提示词
            if t and norm(t) not in norm(vp):
                F.add("G09", "error", sid, f"台词「{t}」没有逐字出现在 video_prompt 里")
            # G10 台词来自剧本
            if script_doc and t and norm(t) not in script_norm:
                F.add("G10", "error" if not _waived(sh, "G10") else "warn", sid, f"台词「{t}」在剧本里找不到（剧本和镜头漂移）")
            covered_dialogue.add(norm(t))
        if dlg and need + 0.5 > seconds:
            F.add("G04", "error", sid, f"台词需要约 {need:.1f}s + 0.5s 收尾，seconds={seconds} 装不下")
        if kind not in INSERT_KINDS and not dlg and not sh.get("silent_reason") and not _waived(sh, "G05"):
            F.add("G05", "warn", sid, "人物镜没有台词；要么给一句，要么写 silent_reason")

        # G06 不出可读文字；G07 禁词
        if notext and notext.lower() not in fp.lower() and not _waived(sh, "G06"):
            F.add("G06", "error", sid, f"起始帧提示词缺「{notext}」")
        if READABLE_TEXT_RE.search(fp) and not sh.get("readable_text_ok"):
            F.add("G06", "warn", sid, "起始帧提示词像是在要求画面里出现可读文字；文字应走后期叠加")
        for w in forbidden:
            for label, body in (("frame_prompt", fp), ("video_prompt", vp)):
                if re.search(rf"\b{re.escape(w)}\b", body.lower()) and not re.search(rf"\bno\s+(?:\w+\s+){{0,2}}{re.escape(w)}", body.lower()):
                    F.add("G07", "error", sid, f"{label} 含禁词「{w}」")

        # G08 轴线：同一场景同一主体朝向一致
        facing = sh.get("facing")
        if facing and sh.get("subject") and kind not in INSERT_KINDS:
            key = (scene, sh["subject"])
            prev = facing_by_scene.get(key)
            if prev and prev != facing and not sh.get("axis_break"):
                F.add("G08", "error", sid, f"{sh['subject']} 在 {scene} 里朝向从 {prev} 变成 {facing}，没有 axis_break 说明")
            facing_by_scene.setdefault(key, facing)
        if kind not in INSERT_KINDS and not facing and not _waived(sh, "G08"):
            F.add("G08", "warn", sid, "人物镜没写 facing（left/right/camera），轴线无法核对")

        # G09 视频提示词结构（H3 三段）
        for k in keys:
            if k and k not in vp:
                F.add("G09", "error", sid, f"video_prompt 缺「{k}:」段")
        if dlg and "<d>" not in vp:
            F.add("G09", "error", sid, "有台词但 video_prompt 里没有 <d>…</d> 台词标记")

        # G23 连续性锁：锁面逐字进范围内的起始帧提示词（否定式不算携带）
        for lk in locks:
            scope = lk.get("shots", "all")
            if scope != "all" and sid not in (scope or []):
                continue
            phrase = (lk.get("phrase") or "").lower()
            if phrase and kind not in INSERT_KINDS and sh.get("subject") and lk.get("subject", sh.get("subject")) == sh.get("subject"):
                hit = re.search(r"(?<!no )(?<!without )" + re.escape(phrase), fp.lower())
                if not hit and not _waived(sh, "G23"):
                    F.add("G23", "error", sid, f"锁 {lk.get('id')} 的锁面「{lk.get('phrase')}」没有逐字出现在 frame_prompt 里")
        # G24 回指词：图片模型看不到上一镜
        for label in ("keyframe", "frame_prompt", "end_state", "motion"):
            if BACKREF_RE.search(sh.get(label, "") or ""):
                F.add("G24", "error", sid, f"{label} 里有「同上/与上一镜相同/same as previous」一类回指词；写成绝对事实")
        b = sh.get("boundary") or {}
        for side in ("start", "end"):
            for k, v in (b.get(side) or {}).items():
                if isinstance(v, str) and BACKREF_RE.search(v):
                    F.add("G24", "error", sid, f"boundary.{side}.{k} 用了回指词")
        # G26 边界链：同场同主体相邻镜，前一镜 end == 本镜 start（逐项字符串比对）
        if kind not in INSERT_KINDS and sh.get("subject"):
            key = (scene, sh["subject"])
            prev = prev_by_scene_subject.get(key)
            if prev and b.get("start") and (prev.get("boundary") or {}).get("end"):
                pe, cs = prev["boundary"]["end"], b["start"]
                diffs = [k for k in BOUNDARY_KEYS if k in pe and k in cs and norm(str(pe[k])) != norm(str(cs[k]))]
                if diffs and not sh.get("boundary_break") and not _waived(sh, "G26"):
                    F.add("G26", "error", sid, f"与上一镜 {prev['id']} 的边界链不接：{diffs} 前一镜终点≠本镜起点；补一镜、改边界，或写 boundary_break 说明镜外发生了什么")
            # G27 同景别同主体跳切
            if prev and prev.get("framing") and sh.get("framing") and norm(prev["framing"]) == norm(sh["framing"]) and not _waived(sh, "G27"):
                F.add("G27", "warn", sid, f"和上一镜 {prev['id']} 同主体同景别「{sh['framing']}」相邻，是跳切；换景别、角度或中间加反应/插入镜")
            prev_by_scene_subject[key] = sh
            if facing in ("left", "right"):
                facings_in_scene.setdefault(scene, {})[sh["subject"]] = facing

        # G21 说话人音色描述全剧一致（refs.json 身份图的 voice 字段）；G22 不留分支
        for d in dlg:
            spk = d.get("speaker")
            voice = next((r.get("voice") for r in refs.values() if r.get("kind") == "identity" and r.get("subject") == spk and r.get("voice")), None)
            if voice and voice.lower() not in vp.lower() and not _waived(sh, "G21"):
                F.add("G21", "warn", sid, f"「{spk}」的音色描述「{voice}」没写进 video_prompt；首帧模式下靠它保持逐镜音色一致")
        for label, body in (("frame_prompt", fp), ("video_prompt", vp)):
            plain = re.sub(r"<d>.*?</d>", "", body, flags=re.S)
            if re.search(r"\b(?:either|or else|alternatively)\b|\(or\b|\bor\b(?=[^.]*\b(?:maybe|possibly|optionally)\b)|或者|二选一|任选|可选", plain, re.I) and not sh.get("alternatives_ok"):
                F.add("G22", "warn", sid, f"{label} 里像是留了分支（or / 或者 / 可选）；提示词要定稿，不给模型二选一")

        # G12 后期叠加
        for ov in sh.get("overlay") or []:
            if ov.get("kind") not in ("text", "stamp", "panel"):
                F.add("G12", "error", sid, f"overlay.kind 只能是 text/stamp/panel：{ov}")
            if ov.get("kind") == "stamp" and ov.get("side") not in ("L", "R"):
                F.add("G12", "error", sid, "stamp 叠加必须写 side: L/R（放在说话人脑后留空的一侧）")
            if ov.get("kind") in ("text", "panel") and not ov.get("text"):
                F.add("G12", "error", sid, "text/panel 叠加缺 text")

        # G13 质量地板
        if len(sh.get("keyframe", "")) < 20:
            F.add("G13", "warn", sid, "冻结关键帧描述太短（<20 字），下游没法核对构图")
        if kind not in INSERT_KINDS and one and one.lower() in fp.lower() and re.search(r"\b(two|three|both|couple|crowd|people)\b", fp.lower()) and not sh.get("multi_person"):
            F.add("G13", "warn", sid, "起始帧提示词既写一镜一人又出现 two/both/people 等词，检查是否多人入画")
        if kind not in INSERT_KINDS and re.search(r"\bin focus\b", fp.lower()) and not _waived(sh, "G13"):
            F.add("G13", "warn", sid, "「in focus」给虚焦背景里的路人留了口子（实战里多出过人）；写 Only one person in the frame，不写 in focus")

    # G17 视频正文里不该出现人名（H3 用 Subject/Speaker 编号指代；<d> 里的台词除外）
    banned = set()
    for r in refs.values():
        if r.get("kind") == "identity" and r.get("subject"):
            banned.add(str(r["subject"]))
    if visual:
        banned |= set(visual.get("characters", []))
    for sh in shots:
        vp = sh.get("video_prompt", "") or ""
        rest = re.sub(r"<d>.*?</d>", "", vp, flags=re.S)
        for nm in banned:
            if nm and re.search(rf"(?<![A-Za-z]){re.escape(nm)}(?![A-Za-z])", rest) and not _waived(sh, "G17"):
                F.add("G17", "warn", sh.get("id"), f"video_prompt 正文出现人名「{nm}」；H3 正文用 the man / (S1) 这类指代，人名只放起始帧提示词")
                break

    # G16 剧本层：冷开场、估时、台词占比、连说
    if script_doc:
        all_lines = [ln for sc in script_doc["scenes"] for ln in sc["lines"] if ln["type"] in ("action", "dialogue")]
        head = all_lines[:3]
        if all_lines and not any(ln["type"] == "dialogue" for ln in head):
            F.add("G16", "warn", None, "冷开场：前 3 拍没有对白；爽剧要在前 3 拍内出现可见冲突或异常，主体在动")
        d_secs = sum(speech_seconds(ln["text"], lang, rates) for ln in all_lines if ln["type"] == "dialogue")
        a_secs = 2.5 * sum(1 for ln in all_lines if ln["type"] == "action")
        est = d_secs + a_secs
        target = float(project.get("target_seconds") or 0)
        if target and (est < target * 0.75 or est > target * 1.25):
            F.add("G16", "warn", None, f"剧本估时 {est:.0f}s（台词 {d_secs:.0f}s + 动作段 {a_secs:.0f}s），目标 {target:.0f}s，偏差超过 25%")
        ratio_min = float(project.get("dialogue_ratio_min", 0.35))
        if est and d_secs / est < ratio_min:
            F.add("G16", "warn", None, f"台词秒数占比 {d_secs / est:.0%} 低于 {ratio_min:.0%}；本项目要求台词要多")
        for sc in script_doc["scenes"]:
            run, prev = 0, None
            for ln in sc["lines"]:
                if ln["type"] == "dialogue":
                    run = run + 1 if ln["speaker"] == prev else 1
                    prev = ln["speaker"]
                    if run == 4:
                        F.add("G16", "warn", None, f"{sc['id']}：「{prev}」连说 4 句以上，中间要有对方反应或一个动作")
                elif ln["type"] == "action":
                    run, prev = 0, None
            if not any(ln["type"] == "action" for ln in sc["lines"]):
                F.add("G16", "warn", None, f"{sc['id']} 没有动作段，只有对白")

    # G25 正反打：同场两个人物的朝向应互补（都朝画左 = 在看同一个画外第三者）
    for sc_id, fmap in facings_in_scene.items():
        if len(fmap) >= 2 and len(set(fmap.values())) == 1:
            sc_axis = (scenes.get(sc_id) or {}).get("axis", "")
            F.add("G25", "warn", None, f"{sc_id}：{list(fmap)} 全都面朝画{'左' if list(fmap.values())[0] == 'left' else '右'}，正反打没有互补朝向（轴线声明：{sc_axis or '无'}）")

    # G11 覆盖：剧本每场有镜头；每句对白有镜头
    if script_doc:
        for sc_id in script_scene_ids - covered_scenes:
            F.add("G11", "error", None, f"剧本场景 {sc_id} 没有任何镜头")
        for d in script_dialogue:
            if norm(d["text"]) not in covered_dialogue:
                F.add("G11", "warn", None, f"剧本对白「{d['speaker']}：{d['text']}」没有镜头承载")
    # G14 时长预算
    target = float(project.get("target_seconds") or 0)
    if target and shots:
        est_final = sum(min(float(s.get("seconds") or 0) - 0.5, float(s.get("seconds") or 0) * 0.9) for s in shots)
        if est_final < target * 0.7 or est_final > target * 1.35:
            F.add("G14", "warn", None, f"按每镜约留 90% 估成片 {est_final:.0f}s，目标 {target:.0f}s，偏差超过 30%")
    if not shots:
        F.add("G01", "error", None, "shots 为空")
    return F


# ---- 参考图门（G18–G20） ---------------------------------------------------------

def check_refs(project: Project) -> Findings:
    F = Findings()
    refs = project.load_refs()
    ident = {k: v for k, v in refs.items() if v.get("kind") == "identity"}
    for rid, r in refs.items():
        p = (r.get("prompt") or "")
        low = p.lower()
        if not p:
            F.add("G18", "error", rid, "缺 prompt")
            continue
        if re.search(r"[\u3040-\u30ff\u4e00-\u9fff]", p):
            F.add("G18", "error", rid, "参考图提示词必须是英文（机器字段）")
        if "no text" not in low and "no readable text" not in low:
            F.add("G18", "error", rid, "缺 no text")
        kind = r.get("kind")
        if kind == "identity":
            if not re.search(r"\bone\b", low) or re.search(r"\b(two|three|both|couple|crowd|people)\b", low):
                F.add("G18", "error", rid, "身份图必须是一个人：写 one …，不能出现 two/both/people")
            if not any(w in low for w in ("full-body", "full body", "head-to-toe")):
                F.add("G18", "warn", rid, "身份图建议全身（full-body）")
            if not any(w in low for w in ("facing the camera", "frontal", "front view")):
                F.add("G18", "warn", rid, "身份图建议正面（facing the camera）")
            if re.search(r"\b(watch|ring|necklace|chain|bracelet|earrings?|sunglasses)\b", low) and not r.get("accessories_ok"):
                F.add("G18", "warn", rid, "身份图带饰品（表/戒指/链子），以后每镜都会跟着人物走，难以去掉；确需保留写 accessories_ok: true")
            if not r.get("subject"):
                F.add("G18", "error", rid, "身份图缺 subject（人物名，用来对账）")
        elif kind == "plate":
            if not re.search(r"\bno (?:people|person|humans?|figures?)\b", low):
                F.add("G19", "error", rid, "底板必须写 No people")
            if not any(w in low for w in ("left", "right")):
                F.add("G19", "warn", rid, "底板建议写清画左/画右各是什么（left/right），轴线才有依据")
        elif kind == "prop":
            if not re.search(r"\bno (?:hands?|fingers?|people)\b", low):
                F.add("G19", "error", rid, "道具图必须写 no hands")
            if "white background" not in low and "plain" not in low:
                F.add("G19", "warn", rid, "道具图建议白底/素底并写尺度（手持级/桌面级）")
        for dep in r.get("refs") or []:
            if dep not in refs:
                F.add("G18", "error", rid, f"依赖的参考图 {dep} 不存在")
    ids = list(ident)
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            jac = _jaccard(ident[ids[i]].get("prompt", ""), ident[ids[j]].get("prompt", ""))
            if jac >= 0.75:
                F.add("G20", "error", ids[i], f"和 {ids[j]} 的身份图提示词相似度 {jac:.0%}，观众会认错人：至少换脸型、发型、体形、服装之一")
    return F


def build_video_prompt(project: Project, sh: dict) -> str:
    """模型只写 video_body（英文动作正文，含 <d> 台词）和 soundscape，骨架由程序拼，减少结构错误。"""
    head = project.get("video_prompt_head") or "integrated_multimodal_description: [Shot 1] Single continuous take, starting exactly from the opening frame."
    body = (sh.get("video_body") or "").strip()
    sound = (sh.get("soundscape") or "").strip() or "quiet room tone"
    music = (sh.get("music") or "").strip() or "N/A"
    return f"{head} {body}\noverall_soundscape: {sound}\nnon_diegetic_music: {music}"


def build_prompts(project: Project, ep: str) -> int:
    data = project.load_shots(ep)
    n = 0
    for sh in data.get("shots") or []:
        if not sh.get("video_prompt") and sh.get("video_body"):
            sh["video_prompt"] = build_video_prompt(project, sh)
            n += 1
    if n:
        project.shots_path(ep).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return n


# ---- 渲染 ---------------------------------------------------------------------

def _facing_cn(f: str | None) -> str:
    return {"left": "面朝画左", "right": "面朝画右", "camera": "面朝镜头"}.get(f or "", f or "未写")


def render(project: Project, ep: str) -> list[Path]:
    data = project.load_shots(ep)
    refs = project.load_refs()
    shots = data.get("shots") or []
    prof = project.sub("profiles")
    review = project.load_review(ep)
    out_paths = []
    pd = project.prompts_dir(ep)
    pd.mkdir(parents=True, exist_ok=True)

    # 分镜.md
    L = [f"# {ep} 分镜", "",
         f"目标模型：{project.get('video_dialect')}；一镜一生成，keyframe 首帧模式；每镜生成秒数见各镜；成片取用区间按审片结果（审查/{ep}-review.json）。",
         f"拍法：{project.get('one_person_clause')} 每镜一人或一双手；关系和冲突靠特写与剪辑建立；字幕与后期字全部后期叠加，生成画面里不出字。", ""]
    if data.get("notes"):
        L += ["本集说明：", *[f"- {n}" for n in data["notes"]], ""]
    for sc in data.get("scenes") or []:
        L.append(f"- 场景 {sc.get('id')}：轴线 {sc.get('axis', '未写')}；底板 {', '.join(sc.get('plates') or []) or '无'}")
    L.append("")
    for sh in shots:
        sid = sh["id"]
        ft = project.chosen_take(ep, sid, "frame", review)
        fpath = project.frame_path(ep, sid, ft) if ft else None
        dl = "；".join(f"约 {d.get('at', 0.5)}s {d.get('speaker')}「{d.get('text')}」" for d in sh.get("dialogue") or []) or "无对白"
        ov = "；".join(f"{o['kind']}（{o.get('side') or o.get('text')}）" for o in sh.get("overlay") or []) or "无"
        L += [f"## SHOT-{sid} · {sh.get('title', '')}",
              f"- 场景：{sh.get('scene')}",
              f"- 来源：{'；'.join('「' + a + '」' for a in sh.get('script_anchor') or []) or '无'}",
              f"- 时长：生成 {sh.get('seconds')} 秒",
              f"- 目的：{sh.get('duty', '')}",
              f"- 景别/机位：{sh.get('framing', '')}",
              f"- 主体与朝向：{sh.get('subject') or sh.get('kind', 'insert')}，{_facing_cn(sh.get('facing'))}",
              f"- 起点（冻结关键帧）：{sh.get('keyframe', '')}",
              f"- 唯一动作：{sh.get('motion', '')}",
              f"- 终点：{sh.get('end_state', '')}",
              f"- 声音：{sh.get('sound', '')}；对白：{dl}",
              f"- 后期叠加：{ov}",
              f"- 视觉依据：{'；'.join(sh.get('visual_deps') or []) or '无'}",
              f"- 连续性：{'；'.join(sh.get('continuity') or []) or '无'}",
              f"- 起始帧：{fpath.relative_to(project.root) if fpath else '尚未生成'}",
              ""]
    p = project.ep_dir(ep) / "分镜.md"
    p.write_text("\n".join(L), encoding="utf-8")
    out_paths.append(p)

    # 图片提示词.md
    used_refs = sorted({r for sh in shots for r in sh.get("frame_refs") or []})
    L = [f"# {ep} 图片提示词", "",
         f"> 参考图（身份图/底板）在 参考图/，本集用到 {len(used_refs)} 张；起始帧正文与《分镜.md》冻结关键帧同源，都来自 shots.json。风格句写明画面里不出字。", ""]
    for rid in used_refs:
        r = refs.get(rid, {})
        png = project.ref_png(rid)
        L += [f"## {rid} · {r.get('name', rid)}",
              f"- 用途：{r.get('kind', '')}（控制：{r.get('controls', '')}；不得控制：{r.get('not_controls', '')}）",
              f"- 生成：{r.get('profile') or prof['ref']}，{r.get('res') or prof['ref_res']}",
              f"- 路径：参考图/{rid}.png（{'已生成' if png.exists() else '尚未生成'}）", "",
              "### 可复制提示词", "", f"> {r.get('prompt', '')}", ""]
        (pd / f"ref_{rid}.txt").write_text(r.get("prompt", ""), encoding="utf-8")
    for sh in shots:
        sid = sh["id"]
        ft = project.chosen_take(ep, sid, "frame", review)
        L += [f"## IMG-F-{sid} · SHOT-{sid} 起始帧",
              f"- 冻结关键帧：{sh.get('keyframe', '')}",
              f"- 参考：{', '.join(sh.get('frame_refs') or []) or '无（文生）'}",
              f"- 生成：{sh.get('frame_profile') or prof['frame']}，{prof['frame_res']}，种子 {project.seed(sid, 'frame', 1)}（take 1）",
              f"- 路径：{project.frame_path(ep, sid, ft).relative_to(project.root) if ft else '尚未生成'}", "",
              "### 可复制提示词", "", f"> {sh.get('frame_prompt', '')}", ""]
        (pd / f"frame_{sid}.txt").write_text(sh.get("frame_prompt", ""), encoding="utf-8")
    p = project.ep_dir(ep) / "图片提示词.md"
    p.write_text("\n".join(L), encoding="utf-8")
    out_paths.append(p)

    # 视频提示词.md
    L = [f"# {ep} 视频提示词", "",
         f"目标模型：{project.get('video_dialect')}（正文 {project.get('prompt_lang')}，对白 {project.get('dialogue_lang')}）；"
         f"档位 {prof['video']}，{prof['video_res']}，一镜一生成，keyframe 首帧模式。台词放在 <d>[语言] …</d> 里并写开口时点；"
         "静态外观由起始帧承担，正文不重复；任何字幕、面板都后期叠加。", ""]
    for sh in shots:
        sid = sh["id"]
        ft = project.chosen_take(ep, sid, "frame", review)
        L += [f"## MOTION-{sid} · {sh.get('title', '')}",
              f"- 分镜：SHOT-{sid}",
              f"- 时长：{sh.get('seconds')}",
              f"- 生成方式：图生视频（起始帧 {project.frame_path(ep, sid, ft).relative_to(project.root) if ft else '尚未生成'}）",
              f"- 起始帧：{sh.get('keyframe', '')}",
              f"- 状态链：{sh.get('motion', '')}",
              f"- 终点：{sh.get('end_state', '')}", "",
              "### 可复制提示词", "", *[f"> {ln}" for ln in (sh.get("video_prompt", "") or "").splitlines()], ""]
        (pd / f"video_{sid}.txt").write_text(sh.get("video_prompt", ""), encoding="utf-8")
    p = project.ep_dir(ep) / "视频提示词.md"
    p.write_text("\n".join(L), encoding="utf-8")
    out_paths.append(p)
    return out_paths


def coverage(project: Project, ep: str) -> dict:
    data = project.load_shots(ep)
    doc = parse_screenplay(project.script_path(ep).read_text(encoding="utf-8"))
    covered = {norm(d.get("text", "")) for sh in data.get("shots") or [] for d in sh.get("dialogue") or []}
    scenes_with = {sh.get("scene") for sh in data.get("shots") or []}
    rows = []
    for d in dialogue_lines(doc):
        rows.append({"scene": d["scene"], "speaker": d["speaker"], "text": d["text"], "covered": norm(d["text"]) in covered})
    return {"scenes": [{"id": s["id"], "covered": s["id"] in scenes_with} for s in doc["scenes"]], "dialogue": rows}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("check", "render", "coverage", "build"):
        s = sub.add_parser(name)
        s.add_argument("project")
        s.add_argument("episode")
        s.add_argument("--json", action="store_true")
        s.add_argument("--strict", action="store_true", help="warn 也当 error")
    cr = sub.add_parser("check-refs")
    cr.add_argument("project")
    cr.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    pr = Project(a.project)
    if a.cmd == "check-refs":
        F = check_refs(pr)
        log_gates(pr, "-", F, "refs")
        if a.json:
            print(json.dumps({"errors": F.errors(), "warns": F.warns()}, ensure_ascii=False, indent=2))
        else:
            for f in F.items:
                print(f"[{f['level']}] {f['code']} {f['shot'] or '-'}: {f['msg']}")
            print(f"{len(F.errors())} errors, {len(F.warns())} warnings")
        return 1 if F.errors() else 0
    if a.cmd == "build":
        n = build_prompts(pr, a.episode)
        print(f"built {n} video prompts")
        return 0
    if a.cmd == "check":
        build_prompts(pr, a.episode)
        F = check(pr, a.episode)
        log_gates(pr, a.episode, F, "shots")
        if a.strict:
            for f in F.items:
                f["level"] = "error"
        if a.json:
            print(json.dumps({"errors": F.errors(), "warns": F.warns()}, ensure_ascii=False, indent=2))
        else:
            for f in F.items:
                print(f"[{f['level']}] {f['code']} {f['shot'] or '-'}: {f['msg']}")
            print(f"{len(F.errors())} errors, {len(F.warns())} warnings")
        return 1 if F.errors() else 0
    if a.cmd == "render":
        for p in render(pr, a.episode):
            print("wrote", p)
        return 0
    if a.cmd == "coverage":
        cov = coverage(pr, a.episode)
        if a.json:
            print(json.dumps(cov, ensure_ascii=False, indent=2))
        else:
            for s in cov["scenes"]:
                print(f"{'OK ' if s['covered'] else 'NO '} scene {s['id']}")
            for d in cov["dialogue"]:
                print(f"{'OK ' if d['covered'] else 'NO '} {d['scene']} {d['speaker']}：{d['text']}")
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
