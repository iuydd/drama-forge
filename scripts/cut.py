#!/usr/bin/env python3
"""把审过的镜头剪成成片：取用区间、字幕、后期叠加（文字/面板/印章字）、环境声、录音垫入、响度归一。

  cut.py <项目> <EP> [--out PATH] [--no-loudnorm] [--dry-run]
  cut.py --panel-demo OUT.png [--theme tech|xianxia|scroll] [--bg 起始帧.png]   面板样式预览（不需要项目）

来源：shots.json（镜序、台词、叠加）、审查/<EP>-review.json（take、取用区间、结论）、脚本/asr_cache.json（词级时间）。
出点规则（来自实战）：
- after_last_word：说完至少留 0.5 秒；有印章字（如「嘘」）时留 hold+0.1 秒给它亮完；不超过素材长度 −0.1。
- to_end：留白结尾，出点 = 最后一个音结束 + 0.02。
- fixed：按 review 里的 in/out。full：整条（去掉最后 0.2 秒）。
- action：入点 = 首词 −0.15（无台词为 0），出点 = 动作结束 +0.2（且不早于末词 +0.3）。
- 正式剪辑先验证所选 take 的画面、听审、连续性证据与媒体/镜头指纹；pending_review/retake/未审素材不准入。
- 动作与对白保护仅使用 video_takes[n].assessment 的已审 action_window/speech_window；镜头级计划和运动能量候选不当实测。
- --draft 可组装未审素材，输出到审查/<EP>-草剪.mp4 与草剪单.md，不覆盖正式成片。
- verdict=drop 需要说明；verdict=mute 仅在不会丢失必要对白或有已审替代音源时使用。
字幕按句、按字数比例落在 ASR 首末词之间；印章字在最后一个音落下时亮起、停 hold 秒、本镜内淡出、轻微抖动。
声音：drama.json 的 beds（按场景的底噪文件，"*" 兜底）按镜铺；有镜没铺到 beds 时，整片垫一层粉噪房间音
（drama.json 的 room_tone_db，默认 −48 dBFS，null 关闭），避免数字静音。shots.json 的 sfx: [{"file", "at", "gain_db"}]
按源素材秒 at 叠音效（file 相对项目根，剪点外的丢弃）。
成片整体归一到 drama.json 的 loudness（默认 −16 LUFS）并加限幅。
系统面板（overlay kind=panel）：毛玻璃深色底、细描边外发光、圆角、标题栏图标、逐字打出、缩放/滑入/展开入场、光带扫过、
淡出、可选全息抖动与入场音效；样式在 drama.json overlays.panel（主题 tech / xianxia / scroll，见 references/styles.md §12）。
节奏：剪辑单逐镜标出短于下限的镜（对白镜 < 说完 + 0.8s 或 < 2.5s、反应镜 < 1.5s、插入镜 < 1.5s 且无 fast_cut_reason），
并统计同场平均镜长（drama.json pace）。
台词边界（有 ASR 词级时间时）：入点落在词内部、或切掉入点前 0.3 秒内开始的词（句首语气词「あれ？」）→ 入点前移到该词开始前 0.1 秒；
出点落在词内部 → 后移到词尾 + 0.1 秒；只保护属于本镜台词的词，调整写进剪辑单「取用」列。字幕以取用区间内实际存在的词为准：
句首/句尾词不在区间内就从字幕去掉（字幕是译文时不硬删，记警告要人工改），整句都不在就去掉整句。
文字排版：金额/数字/带货币符号的串、拉丁词与专名（readings、dialogue[].reading、critical_terms）折行时不拆；字幕与后期字超过两行分屏；
有 OpenCV（或测试注入 FACE_HOOK）时取叠字时段中段三帧找人脸，字幕/后期字/面板压脸就换到上/下/左/右候选位置，都压就缩小并记警告；
没有 OpenCV 时剪辑单写「未做避脸」。成片在滤镜图里 trim 到剪辑总长（不留叠字合成拖尾），尾帧定格超过 0.3 秒写警告。
必须拍清楚：shots.json scenes[].must_show 每条事实列出还在片中的承担镜；承担镜全被删、或所选 take 的 must_show_check 有 fail，正式剪辑拒绝。
元数据：成片旁写 <EP>.overlays.json（schema drama-forge/overlays/v1）：segments（每段镜号、take、成片起止、取用 in/out、台词边界注记、字幕裁剪警告）
与 overlays（每条叠字的种类、时段、文字、渲染行拆分 lines、不可拆词 protected、位置 rect/position、人脸检查结果、警告），供 final_qa.py 终验。
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import Project, ffprobe_duration, norm  # noqa: E402
from review_quality import (audio_status, cut_issues, fmt_audio, must_show_coverage, protect_interval, take_quality,
                            verified_action)

try:
    from PIL import Image, ImageDraw, ImageFilter, ImageFont
except ImportError:  # pragma: no cover
    raise SystemExit("缺少 Pillow：pip install pillow")

FONT_DEFAULTS = {
    "sub": ["/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc", "/System/Library/Fonts/PingFang.ttc",
            "/System/Library/Fonts/Hiragino Sans GB.ttc", "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
            "/usr/share/fonts/noto-cjk/NotoSansCJK-Bold.ttc", "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"],
    "stamp": ["/System/Library/AssetsV2/com_apple_MobileAsset_Font8/*/AssetData/Kyokasho.ttc",
              "/System/Library/AssetsV2/com_apple_MobileAsset_Font8/*/AssetData/ToppanBunkyuMidashiMinchoStdN-ExtraBold.otf",
              "/usr/share/fonts/opentype/noto/NotoSerifCJK-Black.ttc", "/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc"],
}
FILTERS = {"phone": "highpass=f=350,lowpass=f=3200,aecho=0.8:0.6:40:0.25,volume=0.9",
           "hall": "highpass=f=120,aecho=0.8:0.7:120|240:0.35|0.2,volume=1.1",
           "glass": "lowpass=f=900,volume=0.5",   # 隔玻璃门/墙的闷声：镜判 mute，再用 audio_from 垫回本镜原声
           "none": "volume=1.0"}


def find_font(cands: list[str]) -> str | None:
    for f in cands:
        if not f:
            continue
        for g in (glob.glob(f) if "*" in f else [f]):
            if os.path.exists(g):
                return g
    return None


def lufs(path: Path) -> float:
    e = subprocess.run(["ffmpeg", "-i", str(path), "-af", "ebur128", "-f", "null", "-"], capture_output=True, text=True).stderr
    m = re.findall(r"I:\s+(-?[0-9.]+) LUFS", e)
    return float(m[-1]) if m else -23.0


# ---- 文字排版：金额/数字/专名不断行 -------------------------------------------------------------
# 金额与数字串（¥3,000,000、300万円、3.5%、十件）、拉丁词、专名（drama.json readings、dialogue[].reading、critical_terms）
# 在折行时当作不可分的一个词：整体放不进本行就整体换到下一行；单个词比一行还宽时独占一行并记警告。
_NUM = r"[0-9０-９][0-9０-９,，.．]*"
_KNUM = r"[〇零一二三四五六七八九十百千万萬億亿兆两]"
_UNIT = r"(?:万|萬|億|亿|千|百|兆)"
_TAIL = r"(?:円|元|ドル|美元|块|塊|%|％|倍|件|个|個|人|年|歳|岁|秒|分|点|枚|本|つ)"
NUMBER_RE = re.compile(rf"[¥￥$€£]\s?{_NUM}(?:\s?{_UNIT})*(?:\s?{_TAIL})?"
                       rf"|{_NUM}(?:\s?{_UNIT})*(?:\s?{_TAIL})?"
                       rf"|{_KNUM}{{2,}}{_TAIL}?|{_KNUM}{_TAIL}"
                       r"|[A-Za-z][A-Za-z'’\-]*")
NO_LINE_START = set("、。，,．.！!？?…」』）)】〕ー〜~：:；;")
BREAK_AFTER = set("、。？！…　 ,.?!，；;")


def protected_spans(text: str, terms=()) -> list[tuple[int, int]]:
    """需要整体保留在同一行的片段 [start, end)：金额/数字、拉丁词、专名。重叠的合并。"""
    spans = [m.span() for m in NUMBER_RE.finditer(text or "") if m.end() - m.start() > 1]
    for term in sorted({t for t in terms or () if t and len(t) > 1}, key=len, reverse=True):
        start = 0
        while True:
            i = text.find(term, start)
            if i < 0:
                break
            spans.append((i, i + len(term)))
            start = i + 1
    spans.sort()
    merged: list[list[int]] = []
    for s, e in spans:
        if merged and s < merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    return [(s, e) for s, e in merged]


def protected_tokens(text: str, terms=()) -> list[str]:
    """文本里必须不断行的词（终验按它检查断行）。拉丁词不列入：它们断了也看得出来，只在折行时照顾。"""
    out = []
    for s, e in protected_spans(text, terms):
        tok = text[s:e].strip()
        if tok and not re.fullmatch(r"[A-Za-z][A-Za-z'’\-]*", tok):
            out.append(tok)
    return out


def _atoms(text: str, terms=()) -> list[str]:
    spans = protected_spans(text, terms)
    atoms, i = [], 0
    for s, e in spans:
        atoms.extend(text[i:s])
        atoms.append(text[s:e])
        i = e
    atoms.extend(text[i:])
    return atoms


def wrap_lines(text: str, f, maxw: int, terms=(), warnings: list | None = None) -> list[str]:
    """按像素宽折行，金额/数字/专名当作不可分的词；行首不放句读。返回行列表。"""
    d = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    lines: list[str] = []
    cur: list[str] = []
    for atom in _atoms(text, terms):
        if cur and d.textlength("".join(cur) + atom, font=f) > maxw and atom not in NO_LINE_START:
            cut_at = max((k + 1 for k, a in enumerate(cur) if a in BREAK_AFTER), default=0)
            if cut_at <= 0 or len("".join(cur[cut_at:])) > 12:
                cut_at = len(cur)
            lines.append("".join(cur[:cut_at]))
            cur = cur[cut_at:]
        cur.append(atom)
        if len(atom) > 1 and d.textlength(atom, font=f) > maxw and warnings is not None:
            warnings.append(f"「{atom}」比一行还宽，只能独占一行")
    lines.append("".join(cur))
    return [ln for ln in lines if ln != ""] or [""]


def wrap(text: str, f, maxw: int, terms=()) -> str:
    return "\n".join(wrap_lines(text, f, maxw, terms))


def layout_text(text: str, size: int, font: str, maxw: int, terms=(), warnings: list | None = None) -> list[str]:
    f = ImageFont.truetype(font, size)
    out = []
    for line in (text or "").split("\n"):   # 面板多行：逐行折行
        out.extend(wrap_lines(line, f, maxw, terms, warnings))
    return out


def text_png(text: str, path: Path, size: int, font: str, maxw: int, terms=()) -> tuple[int, int]:
    f = ImageFont.truetype(font, size)
    text = "\n".join(layout_text(text, size, font, maxw, terms))
    bb = ImageDraw.Draw(Image.new("RGBA", (1, 1))).multiline_textbbox((0, 0), text, font=f, stroke_width=5, spacing=10, align="center")
    bb = [int(round(v)) for v in bb]
    im = Image.new("RGBA", (bb[2] - bb[0] + 40, bb[3] - bb[1] + 36), (0, 0, 0, 0))
    sh = Image.new("RGBA", im.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).multiline_text((22 - bb[0], 22 - bb[1]), text, font=f, fill=(0, 0, 0, 200), stroke_width=5,
                                      stroke_fill=(0, 0, 0, 200), spacing=10, align="center")
    im = Image.alpha_composite(im, sh.filter(ImageFilter.GaussianBlur(4)))
    ImageDraw.Draw(im).multiline_text((18 - bb[0], 16 - bb[1]), text, font=f, fill=(255, 255, 255, 255),
                                      stroke_width=4 if size > 40 else 5, stroke_fill=(0, 0, 0, 255), spacing=10, align="center")
    im.save(path)
    return im.size


def stamp_png(cfg: dict, path: Path, font: str) -> tuple[int, int]:
    f = ImageFont.truetype(font, int(cfg.get("size", 300)))
    glyph = cfg.get("glyph", "!")
    pad = 80
    bb = ImageDraw.Draw(Image.new("RGBA", (1, 1))).textbbox((0, 0), glyph, font=f)
    size = (bb[2] - bb[0] + pad * 2, bb[3] - bb[1] + pad * 2)
    org = (pad - bb[0], pad - bb[1])
    r, g, b = cfg.get("color", [215, 0, 18])
    im = Image.new("RGBA", size, (0, 0, 0, 0))
    if cfg.get("glow", True):
        glow = Image.new("RGBA", size, (0, 0, 0, 0))
        ImageDraw.Draw(glow).text(org, glyph, font=f, fill=(min(255, r + 40), g + 20, b + 12, 255))
        im = Image.alpha_composite(im, glow.filter(ImageFilter.GaussianBlur(28)))
        im = Image.alpha_composite(im, glow.filter(ImageFilter.GaussianBlur(8)))
    core = Image.new("RGBA", size, (0, 0, 0, 0))
    ImageDraw.Draw(core).text(org, glyph, font=f, fill=(r, g, b, 235))
    im = Image.alpha_composite(im, core)
    alpha = float(cfg.get("alpha", 0.88))
    im.putalpha(im.getchannel("A").point(lambda a: int(a * alpha)))
    im.save(path)
    return size


# ---- 系统面板（overlay kind=panel）：玻璃底 + 描边外发光 + 标题栏 + 逐字打出 + 入场动画 + 入场音效 ----------
# 样式来源：drama.json overlays.panel（覆盖主题预设），单条 overlay 可再覆盖 title/theme/position/width/accent/icon。
PANEL_DEFAULT = {
    "theme": "tech",
    "accent": [0, 229, 255],        # 主色：冷青
    "accent2": [70, 130, 255],      # 副色：电蓝（角标、分隔线尾）
    "fill": [6, 14, 30], "fill_alpha": 0.58,   # 深色半透明底
    "text_color": [226, 250, 255],
    "title": "SYSTEM", "icon": "hex",          # icon: hex | rune | seal | none
    "position": "top_left",                    # top_left | top_right | top | center | left | right，或 [x, y]（面板中心的画面比例）
    "width": 0.36,                             # 面板宽 = 画宽 × width
    "font_size": 0,                            # 0 = 画高 / 26
    "radius": 14, "border": 2, "glow": 16,     # 圆角、描边粗细、外发光模糊半径（0 关）
    "glass": True, "glass_blur": 14,           # 毛玻璃：面板下的画面模糊
    "scanlines": True, "sweep": True,          # 细扫描线、光带扫过
    "enter": 0.32, "enter_mode": "scale",      # 入场时长（0.25–0.4s）与方式：scale | slide | unroll
    "exit": 0.25,                              # 出场淡出
    "type_cps": 22, "cursor": True,            # 逐字打出速度（字/秒，0 = 一次出全）、打字光标
    "hologram": True,                          # 轻微全息抖动
    "sfx": True, "sfx_file": None, "sfx_gain_db": -10,   # 入场音效：sfx_file 优先，否则程序生成
    "font": [], "title_font": [],
}
PANEL_THEMES = {
    "tech": {},   # 都市科技：冷青电蓝、扫描线、HUD 角标
    "xianxia": {"accent": [255, 205, 110], "accent2": [120, 255, 205], "fill": [18, 12, 6], "fill_alpha": 0.5,
                "text_color": [255, 246, 222], "title": "灵识", "icon": "rune", "scanlines": False, "hologram": False,
                "type_cps": 14, "cursor": False, "radius": 18, "serif": True},   # 修仙：金光玉色、符文环、无扫描线
    "scroll": {"accent": [118, 70, 28], "accent2": [178, 36, 28], "fill": [236, 221, 182], "fill_alpha": 0.95,
               "text_color": [58, 32, 12], "title": "", "icon": "seal", "glass": False, "glow": 0, "scanlines": False,
               "sweep": False, "hologram": False, "enter_mode": "unroll", "enter": 0.4, "type_cps": 10, "cursor": False,
               "radius": 6, "serif": True},   # 古风卷轴：宣纸底、朱印、横向展开
}
# 面板字体按文字语种挑：含假名用日文字体；纯汉字（简体中文）先用中文字体，日文字体缺简体字形会出方块
PANEL_FONTS = {"ja": ["/System/Library/Fonts/ヒラギノ角ゴシック W4.ttc", "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc"],
               "zh": ["/System/Library/Fonts/PingFang.ttc", "/System/Library/Fonts/Hiragino Sans GB.ttc",
                      "/System/Library/Fonts/STHeiti Medium.ttc"],
               "any": ["/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc"]}
PANEL_SERIF_FONTS = {"ja": ["/System/Library/Fonts/ヒラギノ明朝 ProN.ttc"],
                     "zh": ["/System/Library/Fonts/Supplemental/Songti.ttc", "/System/Library/Fonts/Songti.ttc"],
                     "any": ["/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc", "/usr/share/fonts/noto-cjk/NotoSerifCJK-Regular.ttc"]}


def _panel_fonts(text: str, serif: bool) -> list[str]:
    lang = "ja" if re.search(r"[\u3040-\u30ff]", text or "") else "zh"
    other = "zh" if lang == "ja" else "ja"
    table = PANEL_SERIF_FONTS if serif else PANEL_FONTS
    plain = PANEL_FONTS
    return table[lang] + table["any"] + plain[lang] + plain["any"] + table[other] + plain[other]
MONO_FONTS = ["/System/Library/Fonts/SFNSMono.ttf", "/System/Library/Fonts/Menlo.ttc",
              "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", "/usr/share/fonts/dejavu/DejaVuSansMono.ttf"]
# 入场音效（程序生成，免素材）：tech 电子「叮」、xianxia 钟磬、scroll 纸声
PANEL_SFX = {
    "tech": ("aevalsrc='0.30*sin(2*PI*1760*t)*exp(-13*t)+0.22*sin(2*PI*2637*t)*exp(-19*t)+0.16*sin(2*PI*(900+5200*t)*t)*exp(-40*t)'"
             ":s=48000:d=0.45"),
    "xianxia": "aevalsrc='0.28*sin(2*PI*1046.5*t)*exp(-3.5*t)+0.18*sin(2*PI*1568*t)*exp(-4.5*t)+0.1*sin(2*PI*2093*t)*exp(-6*t)':s=48000:d=1.2",
    "scroll": "anoisesrc=d=0.5:c=brown:a=0.6:seed=7,highpass=f=300,lowpass=f=4000,afade=t=in:d=0.08",
}


def panel_cfg(overlays: dict | None, ov: dict | None = None) -> dict:
    user = dict((overlays or {}).get("panel") or {})
    ov = ov or {}
    theme = ov.get("theme") or user.get("theme") or PANEL_DEFAULT["theme"]
    cfg = {**PANEL_DEFAULT, **PANEL_THEMES.get(theme, {}), **user}
    cfg.update({k: ov[k] for k in ("title", "position", "width", "accent", "icon") if k in ov})
    cfg["theme"] = theme
    return cfg


def _ease_out(x: float) -> float:
    x = min(1.0, max(0.0, x))
    return 1 - (1 - x) ** 3


def _rgba(c, a: float = 1.0) -> tuple:
    return (int(c[0]), int(c[1]), int(c[2]), int(max(0, min(255, a * 255))))


def _panel_icon(d: "ImageDraw.ImageDraw", kind: str, cx: float, cy: float, r: float, cfg: dict) -> None:
    import math
    acc, acc2 = cfg["accent"], cfg["accent2"]
    if kind == "hex":
        pts = [(cx + r * math.cos(math.pi / 6 + k * math.pi / 3), cy + r * math.sin(math.pi / 6 + k * math.pi / 3)) for k in range(6)]
        d.polygon(pts, outline=_rgba(acc), width=2)
        d.ellipse([cx - r * 0.32, cy - r * 0.32, cx + r * 0.32, cy + r * 0.32], fill=_rgba(acc2))
    elif kind == "rune":
        d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=_rgba(acc), width=2)
        d.ellipse([cx - r * 0.55, cy - r * 0.55, cx + r * 0.55, cy + r * 0.55], outline=_rgba(acc2), width=1)
        for k in range(8):
            a = k * math.pi / 4
            d.line([(cx + r * 0.62 * math.cos(a), cy + r * 0.62 * math.sin(a)), (cx + r * 0.95 * math.cos(a), cy + r * 0.95 * math.sin(a))], fill=_rgba(acc), width=1)
    elif kind == "seal":
        d.rounded_rectangle([cx - r, cy - r, cx + r, cy + r], radius=r * 0.2, fill=_rgba(acc2, 0.92))
        d.rectangle([cx - r * 0.62, cy - r * 0.62, cx + r * 0.62, cy + r * 0.62], outline=(250, 236, 220, 230), width=2)


def panel_geometry(text: str, cfg: dict, W: int, H: int) -> dict:
    """面板的字体、折行与落位（不画图）：cut 避脸时先用它算各候选位置的面板框。"""
    fs = int(cfg.get("font_size") or max(20, H // 26))
    serif = bool(cfg.get("serif"))
    body_font = find_font(list(cfg.get("font") or []) + _panel_fonts(f"{text}{cfg.get('title') or ''}", serif) + FONT_DEFAULTS["sub"])
    if not body_font:
        raise FileNotFoundError("面板找不到字体")
    title = str(cfg.get("title") or "")
    latin_title = bool(title) and all(ord(ch) < 128 for ch in title)
    title_font = find_font(list(cfg.get("title_font") or []) + (MONO_FONTS if latin_title else []) + [body_font]) or body_font
    f_body = ImageFont.truetype(body_font, fs)
    pw = int(W * float(cfg.get("width", 0.36))) // 2 * 2
    pad = int(fs * 0.8)
    lines = []
    for ln in (text or "").split("\n"):
        lines.extend(wrap_lines(ln, f_body, pw - 2 * pad, cfg.get("_terms") or ()))
    line_h = int(fs * 1.5)
    icon = cfg.get("icon") or "none"
    title_h = int(fs * 1.25) if (title or icon != "none") else 0
    sep = int(fs * 0.55) if title_h else 0
    ph = (pad + title_h + sep + len(lines) * line_h + int(pad * 0.7)) // 2 * 2
    # 落位（面板本体左上角，视频坐标，取偶数方便 yuv 裁切）
    pos, m = cfg.get("position") or "top_left", int(W * 0.035)
    top = int(H * 0.09)
    if isinstance(pos, (list, tuple)) and len(pos) == 2:
        X, Y = int(W * float(pos[0]) - pw / 2), int(H * float(pos[1]) - ph / 2)
    else:
        X = {"top_left": m, "left": m, "top_right": W - m - pw, "right": W - m - pw}.get(pos, (W - pw) // 2)
        Y = {"top_left": top, "top_right": int(H * 0.13), "top": top, "left": (H - ph) // 2, "right": (H - ph) // 2}.get(pos, int((H - ph) / 2 - H * 0.05))
    X, Y = max(0, min(W - pw, X)) // 2 * 2, max(0, min(H - ph, Y)) // 2 * 2
    return {"fs": fs, "body_font": body_font, "title_font": title_font, "title": title, "latin_title": latin_title,
            "pw": pw, "ph": ph, "pad": pad, "lines": lines, "line_h": line_h, "icon": icon, "title_h": title_h, "sep": sep,
            "X": X, "Y": Y}


def render_panel_frames(text: str, cfg: dict, dur: float, W: int, H: int, fps: int, out_dir: Path, prefix: str) -> dict:
    """把一条面板画成逐帧 PNG（含入场、逐字、光带、抖动、出场），返回画布大小与落位。"""
    import math
    import random
    g = panel_geometry(text, cfg, W, H)
    fs, body_font, title_font, title, latin_title = g["fs"], g["body_font"], g["title_font"], g["title"], g["latin_title"]
    pw, ph, pad, lines, line_h, icon, title_h, sep, X, Y = (g[k] for k in ("pw", "ph", "pad", "lines", "line_h", "icon", "title_h", "sep", "X", "Y"))
    f_body = ImageFont.truetype(body_font, fs)
    f_title = ImageFont.truetype(title_font, max(12, int(fs * 0.72)))
    G = int(float(cfg.get("glow") or 0) * 1.6) + 10          # 画布四周给外发光和抖动留的边
    cw, ch = pw + 2 * G, ph + 2 * G
    rad = int(cfg.get("radius", 14))
    body = [G, G, G + pw - 1, G + ph - 1]

    acc, acc2 = cfg["accent"], cfg["accent2"]
    mask = Image.new("L", (cw, ch), 0)
    ImageDraw.Draw(mask).rounded_rectangle(body, radius=rad, fill=255)
    base = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    shadow = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))   # 投影：亮背景上也能把面板托起来
    ImageDraw.Draw(shadow).rounded_rectangle([body[0] + 2, body[1] + 5, body[2] + 2, body[3] + 5], radius=rad, fill=(0, 0, 0, 110))
    base = Image.alpha_composite(base, shadow.filter(ImageFilter.GaussianBlur(9)))
    if float(cfg.get("glow") or 0) > 0:   # 外发光：描边糊开两层
        gl = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        ImageDraw.Draw(gl).rounded_rectangle(body, radius=rad, outline=_rgba(acc), width=4)
        wide = gl.filter(ImageFilter.GaussianBlur(float(cfg["glow"])))
        base = Image.alpha_composite(Image.alpha_composite(base, wide), wide)
        base = Image.alpha_composite(base, gl.filter(ImageFilter.GaussianBlur(float(cfg["glow"]) / 3)))
    # 面板内部分层画、逐层 alpha_composite（在同一层上画半透明线会直接改写透明度，出现条纹）
    inner = Image.new("RGBA", (cw, ch), _rgba(cfg["fill"], float(cfg.get("fill_alpha", 0.56))))
    deco = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    dd = ImageDraw.Draw(deco)
    for yy in range(G, G + int(ph * 0.45)):   # 顶部一层主色微光，像玻璃反光
        dd.line([(G, yy), (G + pw, yy)], fill=_rgba(acc, 0.14 * (1 - (yy - G) / (ph * 0.45))))
    inner = Image.alpha_composite(inner, deco)
    if cfg.get("scanlines"):
        scan = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        ds = ImageDraw.Draw(scan)
        for yy in range(G, G + ph, 4):
            ds.line([(G, yy), (G + pw, yy)], fill=_rgba(acc, 0.06))
        inner = Image.alpha_composite(inner, scan)
    if cfg.get("theme") == "scroll":   # 卷轴：左右两根轴
        rod = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        for x0 in (G, G + pw - int(fs * 0.45)):
            ImageDraw.Draw(rod).rectangle([x0, G, x0 + int(fs * 0.45), G + ph], fill=_rgba([96, 58, 24], 0.95))
        inner = Image.alpha_composite(inner, rod)
    inner.putalpha(Image.composite(inner.getchannel("A"), Image.new("L", (cw, ch), 0), mask))
    base = Image.alpha_composite(base, inner)
    top_layer = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))   # 描边、角标、标题栏画在透明层上再叠
    d = ImageDraw.Draw(top_layer)
    d.rounded_rectangle(body, radius=rad, outline=_rgba(acc, 0.9), width=int(cfg.get("border", 2)))
    if cfg.get("theme") == "tech":   # HUD 角标
        L_ = int(fs * 0.7)
        for (x0, y0, sx, sy) in ((body[0] - 5, body[1] - 5, 1, 1), (body[2] + 5, body[1] - 5, -1, 1), (body[0] - 5, body[3] + 5, 1, -1), (body[2] + 5, body[3] + 5, -1, -1)):
            d.line([(x0, y0), (x0 + sx * L_, y0)], fill=_rgba(acc2), width=2)
            d.line([(x0, y0), (x0, y0 + sy * L_)], fill=_rgba(acc2), width=2)
    if title_h:
        cy = G + pad * 0.6 + title_h / 2
        ix = G + pad
        if icon != "none":
            _panel_icon(d, icon, ix + title_h * 0.36, cy, title_h * 0.34, cfg)
            ix += title_h * 0.9
        if title:
            x_ = ix
            for chh in title:   # 标题字距拉开一点
                d.text((x_, cy), chh, font=f_title, fill=_rgba(acc), anchor="lm")
                x_ += d.textlength(chh, font=f_title) + (fs * 0.12 if latin_title else fs * 0.05)
        if cfg.get("theme") == "tech":
            for k in range(3):
                bx = G + pw - pad - k * fs * 0.42
                d.rectangle([bx - fs * 0.22, cy - fs * 0.11, bx, cy + fs * 0.11], fill=_rgba(acc2 if k else acc, 0.85 - 0.25 * k))
        sy_ = int(G + pad * 0.6 + title_h + sep * 0.45)
        x_end = G + pw - pad
        for xx in range(G + pad, x_end):   # 分隔线：主色渐隐
            d.point((xx, sy_), fill=_rgba(acc, 0.85 * (1 - (xx - G - pad) / max(1, x_end - G - pad)) + 0.1))
    base = Image.alpha_composite(base, top_layer)
    text_top = G + pad * 0.6 + title_h + sep

    total = sum(len(x) for x in lines)
    enter, exit_ = float(cfg.get("enter", 0.32)), float(cfg.get("exit", 0.25))
    cps = float(cfg.get("type_cps") or 0)
    if cps > 0:
        cps = max(cps, total / max(0.4, (dur - enter - exit_) * 0.4))   # 可见时长的前 40% 内打完，留时间读
    text_cache: dict[tuple[int, bool], Image.Image] = {}

    def text_layer(n: int, cursor_on: bool) -> Image.Image:
        key = (n, cursor_on)
        if key in text_cache:
            return text_cache[key]
        lay = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        dl = ImageDraw.Draw(lay)
        left, y, cx_, cy_ = n, text_top, G + pad, text_top
        for ln in lines:
            part = ln[:max(0, left)]
            left -= len(ln)
            dl.text((G + pad, y), part, font=f_body, fill=_rgba(cfg["text_color"]))
            if part:
                cx_, cy_ = G + pad + dl.textlength(part, font=f_body), y
            if left <= 0:
                break
            y += line_h
        if cursor_on:
            dl.rectangle([cx_ + 3, cy_ + fs * 0.12, cx_ + 3 + fs * 0.5, cy_ + fs * 1.05], fill=_rgba(acc, 0.85))
        if cfg.get("theme") == "tech" or cfg.get("theme") == "xianxia":   # 字的微光
            glow_ = lay.filter(ImageFilter.GaussianBlur(3))
            lay = Image.alpha_composite(glow_, lay)
        text_cache[key] = lay
        return lay

    rnd = random.Random(crc_seed(prefix))
    n_frames = max(1, int(math.ceil(dur * fps)) + 1)
    for i in range(n_frames):
        t = i / fps
        p = _ease_out(t / enter) if enter > 0 else 1.0
        typing_t = max(0.0, t - enter * 0.8)
        n = total if cps <= 0 else min(total, int(typing_t * cps))
        cursor = bool(cfg.get("cursor")) and (n < total or typing_t * cps < total + cps * 0.6) and int(t * 4) % 2 == 0
        frame = Image.alpha_composite(base, text_layer(n, cursor))
        if cfg.get("sweep"):   # 光带：入场扫一遍，之后每 3 秒淡淡扫一遍
            ph_t = None
            if enter * 0.3 <= t <= enter + 0.35:
                ph_t, amp = (t - enter * 0.3) / (enter * 0.7 + 0.35), 0.34
            elif t > enter + 0.35 and ((t - enter - 0.35) % 3.0) < 0.5:
                ph_t, amp = ((t - enter - 0.35) % 3.0) / 0.5, 0.12
            if ph_t is not None:
                band = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
                by = G + ph * ph_t
                db = ImageDraw.Draw(band)   # 透明层上画，直接写像素即可
                hh = fs * 1.1
                for yy in range(int(by - hh), int(by + hh)):
                    db.line([(G, yy), (G + pw, yy)], fill=(255, 255, 255, int(255 * amp * (1 - abs(yy - by) / hh))))
                band.putalpha(Image.composite(band.getchannel("A"), Image.new("L", (cw, ch), 0), mask))
                frame = Image.alpha_composite(frame, band)
        alpha = p
        if t > dur - exit_:
            alpha *= max(0.0, (dur - t) / exit_)
        mode = cfg.get("enter_mode", "scale")
        out = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        if mode == "scale" and p < 1:
            sc = 0.86 + 0.14 * p
            im = frame.resize((max(1, int(cw * sc)), max(1, int(ch * sc))), Image.BICUBIC)
            out.paste(im, ((cw - im.width) // 2, (ch - im.height) // 2))
        elif mode == "slide" and p < 1:
            out.paste(frame, (0, int((1 - p) * (G - 2))))
        elif mode == "unroll" and p < 1:
            half = int(cw * p / 2)
            win = Image.new("L", (cw, ch), 0)
            ImageDraw.Draw(win).rectangle([cw // 2 - half, 0, cw // 2 + half, ch], fill=255)
            out = Image.composite(frame, out, win)
        else:
            out = frame
        if cfg.get("hologram") and p >= 1 and rnd.random() < 0.08:   # 全息抖动：偶尔横移 1–2 像素、闪一下
            sh_ = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
            sh_.paste(out, (rnd.choice([-2, -1, 1, 2]), 0))
            out, alpha = sh_, alpha * 0.86
        if alpha < 0.999:
            out.putalpha(out.getchannel("A").point(lambda a, k=alpha: int(a * k)))
        out.save(out_dir / f"{prefix}_{i:04d}.png")
    pm = mask.crop((G, G, G + pw, G + ph))
    pm.save(out_dir / f"{prefix}_mask.png")
    return {"canvas": (cw, ch), "pad": G, "x": X, "y": Y, "w": pw, "h": ph, "frames": n_frames, "lines": lines,
            "pattern": str(out_dir / f"{prefix}_%04d.png"), "mask": str(out_dir / f"{prefix}_mask.png")}


def crc_seed(s: str) -> int:
    import zlib
    return zlib.crc32(s.encode("utf-8"))


def panel_sfx(cfg: dict, tmp: Path, root: Path | None = None) -> Path | None:
    """面板入场音效：sfx_file 优先；否则按主题用 ffmpeg lavfi 现场生成。生成不了就返回 None（留钩子、不报错）。"""
    if not cfg.get("sfx"):
        return None
    if cfg.get("sfx_file"):
        p = Path(cfg["sfx_file"])
        p = p if p.is_absolute() or root is None else root / p
        if p.exists():
            return p
        print("panel sfx_file missing; 改用程序生成", p)
    out = tmp / f"panel_sfx_{cfg.get('theme', 'tech')}.wav"
    if out.exists():
        return out
    spec = PANEL_SFX.get(cfg.get("theme"), PANEL_SFX["tech"])
    r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", spec, "-af", "aformat=channel_layouts=stereo,areverse,afade=t=in:d=0.05,areverse",
                        "-ar", "48000", str(out)], capture_output=True, text=True)
    if r.returncode != 0 or not out.exists():
        print("panel sfx 生成失败，跳过（可在 overlays.panel.sfx_file 指定音效文件）", r.stderr.strip()[:120])
        return None
    return out


def add_panel(k: int, s: float, e_: float, text: str, cfg: dict, tmp: Path, W: int, H: int, fps: int, total: float,
              inputs: list, f: list, last: str, n_in: int) -> tuple[str, int]:
    """往 filter_complex 里加一条面板：毛玻璃（裁下面板区域模糊、按圆角遮罩淡入淡出）+ 逐帧面板序列。"""
    info = render_panel_frames(text, cfg, max(0.5, e_ - s), W, H, fps, tmp, f"panel{k}")
    X, Y, pw, ph, G = info["x"], info["y"], info["w"], info["h"], info["pad"]
    enter, exit_ = float(cfg.get("enter", 0.32)), float(cfg.get("exit", 0.25))
    if cfg.get("glass"):
        blur = max(2, min(int(cfg.get("glass_blur", 14)), ph // 4 - 1, pw // 4 - 1))
        inputs += ["-loop", "1", "-framerate", str(fps), "-t", f"{total + 1:.2f}", "-i", info["mask"]]
        mi, n_in = n_in, n_in + 1
        f.append(f"{last}split=2[pm{k}][pc{k}]")
        f.append(f"[pc{k}]crop={pw}:{ph}:{X}:{Y},boxblur=luma_radius={blur}:luma_power=2,eq=brightness=-0.05,format=rgba[pg{k}]")
        f.append(f"[{mi}:v]format=gray,scale={pw}:{ph}[pmk{k}]")
        f.append(f"[pg{k}][pmk{k}]alphamerge,fade=t=in:st={s:.3f}:d={enter:.3f}:alpha=1,"
                 f"fade=t=out:st={max(s, e_ - exit_):.3f}:d={exit_:.3f}:alpha=1[pgl{k}]")
        f.append(f"[pm{k}][pgl{k}]overlay=x={X}:y={Y}:enable='between(t,{s:.3f},{e_:.3f})'[pb{k}]")
        last = f"[pb{k}]"
    inputs += ["-framerate", str(fps), "-start_number", "0", "-i", info["pattern"]]
    pi, n_in = n_in, n_in + 1
    f.append(f"[{pi}:v]format=rgba,setpts=PTS-STARTPTS+{s:.3f}/TB[pp{k}]")
    f.append(f"{last}[pp{k}]overlay=x={X - G}:y={Y - G}:eof_action=pass:enable='between(t,{s:.3f},{e_:.3f})'[w{k}]")
    return f"[w{k}]", n_in


def panel_demo(out_png: Path, theme: str | None = "tech", text: str | None = None, W: int = 1344, H: int = 768, fps: int = 24,
               overlays: dict | None = None, keep_video: Path | None = None, bg_image: Path | None = None) -> dict:
    """面板渲染测试 / 预览：背景（lavfi 合成，或给一张起始帧）→ 叠一条面板 → 抽出面板前帧、入场帧、中间帧。返回帧路径与像素差。"""
    tmp = Path(tempfile.mkdtemp(prefix="panel_demo_"))
    dur, s, e_ = 4.0, 0.5, 3.8
    bg = tmp / "bg.mp4"
    src = (["-loop", "1", "-framerate", str(fps), "-t", f"{dur}", "-i", str(bg_image)] if bg_image
           else ["-f", "lavfi", "-i", f"testsrc2=s={W}x{H}:r={fps}:d={dur}"])
    vf = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}" if bg_image else "boxblur=18:2,eq=brightness=-0.12:saturation=0.55"
    subprocess.run(["ffmpeg", "-y", "-v", "error", *src, "-vf", vf, "-t", f"{dur}", "-pix_fmt", "yuv420p", "-c:v", "libx264", "-crf", "18", str(bg)], check=True)
    cfg = panel_cfg(overlays or {"panel": {"theme": theme or "tech"}}, {"theme": theme} if theme else None)
    theme = cfg["theme"]
    text = text or {"tech": "检测到谎言\n可信度 12% · 剩余次数 2", "xianxia": "灵识感应：此人体内有魔气\n修为 · 筑基中期",
                    "scroll": "圣旨到\n即日起入宫听宣"}.get(theme, "SYSTEM")
    inputs, f = ["-i", str(bg)], []
    last, n_in = add_panel(0, s, e_, text, cfg, tmp, W, H, fps, dur, inputs, f, "[0:v]", 1)
    vid = keep_video or tmp / "demo.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", *inputs, "-filter_complex", ";".join(f), "-map", last, "-t", f"{dur}",
                    "-pix_fmt", "yuv420p", "-c:v", "libx264", "-crf", "16", str(vid)], check=True)
    shots = {}
    for name, t in (("before", 0.2), ("enter", s + 0.12), ("mid", (s + e_) / 2)):
        p = tmp / f"{name}.png"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{t:.3f}", "-i", str(vid), "-frames:v", "1", str(p)], check=True)
        shots[name] = p
    out_png = Path(out_png)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(shots["mid"], out_png)

    def diff(a: Path, b: Path) -> float:
        from PIL import ImageChops, ImageStat
        return sum(ImageStat.Stat(ImageChops.difference(Image.open(a).convert("RGB"), Image.open(b).convert("RGB"))).mean) / 3
    return {"frame": out_png, "video": vid, "before_vs_mid": diff(shots["before"], shots["mid"]),
            "enter_vs_mid": diff(shots["enter"], shots["mid"]), "frames": {k: str(v) for k, v in shots.items()}}


def align_phrases(words: list, phrases: list[str]) -> list[tuple[float, float] | None]:
    """把若干句台词按顺序对到 ASR 词序列上（规范化后累计匹配）；对不上的返回 None。words = [(start, end, text)]。"""
    return [(words[ij[0]][0], words[ij[1]][1]) if ij else None for ij in align_phrase_indices(words, phrases)]


def align_phrase_indices(words: list, phrases: list[str]) -> list[tuple[int, int] | None]:
    """同 align_phrases，但返回每句对上的词下标 (i, j)（含两端）。"""
    from common import norm
    out: list[tuple[int, int] | None] = []
    texts = [norm(w[2]) for w in words]
    pos = 0
    for ph in phrases:
        target = norm(ph)
        if not target or pos >= len(words):
            out.append(None)
            continue
        found = None
        for strict in (True, False):  # 先要求起始词本身属于这句台词（跳过前一句的尾巴），找不到再放宽
            for i in range(pos, len(words)):
                if strict and texts[i] and texts[i] not in target and not target.startswith(texts[i][:2]):
                    continue
                acc = ""
                for j in range(i, len(words)):
                    acc += texts[j]
                    if len(acc) >= len(target) * 0.8 and (target in acc or acc in target or acc.endswith(target[-max(2, len(target) // 3):])):
                        found = (i, j)
                        pos = j + 1
                        break
                    if len(acc) > len(target) * 1.6:
                        break
                if found:
                    break
            if found:
                break
        out.append(found)
    return out


# ---- 台词边界：入点/出点不切词，字幕以取用区间内实际存在的词为准 ----------------------------------------
def _word_belongs(text: str, expected: str) -> bool:
    """ASR 词是否属于本镜台词（规范化后是台词的子串，或有两个字连着出现在台词里）；不属于的杂音不去保护。"""
    from common import norm
    t = norm(text)
    if not t:
        return False
    if not expected or t in expected:
        return True
    return any(t[k:k + 2] in expected for k in range(len(t) - 1))


def guard_word_edges(words: list, a: float, b: float, clip: float, expected: str = "") -> tuple[float, float, list[str]]:
    """入点落在词内部、或切掉入点前 0.3 秒内刚开始的词（句首语气词「あれ？」）：入点前移到该词开始前 0.1 秒；
    出点落在词内部：出点后移到词尾 + 0.1 秒（不超过素材长度 −0.02）。只保护属于本镜台词的词。返回新 a、b 与剪辑单注记。"""
    notes: list[str] = []
    for _ in range(len(words) + 2):
        changed = False
        for w in words:
            s, e, txt = float(w[0]), float(w[1]), str(w[2]) if len(w) > 2 else ""
            if not _word_belongs(txt, expected):
                continue
            if s < a < e or a - 0.3 <= s < a + 0.05:
                na = max(0.0, s - 0.1)
                if na < a - 1e-6:
                    notes.append(f"入点 {a:.2f}→{na:.2f}（保住句首「{txt.strip()}」）")
                    a, changed = na, True
            if s < b < e:
                nb = min(clip - 0.02, e + 0.1)
                if nb > b + 1e-6:
                    notes.append(f"出点 {b:.2f}→{nb:.2f}（保住词尾「{txt.strip()}」）")
                    b, changed = nb, True
        if not changed:
            break
    return a, b, notes


def _strip_heard(sub: str, heard: str, from_end: bool) -> str | None:
    """从字幕首（或尾）去掉与 heard 规范化后逐字相同的部分（跳过标点）；对不上返回 None。"""
    from common import norm
    target = norm(heard)
    if not target:
        return sub
    chars = list(reversed(sub)) if from_end else list(sub)
    want = list(reversed(target)) if from_end else list(target)
    k = i = 0
    while i < len(chars) and k < len(want):
        c = chars[i]
        if not norm(c):
            i += 1
            continue
        if c != want[k]:
            return None
        k += 1
        i += 1
    if k < len(want):
        return None
    rest = chars[i:]
    while rest and not norm(rest[0]):
        rest = rest[1:]
    out = "".join(reversed(rest)) if from_end else "".join(rest)
    return out


def trim_subtitles(words: list, lines: list[dict], a: float, b: float) -> tuple[list[dict], list[str]]:
    """字幕以取用区间 [a, b] 内实际存在的词为准。lines = [{"sub": 字幕文字, "text": 台词原文}]。
    某句的首/尾词不在区间内：字幕去掉对应部分（字幕=原文且对得上时），否则保留并记警告要人工改；整句都不在区间内：去掉整句。"""
    if not words:
        return lines, []
    idx = align_phrase_indices(words, [ln["text"] for ln in lines])
    kept, warns = [], []
    for ln, ij in zip(lines, idx):
        if not ij:
            kept.append(ln)
            continue
        ws = words[ij[0]:ij[1] + 1]
        inside = [w for w in ws if w[1] > a + 0.02 and w[0] < b - 0.02]
        if not inside:
            warns.append(f"「{ln['sub']}」整句不在取用区间内，字幕已去掉")
            continue
        head = [w for w in ws if w[1] <= a + 0.02]
        tail = [w for w in ws if w[0] >= b - 0.02]
        sub = ln["sub"]
        for part, from_end in ((head, False), (tail, True)):
            if not part:
                continue
            heard = "".join(str(w[2]) for w in part)
            new = _strip_heard(sub, heard, from_end) if ln["sub"] == ln["text"] else None
            where = "句尾" if from_end else "句首"
            if new:
                warns.append(f"字幕去掉{where}「{heard.strip()}」（不在取用区间内）")
                sub = new
            else:
                warns.append(f"{where}「{heard.strip()}」不在取用区间内，但字幕对不上声音，需人工改字幕")
        kept.append({**ln, "sub": sub})
    return kept, warns


# ---- 叠字避脸：OpenCV（有就用）检测该镜中段几帧的人脸，叠字框与人脸相交就换位置 -------------------------------
FACE_HOOK = None   # 测试注入：callable(video_path, times) -> [[x, y, w, h], ...]（视频像素）；None = 用 OpenCV


def face_detector_name() -> str | None:
    if FACE_HOOK is not None:
        return "hook"
    try:
        import cv2  # noqa: F401
        return "opencv-haar"
    except Exception:  # noqa: BLE001
        return None


def detect_faces(video: Path, times: list[float]) -> list[list[int]] | None:
    """在 video 的这些时刻取帧找人脸（正脸 + 左右侧脸），返回像素框；没有检测器返回 None（未做，不是没脸）。"""
    if FACE_HOOK is not None:
        return [list(map(int, b)) for b in FACE_HOOK(video, times)]
    try:
        import cv2
    except Exception:  # noqa: BLE001
        return None
    base = getattr(getattr(cv2, "data", None), "haarcascades", "")
    cascades = [cv2.CascadeClassifier(os.path.join(base, n)) for n in
                ("haarcascade_frontalface_default.xml", "haarcascade_profileface.xml")]
    cascades = [c for c in cascades if not c.empty()]
    if not cascades:
        return None
    cap = cv2.VideoCapture(str(video))
    boxes: list[list[int]] = []
    try:
        for t in times:
            cap.set(cv2.CAP_PROP_POS_MSEC, max(0.0, t) * 1000)
            ok, frame = cap.read()
            if not ok:
                continue
            gray = cv2.equalizeHist(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY))
            h, w = gray.shape
            mn = (max(24, h // 14), max(24, h // 14))
            for k, cas in enumerate(cascades):
                for flip in ((False, True) if k == 1 else (False,)):   # 侧脸模型只认一侧，翻转再找一次
                    g = cv2.flip(gray, 1) if flip else gray
                    for (x, y, bw, bh) in cas.detectMultiScale(g, scaleFactor=1.1, minNeighbors=5, minSize=mn):
                        x = w - x - bw if flip else x
                        boxes.append([int(x), int(y), int(bw), int(bh)])
    finally:
        cap.release()
    return boxes


def _grow(box, k: float = 0.15) -> list[float]:
    x, y, w, h = box
    return [x - w * k, y - h * k * 1.5, w * (1 + 2 * k), h * (1 + 2.5 * k)]   # 上方多留：额头、头发


def overlap_area(r1, r2) -> float:
    ax, ay, aw, ah = r1
    bx, by, bw, bh = r2
    return max(0.0, min(ax + aw, bx + bw) - max(ax, bx)) * max(0.0, min(ay + ah, by + bh) - max(ay, by))


def face_overlap(rect, faces) -> float:
    return sum(overlap_area(rect, _grow(f)) for f in faces or [])


def place_avoiding(cands: list[tuple[str, list[int]]], faces, others=()) -> tuple[str, list[int], float]:
    """按顺序取第一个既不与人脸相交、也不压到同时段其他叠字（others）的候选位置；
    都不行返回人脸相交面积最小的那个（调用方再缩小）。返回的第三项只算人脸相交面积。"""
    best = None
    for name, rect in cands:
        ov = face_overlap(rect, faces)
        clash = sum(overlap_area(rect, o) for o in others)
        if ov <= 0 and clash <= 0:
            return name, rect, 0.0
        if best is None or (ov, clash) < (best[2], best[3]):
            best = (name, rect, ov, clash)
    return best[:3]


def text_candidates(kind: str, w: int, h: int, W: int, H: int, y_frac: float | None = None) -> list[tuple[str, list[int]]]:
    """叠字的候选位置（左上角 + 宽高）：字幕默认底部，后期字默认画面 0.30 高处；再试上/下/左/右。"""
    m = 40
    if kind == "sub":
        return [("bottom", [(W - w) // 2, H - h - m, w, h]), ("top", [(W - w) // 2, m, w, h]),
                ("bottom_left", [m, H - h - m, w, h]), ("bottom_right", [W - w - m, H - h - m, w, h]),
                ("top_left", [m, m, w, h]), ("top_right", [W - w - m, m, w, h])]
    cy = int(H * (0.30 if y_frac is None else float(y_frac)) - h / 2)
    return [("default", [(W - w) // 2, cy, w, h]), ("top", [(W - w) // 2, m, w, h]),
            ("bottom", [(W - w) // 2, int(H * 0.72 - h / 2), w, h]),
            ("left", [m, cy, w, h]), ("right", [W - w - m, cy, w, h])]


def paginate(lines: list[str], per_page: int = 2) -> list[list[str]]:
    """超过两行的长文字分屏：每屏最多两行。"""
    return [lines[k:k + per_page] for k in range(0, len(lines), per_page)] or [[""]]



OVERLAYS_SCHEMA = "drama-forge/overlays/v1"


def overlays_path(video: Path) -> Path:
    """成片旁的叠字元数据：成片/<EP>.overlays.json（草剪：审查/<EP>-草剪.overlays.json）。"""
    return Path(video).with_suffix(".overlays.json")


def text_terms(project: Project, data: dict) -> list[str]:
    """折行不可拆的专名：drama.json readings、各句 dialogue[].reading、各镜 critical_terms。"""
    out = set((project.get("readings") or {}).keys())
    for sh in data.get("shots") or []:
        out.update(sh.get("critical_terms") or [])
        for d in sh.get("dialogue") or []:
            if isinstance(d.get("reading"), dict):
                out.update(d["reading"].keys())
    return sorted(t for t in out if isinstance(t, str) and len(t) > 1)


def cut(project: Project, ep: str, out: Path | None = None, loudnorm: bool = True, dry: bool = False, draft: bool = False) -> Path | None:
    from review_tool import ASR  # 词级时间缓存
    data = project.load_shots(ep)
    review = project.load_review(ep)
    if not draft:
        issues = cut_issues(project, ep, data, review)
        if issues:
            raise ValueError("正式剪辑未通过审查准入：\n" + "\n".join(issues) + "\n未审素材可用 --draft 生成草剪预览")
    elif out is not None and out.resolve() == project.final_path(ep).resolve():
        raise ValueError("草剪不得覆盖正式成片路径")
    W, H = int(project.get("width")), int(project.get("height"))
    FPS = int(project.get("fps"))
    subcfg = project.sub("subtitle")
    fonts = project.sub("fonts")
    # 中文台词：日文字体缺简体字（额/归/剑等会成方框），先用简体中文字体
    zh_first = ["/System/Library/Fonts/Hiragino Sans GB.ttc", "/System/Library/Fonts/PingFang.ttc",
                "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"] if str(project.get("dialogue_lang") or "").startswith("zh") else []
    sub_font = find_font((fonts.get("sub") or []) + zh_first + FONT_DEFAULTS["sub"])
    zh_fonts = PANEL_FONTS["zh"] + ["/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"]

    def font_for(text: str) -> str | None:
        """没在 drama.json fonts.sub 指定字体时按文字挑：无假名（中文译文字幕、中文后期字）先用简体中文字体，免得日文字体缺字成方框。"""
        if fonts.get("sub") or re.search(r"[\u3040-\u30ff]", text or ""):
            return sub_font
        return find_font(zh_fonts) or sub_font
    stamps = project.sub("overlays")
    tmp = Path(tempfile.mkdtemp(prefix=f"cut_{ep}_"))
    asr = ASR(project)
    shots_by_id = {sh["id"]: sh for sh in data.get("shots") or []}

    segs, over, recs, beds, sfxs, extended, t0 = [], [], [], [], [], [], 0.0
    seg_meta: list[dict] = []          # 逐段元数据，写进 成片/<EP>.overlays.json 供 final_qa.py 终验
    boundary_fixed: list[str] = []     # 入点/出点因台词边界调整的镜
    no_words: list[str] = []           # 有台词但没有 ASR 词级时间、台词边界没法检查的镜
    terms = text_terms(project, data)  # 折行时不可拆的专名
    pace = project.sub("pace")
    pace_rows: list[tuple[str, str, float, float, str]] = []   # (镜, 场, 成片时长, 下限, 类别)
    sheet = [f"# {ep} {'草剪预览（未完成审查）' if draft else '剪辑单'}", "", "| # | 镜 | take | 取用 | 时长 | 成片位置 | 字幕 | 叠加 | 结论 |", "|---|---|---|---|---|---|---|---|---|"]
    order = data.get("cut_order") or [sh["id"] for sh in data.get("shots") or []]
    for sid in order:
        sh = shots_by_id.get(sid)
        if not sh:
            continue
        entry = (review.get("shots") or {}).get(sid) or {}
        selected = project.chosen_take(ep, sid, "video", review)
        selected_rec = (entry.get("video_takes") or {}).get(str(selected)) or {}
        # Legacy shot-level edit points are not transferred to a different take.
        e = {k: v for k, v in entry.items() if k not in ("in", "out", "mode", "speed")}
        e.update(selected_rec.get("edit") or {})
        if e.get("verdict") in ("drop", "missing"):
            continue
        take = project.chosen_take(ep, sid, "video", review)
        if not take:
            print("skip (no clip)", sid)
            continue
        src = project.video_path(ep, sid, take)
        clip = ffprobe_duration(src)
        dlg = sh.get("dialogue") or []
        stamp_ovs = [o for o in sh.get("overlay") or [] if o.get("kind") == "stamp"]
        mode = e.get("mode") or ("after_last_word" if dlg else "full")
        mrec = (e.get("video_takes") or {}).get(str(take)) or {}
        act = verified_action(mrec)
        assessment = mrec.get("assessment") or {}
        speech = assessment.get("speech_window") if dlg and not sh.get("audio_from") else None
        if draft and take_quality(src, sh, mrec):
            act, speech = None, None
        if mode == "action" and not act:
            mode = "after_last_word" if dlg else "full"
        a = float(e.get("in", 0.0) or 0.0)
        b = e.get("out")
        b = float(b) if b is not None else clip - 0.2
        freeze = 0.0
        need_words = bool(dlg or stamp_ovs or mode == "to_end")
        wsx = [tuple(w) for w in (asr.words([src])[str(src)] if need_words and asr.py else [])] if need_words else []
        wall = list(wsx)   # 整条素材的词（字幕按取用区间裁剪要用）
        wsx = [w for w in wsx if w[1] > a - 0.5]
        ws = [(w[0], w[1]) for w in wsx]
        if mode == "to_end" and ws:
            b = ws[-1][1] + 0.02
        elif mode == "after_last_word" and ws:
            hold = max([float(stamps.get(o.get("name", "stamp"), stamps.get("stamp", {})).get("hold", 1.5)) for o in stamp_ovs] + [0])
            tail = hold + 0.1 if stamp_ovs else 0.5
            want = min(clip - 0.1, ws[-1][1] + tail)
            b = max(b, want) if e.get("out") is not None else want  # 没手写出点时收在末词 + 尾巴，不拖到素材结尾
            if stamp_ovs:  # 印章字镜素材不够停留时，尾帧定格补足（不为此重拍）
                freeze = max(0.0, ws[-1][1] + tail - (clip - 0.1))
        elif mode == "full":
            b = clip - 0.2
        elif mode == "action":
            a = min(max(0.0, ws[0][0] - 0.15) if ws else 0.0, act[0])
            b = min(clip - 0.1, max(act[1] + 0.2, ws[-1][1] + 0.3 if ws else 0.0))
        original_a, original_b = a, b
        a, b = protect_interval(a, b, clip, act, speech)
        ext = ""
        if a != original_a or b != original_b:
            ext = f"取用因已审动作/对白保护 {original_a:.2f}–{original_b:.2f}→{a:.2f}–{b:.2f}（reviewed_take）"
            extended.append(sid)
        # 台词边界：入点/出点不切在词中间、不切掉句首语气词（只保护属于本镜台词的词）
        bnotes: list[str] = []
        if wall and dlg and not sh.get("audio_from"):
            a, b, bnotes = guard_word_edges(wall, a, b, clip, norm("".join(d.get("text", "") for d in dlg)))
            if bnotes:
                boundary_fixed.append(sid)
        elif dlg and not sh.get("audio_from"):
            no_words.append(sid)
        if b - a < 0.5:
            if not draft:
                raise ValueError(f"{sid}: 取用短于 0.5 秒，先核对是否保留完整职责，不静默删镜")
            print("draft skip (too short)", sid, a, b)
            continue
        wsx = [w for w in wall if w[1] > a - 0.5] if wall else wsx
        ws = [(w[0], w[1]) for w in wsx if w[0] < b]
        i = len(segs)
        seg = tmp / f"seg_{i:02d}.mp4"
        speed = float(e.get("speed") or 1.0)
        vf = f"trim={a}:{b},setpts=PTS-STARTPTS,fps={FPS},scale={W}:{H}"
        af = f"atrim={a}:{b},asetpts=PTS-STARTPTS,aresample=48000"
        if speed != 1.0:
            vf += f",setpts=PTS/{speed}"
            af += f",atempo={min(max(speed, 0.5), 2.0)}"
        if freeze > 0:
            vf += f",tpad=stop_mode=clone:stop_duration={freeze:.3f}"
            af += f",apad=pad_dur={freeze:.3f}"
        if e.get("verdict") == "mute":
            af += ",volume=0"
        if not dry:
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(src), "-vf", vf, "-af", af, "-c:v", "libx264", "-crf", "16",
                            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", str(seg)], check=True)
        dur = (b - a) / speed + freeze
        dur = max(1, round(dur * FPS)) / FPS  # 取整到整帧：否则合并时每段多带一帧，字幕/印章字随片长累积提前
        segs.append((seg, dur))
        seg_meta.append({"shot": sid, "scene": sh.get("scene"), "take": take, "start": round(t0, 3), "end": round(t0 + dur, 3),
                         "in": round(a, 3), "out": round(b, 3), "speed": speed, "freeze": round(freeze, 3), "kind": sh.get("kind", "person"),
                         "boundary_notes": bnotes, "subtitle_warnings": []})
        # 节奏下限：对白镜 ≥ max(dialogue_min, 说完 + dialogue_tail)；反应镜 ≥ reaction_min；插入/冲击镜 ≥ insert_min（fast_cut_reason 可豁免）
        kind_ = sh.get("kind", "person")
        if kind_ == "person" and dlg and not sh.get("audio_from"):
            said = ((ws[-1][1] - a) / speed) if ws else 0.0
            floor, cls = max(float(pace["dialogue_min"]), said + float(pace["dialogue_tail"])), "对白"
        elif kind_ == "person":
            floor, cls = (0.0 if sh.get("fast_cut_reason") else float(pace["reaction_min"])), "反应"
        else:
            floor, cls = (0.0 if sh.get("fast_cut_reason") else float(pace["insert_min"])), "插入"
        pace_rows.append((sid, str(sh.get("scene") or ""), dur, floor, cls))
        short_mark = f"（过短：{cls}镜下限 {floor:.1f}s）" if dur + 1e-3 < floor else ""
        # 字幕：文字取剧本，时间取 ASR（先按句对齐，对不上再按字数比例）
        sub_lines = [{"sub": d.get("subtitle") or d.get("text", ""), "text": d.get("text", "")} for d in dlg if d.get("text")]
        if sub_lines and wall and not sh.get("audio_from"):   # 字幕以取用区间内实际存在的词为准
            sub_lines, swarn = trim_subtitles(wall, sub_lines, a, b)
            seg_meta[-1]["subtitle_warnings"] = swarn
        subs = [x["sub"] for x in sub_lines]
        sub_src = [x["text"] for x in sub_lines]
        if subs:
            if sh.get("audio_from"):
                s0, s1 = float(sh["audio_from"][0].get("at", 0.3)), min(dur, float(sh["audio_from"][-1].get("at", 0.3)) + 2.2)
            elif ws:
                s0, s1 = max(0.0, (ws[0][0] - a) / speed - 0.1), min(dur, (ws[-1][1] - a) / speed + 0.25)
            else:
                s0, s1 = dur * 0.2, dur * 0.8
            aligned = align_phrases([w for w in wsx if w[0] < b], sub_src) if (wsx and not sh.get("audio_from")) else [None] * len(subs)
            tot = sum(len(x) for x in subs) or 1
            c = s0
            for x, src_text, al in zip(subs, sub_src, aligned):
                d_ = (s1 - s0) * len(x) / tot
                meta = {"shot": sid, "seg": i, "speech": src_text}
                if al:
                    st_, en_ = max(0.0, (max(al[0], a) - a) / speed - 0.1), min(dur, (al[1] - a) / speed + 0.25)
                    over.append((t0 + st_, t0 + en_, "sub", x, None, meta))
                    c = en_
                else:
                    over.append((t0 + c, t0 + c + d_, "sub", x, None, meta))
                    c += d_
        # 叠加
        for o in sh.get("overlay") or []:
            if o.get("kind") == "stamp":
                cfg = stamps.get(o.get("name", "stamp"), stamps.get("stamp", {}))
                hold = float(cfg.get("hold", 1.5))
                end = ((ws[-1][1] - a) / speed) if ws else dur - hold - 0.1
                if o.get("phrase") and wsx:  # 只在谎的那一小句说完时亮，不是整段最后一个词
                    al = align_phrases([w for w in wsx if w[0] < b], [o["phrase"]])[0]
                    if al:
                        end = (al[1] - a) / speed
                if o.get("at") is not None:
                    end = float(o["at"])
                s0 = min(max(0.0, end), dur - 0.4)
                s1 = min(dur, s0 + hold)
                over.append((t0 + s0, t0 + s1, "stamp", o.get("side", "R"), o.get("name", "stamp"), {"shot": sid, "seg": i}))
        texts = [o for o in sh.get("overlay") or [] if o.get("kind") in ("text", "panel")]
        min_panel = 1.6   # 面板要够时间入场、打字、读完
        lo = 0.42 if sh.get("audio_from") else 0.15
        for k, o in enumerate(texts):
            n = len(texts)
            s0 = float(o["at"]) if o.get("at") is not None else dur * (lo + (0.97 - lo) * k / n)
            s1 = min(dur, float(o["until"])) if o.get("until") is not None else dur * (lo + (0.97 - lo) * (k + 1) / n) - 0.05
            if o.get("kind") == "panel":
                s1 = max(s1, min(dur, s0 + min_panel))
                over.append((t0 + s0, t0 + s1, "panel", o.get("text", ""), o, {"shot": sid, "seg": i}))
            else:
                over.append((t0 + s0, t0 + s1, "text", o.get("text", ""), o.get("y"), {"shot": sid, "seg": i}))   # y：可选，字幕卡中心高度（画面比例，默认 0.30）
        # 从别的镜垫进来的录音
        for rec in sh.get("audio_from") or []:
            rs_sh = rec.get("shot")
            rt = project.chosen_take(ep, rs_sh, "video", review)
            if not rt:
                continue
            rv = project.video_path(ep, rs_sh, rt)
            rw = [(s, en) for s, en, _ in (asr.words([rv])[str(rv)] if asr.py else [])]
            if not rw:
                source_entry = (review.get("shots") or {}).get(rs_sh) or {}
                source_take = (source_entry.get("video_takes") or {}).get(str(rt)) or {}
                source_window = (source_take.get("assessment") or {}).get("speech_window")
                if source_window:
                    rw = [tuple(source_window)]
            if rw:
                tail = rec.get("tail")
                st = rw[-1][1] - float(tail) if tail else rw[0][0] - 0.05
                recs.append((rv, max(0.0, st), rw[-1][1] + 0.2, t0 + float(rec.get("at", 0.3)), rec.get("filter", "phone")))
                # 垫进来的录音自带字幕：显式 subtitle，否则取源镜台词（本镜已挂同句 dialogue 时不重复）
                src_sub = rec.get("subtitle")
                if src_sub is None and not tail:
                    src_sub = [d.get("subtitle") or d.get("text", "") for d in (shots_by_id.get(rs_sh, {}).get("dialogue") or [])]
                lines = [x for x in ([src_sub] if isinstance(src_sub, str) else (src_sub or [])) if x and x not in subs]
                if lines:
                    r0 = t0 + float(rec.get("at", 0.3))
                    r1 = min(t0 + dur, r0 + (rw[-1][1] + 0.2 - max(0.0, st)) + 0.25)
                    tot = sum(len(x) for x in lines)
                    for x in lines:  # 多句按字数分摊录音时长
                        r_ = r0 + (r1 - r0) * len(x) / tot
                        over.append((r0, r_, "sub", x, None, {"shot": sid, "seg": i, "speech": x, "audio_from": rs_sh}))
                        r0 = r_
        # 环境声
        bed = (project.sub("beds") or {}).get(sh.get("scene")) or (project.sub("beds") or {}).get("*")
        if bed and (project.root / bed).exists():
            beds.append((project.root / bed, t0, dur, float((project.sub("beds") or {}).get("gain_db", -18))))
        for fx in sh.get("sfx") or []:  # 音效：at 是源素材秒，换算到成片时间
            fxp, at = project.root / str(fx.get("file", "")), float(fx.get("at", a))
            if not fx.get("file") or not fxp.exists():
                print("sfx missing", sid, fx.get("file"))
            elif a <= at < b:
                sfxs.append((fxp, t0 + (at - a) / speed, float(fx.get("gain_db", 0))))
        notes_cell = "；".join([x for x in [ext] if x] + bnotes + seg_meta[-1]["subtitle_warnings"])
        sheet.append(f"| {i + 1} | {sid} | {take} | {a:.2f}–{b:.2f}（{mode}）{'；' + notes_cell if notes_cell else ''} | {dur:.2f}s{short_mark} | {t0:.1f}–{t0 + dur:.1f}s | "
                     f"{'；'.join(subs) or '无'} | {'；'.join(o.get('kind') + (':' + str(o.get('text') or o.get('side'))) for o in sh.get('overlay') or []) or '无'} | {e.get('verdict', '')}{('（' + fmt_audio(audio_status(mrec.get('assessment'))) + '）') if dlg else ''} |")
        t0 += dur
    if not segs:
        print(ep, "没有可用素材")
        return None
    dst = out or (project.review_dir / f"{ep}-草剪.mp4" if draft else project.final_path(ep))
    sheet += ["", f"成片：{dst.relative_to(project.root) if dst.is_relative_to(project.root) else dst}，总长约 {t0:.1f} 秒，{len(segs)} 镜。"]
    if extended:
        sheet.append(f"出点因动作延长：{'、'.join(extended)}。")
    sheet.append(f"台词边界：入点/出点因不切词调整 {len(boundary_fixed)} 镜{('（' + '、'.join(boundary_fixed) + '）') if boundary_fixed else ''}；"
                 f"字幕按取用区间裁剪 {sum(1 for m in seg_meta if m['subtitle_warnings'])} 镜；"
                 + (f"没有 ASR 词级时间、未做台词边界检查：{'、'.join(no_words)}。" if no_words else "全部对白镜都按词级时间检查过。"))
    tail = seg_meta[-1]
    if tail["freeze"] > 0.3:
        sheet.append(f"⚠ 片尾：最后一镜 {tail['shot']} 尾帧定格 {tail['freeze']:.2f}s，超过 0.3 秒静止拖尾上限；换能停留更久的 take 或缩短印章字停留。")
    cut_ids = [m["shot"] for m in seg_meta]
    ms_rows = must_show_coverage(data, cut_ids)
    if ms_rows:
        sheet.append("必须拍清楚：" + "；".join(
            f"{r['id']}「{r['fact']}」→ {'、'.join(r['in_cut']) if r['in_cut'] else '✗ 承担镜全部不在片中'}" for r in ms_rows) + "。")
    exp = [m for m in seg_meta if shots_by_id.get(m["shot"], {}).get("explains_ability")]
    if exp:
        runs, cur = [], []
        for m in seg_meta:
            if shots_by_id.get(m["shot"], {}).get("explains_ability"):
                cur.append(m)
            else:
                runs, cur = (runs + [cur] if len(cur) >= 2 else runs), []
        runs = runs + [cur] if len(cur) >= 2 else runs
        sheet.append(f"能力解释镜（explains_ability）：{len(exp)} 镜共 {sum(m['end'] - m['start'] for m in exp):.1f}s"
                     + ("；连续解释 " + "；".join(f"{r[0]['shot']}→{r[-1]['shot']} {r[-1]['end'] - r[0]['start']:.1f}s" for r in runs) if runs else "")
                     + "。观众刚看过的能力不再重复确认。")
    face_name = face_detector_name()
    sheet.append("避脸：" + ("dry-run 不检测。" if dry else (f"用 {face_name} 检测人脸，结果见下。" if face_name else "未做避脸（环境没有 OpenCV），叠字位置需人工看接触表。")))
    shorts = [(sid, d, fl, c) for sid, _, d, fl, c in pace_rows if d + 1e-3 < fl]
    by_scene: dict[str, list[float]] = {}
    for _, sc, d, _, _ in pace_rows:
        by_scene.setdefault(sc, []).append(d)
    slow = [f"{sc} {sum(v) / len(v):.2f}s" for sc, v in by_scene.items() if sum(v) / len(v) + 1e-3 < float(pace["scene_avg_min"])]
    avg = t0 / max(1, len(segs))
    sheet.append(f"节奏：平均镜长 {avg:.1f}s；长镜（≥8s）{sum(1 for r in pace_rows if r[2] >= 8)} 个；"
                 f"过短镜 {len(shorts)} 个{('（' + '、'.join(f'{x[0]} {x[1]:.1f}s<{x[2]:.1f}s {x[3]}' for x in shorts) + '）') if shorts else ''}；"
                 f"同场平均镜长低于 {float(pace['scene_avg_min']):.1f}s：{'、'.join(slow) if slow else '无'}。")
    panels_n = sum(1 for o in over if o[2] == "panel")
    pcfg = panel_cfg(stamps)
    if panels_n:
        sheet.append(f"面板：{panels_n} 个，主题 {pcfg['theme']}，位置 {pcfg['position']}，入场 {pcfg['enter_mode']} {float(pcfg['enter']):.2f}s，"
                     f"音效 {'开' if pcfg.get('sfx') else '关'}。")
    room_db = project.get("room_tone_db", -48.0)
    room = room_db is not None and len(beds) < len(segs)
    sheet.append(f"声音：beds {len(beds)}/{len(segs)} 镜；房间音 {f'{float(room_db):.0f} dBFS 整片' if room else '无'}；音效 {len(sfxs)} 个。")
    # AI 生成显式标识（《人工智能生成合成内容标识办法》）：drama.json ai_label 有文字就叠在前 3 秒右上角；null/未写 = 不叠
    ai_label = project.get("ai_label")
    ai_label = str(ai_label).strip() if ai_label else ""
    if draft:
        ai_label = "草剪预览 · 未完成审查" + (" · " + ai_label if ai_label else "")
    if ai_label and not sub_font:
        sheet.append("AI 标识：无（找不到字体，没叠上；交付前必须补）。")
    elif ai_label:
        sheet.append(f"AI 标识：有（「{ai_label}」，前 3 秒右上角）。")
    else:
        sheet.append("AI 标识：无（drama.json ai_label 为 null 或未写；只在海外发行时可以不叠，理由写进决策记录）。")
    (project.ep_dir(ep) / ("草剪单.md" if draft else "剪辑单.md")).write_text("\n".join(sheet), encoding="utf-8")
    if dry:
        print("\n".join(sheet))
        return None

    inputs, f, cat = [], [], ""
    for i, (p, dur) in enumerate(segs):
        inputs += ["-i", str(p)]
        f.append(f"[{i}:v]trim=duration={dur:.4f},setpts=PTS-STARTPTS[v{i}]")
        f.append(f"[{i}:a]atrim=duration={dur:.4f},asetpts=PTS-STARTPTS,apad=whole_dur={dur:.4f}[a{i}]")
        cat += f"[v{i}][a{i}]"
    f.append(f"{cat}concat=n={len(segs)}:v=1:a=1[vc][ac]")
    last, n_in = "[vc]", len(segs)  # n_in：已经加进 ffmpeg 的输入个数（每个 -i 算一个）
    stamp_font_cache: dict[str, str | None] = {}
    # 台词字幕互不重叠：后一句出现时前一句截止（同位置叠字会糊成一团）
    subs_ix = sorted((i for i, o in enumerate(over) if o[2] == "sub"), key=lambda i: over[i][0])  # noqa: E741
    for i, j in zip(subs_ix, subs_ix[1:]):
        if over[i][1] > over[j][0]:
            over[i] = (over[i][0], max(over[i][0] + 0.2, over[j][0] - 0.02), *over[i][2:])
    maxw = int(subcfg["max_width"])
    # 长文字分屏：字幕/后期字折行后超过两行，按字数把时段分给每屏（每屏最多两行）
    expanded = []
    for (s, e_, kind, t, name, meta) in over:
        if kind in ("sub", "text") and sub_font:
            size = int(subcfg["size"] if len(t) <= int(subcfg["long_threshold"]) else subcfg["size_long"]) if kind == "sub" else 58
            lw: list[str] = []
            pages = paginate(layout_text(t, size, font_for(t), maxw, terms, lw))
            tot = sum(len("".join(pg)) for pg in pages) or 1
            c = s
            for pi, pg in enumerate(pages):
                d_ = (e_ - s) * len("".join(pg)) / tot
                end_ = e_ if pi == len(pages) - 1 else c + d_
                pw_ = list(lw) + ([f"分屏第 {pi + 1} 屏只有 {end_ - c:.2f}s，可能读不完"] if len(pages) > 1 and end_ - c < 0.8 else [])
                expanded.append((c, end_, kind, "\n".join(pg), name,
                                 {**meta, "size": size, "full_text": t, "page": [pi + 1, len(pages)], "layout_warnings": pw_}))
                c = end_
        else:
            expanded.append((s, e_, kind, t, name, meta))
    over = expanded
    face_cache: dict = {}

    def faces_for(meta: dict, s: float, e_: float):
        """叠字时段中段三帧（25%/50%/75%）的人脸框；没有检测器返回 None。"""
        if not face_name or meta.get("seg") is None:
            return None
        i_ = meta["seg"]
        times = [max(0.0, s + (e_ - s) * q - seg_meta[i_]["start"]) for q in (0.25, 0.5, 0.75)]
        key = (i_, tuple(round(x, 2) for x in times))
        if key not in face_cache:
            face_cache[key] = detect_faces(segs[i_][0], times)
        return face_cache[key]

    ov_records: list[dict] = []
    panel_sfxs: list[tuple[Path, float, float]] = []
    for k, (s, e_, kind, t, name, meta) in enumerate(over):
        png = tmp / f"ov_{k}.png"
        full = meta.get("full_text", t) if isinstance(t, str) else ""
        rec = {"k": k, "kind": kind, "shot": meta.get("shot"), "start": round(s, 3), "end": round(e_, 3), "text": t if isinstance(t, str) else "",
               "full_text": full, "speech": meta.get("speech"), "page": meta.get("page"), "audio_from": meta.get("audio_from"),
               "warnings": list(meta.get("layout_warnings") or []), "protected": protected_tokens(full, terms) if kind != "stamp" else [],
               "face_check": "skipped" if not face_name else "done", "faces": [], "face_overlap": None}
        if kind == "panel":
            cfg_p = panel_cfg(stamps, name if isinstance(name, dict) else None)
            cfg_p["_terms"] = terms
            try:
                pos0 = cfg_p.get("position") or "top_left"
                faces = faces_for(meta, s, e_)
                ov = 0.0
                if faces is not None:   # 检测做了（哪怕没找到脸）就同时避开同时段已放好的叠字
                    order_ = [pos0] + [p_ for p_ in ("top_left", "top_right", "top", "left", "right") if p_ != pos0]
                    cands = []
                    for p_ in order_:
                        g = panel_geometry(t, {**cfg_p, "position": p_}, W, H)
                        cands.append((str(p_), [g["X"], g["Y"], g["pw"], g["ph"]]))
                    others = [r["rect"] for r in ov_records if r.get("rect") and r["start"] < e_ and r["end"] > s]
                    chosen_name, _, ov = place_avoiding(cands, faces, others)
                    cfg_p["position"] = order_[[c_[0] for c_ in cands].index(chosen_name)]
                    if ov > 0:
                        cfg_p["width"] = round(float(cfg_p.get("width", 0.36)) * 0.8, 3)
                        g = panel_geometry(t, cfg_p, W, H)
                        ov = face_overlap([g["X"], g["Y"], g["pw"], g["ph"]], faces)
                        rec["warnings"].append(f"面板所有候选位置都压到人脸，已缩小到 {cfg_p['width']:.2f} 画宽" + ("，仍相交" if ov > 0 else ""))
                g = panel_geometry(t, cfg_p, W, H)
                last, n_in = add_panel(k, s, e_, t, cfg_p, tmp, W, H, FPS, t0, inputs, f, last, n_in)
            except FileNotFoundError as err:
                print("panel skipped:", err)
                continue
            rec.update(rect=[g["X"], g["Y"], g["pw"], g["ph"]], lines=g["lines"], position=str(cfg_p["position"]),
                       moved=str(cfg_p["position"]) != str(pos0), faces=faces or [], face_overlap=(ov > 0) if faces is not None else None)
            ov_records.append(rec)
            fx = panel_sfx(cfg_p, tmp, project.root)
            if fx:
                panel_sfxs.append((fx, s + 0.02, float(cfg_p.get("sfx_gain_db", -10))))
            continue
        if kind == "stamp":
            cfg = stamps.get(name or "stamp", stamps.get("stamp", {}))
            if name not in stamp_font_cache:
                stamp_font_cache[name] = find_font((cfg.get("font") or []) + FONT_DEFAULTS["stamp"] + FONT_DEFAULTS["sub"])
            font = stamp_font_cache[name]
            if not font:
                print("no stamp font; skip", name)
                continue
            w, h = stamp_png(cfg, png, font)
            cx = W * float(cfg.get("x_right", 0.80) if t == "R" else cfg.get("x_left", 0.20))
            cy = H * float(cfg.get("y", 0.34))
            if cfg.get("jitter", True):
                x, y = f"{cx - w / 2:.0f}+3*sin(t*37)", f"{cy - h / 2:.0f}+3*cos(t*29)"
            else:
                x, y = f"{cx - w / 2:.0f}", f"{cy - h / 2:.0f}"
            fin, fout = 0.08, 0.35
            rec.update(text=str(cfg.get("glyph", "!")), rect=[int(cx - w / 2), int(cy - h / 2), w, h], lines=[str(cfg.get("glyph", "!"))],
                       position=t, face_check="not_applicable")   # 印章字按设计贴在说话人一侧，不做避脸
        else:
            if not sub_font:
                continue
            size = int(meta.get("size") or 58)
            tfont = font_for(meta.get("full_text", t))
            w, h = text_png(t, png, size, tfont, maxw, terms)
            y_frac = name if kind == "text" else None
            cands = text_candidates(kind, w, h, W, H, y_frac)
            pos_name, rect, ov = cands[0][0], cands[0][1], 0.0
            faces = faces_for(meta, s, e_)
            if faces is not None:
                others = [r["rect"] for r in ov_records if r.get("rect") and r["start"] < e_ and r["end"] > s]
                pos_name, rect, ov = place_avoiding(cands, faces, others)
                if ov > 0:
                    size = int(size * 0.8)
                    w, h = text_png(t, png, size, tfont, maxw, terms)
                    pos_name, rect, ov = place_avoiding(text_candidates(kind, w, h, W, H, y_frac), faces, others)
                    rec["warnings"].append(f"{'字幕' if kind == 'sub' else '后期字'}所有候选位置都压到人脸，已缩小到 {size}px" + ("，仍相交" if ov > 0 else ""))
            x, y = str(rect[0]), str(rect[1])
            fin = fout = 0.15 if kind == "sub" else 0.2
            rec.update(rect=rect, size=size, lines=layout_text(t, size, tfont, maxw, terms), position=pos_name,
                       moved=pos_name != cands[0][0], faces=faces or [], face_overlap=(ov > 0) if faces is not None else None)
        ov_records.append(rec)
        inputs += ["-loop", "1", "-t", f"{e_ + 1:.2f}", "-i", str(png)]
        idx, n_in = n_in, n_in + 1
        f.append(f"[{idx}:v]format=rgba,fade=t=in:st={s:.2f}:d={fin}:alpha=1,fade=t=out:st={max(s, e_ - fout):.2f}:d={fout}:alpha=1[o{k}]")
        f.append(f"{last}[o{k}]overlay=x='{x}':y='{y}':enable='between(t,{s:.2f},{e_:.2f})'[w{k}]")
        last = f"[w{k}]"
    if ai_label and sub_font:
        png = tmp / "ai_label.png"
        w, h = text_png(ai_label, png, max(22, H // 30), sub_font, W // 3)
        end = min(3.0, t0)
        inputs += ["-loop", "1", "-t", f"{end + 1:.2f}", "-i", str(png)]
        idx, n_in = n_in, n_in + 1
        f.append(f"[{idx}:v]format=rgba,colorchannelmixer=aa=0.85[lab]")
        f.append(f"{last}[lab]overlay=x='{W - w - 24}':y='24':enable='between(t,0,{end:.2f})'[wlab]")
        last = "[wlab]"
    amap = "[ac]"
    extra = []
    for k, (rv, rs, re_, at, flt) in enumerate(recs):
        inputs += ["-i", str(rv)]
        idx, n_in = n_in, n_in + 1
        f.append(f"[{idx}:a]atrim={rs:.2f}:{re_:.2f},asetpts=PTS-STARTPTS,aresample=48000,{FILTERS.get(flt, FILTERS['none'])},adelay={int(at * 1000)}:all=1[r{k}]")
        extra.append(f"[r{k}]")
    for k, (bp, at, dur, gain) in enumerate(beds):
        inputs += ["-stream_loop", "-1", "-i", str(bp)]
        idx, n_in = n_in, n_in + 1
        f.append(f"[{idx}:a]atrim=0:{dur:.2f},asetpts=PTS-STARTPTS,aresample=48000,volume={gain}dB,adelay={int(at * 1000)}:all=1[b{k}]")
        extra.append(f"[b{k}]")
    for k, (fxp, at, gain) in enumerate(sfxs + panel_sfxs):
        inputs += ["-i", str(fxp)]
        idx, n_in = n_in, n_in + 1
        f.append(f"[{idx}:a]aresample=48000,aformat=channel_layouts=stereo,volume={gain}dB,adelay={int(at * 1000)}:all=1[x{k}]")
        extra.append(f"[x{k}]")
    room_src = (f"anoisesrc=d={t0 + 0.5:.2f}:c=pink:r=48000:a=0.5:seed=1,highpass=f=80,lowpass=f=5000,"  # 粉噪 a=0.5 带通后约 −26.8 dBFS RMS
                f"aformat=channel_layouts=stereo,volume={float(room_db) + 26.8:.1f}dB[rt]") if room else ""
    if room and not loudnorm:  # 要响度归一时放到归一之后再垫，room_tone_db 才是成片里的真实电平
        f.append(room_src)
        extra.append("[rt]")
    if extra:
        f.append(f"[ac]{''.join(extra)}amix=inputs={len(extra) + 1}:normalize=0:duration=first[am]")
        amap = "[am]"
    dst.parent.mkdir(parents=True, exist_ok=True)
    # 片长截断：叠字/面板输入比成片长（-loop … -t e+1），overlay 会把画面拖长约 1 秒成无声停帧；在滤镜图里 trim 到剪辑总长
    # （不用输出端 -t：输入多时 ffmpeg 8 会卡在收尾）
    f.append(f"{last}trim=duration={t0:.4f},setpts=PTS-STARTPTS[vend]")
    last = "[vend]"
    subprocess.run(["ffmpeg", "-y", "-v", "error", *inputs, "-filter_complex", ";".join(f), "-map", last, "-map", amap, "-r", str(FPS),
                    "-c:v", "libx264", "-crf", "17", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(dst)], check=True)
    if loudnorm:
        g = float(project.get("loudness")) - lufs(dst)
        tmp_out = str(dst) + ".tmp.mp4"
        af = f"[0:a]volume={g:.2f}dB[ln];{room_src};[ln][rt]amix=inputs=2:normalize=0:duration=first," if room else f"[0:a]volume={g:.2f}dB,"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(dst), "-filter_complex", af + "alimiter=limit=0.8:level=false[aout]",
                        "-map", "0:v", "-map", "[aout]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", tmp_out], check=True)
        os.replace(tmp_out, dst)
    # 成片元数据：终验（final_qa.py）读它检查断行、遮脸、字幕与声音、切点
    real = ffprobe_duration(dst)
    if real > t0 + 0.3:
        sheet.append(f"⚠ 片尾：成片实长 {real:.2f}s 比剪辑总长 {t0:.2f}s 多 {real - t0:.2f}s（静止拖尾），需排查。")
    moved = [r for r in ov_records if r.get("moved")]
    still = [r for r in ov_records if r.get("face_overlap")]
    if face_name:
        sheet.append(f"避脸结果：{len(ov_records)} 条叠字，换位 {len(moved)} 条，缩小后仍压脸 {len(still)} 条"
                     + ("（" + "、".join(f"{r['shot']} {r['start']:.1f}s" for r in still) + "）" if still else "") + "。")
    lw_ = [f"{r['shot']}：{w}" for r in ov_records for w in r.get("warnings") or []]
    if lw_:
        sheet.append("排版警告：" + "；".join(lw_) + "。")
    (project.ep_dir(ep) / ("草剪单.md" if draft else "剪辑单.md")).write_text("\n".join(sheet), encoding="utf-8")
    meta_path = overlays_path(dst)
    meta_path.write_text(json.dumps({
        "schema": OVERLAYS_SCHEMA, "episode": ep, "draft": draft,
        "video": str(dst.relative_to(project.root)) if dst.is_relative_to(project.root) else str(dst),
        "duration": round(t0, 3), "width": W, "height": H, "fps": FPS, "face_detector": face_name, "terms": terms,
        "segments": seg_meta, "overlays": ov_records}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(dst, round(t0, 2), f"{len(segs)} shots, {sum(1 for o in over if o[2] == 'stamp')} stamps; meta {meta_path.name}")
    return dst


def main(argv=None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    if "--panel-demo" in argv:
        dp = argparse.ArgumentParser(description="面板样式预览：合成背景（或 --bg 一张起始帧）上叠一条面板，存中间帧")
        dp.add_argument("--panel-demo", required=True, metavar="OUT.png")
        dp.add_argument("--theme", choices=sorted(PANEL_THEMES), help="默认 tech；给了 --project 就用项目 overlays.panel.theme")
        dp.add_argument("--text")
        dp.add_argument("--bg")
        dp.add_argument("--project", help="读这个项目 drama.json 的 overlays.panel")
        x = dp.parse_args(argv)
        ov = Project(x.project).sub("overlays") if x.project else None
        r = panel_demo(Path(x.panel_demo), x.theme, x.text, overlays=ov, bg_image=Path(x.bg) if x.bg else None,
                       keep_video=Path(x.panel_demo).with_suffix(".mp4"))
        print(r["frame"], r["video"], f"面板前/中间帧差 {r['before_vs_mid']:.2f}，入场/中间帧差 {r['enter_vs_mid']:.2f}")
        return 0
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("project")
    ap.add_argument("episode")
    ap.add_argument("--out")
    ap.add_argument("--no-loudnorm", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--draft", action="store_true", help="unapproved rough cut; separate output and cut sheet")
    a = ap.parse_args(argv)
    cut(Project(a.project), a.episode, Path(a.out) if a.out else None, not a.no_loudnorm, a.dry_run, a.draft)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
