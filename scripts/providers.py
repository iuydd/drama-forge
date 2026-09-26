#!/usr/bin/env python3
"""官方接口适配器：MiniMax 视频（H3 官方 API）/ 语音 / 音乐、Seedance（火山方舟）、GPT Image 2。

H3 自建中转仍走 h3_client.py；本文件只在用户把某个镜头或配音、配乐指定给这些官方通道时使用
（SKILL.md 硬约束 1b：模型、档位、分辨率由用户指定，本文件不内置任何默认视频/语音模型）。

纪律与 h3_client.py 相同，并复用它的任务账本（脚本/jobs.jsonl）：
- 提交前查 STOP/DEADLINE、未决提交（submission_intent）与同名未收回任务；有同名未收回任务就收回，不重新 POST。
- 先写 submission_intent 再 POST；拿到任务号立即写 submitted，早于第一次轮询。
- POST 永不自动重发。服务端明确拒绝（HTTP 4xx 或 base_resp 非 0）记 not_submitted；网络断开、
  超时、HTTP 5xx、响应解析失败记 submission_unknown，按 runtime-boundaries.md 对账后再动。
- 只重试 GET；下载写 .part、校验文件头后原子改名。
- 密钥只从环境变量读（MINIMAX_API_KEY、ARK_API_KEY、OPENAI_API_KEY），不落盘、不打印、不进账本。

job 文件（JSON）：
  {"name": "V_EP001-S03_t2", "provider": "minimax-video", "model": "<用户指定的模型 ID>",
   "prompt": "逐字可复制正文", "out": "视频/V_S03_t2.mp4",
   "references": [{"path": "起始帧/F_S03_t1.png", "role": "first_frame", "label": "S03 起始帧",
                   "may_control": ["开场构图"], "must_not_control": ["终点姿态"]}],
   "parameters": {"duration": 6, "resolution": "768P", "prompt_language": "en"}}
provider 取 minimax-video | seedance | minimax-speech | minimax-music | gpt-image-2。

命令行：
  providers.py compile --job J [--root 项目]      # 只编译并打印请求体（参考图数据省略），不联网
  providers.py run     --job J  --root 项目        # 提交（或收回同名未收回任务）并下载
  providers.py collect --provider P --task ID --out OUT --root 项目   # 按任务号收回，不提交
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))
from h3_client import Client, Stop, SubmissionUnknown  # noqa: E402  复用账本、锁与 STOP/DEADLINE

BASES = {
    "minimax-video": ("MINIMAX_VIDEO_BASE_URL", "https://api.minimax.io/v2", "MINIMAX_API_KEY"),
    "minimax-speech": ("MINIMAX_BASE_URL", "https://api.minimax.io/v1", "MINIMAX_API_KEY"),
    "minimax-music": ("MINIMAX_BASE_URL", "https://api.minimax.io/v1", "MINIMAX_API_KEY"),
    "seedance": ("SEEDANCE_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3", "ARK_API_KEY"),
    "gpt-image-2": ("OPENAI_BASE_URL", "https://api.openai.com/v1", "OPENAI_API_KEY"),
}
KIND = {"minimax-video": "video", "seedance": "video", "minimax-speech": "tts",
        "minimax-music": "music", "gpt-image-2": "image"}
RATIOS = {"adaptive", "1:1", "3:4", "4:3", "9:16", "16:9", "21:9"}
H3_RESOLUTIONS = {"480P", "768P", "2K"}
ROLE_FIELD = {"first_frame": "image_url", "last_frame": "image_url", "reference_image": "image_url",
              "reference_video": "video_url", "reference_audio": "audio_url"}
MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp",
        ".mp4": "video/mp4", ".mov": "video/quicktime", ".webm": "video/webm", ".wav": "audio/wav",
        ".mp3": "audio/mpeg", ".m4a": "audio/mp4", ".aac": "audio/aac", ".flac": "audio/flac"}
# MiniMax 公布的单文件上限；Seedance 未公布，沿用同一保守上限。base64 膨胀约 1/3，请求上限按编码后算。
INLINE_LIMIT = {"image_url": 30 << 20, "video_url": 50 << 20, "audio_url": 15 << 20}
INLINE_BODY_LIMIT = 64 << 20
# 与各引擎共有的六个情绪；calm/fluent/whisper 只有部分型号收、neutral 官方已不再列出：平读就不传 emotion。
SPEECH_EMOTIONS = {"happy", "sad", "angry", "fearful", "disgusted", "surprised"}
SPEECH_LANGUAGES = {"Chinese", "Chinese,Yue", "English", "Japanese", "Korean", "Spanish", "French", "German",
                    "Portuguese", "Russian", "Italian", "Indonesian", "Vietnamese", "Thai", "Arabic", "Turkish"}
RUNNING = {"queued", "pending", "running", "processing", "in_progress", "preparing"}
FAILED = {"failed", "fail", "cancelled", "canceled", "timeout", "expired"}


class ProviderError(RuntimeError):
    """可以安全汇报的失败：不含响应正文、提示词和密钥。"""

    def __init__(self, message: str, *, category: str = "provider", retryable: bool = False,
                 http_status: int | None = None, rejected: bool = False):
        super().__init__(message)
        self.category, self.retryable, self.http_status, self.rejected = category, retryable, http_status, rejected


# ---- 纯函数：校验与编译（不联网、不读环境变量） -----------------------------------------------
def check_media(name: str, data: bytes) -> None:
    """文件头必须和扩展名一致；参考图送出前、下载结果落盘前都查。"""
    suffix = Path(name).suffix.casefold()
    ok = {
        ".png": data.startswith(b"\x89PNG\r\n\x1a\n"),
        ".jpg": data.startswith(b"\xff\xd8\xff"), ".jpeg": data.startswith(b"\xff\xd8\xff"),
        ".webp": data[:4] == b"RIFF" and data[8:12] == b"WEBP",
        ".wav": data[:4] == b"RIFF" and data[8:12] == b"WAVE",
        ".mp3": data.startswith(b"ID3") or (len(data) > 1 and data[0] == 0xFF and data[1] & 0xE0 == 0xE0),
        ".mp4": data[4:8] == b"ftyp", ".mov": data[4:8] in (b"ftyp", b"moov", b"wide"),
    }.get(suffix)
    if ok is None:
        return  # 其余格式（webm/m4a/aac/flac）只查非空
    if not data or not ok:
        raise ProviderError(f"{name}: 文件内容与扩展名 {suffix} 不符", category="media")


def inline_references(refs: Sequence[Mapping[str, Any]], root: Path) -> list[str]:
    """项目内参考文件编码成 data URI（两家都接受），带单文件与整请求上限。"""
    urls, total = [], 0
    for ref in refs:
        field = ROLE_FIELD[ref["role"]]
        path = (root / ref["path"]).resolve()
        mime = MIME.get(path.suffix.casefold())
        if not mime or not mime.startswith(field.split("_")[0]):
            raise ValueError(f"{ref['path']}: {ref['role']} 不收 {path.suffix or '无扩展名'} 文件")
        data = path.read_bytes()
        if not data:
            raise ValueError(f"{ref['path']}: 参考文件为空")
        check_media(path.name, data)
        if len(data) > INLINE_LIMIT[field]:
            raise ValueError(f"{ref['path']}: 超过 {INLINE_LIMIT[field] >> 20}MB 内联上限，改传 HTTPS 地址")
        encoded = base64.b64encode(data).decode("ascii")
        total += len(encoded)
        if total > INLINE_BODY_LIMIT:
            raise ValueError("参考文件合计超过请求体上限，把最大的几个改成 HTTPS 地址")
        urls.append(f"data:{mime};base64,{encoded}")
    return urls


def _refs(job: Mapping[str, Any]) -> list[dict]:
    refs = job.get("references") or []
    for i, ref in enumerate(refs, 1):
        for key in ("path", "role", "label"):
            if not isinstance(ref.get(key), str) or not ref[key].strip():
                raise ValueError(f"第 {i} 个参考缺 {key}")
        if ref["role"] not in ROLE_FIELD:
            raise ValueError(f"第 {i} 个参考的 role 不认识：{ref['role']}")
        for key in ("may_control", "must_not_control"):
            if not isinstance(ref.get(key), list) or not ref[key] or not all(isinstance(x, str) and x.strip() for x in ref[key]):
                raise ValueError(f"第 {i} 个参考缺 {key}（写清这张图管什么、不管什么）")
        if set(ref["may_control"]) & set(ref["must_not_control"]):
            raise ValueError(f"第 {i} 个参考的 may_control 与 must_not_control 重叠")
    return list(refs)


def reference_tokens(roles: Sequence[str], style: str) -> list[str]:
    """按同类素材顺序编号：H3 用 <Picture N>，Seedance 用 @图片N；首尾帧也占一个图片序号，不跳号。"""
    names = {"h3": {"image_url": "<Picture {}>", "video_url": "<Video {}>", "audio_url": "<Audio {}>"},
             "seedance": {"image_url": "@图片{}", "video_url": "@视频{}", "audio_url": "@音频{}"}}[style]
    count = {"image_url": 0, "video_url": 0, "audio_url": 0}
    out = []
    for role in roles:
        field = ROLE_FIELD[role]
        count[field] += 1
        out.append(names[field].format(count[field]))
    return out


def with_reference_contract(prompt: str, refs: Sequence[Mapping[str, Any]], tokens: Sequence[str],
                            language: str = "en") -> str:
    """把每张参考的名称、职责、管什么/不管什么按顺序追加到正文后，语言跟正文一致。"""
    if not refs:
        return prompt
    zh = language.casefold().startswith("zh")
    lines = []
    for ref, token in zip(refs, tokens):
        may, must = "、".join(ref["may_control"]) if zh else ", ".join(ref["may_control"]), \
            "、".join(ref["must_not_control"]) if zh else ", ".join(ref["must_not_control"])
        lines.append(f"{token}（{ref['label']}）只控制：{may}；不控制：{must}。" if zh
                     else f"{token} ({ref['label']}) controls only: {may}. It does not control: {must}.")
    return prompt.rstrip() + ("\n\n参考约束：\n" if zh else "\n\nReference contract:\n") + "\n".join(lines)


def _base(job: Mapping[str, Any], kind: str) -> tuple[str, dict]:
    if job.get("kind", kind) != kind:
        raise ValueError(f"这个通道只收 {kind} 任务")
    prompt = job.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("prompt 为空")
    params = dict(job.get("parameters") or {})
    if any(k.lower() in ("api_key", "token", "authorization", "key", "secret") for k in params):
        raise ValueError("parameters 里不能放密钥")
    return prompt, params


def _only(params: dict, allowed: set[str]) -> None:
    extra = set(params) - allowed
    if extra:
        raise ValueError("不支持的参数：" + ", ".join(sorted(extra)))


def _model(job: Mapping[str, Any], env: str | None = None) -> str:
    model = job.get("model") or (os.environ.get(env) if env else None)
    if not isinstance(model, str) or not model.strip():
        raise ValueError("缺模型 ID：由用户指定后写进 job 的 model（SKILL.md 硬约束 1b），不内置默认")
    return model.strip()


def compile_minimax_video(job: Mapping[str, Any], urls: Sequence[str], *, durations: tuple[int, int],
                          resolutions: set[str], ratios: set[str] | None = None) -> dict:
    """MiniMax 视频（H3）官方请求体。durations/resolutions/ratios 是账号实际开通型号的能力，调用方显式给。"""
    prompt, p = _base(job, "video")
    _only(p, {"duration", "resolution", "ratio", "prompt_language"})
    if not str(job.get("out", "")).casefold().endswith(".mp4"):
        raise ValueError("视频输出必须是 .mp4")
    refs = _refs(job)
    if len(urls) != len(refs):
        raise ValueError("参考地址数量与 references 不一致")
    d = p.get("duration")
    if not isinstance(d, int) or isinstance(d, bool) or not durations[0] <= d <= durations[1]:
        raise ValueError(f"duration 必须是 {durations[0]}–{durations[1]} 的整数秒")
    res = p.get("resolution")
    if res not in (resolutions & H3_RESOLUTIONS):
        raise ValueError(f"resolution 必须是已开通的 {sorted(resolutions & H3_RESOLUTIONS)} 之一")
    roles = [r["role"] for r in refs]
    for single in ("first_frame", "last_frame"):
        if roles.count(single) > 1:
            raise ValueError(f"{single} 只能有一个")
    if {"first_frame", "last_frame"} & set(roles) and {"reference_image", "reference_video", "reference_audio"} & set(roles):
        raise ValueError("H3 首尾帧与参考输入互斥：起始帧加身份图/底板要整组走 reference_image（六段 full-reference）")
    if "reference_audio" in roles and not {"reference_image", "reference_video"} & set(roles):
        raise ValueError("参考音频必须配至少一张参考图或一段参考视频")
    if roles.count("reference_image") > 9 or roles.count("reference_video") > 3 or roles.count("reference_audio") > 3:
        raise ValueError("超过素材上限：参考图 9、参考视频 3、参考音频 3")
    ratio = p.get("ratio")
    if ratio is not None and (ratio not in RATIOS or (ratios is not None and ratio not in ratios)):
        raise ValueError(f"ratio {ratio} 不在已开通范围")
    if not refs and (ratio is None or ratio == "adaptive"):
        raise ValueError("文生视频必须显式给 ratio，且不能是 adaptive")
    text = with_reference_contract(prompt, refs, reference_tokens(roles, "h3"), p.get("prompt_language", "en"))
    if len(text) > 7000:
        raise ValueError("正文加参考约束超过 7000 字符")
    content = [{"type": "text", "text": text}]
    for ref, url in zip(refs, urls):
        field = ROLE_FIELD[ref["role"]]
        content.append({"type": field, field: {"url": url}, "role": ref["role"]})
    body = {"model": _model(job), "content": content, "duration": d, "resolution": res}
    if ratio is not None:
        body["ratio"] = ratio
    return body


def compile_seedance(job: Mapping[str, Any], urls: Sequence[str], *, durations: tuple[int, int],
                     ratios: set[str] | None = None) -> dict:
    """Seedance 2.0/2.5 任务体；任务类型 reference/edit/extend 是创作决定，不从关键词猜。"""
    prompt, p = _base(job, "video")
    _only(p, {"duration", "ratio", "generate_audio", "omni_reference_task_type", "prompt_language"})
    if not str(job.get("out", "")).casefold().endswith(".mp4"):
        raise ValueError("视频输出必须是 .mp4")
    refs = _refs(job)
    if len(urls) != len(refs):
        raise ValueError("参考地址数量与 references 不一致")
    roles = [r["role"] for r in refs]
    for single in ("first_frame", "last_frame"):
        if roles.count(single) > 1:
            raise ValueError(f"{single} 只能有一个")
    d = p.get("duration")
    if d is not None and (not isinstance(d, int) or isinstance(d, bool)
                          or (d != -1 and not durations[0] <= d <= durations[1])):
        raise ValueError(f"duration 必须是 -1 或 {durations[0]}–{durations[1]} 的整数秒")
    ratio = p.get("ratio")
    if ratio is not None and (ratio not in RATIOS or (ratios is not None and ratio not in ratios)):
        raise ValueError(f"ratio {ratio} 不在已开通范围")
    task = p.get("omni_reference_task_type")
    if task not in (None, "auto", "reference", "edit", "extend"):
        raise ValueError("omni_reference_task_type 只能是 reference/edit/extend/auto")
    if task in ("edit", "extend") and "reference_video" not in roles:
        raise ValueError(f"{task} 必须有参考视频")
    if task == "edit" and (ratio != "adaptive" or d != -1):
        raise ValueError("edit 必须 ratio=adaptive、duration=-1")
    if task == "extend" and ratio != "adaptive":
        raise ValueError("extend 必须 ratio=adaptive")
    gen_audio = p.get("generate_audio")
    if gen_audio is not None and not isinstance(gen_audio, bool):
        raise ValueError("generate_audio 必须是布尔值")
    text = with_reference_contract(prompt, refs, reference_tokens(roles, "seedance"), p.get("prompt_language", "zh"))
    content = [{"type": "text", "text": text}]
    for ref, url in zip(refs, urls):
        field = ROLE_FIELD[ref["role"]]
        content.append({"type": field, field: {"url": url}, "role": ref["role"]})
    body: dict[str, Any] = {"model": _model(job), "content": content}
    for key, value in (("ratio", ratio), ("duration", d), ("generate_audio", gen_audio), ("omni_reference_task_type", task)):
        if value is not None:
            body[key] = value
    return body


def compile_minimax_speech(job: Mapping[str, Any]) -> dict:
    """一句台词的 TTS。prompt 就是送出的文本（剧本原句 + 可选的语气词/停顿标注），不是描述。"""
    text, p = _base(job, "tts")
    _only(p, {"voice_id", "emotion", "speed", "vol", "pitch", "sample_rate", "bitrate", "format",
              "language_boost", "pronunciation"})
    if len(text) > 5000:
        raise ValueError("TTS 文本超过 5000 字符")
    voice = p.get("voice_id")
    if not isinstance(voice, str) or not voice.strip() or voice != voice.strip():
        raise ValueError("缺 voice_id：音色写在视觉设定的 voice 里，由用户确认")
    lang = p.get("language_boost")
    if lang not in SPEECH_LANGUAGES:
        raise ValueError("language_boost 必须显式写台词语言（如 Japanese），不收 auto")
    fmt = p.get("format", Path(str(job.get("out", ""))).suffix.lstrip(".").casefold())
    if fmt not in ("mp3", "wav") or not str(job.get("out", "")).casefold().endswith("." + fmt):
        raise ValueError("format 必须是 mp3/wav 且与输出扩展名一致")
    sample_rate, bitrate = p.get("sample_rate", 32000), p.get("bitrate", 128000)
    if sample_rate not in (16000, 24000, 32000, 44100) or bitrate not in (32000, 64000, 128000, 256000):
        raise ValueError("sample_rate 或 bitrate 不在支持范围")
    voice_setting: dict[str, Any] = {"voice_id": voice}
    emotion = p.get("emotion")
    if emotion is not None:
        if emotion not in SPEECH_EMOTIONS:
            raise ValueError("emotion 只收 happy/sad/angry/fearful/disgusted/surprised；平读不传")
        voice_setting["emotion"] = emotion
    for name, low, high in (("speed", 0.5, 2.0), ("vol", 0.1, 10.0)):
        if p.get(name) is not None:
            value = p[name]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not low <= value <= high:
                raise ValueError(f"{name} 必须在 {low}–{high}")
            voice_setting[name] = float(value)
    if p.get("pitch") is not None:
        if isinstance(p["pitch"], bool) or not isinstance(p["pitch"], int) or not -12 <= p["pitch"] <= 12:
            raise ValueError("pitch 必须是 -12–12 的整数")
        voice_setting["pitch"] = p["pitch"]
    body = {"model": _model(job), "text": text, "stream": False, "output_format": "hex",
            "voice_setting": voice_setting, "language_boost": lang,
            "audio_setting": {"sample_rate": sample_rate, "bitrate": bitrate, "format": fmt}}
    pron = p.get("pronunciation")
    if pron is not None:
        if not isinstance(pron, Mapping) or not pron:
            raise ValueError("pronunciation 必须是非空的 {原词: 读法}")
        tone = []
        for word, reading in pron.items():
            if not (isinstance(word, str) and isinstance(reading, str) and word.strip() and reading.strip() and "/" not in word):
                raise ValueError("pronunciation 每项是短词和读法")
            if word not in text:
                raise ValueError(f"pronunciation 的「{word}」不在这句台词里")
            tone.append(f"{word}/{reading.strip()}")
        body["pronunciation_dict"] = {"tone": tone}
    return body


def compile_minimax_music(job: Mapping[str, Any]) -> dict:
    """配乐或主题曲源音轨（music-3.0）。歌词必须是用户提供或确认的原文，不让供应商改写。"""
    prompt, p = _base(job, "music")
    _only(p, {"lyrics", "is_instrumental", "lyrics_optimizer", "sample_rate", "bitrate", "format"})
    if p.get("lyrics_optimizer"):
        raise ValueError("lyrics_optimizer 不开：供应商改写的歌词没有经过用户确认")
    instrumental = p.get("is_instrumental", False)
    lyrics = p.get("lyrics")
    if not isinstance(instrumental, bool):
        raise ValueError("is_instrumental 必须是布尔值")
    if instrumental and lyrics not in (None, ""):
        raise ValueError("纯配乐不带歌词")
    if not instrumental and (not isinstance(lyrics, str) or not lyrics.strip()):
        raise ValueError("带人声的歌必须给用户确认过的歌词")
    if len(prompt) > 2000 or (isinstance(lyrics, str) and len(lyrics) > 3500):
        raise ValueError("prompt 或歌词超长")
    fmt = p.get("format", Path(str(job.get("out", ""))).suffix.lstrip(".").casefold())
    if fmt not in ("mp3", "wav") or not str(job.get("out", "")).casefold().endswith("." + fmt):
        raise ValueError("format 必须是 mp3/wav 且与输出扩展名一致")
    sample_rate, bitrate = p.get("sample_rate", 44100), p.get("bitrate", 256000)
    if sample_rate not in (16000, 24000, 32000, 44100) or bitrate not in (32000, 64000, 128000, 256000):
        raise ValueError("sample_rate 或 bitrate 不在支持范围")
    body = {"model": "music-3.0", "prompt": prompt, "stream": False, "output_format": "hex",
            "lyrics_optimizer": False, "is_instrumental": instrumental,
            "audio_setting": {"sample_rate": sample_rate, "bitrate": bitrate, "format": fmt}}
    if lyrics:
        body["lyrics"] = lyrics
    return body


def compile_gpt_image(job: Mapping[str, Any]) -> dict:
    """GPT Image 2：无参考走 generations，有参考走 edits（multipart，由 run 组装）。"""
    prompt, p = _base(job, "image")
    _only(p, {"width", "height", "size", "quality", "background", "moderation", "prompt_language"})
    refs = [r for r in (job.get("references") or [])]
    if len(refs) > 16 or any(Path(r["path"]).suffix.casefold() not in (".png", ".jpg", ".jpeg", ".webp") for r in refs):
        raise ValueError("最多 16 张 png/jpg/webp 参考图")
    if refs:
        _refs({"references": [{**r, "role": r.get("role", "reference_image")} for r in refs]})
    language = p.pop("prompt_language", "en")
    if refs:
        prompt = with_reference_contract(prompt, refs, [f"Image {i}" for i in range(1, len(refs) + 1)], language)
    if "width" in p or "height" in p:
        w, h = p.pop("width", None), p.pop("height", None)
        if not isinstance(w, int) or not isinstance(h, int) or "size" in p:
            raise ValueError("width/height 成对给，且不和 size 同时给")
        p["size"] = f"{w}x{h}"
    size = p.get("size")
    if size not in (None, "auto"):
        try:
            w, h = (int(x) for x in str(size).split("x", 1))
        except ValueError as exc:
            raise ValueError("size 写成 宽x高") from exc
        if w % 16 or h % 16 or not 1 / 3 <= w / h <= 3 or max(w, h) > 3840 or not 655_360 <= w * h <= 8_294_400:
            raise ValueError("尺寸要被 16 整除、宽高比 1:3–3:1、边长 ≤3840、总像素 65.5 万–829 万")
    if p.get("background") not in (None, "auto", "opaque"):
        raise ValueError("background 只收 auto/opaque（不支持透明）")
    if p.get("quality") not in (None, "auto", "low", "medium", "high"):
        raise ValueError("quality 只收 auto/low/medium/high")
    if p.get("moderation") not in (None, "auto", "low"):
        raise ValueError("moderation 只收 auto/low")
    fmt = {".png": "png", ".jpg": "jpeg", ".jpeg": "jpeg", ".webp": "webp"}.get(Path(str(job.get("out", ""))).suffix.casefold())
    if not fmt:
        raise ValueError("图片输出扩展名必须是 png/jpg/webp")
    if len(prompt) > 32000:
        raise ValueError("prompt 超长")
    return {"model": "gpt-image-2", "prompt": prompt, "n": 1, "output_format": fmt, **p}


# ---- 运行时：环境配置、HTTP、账本 ---------------------------------------------------------------
Transport = Callable[[str, str, bytes | None, Mapping[str, str]], tuple[int, bytes]]


def urllib_transport(method: str, url: str, body: bytes | None, headers: Mapping[str, str]) -> tuple[int, bytes]:
    req = urllib.request.Request(url, data=body, method=method, headers=dict(headers))
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, b""  # 不保留错误正文：可能带提示词或账号信息


def _env_range(name: str) -> tuple[int, int]:
    lo, hi = os.environ.get(name + "_MIN_DURATION"), os.environ.get(name + "_MAX_DURATION")
    if lo is None or hi is None:
        raise ValueError(f"缺 {name}_MIN_DURATION / {name}_MAX_DURATION：按账号开通型号的时长区间设置")
    return int(lo), int(hi)


def _env_set(name: str) -> set[str] | None:
    raw = os.environ.get(name)
    return {x.strip() for x in raw.split(",") if x.strip()} if raw else None


def compile_job(job: Mapping[str, Any], root: Path) -> dict:
    provider = job.get("provider")
    if provider not in KIND:
        raise ValueError(f"provider 只能是 {sorted(KIND)}")
    job = {**job, "kind": KIND[provider]}
    if provider == "minimax-video":
        res = _env_set("MINIMAX_VIDEO_RESOLUTIONS")
        if not res:
            raise ValueError("缺 MINIMAX_VIDEO_RESOLUTIONS：写账号型号实际接受的分辨率，如 768P,2K")
        return compile_minimax_video(job, inline_references(_refs(job), root), durations=_env_range("MINIMAX_VIDEO"),
                                     resolutions=res, ratios=_env_set("MINIMAX_VIDEO_RATIOS"))
    if provider == "seedance":
        return compile_seedance(job, inline_references(_refs(job), root), durations=_env_range("SEEDANCE"),
                                ratios=_env_set("SEEDANCE_ALLOWED_RATIOS"))
    return {"minimax-speech": compile_minimax_speech, "minimax-music": compile_minimax_music,
            "gpt-image-2": compile_gpt_image}[provider](job)


def _http_json(transport: Transport, method: str, url: str, token: str, body: Any = None) -> dict:
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
    headers = {"Authorization": f"Bearer {token}"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    try:
        status, raw = transport(method, url, data, headers)
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        raise ProviderError(f"网络错误：{type(exc).__name__}", category="network", retryable=True) from exc
    if not 200 <= status < 300:
        raise ProviderError(f"HTTP {status}", category="rate_limit" if status == 429 else "http",
                            retryable=status == 429 or status >= 500, http_status=status,
                            rejected=400 <= status < 500)  # 5xx 可能是网关超时而后端已受理：按未知处理
    try:
        doc = json.loads(raw)
    except (ValueError, UnicodeError) as exc:
        raise ProviderError("响应不是 JSON", category="response") from exc
    if not isinstance(doc, dict):
        raise ProviderError("响应格式不对", category="response")
    base = doc.get("base_resp")
    if isinstance(base, Mapping) and base.get("status_code") not in (0, None):
        raise ProviderError(f"服务端拒绝：status_code {base.get('status_code')}", category="rejected", rejected=True)
    return doc


def _get_retry(fn: Callable[[], Any], tries: int = 360, wait: float = 10.0) -> Any:
    """只重试 GET：网络抖动和 429/5xx 等一会儿再查，已提交的任务不放弃。"""
    for i in range(tries):
        try:
            return fn()
        except ProviderError as exc:
            if not exc.retryable or i == tries - 1:
                raise
            time.sleep(wait)
    raise AssertionError("unreachable")


class Runner:
    def __init__(self, root: Path, transport: Transport = urllib_transport, poll: float = 5.0,
                 get_wait: float = 10.0, timeout: float = 3600.0):
        self.root = Path(root).resolve()
        self.client = Client(root=self.root, channel="providers")  # 只用它的账本、提交锁与 STOP/DEADLINE，不用它的中转 HTTP
        self.transport, self.poll, self.get_wait, self.timeout = transport, poll, get_wait, timeout

    def _base_token(self, provider: str) -> tuple[str, str]:
        env_url, default, env_key = BASES[provider]
        base = os.environ.get(env_url, default).rstrip("/")
        parsed = urllib.parse.urlparse(base)
        if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
            raise ValueError(f"{env_url} 必须是不带账号密码的 https 地址")
        token = os.environ.get(env_key)
        if not token:
            raise SystemExit(f"缺 {env_key}（只从环境变量读，不要写进文件）")
        return base, token

    def run(self, job: Mapping[str, Any]) -> Path:
        provider, name = job.get("provider"), job.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("job 缺 name（任务名，账本按它找同名未收回任务）")
        out = (self.root / str(job.get("out", ""))).resolve()
        if out.exists():
            raise ValueError(f"{out} 已存在：重拍开新 take，不覆盖旧产物")
        body = compile_job(job, self.root)
        fingerprint = hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        base, token = self._base_token(provider)
        c = self.client
        with c.submit_lock():
            unknown = c.unresolved()
            if unknown:
                raise SubmissionUnknown("先对账未决提交，再继续生产：" + ", ".join(r["request_id"] for r in unknown))
            pending = c.pending(name)
            if pending:
                if pending.get("fingerprint") != fingerprint or Path(pending["out"]).resolve() != out:
                    raise SubmissionUnknown("同名未收回任务与当前输入不同；先 collect 原任务，不重新提交")
                task = pending["job"]
                if str(task).startswith("sync-"):
                    raise SubmissionUnknown(f"同步任务 {task} 已受理但结果没落盘；核对供应商记录后按 runtime-boundaries 处理")
            else:
                c.guard()
                request_id = uuid.uuid4().hex
                intent = {"request_id": request_id, "status": "submission_intent", "name": name, "provider": provider,
                          "kind": KIND[provider], "out": str(out), "fingerprint": fingerprint,
                          "profile": body.get("model"), "res": body.get("resolution") or body.get("size")}
                c._append(intent)
                task = self._submit(provider, base, token, body, job, out, intent)
                if task is None:  # 同步通道：结果已在 _submit 里落盘
                    return out
        return self.collect(provider, task, out)

    def _submit(self, provider: str, base: str, token: str, body: dict, job: Mapping[str, Any],
                out: Path, intent: dict) -> str | None:
        c = self.client
        url = {"minimax-video": f"{base}/video_generation", "seedance": f"{base}/contents/generations/tasks",
               "minimax-speech": f"{base}/t2a_v2", "minimax-music": f"{base}/music_generation"}.get(provider)
        try:
            if provider == "gpt-image-2":
                doc = self._gpt_image(base, token, body, job)
            else:
                doc = _http_json(self.transport, "POST", url, token, body)
        except ProviderError as exc:
            if exc.rejected:  # 服务端给了明确的拒绝响应：没有受理，不计费
                c._append({**intent, "status": "not_submitted", "evidence": str(exc)})
            else:
                c._append({**intent, "status": "submission_unknown", "error_type": exc.category})
                raise SubmissionUnknown(f"提交结果未知：{intent['request_id']}；先查供应商任务记录并 reconcile，禁止直接重投") from exc
            raise
        if provider in ("minimax-video", "seedance"):
            task = doc.get("task_id") if provider == "minimax-video" else doc.get("id")
            if not isinstance(task, str) or not task.strip():
                c._append({**intent, "status": "submission_unknown", "error_type": "missing_task_id"})
                raise SubmissionUnknown(f"响应里没有任务号：{intent['request_id']}；先对账")
            c._append({**intent, "status": "submitted", "job": task, "seconds": body.get("duration")})
            return task
        data = self._sync_bytes(provider, doc)  # 同步通道：响应里就是结果
        sync_id = "sync-" + intent["request_id"]
        c._append({**intent, "status": "submitted", "job": sync_id})
        self._write(out, data, sync_id)
        return None

    def _gpt_image(self, base: str, token: str, body: dict, job: Mapping[str, Any]) -> dict:
        refs = job.get("references") or []
        if not refs:
            return _http_json(self.transport, "POST", f"{base}/images/generations", token, body)
        boundary = "----dramaforge" + uuid.uuid4().hex
        parts = []
        for key, value in body.items():
            parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode())
        for ref in refs:
            path = (self.root / ref["path"]).resolve()
            data = path.read_bytes()
            check_media(path.name, data)
            parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="image[]"; filename="{path.name}"\r\n'
                         f'Content-Type: {MIME[path.suffix.casefold()]}\r\n\r\n'.encode() + data + b"\r\n")
        payload = b"".join(parts) + f"--{boundary}--\r\n".encode()
        try:
            status, raw = self.transport("POST", f"{base}/images/edits", payload,
                                         {"Authorization": f"Bearer {token}", "Content-Type": f"multipart/form-data; boundary={boundary}"})
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            raise ProviderError(f"网络错误：{type(exc).__name__}", category="network", retryable=True) from exc
        if not 200 <= status < 300:
            raise ProviderError(f"HTTP {status}", category="http", http_status=status, rejected=400 <= status < 500,
                                retryable=status == 429 or status >= 500)
        return json.loads(raw)

    @staticmethod
    def _sync_bytes(provider: str, doc: Mapping[str, Any]) -> bytes:
        try:
            if provider == "gpt-image-2":
                items = doc.get("data")
                if not isinstance(items, list) or len(items) != 1:
                    raise ValueError
                return base64.b64decode(items[0]["b64_json"], validate=True)
            data = doc.get("data") or {}
            if provider == "minimax-music" and data.get("status") != 2:
                raise ValueError
            content = bytes.fromhex(data["audio"])
            if not content:
                raise ValueError
            return content
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            raise ProviderError("响应里没有可用的结果数据", category="response") from exc

    def _write(self, out: Path, data: bytes, task: str) -> None:
        try:
            check_media(out.name, data)
        except ProviderError:
            self.client._mark(task, "download_failed", out)
            raise
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp = out.with_suffix(out.suffix + ".part")
        tmp.write_bytes(data)
        os.replace(tmp, out)
        self.client._mark(task, "collected", out)

    def collect(self, provider: str, task: str, out: Path) -> Path:
        """按任务号轮询并下载；不提交任何东西。"""
        if provider not in ("minimax-video", "seedance"):
            raise ValueError("只有异步视频通道需要 collect；同步通道的结果随响应返回")
        base, token = self._base_token(provider)
        quoted = urllib.parse.quote(task, safe="")
        url = f"{base}/query/video_generation/{quoted}" if provider == "minimax-video" else f"{base}/contents/generations/tasks/{quoted}"
        deadline = time.monotonic() + self.timeout
        while True:
            doc = _get_retry(lambda: _http_json(self.transport, "GET", url, token), wait=self.get_wait)
            node = doc.get("task") if provider == "minimax-video" else doc
            status = str((node or {}).get("status", "")).casefold()
            if status in ("succeeded", "success"):
                content = (node or {}).get("content") or {}
                link = content.get("url") if provider == "minimax-video" else content.get("video_url")
                break
            if status in FAILED:
                self.client._mark(task, "failed", out, {"provider_status": status})
                raise ProviderError(f"任务 {task} 终态失败：{status}", category="task_failed")
            if status not in RUNNING:
                raise ProviderError(f"任务 {task} 返回未知状态 {status!r}；不重投，稍后再 collect", category="response")
            if time.monotonic() > deadline:
                raise ProviderError(f"任务 {task} 轮询超时；稍后再 collect，不重投", category="timeout", retryable=True)
            time.sleep(self.poll)
        if not isinstance(link, str) or urllib.parse.urlparse(link).scheme != "https":
            raise ProviderError("结果地址缺失或不是 https", category="response")

        def fetch() -> bytes:
            try:
                status, raw = self.transport("GET", link, None, {})
            except (urllib.error.URLError, OSError, TimeoutError) as exc:
                raise ProviderError("下载网络错误", category="network", retryable=True) from exc
            if not 200 <= status < 300 or not raw:
                raise ProviderError(f"下载失败 HTTP {status}", category="http", retryable=True)
            return raw
        try:
            data = _get_retry(fetch, wait=self.get_wait)
        except ProviderError:
            self.client._mark(task, "download_failed", out)
            raise
        self._write(out, data, task)
        return out


def _redacted(body: Any) -> Any:
    if isinstance(body, dict):
        return {k: _redacted(v) for k, v in body.items()}
    if isinstance(body, list):
        return [_redacted(v) for v in body]
    if isinstance(body, str) and body.startswith("data:") and ";base64," in body:
        return body.split(",", 1)[0] + f",<{len(body)} chars>"
    return body


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("compile", "run"):
        sp = sub.add_parser(name)
        sp.add_argument("--job", required=True)
        sp.add_argument("--root", default=".")
    co = sub.add_parser("collect")
    co.add_argument("--provider", required=True, choices=["minimax-video", "seedance"])
    co.add_argument("--task", required=True)
    co.add_argument("--out", required=True)
    co.add_argument("--root", default=".")
    a = ap.parse_args(argv)
    root = Path(a.root)
    try:
        if a.cmd == "compile":
            job = json.loads(Path(a.job).read_text(encoding="utf-8"))
            print(json.dumps(_redacted(compile_job(job, root)), ensure_ascii=False, indent=2))
        elif a.cmd == "run":
            job = json.loads(Path(a.job).read_text(encoding="utf-8"))
            print("OK", Runner(root).run(job))
        else:
            print("COLLECTED", Runner(root).collect(a.provider, a.task, (root / a.out).resolve()))
    except (ValueError, ProviderError, SubmissionUnknown) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except Stop as exc:
        print(str(exc))
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
