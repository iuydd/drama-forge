#!/usr/bin/env python3
"""Validate and render an explicit cut-only timeline; never chooses story or generates video.

Video coordinates are integer frames; audio coordinates are integer samples.
All ranges are [in, out). This tool requires same-CFR, same-size, same-color
sources, and explicitly reviewed PCM WAV audio. Rendered masters are candidates,
not final semantic, loudness, subtitle, or publication acceptance.
"""
from __future__ import annotations
import argparse
from collections import Counter
from fractions import Fraction
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from typing import Any

VERSION = '1.1.0'
TOP = {'schema_version','status','episode_id','revision','fps','sample_rate','channels',
       'width','height','pixel_format','color','duration_frames','audio_intent','sources',
       'video','audio','events','event_orders','sync_links','allowed_dialogue_overlaps',
       'render_policy','note','presentation'}
VKEYS = {'id','shot_id','source_id','src_in','src_out','dst_in','role','cut_reason',
         'transition','speed','visible_dialogue','note'}
AKEYS = {'id','source_id','src_in','src_out','dst_in','role','gain_db','fade_in_samples',
         'fade_out_samples','line_ids','note'}
SOURCE_KEYS = {'id','kind','path','sha256','review','units','fps','width','height',
               'pixel_format','color','sample_rate','channels','note'}
EVENT_KEYS = {'event_id','kind','source_id','src_in','src_out','required','allow_repeat','line_id','note','story_phase','perceivers'}
SPEECH = {'dialogue','inner','voiceover','system'}
AUDIO_ROLES = SPEECH | {'ambience','sfx','music'}
COLOR_KEYS = {'space','primaries','transfer','range'}
PIXEL_FORMATS = {'yuv420p','yuv422p','yuv444p','yuv420p10le','yuv422p10le','yuv444p10le'}
NAME = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]*\Z')


def digest(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, ensure_ascii=False, sort_keys=True,
                         separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def file_sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def integer(x: Any, minimum: int = 0) -> bool:
    return type(x) is int and x >= minimum


def nonempty(x: Any) -> bool:
    return isinstance(x, str) and bool(x.strip())


def ident(x: Any) -> bool:
    return isinstance(x, str) and bool(NAME.fullmatch(x))


def rate(x: Any) -> Fraction:
    if not isinstance(x, str) or not re.fullmatch(r'[1-9][0-9]*/[1-9][0-9]*', x):
        raise ValueError('fps must be a positive rational string, e.g. 24/1')
    f = Fraction(x)
    if not 1 <= f <= 240:
        raise ValueError('fps outside supported 1..240 range')
    return f


def sample_at(frame: int, fps: Fraction, sample_rate: int) -> int:
    """Round absolute time once, half up. Never sum rounded frame durations."""
    x = Fraction(frame * sample_rate, 1) / fps
    return (2*x.numerator + x.denominator) // (2*x.denominator)


def safe_path(root: Path, raw: Any, exists: bool = True) -> Path:
    if (not isinstance(raw, str) or not raw or '\\' in raw or Path(raw).is_absolute()
            or any(p in ('', '.', '..') for p in raw.split('/'))):
        raise ValueError('unsafe project-relative path')
    root = root.resolve(strict=True)
    p = root / raw
    cursor = root
    for part in raw.split('/'):
        cursor /= part
        if cursor.is_symlink():
            raise ValueError('symlink not allowed in media path')
    if not p.resolve().is_relative_to(root):
        raise ValueError('path escapes project')
    if exists and (not p.is_file() or not p.stat().st_size):
        raise ValueError('missing or empty file: ' + raw)
    return p


def record_path(root: Path, record: Any) -> Path:
    if not isinstance(record, dict):
        raise ValueError('file record required')
    p = safe_path(root, record.get('path'))
    if not isinstance(record.get('sha256'), str) or file_sha(p) != record['sha256']:
        raise ValueError('file hash mismatch: ' + str(record.get('path')))
    return p


def ranges_cover(ranges: Any, start: int, end: int) -> bool:
    if not isinstance(ranges, list) or not ranges:
        return False
    cursor = start
    try:
        for r in sorted(ranges):
            if (not isinstance(r, list) or len(r) != 2
                    or not integer(r[0]) or not integer(r[1], 1) or r[1] <= r[0]):
                return False
            if r[1] <= cursor:
                continue
            if r[0] > cursor:
                return False
            cursor = max(cursor, r[1])
            if cursor >= end:
                return True
    except TypeError:
        return False
    return False


def _schema(t: dict) -> tuple[list[str], dict, Fraction]:
    e: list[str] = []
    extra = set(t) - TOP
    if extra:
        e.append('unsupported timeline fields: ' + ', '.join(sorted(extra)))
    if t.get('schema_version') != 'edit-timeline-1':
        e.append('unsupported schema_version')
    if t.get('status') not in {'DRAFT','LOCKED'}:
        e.append('status must be DRAFT or LOCKED')
    if not ident(t.get('episode_id')) or not nonempty(t.get('revision')):
        e.append('episode_id and revision required')
    try:
        fps = rate(t.get('fps'))
    except ValueError as ex:
        e.append(str(ex)); fps = Fraction(24)
    for k in ('width','height','duration_frames'):
        if not integer(t.get(k), 1):
            e.append(k + ': positive integer required')
    if t.get('sample_rate') not in {44100,48000,96000} or type(t.get('sample_rate')) is not int:
        e.append('unsupported sample_rate')
    if t.get('channels') not in {1,2} or type(t.get('channels')) is not int:
        e.append('channels must be 1 or 2')
    if t.get('pixel_format') not in PIXEL_FORMATS:
        e.append('unsupported pixel_format; no implicit conversion')
    color = t.get('color')
    if not isinstance(color, dict) or set(color) != COLOR_KEYS:
        e.append('explicit color dictionary required')
    elif (any(color[k] not in {'bt709','unspecified'} for k in ('space','primaries','transfer'))
          or color['range'] not in {'tv','pc','unspecified'}):
        e.append('basic renderer only supports matched SDR BT.709/unspecified tags')
    if t.get('audio_intent') not in {'sound','silent'}:
        e.append('explicit audio_intent required')
    if t.get('render_policy') != {'video_codec':'ffv1','audio_codec':'pcm_s24le','container':'mkv'}:
        e.append('basic renderer requires explicit FFV1/PCM/MKV working-master policy')
    sources = t.get('sources')
    by_id: dict = {}
    if not isinstance(sources, list) or not sources:
        e.append('nonempty sources required'); sources = []
    for s in sources:
        if not isinstance(s, dict):
            e.append('source must be object'); continue
        sid = s.get('id')
        if not ident(sid) or sid in by_id:
            e.append('invalid/duplicate source id'); continue
        by_id[sid] = s
        if set(s) - SOURCE_KEYS:
            e.append(sid + ': unsupported source fields')
        if s.get('kind') not in {'video','audio'} or not integer(s.get('units'),1):
            e.append(sid + ': source kind/units invalid')
        if s.get('kind') == 'video':
            try:
                if rate(s.get('fps')) != fps:
                    e.append(sid + ': fps mismatch; explicit conform required')
            except ValueError:
                e.append(sid + ': invalid source fps')
            for k in ('width','height','pixel_format','color'):
                if s.get(k) != t.get(k):
                    e.append(sid + ': mismatched ' + k)
        else:
            for k in ('sample_rate','channels'):
                if s.get(k) != t.get(k):
                    e.append(sid + ': mismatched ' + k)
    return e, by_id, fps


def validate(t: Any) -> dict:
    """Checks explicit data; PASS does not mean reviewed files or good editing."""
    if not isinstance(t, dict):
        return {'status':'BLOCKED','errors':['timeline object required'],'executed':False}
    e, sources, fps = _schema(t)
    if e:
        return {'status':'BLOCKED','errors':e,'executed':False}
    sr, total = t['sample_rate'], t['duration_frames']
    total_samples = sample_at(total, fps, sr)
    vid, aud = t.get('video'), t.get('audio')
    if not isinstance(vid, list) or not vid:
        e.append('nonempty video array required'); vid = []
    if not isinstance(aud, list):
        e.append('audio array required'); aud = []
    if t['audio_intent'] == 'sound' and not aud:
        e.append('sound timeline lacks explicit audio; native tracks are not copied')
    if t['audio_intent'] == 'silent' and aud:
        e.append('silent intent conflicts with audio clips')
    clips: dict = {}
    cursor = 0
    for kind, arr, limit, keys in [('video',vid,total,VKEYS),('audio',aud,total_samples,AKEYS)]:
        for c in arr:
            if not isinstance(c, dict) or not ident(c.get('id')):
                e.append('invalid clip object/id'); continue
            cid = c['id']
            if cid in clips:
                e.append('duplicate clip id: ' + cid)
            clips[cid] = (kind, c)
            if set(c) - keys:
                e.append(cid + ': unsupported clip fields')
            s = sources.get(c.get('source_id'))
            if not s or s['kind'] != kind:
                e.append(cid + ': invalid source kind/id'); continue
            if any(not integer(c.get(k)) for k in ('src_in','src_out','dst_in')):
                e.append(cid + ': coordinates must be nonnegative integers'); continue
            start, end, dst = c['src_in'], c['src_out'], c['dst_in']
            if not 0 <= start < end <= s['units']:
                e.append(cid + ': source range invalid/out of bounds')
            if dst + end-start > limit:
                e.append(cid + ': beyond timeline end; no silent truncation')
            if kind == 'video':
                if dst != cursor:
                    e.append(cid + ': picture gap/overlap or unsorted timeline')
                cursor = dst + end-start
                if c.get('transition') != 'cut' or c.get('speed') != '1/1':
                    e.append(cid + ': unsupported transition/retime')
                if (not ident(c.get('shot_id')) or not nonempty(c.get('role'))
                        or not nonempty(c.get('cut_reason')) or type(c.get('visible_dialogue')) is not bool):
                    e.append(cid + ': shot/role/cut reason/visible_dialogue required')
            else:
                if c.get('role') not in AUDIO_ROLES:
                    e.append(cid + ': unsupported audio role')
                gain = c.get('gain_db')
                if type(gain) not in (int,float) or not math.isfinite(gain) or not -60 <= gain <= 12:
                    e.append(cid + ': invalid explicit gain_db')
                for k in ('fade_in_samples','fade_out_samples'):
                    if not integer(c.get(k)):
                        e.append(cid + ': invalid ' + k)
                if all(integer(c.get(k)) for k in ('fade_in_samples','fade_out_samples')):
                    if c['fade_in_samples'] + c['fade_out_samples'] > end-start:
                        e.append(cid + ': fades overlap or exceed clip')
                lines = c.get('line_ids')
                if (not isinstance(lines,list) or any(not ident(x) for x in lines)
                        or len(set(lines)) != len(lines)):
                    e.append(cid + ': invalid line_ids')
                elif c.get('role') not in SPEECH and lines:
                    e.append(cid + ': dialogue cannot be mislabeled as music/effect')
    if cursor != total:
        e.append('picture does not cover exact duration_frames')
    if e:
        return {'status':'BLOCKED','errors':e,'executed':False}
    events = t.get('events')
    placements: dict[str,list[tuple[Fraction,Fraction,str]]] = {}
    event_map = {}
    expected_lines = Counter()
    if not isinstance(events,list):
        e.append('events array required'); events = []
    for ev in events:
        if not isinstance(ev,dict) or not ident(ev.get('event_id')):
            e.append('invalid event'); continue
        eid = ev['event_id']
        if eid in event_map:
            e.append('duplicate event_id: '+eid)
        event_map[eid] = ev
        if set(ev) - EVENT_KEYS:
            e.append(eid + ': unsupported event fields')
        kind, sid = ev.get('kind'), ev.get('source_id')
        if kind not in {'video','audio'} or sid not in sources or sources[sid]['kind'] != kind:
            e.append(eid + ': invalid event source'); continue
        if (not integer(ev.get('src_in')) or not integer(ev.get('src_out'),1)
                or not ev['src_in'] < ev['src_out'] <= sources[sid]['units']
                or type(ev.get('required')) is not bool or type(ev.get('allow_repeat')) is not bool):
            e.append(eid + ': invalid event bounds/policy'); continue
        arr = vid if kind == 'video' else aud
        placements[eid] = []
        for c in arr:
            if c['source_id'] != sid:
                continue
            if max(c['src_in'],ev['src_in']) >= min(c['src_out'],ev['src_out']):
                continue
            if not c['src_in'] <= ev['src_in'] < ev['src_out'] <= c['src_out']:
                e.append(eid + ': event partially cut in ' + c['id']); continue
            unit_rate = fps if kind == 'video' else Fraction(sr)
            a = Fraction(c['dst_in'] + ev['src_in']-c['src_in'],1) / unit_rate
            b = Fraction(c['dst_in'] + ev['src_out']-c['src_in'],1) / unit_rate
            placements[eid].append((a,b,c['id']))
            if kind == 'audio' and ev.get('line_id'):
                if not ident(ev['line_id']) or ev['line_id'] not in c['line_ids'] or c['role'] not in SPEECH:
                    e.append(eid + ': line assignment/role mismatch')
                else:
                    expected_lines[(c['id'],ev['line_id'])] += 1
        n = len(placements[eid])
        if ev['required'] and n == 0:
            e.append(eid + ': required event missing')
        if n > 1 and not ev['allow_repeat']:
            e.append(eid + ': unapproved repeated event')
    for c in aud:
        for line in c['line_ids']:
            if expected_lines[(c['id'],line)] != 1:
                e.append(c['id'] + ': line must map to exactly one complete audio event: ' + line)
    orders = t.get('event_orders')
    if not isinstance(orders,list):
        e.append('event_orders array required'); orders=[]
    for order in orders:
        if not isinstance(order,dict) or set(order) != {'before','after'}:
            e.append('event order must have before/after'); continue
        a,b = placements.get(order['before'],[]),placements.get(order['after'],[])
        if len(a)!=1 or len(b)!=1:
            e.append('event order lacks unique visible/audible events')
        elif a[0][1] > b[0][0]:
            e.append('event order violated: '+order['before']+' -> '+order['after'])
    allowed = t.get('allowed_dialogue_overlaps')
    overlap_pairs = set()
    if not isinstance(allowed,list):
        e.append('allowed_dialogue_overlaps array required'); allowed=[]
    for o in allowed:
        if (not isinstance(o,dict) or set(o)!={'clips','reason'}
                or not isinstance(o['clips'],list) or len(o['clips'])!=2
                or not all(isinstance(x,str) and x in clips and clips[x][0]=='audio' for x in o['clips'])
                or len(set(o['clips']))!=2 or not nonempty(o['reason'])):
            e.append('invalid approved speech overlap'); continue
        overlap_pairs.add(frozenset(o['clips']))
    speech = [c for c in aud if c['role'] in SPEECH]
    for i,a in enumerate(speech):
        for b in speech[i+1:]:
            if max(a['dst_in'],b['dst_in']) < min(a['dst_in']+a['src_out']-a['src_in'], b['dst_in']+b['src_out']-b['src_in']):
                if frozenset((a['id'],b['id'])) not in overlap_pairs:
                    e.append('unapproved overlapping speech: '+a['id']+'/'+b['id'])
    linked = set()
    links = t.get('sync_links')
    if not isinstance(links,list):
        e.append('sync_links array required'); links=[]
    for link in links:
        keys={'video_clip','audio_clip','source_frame','source_sample','tolerance_samples'}
        if not isinstance(link,dict) or set(link)!=keys:
            e.append('invalid sync link fields');continue
        vp,ap=clips.get(link['video_clip']),clips.get(link['audio_clip'])
        if not vp or vp[0]!='video' or not ap or ap[0]!='audio':
            e.append('sync link clip mismatch');continue
        v,a=vp[1],ap[1]
        if (any(not integer(link[k]) for k in ('source_frame','source_sample','tolerance_samples'))
                or not v['src_in'] <= link['source_frame'] < v['src_out']
                or not a['src_in'] <= link['source_sample'] < a['src_out']
                or a['role'] not in SPEECH):
            e.append('sync anchor outside clip/invalid role');continue
        vpos=sample_at(v['dst_in']+link['source_frame']-v['src_in'],fps,sr)
        apos=a['dst_in']+link['source_sample']-a['src_in']
        if abs(vpos-apos)>link['tolerance_samples']:
            e.append('visible AV sync mismatch: '+v['id'])
        linked.add(v['id'])
    for v in vid:
        if v['visible_dialogue'] and v['id'] not in linked:
            e.append(v['id']+': visible dialogue lacks sync anchor')
    if not e and 'presentation' in t:
        try:
            from presentation_checks import resolve
            e.extend(resolve(t)['errors'])
        except (ImportError, ValueError, TypeError, KeyError) as exc:
            e.append('presentation checks unavailable: ' + str(exc))
    try:
        fingerprint = digest(t)
    except (ValueError, TypeError) as exc:
        fingerprint = None
        e.append('timeline cannot be fingerprinted: ' + str(exc))
    return {'status':'BLOCKED' if e else 'STRUCTURE_OK','errors':e,'executed':False,
            'timeline_sha256':fingerprint, 'duration_frames':total,'duration_samples':total_samples,
            'cut_ids':[vid[i-1]['id']+'__'+vid[i]['id'] for i in range(1,len(vid))],
            'required_event_ids':[v['event_id'] for v in events if isinstance(v,dict) and v.get('required')],
            'semantic_quality_verified':False}


def run(argv: list[str], timeout: float) -> str:
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError('positive finite subprocess timeout required')
    p=subprocess.run(argv, shell=False, capture_output=True, text=True, timeout=timeout)
    if p.returncode:
        raise ValueError('command failed: '+str(argv[0])+'\n'+p.stderr[-4000:])
    return p.stdout


def probe(path: Path, timeout: float=120) -> dict:
    ffprobe=shutil.which('ffprobe')
    if not ffprobe:
        raise ValueError('ffprobe unavailable; no automatic install')
    return json.loads(run([ffprobe,'-v','error','-protocol_whitelist','file,pipe',
                           '-count_frames','-show_streams','-show_format','-of','json',str(path)],timeout))


def _color(stream: dict) -> dict:
    return {key:stream.get(raw,'unspecified') for key,raw in
            [('space','color_space'),('primaries','color_primaries'),('transfer','color_transfer'),('range','color_range')]}


def verify_sources(t: dict, root: Path, timeout: float=120) -> dict:
    result=validate(t)
    if result['status']!='STRUCTURE_OK':
        return result
    errors=[]
    if t['status']!='LOCKED':
        errors.append('production timeline is not LOCKED')
    used={c['source_id'] for c in t['video']+t['audio']}
    for s in t['sources']:
        if s['id'] not in used:
            continue
        try:
            path=record_path(root,s)
            allowed={'.mp4','.mkv','.mov','.webm'} if s['kind']=='video' else {'.wav'}
            if path.suffix.lower() not in allowed:
                raise ValueError('unsupported media container')
            rp=record_path(root,s.get('review'))
            review=json.loads(rp.read_text(encoding='utf-8'))
            if (review.get('schema_version')!='edit-source-review-1' or review.get('status')!='PASS'
                    or review.get('source_sha256')!=s['sha256'] or review.get('kind')!=s['kind']):
                raise ValueError('source review missing, stale or failed')
            if not nonempty(review.get('reviewer')) or not review.get('evidence'):
                raise ValueError('real reviewer/evidence records required')
            for ev in review['evidence']:
                record_path(root,ev)
            arr=t['video'] if s['kind']=='video' else t['audio']
            for c in arr:
                if c['source_id']==s['id'] and not ranges_cover(review.get('accepted_ranges'),c['src_in'],c['src_out']):
                    raise ValueError('adopted range outside reviewed coverage: '+c['id'])
            data=probe(path,timeout)
            streams=[x for x in data.get('streams',[]) if x.get('codec_type')==s['kind']]
            if len(streams)!=1:
                raise ValueError('exactly one relevant media stream required')
            stream=streams[0]
            if s['kind']=='video':
                actual={k:stream.get(k) for k in ('width','height')}
                actual['pixel_format']=stream.get('pix_fmt')
                if any(actual[k]!=s[k] for k in actual) or _color(stream)!=s['color']:
                    raise ValueError('actual dimensions/pixel format/color mismatch')
                if stream.get('sample_aspect_ratio') not in {'1:1','N/A',None}:
                    raise ValueError('non-square pixels require explicit conform')
                if stream.get('field_order') not in {'progressive','unknown',None}:
                    raise ValueError('interlaced source requires explicit conform')
                if any(x.get('rotation',0)!=0 for x in stream.get('side_data_list',[])) or str(stream.get('tags',{}).get('rotate','0')) not in {'0','0.0'}:
                    raise ValueError('rotated source requires explicit orientation conform')
                if int(stream.get('nb_read_frames','0'))!=s['units'] or Fraction(stream.get('avg_frame_rate','0'))!=rate(s['fps']):
                    raise ValueError('actual frame count/rate mismatch')
                frames=json.loads(run([shutil.which('ffprobe'),'-v','error','-protocol_whitelist','file,pipe',
                    '-select_streams','v:0','-show_frames','-show_entries','frame=best_effort_timestamp',
                    '-of','json',str(path)],timeout))['frames']
                pts=[int(x['best_effort_timestamp']) for x in frames]
                tb=Fraction(stream['time_base']); fps=rate(s['fps'])
                if len(pts)!=s['units'] or any(pts[i]<=pts[i-1] for i in range(1,len(pts))):
                    raise ValueError('missing/non-monotonic decoded video timestamps')
                # Container quantization up to 1.1 ticks; this is not a semantic AV tolerance.
                if any(abs((p-pts[0])*tb-Fraction(i,1)/fps)>tb*Fraction(11,10) for i,p in enumerate(pts)):
                    raise ValueError('VFR/irregular PTS unsupported: conform with explicit source mapping')
            else:
                if (not stream.get('codec_name','').startswith('pcm_')
                        or int(stream.get('sample_rate',0))!=s['sample_rate'] or stream.get('channels')!=s['channels']):
                    raise ValueError('explicit same-rate/channel PCM WAV required')
                samples=Fraction(stream['duration_ts'])*Fraction(stream['time_base'])*s['sample_rate']
                if samples!=s['units']:
                    raise ValueError('actual audio sample count mismatch')
        except (OSError,ValueError,TypeError,KeyError,ZeroDivisionError,subprocess.TimeoutExpired) as ex:
            errors.append(s['id']+': '+str(ex))
    result.update(status='BLOCKED' if errors else 'INPUTS_VERIFIED',errors=result['errors']+errors)
    return result


def build_command(t: dict, root: Path, out: Path) -> list[str]:
    """Call only after verification. Uses numeric filter args and argv, never shell."""
    r=validate(t)
    if r['status']!='STRUCTURE_OK':
        raise ValueError('; '.join(r['errors']))
    ffmpeg=shutil.which('ffmpeg')
    if not ffmpeg:
        raise ValueError('ffmpeg unavailable; no automatic install')
    src={s['id']:s for s in t['sources']}
    args=[ffmpeg,'-hide_banner','-loglevel','error','-nostdin','-n','-filter_complex_threads','1']
    graph=[]
    for i,c in enumerate(t['video']):
        path=safe_path(root,src[c['source_id']]['path'])
        args += ['-protocol_whitelist','file,pipe','-noautorotate','-i',str(path)]
        graph.append(f'[{i}:v:0]trim=start_frame={c["src_in"]}:end_frame={c["src_out"]},setpts=PTS-STARTPTS[v{i}]')
    n=len(t['video']);fps=rate(t['fps'])
    inputs=''.join(f'[v{i}]' for i in range(n))
    graph.append(inputs+f'concat=n={n}:v=1:a=0,settb=expr=1/{fps.numerator},setpts=N*{fps.denominator}[vout]')
    sr=t['sample_rate'];layout='mono' if t['channels']==1 else 'stereo'
    total=r['duration_samples']
    for j,c in enumerate(t['audio']):
        i=n+j;path=safe_path(root,src[c['source_id']]['path'])
        args += ['-protocol_whitelist','file,pipe','-i',str(path)]
        duration=c['src_out']-c['src_in']
        f=f'[{i}:a:0]atrim=start_sample={c["src_in"]}:end_sample={c["src_out"]},asetpts=N/SR/TB'
        f+=f',aformat=sample_fmts=fltp:sample_rates={sr}:channel_layouts={layout},volume={c["gain_db"]}dB'
        if c['fade_in_samples']:
            f+=f',afade=t=in:ss=0:ns={c["fade_in_samples"]}'
        if c['fade_out_samples']:
            f+=f',afade=t=out:ss={duration-c["fade_out_samples"]}:ns={c["fade_out_samples"]}'
        f+=f',adelay=delays={c["dst_in"]}S:all=1[a{j}]'
        graph.append(f)
    graph.append(f'anullsrc=r={sr}:cl={layout},atrim=end_sample={total},asetpts=N/SR/TB[asilence]')
    labels='[asilence]'+''.join(f'[a{j}]' for j in range(len(t['audio'])))
    graph.append(labels+f'amix=inputs={len(t["audio"])+1}:duration=longest:normalize=0,atrim=end_sample={total},asetpts=N/SR/TB[aout]')
    args+=['-filter_complex',';'.join(graph),'-map','[vout]','-map','[aout]',
           '-c:v','ffv1','-level','3','-pix_fmt',t['pixel_format'],'-fps_mode','passthrough',
           '-c:a','pcm_s24le','-ar',str(sr),'-ac',str(t['channels']),'-map_metadata','-1']
    for key,flag in [('space','-colorspace'),('primaries','-color_primaries'),('transfer','-color_trc'),('range','-color_range')]:
        if t['color'][key]!='unspecified':
            args+=[flag,t['color'][key]]
    return args+['-f','matroska',str(out)]


def write_new_json(path: Path, obj: Any) -> None:
    with path.open('x',encoding='utf-8') as f:
        json.dump(obj,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n')


def render(t: dict, root: Path, relative_out: str, relative_report: str, timeout: float=180) -> dict:
    root=root.resolve(strict=True)
    out=safe_path(root,relative_out,False);report_path=safe_path(root,relative_report,False)
    if out==report_path or out.suffix.lower()!='.mkv' or report_path.suffix.lower()!='.json':
        raise ValueError('distinct .mkv master and .json report paths required')
    if out.exists() or report_path.exists():
        raise FileExistsError('output/report already exists; never overwrite')
    state=verify_sources(t,root,timeout)
    if state['status']!='INPUTS_VERIFIED':
        raise ValueError('BLOCKED: '+'; '.join(state['errors']))
    out.parent.mkdir(parents=True,exist_ok=True);report_path.parent.mkdir(parents=True,exist_ok=True)
    # mkdir followed by path validation protects against existing unsafe parent links.
    safe_path(root,relative_out,False);safe_path(root,relative_report,False)
    with tempfile.TemporaryDirectory(prefix='.edit-',dir=out.parent) as td:
        temp=Path(td)/'master.mkv'
        argv=build_command(t,root,temp)
        run(argv,timeout)
        data=probe(temp,timeout)
        v=next(x for x in data['streams'] if x.get('codec_type')=='video')
        a=next(x for x in data['streams'] if x.get('codec_type')=='audio')
        if (int(v.get('nb_read_frames',0))!=t['duration_frames']
                or v.get('width')!=t['width'] or v.get('height')!=t['height']
                or v.get('pix_fmt')!=t['pixel_format'] or _color(v)!=t['color']
                or v.get('codec_name')!='ffv1' or a.get('codec_name')!='pcm_s24le'
                or int(a.get('sample_rate',0))!=t['sample_rate'] or a.get('channels')!=t['channels']):
            raise ValueError('rendered media does not match locked working-master spec')
        # Decode the actual audio to verify exact sample count without trusting mux duration.
        pcm=Path(td)/'audio.pcm'
        run([shutil.which('ffmpeg'),'-v','error','-nostdin','-n','-i',str(temp),'-map','0:a:0',
             '-c:a','pcm_s24le','-f','s24le',str(pcm)],timeout)
        actual_samples=pcm.stat().st_size//(3*t['channels'])
        if actual_samples!=state['duration_samples']:
            raise ValueError('rendered audio sample count mismatch')
        for s in t['sources']:
            if s['id'] in {c['source_id'] for c in t['video']+t['audio']}:
                record_path(root,s)  # Source changed during render => do not publish new output.
        sha=file_sha(temp)
        result={'status':'RENDERED_NOT_ACCEPTED','executed':True,'tool_version':VERSION,
                'ffmpeg_version':run([shutil.which('ffmpeg'),'-version'],timeout).splitlines()[0],
                'timeline_sha256':digest(t),'artifact':{'path':relative_out,'sha256':sha},
                'duration_frames':t['duration_frames'],'duration_samples':actual_samples,
                'cut_ids':state['cut_ids'],'required_event_ids':state['required_event_ids'],
                'source_hashes':{s['id']:s.get('sha256') for s in t['sources']},
                'semantic_review':'NOT_RUN','final_mix_review':'NOT_RUN','final_delivery_gate':'NOT_RUN',
                'presentation_applied':False,
                'pending_presentation':bool(t.get('presentation',{}).get('cues')),
                'presentation_note':'Working master only: approved compositor must apply resolved UI/subtitle cues and produce a new reviewed final artifact.',
                'publication_authorized':False,'audio_mix_note':'No automatic limiting/loudness normalization; check actual mix.',
                'scope':'Cut-only working master; no generation, ASR, caption render, upscale or aesthetic judgment.'}
        # Hard link is no-clobber even if another process creates the target first.
        os.link(temp,out)
        try:
            write_new_json(report_path,result)
        except Exception:
            # Leave the complete master for reconciliation; never delete a user's output.
            raise RuntimeError('Master rendered; report commit failed. Reconcile existing master, do not overwrite: '+relative_out)
    return result


def main() -> int:
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest='command',required=True)
    for cmd in ('check','render'):
        q=sub.add_parser(cmd)
        q.add_argument('--timeline',type=Path,required=True)
        q.add_argument('--root',type=Path,required=(cmd=='render'))
        q.add_argument('--timeout',type=float,default=180)
        if cmd=='check': q.add_argument('--production',action='store_true')
        else:
            q.add_argument('--out',required=True);q.add_argument('--report',required=True)
    args=p.parse_args()
    try:
        t=json.loads(args.timeline.read_text(encoding='utf-8'))
        if args.command=='render':
            result=render(t,args.root,args.out,args.report,args.timeout)
        elif args.production:
            if args.root is None: raise ValueError('--production requires --root')
            result=verify_sources(t,args.root.resolve(strict=True),args.timeout)
        else:
            result=validate(t)
    except (OSError,ValueError,TypeError,KeyError,RuntimeError,subprocess.TimeoutExpired) as ex:
        result={'status':'BLOCKED','error':str(ex),'executed':False}
    print(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False))
    return 2 if result['status']=='BLOCKED' else 0

if __name__=='__main__':
    raise SystemExit(main())
