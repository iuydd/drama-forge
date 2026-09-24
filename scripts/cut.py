#!/usr/bin/env python3
"""把审过的镜头剪成成片：取用区间、字幕、后期叠加（文字/面板/印章字）、环境声、录音垫入、响度归一。

  cut.py <项目> <EP> [--out PATH] [--no-loudnorm] [--dry-run]

来源：shots.json（镜序、台词、叠加）、审查/<EP>-review.json（take、取用区间、结论）、脚本/asr_cache.json（词级时间）。
出点规则（来自实战）：
- after_last_word：说完至少留 0.5 秒；有印章字（如「嘘」）时留 hold+0.1 秒给它亮完；不超过素材长度 −0.1。
- to_end：留白结尾，出点 = 最后一个音结束 + 0.02。
- fixed：按 review 里的 in/out。full：整条（去掉最后 0.2 秒）。
- verdict=drop 的镜跳过；verdict=mute 的镜去掉原声（模型自编的人声）。
字幕按句、按字数比例落在 ASR 首末词之间；印章字在最后一个音落下时亮起、停 hold 秒、本镜内淡出、轻微抖动。
成片整体归一到 drama.json 的 loudness（默认 −16 LUFS）并加限幅。
"""
from __future__ import annotations

import argparse
import glob
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import Project, ffprobe_duration  # noqa: E402

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


def wrap(text: str, f, maxw: int) -> str:
    d = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    lines, cur = [], ""
    for ch in text:
        if d.textlength(cur + ch, font=f) > maxw and cur:
            cut = max(cur.rfind(p) for p in "、。？！…　 ,.?!") + 1
            if cut <= 0 or len(cur) - cut > 12:
                cut = len(cur)
            lines.append(cur[:cut])
            cur = cur[cut:]
        cur += ch
    return "\n".join(lines + [cur])


def text_png(text: str, path: Path, size: int, font: str, maxw: int) -> tuple[int, int]:
    f = ImageFont.truetype(font, size)
    text = wrap(text, f, maxw)
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


def align_phrases(words: list, phrases: list[str]) -> list[tuple[float, float] | None]:
    """把若干句台词按顺序对到 ASR 词序列上（规范化后累计匹配）；对不上的返回 None。words = [(start, end, text)]。"""
    from common import norm
    out: list[tuple[float, float] | None] = []
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
                        found = (words[i][0], words[j][1])
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


def cut(project: Project, ep: str, out: Path | None = None, loudnorm: bool = True, dry: bool = False) -> Path | None:
    from review_tool import ASR  # 词级时间缓存
    data = project.load_shots(ep)
    review = project.load_review(ep)
    W, H = int(project.get("width")), int(project.get("height"))
    FPS = int(project.get("fps"))
    subcfg = project.sub("subtitle")
    fonts = project.sub("fonts")
    sub_font = find_font((fonts.get("sub") or []) + FONT_DEFAULTS["sub"])
    stamps = project.sub("overlays")
    tmp = Path(tempfile.mkdtemp(prefix=f"cut_{ep}_"))
    asr = ASR(project)
    shots_by_id = {sh["id"]: sh for sh in data.get("shots") or []}

    segs, over, recs, beds, t0 = [], [], [], [], 0.0
    sheet = [f"# {ep} 剪辑单", "", "| # | 镜 | take | 取用 | 时长 | 成片位置 | 字幕 | 叠加 | 结论 |", "|---|---|---|---|---|---|---|---|---|"]
    order = data.get("cut_order") or [sh["id"] for sh in data.get("shots") or []]
    for sid in order:
        sh = shots_by_id.get(sid)
        if not sh:
            continue
        e = (review.get("shots") or {}).get(sid) or {}
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
        a = float(e.get("in", 0.0) or 0.0)
        b = e.get("out")
        b = float(b) if b is not None else clip - 0.2
        need_words = bool(dlg or stamp_ovs or mode == "to_end")
        wsx = [tuple(w) for w in (asr.words([src])[str(src)] if need_words and asr.py else [])] if need_words else []
        wsx = [w for w in wsx if w[1] > a - 0.5]
        ws = [(w[0], w[1]) for w in wsx]
        if mode == "to_end" and ws:
            b = ws[-1][1] + 0.02
        elif mode == "after_last_word" and ws:
            hold = max([float(stamps.get(o.get("name", "stamp"), stamps.get("stamp", {})).get("hold", 1.5)) for o in stamp_ovs] + [0])
            tail = hold + 0.1 if stamp_ovs else 0.5
            b = max(b, min(clip - 0.1, ws[-1][1] + tail))
        elif mode == "full":
            b = clip - 0.2
        b = min(b, clip)
        if b - a < 0.5:
            print("skip (too short)", sid, a, b)
            continue
        ws = [(s, en) for s, en in ws if s < b]
        i = len(segs)
        seg = tmp / f"seg_{i:02d}.mp4"
        speed = float(e.get("speed") or 1.0)
        vf = f"trim={a}:{b},setpts=PTS-STARTPTS,fps={FPS},scale={W}:{H}"
        af = f"atrim={a}:{b},asetpts=PTS-STARTPTS,aresample=48000"
        if speed != 1.0:
            vf += f",setpts=PTS/{speed}"
            af += f",atempo={min(max(speed, 0.5), 2.0)}"
        if e.get("verdict") == "mute":
            af += ",volume=0"
        if not dry:
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(src), "-vf", vf, "-af", af, "-c:v", "libx264", "-crf", "16",
                            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", str(seg)], check=True)
        dur = (b - a) / speed
        segs.append((seg, dur))
        # 字幕：文字取剧本，时间取 ASR（先按句对齐，对不上再按字数比例）
        subs = [d.get("subtitle") or d.get("text", "") for d in dlg if d.get("text")]
        sub_src = [d.get("text", "") for d in dlg if d.get("text")]
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
            for x, al in zip(subs, aligned):
                d_ = (s1 - s0) * len(x) / tot
                if al:
                    st_, en_ = max(0.0, (al[0] - a) / speed - 0.1), min(dur, (al[1] - a) / speed + 0.25)
                    over.append((t0 + st_, t0 + en_, "sub", x, None))
                    c = en_
                else:
                    over.append((t0 + c, t0 + c + d_, "sub", x, None))
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
                over.append((t0 + s0, t0 + s1, "stamp", o.get("side", "R"), o.get("name", "stamp")))
        texts = [o for o in sh.get("overlay") or [] if o.get("kind") in ("text", "panel")]
        lo = 0.42 if sh.get("audio_from") else 0.15
        for k, o in enumerate(texts):
            n = len(texts)
            s0 = float(o["at"]) if o.get("at") is not None else dur * (lo + (0.97 - lo) * k / n)
            s1 = min(dur, float(o["until"])) if o.get("until") is not None else dur * (lo + (0.97 - lo) * (k + 1) / n) - 0.05
            over.append((t0 + s0, t0 + s1, "text", o.get("text", ""), None))
        # 从别的镜垫进来的录音
        for rec in sh.get("audio_from") or []:
            rs_sh = rec.get("shot")
            rt = project.chosen_take(ep, rs_sh, "video", review)
            if not rt:
                continue
            rv = project.video_path(ep, rs_sh, rt)
            rw = [(s, en) for s, en, _ in (asr.words([rv])[str(rv)] if asr.py else [])]
            if rw:
                tail = rec.get("tail")
                st = rw[-1][1] - float(tail) if tail else rw[0][0] - 0.05
                recs.append((rv, max(0.0, st), rw[-1][1] + 0.2, t0 + float(rec.get("at", 0.3)), rec.get("filter", "phone")))
        # 环境声
        bed = (project.sub("beds") or {}).get(sh.get("scene")) or (project.sub("beds") or {}).get("*")
        if bed and (project.root / bed).exists():
            beds.append((project.root / bed, t0, dur, float((project.sub("beds") or {}).get("gain_db", -18))))
        sheet.append(f"| {i + 1} | {sid} | {take} | {a:.2f}–{b:.2f}（{mode}） | {dur:.2f}s | {t0:.1f}–{t0 + dur:.1f}s | "
                     f"{'；'.join(subs) or '无'} | {'；'.join(o.get('kind') + (':' + str(o.get('text') or o.get('side'))) for o in sh.get('overlay') or []) or '无'} | {e.get('verdict', '')} |")
        t0 += dur
    if not segs:
        print(ep, "没有可用素材")
        return None
    dst = out or project.final_path(ep)
    sheet += ["", f"成片：{dst.relative_to(project.root) if dst.is_relative_to(project.root) else dst}，总长约 {t0:.1f} 秒，{len(segs)} 镜。"]
    (project.ep_dir(ep) / "剪辑单.md").write_text("\n".join(sheet), encoding="utf-8")
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
    for k, (s, e_, kind, t, name) in enumerate(over):
        png = tmp / f"ov_{k}.png"
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
        elif kind == "sub":
            if not sub_font:
                continue
            size = int(subcfg["size"] if len(t) <= int(subcfg["long_threshold"]) else subcfg["size_long"])
            w, h = text_png(t, png, size, sub_font, int(subcfg["max_width"]))
            x, y = str((W - w) // 2), str(H - h - 40)
            fin = fout = 0.15
        else:
            if not sub_font:
                continue
            w, h = text_png(t, png, 58, sub_font, int(subcfg["max_width"]))
            x, y = str((W - w) // 2), str(int(H * 0.30 - h / 2))
            fin = fout = 0.2
        inputs += ["-loop", "1", "-t", f"{e_ + 1:.2f}", "-i", str(png)]
        idx, n_in = n_in, n_in + 1
        f.append(f"[{idx}:v]format=rgba,fade=t=in:st={s:.2f}:d={fin}:alpha=1,fade=t=out:st={max(s, e_ - fout):.2f}:d={fout}:alpha=1[o{k}]")
        f.append(f"{last}[o{k}]overlay=x='{x}':y='{y}':enable='between(t,{s:.2f},{e_:.2f})'[w{k}]")
        last = f"[w{k}]"
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
    if extra:
        f.append(f"[ac]{''.join(extra)}amix=inputs={len(extra) + 1}:normalize=0:duration=first[am]")
        amap = "[am]"
    dst.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-y", "-v", "error", *inputs, "-filter_complex", ";".join(f), "-map", last, "-map", amap, "-r", str(FPS),
                    "-c:v", "libx264", "-crf", "17", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(dst)], check=True)
    if loudnorm:
        g = float(project.get("loudness")) - lufs(dst)
        tmp_out = str(dst) + ".tmp.mp4"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(dst), "-c:v", "copy", "-af", f"volume={g:.2f}dB,alimiter=limit=0.8:level=false",
                        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", tmp_out], check=True)
        os.replace(tmp_out, dst)
    print(dst, round(t0, 2), f"{len(segs)} shots, {sum(1 for o in over if o[2] == 'stamp')} stamps")
    return dst


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("project")
    ap.add_argument("episode")
    ap.add_argument("--out")
    ap.add_argument("--no-loudnorm", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    cut(Project(a.project), a.episode, Path(a.out) if a.out else None, not a.no_loudnorm, a.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
