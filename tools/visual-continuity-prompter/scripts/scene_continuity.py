#!/usr/bin/env python3
"""Scene-state / visibility contract checks. No geometry, vision, or model calls.

A checked contract is NOT proof of a correct image. States and camera/occlusion
facts must come from approved staging and actual observation. Compatible with
Python 3.10+; stdlib only. All output paths are explicit and never overwritten.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
from typing import Any

SCHEMA = 'ensemble-1'
VISIBLE = {'visible', 'partial', 'reflection_only'}
VISIBILITY = VISIBLE | {'occluded', 'out_of_frame', 'absent', 'unknown'}
KINDS = {'character', 'prop', 'structure', 'group', 'effect'}


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
        separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def finite(value: Any) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


def entity_errors(entities: Any, label: str) -> list[str]:
    if not isinstance(entities, dict) or not entities:
        return [label + ': nonempty tracked entity map required']
    errors = []
    for eid, e in entities.items():
        if not text(eid) or not isinstance(e, dict):
            errors.append(label + ': malformed entity'); continue
        if e.get('kind') not in KINDS or e.get('presence') not in {'present', 'absent'}:
            errors.append(label + ': invalid kind/presence: ' + eid)
        if not text(e.get('design_id')) or not isinstance(e.get('state'), dict):
            errors.append(label + ': design/state missing: ' + eid)
        elif e.get('presence') == 'present' and not text(e['state'].get('world_anchor')):
            errors.append(label + ': present entity lacks world anchor: ' + eid)
        aliases = e.get('aliases', [])
        if not isinstance(aliases, list) or any(not text(a) for a in aliases):
            errors.append(label + ': aliases invalid: ' + eid)
    return errors


def replay(entities: dict, events: Any, timed: bool, duration: float) -> tuple[dict, list[str]]:
    state, errors, seen = copy.deepcopy(entities), [], set()
    last_t = -1.0
    if not isinstance(events, list):
        return state, ['events: array required']
    for event in events:
        if not isinstance(event, dict):
            errors.append('event: object required'); continue
        eid, event_id = event.get('entity_id'), event.get('event_id')
        if not text(event_id) or event_id in seen:
            errors.append('event: missing/duplicate event ID')
        if text(event_id):
            seen.add(event_id)
        if not text(event.get('cause_ref')) or not text(event.get('approval_ref')):
            errors.append('event: actual authored cause and approval reference required')
        if timed:
            t = event.get('at_s')
            if not finite(t) or not 0 < t < duration or t < last_t:
                errors.append('event: time invalid/out of order')
            else:
                last_t = t
        if not text(eid) or eid not in state:
            errors.append('event: entity must exist in prior registry (possibly absent)'); continue
        if event.get('before') != state[eid]:
            errors.append('event: before state mismatch: ' + eid)
        after = event.get('after')
        ee = entity_errors({eid: after}, 'event.after')
        errors += ee
        if not ee:
            state[eid] = copy.deepcopy(after)
    return state, errors


def validate_bundle(bundle: Any) -> list[str]:
    if not isinstance(bundle, dict) or bundle.get('schema_version') != SCHEMA:
        return ['ensemble: invalid schema']
    errors = []
    if bundle.get('status') != 'locked':
        errors.append('ensemble: state/view contract not locked')
    scope = bundle.get('scope', {})
    if not isinstance(scope, dict):
        scope = {}
    for k in ('project_id', 'episode_id', 'scene_id', 'scene_version',
              'continuity_unit_id', 'shot_id', 'view_id'):
        if not text(scope.get(k)):
            errors.append('ensemble scope missing: ' + k)
    d = bundle.get('duration_s')
    if not finite(d) or d <= 0:
        return errors + ['ensemble: positive finite duration required']
    states = {}
    for key in ('previous_state', 'start_state', 'end_state'):
        snap = bundle.get(key)
        if not isinstance(snap, dict) or not text(snap.get('snapshot_id')):
            errors.append('ensemble: snapshot missing: ' + key); states[key] = {}; continue
        states[key] = snap.get('entities', {})
        errors += entity_errors(states[key], key)
    if errors:
        return errors
    previous, start, end = (states[k] for k in ('previous_state', 'start_state', 'end_state'))
    if set(previous) != set(start) or set(start) != set(end):
        errors.append('ensemble: registry IDs cannot be silently added/deleted; keep absent tombstones')
    cut = bundle.get('cut', {})
    if not isinstance(cut, dict) or cut.get('kind') not in {'camera_only', 'continuous', 'ellipsis', 'scene_entry'}:
        errors.append('ensemble: explicit cut kind required'); cut = {}
    elif cut['kind'] == 'camera_only' and (cut.get('events') != [] or previous != start):
        errors.append('ensemble: camera-only cut cannot mutate scene state')
    new_start, ce = replay(previous, cut.get('events'), False, d)
    errors += ce
    if new_start != start:
        errors.append('ensemble: unexplained change across cut')
    events = bundle.get('events')
    new_end, me = replay(start, events, True, d)
    errors += me
    if new_end != end:
        errors.append('ensemble: unexplained change within shot')
    view = bundle.get('view_plan')
    if not isinstance(view, dict):
        return errors + ['ensemble: view plan required']
    if (view.get('status') != 'locked' or not text(view.get('camera_spec_ref'))
            or not text(view.get('basis_ref')) or not text(view.get('inventory_basis_ref'))):
        errors.append('ensemble: actual camera, staging and whole-scene inventory basis required')
    windows = view.get('windows')
    if not isinstance(windows, list) or not windows:
        return errors + ['ensemble: nonempty visibility windows required']
    ids, expected_union, cursor, win_ids = set(start), set(), 0.0, set()
    valid_events = events if not me and isinstance(events, list) else []
    for w in windows:
        if not isinstance(w, dict):
            errors.append('ensemble: malformed window'); continue
        wid, a, b = w.get('window_id'), w.get('start_s'), w.get('end_s')
        if not text(wid) or wid in win_ids:
            errors.append('ensemble: missing/duplicate window ID')
        if text(wid):
            win_ids.add(wid)
        if not finite(a) or not finite(b) or a != cursor or not a < b <= d:
            errors.append('ensemble: visibility windows must cover timeline without gaps'); continue
        cursor = b
        if not text(w.get('basis_ref')):
            errors.append('ensemble: window visibility basis missing')
        at_state, _ = replay(start, [e for e in valid_events if e['at_s'] <= a], True, d)
        for e in valid_events:
            if (a < e['at_s'] < b and e['before']['presence'] != e['after']['presence']):
                errors.append('ensemble: presence event requires a visibility window boundary')
        rows = w.get('entities')
        if not isinstance(rows, list):
            errors.append('ensemble: entity visibility rows required'); continue
        row_ids = [r.get('entity_id') for r in rows if isinstance(r, dict)]
        if (any(not text(x) for x in row_ids) or len(row_ids) != len(rows)
                or len(set(row_ids)) != len(row_ids) or set(row_ids) != ids):
            errors.append('ensemble: every tracked entity needs exactly one row in each window')
        expected = set()
        for row in rows:
            if not isinstance(row, dict):
                continue
            eid, vis = row.get('entity_id'), row.get('visibility')
            if not text(eid) or eid not in ids:
                continue
            if vis not in VISIBILITY or vis == 'unknown':
                errors.append('ensemble: unresolved visibility: ' + eid); continue
            if not text(row.get('reason')):
                errors.append('ensemble: visibility rationale missing: ' + eid)
            if at_state[eid]['presence'] == 'absent' and vis != 'absent':
                errors.append('ensemble: absent entity cannot appear in view: ' + eid)
            if at_state[eid]['presence'] == 'present' and vis == 'absent':
                errors.append('ensemble: off-frame/occluded is not scene absence: ' + eid)
            if vis in VISIBLE:
                expected.add(eid)
                if (not text(row.get('visual_clause')) or not text(row.get('behavior_clause'))
                        or not text(row.get('still_clause'))):
                    errors.append('ensemble: visible entities need visual anchor and behavior: ' + eid)
                if vis in {'partial', 'reflection_only'} and not text(row.get('visible_parts')):
                    errors.append('ensemble: partial/reflected appearance scope missing: ' + eid)
            elif row.get('visual_clause') or row.get('behavior_clause') or row.get('still_clause'):
                errors.append('ensemble: invisible entity cannot emit model-facing clauses: ' + eid)
            if vis == 'occluded':
                occluder = row.get('occluder_id')
                if not text(occluder) or occluder == eid or occluder not in ids:
                    errors.append('ensemble: occluder must be a distinct registered entity: ' + eid)
                elif at_state[occluder]['presence'] != 'present':
                    errors.append('ensemble: absent object cannot occlude: ' + eid)
        stated = w.get('expected_visible_ids')
        if not isinstance(stated, list) or any(not text(x) for x in stated):
            errors.append('ensemble: explicit window visible-ID list required')
        elif len(stated) != len(set(stated)) or set(stated) != expected:
            errors.append('ensemble: visible IDs omit supporting entities or include invisible ones')
        expected_union |= expected
    if cursor != d:
        errors.append('ensemble: end of shot remains uncovered')
    focus = bundle.get('focus_ids')
    if not isinstance(focus, list) or any(not text(x) for x in focus):
        errors.append('ensemble: explicit focus IDs required')
    elif not set(focus).issubset(expected_union):
        errors.append('ensemble: focus must be visibly represented sometime during shot')
    return sorted(set(errors))


def visible_ids(bundle: dict) -> set[str]:
    return {r['entity_id'] for w in bundle['view_plan']['windows']
            for r in w['entities'] if r['visibility'] in VISIBLE}


def render_entity_clause(row: dict, image: bool = False) -> str:
    """Render one already-validated visible row; reuse for scoped alias checks."""
    clause = row['visual_clause'] + '；'
    clause += (row['still_clause'] if image else
               '本段起始状态：' + row['still_clause'] + '；本段动作：' + row['behavior_clause'])
    if row['visibility'] in {'partial', 'reflection_only'}:
        clause += '；可见范围仅限：' + row['visible_parts']
    return clause


def render_blocks(bundle: dict, image: bool = False) -> list[str]:
    """Keep each window's frozen visible facts attached to its time span."""
    errors = validate_bundle(bundle)
    if errors:
        raise ValueError('; '.join(errors))
    windows = bundle['view_plan']['windows'][:1] if image else bundle['view_plan']['windows']
    entities = bundle['start_state']['entities']
    blocks = []
    for w in windows:
        clauses = []
        for r in w['entities']:
            if r['visibility'] not in VISIBLE:
                continue
            kind = entities[r['entity_id']]['kind']
            label = {'character': '现场人物', 'group': '现场群体', 'prop': '物件与画内内容',
                     'structure': '场景结构', 'effect': '可见效果'}[kind]
            if kind in {'character', 'group'} and r['visibility'] == 'reflection_only':
                label = '人物反射或画内形象'
            clauses.append(label + '：' + render_entity_clause(r, image))
        if clauses:
            prefix = '本张起始画面' if image else f'{w["start_s"]}–{w["end_s"]}秒画内延续'
            blocks.append(prefix + '：' + '。'.join(clauses) + '。\n'
                          '现场表演由上述现场人物与群体承担，物件或屏幕中的平面人物按声明的图像内容呈现；'
                          '保留已声明的局部、反射和正常构图裁切。'
                          '画面内及四边不得出现未声明的额外人物或额外人物的手、胳膊、肩膀等身体部分。')
    return blocks


def render_clauses(bundle: dict, image: bool = False) -> str:
    return '\n'.join(render_blocks(bundle, image))


def validate_shot(shot: dict) -> list[str]:
    if 'ensemble_required' in shot and type(shot['ensemble_required']) is not bool:
        return ['ensemble_required: boolean required']
    bundle = shot.get('ensemble')
    if bundle is None:
        return ['ensemble: required contract missing'] if shot.get('ensemble_required') is True else []
    errors = validate_bundle(bundle)
    if errors:
        return errors
    scope = bundle['scope']
    for key in ('shot_id', 'scene_id', 'scene_version', 'view_id'):
        if scope[key] != shot.get(key):
            errors.append('ensemble: shot binding mismatch: ' + key)
    if shot.get('mode') in {'video_i2v', 'video_reference'} and bundle['duration_s'] != shot.get('video', {}).get('duration_s'):
        errors.append('ensemble: video duration mismatch')
    insert = shot.get('insert_policy')
    if isinstance(insert, dict):
        actual = visible_ids(bundle)
        stated = insert.get('visible_entity_ids', [])
        if not isinstance(stated, list) or any(not text(x) for x in stated) or set(stated) != actual:
            errors.append('ensemble: insert whitelist must come from whole view, not focal subject')
        if insert.get('kind') == 'object_only':
            for w in bundle['view_plan']['windows']:
                for r in w['entities']:
                    if (r['visibility'] in VISIBLE
                            and bundle['start_state']['entities'][r['entity_id']]['kind'] == 'character'):
                        errors.append('ensemble: object-only label conflicts with a visible character/part/reflection')
    return sorted(set(errors))


def check_observation(bundle: dict, observation: Any, first_frame: bool = False) -> list[str]:
    """Check declared per-entity observations, not visual truth or artifact files."""
    errors = validate_bundle(bundle)
    if errors:
        return errors
    if not isinstance(observation, dict) or observation.get('ensemble_sha256') != digest(bundle):
        return ['ensemble observation: stale/missing contract digest']
    needed = bundle['view_plan']['windows'][:1] if first_frame else bundle['view_plan']['windows']
    seen = observation.get('windows')
    if not isinstance(seen, list) or len(seen) != len(needed):
        return ['ensemble observation: coverage missing/extra windows']
    for wanted, actual in zip(needed, seen):
        if not isinstance(actual, dict) or actual.get('window_id') != wanted['window_id']:
            errors.append('ensemble observation: window mismatch'); continue
        results = actual.get('entities')
        if not isinstance(results, dict) or set(results) != set(bundle['start_state']['entities']):
            errors.append('ensemble observation: missing entity checks'); continue
        for eid, result in results.items():
            if (not isinstance(result, dict) or result.get('result') != 'PASS'
                    or not text(result.get('observation'))):
                errors.append('ensemble observation: unresolved entity ' + eid)
        if actual.get('full_frame_result') != 'PASS' or actual.get('unexpected_visible_entities') != []:
            errors.append('ensemble observation: full-frame/unexpected entity issue')
    if not text(observation.get('temporal_basis')) and not first_frame:
        errors.append('ensemble observation: actual temporal coverage description required')
    return errors


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--bundle', type=Path, required=True)
    p.add_argument('--clauses', action='store_true')
    p.add_argument('--image', action='store_true')
    a = p.parse_args()
    try:
        bundle = json.loads(a.bundle.read_text(encoding='utf-8'))
        errors = validate_bundle(bundle)
        result = {'status': 'BLOCKED' if errors else 'CONTRACT_OK', 'errors': errors,
                  'visual_quality_verified': False, 'executed_generation': False}
        if not errors and a.clauses:
            result['context_clauses'] = render_clauses(bundle, a.image)
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        return 2 if errors else 0
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(json.dumps({'status': 'BLOCKED', 'error': str(exc)}, ensure_ascii=False))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
