#!/usr/bin/env python3
"""Episode state inheritance and spatial handoffs. Stdlib; NO vision or generation.

Facts are authored, not inferred geometry. State deltas do not prove an action
occurred. Observations must come from actual media; the host protects approval.
"""
from __future__ import annotations
import argparse
from copy import deepcopy
from pathlib import Path
from typing import Any
from brain_handoff import digest, read_json, text, verify_record
from spatial_math import equal_value

RELATIONS = {'opening', 'camera_only', 'continuous', 'return', 'new_scene',
             'ellipsis', 'flashback', 'resume', 'parallel', 'intentional'}
DISCONTINUOUS = {'new_scene', 'ellipsis', 'flashback', 'resume', 'parallel', 'intentional'}
STAGES = {'start_frame', 'video', 'final'}


def unique_strings(x: Any, nonempty: bool = False) -> bool:
    return (isinstance(x, list) and (bool(x) or not nonempty)
            and all(text(v) for v in x) and len(x) == len(set(x)))


def index(rows: Any, key: str, label: str, errors: list[str]) -> dict:
    if not isinstance(rows, list):
        errors.append(label + ': array required'); return {}
    result = {}
    for row in rows:
        if not isinstance(row, dict) or not text(row.get(key)):
            errors.append(label + ': object/ID required'); continue
        if row[key] in result:
            errors.append(label + ': duplicate ID ' + row[key])
        result[row[key]] = row
    return result


def _resolve(plan: Any, production: bool = True) -> tuple[dict, list[str]]:
    """Replay a persistent world ledger; no hidden resets on A -> B -> A cuts."""
    errors: list[str] = []
    if not isinstance(plan, dict) or plan.get('schema_version') != 'sequence-continuity-1':
        return {}, ['sequence: unsupported/missing plan']
    for key in ('episode_id', 'revision'):
        if not text(plan.get(key)): errors.append('sequence: missing ' + key)
    if production and (plan.get('status') != 'LOCKED' or plan.get('example_only') is not False):
        errors.append('sequence: draft/example plan is not production approval')
    initial = plan.get('initial')
    if (not isinstance(initial, dict) or not text(initial.get('state_id'))
            or not isinstance(initial.get('facts'), dict) or not initial['facts']
            or any(not text(k) for k in initial['facts'])):
        return {}, errors + ['sequence: initial named world facts required']
    try:
        digest(initial['facts'])  # reject nonfinite/unserializable authored facts
    except (ValueError, TypeError):
        return {}, errors + ['sequence: facts must be finite JSON values']
    nullable = plan.get('known_empty_keys', [])
    if not unique_strings(nullable) or not set(nullable).issubset(initial['facts']):
        errors.append('sequence: invalid explicit known-empty fact keys'); nullable = []
    if any(v is None and k not in nullable for k, v in initial['facts'].items()):
        errors.append('sequence: unresolved initial fact')
    fixed = plan.get('fixed_keys')
    if not unique_strings(fixed) or not set(fixed).issubset(initial['facts']):
        errors.append('sequence: invalid fixed fact keys'); fixed = []
    states = {initial['state_id']: deepcopy(initial['facts'])}
    parents = {initial['state_id']: None}
    delta_modes, event_owners = {}, {}
    nodes = index(plan.get('states'), 'state_id', 'sequence states', errors)
    for sid, node in nodes.items():
        parent = node.get('parent_state_id')
        if sid in states or not text(parent) or parent not in states:
            errors.append('sequence: state parent missing/forward/cyclic/duplicate: ' + sid); continue
        changes = node.get('changes')
        if not isinstance(changes, list) or not changes:
            errors.append('sequence: use the same state ID for an unchanged world: ' + sid); continue
        current, used, modes = deepcopy(states[parent]), set(), []
        for change in changes:
            if not isinstance(change, dict):
                errors.append('sequence: malformed change'); continue
            key = change.get('key')
            if not text(key) or key not in current or key in used:
                errors.append('sequence: unknown/duplicate changed fact'); continue
            used.add(key)
            if key in fixed: errors.append('sequence: immutable layout/design fact changed: ' + key)
            if 'before' not in change or digest(change['before']) != digest(current[key]):
                errors.append('sequence: change starts from wrong prior state: ' + key)
            if ('after' not in change or (change['after'] is None and key not in nullable)
                    or digest(change.get('after')) == digest(current[key])):
                errors.append('sequence: unknown/no-op state change: ' + key)
            for field in ('event_id', 'cause_ref', 'approval_ref'):
                if not text(change.get(field)): errors.append('sequence: change needs ' + field)
            event = change.get('event_id')
            if text(event):
                if event in event_owners and event_owners[event] != sid:
                    errors.append('sequence: one event replayed in different states: ' + event)
                event_owners[event] = sid
            mode = change.get('mode')
            if mode not in {'on_screen', 'offscreen_ellipsis'}:
                errors.append('sequence: change needs explicit visibility mode')
            modes.append(mode)
            current[key] = deepcopy(change.get('after'))
        states[sid], parents[sid], delta_modes[sid] = current, parent, modes
    from world_constraints import check_states, check_camera_path
    errors.extend(check_states(states, plan.get('world_constraints', [])))
    def path(ancestor, child):
        if not text(ancestor) or not text(child) or ancestor not in states or child not in states:
            return None
        result = []
        while child != ancestor:
            if parents.get(child) is None: return None
            result.append(child); child = parents[child]
        return list(reversed(result))
    scenes = plan.get('scenes')
    if not isinstance(scenes, dict) or not scenes:
        errors.append('sequence: scene registry required'); scenes = {}
    for sid, scene in scenes.items():
        if not isinstance(scene, dict):
            errors.append('sequence: malformed scene'); continue
        for key in ('layout_revision', 'coordinate_frame'):
            if not text(scene.get(key)): errors.append('sequence: scene missing ' + key)
        if not unique_strings(scene.get('landmarks'), True):
            errors.append('sequence: scene landmarks required')
        views = scene.get('views')
        if not isinstance(views, dict) or not views:
            errors.append('sequence: finite approved camera registry required'); continue
        for vid, view in views.items():
            if not text(vid) or not isinstance(view, dict):
                errors.append('sequence: malformed view'); continue
            for key in ('axis_side', 'plate_asset_id', 'orientation_basis'):
                if not text(view.get(key)): errors.append('sequence: view missing ' + key)
            if not unique_strings(view.get('screen_landmarks')):
                errors.append('sequence: view screen landmarks required')
            elif not set(view['screen_landmarks']).issubset(scene.get('landmarks', [])):
                errors.append('sequence: view uses unregistered landmark')
    shots = index(plan.get('shots'), 'shot_id', 'sequence shots', errors)
    if not shots: errors.append('sequence: nonempty shot scope required')
    previous, visited, resume_stack = None, set(), []
    projections = {}
    for sid, shot in shots.items():
        scene_id, view_id = shot.get('scene_id'), shot.get('view_id')
        scene = scenes.get(scene_id, {}) if text(scene_id) else {}
        views = scene.get('views', {}) if isinstance(scene, dict) else {}
        if not text(view_id) or view_id not in views:
            errors.append(sid + ': unregistered scene/view')
        a, b = shot.get('state_in'), shot.get('state_out')
        if path(a, b) is None: errors.append(sid + ': missing or regressing in-shot state')
        relation = shot.get('relation')
        if relation not in RELATIONS: errors.append(sid + ': explicit cut/time relation required')
        if not text(shot.get('transition_basis')): errors.append(sid + ': transition basis missing')
        if relation in DISCONTINUOUS and (not text(shot.get('approval_ref'))
                or not text(shot.get('orientation_cue'))):
            errors.append(sid + ': deliberate time/place change requires approved orientation')
        if previous is None:
            if relation != 'opening': errors.append(sid + ': first shot must establish opening state')
        else:
            if relation == 'opening': errors.append(sid + ': cannot reopen/reset the world mid-sequence')
            pa, pb = previous.get('state_in'), previous.get('state_out')
            if relation in {'camera_only', 'continuous'}:
                if a != pb or scene_id != previous.get('scene_id'):
                    errors.append(sid + ': ordinary cut cannot silently change world/time/location')
            elif relation == 'flashback':
                resume_stack.append(pb)
            elif relation == 'resume':
                if not resume_stack or path(resume_stack.pop(), a) is None:
                    errors.append(sid + ': resume must restore current-time state, not overwrite it')
            elif relation == 'parallel':
                # Explicit overlapping coverage is allowed, but not unexplained state forks.
                if path(pa, a) is None or (path(pb, b) is None and path(b, pb) is None):
                    errors.append(sid + ': contradictory parallel world branches')
            elif relation != 'intentional':
                gap = path(pb, a)
                if gap is None:
                    errors.append(sid + ': state reset/fork across transition or return')
                elif any(m != 'offscreen_ellipsis' for n in gap for m in delta_modes.get(n, [])):
                    errors.append(sid + ': skipped on-screen event between shots')
            if relation == 'return' and scene_id not in visited:
                errors.append(sid + ': cannot return to an unestablished location')
            if scene_id == previous.get('scene_id') and view_id in views:
                pv = views.get(previous.get('view_id'), {})
                if pv.get('axis_side') != views[view_id].get('axis_side'):
                    if not text(shot.get('axis_change_approval')) or not text(shot.get('orientation_cue')):
                        errors.append(sid + ': axis-side change lacks approved orientation cue')
        keys = shot.get('state_keys')
        if not unique_strings(keys, True) or not set(keys).issubset(initial['facts']):
            errors.append(sid + ': relevant tracked fact scope required'); keys = []
        for boundary in ('start', 'end'):
            visible = shot.get('visible_' + boundary + '_keys')
            if not unique_strings(visible) or not set(visible).issubset(keys):
                errors.append(sid + ': visible fact keys must be a subset of persistent state')
            screen = shot.get('screen_' + boundary)
            if not isinstance(screen, dict) or any(not text(k) or v is None for k, v in screen.items()):
                errors.append(sid + ': explicit resolved screen projection required')
        if plan.get('policy_version') == '4.2.0':
            if not any(shot.get(k) for k in ('visible_start_keys','visible_end_keys','screen_start','screen_end')):
                scope=shot.get('empty_observation_scope', {})
                if not isinstance(scope,dict) or not text(scope.get('reason')) or not text(scope.get('basis_ref')):
                    errors.append(sid + ': empty observation scope needs a frozen visibility rationale')
            errors.extend(sid+': '+e for e in check_camera_path(shot))
        if not text(shot.get('continuity_clause')):
            errors.append(sid + ': brain-authored concrete continuity prompt clause missing')
        method = shot.get('reference_policy')
        if method not in {'same_view_plate', 'adopted_edge', 'target_view_plate', 'establish'}:
            errors.append(sid + ': approved reference construction route missing')
        bindings = shot.get('ensemble_bindings')
        if not isinstance(bindings, list):
            errors.append(sid + ': explicit state-to-ensemble binding array required')
        else:
            bound = [v.get('key') for v in bindings if isinstance(v, dict)]
            if bound != keys or len(bound) != len(bindings):
                errors.append(sid + ': every tracked fact must bind once, in declared order')
            for bind in bindings:
                if (not isinstance(bind, dict) or not text(bind.get('entity_id'))
                        or not isinstance(bind.get('path'), list) or not bind['path']
                        or any(not text(x) for x in bind['path'])):
                    errors.append(sid + ': invalid ensemble state field path')
        # Same view + identical declared dependencies => same screen relation.
        # Legacy entity-named keys get a conservative mapping; v4.2 makes it explicit.
        for boundary, state_id in (('start', a), ('end', b)):
            projection = shot.get('screen_' + boundary, {})
            dependencies = shot.get('projection_dependencies', {})
            current_facts = states.get(state_id, {})
            if not isinstance(projection, dict): continue
            for prop, value in projection.items():
                deps = dependencies.get(prop) if isinstance(dependencies, dict) else None
                if deps is None and plan.get('policy_version')=='4.2.0':
                    errors.append(sid + ': screen property needs explicit fact dependencies: ' + prop)
                    continue
                if deps is None:
                    entity = prop.split('_')[0].upper()
                    deps = [k for k in keys if k.split('.')[0].upper() == entity]
                if not deps:
                    if plan.get('policy_version') == '4.2.0':
                        errors.append(sid + ': screen property needs explicit fact dependencies: ' + prop)
                    continue
                if not unique_strings(deps, True) or not set(deps).issubset(current_facts):
                    errors.append(sid + ': invalid screen projection dependencies'); continue
                camera_pose = shot.get('camera_pose_' + boundary, 'fixed')
                projection_key = digest({'scene': scene_id, 'view': view_id,
                    'layout': scene.get('layout_revision'), 'view_design': views.get(view_id),
                    'camera_pose': camera_pose, 'property': prop,
                    'facts': {k: current_facts[k] for k in deps}})
                if projection_key in projections and projections[projection_key] != value:
                    errors.append(sid + ': unchanged world/view has contradictory screen projection: ' + prop)
                projections[projection_key] = value
        previous = shot
        if text(scene_id): visited.add(scene_id)
    try:
        digest(states)
    except (ValueError, TypeError):
        errors.append('sequence: state changes contain nonfinite/unserializable values')
    return {'states': states, 'shots': shots, 'scenes': scenes}, list(dict.fromkeys(errors))


def resolve(plan: Any, production: bool = True) -> tuple[dict, list[str]]:
    # A malformed contract must fail closed rather than crash its caller.
    try:
        return _resolve(plan, production)
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        return {}, ['sequence: malformed contract: ' + str(exc)]


def check_shot(plan: dict, shot: dict, prompt: str | None = None) -> list[str]:
    ctx, errors = resolve(plan)
    if errors: return errors
    if shot.get('policy_version')=='4.2.0' and plan.get('policy_version')!='4.2.0':
        errors.append('sequence: v4.2 shot cannot use legacy implicit scope')
    row = ctx['shots'].get(shot.get('shot_id'))
    if row is None: return ['sequence: shot missing from brain-frozen sequence']
    for key in ('episode_id',):
        if plan.get(key) != shot.get(key): errors.append('sequence: shot/plan ' + key + ' differs')
    for key in ('scene_id', 'view_id'):
        if row.get(key) != shot.get(key): errors.append('sequence: shot/plan ' + key + ' differs')
    if prompt is not None and row['continuity_clause'] not in prompt:
        errors.append('sequence: final prompt lost or rewrote the frozen continuity clause')
    if shot.get('policy_version')=='4.2.0' and shot.get('camera_motion','fixed')!=row.get('camera_motion','fixed'):
        errors.append('sequence: actual moving-camera contract is missing/different in the frozen path plan')
    ensemble = shot.get('ensemble', {})
    for moment, state_name in (('start_state', 'state_in'), ('end_state', 'state_out')):
        entities = ensemble.get(moment, {}).get('entities', {})
        for bind in row['ensemble_bindings']:
            value = entities.get(bind['entity_id'])
            for field in bind['path']:
                value = value.get(field) if isinstance(value, dict) else None
            if digest(value) != digest(ctx['states'][row[state_name]][bind['key']]):
                errors.append('sequence: ensemble/ledger disagreement: ' + moment + '/' + bind['key'])
    # Boundary checks must cover facts visible in the already-frozen ensemble.
    # A hidden face of a partially visible prop can be exempted WITH a reason;
    # visible objects cannot disappear from review by clearing two arrays.
    windows = ensemble.get('view_plan', {}).get('windows', [])
    for boundary, window in (('start', windows[0] if windows else {}), ('end', windows[-1] if windows else {})):
        visibility = {v.get('entity_id'): v.get('visibility') for v in window.get('entities', [])}
        visible_keys = set(row.get('visible_' + boundary + '_keys', []))
        exemptions = row.get('boundary_exemptions', {}).get(boundary, {})
        for bind in row['ensemble_bindings']:
            vis = visibility.get(bind['entity_id'])
            if vis in {'visible', 'partial', 'reflection_only'} and bind['key'] not in visible_keys:
                exemption = exemptions.get(bind['key'], {})
                if (not isinstance(exemption, dict) or not text(exemption.get('reason'))
                        or not text(exemption.get('basis_ref'))):
                    errors.append('sequence: visible fact omitted from boundary review: ' + boundary + '/' + bind['key'])
            if vis in {'occluded', 'out_of_frame', 'absent'} and bind['key'] in visible_keys:
                errors.append('sequence: invisible fact falsely claimed observable: ' + boundary + '/' + bind['key'])
    views = ctx['scenes'][row['scene_id']]['views']
    plate_id = views[row['view_id']]['plate_asset_id']
    refs = shot.get('references', [])
    plate_roles = {'asset_ref'} if shot.get('mode') == 'video_reference' else {'scene_base', 'start_frame', 'previous_end'}
    if not any(isinstance(r, dict) and r.get('role') in plate_roles
               and (r.get('asset_id') == plate_id or r.get('scene_anchor_asset_id') == plate_id)
               for r in refs):
        errors.append('sequence: target view plate or its explicit lineage is absent from request')
    return errors


def check_file(record, root: Path, verify=verify_record, shot=None, prompt=None):
    errors = verify(record, root)
    if errors: return {}, ['sequence: ' + e for e in errors]
    plan = read_json(root / record['path'])
    ctx, errors = resolve(plan)
    if shot is not None and not errors: errors += check_shot(plan, shot, prompt)
    return ({'plan': plan, **ctx} if not errors else {}), errors


def load_bindings(spec: dict, root: Path, verify=verify_record):
    from brain_handoff import load_task
    errors, context = [], {}
    bindings = spec.get('continuity_bindings')
    if not isinstance(bindings, list) or not bindings:
        return {}, ['sequence: actual continuity_bindings required']
    for binding in bindings:
        if not isinstance(binding, dict):
            errors.append('sequence: malformed file binding'); continue
        sid = binding.get('shot_id')
        ctx, ce = check_file(binding.get('plan'), root, verify)
        errors += ce + ['sequence media: ' + e for e in verify(binding.get('media'), root)]
        task, packet, be = load_task(binding.get('brain_binding'), root, verify)
        errors += be
        if task and (task.get('continuity_plan') != binding.get('plan')
                     or packet.get('episode_id') != spec.get('episode_id')):
            errors.append('sequence: plan is not the brain-frozen task plan')
        if task and spec.get('policy_version') in {'4.1.0', '4.2.0'} and packet.get('policy_version') != spec.get('policy_version'):
            errors.append('sequence: legacy brain packet cannot approve a v4.1 production stage')
        if task and spec.get('action') != 'final_delivery' and task['request'].get('shot_id') != sid:
            errors.append('sequence: wrong approved shot')
        if spec.get('action') == 'final_delivery' or len(spec.get('shot_ids', [])) == 1:
            if binding.get('media') != spec.get('subject'):
                errors.append('sequence: review media differs from gate subject')
        peers = [b for b in spec.get('fidelity_bindings', []) if isinstance(b, dict) and b.get('shot_id') == sid]
        if len(peers) != 1 or peers[0].get('media') != binding.get('media'):
            errors.append('sequence: media does not match existing fidelity gate')
        if ctx and spec.get('action') in {'pre_video', 'shot_edit'}:
            eb = [v for v in spec.get('ensemble_bindings', []) if isinstance(v, dict) and v.get('shot_id') == sid]
            if len(eb) != 1:
                errors.append('sequence: matching ensemble shot binding required')
            else:
                er = eb[0].get('shot_contract'); ee = verify(er, root)
                errors.extend(ee)
                if not ee:
                    authored_shot = read_json(root / er['path'])
                    errors.extend(check_shot(ctx['plan'], authored_shot))
        if ctx:
            if spec.get('policy_version')=='4.2.0' and ctx['plan'].get('policy_version')!='4.2.0':
                errors.append('sequence: v4.2 stage needs explicit v4.2 plan policy')
            if ctx['plan'].get('episode_id') != spec.get('episode_id') or sid not in ctx['shots']:
                errors.append('sequence: shot/episode scope differs')
            elif text(sid): context[sid] = {**ctx, 'record': binding['plan'], 'media': binding['media']}
    ids = [b.get('shot_id') for b in bindings if isinstance(b, dict)]
    if ids != spec.get('shot_ids') or len(context) != len(ids):
        errors.append('sequence: exact ordered shot coverage required')
    if len({v['record']['sha256'] for v in context.values()}) > 1:
        errors.append('sequence: mixed world-ledger revisions in one stage batch')
    return context, errors


def expected_values(ctx: dict, sid: str, moment: str) -> dict:
    row = ctx['shots'][sid]; boundary = 'start' if moment == 'in' else 'end'
    state = ctx['states'][row['state_in' if moment == 'in' else 'state_out']]
    return ({'world:' + k: state[k] for k in row['visible_' + boundary + '_keys']}
            | {'screen:' + k: v for k, v in row['screen_' + boundary].items()})


def expected_revisits(context: dict) -> list[dict]:
    """Group nonadjacent reappearances of visible facts and returns to locations."""
    last_scene, last_fact, groups = {}, {}, {}
    for i, (sid, ctx) in enumerate(context.items()):
        row = ctx['shots'][sid]; scene = row['scene_id']
        candidates = []
        if scene in last_scene: candidates.append((*last_scene[scene], 'scene:' + scene))
        for k in row['visible_start_keys']:
            if k in last_fact: candidates.append((*last_fact[k], 'world:' + k))
        for j, source, key in candidates:
            if j < i - 1: groups.setdefault((source, sid), set()).add(key)
        last_scene[scene] = (i, sid)
        for k in row['visible_end_keys']: last_fact[k] = (i, sid)
    return [{'link_id': a + '__REVISIT__' + b, 'from_shot': a, 'to_shot': b,
             'keys': sorted(keys)} for (a, b), keys in groups.items()]


def check_review(review, context, stage, subject_sha, root, verify=verify_record,
                 timeline=None):
    from fidelity_contract import valid_locator
    errors, failures = [], []
    if not isinstance(review, dict) or review.get('schema_version') != 'sequence-review-1':
        return ['sequence: actual structured continuity review missing'], []
    if stage not in STAGES or review.get('stage') != stage or review.get('subject_sha256') != subject_sha:
        errors.append('sequence: stale subject/stage')
    rows = index(review.get('shots'), 'shot_id', 'sequence review', errors)
    if list(rows) != list(context): errors.append('sequence: observed shot scope incomplete/out of order')
    timeline_ranges = {}
    if stage == 'final':
        # Per occurrence, not per source: a repeated shot needs explicit adopted-shot IDs.
        if not isinstance(timeline, dict):
            errors.append('sequence: final review needs the actual edit timeline')
        else:
            clips = timeline.get('video', [])
            if context:
                plan = next(iter(context.values()))['plan']
                if plan.get('timeline_digest') != digest(timeline):
                    errors.append('sequence: brain-frozen final plan refers to another timeline')
                if list(context) != list(next(iter(context.values()))['shots']):
                    errors.append('sequence: final plan shot scope cannot be silently omitted')
            seen = []
            for sid, ctx in context.items():
                adopted = ctx['shots'][sid].get('adopted_clip_ids')
                if not unique_strings(adopted, True):
                    errors.append('sequence: final plan needs adopted clip IDs: ' + sid); continue
                for cid in adopted:
                    match = [c for c in clips if c.get('id') == cid]
                    if len(match) != 1: errors.append('sequence: unknown adopted clip ' + cid); continue
                    c = match[0]; seen.append(cid)
                    row = ctx['shots'][sid]
                    if c.get('shot_id') != row.get('origin_shot_id', sid):
                        errors.append('sequence: adopted clip belongs to another source shot')
                    timeline_ranges.setdefault(sid, []).append([c['dst_in'], c['dst_in'] + c['src_out'] - c['src_in']])
            if seen != [c.get('id') for c in clips]:
                errors.append('sequence: actual timeline clip coverage/reuse/order mismatch')
            if review.get('timeline_digest') != digest(timeline):
                errors.append('sequence: final observed timeline is stale')
    for sid, ctx in context.items():
        obs = rows.get(sid, {})
        sha = ctx['media']['sha256']
        plan_matches = obs.get('plan_sha256') == ctx['record']['sha256']
        if not plan_matches and stage != 'final' and ctx['plan'].get('policy_version') == '4.2.0' and isinstance(obs.get('original_plan'),dict):
            from workflow_support import reusable_observation
            plan_matches = reusable_observation(obs['original_plan'],ctx['plan'],sid,ctx['media'],obs,root)
        if not plan_matches or obs.get('media_sha256') != sha:
            errors.append(sid + ': observed plan/media revision differs')
        if not text(obs.get('reviewer_id')): errors.append(sid + ': actual reviewer missing')
        if stage != 'start_frame' and obs.get('full_interval_viewed') is not True:
            errors.append(sid + ': isolated endpoint images cannot prove dynamic continuity')
        camera=ctx['shots'][sid].get('camera_path')
        if stage!='start_frame' and camera:
            points=camera['waypoints'];checks=obs.get('trajectory_review',[])
            if not isinstance(checks,list) or [c.get('waypoint_id') for c in checks if isinstance(c,dict)]!=[p['id'] for p in points]:
                errors.append(sid+': intermediate camera trajectory observations missing')
            else:
                previous=-1
                for c in checks:
                    loc=c.get('locator');frame=c.get('event_frame')
                    if not valid_locator(loc,stage) or type(frame) is not int or not loc['start']<=frame<loc['end'] or frame<previous:
                        errors.append(sid+': invalid/unsorted actual camera waypoint evidence')
                    else:previous=frame
                    if c.get('media_sha256')!=sha or not text(c.get('observation')):errors.append(sid+': stale/missing trajectory observation')
                    if c.get('result')=='FAIL':failures.append(sid+': actual camera trajectory failed')
                    elif c.get('result')!='PASS':errors.append(sid+': trajectory not actually confirmed')
                    evidence=c.get('evidence')
                    if not isinstance(evidence,list) or not evidence:errors.append(sid+': trajectory actual evidence missing')
                    else:
                        for record in evidence:errors.extend(verify(record,root))
        moments = index(obs.get('moments'), 'id', sid + ' moments', errors)
        needed = ['in'] if stage == 'start_frame' else ['in', 'out']
        if list(moments) != needed: errors.append(sid + ': entry/exit observations missing')
        for moment in needed:
            point = moments.get(moment, {})
            if point.get('result') == 'FAIL': failures.append(sid + '/' + moment + ': observed continuity failure')
            elif point.get('result') != 'PASS': errors.append(sid + '/' + moment + ': mandatory observation unknown')
            expected = expected_values(ctx, sid, moment)
            actual = point.get('values')
            tolerance = ctx['shots'][sid].get('observation_tolerances', {})
            if not isinstance(actual, dict) or set(actual) != set(expected):
                failures.append(sid + '/' + moment + ': observed world/screen fact coverage differs')
            else:
                for key, value in expected.items():
                    try:
                        if not equal_value(value, actual[key], tolerance.get(key)):
                            failures.append(sid + '/' + moment + ': observed world/screen facts differ: ' + key)
                    except ValueError as exc: errors.append(sid + ': invalid tolerance: ' + str(exc))
            if not text(point.get('observation')): errors.append(sid + ': actual observation missing')
            locator = point.get('locator')
            if not valid_locator(locator, stage): errors.append(sid + ': actual media locator missing')
            elif stage == 'final':
                # Endpoint evidence must cover each actual adopted boundary, not arbitrary frames.
                ranges = timeline_ranges.get(sid, [])
                for a, b in ranges:
                    boundary = a if moment == 'in' else b - 1
                    if not locator['start'] <= boundary < locator['end']:
                        errors.append(sid + ': evidence omits adopted ' + moment + ' boundary')
                if timeline and locator['end'] > timeline['duration_frames']:
                    errors.append(sid + ': evidence outside final media duration')
            if point.get('media_sha256') != sha: errors.append(sid + ': endpoint evidence media differs')
            ev = point.get('evidence')
            if not isinstance(ev, list) or not ev: errors.append(sid + ': actual evidence files missing')
            else:
                for record in ev: errors += ['sequence evidence: ' + e for e in verify(record, root)]
    if stage == 'final':
        wanted = expected_revisits(context)
        links = index(review.get('revisits'), 'link_id', 'sequence revisits', errors)
        if list(links) != [r['link_id'] for r in wanted]:
            errors.append('sequence: nonadjacent location/prop reappearance review missing')
        for expected in wanted:
            r = links.get(expected['link_id'], {})
            if r.get('binding_digest') != digest(expected): errors.append('sequence: stale revisit pair/scope')
            if r.get('paired_context_viewed') is not True: errors.append('sequence: revisit pair not actually compared')
            if r.get('result') == 'FAIL': failures.append('sequence: failed revisit ' + expected['link_id'])
            elif r.get('result') != 'PASS': errors.append('sequence: revisit observation unknown')
            if not text(r.get('observation')): errors.append('sequence: revisit observation missing')
            # Existing shot endpoint evidence is reused by ID, not regenerated in another model call.
            if r.get('evidence_moments') != [expected['from_shot'] + '/out', expected['to_shot'] + '/in']:
                errors.append('sequence: revisit must reuse the actual source-exit/target-entry evidence')
    return list(dict.fromkeys(errors)), list(dict.fromkeys(failures))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--plan', type=Path, required=True)
    a = p.parse_args()
    try:
        _, errors = resolve(read_json(a.plan))
        result = {'status': 'BLOCKED' if errors else 'CONTRACT_OK', 'errors': errors,
                  'media_quality_verified': False, 'executed_generation': False}
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
        result = {'status': 'BLOCKED', 'errors': [str(exc)], 'media_quality_verified': False}
    import json
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return 2 if result['status'] == 'BLOCKED' else 0


if __name__ == '__main__': raise SystemExit(main())
