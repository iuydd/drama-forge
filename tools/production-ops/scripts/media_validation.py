#!/usr/bin/env python3
"""Decode/probe actual media and package a strictly allowlisted blind review.

Technical decoding is not semantic acceptance. Blind packaging isolates files,
not the review model's previous memory; the host must start a fresh reviewer.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile
from brain_handoff import verify_record, text


def probe_media(path:Path,kind:str)->dict:
    if kind=='document':return {'decoded':True,'kind':'document','semantic_quality_verified':False}
    if kind=='image':
        from PIL import Image
        with Image.open(path) as im:
            size=im.size;mode=im.mode;im.verify()
        return {'decoded':True,'kind':'image','width':size[0],'height':size[1],'mode':mode,'semantic_quality_verified':False}
    if kind not in {'video','audio'}:raise ValueError('unsupported media type')
    p=subprocess.run(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(path)],capture_output=True,text=True,timeout=30)
    if p.returncode:raise ValueError('actual media decoder failed')
    data=json.loads(p.stdout);streams=data.get('streams',[])
    required='video' if kind=='video' else 'audio'
    if not any(s.get('codec_type')==required for s in streams):raise ValueError('media type does not match decoded stream')
    return {'decoded':True,'kind':kind,'streams':[{k:s.get(k) for k in ('codec_type','width','height','sample_rate','r_frame_rate','duration','nb_frames')} for s in streams],
            'duration':data.get('format',{}).get('duration'),'semantic_quality_verified':False}


def blind_capsule(media:list[dict],brief:str,root:Path,destination:Path,*,allowed_prior_context:str='')->dict:
    if not media or not text(brief):raise ValueError('actual review media and neutral brief required')
    allowed={'image','video','audio'}
    for rec in media:
        if rec.get('media_kind') not in allowed:raise ValueError('blind capsule rejects scripts, target answers, logs and unknown file roles')
        errors=verify_record(rec,root)
        if errors:raise ValueError('; '.join(errors))
        probe_media(root/rec['path'],rec['media_kind'])
    manifest=[]
    with zipfile.ZipFile(destination,'x',compression=zipfile.ZIP_STORED) as z:
        z.writestr('REVIEW.txt',brief+'\n\nAllowed prior context:\n'+allowed_prior_context)
        for i,rec in enumerate(media):
            suffix=Path(rec['path']).suffix.lower()
            name=f'media/{i:03d}-{rec["sha256"][:16]}{suffix}'
            z.write(root/rec['path'],name)
            manifest.append({'file':name,'sha256':rec['sha256'],'media_kind':rec['media_kind']})
        z.writestr('manifest.json',json.dumps(manifest,ensure_ascii=False,indent=2))
    return {'files':len(media),'file_allowlist_enforced':True,'reviewer_memory_isolation_verified':False}
