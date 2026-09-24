#!/usr/bin/env python3
"""H3 Studio 自建中转的客户端：图片、视频、收回、状态。

实战规则（来自已跑通的项目）：
- 串行：提交前等 /api/status 空闲（running 为空或 0，且 queued 为 0）；一次只有一个任务在飞。
- 只重试 GET（查询、下载），绝不重发 POST；网络断开时一直等，不放弃已提交的任务。
- 每次提交立即把任务号写进 ids.log 和 jobs.jsonl；中断后用 collect 按任务号收回，不盲目重发。
- 项目根目录有 STOP 文件就退出；环境变量 DEADLINE=YYYYmmddHHMM 到点退出。
- token 只从环境变量 H3_STUDIO_TOKEN 读，不落盘、不打印、不写进任何文件。

命令行：
  h3_client.py status  [--api URL]
  h3_client.py config  [--api URL]
  h3_client.py image   --prompt-file P --out OUT [--profile qwen21_bf16] [--res 1K] [--seed N] [--ref PNG ...] [--aspect 16:9]
  h3_client.py video   --prompt-file P --out OUT --frame PNG [--seconds 5] [--profile fasth3] [--res 768p] [--seed N]
  h3_client.py collect --job ID --kind image|video --out OUT
  公共参数：--api URL（不给就取环境变量 H3_API；两者都没有会报错）、--root 项目根（找 STOP、写 ids.log；默认当前目录）、--name 任务名（写日志用）
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import sys
import time
from contextlib import contextmanager
from pathlib import Path

try:
    import fcntl
except ImportError:  # Windows
    fcntl = None

try:
    import requests
except ImportError:  # pragma: no cover
    raise SystemExit("缺少 requests：pip install requests")

FAILED = ("failed", "error", "cancelled", "canceled")


class Stop(SystemExit):
    """STOP 文件或 DEADLINE 触发的正常退出。"""


def _now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


class Client:
    def __init__(self, api: str | None = None, token: str | None = None, root: Path | None = None,
                 poll: float = 3.0, log_dir: Path | None = None):
        self.api = (api or os.environ.get("H3_API") or "").rstrip("/")
        self.token = token or os.environ.get("H3_STUDIO_TOKEN")
        self.root = Path(root or ".").resolve()
        self.poll = poll
        self.log_dir = Path(log_dir) if log_dir else self.root / "脚本"
        self.s = requests.Session()
        if self.token:
            self.s.headers["Authorization"] = "Bearer " + self.token

    # ---- 守门 ----------------------------------------------------------------
    def guard(self) -> None:
        """STOP 文件 / DEADLINE：在提交前检查，正在飞的任务不受影响。"""
        if (self.root / "STOP").exists():
            raise Stop("STOP")
        dl = os.environ.get("DEADLINE")
        if dl and time.strftime("%Y%m%d%H%M") >= dl:
            raise Stop("DEADLINE")

    @contextmanager
    def submit_lock(self):
        """空闲检查 + POST 用一把文件锁包住：同一台机器上两个提交者不会同时提交。"""
        self.log_dir.mkdir(parents=True, exist_ok=True)
        lock_path = self.log_dir / ".submit.lock"
        f = open(lock_path, "a+")
        try:
            if fcntl:
                fcntl.flock(f, fcntl.LOCK_EX)
            yield
        finally:
            if fcntl:
                fcntl.flock(f, fcntl.LOCK_UN)
            f.close()

    def _post(self, path: str, payload: dict, name: str, kind: str) -> str:
        try:
            r = self.s.post(self.api + path, json=payload, timeout=120)
            r.raise_for_status()
            return r.json()["id"]
        except (requests.RequestException, KeyError, ValueError) as e:
            self._mark("-", "post_failed", Path(name or "-"), extra={"kind": kind, "error": str(e)[:200]})
            raise

    def require_token(self) -> None:
        if not self.api:
            raise SystemExit("缺 H3_API：设环境变量 H3_API，或在 drama.json 写 api_base")
        if not self.token:
            raise SystemExit("缺 H3_STUDIO_TOKEN（只从环境变量读，不要写进文件）")

    # ---- HTTP ----------------------------------------------------------------
    def rget(self, path: str, timeout: float = 30, tries: int = 3000, **kw) -> requests.Response:
        """只重试 GET；网络抖动时每 10 秒重试一次，直到成功。"""
        if not self.api:
            raise SystemExit("缺 H3_API：设环境变量 H3_API，或在 drama.json 写 api_base")
        url = path if path.startswith("http") else self.api + path
        last = None
        for _ in range(tries):
            try:
                r = self.s.get(url, timeout=timeout, **kw)
                r.raise_for_status()
                return r
            except requests.RequestException as e:  # noqa: PERF203
                last = e
                time.sleep(10)
        raise SystemExit(f"network down too long: {last}")

    def status(self) -> dict:
        return self.rget("/api/status").json()

    def config(self) -> dict:
        return self.rget("/api/config").json()

    def wait_idle(self) -> None:
        while True:
            st = self.status()
            if st.get("running") in (None, 0) and st.get("queued") in (None, 0):
                return
            time.sleep(self.poll)

    # ---- 提交 ----------------------------------------------------------------
    @staticmethod
    def _data_uri(path: Path) -> str:
        return "data:image/png;base64," + base64.b64encode(Path(path).read_bytes()).decode()

    def _log(self, name: str, kind: str, payload: dict, jid: str, out: Path) -> None:
        self.log_dir.mkdir(parents=True, exist_ok=True)
        size = payload.get("res") if kind == "image" else payload.get("seconds")
        with open(self.log_dir / "ids.log", "a", encoding="utf-8") as f:
            f.write(f"{_now()} {name} {kind} {payload.get('profile')} {size} {jid} {out}\n")
        with open(self.log_dir / "jobs.jsonl", "a", encoding="utf-8") as f:
            rec = {"time": _now(), "name": name, "kind": kind, "job": jid, "out": str(out),
                   "profile": payload.get("profile"), "res": payload.get("res"), "seconds": payload.get("seconds"),
                   "seed": payload.get("seed"), "image_mode": payload.get("image_mode"), "n_images": len(payload.get("images") or []),
                   "prompt_sha256": hashlib.sha256(payload.get("prompt", "").encode("utf-8")).hexdigest()[:16],
                   "status": "submitted"}
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    def ledger(self) -> list[dict]:
        p = self.log_dir / "jobs.jsonl"
        if not p.exists():
            return []
        out = []
        for line in p.read_text(encoding="utf-8").splitlines():
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return out

    def pending(self, name: str) -> dict | None:
        """同名任务已提交但还没收回（也没标失败）→ 返回那条记录；提交前先查它，不重新 POST。"""
        subs = {}
        done = set()
        for r in self.ledger():
            if r.get("status") == "submitted" and r.get("name") == name:
                subs[r["job"]] = r
            elif r.get("status") in ("collected", "failed"):
                done.add(r.get("job"))
        for jid in reversed(list(subs)):
            if jid not in done:
                return subs[jid]
        return None

    def submit_image(self, prompt: str, out: Path, profile: str = "qwen21_bf16", res: str = "1K", seed: int = 0,
                     refs: list[Path] | None = None, aspect: str = "16:9", name: str = "") -> str:
        self.require_token()
        self.guard()
        payload = {"prompt": prompt.strip(), "profile": profile, "aspect": aspect, "res": res, "seed": int(seed),
                   "images": [self._data_uri(p) for p in (refs or [])]}
        with self.submit_lock():
            self.wait_idle()
            jid = self._post("/api/v1/image", payload, name or out.stem, "image")
            self._log(name or out.stem, "image", payload, jid, out)
        return jid

    def submit_video(self, prompt: str, out: Path, frame: Path, seconds: float = 5.0, profile: str = "fasth3",
                     res: str = "768p", seed: int = 0, aspect: str = "16:9", name: str = "",
                     image_mode: str = "keyframe") -> str:
        self.require_token()
        self.guard()
        payload = {"prompt": prompt.strip(), "profile": profile, "aspect": aspect, "res": res,
                   "seconds": float(seconds), "seed": int(seed), "image_mode": image_mode,
                   "images": [self._data_uri(frame)]}
        with self.submit_lock():
            self.wait_idle()
            jid = self._post("/api/v1/generate", payload, name or out.stem, "video")
            self._log(name or out.stem, "video", payload, jid, out)
        return jid

    # ---- 等待与收回 -----------------------------------------------------------
    def wait_job(self, jid: str, poll: float | None = None) -> dict:
        while True:
            j = self.rget(f"/api/jobs/{jid}").json()
            st = j.get("status")
            if st == "done":
                return j
            if st in FAILED:
                self._mark(jid, "failed", Path("-"))
                raise RuntimeError(f"provider failed {jid}: {j.get('error') or st}")
            time.sleep(poll or self.poll)

    def download(self, job: dict, kind: str, out: Path) -> Path:
        jid = job.get("id") or job.get("job_id")
        if kind == "image":
            url = job.get("image_download") or f"/api/jobs/{jid}/image"
            data = self.rget(url, timeout=120).content
        else:
            url = job.get("video_download") or f"/api/jobs/{jid}/video"
            data = self.rget(url, timeout=300).content
        out = Path(out)
        if not data:
            self._mark(jid, "failed", out)
            raise RuntimeError(f"{jid}: 下载到空文件")
        if kind == "image" and not (data.startswith(b"\x89PNG") or data.startswith(b"\xff\xd8") or data[:4] == b"RIFF"):
            self._mark(jid, "failed", out)
            raise RuntimeError(f"{jid}: 下载内容不是图片（前 8 字节 {data[:8]!r}）")
        if kind == "video" and b"ftyp" not in data[:64]:
            self._mark(jid, "failed", out)
            raise RuntimeError(f"{jid}: 下载内容不是 mp4（前 16 字节 {data[:16]!r}）")
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp = out.with_suffix(out.suffix + ".part")
        tmp.write_bytes(data)
        os.replace(tmp, out)
        self._mark(jid, "collected", out)
        return out

    def _mark(self, jid: str, status: str, out: Path, extra: dict | None = None) -> None:
        try:
            self.log_dir.mkdir(parents=True, exist_ok=True)
            with open(self.log_dir / "jobs.jsonl", "a", encoding="utf-8") as f:
                rec = {"time": _now(), "job": jid, "status": status, "out": str(out)}
                if extra:
                    rec.update(extra)
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except OSError:
            pass

    def collect(self, jid: str, kind: str, out: Path) -> Path:
        job = self.wait_job(jid, poll=10)
        job.setdefault("id", jid)
        return self.download(job, kind, out)

    # ---- 一步到位（先查账本里未收回的同名任务，有就收回，不重新 POST） ---------------
    def _collect_pending(self, name: str, kind: str, out: Path) -> tuple[str, Path] | None:
        rec = self.pending(name) if name else None
        if not rec:
            return None
        try:
            return rec["job"], self.collect(rec["job"], kind, out)
        except RuntimeError:
            return None  # 对方已失败：账本已标 failed，继续正常提交

    def image(self, prompt: str, out: Path, **kw) -> tuple[str, Path]:
        got = self._collect_pending(kw.get("name", ""), "image", out)
        if got:
            return got
        jid = self.submit_image(prompt, out, **kw)
        job = self.wait_job(jid)
        job.setdefault("id", jid)
        return jid, self.download(job, "image", out)

    def video(self, prompt: str, out: Path, frame: Path, **kw) -> tuple[str, Path]:
        got = self._collect_pending(kw.get("name", ""), "video", out)
        if got:
            return got
        jid = self.submit_video(prompt, out, frame, **kw)
        job = self.wait_job(jid)
        job.setdefault("id", jid)
        return jid, self.download(job, "video", out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--api")
    ap.add_argument("--root", default=".")
    ap.add_argument("--name", default="")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    sub.add_parser("config")
    im = sub.add_parser("image")
    im.add_argument("--prompt-file", required=True)
    im.add_argument("--out", required=True)
    im.add_argument("--profile", default="qwen21_bf16")
    im.add_argument("--res", default="1K")
    im.add_argument("--seed", type=int, default=0)
    im.add_argument("--aspect", default="16:9")
    im.add_argument("--ref", action="append", default=[])
    vi = sub.add_parser("video")
    vi.add_argument("--prompt-file", required=True)
    vi.add_argument("--out", required=True)
    vi.add_argument("--frame", required=True)
    vi.add_argument("--seconds", type=float, default=5.0)
    vi.add_argument("--profile", default=os.environ.get("VIDEO_PROFILE", "fasth3"))
    vi.add_argument("--res", default="768p")
    vi.add_argument("--seed", type=int, default=0)
    vi.add_argument("--aspect", default="16:9")
    co = sub.add_parser("collect")
    co.add_argument("--job", required=True)
    co.add_argument("--kind", choices=["image", "video"], required=True)
    co.add_argument("--out", required=True)
    a = ap.parse_args(argv)

    c = Client(api=a.api, root=Path(a.root))
    try:
        if a.cmd == "status":
            print(json.dumps(c.status(), ensure_ascii=False))
        elif a.cmd == "config":
            print(json.dumps(c.config(), ensure_ascii=False, indent=2))
        elif a.cmd == "image":
            jid, out = c.image(Path(a.prompt_file).read_text(encoding="utf-8"), Path(a.out), profile=a.profile,
                               res=a.res, seed=a.seed, refs=[Path(p) for p in a.ref], aspect=a.aspect, name=a.name)
            print("OK", a.name or out.stem, jid, out)
        elif a.cmd == "video":
            jid, out = c.video(Path(a.prompt_file).read_text(encoding="utf-8"), Path(a.out), Path(a.frame),
                               seconds=a.seconds, profile=a.profile, res=a.res, seed=a.seed, aspect=a.aspect, name=a.name)
            print("OK", a.name or out.stem, jid, out)
        elif a.cmd == "collect":
            out = c.collect(a.job, a.kind, Path(a.out))
            print("COLLECTED", a.job, out)
    except Stop as e:
        print(str(e))
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
