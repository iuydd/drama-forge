"""fal 超分步骤离线自测：mock fal 队列与 CDN，本机 ffmpeg 造片，验证请求体、1080p 成片、音轨 remux、原片留存。"""
import sys, json, subprocess, tempfile, os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import fal_client as F
d = Path(tempfile.mkdtemp())
# 造一个带音轨的 480p 原片和一个无音轨的 1080p "超分结果"
subprocess.run(["ffmpeg","-v","error","-f","lavfi","-i","testsrc=s=854x480:r=24:d=2","-f","lavfi","-i","sine=d=2","-shortest","-pix_fmt","yuv420p",str(d/"src.mp4")],check=True)
subprocess.run(["ffmpeg","-v","error","-f","lavfi","-i","testsrc=s=1920x1080:r=24:d=2","-pix_fmt","yuv420p",str(d/"up.mp4")],check=True)
SRC=(d/"src.mp4").read_bytes(); UP=(d/"up.mp4").read_bytes()
posts=[]
class R:
    def __init__(s,j=None,c=b"",code=200): s._j=j; s.content=c; s.status_code=code; s.text=""
    def json(s): return s._j
    def raise_for_status(s): pass
os.environ["FAL_KEY"]="x"
c = F.FalClient("minimax/h3-max-turbo/image-to-video", root=d, log_dir=d, poll=0, upscale=F.upscale_config(True))
c.s.post=lambda u,json,timeout: (posts.append((u,json)), R({"request_id":"U1"}))[1]
c.rget=lambda u: R({"status":"COMPLETED"})
c.s.get=lambda u,timeout: R({"video":{"url":"https://cdn/up.mp4"},"duration":2})
F.requests.get=lambda u,timeout: R(c=SRC if "src" in u else UP)
c._mark=lambda *a,**k: None
out=d/"视频"/"V_S01.mp4"
c.download({"id":"J1","video":{"url":"https://cdn/src.mp4"}},"video",out)
u,body=posts[0]
assert u.endswith("fal-ai/bytedance-upscaler/upscale/video") and body["video_url"]=="https://cdn/src.mp4" and body["target_fps"]==24, (u,body)
pr=subprocess.run(["ffprobe","-v","error","-show_entries","stream=codec_type,width,height","-of","csv=p=0",str(out)],capture_output=True,text=True).stdout.split()
print(pr); assert "video,1920,1080" in pr and any(x.startswith("audio") for x in pr)
assert (d/"视频"/"_src"/"V_S01.mp4").exists() and not list((d/"视频").glob("*.part*"))
led=[json.loads(l) for l in (d/"jobs.jsonl").read_text().splitlines()] if (d/"jobs.jsonl").exists() else []
print("ledger", [r.get("status") for r in led]); print("OK")
