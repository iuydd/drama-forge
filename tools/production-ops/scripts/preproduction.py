#!/usr/bin/env python3
"""Upfront-only brain protocol. Local validation/binding, never generates media.

Content is data, never eval/exec. Files and acceptance are acquired at runtime;
receiving a blueprint is not media approval or authority to spend money.
"""
from __future__ import annotations
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any
from brain_handoff import digest, read_json, text, verify_record
from h3_reference import is_reference, reference_errors, native_payload

ROOT = Path(__file__).resolve().parents[3]
VERSION = '4.3.0'
RISKS = {'direction', 'gaze', 'action', 'text', 'placement', 'performance'}
KINDS = {'asset_image','start_frame','video','audio','edit'}
MAX_BYTES = 32 * 1024 * 1024


def strict_json(s: str) -> Any:
    if not isinstance(s, str) or len(s.encode('utf-8')) > MAX_BYTES:
        raise ValueError('JSON input missing or too large')
    def pairs(rows):
        d = {}
        for k, v in rows:
            if k in d: raise ValueError('duplicate JSON key: ' + k)
            d[k] = v
        return d
    def bad(x): raise ValueError('nonfinite JSON constant: ' + x)
    return json.loads(s, object_pairs_hook=pairs, parse_constant=bad)


def unique(values: Any, nonempty=False) -> bool:
    return isinstance(values,list) and (bool(values) or not nonempty) and all(text(v) for v in values) and len(values)==len(set(values))


def request_errors(r: Any) -> list[str]:
    if not isinstance(r,dict): return ['project request must be object']
    e = []
    for k in ('project_id','request_id','user_brief'):
        if not text(r.get(k)): e.append('request: missing ' + k)
    if not unique(r.get('episode_ids'),True): e.append('request: explicit episode scope required')
    for k in ('source_texts','existing_assets'):
        if not isinstance(r.get(k),list): e.append('request: ' + k + ' must be array')
    for k in ('media_profiles','quality_limits'):
        if not isinstance(r.get(k),dict): e.append('request: ' + k + ' must be object (unknown may be empty)')
    return e


def prepare(r: dict) -> dict:
    e = request_errors(r)
    if e: raise ValueError('; '.join(e))
    if r.get('legacy_brain_compatibility') is not True:
        raise ValueError('legacy Brain transport requires explicit legacy_brain_compatibility=true; current production uses upfront_self')
    brain = (ROOT/'assets/brain-skill.md').read_text(encoding='utf-8')
    schema = read_json(ROOT/'schemas/brain-response.schema.json')
    instructions = brain + '\n\n# 自动交换记录格式\n' + (ROOT/'prompts/record-format.txt').read_text(encoding='utf-8')
    prompt = (ROOT/'prompts/agent-to-brain.txt').read_text(encoding='utf-8').replace('{{PROJECT_REQUEST_JSON}}',json.dumps(r,ensure_ascii=False,indent=2))
    return {'schema_version':'brain-message-1','workflow_version':VERSION,'instructions':instructions,
            'input':prompt+'\n\n响应JSON Schema：\n'+json.dumps(schema,ensure_ascii=False),
            'request_id':r['request_id'],'request_digest':digest(r),'tools':[],
            'production_started':False}


def part_errors(p: Any) -> list[str]:
    import jsonschema
    schema = read_json(ROOT/'schemas/brain-response.schema.json')
    e = [str(x.message) for x in jsonschema.Draft202012Validator(schema).iter_errors(p)]
    if e: return e
    ids = [x['id'] for x in p['manifest']]
    if not unique(ids,True): e.append('manifest: duplicate/empty record ID')
    records = [x['id'] for x in p['records']]
    if not unique(records): e.append('part: duplicate record ID')
    if not set(records).issubset(ids): e.append('part: unmanifested record')
    for item in p['records']:
        try:
            value = strict_json(item['content'])
            if not isinstance(value,dict): e.append('record content must be object: '+item['id'])
        except (ValueError,TypeError) as ex: e.append('record JSON invalid: '+item['id']+': '+str(ex))
    for row in p['manifest']:
        if row['episode_id'] is not None and row['episode_id'] not in p['episode_ids']:
            e.append('manifest episode outside requested scope')
    return e


def assemble(parts: list[dict], request: dict) -> dict:
    e = request_errors(request)
    if e: raise ValueError('; '.join(e))
    if not parts: raise ValueError('no response parts')
    for p in parts:
        e = part_errors(p)
        if e: raise ValueError('; '.join(e))
    base = parts[0]
    for k in ('project_id','request_id','episode_ids'):
        if base[k]!=request[k]: raise ValueError('response/request scope mismatch: '+k)
    stable = ('project_id','request_id','plan_id','revision','episode_ids','manifest','invalidates')
    indices, rows, blocked = {}, {}, []
    for p in parts:
        if any(p[k]!=base[k] for k in stable): raise ValueError('mixed revision/scope/manifest in response parts')
        i = p['part_index']
        if i in indices:
            if indices[i]!=p: raise ValueError('conflicting duplicate part')
            continue
        indices[i] = p
        blocked.extend(p['execution_blockers'])
        for row in p['records']:
            obj = strict_json(row['content'])
            if row['id'] in rows and rows[row['id']]!=obj: raise ValueError('conflicting repeated record: '+row['id'])
            rows[row['id']] = obj
    if sorted(indices)!=list(range(1,max(indices)+1)): raise ValueError('missing part index')
    missing = [r['id'] for r in base['manifest'] if r['id'] not in rows]
    last = indices[max(indices)]
    if any(p['status']=='BLOCKED' for p in indices.values()): status='BLOCKED'
    elif missing or last['status']!='COMPLETE': status='INCOMPLETE'
    else: status='PLAN_COMPLETE'
    if any(p['status']=='COMPLETE' for i,p in indices.items() if i!=max(indices)):
        raise ValueError('COMPLETE occurred before last part')
    result = {'schema_version':'preproduction-plan-1','workflow_version':VERSION,'workflow_mode':'upfront_only',
              **{k:deepcopy(base[k]) for k in stable},'status':status,'records':rows,
              'missing_records':missing,'execution_blockers':list(dict.fromkeys(blocked)),
              'request':deepcopy(request),'response_parts_digest':digest([indices[i] for i in sorted(indices)]),
              'assumptions':list(dict.fromkeys(x for p in indices.values() for x in p['assumptions'])),
              'media_approved':False,'spending_authorized':False}
    if status=='PLAN_COMPLETE':
        errs=plan_errors(result)
        if errs: raise ValueError('; '.join(errs))
    return result


def group(plan: dict, kind: str) -> list[dict]:
    return [plan['records'][r['id']] for r in plan['manifest'] if r['kind']==kind and r['id'] in plan['records']]


def slots(value: Any) -> list[dict]:
    if isinstance(value,dict):
        if '$asset' in value: return [value]
        return [s for v in value.values() for s in slots(v)]
    if isinstance(value,list): return [s for v in value for s in slots(v)]
    return []


def new_view_errors(task: dict) -> list[str]:
    """Scene assets use the existing scene/shot compiler, not an unbound text route."""
    request = task.get('request_template', {})
    execution = task.get('execution_template')
    if task.get('kind') != 'asset_image':
        return ['new_view must produce an asset_image']
    if not isinstance(execution, dict) or any(not isinstance(execution.get(k), dict)
            for k in ('scene', 'shot', 'runtime_profile')):
        return ['new_view requires the shared scene/shot/runtime_profile execution template']
    if request.get('configuration_sha256') != 'COMPUTE_FROM_EXECUTION_TEMPLATE':
        return ['new_view must bind its shared scene through COMPUTE_FROM_EXECUTION_TEMPLATE']
    shot = execution['shot']
    if shot.get('mode') != 'new_view' or shot.get('shot_id') != request.get('shot_id'):
        return ['new_view execution shot identity/mode differs from request']
    sources = [r for r in shot.get('references', []) if isinstance(r, dict)
               and r.get('primary') is True and r.get('role') == 'scene_base']
    if len(sources) != 1 or not any(s.get('$asset') == sources[0].get('asset_id') for s in slots(sources[0])):
        return ['new_view requires an accepted scene-base asset slot, not identity-only or empty inputs']
    visual = ROOT / 'tools/visual-continuity-prompter/scripts'
    if str(visual) not in sys.path:
        sys.path.insert(0, str(visual))
    from continuity_tools import validate
    return ['new_view: ' + error for error in validate(execution['scene'], shot,
            execution['runtime_profile'], production=False)]


def missing_state_facts(before: dict, after: dict, prefix: str = '') -> list[str]:
    """End states are snapshots; an explicit value can change, a fact cannot vanish."""
    missing = []
    for key, value in before.items():
        path = prefix + str(key)
        if key not in after:
            missing.append(path)
        elif isinstance(value, dict):
            if not isinstance(after[key], dict):
                missing.append(path)
            else:
                missing.extend(missing_state_facts(value, after[key], path + '.'))
    return missing


def plan_errors(p: Any) -> list[str]:
    if not isinstance(p,dict) or p.get('schema_version')!='preproduction-plan-1': return ['unsupported preproduction plan']
    if p.get('workflow_mode')!='upfront_only' or p.get('workflow_version')!=VERSION: return ['wrong workflow']
    if p.get('status')!='PLAN_COMPLETE': return ['all upfront records must be complete before production']
    if p.get('media_approved') is not False or p.get('spending_authorized') is not False:
        return ['plan must not claim media approval or spending authorization']
    try:
        if p.get('missing_records')!=[]: return ['missing upfront records']
        e=request_errors(p.get('request'))
        if e: return e
        if any(p.get(k)!=p['request'].get(k) for k in ('project_id','request_id','episode_ids')):
            return ['assembled plan/request identity or episode scope changed']
        manifest=p.get('manifest');records=p.get('records')
        if not isinstance(manifest,list) or not isinstance(records,dict): return ['plan manifest/records required']
        mids=[m.get('id') for m in manifest if isinstance(m,dict)]
        if len(mids)!=len(manifest) or not unique(mids,True) or set(mids)!=set(records):
            return ['plan manifest must cover each record exactly once']
        if any(not isinstance(v,dict) for v in records.values()): return ['record objects required']
        valid_kinds={'world','episode','asset','task','repair','delivery'}
        if any(m.get('kind') not in valid_kinds or m.get('episode_id') not in [None]+p['episode_ids'] for m in manifest):
            return ['manifest kind or episode invalid']
        if len(group(p,'world'))!=1 or len(group(p,'delivery'))!=1: e.append('one world and one delivery record required')
        worlds=group(p,'world')
        if worlds:
            w=worlds[0]
            if not isinstance(w.get('locations'),list) or not w['locations']: e.append('world locations required')
            if not isinstance(w.get('initial_state'),dict) or not w['initial_state']: e.append('world initial state required')
        eps=group(p,'episode'); ids=[x.get('episode_id') for x in eps]
        if ids!=p['episode_ids']: e.append('complete episode records in requested order required')
        tasks=group(p,'task'); tids=[x.get('task_id') for x in tasks]
        if not unique(tids,True): return e+['unique nonempty task IDs required']
        by_id=dict(zip(tids,tasks)); assets=group(p,'asset'); aids=[x.get('asset_id') for x in assets]
        if not unique(aids,True): e.append('unique asset IDs required')
        existing={x.get('asset_id') for x in p['request']['existing_assets'] if isinstance(x,dict)}
        producer={}
        for a in assets:
            aid=a.get('asset_id')
            if not text(a.get('description')) or not unique(a.get('acceptance'),True): e.append('asset identity/acceptance missing: '+str(aid))
            if a.get('existing') is True:
                if aid not in existing or a.get('producer_task_id') is not None: e.append('unverified existing asset: '+str(aid))
            elif a.get('existing') is False:
                prod=a.get('producer_task_id')
                if prod not in by_id or aid not in by_id[prod].get('produces',[]): e.append('asset producer missing: '+str(aid))
                producer[aid]=prod
            else: e.append('asset existing state unspecified')
        deps={}
        for t in tasks:
            tid=t['task_id']; req=t.get('request_template',{})
            if t.get('kind') not in KINDS or req.get('kind')!=t.get('kind'): e.append(tid+': invalid request kind')
            if t.get('episode_id') is not None and t['episode_id'] not in p['episode_ids']: e.append(tid+': episode outside scope')
            if not text(req.get('prompt')) or re.search(r'\{\{|\bTODO\b|自行补全|后续同理',req.get('prompt','')): e.append(tid+': complete literal prompt required')
            if not isinstance(req.get('inputs'),list) or not isinstance(req.get('output_spec'),dict): e.append(tid+': explicit inputs/output spec required')
            if req.get('mode') == 'new_view':
                e.extend(tid+': '+err for err in new_view_errors(t))
            if t.get('kind') == 'video':
                if req.get('video_input') not in {'references', 'keyframe'}:
                    e.append(tid+': explicit video_input required (default references; keyframe only by request)')
                if is_reference(req):
                    e.extend(tid+': '+err for err in reference_errors(req))
                    for ref in req.get('inputs', []):
                        if isinstance(ref,dict) and ref.get('file') != {'$asset':ref.get('asset_id'),'field':'file'}:
                            e.append(tid+': each reference must bind its own accepted asset file')
            if not unique(t.get('depends_on')) or not set(t.get('depends_on',[])).issubset(tids) or tid in t.get('depends_on',[]): e.append(tid+': dependency missing/invalid')
            deps[tid]=set(t.get('depends_on',[]))
            if not unique(t.get('produces'),True) or not set(t.get('produces',[])).issubset(aids): e.append(tid+': produced assets missing')
            if not unique(t.get('acceptance'),True): e.append(tid+': actual acceptance criteria missing')
            risks=t.get('requirements')
            if not isinstance(risks,dict) or set(risks)!=RISKS or any(not text(v) for v in risks.values()): e.append(tid+': six applicable requirements/NA reasons required')
            if t.get('kind') in {'start_frame','video'}:
                state=t.get('state')
                if not isinstance(state,dict) or not isinstance(state.get('in'),dict) or not isinstance(state.get('out'),dict) or not text(state.get('transition')) or not isinstance(state.get('allowed_changes'),list): e.append(tid+': state/transition missing')
                else:
                    e.extend(tid+': end state lost fact: '+key for key in missing_state_facts(state['in'],state['out']))
            for s in slots(t):
                if set(s)!={'$asset','field'} or s['field'] not in {'file','path','sha256'} or s['$asset'] not in aids: e.append(tid+': unknown/non-file asset slot')
            # A direct locked quality key cannot silently diverge in a task.
            for k,v in p['request']['quality_limits'].items():
                if k in req['output_spec'] and req['output_spec'][k]!=v: e.append(tid+': changed locked quality '+k)
        visiting,done=set(),set()
        def visit(i):
            if i in visiting: raise ValueError('cyclic task dependencies')
            if i in done: return
            visiting.add(i)
            for j in deps.get(i,set()):
                if j not in by_id: continue
                visit(j)
            visiting.remove(i);done.add(i)
        for i in tids: visit(i)
        def ancestors(i):
            out=set(deps[i]); stack=list(out)
            while stack:
                for j in deps.get(stack.pop(),set()):
                    if j not in out: out.add(j);stack.append(j)
            return out
        for t in tasks:
            for s in slots(t):
                pr=producer.get(s['$asset'])
                if pr and pr not in ancestors(t['task_id']): e.append(t['task_id']+': asset producer is not an upstream dependency')
        for ep in eps:
            if not text(ep.get('script')): e.append('full episode script missing')
            if not unique(ep.get('shot_ids'),True) or not isinstance(ep.get('dialogue'),list) or not isinstance(ep.get('edit_plan'),dict) or not ep.get('edit_plan') or not unique(ep.get('qa_targets'),True): e.append('episode shots/dialogue/edit/QA missing')
            for sh in ep.get('shot_ids',[]):
                vids=[t for t in tasks if t.get('shot_id')==sh and t.get('episode_id')==ep['episode_id'] and t['kind']=='video']
                if not vids: e.append('missing video for '+sh)
                # video_input=references: character/prop/scene assets go straight to the video model, no start frame.
                ref_mode=bool(vids) and all(is_reference(v['request_template']) for v in vids)
                if ref_mode:
                    if any(t.get('shot_id')==sh and t.get('episode_id')==ep['episode_id'] and t['kind']=='start_frame' for t in tasks):
                        e.append(sh+': reference video must not schedule a start_frame task')
                    for v in vids:
                        if not slots(v): e.append(v['task_id']+': references mode needs accepted asset inputs')
                        for slot in slots(v):
                            prod=by_id.get(producer.get(slot['$asset']),{})
                            if prod.get('kind') in {'start_frame','video'}:
                                e.append(v['task_id']+': references cannot use a generated start frame or previous video')
                elif not any(t.get('shot_id')==sh and t.get('episode_id')==ep['episode_id'] and t['kind']=='start_frame' for t in tasks): e.append('missing start_frame for '+sh)
        for r in group(p,'repair'):
            if not text(r.get('trigger')) or not unique(r.get('task_ids'),True) or not set(r['task_ids']).issubset(tids) or not unique(r.get('replaces'),True) or not set(r['replaces']).issubset(tids): e.append('repair needs concrete condition and full task branches')
            if type(r.get('max_attempts')) is not int or r['max_attempts']<1 or not unique(r.get('preserve'),True) or not unique(r.get('recheck'),True): e.append('repair limits/preservation/recheck missing')
        delivery=group(p,'delivery')
        if delivery:
            d=delivery[0]
            if d.get('episode_order')!=p['episode_ids'] or not set(('G0','G1','G2','G3','G4')).issubset(d.get('required_gates',[])): e.append('delivery scope/gates missing')
            if d.get('auto_publish') is not False: e.append('production does not authorize publishing')
            if type(d.get('max_attempts_per_failure_chain')) is not int or d['max_attempts_per_failure_chain']<1: e.append('bounded failure chain required')
        return sorted(set(e))
    except (KeyError,TypeError,ValueError,RecursionError) as ex:
        return ['malformed/contradictory upfront plan: '+str(ex)]


def validate_registry(registry: dict, root: Path, required: set[str]) -> dict:
    if not isinstance(registry,dict) or registry.get('schema_version')!='accepted-asset-registry-1': raise ValueError('actual asset registry required')
    rows=registry.get('assets')
    if not isinstance(rows,list): raise ValueError('registry assets array required')
    ids=[r.get('asset_id') for r in rows if isinstance(r,dict)]
    if len(ids)!=len(rows) or not unique(ids): raise ValueError('registry asset IDs invalid')
    result={r['asset_id']:r for r in rows}
    for aid in required:
        if aid not in result: raise ValueError('asset not produced/accepted: '+aid)
        r=result[aid]
        errors=verify_record(r.get('file'),root)+verify_record(r.get('review'),root)
        if errors: raise ValueError('; '.join(errors))
        review=read_json(root/r['review']['path'])
        if (review.get('status')!='ACCEPTED' or review.get('subject')!=r['file'] or
            review.get('reviewer_role') not in {'production_reviewer','independent_reviewer'} or
            not text(review.get('reviewer_id')) or not text(review.get('observation')) or
            review.get('full_required_scope_observed') is not True):
            raise ValueError('asset has no current local media acceptance: '+aid)
        evidence=review.get('evidence')
        if not isinstance(evidence,list) or not evidence: raise ValueError('actual media observation evidence required')
        for ev in evidence:
            errors=verify_record(ev,root)
            if errors: raise ValueError('; '.join(errors))
    return result


def expand(value: Any, assets: dict) -> Any:
    if isinstance(value,dict):
        if '$asset' in value:
            if set(value)!={'$asset','field'} or value['field'] not in {'file','path','sha256'}: raise ValueError('only declared file slots can be bound')
            r=assets[value['$asset']]['file']
            return deepcopy(r if value['field']=='file' else r[value['field']])
        return {k:expand(v,assets) for k,v in value.items()}
    if isinstance(value,list): return [expand(v,assets) for v in value]
    return value


def bind_task(plan: dict, task_id: str, registry: dict, root: Path) -> dict:
    e=plan_errors(plan)
    if e: raise ValueError('; '.join(e))
    if plan.get('execution_blockers'): raise ValueError('unresolved execution blockers: '+ '; '.join(plan['execution_blockers']))
    ts=[t for t in group(plan,'task') if t['task_id']==task_id]
    if len(ts)!=1: raise ValueError('unknown task ID')
    t=ts[0]; required={s['$asset'] for s in slots(t)}
    assets=validate_registry(registry,root,required)
    request=expand(t['request_template'],assets)
    execution=expand(t.get('execution_template'),assets)
    # Adapt file slots to legacy flat reference records without changing order/text.
    for ref in request['inputs']:
        if isinstance(ref,dict) and 'file' in ref:
            file=ref.pop('file')
            if not isinstance(file,dict) or set(file)!={'path','sha256'}: raise ValueError('file slot did not bind to a real record')
            if 'path' in ref or 'sha256' in ref: raise ValueError('ambiguous input file binding')
            ref.update(file)
    if request.get('configuration_sha256')=='COMPUTE_FROM_EXECUTION_TEMPLATE':
        if not isinstance(execution,dict): raise ValueError('runtime scene/shot/profile template required')
        # Propagate the plan's explicit route into its execution copy. Older 4.2
        # snapshots without video_input remain byte-compatible when used directly.
        if request.get('kind') == 'video':
            for key in ('video_input','image_mode'):
                if key in request: execution['shot'].setdefault(key,request[key])
        from brain_handoff import request_snapshot
        snap=request_snapshot(execution['scene'],execution['shot'],execution['runtime_profile'],request['prompt'])
        request['configuration_sha256']=snap['configuration_sha256']
        if request!=snap: raise ValueError('complete request differs from deterministic execution snapshot')
        if request.get('mode') == 'new_view':
            from continuity_tools import compile_package
            compiled = compile_package(execution['scene'], execution['shot'], execution['runtime_profile'], root)
            if not compiled['prompt'] or compiled['prompt'] != request['prompt']:
                raise ValueError('new_view final prompt differs from the shared scene/view compilation')
    return {'request':request,'request_sha256':digest(request),'execution_inputs':execution,
            'plan_sha256':digest(plan),'task_id':task_id,
            'bound_assets':{a:assets[a]['file'] for a in sorted(required)},
            'media_acceptance_owner':'production_reviewer',
            'brain_media_review_performed':False,'ready_for_submission':False,
            'remaining_gates':['current_production_gates','capability','native_payload','budget','protected_host_approval']}


def delegated_packet_errors(packet: dict, task: dict, root: Path) -> list[str]:
    """Bridge into legacy 4.2 media validators without pretending brain saw media."""
    e=[]
    if packet.get('workflow_version')!=VERSION or packet.get('workflow_mode')!='upfront_only' or packet.get('decision_owner')!='production_supervisor':
        return ['execution packet requires explicit upfront-only delegation']
    for key in ('preproduction_plan','asset_registry'):
        e+=verify_record(packet.get(key),root)
    if e: return e
    try:
        plan=read_json(root/packet['preproduction_plan']['path'])
        registry=read_json(root/packet['asset_registry']['path'])
        actual=bind_task(plan,task.get('plan_task_id'),registry,root)
        if actual['request']!=task.get('request'): e.append('runtime request exceeds brain-authored recipe')
        if packet.get('episode_id') not in plan.get('episode_ids',[]): e.append('runtime episode outside upfront scope')
        if packet.get('brain_media_review_performed') is not False: e.append('cannot attribute runtime media review to upfront brain')
        declared=next(t for t in group(plan,'task') if t['task_id']==task['plan_task_id'])
        if declared.get('episode_id') not in (None,packet['episode_id']): e.append('task belongs to another episode')
    except (KeyError,ValueError,TypeError,StopIteration,OSError) as ex: e.append('delegation: '+str(ex))
    return e


def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    a=sub.add_parser('prepare');a.add_argument('--request',type=Path,required=True);a.add_argument('--out',type=Path,required=True)
    a=sub.add_parser('assemble');a.add_argument('--request',type=Path,required=True);a.add_argument('--parts',type=Path,nargs='+',required=True);a.add_argument('--out',type=Path,required=True)
    a=sub.add_parser('validate');a.add_argument('--plan',type=Path,required=True)
    for command in ('bind','export-h3'):
        a=sub.add_parser(command);a.add_argument('--plan',type=Path,required=True);a.add_argument('--registry',type=Path,required=True);a.add_argument('--root',type=Path,required=True);a.add_argument('--task',required=True);a.add_argument('--out',type=Path,required=True)
    args=p.parse_args()
    try:
        if args.command=='prepare': result=prepare(read_json(args.request))
        elif args.command=='assemble': result=assemble([read_json(x) for x in args.parts],read_json(args.request))
        elif args.command in {'bind','export-h3'}:
            result=bind_task(read_json(args.plan),args.task,read_json(args.registry),args.root.resolve(strict=True))
            if args.command=='export-h3':
                payload=native_payload(result['request'],args.root)
                result.update(endpoint='/api/v1/generate',native_payload=payload,native_request_sha256=digest(payload),production_started=False)
        else:
            errors=plan_errors(read_json(args.plan));print(json.dumps({'status':'BLOCKED' if errors else 'PLAN_COMPLETE','errors':errors,'media_approved':False},ensure_ascii=False));return 2 if errors else 0
        if hasattr(args,'out'):
            args.out.parent.mkdir(parents=True,exist_ok=True)
            with args.out.open('x',encoding='utf-8') as f: json.dump(result,f,ensure_ascii=False,indent=2,allow_nan=False)
        print(json.dumps({'status':result.get('status','WRITTEN'),'production_started':False,'output':str(args.out)},ensure_ascii=False))
        return 0
    except (OSError,ValueError,TypeError,KeyError) as ex:
        print(json.dumps({'status':'BLOCKED','error':str(ex),'production_started':False},ensure_ascii=False));return 2

if __name__=='__main__': raise SystemExit(main())
