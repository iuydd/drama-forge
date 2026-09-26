#!/usr/bin/env python3
"""可灵（Kling）开放平台 API 的视频客户端：单图首帧转视频（/v1/videos/image2video）。

沿用 h3_client.Client 的账本（脚本/jobs.jsonl：submission_intent → submitted → collected）、提交锁、STOP/DEADLINE、
未决提交阻断与 collect 收回；只替换提交、轮询、下载三处。

- 密钥只从环境变量 KLING_API_KEY 读（Authorization: Bearer），不落盘、不打印、不写进账本。
- 接口域名：环境变量 KLING_API_BASE，默认 https://api-beijing.klingai.com（北京站；新加坡站 key 不通用）。
- drama.json：video_provider="kling"，profiles.video 写模型名（例 kling-v3），profiles.video_res 写 std / pro（720p / 1080p）；
  kling_sound 写 "on" / "off"（原生音频，默认 off）。
- 时长只接受整数 3–15 秒（kling-v3 实测）：镜头秒数向上取整、不足 3 取 3。
- 起始帧以原始 base64（不带 data: 前缀）内联上传。
- 实测注意：1×1 像素这类明显无效的图片不会被同步拒绝，会建成任务再终态失败；探测参数只用会被同步校验拒绝的错误值。

  kling_client.py collect --root <项目> --job <task_id> --out OUT
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import os
import sys
import time
import uuid
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from h3_client import Client, PendingElsewhere, SubmissionUnknown, rec_channel  # noqa: E402

BASE = os.environ.get("KLING_API_BASE", "https://api-beijing.klingai.com").rstrip("/")
PATH = "/v1/videos/image2video"


class KlingClient(Client):
    def __init__(self, model: str, root: Path | None = None, log_dir: Path | None = None, poll: float = 10.0,
                 sound: str = "off"):
        super().__init__(api=BASE, token="", root=root, poll=poll, log_dir=log_dir, channel="kling")
        self.model = model
        self.sound = sound if sound in ("on", "off") else "off"
        key = os.environ.get("KLING_API_KEY")
        self.s.headers.pop("Authorization", None)
        if key:
            self.s.headers["Authorization"] = "Bearer " + key

    def require_token(self) -> None:
        if not self.s.headers.get("Authorization"):
            raise SystemExit("缺 KLING_API_KEY（只从环境变量读，不要写进文件）")

    def wait_idle(self) -> None:  # 云端队列；并发上限由资源包决定，由 produce.py --jobs 控制
        return

    def submit_video(self, prompt: str, out: Path, frame: Path, seconds: float = 5.0, profile: str | None = None,
                     res: str | None = None, seed: int = 0, aspect: str = "16:9", name: str = "",
                     image_mode: str = "keyframe", sound: str | None = None) -> str:
        self.require_token()
        self.guard()
        mode = (res or "std").lower()
        if mode not in ("std", "pro"):
            raise ValueError(f"可灵档位只接受 std / pro，收到 {res!r}")
        dur = min(15, max(3, math.ceil(float(seconds))))
        img = base64.b64encode(Path(frame).read_bytes()).decode()
        body = {"model_name": profile or self.model, "image": img, "prompt": prompt.strip()[:2500],
                "duration": str(dur), "mode": mode, "sound": sound if sound in ("on", "off") else self.sound}
        name = name or out.stem
        fingerprint = hashlib.sha256(json.dumps({**body, "image": hashlib.sha256(Path(frame).read_bytes()).hexdigest()},
                                                sort_keys=True, ensure_ascii=False).encode()).hexdigest()
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
                      "out": str(out.resolve()), "fingerprint": fingerprint, "profile": body["model_name"], "res": mode}
            self._append(intent)
            try:
                r = self.s.post(BASE + PATH, json=body, timeout=120)
            except requests.RequestException as exc:
                self._append({**intent, "status": "submission_unknown", "error_type": type(exc).__name__})
                raise SubmissionUnknown(f"提交结果未知：{request_id}；先到可灵任务列表对账并 reconcile，禁止直接重投") from exc
            if 400 <= r.status_code < 500:
                self._append({**intent, "status": "not_submitted", "http": r.status_code, "error": r.text[:300]})
                raise RuntimeError(f"可灵拒绝（未受理不计费）：HTTP {r.status_code} {r.text[:300]}")
            try:
                r.raise_for_status()
                j = r.json()
                if j.get("code") != 0:
                    raise ValueError(f"code {j.get('code')} {j.get('message')}")
                jid = str(j["data"]["task_id"])
            except (requests.RequestException, KeyError, ValueError, TypeError) as exc:
                self._append({**intent, "status": "submission_unknown", "error_type": type(exc).__name__})
                raise SubmissionUnknown(f"提交结果未知：{request_id}；先到可灵任务列表对账并 reconcile，禁止直接重投") from exc
            self._log(name, "video", {"profile": body["model_name"], "res": mode, "seconds": dur, "sound": body["sound"],
                                      "prompt": body["prompt"], "images": [1]},
                      jid, out, request_id=request_id, fingerprint=fingerprint)
            return jid

    def wait_job(self, jid: str, poll: float | None = None) -> dict:
        while True:
            j = self.rget(f"{BASE}{PATH}/{jid}").json()
            d = j.get("data") or {}
            st = d.get("task_status")
            if st == "succeed":
                d["id"] = jid
                return d
            if st == "failed":
                self._mark(jid, "failed", Path("-"), {"msg": d.get("task_status_msg")})
                raise RuntimeError(f"可灵任务失败 {jid}: {d.get('task_status_msg')}")
            time.sleep(poll or self.poll)

    def download(self, job: dict, kind: str, out: Path) -> Path:
        jid = job["id"]
        vids = ((job.get("task_result") or {}).get("videos")) or []
        url = (vids[0] or {}).get("url") if vids else ""
        if not url:
            self._mark(jid, "download_failed", Path(out))
            raise RuntimeError(f"{jid}: 结果里没有 videos[0].url")
        data = requests.get(url, timeout=300).content  # 结果 CDN 地址，不带密钥
        out = Path(out)
        if not data or b"ftyp" not in data[:64]:
            self._mark(jid, "download_failed", out)
            raise RuntimeError(f"{jid}: 下载内容不是 mp4")
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp = out.with_suffix(out.suffix + ".part")
        tmp.write_bytes(data)
        os.replace(tmp, out)
        self._mark(jid, "collected", out)
        return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("collect")
    c.add_argument("--root", required=True)
    c.add_argument("--job", required=True)
    c.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    cl = KlingClient("", root=Path(a.root), log_dir=Path(a.root) / "脚本")
    cl.require_token()
    job = cl.wait_job(a.job)
    print(cl.download(job, "video", Path(a.out)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
