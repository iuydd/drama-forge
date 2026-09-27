#!/usr/bin/env python3
"""fal 队列接口的视频客户端（MiniMax H3 Max / H3 Max Turbo 等 fal 托管模型）。

沿用 h3_client.Client 的账本（脚本/jobs.jsonl：submission_intent → submitted → collected）、提交锁、STOP/DEADLINE、
未决提交阻断与 collect 收回；只替换提交、轮询、下载三处。

- 密钥只从环境变量 FAL_KEY 读，不落盘、不打印、不写进账本。
- 端点：drama.json 的 profiles.video 写 fal 端点 ID（例 "minimax/h3-max-turbo/image-to-video"），
  profiles.video_res 写 480P / 768P / 1080P；video_provider 写 "fal" 时 produce.py videos 走本客户端。
- 时长只接受整数 5–15 秒：镜头秒数向上取整、不足 5 取 5（剪辑再按取用区间收）。
- prompt_expansion_mode 固定 disabled：提示词由分镜写定，扩写会改动逐字台词。
- 起始帧以 data URI 内联上传。
- 超分（drama.json 的 video_upscale，用户 2026-09-26 定方案 A：480P 生成 + ByteDance Upscaler 到 1080p）：
  生成结果下载后，用它的 CDN 地址提交超分端点，target_fps 锁 24；原片存 视频/_src/，音轨从原片 remux 回成片。
  超分失败时成片位置先放原片并报错，之后用 upscale 子命令补。

  fal_client.py collect --root <项目> --job <request_id> --endpoint <端点> --out OUT
  fal_client.py upscale --root <项目> --src 视频/_src/X.mp4 --out 视频/X.mp4
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from h3_client import Client, PendingElsewhere, SubmissionUnknown, rec_channel  # noqa: E402

QUEUE = "https://queue.fal.run"
UPSCALE_DEFAULT = {"endpoint": "fal-ai/bytedance-upscaler/upscale/video", "target_resolution": "1080p",
                   "target_fps": 24, "enhancement_tier": "standard", "enhancement_preset": "aigc", "fidelity": "high"}


def upscale_config(project_cfg) -> dict | None:
    """drama.json 的 video_upscale：true 用默认；对象覆盖默认字段；缺省或 false 不超分。"""
    if not project_cfg:
        return None
    return {**UPSCALE_DEFAULT, **(project_cfg if isinstance(project_cfg, dict) else {})}


class FalClient(Client):
    def __init__(self, endpoint: str, root: Path | None = None, log_dir: Path | None = None, poll: float = 5.0,
                 upscale: dict | None = None):
        super().__init__(api=QUEUE, token="", root=root, poll=poll, log_dir=log_dir, channel="fal")
        self.endpoint = endpoint.strip("/")
        self.upscale = upscale
        key = os.environ.get("FAL_KEY")
        self.s.headers.pop("Authorization", None)
        if key:
            self.s.headers["Authorization"] = "Key " + key

    def require_token(self) -> None:
        if not self.s.headers.get("Authorization"):
            raise SystemExit("缺 FAL_KEY（只从环境变量读，不要写进文件）")

    def wait_idle(self) -> None:  # fal 自带队列；串行由本进程逐镜「提交 → 等完 → 下载」保证
        return

    def _base(self) -> str:
        # 查询与结果 URL 用模型根路径（owner/model），不带 /image-to-video 这类子路径
        return f"{QUEUE}/{'/'.join(self.endpoint.split('/')[:2])}"

    def submit_video(self, prompt: str, out: Path, frame: Path, seconds: float = 5.0, profile: str | None = None,
                     res: str | None = None, seed: int = 0, aspect: str = "16:9", name: str = "",
                     image_mode: str = "keyframe") -> str:
        self.require_token()
        self.guard()
        if res not in ("480P", "768P", "1080P"):
            raise ValueError(f"fal 分辨率只接受 480P/768P/1080P，收到 {res!r}")
        dur = min(15, max(5, math.ceil(float(seconds))))
        body = {"prompt": prompt.strip(), "duration": dur, "resolution": res, "seed": int(seed),
                "prompt_expansion_mode": "disabled", "image_url": self._data_uri(frame)}
        name = name or out.stem
        fingerprint = hashlib.sha256(json.dumps({**body, "image_url": hashlib.sha256(Path(frame).read_bytes()).hexdigest(),
                                                 "endpoint": self.endpoint}, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        with self.submit_lock():
            unknown = self.unresolved()
            if unknown:
                raise SubmissionUnknown("先对账未决提交，再继续生产：" + ", ".join(r["request_id"] for r in unknown))
            pending = self.pending(name)
            if pending and rec_channel(pending) != self.channel:
                raise PendingElsewhere(rec_channel(pending), pending)
            if pending:
                if pending.get("kind") != "video" or Path(pending["out"]).resolve() != out.resolve():
                    raise SubmissionUnknown("同名未收回任务与当前输入不同；先 collect 原任务，不重新提交")
                return pending["job"]
            self.guard()
            request_id = uuid.uuid4().hex
            intent = {"request_id": request_id, "status": "submission_intent", "name": name, "kind": "video",
                      "out": str(out.resolve()), "fingerprint": fingerprint, "profile": self.endpoint, "res": res}
            self._append(intent)
            try:
                r = self.s.post(f"{QUEUE}/{self.endpoint}", json=body, timeout=120)
                r.raise_for_status()
                jid = r.json()["request_id"]
                if not isinstance(jid, str) or not jid.strip():
                    raise ValueError("missing request_id")
            except (requests.RequestException, KeyError, ValueError, TypeError) as exc:
                self._append({**intent, "status": "submission_unknown", "error_type": type(exc).__name__})
                raise SubmissionUnknown(f"提交结果未知：{request_id}；先查 fal 请求记录并 reconcile，禁止直接重投") from exc
            self._log(name, "video", {"profile": self.endpoint, "res": res, "seconds": dur, "seed": int(seed),
                                      "prompt": body["prompt"], "images": [1]},
                      jid, out, request_id=request_id, fingerprint=fingerprint)
            return jid

    def wait_job(self, jid: str, poll: float | None = None) -> dict:
        while True:
            st = self.rget(f"{self._base()}/requests/{jid}/status").json()
            if st.get("status") == "COMPLETED":
                res = self.s.get(f"{self._base()}/requests/{jid}", timeout=60)
                if res.status_code >= 400:
                    self._mark(jid, "failed", Path("-"), {"http": res.status_code})
                    raise RuntimeError(f"fal failed {jid}: HTTP {res.status_code} {res.text[:300]}")
                job = res.json()
                job["id"] = jid
                return job
            time.sleep(poll or self.poll)

    def download(self, job: dict, kind: str, out: Path) -> Path:
        jid = job["id"]
        url = ((job.get("video") or {}).get("url")) or ""
        if not url:
            self._mark(jid, "download_failed", Path(out))
            raise RuntimeError(f"{jid}: 结果里没有 video.url")
        data = requests.get(url, timeout=300).content  # CDN 地址，不带密钥
        out = Path(out)
        if not data or b"ftyp" not in data[:64]:
            self._mark(jid, "download_failed", out)
            raise RuntimeError(f"{jid}: 下载内容不是 mp4")
        out.parent.mkdir(parents=True, exist_ok=True)
        if self.upscale:
            src = out.parent / "_src" / out.name
            src.parent.mkdir(parents=True, exist_ok=True)
            _atomic_write(src, data)
            _atomic_write(out, data)  # 超分失败时成片位置至少有原片
            self._mark(jid, "collected", out)
            self.upscale_video(url, src, out)
            return out
        _atomic_write(out, data)
        self._mark(jid, "collected", out)
        return out

    def upscale_video(self, src_url: str, src: Path, out: Path) -> Path:
        """超分 src_url（fal CDN 地址或 data URI）→ out；音轨从 src 原片 remux，避免超分端点丢音或改音。"""
        self.require_token()
        cfg = dict(self.upscale or UPSCALE_DEFAULT)
        ep = cfg.pop("endpoint").strip("/")
        body = {"video_url": src_url, **cfg}
        r = self.s.post(f"{QUEUE}/{ep}", json=body, timeout=120)
        r.raise_for_status()
        rid = r.json()["request_id"]
        base = f"{QUEUE}/{'/'.join(ep.split('/')[:2])}"
        while True:
            st = self.rget(f"{base}/requests/{rid}/status").json()
            if st.get("status") == "COMPLETED":
                break
            time.sleep(self.poll)
        res = self.s.get(f"{base}/requests/{rid}", timeout=60)
        if res.status_code >= 400:
            raise RuntimeError(f"超分失败 {rid}: HTTP {res.status_code} {res.text[:300]}；成片位置是原片，用 upscale 子命令补")
        url = ((res.json().get("video") or {}).get("url")) or ""
        data = requests.get(url, timeout=600).content if url else b""
        if not data or b"ftyp" not in data[:64]:
            raise RuntimeError(f"超分结果不是 mp4 {rid}；成片位置是原片，用 upscale 子命令补")
        up = out.with_name(out.stem + ".up.part.mp4")
        up.write_bytes(data)
        mux = out.with_name(out.stem + ".mux.part.mp4")
        cmd = ["ffmpeg", "-y", "-v", "error", "-i", str(up), "-i", str(src), "-map", "0:v:0", "-map", "1:a?",
               "-c", "copy", "-shortest", str(mux)]
        if shutil.which("ffmpeg") and subprocess.run(cmd).returncode == 0:
            os.replace(mux, out)
            up.unlink(missing_ok=True)
        else:
            mux.unlink(missing_ok=True)
            os.replace(up, out)
        self._append({"request_id": rid, "status": "upscaled", "name": out.stem, "kind": "upscale",
                      "out": str(out.resolve()), "src": str(src.resolve()), "profile": ep,
                      "billed_seconds": res.json().get("duration"), "sha256": _sha256(out)})
        return out


def _sha256(path: Path) -> str:
    import hashlib
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def _atomic_write(path: Path, data: bytes) -> None:
    tmp = path.with_suffix(path.suffix + ".part")
    tmp.write_bytes(data)
    os.replace(tmp, path)


class FalImageClient(FalClient):
    """fal 图片编辑端点（例 alibaba/qwen-image-3/edit）：起始帧 = 提示词 + 1–3 张参考图（按 frame_refs 顺序 = image 1/2/3）。"""

    SIZES = {"16:9": {"1K": (1344, 768), "2K": (2048, 1152)}, "9:16": {"1K": (768, 1344), "2K": (1152, 2048)},
             "1:1": {"1K": (1024, 1024), "2K": (2048, 2048)}}

    def submit_image(self, prompt: str, out: Path, profile: str | None = None, res: str | None = None, seed: int = 0,
                     refs: list[Path] | None = None, aspect: str = "16:9", name: str = "") -> str:
        self.require_token()
        self.guard()
        refs = list(refs or [])
        t2i = self.endpoint.endswith("text-to-image")
        if not refs and not t2i:
            raise ValueError("fal 图片编辑端点至少要 1 张参考图（起始帧挂底板或身份图）；无参考的参考图用文生图端点")
        if len(refs) > 3:
            raise ValueError(f"fal 图片编辑端点最多 3 张参考图，收到 {len(refs)}：分镜里删到 3 张")
        w, h = self.SIZES.get(aspect or "16:9", self.SIZES["16:9"]).get(res or "1K", (1344, 768))
        # 提示词里的 Picture N 改成该端点的记法 image N
        import re as _re
        text = _re.sub(r"\bPicture (\d)", r"image \1", prompt.strip())
        body = {"prompt": text[:5000], "seed": int(seed),
                "image_size": {"width": w, "height": h}, "enable_prompt_expansion": False,
                "num_images": 1, "output_format": "png"}
        if not t2i:
            body["image_urls"] = [self._data_uri(p) for p in refs]
        name = name or out.stem
        fingerprint = hashlib.sha256(json.dumps({"prompt": body["prompt"], "seed": seed, "size": [w, h],
                                                 "refs": [hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in refs],
                                                 "endpoint": self.endpoint}, sort_keys=True).encode()).hexdigest()
        with self.submit_lock():
            unknown = self.unresolved()
            if unknown:
                raise SubmissionUnknown("先对账未决提交，再继续生产：" + ", ".join(r["request_id"] for r in unknown))
            pending = self.pending(name)
            if pending and rec_channel(pending) != self.channel:
                raise PendingElsewhere(rec_channel(pending), pending)
            if pending:
                if pending.get("kind") != "image" or Path(pending["out"]).resolve() != out.resolve():
                    raise SubmissionUnknown("同名未收回任务与当前输入不同；先 collect 原任务，不重新提交")
                return pending["job"]
            self.guard()
            request_id = uuid.uuid4().hex
            intent = {"request_id": request_id, "status": "submission_intent", "name": name, "kind": "image",
                      "out": str(out.resolve()), "fingerprint": fingerprint, "profile": self.endpoint, "res": res}
            self._append(intent)
            try:
                r = self.s.post(f"{QUEUE}/{self.endpoint}", json=body, timeout=120)
                r.raise_for_status()
                jid = r.json()["request_id"]
                if not isinstance(jid, str) or not jid.strip():
                    raise ValueError("missing request_id")
            except (requests.RequestException, KeyError, ValueError, TypeError) as exc:
                self._append({**intent, "status": "submission_unknown", "error_type": type(exc).__name__})
                raise SubmissionUnknown(f"提交结果未知：{request_id}；先查 fal 请求记录并 reconcile，禁止直接重投") from exc
            self._log(name, "image", {"profile": self.endpoint, "res": res, "seed": int(seed), "prompt": body["prompt"],
                                      "images": refs}, jid, out, request_id=request_id, fingerprint=fingerprint)
            return jid

    def download(self, job: dict, kind: str, out: Path) -> Path:
        if kind != "image":
            return super().download(job, kind, out)
        jid = job["id"]
        imgs = job.get("images") or []
        url = (imgs[0] or {}).get("url") if imgs else ""
        if not url:
            self._mark(jid, "download_failed", Path(out))
            raise RuntimeError(f"{jid}: 结果里没有 images[0].url")
        data = requests.get(url, timeout=120).content
        out = Path(out)
        if not data.startswith(b"\x89PNG") and not data.startswith(b"\xff\xd8") and data[:4] != b"RIFF":
            self._mark(jid, "download_failed", out)
            raise RuntimeError(f"{jid}: 下载内容不是图片")
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp = out.with_suffix(out.suffix + ".part")
        tmp.write_bytes(data)
        os.replace(tmp, out)
        self._mark(jid, "collected", out)
        return out

    def image(self, prompt: str, out: Path, **kw) -> tuple[str, Path]:
        jid = self.submit_image(prompt, out, **kw)
        job = self.wait_job(jid)
        return jid, self.download(job, "image", out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("collect")
    c.add_argument("--root", required=True)
    c.add_argument("--job", required=True)
    c.add_argument("--endpoint", required=True)
    c.add_argument("--out", required=True)
    u = sub.add_parser("upscale", help="补超分：原片 → 1080p（配置取 drama.json 的 video_upscale，缺省用默认）")
    u.add_argument("--root", required=True)
    u.add_argument("--src", required=True)
    u.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    root = Path(a.root)
    if a.cmd == "upscale":
        cfg = json.loads((root / "drama.json").read_text(encoding="utf-8")).get("video_upscale") or True
        cl = FalClient("-", root=root, log_dir=root / "脚本", upscale=upscale_config(cfg))
        src = Path(a.src)
        print("UPSCALED", cl.upscale_video("data:video/mp4;base64," + base64.b64encode(src.read_bytes()).decode(), src, Path(a.out)))
        return 0
    cfg = json.loads((root / "drama.json").read_text(encoding="utf-8")).get("video_upscale") \
        if (root / "drama.json").exists() else None
    cl = FalClient(a.endpoint, root=root, log_dir=root / "脚本", upscale=upscale_config(cfg))
    cl.require_token()
    print("COLLECTED", a.job, cl.collect(a.job, "video", Path(a.out)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
