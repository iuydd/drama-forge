#!/usr/bin/env python3
"""镜头规格（shots.json）的机械质量门与文档渲染。

  shots_tool.py check  <项目> <EP> [--json]      跑全部门；有 error 时退出码 1
  shots_tool.py render <项目> <EP>               生成 分镜.md / 图片提示词.md / 视频提示词.md 和 脚本/prompts/<EP>/*.txt
  shots_tool.py coverage <项目> <EP>             剧本每句对白 / 每场是否有镜头承载

  shots_tool.py check-refs <项目>                 参考图门 G18–G20、G34（身份图/底板/道具图提示词、雷同、尺度锚点；头肩图 -FACE 免全身与身高、同人不比雷同）
  shots_tool.py build  <项目> <EP>                只写了 video_body/soundscape 的镜头，拼出 H3 三段 video_prompt

门的编号 G00–G53（见 references/pipeline-contract.md §7），分 error / warn 两级；error 必须修、永不豁免。warn 由写作者判断后
可在 shot（G49 可在 scene）里豁免，只认完整写法 "waive": [{"gate": "G05", "reason": "≥8 字、引本镜事实", "decision": "D-003"}]；
旧写法 "waive": ["G05"]、缺理由或缺决策记录编号的豁免不生效（G51 提示）。每次 check 追加一行 脚本/gates.jsonl（含生效的阈值与豁免）。
G50 drama.json 门阈值比内置默认宽松（error）；G52 恶意执行预演 adversarial_preflight；G53 画内人数与对话对象（11c）。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (DEFAULTS, Project, dialogue_lines, norm, parse_screenplay, parse_visual, speakers, speech_seconds)  # noqa: E402
from difflib import SequenceMatcher  # noqa: E402
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
                                 "codes": sorted({x["code"] for x in findings.items}),
                                 "limits": getattr(findings, "limits", None), "waived": getattr(findings, "waived", None)},
                                ensure_ascii=False) + "\n")
    except OSError:
        pass

REQUIRED_SHOT = ("id", "scene", "title", "duty", "keyframe", "frame_prompt", "motion", "video_prompt", "seconds", "end_state")
INSERT_KINDS = {"insert", "hands", "feet", "object", "plate", "empty"}
STYLE_PRESETS = ("live_modern", "live_period", "live_xianxia", "anime_cel", "guoman_3d", "manhwa", "cg_realistic")  # references/styles.md
# G34 尺度锚点：人物与现实参照物的关系、厘米身高、相对身高
SCALE_RE = re.compile(r"\b(?:reach(?:es|ing)?|comes? up to|level with|up to (?:his|her|their))\b[^.]{0,40}\b(?:waist|hips?|chest|knees?|shoulders?|chin|thighs?|ankles?|eyes?|head)\b"
                      r"|\b\d+(?:\.\d+)?\s*(?:cm|centimet(?:re|er)s?|m|met(?:re|er)s?)\b(?:\s+(?:tall|high|wide|long|deep))?"
                      r"|\b(?:a|half a|about a) head (?:taller|shorter)\b|\b(?:taller|shorter) than\b|\b(?:waist|knee|ankle|chest|shoulder|hip|thigh)[- ](?:high|height|level)\b"
                      r"|\bstandard (?:door|doorway|handrail|railing|desk|step)s?\b", re.I)
SCALE_FRAMING_RE = re.compile(r"中景|全景|全身|远景|双人|过肩|wide|full[- ]body|medium shot(?! close)", re.I)
ACTION_WORDS_RE = re.compile(r"撞|推(?![镜近进])|冲(?!过的)|摔|抢|让开|让一步|让步|横跨|躲开|闪开|扑|砸|踢|夺|甩|charge|shove|push(?!-?in)|lunge|slam|grab", re.I)
USE_PLAN_RE = re.compile(r"(?:取用|只留|留)约?\s*([0-9]+(?:\.[0-9]+)?)\s*(?:s|秒)")
BACKREF_RE = re.compile(r"同上|与上一镜相同|和上一镜相同|保持不变|同前|same as (?:the )?previous|as before|unchanged from|as in the previous", re.I)
BOUNDARY_KEYS = ("position", "facing", "gaze", "hands", "held", "state")
# G36 画风漂移诱因词：动漫类起始帧不写摄影/渲染词（styles.md §1、storyboard-keyframes §6b 第 8 项）
ANIME_PRESETS = ("anime_cel", "manhwa")
LIVE_LOOK_PRESETS = ("live_modern", "live_period", "live_xianxia", "cg_realistic")
ANIME_DRIFT_RE = re.compile(r"\b\d{2,3}\s?mm\b|\bbokeh\b|cinematic lighting|\bvolumetric\b|\b[48]k\b|photo-?realistic|\bphotograph(?:ic|y)?\b|film grain|depth of field", re.I)
GUOMAN_DRIFT_RE = re.compile(r"photo-?realistic|\bphotograph(?:ic|y)?\b|film grain", re.I)
LIVE_HEAD_RE = re.compile(r"realistic human|\bhandheld\b", re.I)
HEAD_FX_RE = re.compile(r"motivated camera|\bhandheld\b|\bparticles?\b|\bmist\b|\bvolumetric\b", re.I)
NEG_BEFORE_RE = re.compile(r"\b(?:no|not|never|without|nor)\s+(?:[\w-]+\s+){0,2}$", re.I)
# G37 单句长度（screenplay §4"短"）：可发声字数；en 按词
LINE_MAX_DEFAULT = {"zh": 15, "ja": 20, "en": 10}
FACE_SUFFIX = "-FACE"   # 头肩身份图 IMG-<NAME>-FACE（visual-assets §3）
CLOSE_FRAMING_RE = re.compile(r"中近景|近景|特写|close-?up|medium close", re.I)
# G43 视线：说话人看着对手（正反打时视线方向与对手的画面位置一致）
GAZE_DIRS = ("left", "right", "camera", "down", "up")
GAZE_TEXT_RE = re.compile(r"\b(?:eyes?|gaze|gazes|gazing|look(?:s|ing)?|stares?|staring|glanc\w*|watch(?:es|ing)?)\b[^.;]{0,70}?\bscreen[- ]?(left|right)\b", re.I)
CAMERA_LOOK_RE = re.compile(r"\b(?:looks?|looking|stares?|staring|eyes?|gazes?)\b[^.;]{0,30}?\b(?:into|at|toward|towards)\s+(?:the\s+)?(?:camera|lens|viewer)\b|\bbreaks? the fourth wall\b", re.I)
NEG_WIDE_RE = re.compile(r"\b(?:no|not|never|without|nor|nobody|no one|none|doesn't|does not|don't|do not|never)\b[^.;]{0,25}$", re.I)
# G32 事件起因：登场、摔落、冲突爆发、受伤、闯入这类事件要交代起因（挂 requires_setup）
EVENT_RE = re.compile(r"登场|出场|入画|闯入|闯进|冲进|破门|摔|掉落|跌落|跌倒|倒地|爆发|受伤|流血|起火|着火|爆炸|灯灭|停电|打碎|碎裂|撞|打翻|泼")
# G44 台词语种与读音
LANG_TAGS = {"ja": ("japanese",), "zh": ("chinese", "mandarin", "cantonese"), "en": ("english",), "ko": ("korean",)}
KANA_RE = re.compile(r"[\u3040-\u30ff]")
HAN_RE = re.compile(r"[\u4e00-\u9fff]")
READABLE_TEXT_RE = re.compile(r"\b(reads?|reading|text says|says ['\"]|written|lettering|letters spell|caption|subtitle|sign(?:board)? (?:that )?says|headline)\b", re.I)
# G46/G47 必拍事实 must_show（storyboard-keyframes §2e）
MUST_SHOW_KINDS = ("count", "action", "state", "loss", "identity")
NUMBER_RE = re.compile(r"\d|\b(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|dozen|single|pair)\b", re.I)
# G48/G49 默认阈值；drama.json 的 gate_limits 可覆盖（screenplay §5b3、storyboard-keyframes §8c）
GATE_LIMITS_DEFAULT = {"ability_explain_shots": 2, "ability_explain_seconds": 12.0, "recap_window": 30.0,
                       "recap_explain_shots": 1, "talk_only_ratio": 0.5, "talk_only_min_shots": 3}
# G49 承接对方行为、改变局面的可见动作或反应（motion 里出现任一即不算"只说不做"）
REACT_RE = re.compile(r"接过|接住|夺|抢|推|拽|拉住|拉开|按住|按下|抓|攥|握住|松开|递|塞给|扔|摔|砸|踢|拍|指向|指着|举起|拿起|放下|放回|合上|打开|掀|撕|起身|站起|坐下|后退|退后|上前|逼近|凑近|转身|侧身|别过|回头|躲|挡|拦|扶|一摊|摊手|抬手|挥|点头|摇头|低头|僵|愣|笑容.{0,2}(?:停|收|凝|僵)|收起笑|变脸|皱眉|咬牙|瞪|避开|打断|鞠躬|跪|冲|扑|撞|让开"
                      r"|\b(?:grab|push|shove|pull|hand(?:s|ed)? over|slam|point|stand(?:s)? up|step(?:s)? (?:back|forward)|turn(?:s)? away|nod|shake(?:s)? (?:his|her) head|freez|flinch|recoil|close(?:s)? the|open(?:s)? the)", re.I)


# G49 弱动作：只写这些不算「承接对方、改变局面」（关键词堆砌防护）
WEAK_ACT_RE = re.compile(r"点头|摇头|低头|抬头|看了?一眼|看向|看着|\bnods?\b|\bnodding\b|\blooks?\b(?: at| toward| up| down)?|\bglances?\b", re.I)


def scene_state_issues(shots: list[dict]) -> list[dict]:
    states = {}
    issues = []
    def flatten(value, prefix=""):
        for key, item in value.items():
            path = f"{prefix}/{key}"
            if isinstance(item, dict):
                yield from flatten(item, path)
            else:
                yield path, item
    for shot in shots:
        state = states.setdefault(shot.get("scene"), {})
        block = shot.get("scene_state") or {}
        for path, value in flatten(block.get("start") or {}):
            if path in state and state[path] != value:
                issues.append({"shot": shot["id"], "message": f"场景事实 {path} 从 {state[path]!r} 跳到 {value!r}；核对中间已发生的状态变化或明确时空跳转"})
            state[path] = value
        state.update(dict(flatten(block.get("end") or {})))
    return issues


HARD_ERRORS = {"G55", "G56", "G00", "G01", "G04", "G06", "G07", "G09", "G10", "G11", "G12", "G20", "G40", "G41", "G46", "G50"}


class Findings:
    def __init__(self):
        self.items: list[dict] = []
        self.limits: dict | None = None
        self.waived: list | None = None

    def add(self, code: str, level: str, shot: str | None, msg: str):
        # 2026-09-27 大改：只有防事故的门拦截（文件/字段/ID、秒数装得下台词、画面不出字、禁词、台词逐字、
        # 剧本每场有镜、叠加类型、两人长得太像、剪辑顺序、必拍事实格式、阈值只能收紧）；其余降为提示。
        if level == "error" and code not in HARD_ERRORS:
            level = "warn"
        self.items.append({"code": code, "level": level, "shot": shot, "msg": msg})

    def errors(self):
        return [f for f in self.items if f["level"] == "error"]

    def warns(self):
        return [f for f in self.items if f["level"] == "warn"]


WAIVE_REASON_MIN = 8
DECISION_RE = re.compile(r"\bD-\d+\b")
# 这些门的 error 以前能被 waive 降级或抹掉；现在 error 门一律不认 waive（G51 提示旧豁免已失效）
FORMERLY_WAIVED_ERRORS = ("G02", "G06", "G10", "G23", "G26")
# 只有这些 warn 门认 waive；其余门号写进 waive 一律不生效并报 G51
WAIVABLE_GATES = {"G03", "G05", "G08", "G13", "G17", "G21", "G27", "G29", "G30", "G31", "G32", "G34", "G35",
                  "G36", "G38", "G40", "G42", "G43", "G44", "G45", "G47", "G48", "G49", "G54"}
DECISION_ROW_RE = re.compile(r"^\|\s*(D-\d+)\s*\|", re.M)   # 决策记录表里真实的一行（模板占位【D-001】不算）


def _waive_entry(shot: dict, code: str) -> dict | None:
    for w in shot.get("waive") or []:
        if isinstance(w, dict) and w.get("gate") == code:
            return w
    return None


def _waived(shot: dict, code: str) -> bool:
    """只认 waive_findings 核验过的豁免（_ok）：warn 门、理由 ≥8 字、decision 在决策记录里真有这一行。"""
    w = _waive_entry(shot, code)
    return bool(w and w.get("_ok"))


def _people_count(fp: str, one: str) -> int | None:
    """起始帧提示词里写定的画内人数：单人固定句 → 1；exactly N people/figures/persons → N；都没有 → None。"""
    low = fp.lower()
    if one and one.lower() in low or "only one person in the frame" in low:
        return 1
    m = re.search(r"\bexactly\s+(\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s+(?:people|persons?|figures?|characters?|men|women|individuals|humans?)\b", low)
    if not m:
        return None
    w = m.group(1)
    return int(w) if w.isdigit() else _EN_NUM.index(w)


_CN_DIGIT = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
_EN_NUM = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve",
           "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen", "twenty"]


def _fact_numbers(fact: str) -> list[int]:
    """必拍事实里写到的数量：阿拉伯数字，或后面跟量词的中文数字（十件、五份），去重保序。"""
    out: list[int] = []
    for m in re.finditer(r"\d+|[零一二两三四五六七八九十]+(?=\s*[件个份张只把枚块人位名条根本支盒箱袋颗瓶杯次道])", fact):
        t = m.group(0)
        if t.isdigit():
            n = int(t)
        elif "十" in t:
            a, _, b = t.partition("十")
            n = (_CN_DIGIT.get(a, 1) if a else 1) * 10 + (_CN_DIGIT.get(b, 0) if b else 0)
        elif len(t) == 1:
            n = _CN_DIGIT[t]
        else:
            continue
        if n not in out:
            out.append(n)
    return out


def _prompt_has_number(prompt: str, n: int) -> bool:
    if re.search(rf"(?<!\d){n}(?!\d)", prompt):
        return True
    return n < len(_EN_NUM) and re.search(rf"\b{_EN_NUM[n]}\b", prompt, re.I) is not None


def _planned_use(sh: dict) -> float:
    """计划取用秒数：motion/duty/continuity 里写的「取用约 Xs」取最小值，没写按整条 seconds（与 G42 同口径）。"""
    txt = " ".join([str(sh.get("motion") or ""), str(sh.get("duty") or "")] + [str(x) for x in sh.get("continuity") or []])
    vals = [float(x) for x in USE_PLAN_RE.findall(txt)]
    return min(vals) if vals else float(sh.get("seconds") or 0)


# G50：门阈值不许调松（SKILL 防钻空子总则第 9 条）。方向：+1 = 数值越大越宽松，-1 = 越小越宽松
LOOSER = {"gate_limits": {"ability_explain_shots": 1, "ability_explain_seconds": 1, "recap_window": -1, "recap_explain_shots": 1,
                          "talk_only_ratio": 1, "talk_only_min_shots": 1},
          "pace": {"dialogue_min": -1, "dialogue_tail": -1, "reaction_min": -1, "insert_min": -1, "scene_avg_min": -1}}
FINAL_ASR_MIN = 0.8


def config_limits(project: Project, F: "Findings | None" = None) -> dict:
    """实际生效的阈值：drama.json 只能收紧；比内置默认宽松的值不生效（用默认）并报 G50 error。"""
    out = {}
    for sec, dirs in LOOSER.items():
        base = GATE_LIMITS_DEFAULT if sec == "gate_limits" else DEFAULTS["pace"]
        user = project.cfg.get(sec) or {}
        eff = dict(base)
        for k, v in user.items():
            if k not in dirs or not isinstance(v, (int, float)) or isinstance(v, bool):
                eff[k] = v
                continue
            if (v - float(base[k])) * dirs[k] > 1e-9:
                if F is not None:
                    F.add("G50", "error", None, f"drama.json {sec}.{k}={v} 比内置默认 {base[k]} 宽松；门阈值只能收紧不能调松（改回默认或删掉这一项）")
            else:
                eff[k] = v
        out[sec] = eff
    fq = (project.cfg.get("final_qa") or {}).get("asr_min")
    if isinstance(fq, (int, float)) and fq < FINAL_ASR_MIN and F is not None:
        F.add("G50", "error", None, f"drama.json final_qa.asr_min={fq} 低于内置下限 {FINAL_ASR_MIN}；终验按 {FINAL_ASR_MIN} 执行，删掉这一项")
    ap = (project.cfg.get("budget") or {}).get("asr_pass")
    if isinstance(ap, (int, float)) and ap < DEFAULTS["budget"]["asr_pass"] and F is not None:
        F.add("G50", "error", None, f"drama.json budget.asr_pass={ap} 低于内置 {DEFAULTS['budget']['asr_pass']}；改回默认")
    for lang_, cap in (project.cfg.get("line_max") or {}).items():
        if lang_ in LINE_MAX_DEFAULT and isinstance(cap, (int, float)) and cap > LINE_MAX_DEFAULT[lang_] and F is not None:
            F.add("G50", "error", None, f"drama.json line_max.{lang_}={cap} 比内置 {LINE_MAX_DEFAULT[lang_]} 宽松；单句上限只能收紧")
    for key in ("one_person_clause", "no_text_clause"):
        if key in project.cfg and not str(project.cfg.get(key) or "").strip() and F is not None:
            F.add("G50", "warn", None, f"drama.json {key} 是空的：门照样按内置默认句「{DEFAULTS[key]}」查，删掉这一项或写回默认句")
    return out


def waive_findings(F: "Findings", shots: list[dict], scenes: list[dict], project: Project) -> None:
    """G51：豁免写法。只认 {gate, reason, decision}；decision 要在 项目开发/决策记录.md 里查得到。"""
    rec_p = project.root / "项目开发" / "决策记录.md"
    rec_text = rec_p.read_text(encoding="utf-8") if rec_p.exists() else ""
    rec_ids = set(DECISION_ROW_RE.findall(rec_text))
    waived = []
    for owner in list(shots) + list(scenes):
        oid = owner.get("id")
        for w in owner.get("waive") or []:
            if isinstance(w, str):
                F.add("G51", "warn", oid, f"waive「{w}」是旧写法，不生效；warn 门豁免写成 {{\"gate\": \"{w}\", \"reason\": \"引本镜事实的理由\", \"decision\": \"D-xxx\"}}"
                      + ("；这是 error 门，任何写法都不能豁免" if w in FORMERLY_WAIVED_ERRORS else ""))
                continue
            if not isinstance(w, dict) or not w.get("gate"):
                F.add("G51", "warn", oid, f"waive 条目格式不对：{w}")
                continue
            gate, reason, dec = w.get("gate"), str(w.get("reason") or "").strip(), str(w.get("decision") or "")
            w.pop("_ok", None)
            if gate in FORMERLY_WAIVED_ERRORS or gate not in WAIVABLE_GATES:
                F.add("G51", "warn", oid, f"waive {gate} 无效：只有 warn 门能豁免（error 门永不豁免）")
            elif len(reason) < WAIVE_REASON_MIN or not DECISION_RE.search(dec):
                F.add("G51", "warn", oid, f"waive {gate} 缺理由（≥{WAIVE_REASON_MIN} 字）或决策记录编号（D-xxx），不生效")
            else:
                if DECISION_RE.search(dec).group(0) not in rec_ids:
                    F.add("G51", "warn", oid, f"waive {gate} 引的 {dec} 在 项目开发/决策记录.md 的表里没有这一行，不生效")
                    continue
                w["_ok"] = True
                waived.append([oid, gate, reason, dec])
    F.waived = waived


# G54 提示词漏洞机械检查：每条对应 references/4-分镜与视频提示词.md 的编号；只报 warn（L14 头句 / L15 封口句是 error），逐条改或按总则 7 豁免
_LR_RE = re.compile(r"\b(left|right)\b", re.I)
_LR_OK_RE = re.compile(r"(screen[- ]|\b(?:has|had|have|just|already|was|were)\s+)$", re.I)
_LR_POSS_RE = re.compile(r"(?:\b(?:his|her|their|its|my)|\w's)\s+(?:[a-z-]+\s+)?$", re.I)
_LR_BODY_RE = re.compile(r"\s+(?:[a-z-]+\s+)?(?:hand|arm|foot|leg|shoulder|cheek|eye|ear|knee|hip|wrist|side of|palm|thumb|elbow|ankle|temple|fist|fingers?|hands|arms|feet|legs|shoulders|cheeks|eyes|ears|knees|hips|eyebrows?|brows?|forearms?|sleeves?|pockets?|cuffs?|collar|lapel|jaw|chin|heels?|toes?|calf|thigh|gloves?|shoes?|boots?|breast|earlobe|nostril|ribs?|flank)\b", re.I)
_MOVE_RE = re.compile(r"\b(skid\w*|stumbl\w*|slip(?:s|ped|ping)?|toppl\w*|lung(?:e|es|ing)|(?:she|he|they|body|feet|shoe|foot)\s+(?:\w+\s+)?slid(?:e|es|ing)?)\b", re.I)
_QTY_RE = re.compile(r"\b(\d+(?:\.\d+)?|half|one|two|three|four|five|a few|a)[\s-]*(?:a\s+)?(cm|centimet\w*|met(?:re|er)s?|m|tiles?|steps?|strides?|paces?|inch\w*|body lengths?|arm'?s? lengths?|hand'?s? width)\b|\b\d+(?:\.\d+)?\s*(?:feet|foot)\b", re.I)
_PHYS_RE = re.compile(r"\b(fall(?:s|ing)?\s+(?:backward|forward|down|over|off|flat|hard)|fell\b|slip(?:s|ped)\b(?!\s+(?:out|in|into|through|away|past))|skid\w*|trip(?:s|ped)\b|collaps\w*|toppl\w*|knock\w*\s+(?:over|down)|(?<!mist )(?<!smoke )(?<!light )(?<!fog )spill(?:s|ed|ing)?\b|crash(?:es|ed)?\s+(?:into|onto|down))", re.I)
# L18：hard/snap/whip 多义（hard floor、snaps his fingers、whip-pan），不再算速度证据
_SPEED_RE = re.compile(r"\b(fast|sudden\w*|abrupt\w*|instant\w*|fraction of a second|less than|violent\w*|at once|in under|within \d|at full speed|quickly|rapid\w*|in one motion)\b", re.I)
_IMPACT_RE = re.compile(r"\b(land\w*|hit\w*|smash\w*|slam\w*|thud\w*|bounc\w*|splash\w*|crash\w*|onto)\b", re.I)
_EXIT_RE = re.compile(r"\b(out of (?:the )?frame|leav\w* the frame|exit\w* the frame|out of shot)\b", re.I)
_WINDOW_RE = re.compile(r"(?:^|[.;]\s+)(?:At|From|Between|By)\s+(?:about\s+)?\d+(?:\.\d+)?\s*(?:s\b|sec)", re.I)
_SHAKE_RE = re.compile(r"\bhandheld\b|\bsway\w*|\bshak\w*", re.I)
_VAGUE_RE = re.compile(r"\b(a little|briefly|a moment|gently|somewhat|a bit)\b", re.I)
_KEEP_VAGUE_RE = re.compile(r"\bkeep\b[^.]*\bexactly\b|\b(?:scene|room|everything|background|the rest)\s+(?:stays?|remains?)\s+exactly\b", re.I)
_FRAME_MOTION_RE = re.compile(r"\bno (?:pan|tilt|zoom|cut)s?\b|\bcamera (?:moves|pushes|pans)\b|\bthen\b|\bslowly\b", re.I)
_COLLECTIVE_RE = re.compile(r"(?<!\bno )\b(everyone|everything else|the rest|other elements|all other)\b", re.I)
_INNER_RE = re.compile(r"\b(is being|has been|because|in front of (?:him|her))\b", re.I)


def _sents(text: str) -> list[str]:
    return [x for x in re.split(r"(?<=[.;!?])\s+", text or "") if x.strip()]


def _neg_hit(rx, text: str) -> list[str]:
    return [m.group(0) for m in rx.finditer(text) if not NEG_BEFORE_RE.search(text[max(0, m.start() - 30):m.start()])]


def lr_findings(F: "Findings", sid: str, label: str, text: str) -> None:
    """L01/L20：裸 left/right；his/her left 只在后接身体部位时豁免，to/on his left 这种人物坐标照样报。"""
    body = re.sub(r"<d>.*?</d>", "", text or "", flags=re.S).split("overall_soundscape:")[0]
    bad = []
    for m in _LR_RE.finditer(body):
        pre, post = body[max(0, m.start() - 24):m.start()], body[m.end():m.end() + 30]
        if _LR_OK_RE.search(pre) or re.match(r"\s*(?:(?:edge|side|third|half|corner)\s+)?of (?:the )?(?:frame|screen|image|cent(?:re|er))|\s+edge\b", post, re.I):
            continue
        if _LR_POSS_RE.search(pre) and _LR_BODY_RE.match(post) and not re.search(r"\b(?:to|on|toward|towards)\s+(?:his|her|their|its|my)\s+(?:[a-z-]+\s+)?$", pre, re.I):
            continue
        bad.append(m.group(1).lower())
    if bad:
        pers = re.search(r"\b(?:to|on)\s+(?:his|her|their)\s+(?:left|right)\b", body, re.I)
        F.add("G54", "warn", sid, f"L01 {label} 方向写了裸 {sorted(set(bad))}{'（含人物坐标「' + pers.group(0) + '」，L20）' if pers else ''}：人物对着镜头时左右会读反，改用画面里的实物做参照（朝门、背对洗手台）；"
              "非写不可写 screen-left 并在同一句写人物朝向；his/her left 只用于身体部位（her left hand）")


def loophole_findings(F: "Findings", sid: str, vp: str, seconds, *, head: str = "", sh: dict | None = None) -> None:
    """G54：把攻防里反复出现、能用规则查的漏洞在分镜门里查掉（L01–L06、L14、L16–L20、L23、L24、L28，见 references/4-分镜与视频提示词.md）。"""
    sh = sh or {}
    raw = vp or ""
    if head:
        raw = raw.replace(head, " ")
    text = re.sub(r"<d>.*?</d>", "", raw, flags=re.S)
    body = text.split("overall_soundscape:")[0]
    if not body.strip():
        return
    sents = _sents(body)
    lr_findings(F, sid, "video_prompt", body)
    low = body.lower()
    if re.search(r"locked|static shot|tripod|holds a static", low):
        miss = [w for w in ("pan", "tilt", "zoom", "cut")
                if not re.search(rf"\bno (?:[a-z-]+s?(?:,\s*|\s+(?:or|and|nor)\s+)(?:no\s+)?)*{w}s?\b", low)]
        if miss:
            F.add("G54", "warn", sid, f"L02 写了锁机位但没封住 {miss}：锁定写全 no pan, no tilt, no shake, no reframing, no zoom, no cuts（同一句逗号串起来），模型会借机摇镜代替人物动作")
    elif not any(re.match(r"(?:\[Shot \d+\]\s*)?(?:The camera|Locked|Static)\b", x.strip(), re.I) or re.search(r"\bcamera\b", x, re.I) for x in sents):
        F.add("G54", "warn", sid, "L02 摄影机一栏没写：锁定也要写（The camera … / Locked-off …：景别 + 机位高度 + no pan, no tilt, no zoom, no cuts）；medium shot、gunshot 不算写了镜头")
    shake, lock = _neg_hit(_SHAKE_RE, body), re.search(r"\blocked\b|\bstatic\b|\bno pan\b", low)
    if shake and lock:
        F.add("G54", "warn", sid, f"L14 本镜同时写了 {sorted(set(w.lower() for w in shake))} 和锁定（{lock.group(0)}）：两句互相打架，模型挑容易的那句；锁定就删 handheld/sway，要晃就删 locked")

    def near(rx_act, rx_ev):
        for i, x in enumerate(sents):
            if rx_act.search(x):
                ctx = x + " " + (sents[i + 1] if i + 1 < len(sents) else "")
                yield x, ctx, rx_ev
    for x, ctx, _ in near(_MOVE_RE, _QTY_RE):
        if not _QTY_RE.search(ctx):
            F.add("G54", "warn", sid, f"L03 有位移动作但动作句及下一句没有可量的距离：「{x.strip()[:60]}」；写成 across three tiles / half a metre / one full stride，否则模型只挪几厘米交差")
            break
    windows = len(_WINDOW_RE.findall(body))
    try:
        sec = float(seconds or 0)
    except (TypeError, ValueError):
        sec = 0
    crowded = [s_.strip()[:60] for s_ in re.split(r"(?<=\.)\s+", body)
               if re.match(r"(At|From|Between|By)\s+(about\s+)?\d", s_.strip())
               and not re.search(r"\b(says|asks|shouts|whispers|replies|mutters|calls out|speaks)\b", s_)
               and len(re.findall(r",\s*(?:and|then)\s|;\s|\bthen\b|\bwhile\b", s_)) >= 3]
    if (sec and windows > sec) or crowded:
        F.add("G54", "warn", sid, f"L04 时间窗里塞了多个动作（{windows} 个时间窗 / {sec:g} 秒{'；' + crowded[0] + '…' if crowded else ''}）：一条视频一个主动作、每个时间窗一个动作，多写的里面最难的会被丢掉")
    for x, ctx, _ in near(_PHYS_RE, None):
        need = [n for n, r_ in (("速度/失控", _SPEED_RE), ("落地/撞击", _IMPACT_RE)) if not r_.search(ctx)]
        if need:
            F.add("G54", "warn", sid, f"L05 物理动作「{x.strip()[:50]}」所在句及下一句没写 {need}：按常识写多快、是否失控、怎么落地，否则模型用慢而可控的动作交差（滑倒拍成坐下）")
            break
    for m in _EXIT_RE.finditer(body):
        sent = body[max(0, body.rfind(".", 0, m.start()) + 1):body.find(".", m.end()) if body.find(".", m.end()) > 0 else len(body)]
        if not re.search(r"\b(left|right|top|bottom) edge\b", sent, re.I):
            F.add("G54", "warn", sid, f"L06 终点句「{m.group(0)}」没写从画框哪条边离开：写 through the left/right/top/bottom edge of the frame 和离开方式，否则模型让人走出去交差")
            break
        if re.search(r"\b(walk\w*|step\w*|strolls?)\b", sent, re.I) and not sh.get("walk_exit_ok"):
            F.add("G54", "warn", sid, f"L19 出画方式是走/迈步：「{sent.strip()[:60]}」；要表现被推、摔、拖出画就写那个动作，确实是走出去写 walk_exit_ok: true")
            break
    for x in sents:
        if _KEEP_VAGUE_RE.search(x):
            F.add("G54", "warn", sid, f"L16 video_prompt 用了模糊保持「{_KEEP_VAGUE_RE.search(x).group(0)}」：模型不知道「exactly」指什么；逐项写哪几样东西不动（the door, the lamp and the box do not move）")
            break
    for m in re.finditer(r"<d>", raw):
        pre = raw[:m.start()]
        cut = max(pre.rfind(". "), pre.rfind("</d>"))
        s_ = pre[cut + 1:] if cut >= 0 else pre
        hit = _INNER_RE.search(s_)
        if hit and hit.group(0).startswith("in front of"):   # 站位的 in front of her own body 不算，只查破折号后的情绪从句
            hit = re.search(r"\bin front of (?:him|her)\b(?! own)", s_.split("—")[-1]) if "—" in s_ else None
            hit = hit or re.search(r"\b(is being|has been|because)\b", s_)
        if hit:
            F.add("G54", "warn", sid, f"L23 台词前那句写了内心/因果从句「{hit.group(0)}」：「{s_.strip()[:60]}」；模型拍不出原因，只拍看得见的动作和表情（jaw tightens, eyes drop）")
            break
    picture_findings(F, sid, "video_prompt", body)
    vague = sorted({m.group(1).lower() for m in _VAGUE_RE.finditer(body)})
    if vague:
        F.add("G54", "warn", sid, f"L28 video_prompt 用了模糊量词 {vague}：模型按最省事的幅度拍；写成秒数、距离、角度（for 0.5 seconds, about 10 cm）")


def picture_findings(F: "Findings", sid: str, label: str, text: str) -> None:
    """L24：Picture N sets only … 的分工句要同句写 not from Picture M。"""
    for x in re.split(r"(?<=[.!?])\s+", text or ""):
        if re.search(r"\bPicture \d sets only\b", x, re.I) and not re.search(r"\bnot from Picture \d\b", x, re.I):
            F.add("G54", "warn", sid, f"L24 {label} 分工句「{x.strip()[:60]}」没写反面：同句补 …, not from Picture {re.search(r'Picture (\d)', x).group(1)}，否则模型从两张图里各取一半")
            break


def seal_findings(F: "Findings", sid: str, vp: str, sh: dict, one: str = "") -> None:
    """L15：视频提示词的必备封口句（声音、台词、时长、人数），缺一条报 error。"""
    if not (vp or "").strip():
        return
    low = re.sub(r"<d>.*?</d>", "", vp, flags=re.S).lower()
    miss = []
    if "these are the only sounds in the shot" not in low:
        miss.append("These are the only sounds in the shot")
    if [d for d in sh.get("dialogue") or [] if isinstance(d, dict) and d.get("text")]:
        if "these are the only words spoken in this shot" not in low:
            miss.append("These are the only words spoken in this shot")
    elif "no one speaks" not in low:
        miss.append("No one speaks")
    if "until the end of the clip" not in low:
        miss.append("until the end of the clip")
    if not (re.search(r"\bexactly \w+ (?:people|persons?)\b|\bonly one person\b|\bno (?:people|person|humans?|one else)\b", low) or (one and one.lower() in low)):
        miss.append("人数句（Exactly N people / Only one person in the frame.）")
    if miss:
        F.add("G54", "error", sid, f"L15 video_prompt 缺必备封口句 {miss}：没有封口，模型会自己加声音、台词、人和动作收尾（references/4-分镜与视频提示词.md L15）")


def frame_findings(F: "Findings", sid: str, fp: str) -> None:
    """L21/L16/L27/L24：静帧提示词里的左右、模糊保持、运动词、集合词、分工句。"""
    if not (fp or "").strip():
        return
    lr_findings(F, sid, "frame_prompt", fp)
    m = _KEEP_VAGUE_RE.search(fp)
    if m:
        F.add("G54", "warn", sid, f"L16 frame_prompt 用了模糊保持「{m.group(0)}」：逐项写哪几样东西保持参考图原样")
    mv = sorted({m.group(0).lower() for m in _FRAME_MOTION_RE.finditer(fp)})
    if mv:
        F.add("G54", "warn", sid, f"L21 frame_prompt 是静帧却写了运动/时间词 {mv}：起始帧只写这一瞬间的状态，运镜和先后顺序写进 video_prompt")
    col = sorted({m.group(1).lower() for m in _COLLECTIVE_RE.finditer(fp)})
    if col:
        F.add("G54", "warn", sid, f"L27 frame_prompt 用了集合词 {col}：模型不知道集合里有什么，逐件点名（the desk, the lamp and the two chairs）")
    picture_findings(F, sid, "frame_prompt", fp)


def drift_findings(F: "Findings", sid: str, vp: str, sh: dict, refs: dict) -> None:
    """L22：refs.json 身份图的 drift_anchors 逐字进本镜 video_prompt（人物在 in_frame / subject 里时）。"""
    people = set(sh.get("in_frame") or []) | ({sh["subject"]} if sh.get("subject") else set())
    low = (vp or "").lower()
    for rid, r in refs.items():
        if r.get("kind") != "identity" or r.get("subject") not in people:
            continue
        miss = [a for a in r.get("drift_anchors") or [] if isinstance(a, str) and a.strip() and a.lower() not in low]
        if miss:
            F.add("G54", "warn", sid, f"L22 「{r['subject']}」的漂移锚点 {miss}（{rid}.drift_anchors）没逐字写进 video_prompt：长镜头后半段脸和衣服会漂，锚点句每镜照抄")


_PHRASE_STOP = {"a", "an", "the", "one", "two", "three", "four", "five", "single", "exactly", "of", "on", "in", "at", "to", "from", "with", "and",
                "or", "is", "are", "sits", "stands", "lies", "rests", "his", "her", "their", "its", "this", "that", "by", "near", "beside", "under",
                "behind", "into", "onto", "over", "no", "other", "every", "each", "same", "only", "holds", "holding", "has", "carries", "carrying"}


def prop_phrase_findings(F: "Findings", shots: list[dict]) -> None:
    """L26：scene_state 里 set/props 的 en 名，同集各镜用的名词短语要一致（the cracked blue helmet 不能下一镜变 the helmet）。"""
    names = set()
    for sh in shots:
        for part in ("start", "end"):
            for grp in ("set", "props"):
                for v in (((sh.get("scene_state") or {}).get(part) or {}).get(grp) or {}).values():
                    if isinstance(v, dict) and isinstance(v.get("en"), str) and v["en"].strip():
                        names.add(v["en"].strip().lower())
    for name in sorted(names):
        seen: dict[str, str] = {}
        for sh in shots:
            text = re.sub(r"<d>.*?</d>", "", " ".join(str(sh.get(k) or "") for k in ("frame_prompt", "video_prompt")), flags=re.S).lower()
            for m in re.finditer(rf"((?:[a-z-]+\s+){{0,6}}){re.escape(name)}\b", text):
                words = m.group(1).split()
                keep = []
                for w in reversed(words):
                    if w in _PHRASE_STOP or re.search(r"[^a-z-]", w):
                        break
                    keep.insert(0, w)
                seen.setdefault(" ".join(keep + [name]), sh.get("id"))
        if len(seen) > 1:
            F.add("G54", "warn", None, f"L26 道具「{name}」各镜写法不一：{', '.join(f'{k}（{v}）' for k, v in list(seen.items())[:4])}；同一件东西每镜用同一个名词短语，否则模型当成两件")


def light_findings(F: "Findings", shots: list[dict]) -> None:
    """L25：同一场各镜 frame_prompt 的 key light 句逐字一致（写了 single key light / only light source 的场才查）。"""
    by_scene: dict[str, dict[str, str]] = {}
    for sh in shots:
        fp = sh.get("frame_prompt") or ""
        if not re.search(r"single key light|only light source", fp, re.I):
            continue
        for x in _sents(fp):
            if re.search(r"key light", x, re.I):
                by_scene.setdefault(sh.get("scene"), {}).setdefault(norm(x), sh.get("id"))
    for sc, d in by_scene.items():
        if len(d) > 1:
            F.add("G54", "warn", list(d.values())[1], f"L25 {sc} 各镜的主光句不一致（{', '.join(list(d.values())[:4])}）：同一场的 key light 句逐字照抄，不然光向跳、影子换边")


_NEAR_RE = re.compile(r"\b(?:sits?|rests?|lies|lie|stands?|is placed|are placed|is stacked|are stacked|is piled|are piled|leans?|is propped|are propped)\b[^.;]{0,40}?\b(beside|next to|near|close to|by the)\b", re.I)
_DEPTH_RE = re.compile(r"\b(far side|near side|behind|in front of|between\b[^.;]*\band\b|nearest (?:to )?the camera|closest to the camera|(?:closer to|farther from|further from|away from) the camera|toward the camera|back wall|foreground|background|camera side)\b", re.I)
_OPENABLE_RE = re.compile(r"\b(doors?|windows?|drawers?|curtains?|cabinet doors?|wardrobe doors?|gates?|lids?|shutters?)\b[^.;,]{0,25}?\b(open|ajar|half[- ]open|partly open|partially open|opened)\b|\b(open|ajar|half[- ]open|partly open)\s+(doors?|windows?|drawers?|gates?|lids?)\b", re.I)
_OPEN_QTY_RE = re.compile(r"\b(\d+\s*(?:degrees?|°|cm|centimet\w*)|hand'?s? width|finger'?s? width|a crack|a gap of|fully open|wide open|flat open|pushed flat|all the way|flat against the wall|at a right angle|halfway)\b", re.I)
_STILL_RE = re.compile(r"\b(does not move|do not move|stays? (?:exactly )?(?:as|at|where|still|in place|the same)|remains? (?:exactly )?(?:as|at|still|in place|the same|open|shut|closed)|never moves?)\b", re.I)
_COUNT_OBJ_RE = re.compile(r"\b(?:exactly (?:one|two|three|four|five|six|\d+)|one single)\s+(?!people\b|persons?\b|man\b|woman\b|men\b|women\b|figures?\b|times?\b|seconds?\b|words?\b|lines?\b|steps?\b|strides?\b|beats?\b|hits?\b|blinks?\b|breaths?\b|sounds?\b|shots?\b|takes?\b)([a-z-]+(?:\s+[a-z-]+)?)", re.I)


def set_findings(F: "Findings", sid: str, label: str, body: str, *, video: bool) -> None:
    """G54 L11–L13：陈设清点排他句、物件前后位置、门窗开度（references/4-分镜与视频提示词.md）。"""
    text = re.sub(r"<d>.*?</d>", "", body or "", flags=re.S).split("overall_soundscape:")[0]
    if not text.strip():
        return
    sents = [x for x in re.split(r"(?<=[.;])\s+", text) if x.strip()]
    counted = [re.sub(r"\s+(?:of|in|on|at|with|and|from)$", "", m.group(1).lower()) for m in _COUNT_OBJ_RE.finditer(text)]
    if counted and not re.search(r"\bno other\b|\bnothing else\b|\bthe only\b[^.]*\bin the (?:room|frame|shot)", text, re.I):
        F.add("G54", "warn", sid, f"L11 {label} 给物件写了数量（{', '.join(sorted(set(counted))[:4])}）却没有同类排他句：补 There are no other boxes, chairs or … anywhere in the room，否则模型按「场景应该有」多补一件")
    for x in sents:
        if _NEAR_RE.search(x) and not _DEPTH_RE.search(x) and not re.search(r"\b(camera|lens|shot)\b", x, re.I):
            F.add("G54", "warn", sid, f"L12 {label} 用「{_NEAR_RE.search(x).group(1)}」写位置但没写前后（以镜头为准）：「{x.strip()[:70]}」；补 on the far side of … from the camera / between … and the back wall / nearest the camera")
            break
    for x in sents:
        m = _OPENABLE_RE.search(x)
        if m and not _OPEN_QTY_RE.search(x) and not re.search(r"\b(?:does not|do not|never|won't|cannot|can't)\s+(?:\w+\s+)?open\b", x, re.I):
            F.add("G54", "warn", sid, f"L13 {label} 写了「{m.group(0)}」但没写开度：写成 open about one hand's width, roughly 15 degrees 加画面参照，并与上一镜 end_state 一致")
            break
    if video and any(_OPENABLE_RE.search(x) and not re.search(r"\b(?:does not|do not|never)\s+(?:\w+\s+)?open\b", x, re.I) for x in sents) and not _STILL_RE.search(text) and not re.search(r"\b(opens|closes|swings|slides|pushes|pulls|shuts)\b", text, re.I):
        F.add("G54", "warn", sid, f"L13 {label} 里有开着的门窗却没写全程不动：补 the study door does not move throughout the entire clip")


def adversarial_findings(F: "Findings", owner: str | None, items, sources: list[str], *, code: str = "G52") -> None:
    """G52：恶意执行预演。缺或少于 3 条 → warn（produce.py 提交前升 error）；blocked_by 不是当前提示词原句也不是「验收：」→ error；worst 重复 → error。"""
    items = items if isinstance(items, list) else []
    good = [x for x in items if isinstance(x, dict) and str(x.get("worst") or "").strip()]
    if len(good) < 3:
        F.add(code, "warn", owner, f"adversarial_preflight 只有 {len(good)} 条：提交前写 3 条「完全符合字面但最差」的成品和各自的堵法"
              "（[{\"worst\": …, \"blocked_by\": 提示词原句或「验收：…」}]，video-prompts-general §2b 第五部分）；不满 3 条 produce.py 拒绝提交")
    worsts = [norm(str(x["worst"])) for x in good]
    if any(SequenceMatcher(None, worsts[i], worsts[j]).ratio() > 0.8 for i in range(len(worsts)) for j in range(i + 1, len(worsts))):
        F.add(code, "error", owner, "adversarial_preflight 的 worst 有重复：三条要从不同角度想（人、手、时间、声音、镜头、可见性）")
    hay = "\n".join(sources)
    acc = [str(x.get("blocked_by") or "").strip() for x in good if str(x.get("blocked_by") or "").strip().startswith("验收：")]
    if len(acc) > 1:
        F.add(code, "error", owner, f"L29 adversarial_preflight 有 {len(acc)} 条 blocked_by 靠「验收：」：最多 1 条推给审片，其余要在提示词里堵住")
    for b in acc:
        if not re.search(r"\d|帧|秒", b):
            F.add(code, "error", owner, f"L29 验收条「{b[:40]}」没有可核对的数字/帧/秒：写成「验收：第 1.2–1.8 秒逐帧数人数=2」这类能数出来的条件")
    for x in good:
        b = str(x.get("blocked_by") or "").strip()
        if not b:
            F.add(code, "error", owner, f"adversarial_preflight「{str(x['worst'])[:20]}」没写 blocked_by")
        elif not b.startswith("验收：") and b not in hay:
            F.add(code, "error", owner, f"adversarial_preflight 的 blocked_by「{b[:40]}」不在当前提示词里（要逐字引提示词原句，或写「验收：…」指向验收项）；提示词改过就同步改预演")


def script_must_show(doc: dict) -> dict[str, list[str]]:
    """剧本每场 `[连续性] … 必拍：①… ②…` 的条目（C 阶段写，E 阶段逐条抄进 scenes[].must_show）。"""
    out: dict[str, list[str]] = {}
    for sc in doc["scenes"]:
        for ln in sc["lines"]:
            if ln["type"] == "tag" and ln["tag"] == "连续性" and re.search(r"必拍\s*[：:]", ln["text"]):
                body = re.split(r"必拍\s*[：:]", ln["text"], maxsplit=1)[-1]
                items = [x.strip(" 。；;，,") for x in re.split(r"[①②③④⑤⑥⑦⑧⑨⑩]|(?<![\d.])\d+[.、)）](?!\d)", body)]
                out.setdefault(sc["id"], []).extend(x for x in items if x)
    return out


def must_show_vs_script(F: "Findings", doc: dict, scenes: list[dict]) -> None:
    """G46 对账：剧本「必拍：」逐条要进同场 must_show（条数不少、每条文字照抄到可认出）。"""
    want = script_must_show(doc)
    have = {sc.get("id"): [str(f.get("fact") or "") for f in sc.get("must_show") or [] if isinstance(f, dict)] for sc in scenes}
    for sc in doc["scenes"]:
        sc_id = sc["id"]
        items = want.get(sc_id) or []
        if not items:
            F.add("G46", "warn", None, f"剧本 {sc_id} 没写「[连续性] … 必拍：①…」：按 screenplay 规则补（每场 ≥3 条观众必须看见的事实），再抄进 scenes[].must_show")
            continue
        facts = have.get(sc_id) or []
        if len(facts) < len(items):
            F.add("G46", "error", None, f"剧本 {sc_id} 必拍 {len(items)} 条，shots.json 同场 must_show 只有 {len(facts)} 条；逐条抄进 must_show 并指定承担镜")
        for it in items:
            best = max((SequenceMatcher(None, norm(it), norm(f)).ratio() for f in facts), default=0.0)
            if best < 0.5:
                F.add("G46", "error", None, f"剧本 {sc_id} 必拍「{it[:24]}」没照抄进 must_show（最相近 {best:.0%}）；照剧本原意写 fact，不许换成空话")


SPEC_KEYS = ("shot_size", "height", "facing", "blocking", "props", "start_state", "end_state", "link", "invariants")


def spec_lock_findings(F, data: dict, shots: list[dict]) -> None:
    """G55/G56（2026-09-27 用户定：镜头规格先锁死、执行不临时发挥；切镜头时场景内容必须相同）。
    只对写了 camera_setups 的新式分镜生效，旧项目不受影响。
    G56 规格完整：每镜 camera_setup 指向已定义机位，spec 的九项都写了；link 取 continuous / new_angle / new_scene。
    G55 场景锁：起始帧提示词逐字包含本机位的 lock 段，frame_refs 挂本机位底板；start_from_prev 指向更早、同机位的镜。"""
    setups = data.get("camera_setups")
    if not setups:
        return
    order = [sh["id"] for sh in shots]
    by = {sh["id"]: sh for sh in shots}
    for sh in shots:
        sid, cs = sh["id"], sh.get("camera_setup")
        if cs not in setups:
            F.add("G56", "error", sid, f"camera_setup「{cs}」没在 camera_setups 里定义：先在规划阶段定机位")
            continue
        spec = sh.get("spec") or {}
        miss = [k for k in SPEC_KEYS if not str(spec.get(k) or "").strip()]
        if miss:
            F.add("G56", "error", sid, f"镜头规格缺 {miss}：规格不全不许出图，回规划补全")
        if spec.get("link") not in (None, "", "continuous", "new_angle", "new_scene"):
            F.add("G56", "error", sid, "spec.link 只能是 continuous / new_angle / new_scene")
        prev = sh.get("start_from_prev")
        if prev:
            if prev not in by or order.index(prev) >= order.index(sid):
                F.add("G55", "error", sid, f"start_from_prev 指向不存在或更晚的镜 {prev}")
            elif by[prev].get("camera_setup") != cs:
                F.add("G55", "error", sid, f"末帧接续只能用于同机位：{prev} 是 {by[prev].get('camera_setup')}，本镜是 {cs}")
            continue
        st = setups[cs]
        lock = (st.get("lock") or "").strip()
        if not lock:
            F.add("G55", "error", sid, f"机位 {cs} 没写 lock（这个机位下看得见的全部固定陈设与位置）")
        elif lock not in (sh.get("frame_prompt") or ""):
            F.add("G55", "error", sid, f"起始帧提示词没有逐字包含机位 {cs} 的场景锁段：同机位每镜原样粘贴，切镜头场景才不会变")
        if st.get("plate") and st["plate"] not in (sh.get("frame_refs") or []):
            F.add("G55", "error", sid, f"frame_refs 没挂机位 {cs} 的底板 {st['plate']}")


def check(project: Project, ep: str) -> Findings:
    F = Findings()
    data = project.load_shots(ep)
    refs = project.load_refs()
    shots = data.get("shots") or []
    if data.get("cut_order") is not None:
        order = data["cut_order"]
        by_id = {sh["id"]: sh for sh in shots}
        if not order or len(order) != len(set(order)) or any(sid not in by_id for sid in order):
            F.add("G41", "error", None, "cut_order 为空、重复或包含未知镜头")
        else:
            shots = [by_id[sid] for sid in order] + [sh for sh in shots if sh["id"] not in order]
    scenes = {s["id"]: s for s in (data.get("scenes") or []) if "id" in s}
    lang = project.get("dialogue_lang")
    rates = project.sub("speech_rates")
    secs = project.sub("shot_seconds")
    one = project.get("one_person_clause") or DEFAULTS["one_person_clause"]    # 置空不等于关门：空值用内置默认句
    notext = project.get("no_text_clause") or DEFAULTS["no_text_clause"]
    forbidden = [w.lower() for w in project.get("forbidden_words") or []]
    keys = project.get("video_prompt_keys") or []
    fast_craft = project.get("craft_profile") == "commercial_fast"
    start_value = project.get("dialogue_start_max")
    start_max = float(start_value) if start_value is not None else (1.0 if fast_craft else None)

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
    # [VO] / [OS] 角色：台词 也是剧本台词（心声、画外声），G10 对照时一并收进来
    for sc in (script_doc["scenes"] if script_doc else []):
        for ln in sc["lines"]:
            if ln.get("type") == "tag" and ln.get("tag") in ("VO", "OS") and "：" in ln.get("text", ""):
                spk, txt = ln["text"].split("：", 1)
                script_norm.setdefault(norm(txt.strip()), {"scene": sc["id"], "speaker": spk.strip(), "text": txt.strip()})
    cast = speakers(script_doc, visual) if script_doc else set()

    ids_seen = set()
    locks = data.get("locks") or []
    prev_by_scene_subject: dict[tuple[str, str], dict] = {}
    facings_in_scene: dict[str, dict[str, str]] = {}
    facing_by_scene: dict[tuple[str, str], str] = {}
    covered_dialogue: set[str] = set()
    covered_scenes: set[str] = set()
    planned_total = 0.0
    pace = config_limits(project)["pace"]   # 比默认宽松的值不生效（G50）
    scene_use: dict[str, list[float]] = {}
    prev_shot: dict | None = None
    readings_all = project.get("readings") or {}
    single_reasons: dict[str, list[str]] = {}
    scene_people: dict[str, dict[str, bool]] = {}
    F.limits = config_limits(project, F)
    waive_findings(F, shots, data.get("scenes") or [], project)

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
        for name, st_ in (((sh.get("scene_state") or {}).get("start") or {}).get("characters") or {}).items():
            if isinstance(st_, dict) and "present" in st_:
                scene_people.setdefault(scene, {})[name] = bool(st_["present"])
        if script_doc and scene not in script_scene_ids:
            F.add("G01", "error", sid, f"场景 {scene} 不在剧本里")
        covered_scenes.add(scene)
        kind = sh.get("kind", "person")
        fp, vp = sh.get("frame_prompt", "") or "", sh.get("video_prompt", "") or ""
        seconds = float(sh.get("seconds") or 0)
        planned_total += seconds
        talk = [d for d in sh.get("dialogue") or [] if d.get("text") and not d.get("vo")] if not sh.get("audio_from") else []
        if kind in INSERT_KINDS and (talk or sh.get("characters")):
            # kind 是自报字段，不能用来逃人物镜的门：有镜内台词或 characters 的镜一律按人物镜查
            F.add("G01", "warn", sid, f"kind 标成「{kind}」但本镜有{'镜内台词' if talk else ' characters'}：按人物镜查全部门；确是插入镜就把台词改成 vo 或拆出去")
            kind = "person"

        # G02 画内人数句（不看 kind 声明，见上）：单人写固定句，多人写 exactly N（video-prompts-general §2b 封闭世界）
        n_people = _people_count(fp, one)
        if kind not in INSERT_KINDS:
            if n_people is None:
                F.add("G02", "error", sid, f"起始帧提示词缺画内人数句：单人写「{one}」，多人写 exactly N people（并开 multi_person、逐人写位置朝向）")
            elif sh.get("multi_person") and n_people < 2:
                F.add("G02", "error", sid, "multi_person 镜的起始帧提示词要写 exactly N people（N≥2），不能写单人句")
            elif n_people >= 2 and not sh.get("multi_person"):
                F.add("G02", "warn", sid, f"起始帧写了 exactly {n_people} people 但 multi_person 没开；多人镜打开 multi_person 并写 multi_person_reason")

        # G53 单人对白须提供空间关系理由（SKILL 11c）；真实性由 reviewer 与预演核验
        if kind not in INSERT_KINDS and talk and n_people == 1:
            sr = str(sh.get("single_reason") or "").strip()
            if not sr:
                F.add("G53", "error", sid, "台词镜只有一人入画：默认让听者入画（multi_person + exactly N，听者只露背/肩），"
                      "单人对白须写 single_reason（引建立镜号、剧本原句、对象方位、视线与切回承接）；自言自语或全场喊话也须具体理由")
            elif len(sr) < 10:
                F.add("G53", "error", sid, f"single_reason「{sr}」太短，说不清为什么不给听者入画（引剧本原句和上一镜镜号）")
            else:
                single_reasons.setdefault(sr, []).append(sid)
        if kind not in INSERT_KINDS and n_people and n_people >= 2:
            present = sorted(k for k, v in (scene_people.get(scene) or {}).items() if v)
            in_frame = sh.get("in_frame")
            if isinstance(in_frame, list) and in_frame:
                if len(in_frame) != n_people:
                    F.add("G53", "error", sid, f"frame_prompt 写 exactly {n_people}，in_frame 列了 {len(in_frame)} 人 {in_frame}；人数写死且一致")
                gone = [x for x in in_frame if present and x not in present]
                if gone:
                    F.add("G53", "error", sid, f"in_frame 里的 {gone} 不在 scene_state 的在场名单 {present} 里（已离场或没登场）")
            elif present and n_people > len(present):
                F.add("G53", "error", sid, f"frame_prompt 写 exactly {n_people} 人入画，scene_state 在场只有 {len(present)} 人 {present}；多出来的人从哪来")

        # G03 参考图存在；人物镜要有身份图
        for r in sh.get("frame_refs") or []:
            if r not in refs:
                F.add("G03", "error", sid, f"参考图 {r} 不在 refs.json")
        if kind not in INSERT_KINDS and sh.get("subject") and not any(refs.get(r, {}).get("kind") == "identity" for r in sh.get("frame_refs") or []):
            if not _waived(sh, "G03"):
                F.add("G03", "warn", sid, f"人物镜没有绑定「{sh.get('subject')}」的身份图（identity ref）")
        sc = scenes.get(scene) or {}
        if sc.get("plates") and not sh.get("frame_parent") and not any(r in (sc.get("plates") or []) for r in sh.get("frame_refs") or []) and kind != "plate":
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
            if i == 0 and start_max is not None and at > start_max and not sh.get("reaction_first") and not _waived(sh, "G05"):
                F.add("G05", "warn", sid, f"第一句台词 {at}s 才开口（上限 {start_max}s）；要么提前，要么写 reaction_first 并说明")
            if not d.get("speaker"):
                F.add("G04", "error", sid, "台词缺 speaker")
            elif cast and d["speaker"] not in cast:
                F.add("G15", "warn", sid, f"说话人「{d['speaker']}」不在剧本/视觉设定的人物里")
            # G09 台词逐字进视频提示词
            # vo:true（心声、画外音另配）不进视频正文，不查
            if t and not d.get("vo") and norm(t) not in norm(vp):
                F.add("G09", "error", sid, f"台词「{t}」没有逐字出现在 video_prompt 里")
            # G10 台词来自剧本
            if script_doc and t and norm(t) not in script_norm:
                F.add("G10", "error", sid, f"台词「{t}」在剧本里找不到（剧本和镜头漂移）：台词逐字来自剧本，改镜头台词或回剧本改（error 门不能 waive）")
            covered_dialogue.add(norm(t))
        if dlg and need + 0.5 > seconds:
            F.add("G04", "error", sid, f"台词需要约 {need:.1f}s + 0.5s 收尾，seconds={seconds} 装不下")
        if fast_craft and kind not in INSERT_KINDS and not dlg and not sh.get("silent_reason") and not _waived(sh, "G05"):
            F.add("G05", "warn", sid, "人物镜没有台词；要么给一句，要么写 silent_reason")

        # G06 不出可读文字；G07 禁词
        if notext and notext.lower() not in fp.lower():
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
        if project.get("video_dialect", "minimax-h3") == "minimax-h3" and any(not d.get("vo") for d in dlg) and "<d>" not in vp:
            F.add("G09", "error", sid, "有台词但 video_prompt 里没有 <d>…</d> 台词标记")

        # G23 连续性锁：锁面逐字进范围内的起始帧提示词（否定式不算携带）
        for lk in locks:
            scope = lk.get("shots", "all")
            if scope != "all" and sid not in (scope or []):
                continue
            phrase = (lk.get("phrase") or "").lower()
            if phrase and kind not in INSERT_KINDS and sh.get("subject") and lk.get("subject", sh.get("subject")) == sh.get("subject"):
                hit = re.search(r"(?<!no )(?<!without )" + re.escape(phrase), fp.lower())
                if not hit:
                    F.add("G23", "error", sid, f"锁 {lk.get('id')} 的锁面「{lk.get('phrase')}」没有逐字出现在 frame_prompt 里")
                # 视频提示词同样要带锁面（CON-07）；台词 <d>…</d> 不算，只查 warn
                vtext = re.sub(r"<d>.*?</d>", "", (vp or sh.get("video_body") or ""), flags=re.S).lower()
                if vtext and not re.search(r"(?<!no )(?<!without )" + re.escape(phrase), vtext) and not _waived(sh, "G23"):
                    F.add("G23", "warn", sid, f"锁 {lk.get('id')} 的锁面「{lk.get('phrase')}」没有逐字出现在 video_prompt/video_body 里")
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
                # 冲击重复（storyboard-keyframes §2）：重复镜从同一个"动作前"起步，起点本来就等于前一镜起点
                impact_repeat = str(sh.get("split_reason") or "").startswith("冲击重复")
                if diffs and not sh.get("boundary_break") and not impact_repeat:
                    F.add("G26", "error", sid, f"与上一镜 {prev['id']} 的边界链不接：{diffs} 前一镜终点≠本镜起点；补一镜、改边界，或写 boundary_break 说明镜外发生了什么")
            # G27 同景别同主体跳切
            # 紧挨着且没写 split_reason 时由 G45 提示合并成长镜头，这里不再劝"换景别拆开"
            adjacent_unsplit = prev is not None and prev is prev_shot and not sh.get("split_reason")
            if prev and not adjacent_unsplit and not str(sh.get("split_reason") or "").startswith("冲击重复") and prev.get("framing") and sh.get("framing") and norm(prev["framing"]) == norm(sh["framing"]) and not _waived(sh, "G27"):
                F.add("G27", "warn", sid, f"和上一镜 {prev['id']} 同主体同景别「{sh['framing']}」，是跳切；同一人连续的戏合并成一个长镜头，确需拆开就换景别或角度并写 split_reason")
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
        if vp and not _waived(sh, "G54"):
            loophole_findings(F, sid, vp, sh.get("seconds"), head=project.get("video_prompt_head") or "", sh=sh)
            drift_findings(F, sid, vp, sh, refs)
        seal_findings(F, sid, vp, sh, one)   # L15 是 error，豁免不掉
        if not _waived(sh, "G54"):
            set_findings(F, sid, "frame_prompt", fp, video=False)
            set_findings(F, sid, "video_prompt", vp, video=True)
            frame_findings(F, sid, fp)

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
        if kind not in INSERT_KINDS and n_people == 1 and re.search(
                r"\b(two|three|both|couple|crowd|people)\b(?!-quarter)(?!\s+(?:of\s+(?:his|her|their)\s+)?(?:hands?|arms?|eyes?|feet|legs?|palms?|sides?|ends?|shoulders?|knees?|fingers?)\b)",
                fp.lower()) and not sh.get("multi_person"):
            F.add("G13", "warn", sid, "起始帧提示词写了单人句又出现 two/both/people 等词：真是多人镜就开 multi_person、写 exactly N 和逐人位置朝向；不是就删掉这些词")
        if kind not in INSERT_KINDS and re.search(r"\bin focus\b", fp.lower()) and not _waived(sh, "G13"):
            F.add("G13", "warn", sid, "「in focus」给虚焦背景里的路人留了口子（实战里多出过人）；按封闭世界写死画内人数，不写 in focus")
        if re.search(r"\bas (?:a|the) background\b", fp.lower()) and not _waived(sh, "G13"):
            F.add("G13", "warn", sid, "frame_prompt 写了「as a background」：参考图会被当成背景贴图、人物被重画（E30）；写清参考图分工，不用 as a background")

        # G52 恶意执行预演：3 条「完全符合字面但最差」的成品和各自的堵法（blocked_by 必须是当前提示词原句或「验收：…」）
        adversarial_findings(F, sid, sh.get("adversarial_preflight"), [fp, sh.get("motion") or "", vp, sh.get("video_body") or ""])

        # G29 动作职责镜：生成模型动作常晚 1–2 秒，计划取用太短或没标 action_window，动作会落在剪点外
        if kind in ("person", "hands") and ACTION_WORDS_RE.search(sh.get("motion", "") or "") and not _waived(sh, "G29"):
            plan = [float(x) for x in USE_PLAN_RE.findall(" ".join(map(str, sh.get("continuity") or [])) + " " + str(sh.get("silent_reason") or ""))]
            if plan and min(plan) < 2.0:
                F.add("G29", "warn", sid, f"动作镜（{ACTION_WORDS_RE.search(sh['motion']).group(0)}）计划只取用约 {min(plan)}s；动作常晚 1–2s 才发生，取用至少 2s，出点按动作结束定")
            if not sh.get("planned_action_window") and not sh.get("action_window"):
                F.add("G29", "warn", sid, "动作镜建议注明 planned_action_window 估时；生成后每个 take 单独审查 action_window，计划不作为剪点")
        # G30 全景/全身人物镜配台词：脸只有几十像素，口型和表情都读不出
        if kind == "person" and dlg and re.search(r"全景|全身|远景", sh.get("framing", "") or "") and not _waived(sh, "G30"):
            F.add("G30", "warn", sid, f"全景/全身人物镜有台词（{sh.get('framing', '')[:12]}…）；对白镜至少中景，脸高占画高 20% 以上，全景只交代空间不配台词")
        # G31 台词要有情绪：每句 dialogue[].emotion（情绪·强度·语速·音量），配音按它选参考或写 instruct
        if not _waived(sh, "G31"):
            bare = [d.get("text", "")[:10] for d in dlg if not str(d.get("emotion") or "").strip() and not (isinstance(d.get("emotion"), dict) and d["emotion"])]
            if bare:
                F.add("G31", "warn", sid, f"{len(bare)} 句台词没写 emotion（{'、'.join(bare)}…）；写「情绪·强度·语速·音量」，例 惊慌·强·快·大，配音才不会平读")
        # G36 画风漂移诱因词（否定式 no film grain 不算）
        preset_ = project.get("style_preset")
        drift_re = ANIME_DRIFT_RE if preset_ in ANIME_PRESETS else GUOMAN_DRIFT_RE if preset_ == "guoman_3d" else None
        if drift_re and not _waived(sh, "G36"):
            bad = [m.group(0) for m in drift_re.finditer(fp) if not NEG_BEFORE_RE.search(fp[max(0, m.start() - 30):m.start()])]
            if bad:
                F.add("G36", "warn", sid, f"画风 {preset_} 的起始帧出现摄影/渲染词 {sorted(set(bad))}，会把画面往 3D/真人拉；按 storyboard-keyframes §6b 第 8 项换成本画风的镜头词")
        # G38 参考图数量与头肩图绑定（visual-assets §3、§8）
        frefs = list(sh.get("frame_refs") or [])
        n_refs = len(frefs) + (1 if sh.get("frame_parent") else 0)
        if n_refs > 3 and not _waived(sh, "G38"):
            F.add("G38", "warn", sid, f"起始帧挂了 {n_refs} 张参考（含 frame_parent 父帧）；默认 2 张、接触镜 3 张、不超过 3 张，职责重叠的参考会被平均")
        for r in frefs:
            if r.endswith(FACE_SUFFIX) and r[:-len(FACE_SUFFIX)] in frefs and not _waived(sh, "G38"):
                F.add("G38", "warn", sid, f"同时绑了全身身份图 {r[:-len(FACE_SUFFIX)]} 和头肩图 {r}；两张职责重叠，按景别只绑一张")
            elif (refs.get(r) or {}).get("kind") == "identity" and (r + FACE_SUFFIX) in refs and r + FACE_SUFFIX not in frefs \
                    and CLOSE_FRAMING_RE.search(sh.get("framing", "") or "") and not _waived(sh, "G38"):
                F.add("G38", "warn", sid, f"中近景/近景/特写绑的是全身身份图 {r}，但 refs.json 有 {r + FACE_SUFFIX}；近景绑头肩图，脸才不漂")
        # G40 同机位父帧：frame_parent 必须是本镜之前、同场、同主体的镜头
        par = sh.get("frame_parent")
        if par:
            j, ps = next(((j, s_) for j, s_ in enumerate(shots) if s_.get("id") == par), (None, None))
            me = next(j_ for j_, s_ in enumerate(shots) if s_ is sh)
            if j is None or j >= me:
                F.add("G40", "error", sid, f"frame_parent {par} {'不存在' if j is None else '在本镜之后'}；父帧必须是本集前面已出过起始帧的镜头")
            elif (ps.get("scene") != scene or ps.get("subject") != sh.get("subject")) and not _waived(sh, "G40"):
                F.add("G40", "warn", sid, f"frame_parent {par} 和本镜不是同场同主体（{ps.get('scene')}/{ps.get('subject')}）；同机位派生只用于同场同一人物反复回到的机位")

        # G34 尺度锚点：绑了底板的中景以上/双人人物镜，起始帧要写人物与现实参照物的关系
        plate_bound = any(refs.get(r, {}).get("kind") == "plate" for r in sh.get("frame_refs") or [])
        if kind == "person" and plate_bound and (sh.get("multi_person") or SCALE_FRAMING_RE.search(sh.get("framing", "") or "")) \
                and not SCALE_RE.search(fp) and not _waived(sh, "G34"):
            F.add("G34", "warn", sid, "中景以上/双人镜的起始帧没写尺度锚点；写人物与护栏/门/桌/台阶的关系（the handrail reaches his waist），多人写相对身高（visual-assets §12）")
        # G35 only checks a declared requirement; words like "dust/out of focus" prove no motion.
        if sh.get("environment_motion_required") and not str(sh.get("environment_motion") or "").strip() and not _waived(sh, "G35"):
            F.add("G35", "warn", sid, "本镜明确要求环境运动，但未写具体环境变化；静止背景本身不构成错误")

        # G42 节奏下限：计划取用（motion/duty/continuity 里的「取用约 Xs」；没写就按整条 seconds 算）不能过短
        plan_txt = " ".join([str(sh.get("motion") or ""), str(sh.get("duty") or "")] + [str(x) for x in sh.get("continuity") or []])
        plan_vals = [float(x) for x in USE_PLAN_RE.findall(plan_txt)]
        use = min(plan_vals) if plan_vals else seconds
        scene_use.setdefault(scene, []).append(use)
        on_screen_dlg = [d for d in dlg if not sh.get("audio_from") and (not sh.get("subject") or d.get("speaker") == sh.get("subject"))]
        if not _waived(sh, "G42"):
            if kind == "person" and on_screen_dlg:
                floor = max(float(pace["dialogue_min"]), need + float(pace["dialogue_tail"]))
                if use + 1e-6 < floor:
                    F.add("G42", "warn", sid, f"对白镜计划取用约 {use:.1f}s，低于下限 {floor:.1f}s（台词说完约 {need:.1f}s + {pace['dialogue_tail']}s，且不短于 {pace['dialogue_min']}s）；台词要在一个镜头里说完，不在句中切")
            elif kind == "person":
                if use + 1e-6 < float(pace["reaction_min"]) and not sh.get("fast_cut_reason"):
                    F.add("G42", "warn", sid, f"反应镜计划取用约 {use:.1f}s，低于 {pace['reaction_min']}s；冲击剪辑确需更短就写 fast_cut_reason")
            elif use + 1e-6 < float(pace["insert_min"]) and not sh.get("fast_cut_reason"):
                F.add("G42", "warn", sid, f"插入镜计划取用约 {use:.1f}s，短于 {pace['insert_min']}s 而没写 fast_cut_reason（观众来不及看清）")

        # G44 台词语种与读音：lang 与 dialogue_lang 一致、<d>[语种] 标签对、文字像目标语言、日语专名有 reading
        if not _waived(sh, "G44"):
            want_tags = LANG_TAGS.get(str(lang or "")[:2])
            tags = [t.strip().lower() for t in re.findall(r"<d>\s*\[([A-Za-z ]+)\]", vp)]
            bad_tags = sorted({t for t in tags if want_tags and t not in want_tags})
            if bad_tags:
                F.add("G44", "warn", sid, f"video_prompt 的台词语种标签 {bad_tags} 与 dialogue_lang={lang} 不符；语言参数错了，口音和语调会跟着错")
            for d in dlg:
                t = d.get("text", "") or ""
                if d.get("lang") and lang and d["lang"] != lang and not d.get("lang_reason"):
                    F.add("G44", "warn", sid, f"台词「{t[:12]}」lang={d['lang']} 与 dialogue_lang={lang} 不一致；TTS/视频的语言参数必须显式等于台词语言，确属外语台词写 lang_reason")
                eff = str(d.get("lang") or lang or "")[:2]
                if eff == "ja" and HAN_RE.search(t) and not KANA_RE.search(t) and len(norm(t)) >= 4:
                    F.add("G44", "warn", sid, f"日语台词「{t[:12]}」没有一个假名，像中文或书面汉文；按母语口语改写（screenplay §4c）")
                elif eff == "zh" and KANA_RE.search(t):
                    F.add("G44", "warn", sid, f"中文台词「{t[:12]}」里有假名，语种写混了")
                rd = d.get("reading")
                if eff == "ja" and not isinstance(rd, str):
                    known = set(readings_all) | set((rd or {}) if isinstance(rd, dict) else {})
                    miss = sorted(n for n in cast if n and HAN_RE.search(n) and n in t and n not in known)
                    if miss:
                        F.add("G44", "warn", sid, f"台词里的专名 {miss} 没写读音；在 dialogue[].reading 写 {{\"{miss[0]}\": \"假名\"}}（或 drama.json readings），配音前按它校对")

        # G45 同一人不拆两镜：同场相邻两镜主体相同、中间没有别人或插入镜，默认合并成一个长镜头
        if prev_shot is not None and kind not in INSERT_KINDS and sh.get("subject") and not _waived(sh, "G45") \
                and prev_shot.get("scene") == scene and prev_shot.get("kind", "person") not in INSERT_KINDS \
                and prev_shot.get("subject") == sh.get("subject") and not sh.get("split_reason"):
            merged = float(prev_shot.get("seconds") or 0) + seconds
            cap = float(secs["max"])
            extra = f"；合并后约 {merged:.0f}s 超过 shot_seconds.max={cap:.0f}，先删同质节拍" if merged > cap else ""
            F.add("G45", "warn", sid, f"与上一镜 {prev_shot.get('id')} 同场同一人物「{sh['subject']}」相邻、中间没有别人的镜头或插入镜；默认合并成一个长镜头（按内容定时长，上限 {cap:.0f}s）{extra}；只有景别/机位/剧情明显变化或时间跳跃才拆，拆就写 split_reason")
        prev_shot = sh
        for name, st_ in (((sh.get("scene_state") or {}).get("end") or {}).get("characters") or {}).items():
            if isinstance(st_, dict) and "present" in st_:
                scene_people.setdefault(scene, {})[name] = bool(st_["present"])
    for sr, who in single_reasons.items():
        if len(who) >= 2:
            F.add("G53", "error", who[1], f"single_reason 原样用在 {who}：理由挪到另一镜仍成立就是套话（搬家测试），按没写算；每镜引本镜的剧本原句和上一镜镜号")

    # G42 同场平均镜长下限（只设下限，允许长镜头）
    for sc_id, uses in scene_use.items():
        if uses and sum(uses) / len(uses) + 1e-6 < float(pace["scene_avg_min"]):
            F.add("G42", "warn", None, f"{sc_id} 计划平均镜长 {sum(uses) / len(uses):.2f}s，低于 {pace['scene_avg_min']}s；镜头切得太碎，合并同一人的相邻镜、让台词在一个镜头里说完")

    # G43 视线：有台词的人物镜写 gaze（target + direction）；方向与对手在本场的朝向互补；提示词写明视线
    for sh in shots:
        sid, kind = sh.get("id"), sh.get("kind", "person")
        if kind != "person" or _waived(sh, "G43"):
            continue
        dlg = sh.get("dialogue") or []
        speaks = [d for d in dlg if not sh.get("audio_from") and (not sh.get("subject") or d.get("speaker") == sh.get("subject"))]
        gz = sh.get("gaze") if isinstance(sh.get("gaze"), dict) else None
        reason = str(sh.get("gaze_reason") or "").strip()
        if not gz:
            if speaks:
                F.add("G43", "warn", sid, "有台词的人物镜没写 gaze（{\"target\": 说话对象, \"direction\": left/right}）；说话人默认看着对手，不看镜头")
            continue
        tgt, dirn = str(gz.get("target") or ""), str(gz.get("direction") or "")
        if dirn not in GAZE_DIRS or not tgt:
            F.add("G43", "warn", sid, f"gaze 要写 target（人物名或物件）和 direction（{'/'.join(GAZE_DIRS)}）：{gz}")
            continue
        scene = sh.get("scene")
        people = {subj for (sc_, subj) in facing_by_scene if sc_ == scene} | set(cast)
        if dirn == "camera" and not reason:
            F.add("G43", "warn", sid, "gaze 朝镜头：只有独白、直面观众这类剧情才看镜头，写 gaze_reason")
        if tgt not in people and not reason:
            F.add("G43", "warn", sid, f"gaze.target「{tgt}」不是同场人物（看物件、回避视线）；剧情需要就写 gaze_reason")
        if dirn in ("left", "right") and not reason:
            own = sh.get("facing")
            if own in ("left", "right") and own != dirn:
                F.add("G43", "warn", sid, f"gaze 看画{'左' if dirn == 'left' else '右'}，身体 facing 却朝画{'左' if own == 'left' else '右'}；对不上就会像在看画外第三者")
            tf = facing_by_scene.get((scene, tgt))
            if tf == dirn:
                F.add("G43", "warn", sid, f"对手「{tgt}」在本场面朝画{'左' if tf == 'left' else '右'}，说话人也看画{'左' if dirn == 'left' else '右'}：两人看向同一侧，正反打会读成在看画外第三者")
        if dirn in ("left", "right"):
            for label, body in (("frame_prompt", sh.get("frame_prompt") or ""), ("video_prompt", re.sub(r"<d>.*?</d>", "", sh.get("video_prompt") or "", flags=re.S))):
                dirs = {m.group(1).lower() for m in GAZE_TEXT_RE.finditer(body)}
                if not dirs:
                    F.add("G43", "warn", sid, f"{label} 没写视线方向；写 eyes on {tgt if label == 'frame_prompt' else 'the other person'} off screen-{dirn}（眼神略偏离镜头，不看镜头）")
                elif dirn not in dirs:
                    F.add("G43", "warn", sid, f"{label} 写的视线方向 {sorted(dirs)} 与 gaze.direction={dirn} 不一致")
        if dirn != "camera":
            for label, body in (("frame_prompt", sh.get("frame_prompt") or ""), ("video_prompt", sh.get("video_prompt") or "")):
                hit = next((m for m in CAMERA_LOOK_RE.finditer(body) if not NEG_WIDE_RE.search(body[max(0, m.start() - 40):m.start()])), None)
                if hit:
                    F.add("G43", "warn", sid, f"{label} 让人物看镜头（「{hit.group(0)}」），但 gaze 不是 camera；对话镜看对手，不看镜头")

    # G41 scene state survives reverse shots; omitted fields retain their previous value.
    for issue in scene_state_issues(shots):
        F.add("G41", "warn", issue["shot"], issue["message"])

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

    # G32 因果交代：requires_setup 指向的铺垫（名字在前面某镜的 setup_for，或直接写铺垫镜 ID）必须存在且在本镜之前
    order = {s.get("id"): i for i, s in enumerate(shots)}
    for i, sh in enumerate(shots):
        if _waived(sh, "G32"):
            continue
        ev = EVENT_RE.search(f"{sh.get('title') or ''} {sh.get('duty') or ''}")
        if ev and not sh.get("requires_setup") and not sh.get("setup_for"):
            F.add("G32", "warn", sh.get("id"), f"事件镜（{ev.group(0)}）没写起因：requires_setup 写起因镜 ID 或起因名（前面某镜 setup_for 铺垫）；起因就在本镜里先发生，写本镜 ID")
        for need_item in sh.get("requires_setup") or []:
            item = str(need_item)
            if re.fullmatch(r"EP\d{3}-S\d{2,}", item):
                j = order.get(item)
                if j is None:
                    F.add("G32", "warn", sh.get("id"), f"requires_setup 指向的铺垫镜 {item} 不存在")
                elif j > i:   # j == i：起因在本镜内（长镜头里先因后果）
                    F.add("G32", "warn", sh.get("id"), f"requires_setup 指向的铺垫镜 {item} 在本镜之后；已声明的预先披露依赖应在本镜之前；后揭示信息不要写 requires_setup")
                continue
            where = [j for j, s in enumerate(shots) if item in (s.get("setup_for") or [])]
            if not where:
                F.add("G32", "warn", sh.get("id"), f"「{item}」没有任何镜在 setup_for 里铺垫；观众看不到它从哪来（凭空出现）")
            elif min(where) >= i:
                F.add("G32", "warn", sh.get("id"), f"「{item}」的铺垫镜 {shots[min(where)].get('id')} 在本镜之后；已声明的预先披露依赖应在本镜之前")
    # G46 必拍事实：scenes[].must_show 每条都要有镜头 must_show_ids 承担；shots 指向的镜要存在；删镜后承担镜仍在 cut_order
    in_cut = set(data["cut_order"]) if isinstance(data.get("cut_order"), list) and data.get("cut_order") else {s_.get("id") for s_ in shots}
    by_sid = {s_.get("id"): s_ for s_ in shots}
    facts: dict[str, dict] = {}
    for sc in data.get("scenes") or []:
        for f_ in sc.get("must_show") or []:
            if not isinstance(f_, dict) or not f_.get("id") or not str(f_.get("fact") or "").strip():
                F.add("G46", "error", None, f"{sc.get('id')} 的 must_show 条目要写 id 和 fact：{f_}")
                continue
            if f_["id"] in facts:
                F.add("G46", "error", None, f"must_show id {f_['id']} 在本集重复")
                continue
            facts[f_["id"]] = {**f_, "_scene": sc.get("id")}
            if f_.get("kind") and f_["kind"] not in MUST_SHOW_KINDS:
                F.add("G46", "warn", None, f"{f_['id']} 的 kind「{f_['kind']}」不在 {'/'.join(MUST_SHOW_KINDS)} 里")
            for t in f_.get("shots") or []:
                if t not in by_sid:
                    F.add("G46", "error", None, f"{f_['id']}「{f_['fact'][:16]}」的 shots 指向不存在的镜 {t}")
                elif f_["id"] not in (by_sid[t].get("must_show_ids") or []):
                    F.add("G46", "warn", t, f"{f_['id']} 的 shots 列了本镜，但本镜 must_show_ids 没写 {f_['id']}；承担关系两边写一致")
    if script_doc:
        must_show_vs_script(F, script_doc, data.get("scenes") or [])
    carriers: dict[str, list[str]] = {}
    for sh in shots:
        for mid in sh.get("must_show_ids") or []:
            if mid not in facts:
                F.add("G46", "error", sh.get("id"), f"must_show_ids 里的 {mid} 不在任何 scenes[].must_show 里")
            else:
                carriers.setdefault(mid, []).append(sh.get("id"))
    for mid, f_ in facts.items():
        who = carriers.get(mid) or []
        if not who:
            F.add("G46", "error", None, f"{f_['_scene']} 的必拍事实 {mid}「{f_['fact'][:20]}」没有任何镜头的 must_show_ids 承担；补镜或把它写进承担镜，不能靠台词带过")
        elif not any(x in in_cut for x in who):
            F.add("G46", "error", None, f"必拍事实 {mid}「{f_['fact'][:20]}」的承担镜 {who} 都不在 cut_order 里；删镜删掉了因果证据，恢复一镜或换承担镜")
        # G47 数量类事实：承担镜的起始帧提示词要把数字写进去（数量与排布写死，目检时逐个数）
        if f_.get("kind") == "count" or _fact_numbers(str(f_["fact"])):   # 写了数量就按数量事实查，改 kind 逃不掉
            nums = _fact_numbers(str(f_["fact"]))
            for x in sorted(set(who) | set(f_.get("shots") or [])):
                sh = by_sid.get(x)
                if not sh or _waived(sh, "G47"):
                    continue
                fp_ = sh.get("frame_prompt") or ""
                miss = [n for n in nums if not _prompt_has_number(fp_, n)] if nums else ([] if NUMBER_RE.search(fp_) else ["数量"])
                if miss:
                    F.add("G47", "warn", x, f"承担数量事实 {mid}「{f_['fact'][:20]}」，frame_prompt 里没写出 {miss}；把数量和排布写死（exactly ten boxes, five on the top row and five on the bottom row），起始帧目检逐个数")

    # G48 能力规则重复解释：同集 explains_ability 镜累计超限；第二集起开头窗口内不许超过 1 镜
    lim = F.limits["gate_limits"]
    ability_terms = [str(t) for t in project.get("ability_terms") or []]   # 立项时从装置条款抄；自报 explains_ability 之外的兜底
    t_cursor, early, expl = 0.0, [], []
    for sh in shots:
        if sh.get("id") not in in_cut:
            continue
        use = _planned_use(sh)
        said = " ".join(str(d.get("text") or "") for d in sh.get("dialogue") or []) + " " + str(sh.get("duty") or "")
        hit_terms = [t for t in ability_terms if t and t in said]
        if hit_terms and not sh.get("explains_ability"):
            F.add("G48", "warn", sh.get("id"), f"台词/duty 提到能力关键词 {hit_terms[:3]} 却没标 explains_ability；按解释能力计数（drama.json ability_terms）")
        if (sh.get("explains_ability") or hit_terms) and not _waived(sh, "G48"):
            expl.append((sh.get("id"), use))
            if t_cursor < float(lim["recap_window"]):
                early.append(sh.get("id"))
        t_cursor += use
    total_expl = sum(u for _, u in expl)
    if len(expl) > int(lim["ability_explain_shots"]) or total_expl > float(lim["ability_explain_seconds"]) + 1e-6:
        F.add("G48", "warn", None, f"本集 {len(expl)} 镜在解释/确认能力规则（{', '.join(x for x, _ in expl)}，计划约 {total_expl:.0f}s），超过 {lim['ability_explain_shots']} 镜或 {lim['ability_explain_seconds']:.0f}s；"
              "已讲清的规则后面只留一句提醒，新角色确认 ≤1 句（screenplay §5b3）")
    ep_no = int(m_.group(1)) if (m_ := re.match(r"EP(\d+)", ep)) else 1
    if ep_no >= 2 and len(early) > int(lim["recap_explain_shots"]):
        F.add("G48", "warn", None, f"第 {ep_no} 集开头 {lim['recap_window']:.0f}s 内有 {len(early)} 镜解释能力（{', '.join(early)}）；跨集回顾 ≤5 秒、最多 1 镜，观众上一集已经看过")

    # G49 只说不做：场内有台词的人物镜，motion 里没有承接对方行为的动作或反应的比例过高
    talk_by_scene: dict[str, list[tuple[str, bool]]] = {}
    for sh in shots:
        if sh.get("kind", "person") != "person" or not sh.get("dialogue") or sh.get("audio_from") or sh.get("id") not in in_cut:
            continue
        acts = bool(REACT_RE.search(WEAK_ACT_RE.sub("", str(sh.get("motion") or "")))) or _waived(sh, "G49")   # 只点头/看一眼不算承接
        talk_by_scene.setdefault(sh.get("scene"), []).append((sh.get("id"), acts))
    for sc_id, rows in talk_by_scene.items():
        if _waived(scenes.get(sc_id) or {}, "G49") or len(rows) < int(lim["talk_only_min_shots"]):
            continue
        idle = [x for x, a in rows if not a]
        if len(idle) / len(rows) > float(lim["talk_only_ratio"]) + 1e-9:
            F.add("G49", "warn", None, f"{sc_id}：{len(idle)}/{len(rows)} 个对白镜只说不做（{', '.join(idle)}）；motion 里写他怎样接住对方上一个行为、做了什么改变局面（夺过、合上、后退、笑容僵住），不是轮流说明情况（storyboard-keyframes §8c）")

    # G33 风格锁定：drama.json 的 style_preset 七选一，全剧一种
    preset = project.get("style_preset")
    if not preset:
        F.add("G33", "warn", None, "drama.json 没写 style_preset；按 references/styles.md 七选一并全剧锁定（判不出用 live_modern）")
    elif preset not in STYLE_PRESETS:
        F.add("G33", "warn", None, f"style_preset「{preset}」不在风格库里：{', '.join(STYLE_PRESETS)}")

    # G36 视频头句：非真人画风不用把画面往真人拉的词（styles.md §1 视频头句表）
    head_ = project.get("video_prompt_head") or ""
    if preset and preset not in LIVE_LOOK_PRESETS and preset in STYLE_PRESETS:
        bad = [m.group(0) for m in LIVE_HEAD_RE.finditer(head_) if not NEG_BEFORE_RE.search(head_[max(0, m.start() - 30):m.start()])]
        if bad:
            F.add("G36", "warn", None, f"画风 {preset} 的 drama.json video_prompt_head 含 {sorted(set(bad))}（真人头句）；按 styles.md §1 换成本画风的视频头句和保持句")
    fx = sorted({m.group(0).lower() for m in HEAD_FX_RE.finditer(head_) if not NEG_BEFORE_RE.search(head_[max(0, m.start() - 30):m.start()])})
    shk = _neg_hit(_SHAKE_RE, head_)
    if shk:
        F.add("G54", "error", None, f"L14 drama.json video_prompt_head 含 {sorted(set(w.lower() for w in shk))}：头句会拼进每一镜，全剧镜头都在晃、锁定句全部失效；头句只写锁定机位，要手持感就在那一镜正文写 the camera shakes slightly around a fixed position")
    if fx:
        F.add("G36", "warn", None, f"drama.json video_prompt_head 含运镜/特效词 {fx}：每镜都会被加上漂移的机位和多余的粒子雾气；头句用锁定机位（Locked-off camera on a tripod; real-time speed.），运镜写进需要的那一镜")
    # G39 AI 生成标识：drama.json 要明确写 ai_label（大陆发行写标识文字，海外写 null 并记决策）
    if "ai_label" not in project.cfg:
        F.add("G39", "warn", None, "drama.json 没写 ai_label；大陆发行要在成片前 3 秒叠显式标识（例「本片由AI生成」，cut.py 自动叠），只在海外发行写 null 并记决策记录")

    # G16 剧本层：冷开场、估时、台词占比、连说
    if script_doc:
        all_lines = [ln for sc in script_doc["scenes"] for ln in sc["lines"] if ln["type"] in ("action", "dialogue")]
        head = all_lines[:3]
        if fast_craft and all_lines and not any(ln["type"] == "dialogue" for ln in head):
            F.add("G16", "warn", None, "冷开场：前 3 拍没有对白；爽剧要在前 3 拍内出现可见冲突或异常，主体在动")
        d_secs = sum(speech_seconds(ln["text"], lang, rates) for ln in all_lines if ln["type"] == "dialogue")
        a_secs = 2.5 * sum(1 for ln in all_lines if ln["type"] == "action")
        # Unknown overlap gives a range, not a falsely precise sum.
        lower, upper = max(d_secs, a_secs), d_secs + a_secs
        target = float(project.get("target_seconds") or 0)
        if target and (lower > target * 1.25 or upper < target * 0.75):
            F.add("G16", "warn", None, f"剧本粗估区间 {lower:.0f}–{upper:.0f}s，目标 {target:.0f}s；按实际并行/顺序动作逐段核对，不直接相加")
        ratio_min = float(project.get("dialogue_ratio_min", 0.35 if fast_craft else 0) or 0)
        if upper and ratio_min and d_secs / upper < ratio_min:
            F.add("G16", "warn", None, f"按顺序估计的台词占比 {d_secs / upper:.0%} 低于项目参考 {ratio_min:.0%}；先核对并行动作，不据此补台词")
        for sc in script_doc["scenes"]:
            run, prev = 0, None
            for ln in sc["lines"]:
                if ln["type"] == "dialogue":
                    run = run + 1 if ln["speaker"] == prev else 1
                    prev = ln["speaker"]
                    if fast_craft and run == 4:
                        F.add("G16", "warn", None, f"{sc['id']}：「{prev}」连说 4 句以上，中间要有对方反应或一个动作")
                elif ln["type"] == "action":
                    run, prev = 0, None
            if not any(ln["type"] == "action" for ln in sc["lines"]):
                F.add("G16", "warn", None, f"{sc['id']} 没有动作段，只有对白")
        # G37 单句超长：拆成两句、中间插对方反应或动作（为了句数多、反应快，不是少说话）
        # general 档也查（上限放宽到 1.5 倍）：不写 line_max 不等于不查
        lmax = {**(LINE_MAX_DEFAULT if fast_craft else {k: int(v * 1.5) for k, v in LINE_MAX_DEFAULT.items()}), **(project.get("line_max") or {})}
        for d in (script_dialogue if lmax else []):
            t = d["text"]
            if lang == "en" or not re.search(r"[\u3040-\u30ff\u4e00-\u9fff]", t):
                n, cap, unit = len(re.findall(r"[A-Za-z0-9']+", t)), int(lmax.get("en", 10)), "词"
            else:
                n, cap, unit = len(re.findall(r"[\w\u3040-\u30ff\u4e00-\u9fff]", t)), int(lmax.get(lang, lmax.get("zh", 15))), "字"
            if n > cap:
                F.add("G37", "warn", None, f"{d['scene']}「{d['speaker']}：{t[:14]}…」{n} {unit}，超过单句上限 {cap}；拆成两句，中间插对方反应或一个动作；同一人的两句可以放在同一个长镜头里（screenplay §4）")

    # G25 正反打：同场两个人物的朝向应互补（都朝画左 = 在看同一个画外第三者）
    for sc_id, fmap in facings_in_scene.items():
        if len(fmap) >= 2 and len(set(fmap.values())) == 1:
            sc_axis = (scenes.get(sc_id) or {}).get("axis", "")
            F.add("G25", "warn", None, f"{sc_id}：{list(fmap)} 全都面朝画{'左' if list(fmap.values())[0] == 'left' else '右'}，正反打没有互补朝向（轴线声明：{sc_axis or '无'}）")

    # G28 场景连续：同场（同一地点组）的多块底板必须互相派生（refs.json 的 refs 连通），不许各自独立生成
    for sc_id, sc in scenes.items():
        plates = [x for x in (sc.get("plates") or []) if (refs.get(x) or {}).get("kind") == "plate"]
        for group in (sc.get("plate_groups") or [plates]):
            group = [x for x in group if x in plates]
            if len(group) < 2:
                continue
            adj = {x: set() for x in group}
            for x in group:
                for y in list((refs.get(x) or {}).get("refs") or []) + ([refs[x]["same_place_as"]] if (refs.get(x) or {}).get("same_place_as") else []):
                    if y in adj:
                        adj[x].add(y); adj[y].add(x)
            seen, stack = set(), [group[0]]
            while stack:
                x = stack.pop()
                if x not in seen:
                    seen.add(x); stack.extend(adj[x] - seen)
            lonely = [x for x in group if x not in seen]
            if lonely:
                F.add("G28", "error", None, f"{sc_id}：底板 {lonely} 没有和 {group[0]} 互相派生（refs.json 的 refs 不连通），切镜会像换了地方；"
                      f"派生底板挂主底板为参考图重出，确属不同地点就在 scene 写 plate_groups 分组")

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
    light_findings(F, [sh for sh in shots if not _waived(sh, "G54")])
    prop_phrase_findings(F, shots)
    if not shots:
        F.add("G01", "error", None, "shots 为空")
    spec_lock_findings(F, data, shots)
    return F


# ---- 参考图门（G18–G20） ---------------------------------------------------------

def check_refs(project: Project) -> Findings:
    F = Findings()
    refs = project.load_refs()
    ident = {k: v for k, v in refs.items() if v.get("kind") == "identity"}
    for rid, r in refs.items():
        p = (r.get("prompt") or "")
        adversarial_findings(F, rid, r.get("adversarial_preflight"), [p])
        low = p.lower()
        if not p:
            F.add("G18", "error", rid, "缺 prompt")
            continue
        lr_findings(F, rid, "参考图 prompt", p)
        if r.get("refs"):   # 编辑类（挂了上游参考图）才查集合词
            col = sorted({m.group(1).lower() for m in _COLLECTIVE_RE.finditer(p)})
            if col:
                F.add("G54", "warn", rid, f"L27 编辑类参考图 prompt 用了集合词 {col}：模型不知道集合里有什么，逐件点名要保留/要改的东西")
        if re.search(r"[\u3040-\u30ff\u4e00-\u9fff]", p):
            F.add("G18", "error", rid, "参考图提示词必须是英文（机器字段）")
        if "no text" not in low and "no readable text" not in low:
            F.add("G18", "error", rid, "缺 no text")
        kind = r.get("kind")
        if kind == "identity":
            if not re.search(r"\bone\b", low) or re.search(r"\b(two|three|both|couple|crowd|people)\b", low):
                F.add("G18", "error", rid, "身份图必须是一个人：写 one …，不能出现 two/both/people")
            is_face = rid.endswith(FACE_SUFFIX)   # 头肩身份图：不要求全身、身高留在全身图上
            if not is_face and not any(w in low for w in ("full-body", "full body", "head-to-toe")):
                F.add("G18", "warn", rid, "身份图建议全身（full-body）")
            if not any(w in low for w in ("facing the camera", "frontal", "front view")):
                F.add("G18", "warn", rid, "身份图建议正面（facing the camera）")
            if re.search(r"\b(watch|ring|necklace|chain|bracelet|earrings?|sunglasses)\b", low) and not r.get("accessories_ok"):
                F.add("G18", "warn", rid, "身份图带饰品（表/戒指/链子），以后每镜都会跟着人物走，难以去掉；确需保留写 accessories_ok: true")
            if not r.get("subject"):
                F.add("G18", "error", rid, "身份图缺 subject（人物名，用来对账）")
            if not is_face and not re.search(r"\b\d+(?:\.\d+)?\s*(?:cm|centimet(?:re|er)s?|m|met(?:re|er)s?)\b|\b(?:tall|height)\b", low):
                F.add("G34", "warn", rid, "身份图没写身高（about 168 cm tall）；起始帧和底板才有比例依据（visual-assets §12）")
        elif kind == "plate":
            if not re.search(r"\bno (?:people|person|humans?|figures?)\b", low):
                F.add("G19", "error", rid, "底板必须写 No people")
            if not any(w in low for w in ("left", "right")):
                F.add("G19", "warn", rid, "底板建议写清画左/画右各是什么（left/right），轴线才有依据")
            if not SCALE_RE.search(p):
                F.add("G34", "warn", rid, "底板没写尺度参照（a standard 2.1 m door、handrails about 1 m high、each step about 17 cm）；模型会按随意尺寸造环境")
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
            si, sj = ident[ids[i]].get("subject"), ident[ids[j]].get("subject")
            if si and si == sj:   # 同一人物的全身图与头肩图 -FACE 本来就该相似，不算认错人
                continue
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


def _emotion_cn(em) -> str:
    if isinstance(em, dict):
        return "·".join(str(em.get(k)) for k in ("feel", "intensity", "pace", "volume") if em.get(k))
    return str(em)


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
         f"画风：{project.get('style_preset') or '未选（G33）'}（references/styles.md，全剧锁定）。",
         f"目标模型：{project.get('video_dialect')}；一镜一生成，keyframe 首帧模式；每镜生成秒数见各镜；成片取用区间按审片结果（审查/{ep}-review.json）。",
         "拍法：对白默认听者入画（SKILL 11c：两人同框或听者肩背在前景）；多人镜写死 exactly N、逐人位置朝向；"
         "单人对白写 single_reason，引用建立镜、对象方位、视线与切回承接，由 reviewer 和预演核验；自言自语或全场喊话也写具体理由。字幕与后期字全部后期叠加，生成画面里不出字。", ""]
    if data.get("notes"):
        L += ["本集说明：", *[f"- {n}" for n in data["notes"]], ""]
    for sc in data.get("scenes") or []:
        L.append(f"- 场景 {sc.get('id')}：轴线 {sc.get('axis', '未写')}；底板 {', '.join(sc.get('plates') or []) or '无'}")
        for f_ in sc.get("must_show") or []:
            if isinstance(f_, dict):
                L.append(f"  - 必拍 {f_.get('id')}（{f_.get('kind', '?')}）：{f_.get('fact', '')}；承担镜 {', '.join(f_.get('shots') or []) or '未写'}")
    L.append("")
    for sh in shots:
        sid = sh["id"]
        ft = project.chosen_take(ep, sid, "frame", review)
        fpath = project.frame_path(ep, sid, ft) if ft else None
        dl = "；".join(f"约 {d.get('at', 0.5)}s {d.get('speaker')}「{d.get('text')}」" + (f"（{_emotion_cn(d.get('emotion'))}）" if d.get("emotion") else "")
                      + (f"［读音 {'、'.join(f'{k}={v}' for k, v in d['reading'].items()) if isinstance(d['reading'], dict) else d['reading']}］" if d.get("reading") else "")
                      for d in sh.get("dialogue") or []) or "无对白"
        ov = "；".join(f"{o['kind']}（{o.get('side') or o.get('text')}）" for o in sh.get("overlay") or []) or "无"
        L += [f"## SHOT-{sid} · {sh.get('title', '')}",
              f"- 场景：{sh.get('scene')}",
              f"- 来源：{'；'.join('「' + a + '」' for a in sh.get('script_anchor') or []) or '无'}",
              f"- 时长：生成 {sh.get('seconds')} 秒",
              f"- 目的：{sh.get('duty', '')}",
              f"- 景别/机位：{sh.get('framing', '')}",
              f"- 主体与朝向：{sh.get('subject') or sh.get('kind', 'insert')}，{_facing_cn(sh.get('facing'))}"
              + (f"；视线：看{(sh.get('gaze') or {}).get('target', '?')}（画{ {'left': '左', 'right': '右'}.get((sh.get('gaze') or {}).get('direction'), (sh.get('gaze') or {}).get('direction'))}）" if isinstance(sh.get("gaze"), dict) else "")
              + (f"（{sh['gaze_reason']}）" if sh.get("gaze_reason") else ""),
              *([f"- 拆镜理由：{sh['split_reason']}"] if sh.get("split_reason") else []),
              *([f"- 快切理由：{sh['fast_cut_reason']}"] if sh.get("fast_cut_reason") else []),
              f"- 起点（冻结关键帧）：{sh.get('keyframe', '')}",
              f"- 唯一动作：{sh.get('motion', '')}",
              f"- 终点：{sh.get('end_state', '')}",
              f"- 声音：{sh.get('sound', '')}；对白：{dl}",
              f"- 后期叠加：{ov}",
              f"- 视觉依据：{'；'.join(sh.get('visual_deps') or []) or '无'}",
              f"- 连续性：{'；'.join(sh.get('continuity') or []) or '无'}",
              *([f"- 铺垫（本镜交代来处）：{'、'.join(map(str, sh['setup_for']))}"] if sh.get("setup_for") else []),
              *([f"- 需要前面已铺垫：{'、'.join(map(str, sh['requires_setup']))}"] if sh.get("requires_setup") else []),
              *([f"- 承担必拍事实：{'、'.join(map(str, sh['must_show_ids']))}"] if sh.get("must_show_ids") else []),
              *(["- 解释能力规则：是（G48 计数）"] if sh.get("explains_ability") else []),
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
