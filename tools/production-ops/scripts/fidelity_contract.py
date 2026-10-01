#!/usr/bin/env python3
"""Frozen detail coverage and media-bound observations. No semantic inference.

The six risks are assessed BEFORE generation. Observations are supplied by real
viewers/listeners; this module rejects missing, stale and explicitly failed data.
"""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any

CATEGORIES = {'direction', 'gaze', 'action', 'text', 'placement', 'performance'}
STAGES = {'start_frame', 'video', 'final'}
FIELDS = {
 'direction': ('subject_id', 'world_heading', 'screen_heading', 'screen_motion',
               'view_id', 'axis_side', 'transition_basis'),
 'gaze': ('actor_id', 'target_id', 'trigger', 'body', 'head', 'eyes', 'permitted_deviation'),
 'action': ('actor_id', 'effector', 'target_id', 'precondition', 'contact', 'change',
            'postcondition', 'persistence'),
 'text': ('text_id', 'prop_id', 'side', 'exact_text', 'appearance', 'method',
          'reveal_rule', 'legibility_window'),
 'placement': ('prop_id', 'surface_id', 'local_anchor', 'reference_landmarks',
               'size', 'rotation', 'persistence'),
 'performance': ('speaker_id', 'line_ids', 'trigger', 'before', 'after',
                 'listener_id', 'visible_response')}


def text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def derived_assertions(req: dict, stage: str, point: str) -> dict:
    """Project canonical facts; free-form prose remains a semantic review task.

    expected_at is only for approved phase-specific changes, not after-the-fact
    accommodations. v4.2 requires these values to be observed; legacy packets
    still reject explicitly contradictory values even when equals was omitted.
    """
    expected = dict(req['expected'])
    expected.update(req.get('expected_at', {}).get(stage, {}).get(point, {}))
    stable = {
        'direction': ('subject_id', 'world_heading', 'screen_heading', 'screen_motion', 'view_id', 'axis_side'),
        'gaze': ('actor_id', 'target_id'),
        'action': ('actor_id', 'effector', 'target_id'),
        'text': ('text_id', 'prop_id', 'side'),
        'placement': ('prop_id', 'surface_id', 'local_anchor'),
        'performance': ('speaker_id', 'listener_id'),
    }
    result = {k: expected[k] for k in stable[req['category']] if k in expected}
    if req['category'] == 'action':
        if point == 'change': result['visible_change'] = True
        if point == 'after_release': result['persistent_result'] = True
    if req['category'] == 'performance':
        if point in ('before', 'after'): result['intent'] = expected[point]
        if point == 'contrast': result['audible_change'] = True
    if req['category'] == 'text' and stage == 'final' and point == 'readable_text':
        result['text'] = expected['exact_text']
    return result


def validate(contract: Any, production: bool = True) -> list[str]:
    errors = []
    if not isinstance(contract, dict):
        return ['fidelity: contract object missing']
    if contract.get('schema_version') != 'shot-fidelity-1':
        errors.append('fidelity: unsupported schema')
    for field in ('episode_id', 'shot_id', 'scene_id', 'view_id', 'revision'):
        if not text(contract.get(field)):
            errors.append('fidelity: missing ' + field)
    if production and (contract.get('status') != 'LOCKED' or contract.get('example_only') is not False):
        errors.append('fidelity: unlocked/example/unclassified contract')
    risks = contract.get('risks')
    if not isinstance(risks, dict) or set(risks) != CATEGORIES:
        return errors + ['fidelity: all six applicability decisions required']
    for category, item in risks.items():
        if (not isinstance(item, dict) or type(item.get('applicable')) is not bool
                or not text(item.get('basis'))):
            errors.append('fidelity: applicability/basis missing for ' + category)
    requirements = contract.get('requirements')
    if not isinstance(requirements, list) or any(not isinstance(r, dict) for r in requirements):
        return errors + ['fidelity: requirements array required']
    ids = [r.get('id') for r in requirements]
    if any(not text(i) for i in ids) or len(ids) != len(set(ids)):
        return errors + ['fidelity: invalid/duplicate requirement IDs']
    found = set()
    for req in requirements:
        category = req.get('category')
        if category not in CATEGORIES:
            errors.append('fidelity: invalid category'); continue
        found.add(category)
        expected, points = req.get('expected'), req.get('points')
        if not isinstance(expected, dict):
            errors.append('fidelity: expected values missing: ' + req['id']); continue
        for key in FIELDS[category]:
            value = expected.get(key)
            if not (text(value) or isinstance(value, (list, dict)) and bool(value)):
                errors.append('fidelity: missing ' + req['id'] + '.' + key)
        if not isinstance(points, dict) or not points or set(points) - STAGES:
            errors.append('fidelity: invalid stage points: ' + req['id']); continue
        required_stages = {'video', 'final'} if category == 'performance' else STAGES
        if not required_stages.issubset(points):
            errors.append('fidelity: lifecycle coverage missing: ' + req['id'])
        for stage, names in points.items():
            if (not isinstance(names, list) or not names or any(not text(n) for n in names)
                    or len(names) != len(set(names))):
                errors.append('fidelity: invalid/duplicate evidence points: ' + req['id'])
        if category == 'direction' and expected.get('view_id') != contract.get('view_id'):
            errors.append('fidelity: direction expectation uses another camera view')
        video = points.get('video', [])
        final = points.get('final', [])
        if category == 'action':
            if type(expected.get('release_required')) is not bool:
                errors.append('fidelity: explicit release applicability required')
            mandatory = {'precondition', 'contact', 'change', 'result'}
            if expected.get('release_required') is True:
                mandatory.add('after_release')
            if not isinstance(video, list) or not mandatory.issubset(video):
                errors.append('fidelity: contact/change/result/release coverage missing')
        if category == 'performance' and (not isinstance(video, list) or
                    not {'before', 'trigger', 'after', 'contrast'}.issubset(video)):
            errors.append('fidelity: before/trigger/after/contrast coverage missing')
        if category == 'text' and (not isinstance(final, list) or 'readable_text' not in final):
            errors.append('fidelity: final exact text evidence required')
        overrides = req.get('expected_at', {})
        if not isinstance(overrides, dict):
            errors.append('fidelity: invalid phase expectations'); overrides = {}
        for stage_name, phase_values in overrides.items():
            if stage_name not in points or not isinstance(phase_values, dict):
                errors.append('fidelity: invalid phase expectation stage'); continue
            for phase_name, vals in phase_values.items():
                if phase_name not in points[stage_name] or not isinstance(vals, dict):
                    errors.append('fidelity: invalid phase expectation point')
        equals = req.get('equals', {})
        if not isinstance(equals, dict):
            errors.append('fidelity: equals must be an object'); continue
        for stage, items in equals.items():
            if stage not in points or not isinstance(items, dict):
                errors.append('fidelity: equality stage is not covered'); continue
            for point_id, values in items.items():
                if point_id not in points[stage] or not isinstance(values, dict) or not values:
                    errors.append('fidelity: equality point/value is not covered')
                elif not overrides:
                    canonical = derived_assertions(req, stage, point_id)
                    if any(k in canonical and (type(v) is not type(canonical[k]) or v != canonical[k]) for k, v in values.items()):
                        errors.append('fidelity: equality conflicts with authoritative expectation')
    for category, item in risks.items():
        if isinstance(item, dict) and type(item.get('applicable')) is bool:
            if item['applicable'] != (category in found):
                errors.append('fidelity: applicability/requirement mismatch: ' + category)
    return errors


def check_file(record: Any, root: Path, verify, shot: dict | None = None) -> tuple[dict, list[str]]:
    errors = verify(record, root)
    if errors:
        return {}, ['fidelity: ' + e for e in errors]
    # Strict duplicate/nonfinite rejection is shared with the brain packet reader.
    from brain_handoff import read_json
    contract = read_json(root / record['path'])
    errors = validate(contract)
    if isinstance(contract, dict) and shot is not None:
        if shot.get('policy_version')=='4.2.0' and contract.get('policy_version')!='4.2.0':
            errors.append('fidelity: v4.2 shot requires current comparison contract')
        for field in ('shot_id', 'episode_id', 'scene_id', 'view_id'):
            if contract.get(field) != shot.get(field):
                errors.append('fidelity: shot/contract mismatch: ' + field)
    return contract if not errors else {}, errors


def load_bindings(spec: dict, root: Path, verify) -> tuple[dict, list[str]]:
    from brain_handoff import load_task
    errors, context = [], {}
    bindings = spec.get('fidelity_bindings')
    if not isinstance(bindings, list) or not bindings:
        return {}, ['fidelity: actual file bindings missing']
    ids = []
    for binding in bindings:
        if not isinstance(binding, dict):
            errors.append('fidelity: malformed binding'); continue
        sid = binding.get('shot_id'); ids.append(sid)
        contract, ce = check_file(binding.get('contract'), root, verify)
        errors += ce
        if spec.get('policy_version')=='4.2.0' and contract.get('policy_version')!='4.2.0':
            errors.append('fidelity: legacy comparison contract cannot pass a v4.2 gate')
        errors += ['fidelity media: ' + e for e in verify(binding.get('media'), root)]
        if spec.get('action') == 'final_delivery' or len(spec.get('shot_ids', [])) == 1:
            if binding.get('media') != spec.get('subject'):
                errors.append('fidelity: reviewed media differs from gate subject')
        if spec.get('ensemble_required') is True and spec.get('action') in {'pre_video', 'shot_edit'}:
            ensemble = [b for b in spec.get('ensemble_bindings', []) if isinstance(b, dict) and b.get('shot_id') == sid]
            if len(ensemble) != 1 or ensemble[0].get('media') != binding.get('media'):
                errors.append('fidelity: observed media differs from ensemble/start-frame binding')
            elif contract:
                sr = ensemble[0].get('shot_contract')
                se = verify(sr, root)
                errors += ['fidelity scene: ' + e for e in se]
                if not se:
                    from brain_handoff import read_json
                    source_shot = read_json(root / sr['path'])
                    for field in ('shot_id', 'scene_id', 'view_id'):
                        if source_shot.get(field) != contract.get(field):
                            errors.append('fidelity: ensemble/contract scope differs: ' + field)
        task, packet, be = load_task(binding.get('brain_binding'), root, verify)
        errors += be
        if task and (task.get('fidelity_contract') != binding.get('contract') or
                     task['request'].get('shot_id') != sid or
                     packet.get('episode_id') != spec.get('episode_id')):
            errors.append('fidelity: not the brain-frozen shot/contract')
        if contract:
            if contract['shot_id'] != sid or contract['episode_id'] != spec.get('episode_id'):
                errors.append('fidelity: episode/shot scope mismatch')
            if text(sid):
                context[sid] = {'contract': contract, 'record': binding['contract'], 'media': binding.get('media')}
    if ids != spec.get('shot_ids') or len(context) != len(ids):
        errors.append('fidelity: ordered shot coverage mismatch')
    return context, errors


def valid_locator(locator: Any, stage: str) -> bool:
    if not isinstance(locator, dict):
        return False
    if stage == 'start_frame':
        return locator.get('kind') == 'image' and text(locator.get('region'))
    return (locator.get('kind') == 'frames' and
            type(locator.get('start')) is int and type(locator.get('end')) is int and
            0 <= locator['start'] < locator['end'] and locator.get('clock') == 'subject')


def check_review(review: Any, context: dict, stage: str, media_sha: str,
                 root: Path, verify) -> tuple[list[str], list[str]]:
    errors, failures = [], []
    if not isinstance(review, dict) or stage not in STAGES:
        return ['fidelity: actual review/stage missing'], []
    if review.get('stage') != stage or review.get('subject_sha256') != media_sha:
        errors.append('fidelity: wrong stage or stale media review')
    shots = review.get('shots')
    if not isinstance(shots, list) or [s.get('shot_id') for s in shots if isinstance(s, dict)] != list(context):
        return errors + ['fidelity: exact observed shot coverage missing'], []
    for observed in shots:
        item = context[observed['shot_id']]
        shot_media_sha = item['media']['sha256']
        if observed.get('media_sha256') != shot_media_sha:
            errors.append('fidelity: observed shot media mismatch')
        if observed.get('contract_sha256') != item['record']['sha256']:
            errors.append('fidelity: stale observed contract')
        expected = [r for r in item['contract']['requirements'] if stage in r['points']]
        requirements = observed.get('requirements')
        if not isinstance(requirements, list) or [r.get('id') for r in requirements if isinstance(r, dict)] != [r['id'] for r in expected]:
            errors.append('fidelity: required evidence omitted or invented'); continue
        for req, obs in zip(expected, requirements):
            points = obs.get('points')
            if not isinstance(points, list) or [p.get('id') for p in points if isinstance(p, dict)] != req['points'][stage]:
                errors.append('fidelity: missing/duplicate/out-of-order evidence points'); continue
            if req['category'] == 'action' and stage == 'video':
                ordered = ['precondition', 'contact', 'change', 'result']
                if req['expected'].get('release_required') is True:
                    ordered.append('after_release')
                moments = {p['id']: p.get('event_frame') for p in points}
                if any(type(moments.get(name)) is not int for name in ordered):
                    errors.append('fidelity: actual action event frames missing')
                elif any(moments[a] > moments[b] for a, b in zip(ordered, ordered[1:])):
                    failures.append('fidelity: observed action phases are out of order')
            if req['category'] == 'performance' and stage != 'start_frame':
                by_id = {p['id']: p for p in points}
                if {'before', 'trigger', 'after'}.issubset(by_id):
                    strict = item['contract'].get('policy_version') == '4.2.0'
                    frames = []
                    for name in ('before', 'trigger', 'after'):
                        p = by_id[name]; loc = p.get('locator', {})
                        frame = p.get('event_frame', None if strict else loc.get('start'))
                        if (type(frame) is not int or not valid_locator(loc, stage)
                                or not loc['start'] <= frame < loc['end']):
                            errors.append('fidelity: actual performance event frame outside observed range')
                        frames.append(frame)
                    if all(type(v) is int for v in frames) and not frames[0] <= frames[1] <= frames[2]:
                        failures.append('fidelity: performance before/trigger/after out of order')
            for point in points:
                label = observed['shot_id'] + '/' + req['id'] + '/' + point['id']
                if point.get('result') == 'FAIL':
                    failures.append('fidelity: observed failure: ' + label)
                elif point.get('result') != 'PASS':
                    errors.append('fidelity: required observation UNKNOWN: ' + label)
                if not text(point.get('observation')):
                    errors.append('fidelity: actual observation missing: ' + label)
                if not valid_locator(point.get('locator'), stage):
                    errors.append('fidelity: actual image region/frame interval missing: ' + label)
                if point.get('media_sha256') != shot_media_sha:
                    errors.append('fidelity: evidence points to different media: ' + label)
                if req['category'] == 'action' and stage == 'video':
                    loc = point.get('locator', {})
                    frame = point.get('event_frame')
                    if (type(frame) is not int or not valid_locator(loc, stage) or
                            not loc['start'] <= frame < loc['end']):
                        errors.append('fidelity: action event frame outside observed range')
                evidence = point.get('evidence')
                if not isinstance(evidence, list) or not evidence:
                    errors.append('fidelity: evidence files missing: ' + label)
                else:
                    for record in evidence:
                        errors += ['fidelity evidence: ' + e for e in verify(record, root)]
                if req['category'] == 'performance' and stage != 'start_frame':
                    if point.get('modality') not in {'audio_video', 'audio'}:
                        errors.append('fidelity: prosody cannot pass from still frames: ' + label)
                elif point.get('modality') not in {'image', 'video', 'audio_video'}:
                    errors.append('fidelity: visual observation missing: ' + label)
                values = point.get('values', {})
                if not isinstance(values, dict):
                    values = {}; errors.append('fidelity: malformed observed values')
                canonical = derived_assertions(req, stage, point['id'])
                strict = item['contract'].get('policy_version') == '4.2.0'
                assertions = {k: v for k, v in canonical.items() if strict or k in values}
                assertions.update(req.get('equals', {}).get(stage, {}).get(point['id'], {}))
                # A hand-written equals cannot negate the canonical expectation.
                for k, v in canonical.items():
                    if k in values and (type(values[k]) is not type(v) or values[k] != v):
                        failures.append('fidelity: observed value contradicts canonical fact: ' + label + '/' + k)
                if req['category'] == 'text' and stage == 'final' and point['id'] == 'readable_text':
                    assertions = dict(assertions, text=req['expected']['exact_text'])
                for key, value in assertions.items():
                    if key not in values:
                        errors.append('fidelity: required observed value missing: ' + label + '/' + key)
                    elif type(values[key]) is not type(value) or values[key] != value:
                        failures.append('fidelity: observed value contradicts frozen expectation: ' + label + '/' + key)
    return errors, failures
