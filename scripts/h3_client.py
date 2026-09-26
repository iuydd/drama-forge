#!/usr/bin/env python3
"""H3 Studio 自建中转的客户端：图片、视频、收回、状态。

实战规则（来自已跑通的项目）：
- 按槽位提交：/api/status 带 capacity（h3studio 网关，多台机器各跑一个）时，有空槽（slots_free > 0）且没排队才提交，
  最多同时 slots_total 个任务在飞（2026-09-26 为 9）；没有 capacity 的旧服务仍等整机空闲（running 为空或 0，且 queued 为 0）。
- 只重试 GET（查询、下载），绝不重发 POST；网络断开时一直等，不放弃已提交的任务。
- 每次提交立即把任务号写进 ids.log 和 jobs.jsonl；中断后用 collect 按任务号收回，不盲目重发。
- 项目根目录有 STOP 文件就退出；环境变量 DEADLINE=YYYYmmddHHMM 到点退出。
- token 只从环境变量 H3_STUDIO_TOKEN 读，不落盘、不打印、不写进任何文件。

命令行：
  h3_client.py status  [--api URL]
  h3_client.py config  [--api URL]
  h3_client.py image   --prompt-file P --out OUT --profile PROFILE --res RES [--seed N] [--ref PNG ...] [--aspect 16:9]
  h3_client.py video   --prompt-file P --out OUT --frame PNG [--seconds 5] --profile PROFILE --res RES [--seed N]
  h3_client.py collect --job ID --kind image|video --out OUT
  h3_client.py unresolved
  h3_client.py reconcile --request-id ID (--job ID | --not-submitted) --evidence TEXT
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
import uuid
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


class SubmissionUnknown(RuntimeError):
    """Submission may have been accepted; reconcile before sending anything else."""


class PendingElsewhere(RuntimeError):
    """同名任务已在另一个通道提交、还没收回：只能交回那个通道去 collect。"""

    def __init__(self, channel: str, rec: dict):
        super().__init__(f"{rec.get('name')} 在通道 {channel} 有未收回任务 {rec.get('job')}")
        self.channel, self.rec = channel, rec


DEFAULT_CHANNEL = "h3studio"


def rec_channel(rec: dict) -> str:
    """账本记录属于哪个通道；多通道之前写的旧记录一律算 h3studio。"""
    return rec.get("channel") or DEFAULT_CHANNEL


def is_local_api(api: str) -> bool:
    from urllib.parse import urlparse
    return (urlparse(api).hostname or "") in ("127.0.0.1", "localhost", "::1")


class Stop(SystemExit):
    """STOP 文件或 DEADLINE 触发的正常退出。"""


def _now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


class Client:
    def __init__(self, api: str | None = None, token: str | None = None, root: Path | None = None,
                 poll: float = 3.0, log_dir: Path | None = None, channel: str = DEFAULT_CHANNEL):
        self.channel = channel
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
        """空闲检查 + POST 用一把文件锁包住：同一台机器上两个提交者不会往同一通道同时提交。
        锁按通道分：一个通道等空闲时不挡别的通道。"""
        self.log_dir.mkdir(parents=True, exist_ok=True)
        lock_path = self.log_dir / (".submit.lock" if self.channel == DEFAULT_CHANNEL else f".submit.{self.channel}.lock")
        f = open(lock_path, "a+")
        try:
            if fcntl:
                fcntl.flock(f, fcntl.LOCK_EX)
            yield
        finally:
            if fcntl:
                fcntl.flock(f, fcntl.LOCK_UN)
            f.close()

    def _append(self, rec: dict) -> None:
        """Persist safety-critical state before proceeding; write errors must stop submission.
        所有通道（H3/fal/可灵/providers）的提交都先写 submission_intent：子代理（DF_SUBAGENT=1）在这里被拒；
        collected 记录补上产物 sha256，submitted 记录补上起始帧与完整提示词哈希（入剪前核对 take 来源）。"""
        if rec.get("status") == "submission_intent" and os.environ.get("DF_SUBAGENT"):
            raise SystemExit("子代理（DF_SUBAGENT=1）不提交生成任务（硬约束 9）：把要生成的内容交回主会话")
        if rec.get("status") in ("submission_intent", "submitted"):
            rec = {**rec, **{k: v for k, v in (getattr(self, "_submit_extra", None) or {}).items() if k not in rec}}
            rec.setdefault("channel", self.channel)
        if rec.get("status") == "collected" and "sha256" not in rec:
            out = Path(str(rec.get("out") or ""))
            if out.is_file():
                rec = {**rec, "sha256": hashlib.sha256(out.read_bytes()).hexdigest()}
        self.log_dir.mkdir(parents=True, exist_ok=True)
        with open(self.log_dir / "jobs.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps({"time": _now(), **rec}, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())

    def unresolved(self, all_channels: bool = False) -> list[dict]:
        """未决提交（写了 intent 却没有 submitted/not_submitted）。默认只看本通道：别的通道正在提交不算本通道未决。"""
        intents = {}
        resolved = set()
        for rec in self.ledger():
            rid = rec.get("request_id")
            if rec.get("status") == "submission_intent" and rid:
                intents[rid] = rec
            elif rec.get("status") in ("submitted", "not_submitted") and rid:
                resolved.add(rid)
        return [rec for rid, rec in intents.items()
                if rid not in resolved and (all_channels or rec_channel(rec) == self.channel)]

    def reconcile(self, request_id: str, *, job: str | None, not_submitted: bool,
                  evidence: str) -> None:
        if bool(job) == bool(not_submitted) or not evidence.strip():
            raise ValueError("provide exactly one of job/not_submitted and nonempty reconciliation evidence")
        with self.submit_lock():
            rec = next((r for r in self.unresolved() if r["request_id"] == request_id), None)
            if rec is None:
                raise ValueError("request is not unresolved")
            # Evidence must come from provider history/support; this does not query the provider.
            self._append({**rec, "status": "not_submitted" if not_submitted else "submitted",
                          "job": job, "evidence": evidence.strip(), "time": _now()})

    def _submit(self, path: str, payload: dict, name: str, kind: str, out: Path) -> str:
        if not isinstance(payload.get("profile"), str) or not payload["profile"].strip():
            raise ValueError("missing explicit model/profile; set the accepted project profile or --profile")
        if not isinstance(payload.get("res"), str) or not payload["res"].strip():
            raise ValueError("missing explicit resolution; set the accepted project resolution or --res")
        fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False,
                                                separators=(",", ":")).encode()).hexdigest()
        with self.submit_lock():
            unknown = self.unresolved()
            if unknown:
                raise SubmissionUnknown("先对账未决提交，再继续生产：" + ", ".join(r["request_id"] for r in unknown))
            pending = self.pending(name)
            if pending and rec_channel(pending) != self.channel:
                raise PendingElsewhere(rec_channel(pending), pending)
            if pending:
                if (pending.get("kind") != kind or Path(pending["out"]).resolve() != out.resolve()
                        or pending.get("fingerprint") not in (None, fingerprint)):
                    raise SubmissionUnknown("同名未收回任务与当前输入不同；先 collect 原任务，不重新提交")
                return pending["job"]
            self.guard()
            self.wait_idle()
            self.guard()
            request_id = uuid.uuid4().hex
            intent = {"request_id": request_id, "status": "submission_intent", "name": name,
                      "kind": kind, "out": str(out.resolve()), "fingerprint": fingerprint,
                      "profile": payload["profile"], "res": payload["res"]}
            self._append(intent)
            # No invented provider idempotency header: the relay contract does not expose one.
            try:
                response = self.s.post(self.api + path, json=payload, timeout=120)
                response.raise_for_status()
                jid = response.json()["id"]
                if not isinstance(jid, str) or not jid.strip():
                    raise ValueError("missing nonempty provider job id")
            except (requests.RequestException, KeyError, ValueError, TypeError) as exc:
                self._append({**intent, "status": "submission_unknown", "error_type": type(exc).__name__})
                raise SubmissionUnknown(f"提交结果未知：{request_id}；先查供应商任务记录并 reconcile，禁止直接重投") from exc
            self._log(name, kind, payload, jid, out, request_id=request_id, fingerprint=fingerprint)
            return jid

    def require_token(self) -> None:
        if not self.api:
            raise SystemExit("缺 H3_API：设环境变量 H3_API，或在 drama.json 写 api_base")
        if not self.token and not is_local_api(self.api):  # 本机通道（comfy_studio.py）不要 token
            raise SystemExit("缺 H3_STUDIO_TOKEN（只从环境变量读，不要写进文件）")

    # ---- HTTP ----------------------------------------------------------------
    def rget(self, path: str, timeout: float = 30, tries: int = 3000, before_submit: bool = False, **kw) -> requests.Response:
        """只重试 GET；网络抖动时每 10 秒重试一次，直到成功。"""
        if not self.api:
            raise SystemExit("缺 H3_API：设环境变量 H3_API，或在 drama.json 写 api_base")
        url = path if path.startswith("http") else self.api + path
        last = None
        for _ in range(tries):
            if before_submit:
                self.guard()
            try:
                r = self.s.get(url, timeout=timeout, **kw)
                r.raise_for_status()
                return r
            except requests.RequestException as e:  # noqa: PERF203
                last = e
                time.sleep(10)
        raise SystemExit(f"network down too long: {last}")

    def status(self, *, before_submit: bool = False) -> dict:
        return self.rget("/api/status", before_submit=before_submit).json()

    def config(self) -> dict:
        return self.rget("/api/config").json()

    def slots(self) -> int:
        """服务端能同时跑几个任务（capacity.slots_total）；没报就是 1。"""
        cap = self.status().get("capacity")
        return int(cap.get("slots_total") or 1) if isinstance(cap, dict) else 1

    def wait_idle(self) -> None:
        """等到能提交：有 capacity 就等空槽，没有就等整机空闲。"""
        while True:
            self.guard()
            st = self.status(before_submit=True)
            self.guard()
            cap = st.get("capacity")
            if isinstance(cap, dict) and cap.get("slots_total"):
                if int(cap.get("slots_free") or 0) > 0 and not cap.get("queued") and not st.get("queued"):
                    return
            elif st.get("running") in (None, 0) and st.get("queued") in (None, 0):
                return
            time.sleep(self.poll)

    # ---- 提交 ----------------------------------------------------------------
    @staticmethod
    def _data_uri(path: Path) -> str:
        return "data:image/png;base64," + base64.b64encode(Path(path).read_bytes()).decode()

    def _log(self, name: str, kind: str, payload: dict, jid: str, out: Path, *,
             request_id: str, fingerprint: str) -> None:
        self._append({"name": name, "kind": kind, "job": jid, "out": str(out.resolve()),
                      "request_id": request_id, "fingerprint": fingerprint,
                      "profile": payload.get("profile"), "res": payload.get("res"),
                      "seconds": payload.get("seconds"), "seed": payload.get("seed"),
                      "image_mode": payload.get("image_mode"), "n_images": len(payload.get("images") or []),
                      "prompt_sha256": hashlib.sha256(payload.get("prompt", "").encode()).hexdigest()[:16],
                      "status": "submitted"})
        # Human-readable log is secondary; the durable JSON ledger is authoritative.
        with open(self.log_dir / "ids.log", "a", encoding="utf-8") as f:
            f.write(f"{_now()} {name} {kind} {payload.get('profile')} {payload.get('res')} {jid} {out}\n")

    def ledger(self) -> list[dict]:
        p = self.log_dir / "jobs.jsonl"
        if not p.exists():
            return []
        out = []
        for line in p.read_text(encoding="utf-8").splitlines():
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise SubmissionUnknown("任务账本损坏；先恢复账本，禁止忽略记录后重投") from exc
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

    def submit_image(self, prompt: str, out: Path, profile: str | None = None, res: str | None = None, seed: int = 0,
                     refs: list[Path] | None = None, aspect: str = "16:9", name: str = "") -> str:
        self.require_token()
        self.guard()
        payload = {"prompt": prompt.strip(), "profile": profile, "aspect": aspect, "res": res, "seed": int(seed),
                   "images": [self._data_uri(p) for p in (refs or [])]}
        return self._submit("/api/v1/image", payload, name or out.stem, "image", out)

    def submit_video(self, prompt: str, out: Path, frame: Path, seconds: float = 5.0, profile: str | None = None,
                     res: str | None = None, seed: int = 0, aspect: str = "16:9", name: str = "",
                     image_mode: str = "keyframe") -> str:
        self.require_token()
        self.guard()
        payload = {"prompt": prompt.strip(), "profile": profile, "aspect": aspect, "res": res,
                   "seconds": float(seconds), "seed": int(seed), "image_mode": image_mode,
                   "images": [self._data_uri(frame)]}
        return self._submit("/api/v1/generate", payload, name or out.stem, "video", out)

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
            self._mark(jid, "download_failed", out)
            raise RuntimeError(f"{jid}: 下载到空文件")
        if kind == "image" and not (data.startswith(b"\x89PNG") or data.startswith(b"\xff\xd8") or data[:4] == b"RIFF"):
            self._mark(jid, "download_failed", out)
            raise RuntimeError(f"{jid}: 下载内容不是图片（前 8 字节 {data[:8]!r}）")
        if kind == "video" and b"ftyp" not in data[:64]:
            self._mark(jid, "download_failed", out)
            raise RuntimeError(f"{jid}: 下载内容不是 mp4（前 16 字节 {data[:16]!r}）")
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp = out.with_suffix(out.suffix + ".part")
        tmp.write_bytes(data)
        os.replace(tmp, out)
        self._mark(jid, "collected", out)
        return out

    def _mark(self, jid: str, status: str, out: Path, extra: dict | None = None) -> None:
        self._append({"job": jid, "status": status, "out": str(out), **(extra or {})})

    def collect(self, jid: str, kind: str, out: Path) -> Path:
        job = self.wait_job(jid, poll=10)
        job.setdefault("id", jid)
        return self.download(job, kind, out)

    # ---- 一步到位（先查账本里未收回的同名任务，有就收回，不重新 POST） ---------------
    def image(self, prompt: str, out: Path, **kw) -> tuple[str, Path]:
        jid = self.submit_image(prompt, out, **kw)
        job = self.wait_job(jid)
        job.setdefault("id", jid)
        return jid, self.download(job, "image", out)

    def video(self, prompt: str, out: Path, frame: Path, **kw) -> tuple[str, Path]:
        # 账本记起始帧 sha 与完整提示词 sha（可灵会截断提示词，所以记截断前的）；review_quality.provenance_issues 用它核对来源
        self._submit_extra = {"frame_sha256": hashlib.sha256(Path(frame).read_bytes()).hexdigest(),
                              "source_prompt_sha256": hashlib.sha256(prompt.strip().encode()).hexdigest()}
        try:
            jid = self.submit_video(prompt, out, frame, **kw)
        finally:
            self._submit_extra = None
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
    im.add_argument("--profile", required=True)
    im.add_argument("--res", required=True)
    im.add_argument("--seed", type=int, default=0)
    im.add_argument("--aspect", default="16:9")
    im.add_argument("--ref", action="append", default=[])
    vi = sub.add_parser("video")
    vi.add_argument("--prompt-file", required=True)
    vi.add_argument("--out", required=True)
    vi.add_argument("--frame", required=True)
    vi.add_argument("--seconds", type=float, default=5.0)
    vi.add_argument("--profile", required=True)
    vi.add_argument("--res", required=True)
    vi.add_argument("--seed", type=int, default=0)
    vi.add_argument("--aspect", default="16:9")
    co = sub.add_parser("collect")
    co.add_argument("--job", required=True)
    co.add_argument("--kind", choices=["image", "video"], required=True)
    co.add_argument("--out", required=True)
    sub.add_parser("unresolved")
    rc = sub.add_parser("reconcile")
    rc.add_argument("--request-id", required=True)
    group = rc.add_mutually_exclusive_group(required=True)
    group.add_argument("--job")
    group.add_argument("--not-submitted", action="store_true")
    rc.add_argument("--evidence", required=True)
    a = ap.parse_args(argv)

    c = Client(api=a.api, root=Path(a.root))
    try:
        if a.cmd == "unresolved":
            print(json.dumps(c.unresolved(), ensure_ascii=False, indent=2))
        elif a.cmd == "reconcile":
            c.reconcile(a.request_id, job=a.job, not_submitted=a.not_submitted, evidence=a.evidence)
            print("RECONCILED", a.request_id)
        elif a.cmd == "status":
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
    except (SubmissionUnknown, ValueError) as e:
        print(str(e), file=sys.stderr)
        return 2
    except Stop as e:
        print(str(e))
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
