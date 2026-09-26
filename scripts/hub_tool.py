#!/usr/bin/env python3
"""项目总控小工具：多剧进度总览、导出制作资料、成片交付测量、接镜调色。

  hub_tool.py overview <目录>... [--json] [--html PATH]      扫描目录下的 drama.json 项目，列每集进度和下一步
  hub_tool.py export <项目> --out <项目外目录> [--episode EP001 ...] [--media none|final|all] [--overwrite]
  hub_tool.py measure <项目> <EP> [--write]                  成片只报数字：时长、画幅帧率、LUFS/真峰、静音占比、逐镜亮度与蓝减红
  hub_tool.py grade <项目> <EP>                              按 审查/<EP>-grade.json 逐镜校色、加颗粒，输出 成片/<EP>_graded.mp4

说明见 references/project-hub.md 与 references/edit-and-delivery.md §5b、§7。本工具不提交生成任务、不做 git。
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import Project  # noqa: E402

EXPORT_TOOL = "drama-forge hub_tool export"
SECRET_HINTS = ("token", "secret", "apikey", "api_key", ".key", ".env", "credential", "password")
GRADE_LIMITS = {"brightness": (-0.25, 0.25), "saturation": (0.0, 2.0), "warmth": (-30.0, 30.0)}


# ---- overview -------------------------------------------------------------------
def find_projects(paths: list[str]) -> list[Path]:
    found: list[Path] = []
    for raw in paths:
        base = Path(raw).expanduser().resolve()
        cands = [base] + [p for p in sorted(base.glob("*")) if p.is_dir()] + [p for p in sorted(base.glob("*/*")) if p.is_dir()]
        for c in cands:
            if any(part.startswith(".") for part in c.relative_to(base).parts):
                continue
            if (c / "drama.json").is_file() and c not in found:
                found.append(c)
    return found


def overview(paths: list[str]) -> list[dict]:
    from project_tool import next_step, status
    rows = []
    for root in find_projects(paths):
        try:
            pr = Project(root)
            st = status(pr)
            rows.append({"project": str(root), "title": st["title"], "系列简报": st["系列简报"], "情绪集纲": st["情绪集纲"],
                         "参考图": f"{sum(st['参考图'].values())}/{len(st['参考图'])}", "episodes": st["episodes"],
                         "next": next_step(pr)})
        except (SystemExit, Exception) as e:  # 一部剧读不了不影响其他剧
            rows.append({"project": str(root), "title": root.name, "error": str(e)})
    return rows


def _ep_line(ep: str, e: dict) -> str:
    g = e.get("门")
    return (f"{ep} 剧本{'✓' if e.get('剧本') else '✗'} 视觉{'✓' if e.get('视觉设定') else '✗'} shots{'✓' if e.get('shots.json') else '✗'} "
            f"门{(str(g['errors']) + 'E/' + str(g['warns']) + 'W') if g else '-'} 镜{e.get('镜数', '-')} 帧{e.get('起始帧', '-')} "
            f"预演{'✓' if e.get('预演') else '✗'} 视频{e.get('视频', '-')} 审片{e.get('审片', '-')} 成片{'✓' if e.get('成片') else '✗'}")


def _cell(e: dict, key: str) -> str:
    v = e.get(key)
    if isinstance(v, bool) or v is None:          # 布尔项：有没有
        ok, text = bool(v), "✓" if v else "✗"
    else:                                          # 计数项：做完几镜 / 共几镜
        total = e.get("镜数") or 0
        ok, text = total > 0 and v >= total, f"{v}/{total}"
    return f"<td class='{'ok' if ok else 'no'}'>{html.escape(text)}</td>"


def overview_html(rows: list[dict]) -> str:
    cards = []
    for r in rows:
        if "error" in r:
            cards.append(f"<section class='card'><h2>{html.escape(r['title'])}</h2><p class='err'>读不了：{html.escape(r['error'])}</p></section>")
            continue
        eps = "".join(
            f"<tr><th>{html.escape(ep)}</th>" + "".join(_cell(e, k) for k in ("剧本", "视觉设定", "shots.json", "起始帧", "预演", "视频", "审片", "成片")) + "</tr>"
            for ep, e in r["episodes"].items())
        cards.append(
            f"<section class='card'><h2>{html.escape(r['title'])}</h2><p class='path'>{html.escape(r['project'])}</p>"
            f"<p>系列简报 {'✓' if r['系列简报'] else '✗'} · 情绪集纲 {'✓' if r['情绪集纲'] else '✗'} · 参考图 {html.escape(r['参考图'])}</p>"
            f"<div class='scroll'><table><tr><th></th><th>剧本</th><th>视觉</th><th>shots</th><th>起始帧</th><th>预演</th><th>视频</th><th>审片</th><th>成片</th></tr>{eps}</table></div>"
            f"<p class='next'>下一步：{html.escape(r['next'])}</p></section>")
    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>短剧进度总览</title><style>
:root{{--bg:#f7f6f3;--fg:#1f1f1c;--muted:#6b6a64;--card:#fff;--line:#e3e1da;--ok:#1d7a46;--no:#b3452f}}
@media (prefers-color-scheme: dark){{:root{{--bg:#171715;--fg:#ecebe6;--muted:#a09f98;--card:#22221f;--line:#34332f;--ok:#5cc08a;--no:#e3876f}}}}
body{{margin:0;padding:24px 16px;background:var(--bg);color:var(--fg);font:15px/1.55 -apple-system,"PingFang SC","Noto Sans CJK SC",sans-serif}}
h1{{font-size:20px;margin:0 0 4px}} .stamp{{color:var(--muted);margin:0 0 20px}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px;margin:0 0 16px;max-width:960px}}
h2{{font-size:17px;margin:0}} .path{{color:var(--muted);font-size:12px;word-break:break-all}} .scroll{{overflow-x:auto}}
table{{border-collapse:collapse;font-size:13px}} th,td{{padding:4px 8px;border-bottom:1px solid var(--line);text-align:center;white-space:nowrap}}
.ok{{color:var(--ok)}} .no{{color:var(--no)}} .err{{color:var(--no)}} .next{{margin-bottom:0}}
</style></head><body><h1>短剧进度总览</h1><p class="stamp">生成于 {time.strftime('%Y-%m-%d %H:%M')}（只读快照，重新运行 hub_tool.py overview --html 刷新）</p>
{''.join(cards) or '<p>没有找到 drama.json 项目。</p>'}</body></html>
"""


# ---- export ---------------------------------------------------------------------
def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _looks_secret(path: Path) -> bool:
    name = path.name.lower()
    return any(k in name for k in SECRET_HINTS)


def export_files(project: Project, episodes: list[str], media: str) -> list[Path]:
    root = project.root
    picked: list[Path] = []

    def add(p: Path) -> None:
        if p.is_file() and not p.is_symlink() and not _looks_secret(p):
            picked.append(p)

    for p in sorted((root / "项目开发").glob("*.md")):
        add(p)
    add(project.refs_path)
    if media != "none":
        for p in sorted(project.refs_dir.glob("*.png")):   # 只取顶层参考图；子目录（原始真人素材等）不导出
            add(p)
    for ep in episodes:
        d = project.ep_dir(ep)
        for p in sorted(d.glob("*.md")) + [d / "shots.json"]:
            add(p)
        if media != "none":
            for p in sorted((d / "成片").glob("*.mp4")):
                add(p)
        if media == "all":
            for sub in ("起始帧", "视频", "配音"):
                for p in sorted((d / sub).glob("*")):
                    add(p)
        rv = project.review_dir
        for p in sorted(rv.glob(f"{ep}-*")):
            if p.suffix in (".md", ".json") or (media == "all" and p.suffix in (".mp4", ".jpg")):
                add(p)
        if media == "all":
            for p in sorted((rv / f"{ep}-sheets").glob("*.jpg")):
                add(p)
    return picked


def export(project: Project, out: Path, episodes: list[str] | None = None, media: str = "final", overwrite: bool = False) -> Path:
    root = project.root
    out = out.expanduser().resolve()
    if out == root or root in out.parents:
        raise SystemExit(f"--out 必须在项目之外：{out}")
    if out.exists() and any(out.iterdir()):
        man = out / "manifest.json"
        ours = man.is_file() and json.loads(man.read_text(encoding="utf-8")).get("tool") == EXPORT_TOOL
        if not overwrite:
            raise SystemExit(f"{out} 已存在且非空；要覆盖旧的导出加 --overwrite")
        if not ours:
            raise SystemExit(f"{out} 不是本工具导出的目录（没有对应 manifest.json），拒绝覆盖")
        shutil.rmtree(out)
    eps = episodes or project.episodes
    unknown = [e for e in eps if e not in project.episodes]
    if unknown:
        raise SystemExit(f"不在本项目的集：{unknown}")
    files = export_files(project, eps, media)
    out.mkdir(parents=True, exist_ok=True)
    cfg = dict(project.cfg)
    cfg["api_base"] = None                      # 中转地址是私有运行配置，不随资料外发
    (out / "drama.json").write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    rows = [{"path": "drama.json", "bytes": (out / "drama.json").stat().st_size, "sha256": _sha256(out / "drama.json")}]
    for src in files:
        rel = src.relative_to(root)
        dst = out / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        rows.append({"path": rel.as_posix(), "bytes": dst.stat().st_size, "sha256": _sha256(dst)})
    manifest = {
        "tool": EXPORT_TOOL, "title": project.title, "exported_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "episodes": eps, "media": media,
        "asserts_approval": False,   # 当前状态快照：不声称任何审查通过或用户接受
        "excluded": ["脚本/（任务账本、ids.log、ASR 缓存、渲染提示词）", "参考图/ 子目录（原始素材）", "STOP、隐藏文件、疑似凭据文件",
                     "drama.json 的 api_base"],
        "files": rows,
    }
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "checksums.sha256").write_text("".join(f"{r['sha256']}  {r['path']}\n" for r in rows), encoding="utf-8")
    return out


# ---- 剪辑单解析 -------------------------------------------------------------------
def cut_rows(project: Project, ep: str) -> list[dict]:
    """从 cut.py 写的 剪辑单.md 取每段的镜号和成片区间；起点用各段时长累加（两位小数），比"成片位置"列更准。"""
    sheet = project.ep_dir(ep) / "剪辑单.md"
    if not sheet.is_file():
        raise SystemExit(f"没有 {sheet}；先运行 cut.py")
    rows, t0 = [], 0.0
    for line in sheet.read_text(encoding="utf-8").splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 6 or not cells[0].isdigit():
            continue
        m = re.match(r"([\d.]+)s", cells[4])
        if not m:
            continue
        dur = float(m.group(1))
        rows.append({"n": int(cells[0]), "shot": cells[1], "take": cells[2], "start": round(t0, 3), "end": round(t0 + dur, 3)})
        t0 += dur
    return rows


def _need(tool: str) -> str:
    path = shutil.which(tool)
    if not path:
        raise SystemExit(f"需要 {tool} 在 PATH 上；没有就不测，不能写成通过")
    return path


# ---- measure --------------------------------------------------------------------
def _mean_colour(ffmpeg: str, film: Path, start: float, dur: float) -> tuple[float, float] | None:
    r = subprocess.run([ffmpeg, "-v", "error", "-ss", f"{start:.3f}", "-t", f"{max(dur, 0.05):.3f}", "-i", str(film),
                        "-vf", "fps=2,scale=96:-2", "-pix_fmt", "rgb24", "-f", "rawvideo", "-"], capture_output=True)
    raw = r.stdout
    if r.returncode != 0 or len(raw) < 3:
        return None
    n = len(raw) // 3
    red, green, blue = (sum(raw[i::3][:n]) / n for i in range(3))
    return 0.299 * red + 0.587 * green + 0.114 * blue, blue - red


def measure(project: Project, ep: str) -> dict:
    ffmpeg, ffprobe = _need("ffmpeg"), _need("ffprobe")
    film = project.final_path(ep)
    if not film.is_file():
        raise SystemExit(f"没有成片 {film}")
    pr = json.loads(subprocess.run([ffprobe, "-v", "error", "-select_streams", "v:0", "-show_entries",
                                    "stream=width,height,r_frame_rate:format=duration", "-of", "json", str(film)],
                                   capture_output=True, text=True, check=True).stdout)
    st, dur = pr["streams"][0], float(pr["format"]["duration"])
    num, den = (st.get("r_frame_rate") or "0/1").split("/")
    target = project.get("target_seconds")
    res: dict = {"成片": str(film.relative_to(project.root)), "实测时长": round(dur, 2),
                 "目标时长": target, "与目标差": round(dur - float(target), 2) if target else "未测（drama.json 没写 target_seconds）",
                 "画幅": f"{st['width']}×{st['height']}", "画幅是否等于项目设定": [st["width"], st["height"]] == [project.get("width"), project.get("height")],
                 "帧率": round(float(num) / float(den or 1), 3), "帧率是否等于项目设定": abs(float(num) / float(den or 1) - float(project.get("fps", 24))) < 0.01}
    eb = subprocess.run([ffmpeg, "-hide_banner", "-nostats", "-i", str(film), "-af", "ebur128=peak=true", "-f", "null", "-"],
                        capture_output=True, text=True).stderr
    summary = eb[eb.rfind("Summary:"):] if "Summary:" in eb else ""
    m_i = re.search(r"I:\s+(-?[\d.]+) LUFS", summary)
    m_tp = re.search(r"True peak:\s+Peak:\s+(-?[\d.]+|-inf) dBFS", summary)
    res["实测响度 LUFS"] = float(m_i.group(1)) if m_i else "未测（ebur128 没有返回 Summary）"
    res["实测真峰 dBTP"] = (float(m_tp.group(1)) if m_tp.group(1) != "-inf" else "-inf") if m_tp else "未测"
    res["交付响度目标"] = project.get("loudness", -16.0)
    sd = subprocess.run([ffmpeg, "-hide_banner", "-nostats", "-i", str(film), "-af", "silencedetect=n=-50dB:d=0.1", "-f", "null", "-"],
                        capture_output=True, text=True).stderr
    silent = sum(float(x) for x in re.findall(r"silence_duration:\s*([\d.]+)", sd))
    if "silence_start" in sd and silent == 0.0 and "silence_end" not in sd:   # 一直静音到片尾
        silent = dur
    res["静音窗口占比"] = round(silent / dur, 4) if dur else "未测"
    try:
        rows = cut_rows(project, ep)
    except SystemExit as e:
        rows, res["逐镜色彩"] = [], f"未测（{e}）"
    if rows:
        out = []
        for r in rows:
            c = _mean_colour(ffmpeg, film, r["start"], r["end"] - r["start"])
            out.append({"镜": r["shot"], "成片区间": [r["start"], r["end"]],
                        **({"平均亮度": round(c[0], 1), "蓝减红": round(c[1], 1)} if c else {"测量": "未测（取不到画面）"})})
        res["逐镜色彩"] = out
    res["台词完整性"] = "未测（整片 ASR 对全集台词表，edit-and-delivery §7 第 2 步）"
    res["画内文字"] = "未测（1fps 接触表逐张看，§7 第 1 步）"
    res["边界帧"] = "未测（每个剪辑点前后抽帧看黑帧/白帧/半渲染帧，§7）"
    res["说明"] = "只报数字，不是质量结论"
    return res


# ---- grade ----------------------------------------------------------------------
def load_grade(project: Project, ep: str) -> dict:
    path = project.review_dir / f"{ep}-grade.json"
    if not path.is_file():
        raise SystemExit(f"没有 {path}；格式见 edit-and-delivery §5b")
    cfg = json.loads(path.read_text(encoding="utf-8"))
    for sid, corr in (cfg.get("shots") or {}).items():
        for k, v in corr.items():
            if k not in GRADE_LIMITS:
                raise SystemExit(f"{sid}: 不认识的校正项 {k}（只支持 {sorted(GRADE_LIMITS)}）")
            lo, hi = GRADE_LIMITS[k]
            if not lo <= float(v) <= hi:
                raise SystemExit(f"{sid}: {k}={v} 超出工具范围 {lo}…{hi}；更大的校正用外部调色工具")
    g = cfg.get("grain")
    if g is not None and not 0 <= float(g) <= 20:
        raise SystemExit(f"grain={g} 超出 0–20")
    return cfg


def grade_filter(cfg: dict, rows: list[dict]) -> str:
    by_shot = {r["shot"]: r for r in rows}
    stages = []
    for sid, corr in (cfg.get("shots") or {}).items():
        if sid not in by_shot:
            raise SystemExit(f"{sid} 不在当前剪辑单里（被 drop 了或镜号写错）")
        r = by_shot[sid]
        en = f"enable='between(t,{r['start']:.3f},{r['end'] - 0.001:.3f})'"
        eq = [f"{k}={float(corr[k]):g}" for k in ("brightness", "saturation") if k in corr]
        if eq:
            stages.append("eq=" + ":".join(eq) + ":" + en)
        if corr.get("warmth"):
            a = float(corr["warmth"]) / 100.0
            stages.append(f"colorbalance=rm={a:.4f}:bm={-a:.4f}:{en}")
    if cfg.get("grain"):
        stages.append(f"noise=alls={float(cfg['grain']):g}:allf=t+u")
    return ",".join(stages)


def grade(project: Project, ep: str, dry: bool = False) -> Path | str:
    cfg = load_grade(project, ep)
    vf = grade_filter(cfg, cut_rows(project, ep))
    if not vf:
        raise SystemExit("grade.json 里没有任何校正")
    if dry:
        return vf
    ffmpeg = _need("ffmpeg")
    film = project.final_path(ep)
    if not film.is_file():
        raise SystemExit(f"没有成片 {film}")
    dst = film.with_name(f"{film.stem}_graded.mp4")
    subprocess.run([ffmpeg, "-v", "error", "-y", "-i", str(film), "-vf", vf, "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p",
                    "-c:a", "copy", str(dst)], check=True)
    return dst


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    o = sub.add_parser("overview")
    o.add_argument("dirs", nargs="+")
    o.add_argument("--json", action="store_true")
    o.add_argument("--html")
    x = sub.add_parser("export")
    x.add_argument("dir")
    x.add_argument("--out", required=True)
    x.add_argument("--episode", action="append")
    x.add_argument("--media", choices=("none", "final", "all"), default="final")
    x.add_argument("--no-media", action="store_true", help="等同 --media none")
    x.add_argument("--overwrite", action="store_true")
    m = sub.add_parser("measure")
    m.add_argument("dir")
    m.add_argument("ep")
    m.add_argument("--write", action="store_true")
    g = sub.add_parser("grade")
    g.add_argument("dir")
    g.add_argument("ep")
    g.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    if a.cmd == "overview":
        rows = overview(a.dirs)
        if a.html:
            Path(a.html).write_text(overview_html(rows), encoding="utf-8")
            print("wrote", a.html)
        if a.json:
            print(json.dumps(rows, ensure_ascii=False, indent=2))
        elif not a.html:
            for r in rows:
                print(f"{r['title']}  ({r['project']})")
                if "error" in r:
                    print("  读不了：", r["error"])
                    continue
                print(f"  系列简报{'✓' if r['系列简报'] else '✗'} 情绪集纲{'✓' if r['情绪集纲'] else '✗'} 参考图{r['参考图']}")
                for ep, e in r["episodes"].items():
                    print("  " + _ep_line(ep, e))
                print("  下一步：", r["next"].replace("\n", "\n    "))
        return 0
    pr = Project(a.dir)
    if a.cmd == "export":
        out = export(pr, Path(a.out), a.episode, "none" if a.no_media else a.media, a.overwrite)
        print("exported", out)
    elif a.cmd == "measure":
        res = measure(pr, a.ep)
        text = json.dumps(res, ensure_ascii=False, indent=2)
        if a.write:
            (pr.review_dir / f"{a.ep}-交付测量.json").write_text(text, encoding="utf-8")
        print(text)
    elif a.cmd == "grade":
        print(grade(pr, a.ep, a.dry_run))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
