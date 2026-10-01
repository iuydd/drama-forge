#!/usr/bin/env python3
"""Resolve existing edit events into UI/subtitle placements and check declared constraints.

No ASR, OCR, face detection, semantic inference, playback or rendering is performed.
Input is the existing edit-timeline-1 object with optional presentation annotations.
All output coordinates are frames of that same timeline, never a separate story clock.
"""
from __future__ import annotations
import argparse
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
from typing import Any


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def nat(value: Any) -> bool:
    return type(value) is int and value >= 0


def text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def names(value: Any) -> bool:
    return (isinstance(value, list) and all(text(x) for x in value)
        and len(set(value)) == len(value))


def ceil(value: Fraction) -> int:
    return -(-value.numerator // value.denominator)


def rect(value: Any) -> bool:
    return (isinstance(value, list) and len(value) == 4
        and all(type(x) in (int, float) and math.isfinite(x) for x in value)
        and 0 <= value[0] < 1 and 0 <= value[1] < 1
        and value[2] > 0 and value[3] > 0
        and value[0] + value[2] <= 1 and value[1] + value[3] <= 1)


def intersects(a: list, b: list) -> bool:
    return (max(a[0], b[0]) < min(a[0]+a[2], b[0]+b[2])
        and max(a[1], b[1]) < min(a[1]+a[3], b[1]+b[3]))


def placements(t: dict) -> tuple[dict, dict]:
    """Unique adopted event ranges in timeline-frame units, with rational audio boundaries."""
    fps = Fraction(t['fps'])
    if fps <= 0 or type(t['sample_rate']) is not int or t['sample_rate'] <= 0:
        raise ValueError('invalid timeline rate')
    result, events = {}, {}
    for ev in t['events']:
        eid = ev['event_id']
        if eid in events:
            raise ValueError('duplicate event_id')
        events[eid] = ev
        arr = t['video'] if ev['kind'] == 'video' else t['audio']
        unit = Fraction(1) if ev['kind'] == 'video' else fps / t['sample_rate']
        found = []
        for c in arr:
            if c['source_id'] == ev['source_id'] and c['src_in'] <= ev['src_in'] < ev['src_out'] <= c['src_out']:
                found.append((unit * (c['dst_in'] + ev['src_in'] - c['src_in']),
                    unit * (c['dst_in'] + ev['src_out'] - c['src_in'])))
        # A repeated event must have a distinct occurrence ID before it can be an anchor.
        if len(found) == 1:
            result[eid] = found[0]
    return result, events


def resolve(t: dict) -> dict:
    """Returns structural findings only. DRAFT is never a production lock."""
    out = {'status': 'BLOCKED', 'errors': [], 'cues': [], 'orders': [],
           'protected_regions': [], 'executed': False, 'semantics_verified': False}
    e = out['errors']
    try:
        if not isinstance(t, dict):
            raise ValueError('timeline object required')
        p = t.get('presentation')
        if not isinstance(p, dict) or p.get('schema_version') != 'presentation-1':
            raise ValueError('presentation-1 object required')
        if set(p) - {'schema_version','status','policy','cues','orders','protected_regions','note'}:
            e.append('unsupported presentation fields')
        if p.get('status') not in {'DRAFT', 'LOCKED'}:
            e.append('presentation status required')
        policy = p.get('policy')
        if (not isinstance(policy, dict)
            or set(policy) != {'max_subtitle_lead_frames','max_subtitle_tail_frames'}
            or not all(nat(v) for v in policy.values())):
            raise ValueError('explicit nonnegative subtitle tolerances required')
        n = t['duration_frames']
        if not nat(n) or not n:
            raise ValueError('actual positive timeline duration required')
        pts, evs = placements(t)
        by_cue = {}

        def anchor(value: Any) -> Fraction:
            if (not isinstance(value, dict) or set(value) != {'event_id','edge','offset_frames'}
                or value['event_id'] not in pts or value['edge'] not in {'start','end'}
                or type(value['offset_frames']) is not int):
                raise ValueError('anchor must reference one adopted event and signed frame offset')
            return pts[value['event_id']][0 if value['edge'] == 'start' else 1] + value['offset_frames']

        cues = p.get('cues')
        if not isinstance(cues, list):
            raise ValueError('cues array required')
        for c in cues:
            if not isinstance(c, dict) or not text(c.get('id')):
                e.append('invalid cue'); continue
            cid = c['id']
            if cid in by_cue:
                e.append('duplicate cue: '+cid); continue
            if not rect(c.get('rect')) or not text(c.get('text')):
                e.append(cid+': normalized final-canvas rect and exact text required'); continue
            kind = c.get('kind')
            if kind == 'subtitle':
                keys = {'id','kind','event_id','text','lead_frames','tail_frames','rect'}
                ev = evs.get(c.get('event_id'))
                if (set(c) - keys or not ev or ev['kind'] != 'audio'
                    or not text(ev.get('line_id')) or c['event_id'] not in pts):
                    e.append(cid+': subtitle needs one complete adopted audio line event'); continue
                lead, tail = c.get('lead_frames'), c.get('tail_frames')
                if not nat(lead) or not nat(tail):
                    e.append(cid+': nonnegative lead/tail required'); continue
                if lead > policy['max_subtitle_lead_frames'] or tail > policy['max_subtitle_tail_frames']:
                    e.append(cid+': subtitle lead/tail exceeds frozen policy')
                a, b = pts[c['event_id']]
                start, end = ceil(a)-lead, ceil(b)+tail
                row = {'id':cid,'kind':kind,'start':start,'end':end,'readable':start,
                       'event_id':c['event_id'],'line_id':ev['line_id'],'visible_to':[],
                       'visibility':'viewer_only','text':c['text'],'rect':c['rect']}
            elif kind == 'ui':
                keys = {'id','kind','text','start','duration_frames','readable_after_frames',
                        'phase','visibility','visible_to','unit','state_event_id','rect'}
                if set(c) - keys:
                    e.append(cid+': unsupported UI fields')
                if c.get('phase') not in {'quote','confirmation','processing','result','notice','status'}:
                    e.append(cid+': explicit UI state phase required')
                vis = c.get('visibility')
                if vis not in {'private','public','device','viewer_only'} or not names(c.get('visible_to')):
                    e.append(cid+': explicit visibility and recipients required'); continue
                if vis == 'viewer_only' and c['visible_to']:
                    e.append(cid+': viewer-only overlay cannot inform characters')
                if not text(c.get('unit')):
                    e.append(cid+': explicit unit or none required')
                dur, ready = c.get('duration_frames'), c.get('readable_after_frames')
                if not nat(dur) or not dur or not nat(ready) or ready >= dur:
                    e.append(cid+': invalid readable window/duration'); continue
                start = ceil(anchor(c.get('start')))
                end = start+dur
                if c.get('phase') == 'result':
                    eff = c.get('state_event_id')
                    if eff not in pts or evs[eff].get('story_phase') != 'effective':
                        e.append(cid+': result requires an adopted effective-state event')
                    elif Fraction(start) < pts[eff][1]:
                        e.append(cid+': result displayed before effect completed')
                row = {'id':cid,'kind':kind,'start':start,'end':end,'readable':start+ready,
                       'visibility':vis,'visible_to':c['visible_to'],'text':c['text'],'rect':c['rect']}
            else:
                e.append(cid+': unknown cue kind'); continue
            if not 0 <= row['start'] < row['end'] <= n:
                e.append(cid+': cue outside actual adopted timeline')
            by_cue[cid] = row
            out['cues'].append(row)

        def point(value: Any) -> tuple[Fraction, list, str]:
            if (not isinstance(value, dict) or set(value) != {'ref','point'}
                or not isinstance(value['ref'], str)):
                raise ValueError('order endpoint required')
            typ, sep, sid = value['ref'].partition(':')
            pos = value['point']
            if typ == 'event' and sep and sid in pts and pos in {'start','end'}:
                receivers = evs[sid].get('perceivers', [])
                if not names(receivers):
                    raise ValueError('invalid event perceivers')
                return pts[sid][0 if pos=='start' else 1], receivers, 'event'
            if typ == 'cue' and sep and sid in by_cue and pos in {'start','readable','end'}:
                c = by_cue[sid]
                return Fraction(c[pos]), c['visible_to'], c['kind']
            raise ValueError('missing/ambiguous event or cue endpoint')

        orders = p.get('orders')
        if not isinstance(orders, list):
            raise ValueError('orders array required')
        seen = set()
        for order in orders:
            if (not isinstance(order, dict)
                or set(order) != {'id','before','after','min_gap_frames','perceivers'}
                or not text(order.get('id')) or order['id'] in seen
                or not nat(order.get('min_gap_frames')) or not names(order.get('perceivers'))):
                e.append('invalid/duplicate order'); continue
            oid = order['id']; seen.add(oid)
            a, receivers, kind = point(order['before'])
            b, _, _ = point(order['after'])
            if a + order['min_gap_frames'] > b:
                e.append(oid+': information/action dependency violated')
            if not set(order['perceivers']).issubset(receivers):
                e.append(oid+': reaction has no declared perception channel')
            if kind == 'subtitle' and order['perceivers']:
                e.append(oid+': subtitles are not a character knowledge source')
            if (not 0 <= a <= n) or (not 0 <= b <= n):
                e.append(oid+': endpoint outside timeline')
            # Review includes the complete after-event/cue, not just two timestamps.
            starts, ends = [], []
            for endpoint in (order['before'],order['after']):
                typ,_,sid=endpoint['ref'].partition(':')
                starts.append(pts[sid][0] if typ=='event' else Fraction(by_cue[sid]['start']))
                ends.append(pts[sid][1] if typ=='event' else Fraction(by_cue[sid]['end']))
            out['orders'].append({'id':oid,'start':math.floor(min(starts)),
                'end':ceil(max(ends))})

        regions = p.get('protected_regions')
        if not isinstance(regions,list):
            raise ValueError('protected_regions array required')
        seen=set()
        for r in regions:
            if (not isinstance(r,dict) or set(r) != {'id','start','end','rect','purpose'}
                or not text(r.get('id')) or r['id'] in seen or not rect(r.get('rect'))
                or not text(r.get('purpose'))):
                e.append('invalid/duplicate protected region'); continue
            seen.add(r['id']); a=math.floor(anchor(r['start'])); b=ceil(anchor(r['end']))
            if not 0 <= a < b <= n:
                e.append(r['id']+': protected region outside timeline'); continue
            out['protected_regions'].append({'id':r['id'],'start':a,'end':b,'rect':r['rect'],'purpose':r['purpose']})
        for c in out['cues']:
            for r in out['protected_regions']:
                if max(c['start'],r['start']) < min(c['end'],r['end']) and intersects(c['rect'],r['rect']):
                    e.append(c['id']+': overlaps protected region '+r['id'])
        for i,c in enumerate(out['cues']):
            for d in out['cues'][i+1:]:
                if max(c['start'],d['start']) < min(c['end'],d['end']) and intersects(c['rect'],d['rect']):
                    e.append(c['id']+': overlaps text cue '+d['id'])
        out['presentation_sha256']=digest(p)
        out['timeline_digest']=digest(t)
        out['cue_ids']=[x['id'] for x in out['cues']]
        out['order_ids']=[x['id'] for x in out['orders']]
        out['status']='BLOCKED' if e else 'STRUCTURE_OK'
        out['notice']='Known coordinates and supplied observations only; readability and geometry need actual composite review.'
    except (ValueError,TypeError,KeyError,IndexError,ZeroDivisionError,OverflowError) as exc:
        e.append('presentation: '+str(exc))
    return out


def check_review(details: Any, resolved: dict, timeline: dict, subject_sha: str,
                 root: Path, verify_record) -> tuple[list[str], list[str]]:
    """Bind a same-G3 composite review, never infer PASS from resolved coordinates."""
    blockers, failures = [], []
    if not isinstance(details, dict):
        return ['actual presentation_review required in edit_cut_review'], []
    if details.get('subject_sha256') != subject_sha:
        blockers.append('presentation review belongs to another final artifact')
    if details.get('presentation_sha256') != resolved.get('presentation_sha256'):
        blockers.append('stale presentation review')
    if details.get('renderer_consumed_resolved_cues') is not True:
        blockers.append('actual compositor consumption not confirmed')
    records=details.get('render_inputs')
    if not isinstance(records,list) or not records:
        blockers.append('actual render input snapshot records required')
    else:
        for rec in records:
            blockers.extend('render input: '+x for x in verify_record(rec,root))
    if details.get('unresolved_ids') != []:
        blockers.append('unresolved composite issues')
    specs=[('cue_checks',resolved.get('cues',[])),('event_checks',resolved.get('orders',[]))]
    for field,expected in specs:
        checks=details.get(field)
        if not isinstance(checks,list):
            blockers.append(field+' array missing'); continue
        by_id={}
        for c in checks:
            if not isinstance(c,dict) or not text(c.get('id')) or c['id'] in by_id:
                blockers.append(field+': malformed or duplicate observation'); continue
            by_id[c['id']]=c
        if set(by_id)!={x['id'] for x in expected}:
            blockers.append(field+': actual coverage mismatch')
        for item in expected:
            c=by_id.get(item['id'],{})
            if c.get('result')=='FAIL': failures.append('composite failed: '+item['id'])
            elif c.get('result')!='PASS': blockers.append('composite not reviewed: '+item['id'])
            window=c.get('range_frames')
            if (not isinstance(window,list) or len(window)!=2 or not all(nat(x) for x in window)
                or not 0 <= window[0] <= item['start'] < item['end'] <= window[1] <= timeline['duration_frames']):
                blockers.append('incomplete composite context: '+item['id'])
            if not text(c.get('observation')): blockers.append('observation missing: '+item['id'])
            ev=c.get('evidence')
            if not isinstance(ev,list) or not ev: blockers.append('actual composite evidence missing: '+item['id'])
            else:
                for rec in ev:blockers.extend(verify_record(rec,root))
    return blockers,failures


def main() -> int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--timeline',required=True,type=Path)
    a=p.parse_args()
    try:
        t=json.loads(a.timeline.read_text(encoding='utf-8'))
        # Reuse core source-range, event and synchronization validation.
        from edit_timeline import validate
        core=validate(t)
        result=resolve(t) if core['status']=='STRUCTURE_OK' else core
    except (OSError,ValueError,TypeError,KeyError) as exc:
        result={'status':'BLOCKED','errors':[str(exc)],'executed':False}
    print(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False))
    return 0 if result['status']=='STRUCTURE_OK' else 2


if __name__=='__main__':
    raise SystemExit(main())
