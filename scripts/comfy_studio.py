#!/usr/bin/env python3
"""本机出图通道：把本机 ComfyUI 包成和 H3 Studio（h3studio）同一套接口，供 produce.py 当第二条本地通道。

接口与 h3studio 相同，h3_client.Client 直接可用：
  GET  /api/status            {"running": 0|1, "queued": N}
  GET  /api/config            {"profiles": {"image": [...], "video": []}, "image_refs": {档位: 最多几张参考图}}
  POST /api/v1/image          {"prompt","profile","res","aspect","seed","images":[data URI...]} -> {"id"}
  GET  /api/jobs/<id>         {"id","status": queued|running|done|failed, "error"?}
  GET  /api/jobs/<id>/image   PNG

- 一次只跑一个任务（本机单卡），其余排队；任务表写盘，服务重启后已完成的任务仍能按任务号收回，
  没跑完的标 failed（不会让客户端无限等）。
- 切换模型族（qwen21 ↔ krea2）前让 ComfyUI 卸载模型，两个模型不同时常驻。
- 档位参数与 h3studio 对齐：krea2_turbo 8 步 cfg 1 euler/simple（同 seed 与 h3studio 出图几乎一致）；
  qwen21 用官方模板默认（25 步、cfg 1、euler/simple、参考图缩到约 1024²），可用环境变量覆盖。
- 分辨率：1K = 1344×768（竖 768×1344，方 1024×1024），2K = 2752×1536（竖 1536×2752，方 2048×2048）。
- 只监听 127.0.0.1；设了 COMFY_STUDIO_TOKEN 才校验 Bearer token。

用法：
  python3 comfy_studio.py [--port 8190] [--comfy http://127.0.0.1:8188] [--state-dir DIR]
依赖：ComfyUI 已启动、模型文件就位（文件名见下面 MODELS，可用环境变量改）；qwen21 任意宽高比需要
EmptyQwenImage21Latent 节点（没有时退回编码节点自带的 latent）。
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import requests

MODELS = {
    "qwen21": {
        "unet": os.environ.get("QWEN21_UNET", "qwen_image_2.1_bf16.safetensors"),
        "clip": os.environ.get("QWEN21_CLIP", "qwen3vl_8b_bf16.safetensors"),
        "vae": os.environ.get("QWEN21_VAE", "qwen_image_2.1_vae_bf16.safetensors"),
        "steps": int(os.environ.get("QWEN21_STEPS", "25")),
        "cfg": float(os.environ.get("QWEN21_CFG", "1.0")),
        "shift": float(os.environ["QWEN21_SHIFT"]) if os.environ.get("QWEN21_SHIFT") else None,  # 默认用模型自带 shift
        "ref_res": int(os.environ.get("QWEN21_REF_RES", "1024")),  # 参考图缩到约 1024x1024 像素（官方默认）
        "refs": 3,
    },
    "krea2_turbo": {
        "unet": os.environ.get("KREA2_UNET", "krea2_turbo_bf16.safetensors"),
        "clip": os.environ.get("KREA2_CLIP", "qwen3vl_4b_bf16.safetensors"),
        "vae": os.environ.get("KREA2_VAE", "qwen_image_vae.safetensors"),
        "steps": int(os.environ.get("KREA2_STEPS", "8")),
        "cfg": 1.0,
        "refs": 0,
    },
}
FAMILY = {"qwen21": "qwen21", "krea2_turbo": "krea2"}
SIZES = {"1K": {"16:9": (1344, 768), "9:16": (768, 1344), "1:1": (1024, 1024)},
         "2K": {"16:9": (2752, 1536), "9:16": (1536, 2752), "1:1": (2048, 2048)}}


def size_for(res: str, aspect: str) -> tuple[int, int]:
    try:
        return SIZES[res.upper()][aspect or "16:9"]
    except KeyError:
        raise ValueError(f"不支持的分辨率/画幅：{res} {aspect}") from None


class Studio:
    def __init__(self, comfy: str, state_dir: Path):
        self.comfy = comfy.rstrip("/")
        self.dir = state_dir
        (self.dir / "out").mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        self.cv = threading.Condition(self.lock)
        self.jobs: dict[str, dict] = {}
        self.queue: list[str] = []
        self.running: str | None = None
        self.family: str | None = None
        self._load()
        threading.Thread(target=self._worker, daemon=True).start()

    # ---- 任务表持久化 ----------------------------------------------------------
    def _state(self) -> Path:
        return self.dir / "jobs.json"

    def _load(self) -> None:
        if self._state().exists():
            self.jobs = json.loads(self._state().read_text(encoding="utf-8"))
        for j in self.jobs.values():
            if j["status"] in ("queued", "running"):   # 上次没跑完：标失败，交给客户端按失败处理
                j.update(status="failed", error="comfy_studio restarted before the job finished")
        self._save()

    def _save(self) -> None:
        tmp = self._state().with_suffix(".tmp")
        slim = {k: {kk: vv for kk, vv in v.items() if kk != "payload"} for k, v in self.jobs.items()}
        tmp.write_text(json.dumps(slim, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self._state())

    # ---- 提交 ----------------------------------------------------------------
    def submit(self, payload: dict) -> str:
        profile = payload.get("profile")
        if profile not in MODELS:
            raise ValueError(f"本机没有档位 {profile!r}；可用 {sorted(MODELS)}")
        images = payload.get("images") or []
        if len(images) > MODELS[profile]["refs"]:
            raise ValueError(f"{profile} 在本机最多接 {MODELS[profile]['refs']} 张参考图，收到 {len(images)}")
        size_for(payload.get("res") or "", payload.get("aspect") or "16:9")
        jid = "mac-" + time.strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:4]
        with self.cv:
            self.jobs[jid] = {"id": jid, "status": "queued", "profile": profile, "payload": payload,
                              "created": time.time()}
            self.queue.append(jid)
            self._save()
            self.cv.notify()
        return jid

    # ---- 执行 ----------------------------------------------------------------
    def _worker(self) -> None:
        while True:
            with self.cv:
                while not self.queue:
                    self.cv.wait()
                jid = self.queue.pop(0)
                job = self.jobs[jid]
                job["status"] = "running"
                self.running = jid
                self._save()
            try:
                out = self._run(job)
                with self.cv:
                    job.update(status="done", file=str(out))
            except Exception as e:  # noqa: BLE001 — 任何失败都记给客户端，不让它无限等
                with self.cv:
                    job.update(status="failed", error=f"{type(e).__name__}: {e}"[:500])
            finally:
                with self.cv:
                    job.pop("payload", None)
                    self.running = None
                    self._save()

    def _upload(self, data_uri: str, name: str) -> str:
        raw = base64.b64decode(data_uri.split(",", 1)[1])
        r = requests.post(self.comfy + "/upload/image", files={"image": (name, raw, "image/png")},
                          data={"overwrite": "true", "subfolder": "comfy_studio"}, timeout=120)
        r.raise_for_status()
        j = r.json()
        return f"{j['subfolder']}/{j['name']}" if j.get("subfolder") else j["name"]

    def _has_node(self, cls: str) -> bool:
        return cls in requests.get(self.comfy + "/object_info/" + cls, timeout=30).json()

    def _graph(self, jid: str, p: dict) -> dict:
        profile = p["profile"]
        m = MODELS[profile]
        w, h = size_for(p["res"], p.get("aspect") or "16:9")
        g: dict = {}

        def add(nid, ct, **inputs):
            g[nid] = {"class_type": ct, "inputs": inputs}

        add("unet", "UNETLoader", unet_name=m["unet"], weight_dtype="default")
        add("vae", "VAELoader", vae_name=m["vae"])
        seed = int(p.get("seed") or 0)
        if profile == "krea2_turbo":
            add("clip", "CLIPLoader", clip_name=m["clip"], type="krea2")
            add("pos", "CLIPTextEncode", clip=["clip", 0], text=p["prompt"])
            add("neg", "ConditioningZeroOut", conditioning=["pos", 0])
            add("lat", "EmptyLatentImage", width=w, height=h, batch_size=1)
            add("ks", "KSampler", model=["unet", 0], seed=seed, steps=m["steps"], cfg=m["cfg"], sampler_name="euler",
                scheduler="simple", positive=["pos", 0], negative=["neg", 0], latent_image=["lat", 0], denoise=1.0)
        else:  # qwen21
            add("clip", "CLIPLoader", clip_name=m["clip"], type="qwen_image")
            refs = p.get("images") or []
            enc = dict(clip=["clip", 0], prompt=p["prompt"], negative_prompt="", resolution=m["ref_res"], vae=["vae", 0])
            for i, uri in enumerate(refs):
                add(f"ref{i}", "LoadImage", image=self._upload(uri, f"{jid}_ref{i + 1}.png"))
                enc[f"images.image_{i + 1}"] = [f"ref{i}", 0]
            add("enc", "TextEncodeQwenImage21", **enc)
            if self._has_node("EmptyQwenImage21Latent"):
                add("lat", "EmptyQwenImage21Latent", width=w, height=h, batch_size=1)
                latent = ["lat", 0]
            else:
                latent = ["enc", 2]
            model = ["unet", 0]
            if m["shift"] is not None:
                add("ms", "ModelSamplingAuraFlow", model=["unet", 0], shift=m["shift"])
                model = ["ms", 0]
            add("ks", "KSampler", model=model, seed=seed, steps=m["steps"], cfg=m["cfg"], sampler_name="euler",
                scheduler="simple", positive=["enc", 0], negative=["enc", 1], latent_image=latent, denoise=1.0)
        add("dec", "VAEDecode", samples=["ks", 0], vae=["vae", 0])
        add("save", "SaveImage", images=["dec", 0], filename_prefix=f"comfy_studio/{jid}")
        return g

    def _run(self, job: dict) -> Path:
        p = job["payload"]
        fam = FAMILY[p["profile"]]
        if self.family != fam:   # 换模型族（含服务刚起、不知道 ComfyUI 里常驻了什么）先卸载，两个大模型不同时常驻
            requests.post(self.comfy + "/free", json={"unload_models": True, "free_memory": True}, timeout=120)
        self.family = fam
        r = requests.post(self.comfy + "/prompt", json={"prompt": self._graph(job["id"], p), "client_id": "comfy_studio"},
                          timeout=120)
        if r.status_code != 200:
            raise RuntimeError(f"ComfyUI 拒绝工作流：{r.text[:400]}")
        pid = r.json()["prompt_id"]
        while True:
            h = requests.get(f"{self.comfy}/history/{pid}", timeout=60).json()
            if pid in h:
                break
            time.sleep(1)
        st = h[pid]["status"]
        if st.get("status_str") != "success":
            msg = next((m[1].get("exception_message") for m in st.get("messages", []) if m[0] == "execution_error"), st)
            raise RuntimeError(f"ComfyUI 执行失败：{msg}")
        im = next(i for o in h[pid]["outputs"].values() for i in o.get("images", []))
        data = requests.get(self.comfy + "/view", params={"filename": im["filename"], "subfolder": im["subfolder"],
                                                           "type": im["type"]}, timeout=120).content
        out = self.dir / "out" / f"{job['id']}.png"
        out.write_bytes(data)
        return out

    def status(self) -> dict:
        with self.lock:
            return {"running": 1 if self.running else 0, "queued": len(self.queue)}


def make_handler(studio: Studio, token: str | None):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _auth(self) -> bool:
            if token and self.headers.get("Authorization") != "Bearer " + token:
                self._json({"detail": "bad token"}, 401)
                return False
            return True

        def _json(self, obj, code=200):
            body = json.dumps(obj, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if not self._auth():
                return
            parts = self.path.split("?")[0].strip("/").split("/")
            if parts == ["api", "status"]:
                return self._json(studio.status())
            if parts == ["api", "config"]:
                return self._json({"profiles": {"image": sorted(MODELS), "video": []},
                                   "image_refs": {k: v["refs"] for k, v in MODELS.items()}})
            if len(parts) >= 3 and parts[:2] == ["api", "jobs"]:
                job = studio.jobs.get(parts[2])
                if not job:   # 不认识的任务号直接判失败，客户端不会无限重试
                    return self._json({"id": parts[2], "status": "failed", "error": "unknown job"})
                if len(parts) == 3:
                    return self._json({k: job[k] for k in ("id", "status", "error") if k in job})
                if parts[3] == "image" and job["status"] == "done":
                    data = Path(job["file"]).read_bytes()
                    self.send_response(200)
                    self.send_header("Content-Type", "image/png")
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    return self.wfile.write(data)
            return self._json({"detail": "not found"}, 404)

        def do_POST(self):
            if not self._auth():
                return
            if self.path.split("?")[0] != "/api/v1/image":
                return self._json({"detail": "本机通道只出图"}, 404)
            n = int(self.headers.get("Content-Length", "0"))
            try:
                jid = studio.submit(json.loads(self.rfile.read(n) or b"{}"))
            except (ValueError, KeyError, TypeError) as e:
                return self._json({"detail": str(e)}, 400)
            return self._json({"id": jid})

    return H


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=8190)
    ap.add_argument("--comfy", default=os.environ.get("COMFY_URL", "http://127.0.0.1:8188"))
    ap.add_argument("--state-dir", default=os.path.expanduser("~/.drama-forge/comfy_studio"))
    a = ap.parse_args(argv)
    studio = Studio(a.comfy, Path(a.state_dir))
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), make_handler(studio, os.environ.get("COMFY_STUDIO_TOKEN")))
    print(f"comfy_studio on http://127.0.0.1:{a.port} -> ComfyUI {a.comfy}", flush=True)
    srv.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
