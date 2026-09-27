#!/usr/bin/env python3
"""硬约束 11d 攻防的机械部分：判定高风险镜、生成攻击任务书、检查判断栏是否写了。

高风险镜只看镜头的动作描述（motion），不看静态画面描述（keyframe）：
- 物理参与：摔、滑倒、撞、倒下/倒地、跌、打翻/翻倒、扔、砸、泼、洒；
- 人与人的身体接触：接触动词（握抓拽拉扶按盖推拍搂抱）16 字内接身体部位（手腕手背手臂胳膊肩袖口后背腰衣领头发），
  或"身体部位被握/被抓/被拽/被按"。
- 镜头写 "adversary": true / false 可强制纳入或排除（排除要写 adversary_reason）。
多人同框、承担必拍事实、新场景本身不触发：它们由 G52 adversarial_preflight 与分镜审查覆盖。
生成出来不好、要重拍的镜头（11d 第二类）由主会话按需派，不在这里自动判定。

  adversary_plan.py list   <项目> <EP>                 列出高风险镜和触发原因
  adversary_plan.py tasks  <项目> <EP> [--model TEXT]  为提示词有变化的高风险镜写 -vN.txt 与攻击任务书（只做一轮，用户 2026-09-27 定）
  adversary_plan.py status <项目> <EP>                 最新一轮清单缺「判断」一节的镜（送审前必须补齐）
"""
from __future__ import annotations

import argparse
import glob
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TEMPLATE = HERE.parent / "assets/templates/攻击任务书.md"
PHYSICAL = ("摔", "滑倒", "撞", "倒下", "倒地", "跌", "打翻", "翻倒", "扔", "砸", "泼", "洒")
BODY = "(手腕|手背|手臂|胳膊|肩|袖口|后背|腰|衣领|头发)"
CONTACT_RE = re.compile(r"(握|抓|拽|拉|扶|按|盖|推|拍|搂|抱)[^，。；→]{0,16}" + BODY + "|" + BODY + r"[^，。；→]{0,6}(被握|被抓|被拽|被按)")
JUDGE_RE = re.compile(r"^#+\s*.*判断", re.M)
MAX_ROUNDS = 1  # 用户 2026-09-27：攻防只做一轮（SKILL 放行标准与防卡死 4）


def reason(sh: dict) -> str:
    """返回触发原因；空串 = 不是高风险镜。"""
    if sh.get("adversary") is False:
        return ""
    if sh.get("adversary") is True:
        return "镜头标注 adversary:true"
    motion = sh.get("motion") or ""
    hit = [w for w in PHYSICAL if w in motion]
    if hit:
        return "物理参与：" + "、".join(hit)
    m = CONTACT_RE.search(motion)
    if m:
        return "身体接触：" + m.group(0)
    return ""


def high_risk(sh: dict) -> bool:
    return bool(reason(sh))


def _shots(project: Path, ep: str) -> list[dict]:
    return json.loads((project / ep / "shots.json").read_text(encoding="utf-8")).get("shots") or []


def _rounds(adv: Path, sid: str, kind: str) -> list[Path]:
    pat = re.compile(rf"-{kind}(\d+)\.(txt|md)$")
    files = [Path(p) for p in glob.glob(str(adv / f"{sid}-{kind}*.*")) if pat.search(p)]
    return sorted(files, key=lambda p: int(pat.search(str(p)).group(1)))


def latest_frame(project: Path, ep: str, sid: str) -> Path | None:
    fs = sorted(glob.glob(str(project / ep / "起始帧" / f"F_{sid}_t*.png")), key=lambda p: int(p.rsplit("_t", 1)[1][:-4]))
    return Path(fs[-1]) if fs else None


def status(project: Path, ep: str) -> list[str]:
    """最新一轮清单缺判断栏的文件名。"""
    adv = project / "审查/adversary"
    miss = []
    for sh in _shots(project, ep):
        if not high_risk(sh):
            continue
        rs = _rounds(adv, sh["id"], "r")
        if rs and not JUDGE_RE.search(rs[-1].read_text(encoding="utf-8")):
            miss.append(rs[-1].name)
    return miss


def tasks(project: Path, ep: str, model: str) -> list[tuple[str, Path, str]]:
    """为提示词有变化的高风险镜写 -vN.txt 与任务书；返回 [(镜号, 任务书, 角色)]。"""
    adv = project / "审查/adversary"
    adv.mkdir(parents=True, exist_ok=True)
    tmpl = TEMPLATE.read_text(encoding="utf-8")
    out = []
    for sh in _shots(project, ep):
        if not high_risk(sh):
            continue
        sid, vp = sh["id"], sh.get("video_prompt") or ""
        prev = _rounds(adv, sid, "v")
        if prev and prev[-1].read_text(encoding="utf-8") == vp:
            continue
        k = len(prev) + 1
        if k > MAX_ROUNDS:
            continue
        frame = latest_frame(project, ep, sid)
        if frame is None:
            continue
        v = adv / f"{sid}-v{k}.txt"
        v.write_text(vp, encoding="utf-8")
        goal = f"{sh.get('keyframe', '')}；动作：{sh.get('motion', '')}；必拍：{'、'.join(sh.get('must_show_ids') or [])}"[:700]
        t = (tmpl.replace("【图生视频 / 图片编辑 / 文生图】", "图生视频")
             .replace("【模型名，时长/分辨率等本次实际参数】", f"{model}，{sh.get('seconds')} 秒")
             .replace("【一两句：谁、在哪、发生什么，观众必须看清什么】", goal)
             .replace("【图生视频从这张开始 / 编辑的底图 / 参考图】", "图生视频从这张开始")
             .replace("【项目内路径】", str(frame.relative_to(project)))
             .replace("【项目内路径，审查/adversary/<ID>-vN.txt】", str(v.relative_to(project)))
             .replace("【审查/adversary/<ID>-rN.md】", f"审查/adversary/{sid}-r{k}.md"))
        task = adv / f"{sid}-task{k}.md"
        task.write_text(t, encoding="utf-8")
        out.append((sid, task, "adversary" if k == 1 else "adversary2"))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=("list", "tasks", "status"))
    ap.add_argument("project")
    ap.add_argument("episode")
    ap.add_argument("--model", default="", help="写进任务书的模型与参数，例 'MiniMax H3 base50_sol，768p，同轨生成画面与声音'")
    a = ap.parse_args(argv)
    project = Path(a.project).resolve()
    if a.cmd == "list":
        shots = _shots(project, a.episode)
        hits = [(sh["id"], reason(sh)) for sh in shots if high_risk(sh)]
        for sid, r in hits:
            print(sid, r)
        print(f"{len(hits)}/{len(shots)} 镜高风险")
    elif a.cmd == "status":
        miss = status(project, a.episode)
        for m in miss:
            print("缺判断栏", m)
        print(f"{len(miss)} 份清单缺判断栏")
        return 1 if miss else 0
    else:
        if not a.model:
            raise SystemExit("--model 必填：写本项目实际视频模型与参数（硬约束 1b，不从技能默认值猜）")
        for sid, task, role in tasks(project, a.episode, a.model):
            print(role, task.relative_to(project))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
