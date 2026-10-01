#!/usr/bin/env python3
"""Small deterministic helpers for scope reuse, scheduling and technical latitude.

No regeneration is triggered and no old PASS is relabeled. A changed packet still
needs new authorization even when old media observations are safely reusable.
"""
from __future__ import annotations
from copy import deepcopy
import math
from pathlib import Path
from typing import Any
from brain_handoff import digest, read_json, verify_record, text


def shot_scope(plan: dict, sid: str) -> dict:
    from sequence_continuity import resolve
    ctx,errors=resolve(plan)
    if errors: raise ValueError('; '.join(errors))
    row=ctx['shots'][sid]
    keys=set(row['state_keys'])
    deps=row.get('projection_dependencies',{})
    for values in deps.values(): keys.update(values)
    scene=ctx['scenes'][row['scene_id']]
    # Preserve all authored shot semantics, but not unrelated scene views or
    # global ledger revision. Selected start/end facts are deterministic replay.
    result={'policy_version':plan.get('policy_version','legacy'),'episode_id':plan['episode_id'],
            'shot':deepcopy(row),'layout_revision':scene['layout_revision'],
            'coordinate_frame':scene['coordinate_frame'],'landmarks':scene['landmarks'],
            'view':scene['views'][row['view_id']],
            'state_in':{k:ctx['states'][row['state_in']][k] for k in sorted(keys)},
            'state_out':{k:ctx['states'][row['state_out']][k] for k in sorted(keys)}}
    # Only changes on the shot's actual ancestry and relevant facts affect its
    # event semantics. Do not hash unrelated branches or future episodes.
    nodes={n['state_id']:n for n in plan['states']};chain=[];at=row['state_out']
    while at in nodes:
        node=nodes[at]
        changes=[c for c in node['changes'] if c['key'] in keys]
        if changes:chain.append({'state_id':at,'changes':changes})
        at=node['parent_state_id']
    result['relevant_ancestry']=list(reversed(chain))
    return result


def diff_scopes(old: dict,new: dict)->dict:
    old_ids={s['shot_id'] for s in old['shots']};new_ids={s['shot_id'] for s in new['shots']}
    changed=[];unchanged=[]
    for sid in sorted(old_ids & new_ids):
        (unchanged if digest(shot_scope(old,sid))==digest(shot_scope(new,sid)) else changed).append(sid)
    added=sorted(new_ids-old_ids);removed=sorted(old_ids-new_ids)
    sequence=[s['shot_id'] for s in new['shots']];adjacent=set()
    for i,sid in enumerate(sequence):
        if sid in changed+added:
            if i:adjacent.add((sequence[i-1],sid))
            if i+1<len(sequence):adjacent.add((sid,sequence[i+1]))
    old_edges=set(zip([s['shot_id'] for s in old['shots']],[s['shot_id'] for s in old['shots']][1:]))
    new_edges=set(zip(sequence,sequence[1:]));adjacent|=new_edges-old_edges
    from sequence_continuity import expected_revisits, resolve
    context, errors=resolve(new)
    if errors: raise ValueError('; '.join(errors))
    revisits=expected_revisits({sid:{'shots':context['shots']} for sid in sequence})
    affected=set(changed+added)
    old_context, errors=resolve(old)
    old_revisits=expected_revisits({sid:{'shots':old_context['shots']} for sid in old_context['shots']}) if not errors else []
    revisit_ids={digest(r) for r in old_revisits}
    revisit_changes=[r for r in revisits if r['from_shot'] in affected or r['to_shot'] in affected or digest(r) not in revisit_ids]
    return {'revisits_to_review':revisit_changes,'unchanged_shots':unchanged,'changed_shots':changed,'added':added,'removed':removed,
            'cuts_to_review':[list(v) for v in sorted(adjacent)],
            'requires_new_packet_approval':digest(old)!=digest(new),
            'final_export_review_required':digest(old)!=digest(new),
            'notice':'No automatic acceptance; old media and observation provenance must still match.'}


def reusable_observation(old_record: dict,new_plan: dict,sid: str,media: dict,original_observation: dict,root:Path)->bool:
    if verify_record(old_record,root) or verify_record(media,root): return False
    old=read_json(root/old_record['path'])
    if original_observation.get('plan_sha256')!=old_record['sha256'] or original_observation.get('media_sha256')!=media['sha256']: return False
    try:return digest(shot_scope(old,sid))==digest(shot_scope(new_plan,sid))
    except (ValueError,KeyError,TypeError):return False


def critical_path_order(tasks: list[dict]) -> list[str]:
    """Priority, then longest remaining declared work, then FIFO. No fake timings.

    If durations are unknown, each node has one *work unit*, never a guessed
    number of seconds. Actual slot/cost/authorization constraints stay in the
    existing execution_control.plan_dispatch scheduler.
    """
    rows={r['job_id']:r for r in tasks}
    if len(rows)!=len(tasks):raise ValueError('duplicate job ID')
    children={k:[] for k in rows}
    for row in tasks:
        for parent in row.get('depends_on',[]):
            if parent not in rows:raise ValueError('unresolved dependency')
            children[parent].append(row['job_id'])
    use_time=all(type(r.get('estimated_duration_s')) in (float,int) and math.isfinite(r['estimated_duration_s']) and r['estimated_duration_s']>0 for r in tasks)
    scores={};visiting=set()
    def score(k):
        if k in scores:return scores[k]
        if k in visiting:raise ValueError('dependency cycle')
        visiting.add(k);r=rows[k]
        own=r['estimated_duration_s'] if use_time else 1
        value=own+max((score(c) for c in children[k]),default=0)
        visiting.remove(k);scores[k]=value;return value
    for k in rows:score(k)
    return sorted(rows,key=lambda k:(-rows[k].get('priority',0),-scores[k],rows[k].get('queue_order',0),k))


def technical_patch(before: dict,after: dict,policy: dict)->list[str]:
    """Permit only host-approved technical alternatives, never creative changes."""
    if not isinstance(policy,dict) or not isinstance(policy.get('allowed_values'),dict):return ['technical policy not approved']
    hard=set(policy.get('immutable_keys',[]))|{'model_id','steps','precision','width','height','fps','duration','prompt','text_spoken','camera','state','voice_id'}
    errors=[]
    for key in set(before)|set(after):
        if before.get(key)==after.get(key) and type(before.get(key)) is type(after.get(key)):continue
        if key in hard:errors.append('technical action changes protected decision: '+key)
        elif key not in policy['allowed_values'] or after.get(key) not in policy['allowed_values'][key]:errors.append('technical action outside preauthorized alternatives: '+key)
    if not text(policy.get('approval_ref')):errors.append('technical alternatives lack approval')
    return errors
