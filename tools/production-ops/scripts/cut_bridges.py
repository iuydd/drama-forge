#!/usr/bin/env python3
"""Bind paired-cut review to the actual edit timeline. Standard-library only.

This module DOES NOT view media, determine motion/eyeline/personality, generate
frames, or run a model. It checks explicit coverage, source selections, hashes,
and protected event mappings. Paired observations belong to the existing G3.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from fractions import Fraction
from pathlib import Path
from typing import Any, Callable

from edit_timeline import validate as validate_timeline, digest, rate

RELATIONS = {'continuous', 'simultaneous', 'ellipsis', 'new_scene', 'flashback',
             'intentional_discontinuity'}
CATEGORIES = {'action', 'dialogue', 'reaction', 'eyeline', 'insert', 'return',
              'establish', 'parallel', 'intentional', 'static'}
ASPECTS = {'action', 'space_eyeline', 'information_emotion', 'sound'}


def text(x: Any) -> bool:
    return isinstance(x, str) and bool(x.strip())


def integer(x: Any) -> bool:
    return type(x) is int and x >= 0


def signature(clip: dict, sources: dict, side: str) -> dict:
    """The outgoing edge is src_out-1 because all ranges are half open."""
    return {k: clip[k] for k in ('id', 'source_id', 'src_in', 'src_out', 'dst_in')} | {
        'source_sha256': sources[clip['source_id']]['sha256'],
        'edge_frame': clip['src_out']-1 if side == 'left' else clip['src_in']}


def context_plan(timeline: dict, context_frames: int | None = None) -> list[dict]:
    check = validate_timeline(timeline)
    if check['status'] != 'STRUCTURE_OK':
        raise ValueError('valid edit timeline required: ' + '; '.join(check['errors']))
    if context_frames is None:
        context_frames = max(1, math.ceil(rate(timeline['fps']) * 3 / 4))
    if not integer(context_frames) or context_frames < 1:
        raise ValueError('context_frames must be a positive integer')
    sources = {s['id']: s for s in timeline['sources']}
    clips = timeline['video']
    return [{'cut_id': a['id']+'__'+b['id'], 'cut_frame': b['dst_in'],
             'left': signature(a, sources, 'left'), 'right': signature(b, sources, 'right'),
             'context': [max(0, b['dst_in']-context_frames),
                         min(timeline['duration_frames'], b['dst_in']+context_frames)]}
            for a, b in zip(clips, clips[1:])]


def event_windows(timeline: dict, event_id: str) -> list[list[int]]:
    """Map an actually adopted full source event to timeline frame coverage."""
    event = next(e for e in timeline['events'] if e['event_id'] == event_id)
    windows = []
    for clip in timeline['video' if event['kind'] == 'video' else 'audio']:
        if (clip['source_id'] == event['source_id'] and
                clip['src_in'] <= event['src_in'] < event['src_out'] <= clip['src_out']):
            start = clip['dst_in'] + event['src_in'] - clip['src_in']
            end = clip['dst_in'] + event['src_out'] - clip['src_in']
            if event['kind'] == 'audio':
                scale = rate(timeline['fps']) / timeline['sample_rate']
                start, end = math.floor(start * scale), math.ceil(end * scale)
            windows.append([start, end])
    return windows


def _ids(items: Any, key: str, label: str, errors: list[str]) -> dict:
    if not isinstance(items, list):
        errors.append(label+': array required'); return {}
    out = {}
    for item in items:
        if not isinstance(item, dict) or not text(item.get(key)):
            errors.append(label+': object with '+key+' required'); continue
        if item[key] in out:
            errors.append(label+': duplicate '+item[key])
        out[item[key]] = item
    return out


def validate_bundle(bundle: Any, timeline: dict) -> list[str]:
    errors: list[str] = []
    if not isinstance(bundle, dict):
        return ['bridges: object required']
    try:
        plan = context_plan(timeline)
    except (ValueError, TypeError, KeyError) as exc:
        return ['bridges: invalid timeline: '+str(exc)]
    if bundle.get('schema_version') != 'cut-bridges-1':
        errors.append('bridges: unsupported schema')
    if bundle.get('status') != 'LOCKED':
        errors.append('bridges: scope must be LOCKED, not visual acceptance')
    if bundle.get('episode_id') != timeline['episode_id']:
        errors.append('bridges: episode mismatch')
    if bundle.get('timeline_digest') != digest(timeline):
        errors.append('bridges: stale canonical timeline digest')
    cuts = _ids(bundle.get('cuts'), 'cut_id', 'cuts', errors)
    expected = [p['cut_id'] for p in plan]
    if list(cuts) != expected:
        errors.append('bridges: all actual cuts in edit order required')
    events = {v['event_id']: v for v in timeline['events']}
    for p in plan:
        cid = p['cut_id']; c = cuts.get(cid, {})
        for key in ('cut_frame', 'left', 'right'):
            if c.get(key) != p[key]:
                errors.append(cid+': stale adopted '+key)
        if c.get('relation') not in RELATIONS or c.get('category') not in CATEGORIES:
            errors.append(cid+': explicit relation/category required')
        for key in ('connection', 'left_action_state', 'right_action_state',
                    'attention_emotion_link', 'sound_link'):
            if not text(c.get(key)):
                errors.append(cid+': missing '+key)
        # State prose is a frozen annotation, not a computational motion proof.
        if c.get('relation') in {'ellipsis', 'new_scene', 'flashback', 'intentional_discontinuity'}:
            if not text(c.get('approved_transition_ref')) or not text(c.get('orientation_cue')):
                errors.append(cid+': deliberate discontinuity needs approved intent and orientation')
        window = c.get('context')
        if (not isinstance(window, list) or len(window) != 2
                or any(not integer(x) for x in window)
                or not 0 <= window[0] < p['cut_frame'] < window[1] <= timeline['duration_frames']):
            errors.append(cid+': context must cross the actual cut within the timeline')
        event_ids = c.get('linked_event_ids')
        if (not isinstance(event_ids, list) or any(not text(x) for x in event_ids)
                or len(event_ids) != len(set(event_ids)) or any(x not in events for x in event_ids)):
            errors.append(cid+': valid unique linked_event_ids required')
        elif (isinstance(window, list) and len(window) == 2 and all(integer(x) for x in window)):
            for event_id in event_ids:
                placements = event_windows(timeline, event_id)
                if not any(window[0] <= a < b <= window[1] for a, b in placements):
                    errors.append(cid+': context omits linked event '+event_id)
    cues = _ids(bundle.get('character_cues'), 'cue_id', 'character cues', errors)
    for cue_id, c in cues.items():
        if any(not text(c.get(k)) for k in ('character_id', 'choice', 'observable_behavior')):
            errors.append(cue_id+': character, choice and observable behavior required')
        if type(c.get('protect')) is not bool:
            errors.append(cue_id+': protect must be explicit boolean')
        event_ids = c.get('event_ids')
        if (not isinstance(event_ids, list) or any(not text(x) for x in event_ids)
                or len(event_ids) != len(set(event_ids)) or any(x not in events for x in event_ids)):
            errors.append(cue_id+': valid unique event_ids required'); continue
        if c.get('protect') is True:
            if not event_ids or any(events[x].get('required') is not True for x in event_ids):
                errors.append(cue_id+': protected behavior must map to required timeline events')
    return errors


def check_review(review: Any, bundle: dict, timeline: dict, root: Path,
                 verify_record: Callable) -> tuple[list[str], list[str]]:
    """Validate records, not truth. Actual paired media inspection is external."""
    blockers = validate_bundle(bundle, timeline)
    failures: list[str] = []
    if blockers:
        return blockers, failures
    if not isinstance(review, dict):
        return ['paired review missing inside existing edit_cut_review'], failures
    if review.get('schema_version') != 'cut-bridges-review-1':
        blockers.append('paired review: unsupported schema')
    if review.get('bundle_digest') != digest(bundle):
        blockers.append('paired review: stale bundle digest')
    if not text(review.get('reviewer_id')):
        blockers.append('paired review: actual reviewer_id required')
    rows = _ids(review.get('cuts'), 'cut_id', 'paired review', blockers)
    if list(rows) != [c['cut_id'] for c in bundle['cuts']]:
        blockers.append('paired review: missing or unordered cuts')
    for c in bundle['cuts']:
        cid = c['cut_id']; row = rows.get(cid, {})
        if row.get('binding_digest') != digest(c):
            blockers.append(cid+': observation bound to wrong adopted pair')
        if row.get('paired_context_viewed') is not True:
            blockers.append(cid+': two isolated stills are not paired context review')
        observed = row.get('viewed_context')
        if (not isinstance(observed, list) or len(observed) != 2
                or any(not integer(x) for x in observed)
                or not 0 <= observed[0] <= c['context'][0] < c['context'][1] <= observed[1] <= timeline['duration_frames']):
            blockers.append(cid+': actual context coverage incomplete')
        checks = row.get('checks')
        if not isinstance(checks, dict) or set(checks) != ASPECTS:
            blockers.append(cid+': combined G3 aspects missing'); checks = {}
        for key, item in checks.items():
            if not isinstance(item, dict) or not text(item.get('observation')):
                blockers.append(cid+': observed facts required for '+key); continue
            if item.get('result') == 'FAIL':
                failures.append(cid+': '+key+' failed')
            elif item.get('result') not in {'PASS', 'NOT_APPLICABLE'}:
                blockers.append(cid+': '+key+' remains unknown')
            elif item.get('result') == 'NOT_APPLICABLE' and not text(item.get('reason')):
                blockers.append(cid+': '+key+' needs applicability reason')
        evidence = row.get('evidence')
        if not isinstance(evidence, list) or not evidence:
            blockers.append(cid+': actual media inspection evidence required')
        else:
            for r in evidence:
                blockers.extend(verify_record(r, root))
    required_cues = [c['cue_id'] for c in bundle['character_cues'] if c['protect']]
    cues = _ids(review.get('character_cues'), 'cue_id', 'cue review', blockers)
    if set(cues) != set(required_cues):
        blockers.append('paired review: protected cue observations must match scope')
    for cid, c in cues.items():
        if not text(c.get('observation')):
            blockers.append(cid+': actual behavior observation required')
        if c.get('result') == 'FAIL':
            failures.append(cid+': protected behavior missing/contradicted')
        elif c.get('result') != 'PASS':
            blockers.append(cid+': protected behavior not verified')
        evidence = c.get('evidence')
        if not isinstance(evidence, list) or not evidence:
            blockers.append(cid+': protected behavior evidence missing')
        else:
            for record in evidence:
                blockers.extend(verify_record(record, root))
    return list(dict.fromkeys(blockers)), list(dict.fromkeys(failures))


def load_binding(spec: dict, root: Path, verify_record: Callable) -> tuple[dict, list[str]]:
    errors = []
    for key in ('edit_timeline', 'cut_bridges'):
        errors.extend(verify_record(spec.get(key), root))
    if errors:
        return {}, errors
    try:
        t = json.loads((root/spec['edit_timeline']['path']).read_text(encoding='utf-8'))
        b = json.loads((root/spec['cut_bridges']['path']).read_text(encoding='utf-8'))
        if t.get('status') != 'LOCKED':
            errors.append('bridges: final timeline not LOCKED')
        if t.get('episode_id') != spec.get('episode_id'):
            errors.append('bridges: final spec episode mismatch')
        errors.extend(validate_bundle(b, t))
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
        return {}, errors + ['bridges: cannot load actual binding: '+str(exc)]
    return {'bundle': b, 'timeline': t}, errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='mode', required=True)
    for mode in ('plan', 'check'):
        p = sub.add_parser(mode)
        p.add_argument('--timeline', type=Path, required=True)
        if mode == 'check': p.add_argument('--bridges', type=Path, required=True)
    a = parser.parse_args()
    try:
        t = json.loads(a.timeline.read_text(encoding='utf-8'))
        if a.mode == 'plan':
            result = {'status':'PLAN_ONLY', 'executed':False, 'timeline_digest':digest(t),
                      'windows':context_plan(t), 'semantic_quality_verified':False}
        else:
            b = json.loads(a.bridges.read_text(encoding='utf-8'))
            errors = validate_bundle(b, t)
            result = {'status':'BLOCKED' if errors else 'STRUCTURE_OK', 'errors':errors,
                      'executed':False, 'semantic_quality_verified':False}
    except (OSError, ValueError, TypeError, KeyError) as exc:
        result = {'status':'BLOCKED', 'errors':[str(exc)], 'executed':False}
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return 2 if result['status'] == 'BLOCKED' else 0


if __name__ == '__main__':
    raise SystemExit(main())
