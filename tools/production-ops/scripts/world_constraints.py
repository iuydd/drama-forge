#!/usr/bin/env python3
"""Small authored cross-fact invariants, NOT a physics simulator or vision model."""
from brain_handoff import digest, text


def check_states(states: dict, rules: list) -> list[str]:
    errors=[]
    if not isinstance(rules,list): return ['world constraints must be an array']
    ids=set()
    for rule in rules:
        if not isinstance(rule,dict) or not text(rule.get('id')) or rule['id'] in ids:
            errors.append('world constraint needs a unique ID');continue
        ids.add(rule['id']);op=rule.get('op')
        if op not in {'not_all','requires','unique_nonempty'}:
            errors.append('unsupported world constraint operator');continue
        if not text(rule.get('basis_ref')):errors.append('world constraint needs frozen intent basis')
        for sid,facts in states.items():
            if op=='unique_nonempty':
                keys=rule.get('keys')
                if not isinstance(keys,list) or len(keys)<2 or len(set(keys))!=len(keys) or any(k not in facts for k in keys):
                    errors.append('unique ownership/support constraint keys invalid');break
                values=[digest(facts[k]) for k in keys if facts[k] not in (None,'')]
                if len(values)!=len(set(values)):errors.append(f'{sid}: duplicated ownership/resource under {rule["id"]}')
            else:
                condition=rule.get('when');then=rule.get('then')
                if not isinstance(condition,dict) or not condition or not set(condition).issubset(facts):
                    errors.append('world constraint antecedent invalid');break
                matched=all(digest(facts[k])==digest(v) for k,v in condition.items())
                if op=='not_all' and matched:errors.append(f'{sid}: forbidden fact combination under {rule["id"]}')
                if op=='requires':
                    if not isinstance(then,dict) or not then or not set(then).issubset(facts):
                        errors.append('world constraint consequent invalid');break
                    if matched and any(digest(facts[k])!=digest(v) for k,v in then.items()):
                        errors.append(f'{sid}: missing required support/contact fact under {rule["id"]}')
    return list(dict.fromkeys(errors))


def check_camera_path(shot:dict)->list[str]:
    """A moving shot needs authored intermediate coverage, not guessed geometry."""
    a=shot.get('camera_pose_start','fixed');b=shot.get('camera_pose_end','fixed')
    path=shot.get('camera_path')
    moving=shot.get('camera_motion') not in (None,'fixed') or digest(a)!=digest(b)
    if not moving and path is None:return []
    if not isinstance(path,dict) or not text(path.get('basis_ref')):
        return ['moving camera needs frozen trajectory/space basis']
    points=path.get('waypoints')
    if not isinstance(points,list) or len(points)<3:return ['moving camera needs entry, intermediate and exit coverage']
    errors=[];ids=[];previous=-1
    for point in points:
        if not isinstance(point,dict):errors.append('camera waypoint must be an object');continue
        t=point.get('progress')
        if type(t) not in (int,float) or not 0<=t<=1 or t<=previous:errors.append('camera progress must be strictly ordered in [0,1]')
        else:previous=t
        if not text(point.get('id')) or point['id'] in ids:errors.append('camera waypoint IDs invalid')
        else:ids.append(point['id'])
        if not text(point.get('visibility_basis')):errors.append('camera waypoint needs visible-face/occlusion basis')
    if points[0].get('progress')!=0 or points[-1].get('progress')!=1:errors.append('camera path must cover full route')
    if points[0].get('pose')!=a or points[-1].get('pose')!=b:errors.append('camera path endpoints disagree with frozen poses')
    return errors
