#!/usr/bin/env python3
"""Local execution policy helpers. No generation, remote API, shell, or upload.

A plan is NOT a claim on hardware. SlotPool only coordinates one Python process.
A reading receipt proves supplied bytes/version, not comprehension or honesty.
Trusted orchestration must bind actor identity, input facts and real approvals.
"""
from __future__ import annotations
import argparse
from copy import deepcopy
import hashlib
import json
import math
import os
from pathlib import Path
import re
import threading
from typing import Any

WORKER_ACTIONS = {
    'writer': {'read_scoped', 'write_draft', 'propose_task'},
    'director': {'read_scoped', 'write_draft', 'propose_task'},
    'prompter': {'read_scoped', 'write_draft', 'propose_task'},
    'reviewer': {'read_scoped', 'write_review'},
    'blind_viewer': {'read_assigned_media', 'write_retelling'},
}
COORDINATOR_ACTIONS = {'read_scoped', 'write_draft', 'write_review', 'propose_task',
    'plan_dispatch', 'submit_generation', 'query_task', 'retrieve_result',
    'cancel_task', 'publish_asset', 'record_lesson', 'deliver', 'publish_external'}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def digest(value: Any) -> str:
    return sha(json.dumps(value, sort_keys=True, ensure_ascii=False,
               separators=(',', ':'), allow_nan=False).encode())


def positive_int(x: Any) -> bool:
    return type(x) is int and x > 0


def authorize(role: str, action: str) -> bool:
    """role must come from the trusted host, never a subagent's request body."""
    allowed = COORDINATOR_ACTIONS if role == 'coordinator' else WORKER_ACTIONS.get(role, set())
    return action in allowed


def verify_model_route(role: str, route: dict) -> list[str]:
    errors = []
    if role not in WORKER_ACTIONS or not isinstance(route, dict):
        return ['unknown role or route']
    if not isinstance(route.get('model_id'), str) or not route['model_id'].strip():
        errors.append('actual model_id not bound')
    if route.get('verified') is not True:
        errors.append('actual route not verified')
    modalities = route.get('required_modalities', [])
    available = route.get('verified_modalities', [])
    if not isinstance(modalities, list) or not isinstance(available, list) or any(x not in available for x in modalities):
        errors.append('required modalities not verified')
    if role == 'blind_viewer' and route.get('context_isolated') is not True:
        errors.append('blind context must be isolated')
    return errors


def pool_snapshot(pools: dict) -> dict:
    if not isinstance(pools, dict) or not pools:
        raise ValueError('nonempty actual resource pools required')
    free = {}
    for key, value in pools.items():
        if not isinstance(key, str) or not key or not isinstance(value, dict):
            raise ValueError('invalid resource pool')
        if value.get('verified') is not True or not positive_int(value.get('capacity')):
            raise ValueError('capacity unverified: ' + key)
        occupied = value.get('occupied')
        if type(occupied) is not int or occupied < 0:
            raise ValueError('occupied count required: ' + key)
        if value.get('snapshot_reconciled') is not True:
            raise ValueError('inflight/unknown tasks not reconciled: ' + key)
        # Overfull after a capacity reduction means no new dispatch, not negative permits.
        free[key] = max(0, value['capacity'] - occupied)
    return free


def demands_for(task: dict, pools: dict) -> dict:
    demands = task.get('resources')
    if not isinstance(demands, dict) or not demands:
        raise ValueError('nonempty resource demands required')
    if any(k not in pools or not positive_int(v) for k, v in demands.items()):
        raise ValueError('unknown pool or invalid resource demand')
    return demands


def plan_dispatch(data: dict) -> dict:
    """Plan READY, approved tasks within the active_episode call scope.

    Pool capacities are this call's authorized resource budget, not a requirement
    to use all available hardware. Project policy determines that budget.
    Greedy priority/aging order, not a claimed globally optimal packing solution.
    Returned plans are snapshots; trusted dispatch must recheck and atomically claim.
    """
    if not isinstance(data, dict) or data.get('schema_version') != 'dispatch-1':
        raise ValueError('dispatch-1 required')
    if not isinstance(data.get('active_episode'), str) or not data['active_episode']:
        raise ValueError('active_episode required')
    free = pool_snapshot(data.get('pools'))
    tasks = data.get('tasks')
    if not isinstance(tasks, list):
        raise ValueError('tasks array required')
    seen, selected, blocked, waiting = set(), [], {}, []
    active = data['active_episode']
    existing_writers = data.get('occupied_outputs', [])
    if not isinstance(existing_writers, list) or any(not isinstance(x, str) for x in existing_writers):
        raise ValueError('occupied_outputs must be strings')
    outputs = set(existing_writers)
    for t in tasks:
        if not isinstance(t, dict) or not isinstance(t.get('job_id'), str) or not t['job_id'] or t['job_id'] in seen:
            raise ValueError('unique job IDs required')
        seen.add(t['job_id'])
        if type(t.get('priority')) is not int or type(t.get('queue_order')) is not int:
            raise ValueError('integer priority and queue_order required')
        demands_for(t, free)
    order = sorted(tasks, key=lambda t: (-t['priority'], t['queue_order'], t['job_id']))
    if data.get('scheduling_objective') == 'critical_path':
        from workflow_support import critical_path_order
        ranks = {job: i for i, job in enumerate(critical_path_order(tasks))}
        order = sorted(tasks, key=lambda t: ranks[t['job_id']])
    elif data.get('scheduling_objective') not in (None, 'priority_fifo'):
        raise ValueError('unsupported scheduling objective')
    for task in order:
        job = task['job_id']; reasons = []
        if task.get('episode_id') != active:
            reasons.append('outside active_episode scope')
        if task.get('state') != 'READY':
            reasons.append('not READY; existing/unknown submissions must be reconciled, not resubmitted')
        for key in ('dependencies_accepted', 'gates_passed', 'reading_acknowledged',
                    'authorization_verified', 'permission_preflight_passed', 'rate_token_available'):
            if task.get(key) is not True:
                reasons.append(key)
        if not authorize(task.get('actor_role', ''), 'submit_generation'):
            reasons.append('only trusted coordinator may dispatch generation')
        out = task.get('output_key')
        if not isinstance(out, str) or not out:
            reasons.append('unique output_key required')
        elif out in outputs:
            reasons.append('output writer already reserved')
        if reasons:
            blocked[job] = reasons; continue
        demand = task['resources']
        if any(free[k] < count for k, count in demand.items()):
            waiting.append(job); continue
        selected.append(job); outputs.add(out)
        for k, count in demand.items():
            free[k] -= count
    return {'status': 'PLAN_ONLY', 'active_episode': active,
            'dispatch_job_ids': selected, 'resource_wait_job_ids': waiting,
            'blocked_jobs': blocked, 'remaining_permits': free,
            'input_snapshot_sha256': digest(data), 'executed': False,
            'note': 'No atomic remote claim or submission; pass selected jobs through job_ledger and actual adapter.'}


class SlotPool:
    """One-process all-or-nothing permit broker. Not persistent or distributed."""
    def __init__(self, capacities: dict[str, int]):
        if not capacities or any(not isinstance(k, str) or not k or not positive_int(v) for k, v in capacities.items()):
            raise ValueError('positive capacities required')
        self._capacities = dict(capacities)
        self._jobs: dict[str, dict[str, int]] = {}
        self._lock = threading.Lock()

    def acquire(self, job_id: str, demand: dict[str, int]) -> bool:
        if not isinstance(job_id, str) or not job_id:
            raise ValueError('job_id required')
        demand = demands_for({'resources': demand}, self._capacities)
        with self._lock:
            if job_id in self._jobs:
                return False
            used = {k: sum(d.get(k, 0) for d in self._jobs.values()) for k in self._capacities}
            if any(used[k] + v > self._capacities[k] for k, v in demand.items()):
                return False
            self._jobs[job_id] = dict(demand)
            return True

    def release(self, job_id: str, *, terminal_verified: bool) -> bool:
        # For remote jobs, local timeout is not terminal evidence.
        if terminal_verified is not True:
            return False
        with self._lock:
            return self._jobs.pop(job_id, None) is not None

    def snapshot(self) -> dict:
        with self._lock:
            return {'capacities': dict(self._capacities), 'jobs': deepcopy(self._jobs)}


def episode_ready(record: dict, root: Path) -> list[str]:
    """Check files/declared completion prerequisites, not subjective media quality."""
    root = root.resolve(strict=True)
    errors = []
    if not isinstance(record, dict) or record.get('status') != 'EPISODE_DELIVERABLE':
        return ['episode not deliverable']
    for key in ('final_gate_accepted', 'state_archived', 'lessons_recorded', 'costs_reconciled'):
        if record.get(key) is not True:
            errors.append(key + ' missing')
    if record.get('unknown_submission_ids') != []:
        errors.append('unknown submissions remain')
    for key in ('final_artifact', 'final_review'):
        item = record.get(key)
        if not isinstance(item, dict):
            errors.append('missing ' + key); continue
        raw = item.get('path')
        if not isinstance(raw, str) or not raw or Path(raw).is_absolute() or '..' in Path(raw).parts or '\\' in raw:
            errors.append('unsafe ' + key); continue
        p = root / raw
        if not p.is_file() or not p.resolve().is_relative_to(root) or p.is_symlink() or sha(p.read_bytes()) != item.get('sha256'):
            errors.append('missing/stale ' + key)
    if not errors:
        review = json.loads((root / record['final_review']['path']).read_text())
        if review.get('status') != 'ACCEPTED' or review.get('subject_sha256') != record['final_artifact']['sha256']:
            errors.append('final review does not bind accepted final file')
    if record.get('mobile_required') is True:
        m = record.get('mobile_artifact')
        if not isinstance(m, dict) or not isinstance(m.get('path'), str):
            errors.append('mobile deliverable missing')
        else:
            raw = m['path']; p = root / raw
            if (not raw or Path(raw).is_absolute() or '..' in Path(raw).parts or '\\' in raw
                    or not p.is_file() or p.is_symlink() or not p.resolve().is_relative_to(root)):
                errors.append('unsafe or missing mobile file')
            elif (sha(p.read_bytes()) != m.get('sha256') or not positive_int(record.get('mobile_max_bytes'))
                    or p.stat().st_size > record['mobile_max_bytes'] or record.get('mobile_review_passed') is not True):
                errors.append('mobile file stale/oversize/unreviewed')
    return errors


def parse_sections(text: str) -> dict[str, dict]:
    """Only actual standalone anchors outside fenced resources/code count."""
    lines = text.splitlines(keepends=True)
    anchors = []; fence = None
    for number, line in enumerate(lines):
        stripped = line.rstrip('\r\n')
        f = re.match(r'^(`{3,}|~{3,})', stripped)
        if fence:
            if stripped == fence:
                fence = None
            continue
        if f:
            fence = f[1]; continue
        m = re.fullmatch(r'<a id="([a-zA-Z0-9_-]+)"></a>', stripped)
        if m:
            if any(a[0] == m[1] for a in anchors):
                raise ValueError('duplicate section anchor: ' + m[1])
            anchors.append((m[1], number))
    out = {}
    for idx, (anchor, start) in enumerate(anchors):
        end = anchors[idx+1][1] if idx+1 < len(anchors) else len(lines)
        body = ''.join(lines[start:end])
        out[anchor] = {'section_id': anchor, 'start_line': start+1,
                      'end_line': end, 'sha256': sha(body.encode()), 'text': body}
    return out


def stage_anchors(routes: dict, stage: str) -> list[str]:
    if not isinstance(routes, dict) or routes.get('schema_version') != 'reading-map-1':
        raise ValueError('reading-map-1 required')
    required = routes.get('stages', {}).get(stage)
    if not isinstance(required, list) or not required or any(not isinstance(x, str) or not x for x in required):
        raise ValueError('unknown/empty stage route')
    if len(required) != len(set(required)):
        raise ValueError('duplicate required anchors')
    if stage == 'blind' and required != ['runtime-blind-brief']:
        raise ValueError('blind viewer must receive only the isolated brief')
    return required


def reading_pack(skill: Path, routes: dict, stage: str, actor_id: str, scope: str) -> dict:
    if not actor_id.strip() or not scope.strip():
        raise ValueError('actor and task scope required')
    raw = skill.read_bytes(); sections = parse_sections(raw.decode('utf-8'))
    required = stage_anchors(routes, stage)
    if any(x not in sections for x in required):
        raise ValueError('required chapter absent from actual skill')
    records = [{k: v for k, v in sections[x].items() if k != 'text'} for x in required]
    receipt = {'schema_version': 'reading-receipt-1', 'status': 'ISSUED_NOT_ACKNOWLEDGED',
        'actor_id': actor_id, 'stage': stage, 'task_scope': scope,
        'skill_sha256': sha(raw), 'route_sha256': digest(required),
        'sections': records, 'applied_rules': []}
    # No filename/path leaked to blind workers. The host retains this receipt.
    return {'receipt': receipt, 'instruction_text': '\n'.join(sections[x]['text'] for x in required),
        'scope': 'Bytes provided, not proof of human/model comprehension.'}


def check_reading(skill: Path, routes: dict, receipt: dict, stage: str, actor_id: str, scope: str) -> list[str]:
    expected = reading_pack(skill, routes, stage, actor_id, scope)['receipt']
    errors = []
    if not isinstance(receipt, dict):
        return ['reading receipt missing']
    for key in ('schema_version', 'actor_id', 'stage', 'task_scope', 'skill_sha256', 'route_sha256', 'sections'):
        if receipt.get(key) != expected[key]:
            errors.append('missing/stale reading field: ' + key)
    if receipt.get('status') != 'ACKNOWLEDGED':
        errors.append('actual agent acknowledgment missing')
    rules = receipt.get('applied_rules')
    if not isinstance(rules, list) or not rules or any(not isinstance(x, str) or not x.strip() for x in rules):
        errors.append('brief applicable rules not acknowledged')
    return errors


def environment_check(profile: dict, env: dict[str, str] | None = None) -> dict:
    """Only validate variable presence/format; never return endpoint/token values."""
    env = os.environ if env is None else env
    if not isinstance(profile, dict):
        return {'status': 'BLOCKED', 'blockers': ['profile object required'], 'connected': False, 'secrets_returned': False}
    errors = []
    names = profile.get('connection_env', {}) if isinstance(profile, dict) else {}
    for key in ('base_url', 'token'):
        name = names.get(key)
        if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', name):
            errors.append('environment variable name unmapped: ' + key); continue
        value = env.get(name)
        if not isinstance(value, str) or not value.strip():
            errors.append('environment variable missing: ' + key)
        elif key == 'base_url':
            from urllib.parse import urlsplit
            try:
                p = urlsplit(value)
                if p.scheme not in ('http', 'https') or not p.netloc or p.username or p.password or p.query or p.fragment:
                    errors.append('endpoint format unsafe or unsupported')
            except ValueError:
                errors.append('endpoint format invalid')
    if profile.get('unattended_permission_preflight') != 'VERIFIED':
        errors.append('noninteractive permissions not preverified')
    return {'status': 'BLOCKED' if errors else 'PREFLIGHT_RECORDS_OK',
            'blockers': errors, 'connected': False, 'secrets_returned': False,
            'note': 'No network call or OS permission test performed.'}


def mobile_plan(duration_s: float, max_bytes: int,
                audio_bps: int = 128_000, fraction: float = .90) -> dict:
    if type(duration_s) not in (int, float) or not math.isfinite(duration_s) or duration_s <= 0:
        raise ValueError('measured positive duration required')
    if not positive_int(max_bytes) or type(audio_bps) is not int or audio_bps < 0:
        raise ValueError('valid byte limit/audio bitrate required')
    if type(fraction) not in (int, float) or not math.isfinite(fraction) or not 0 < fraction < 1:
        raise ValueError('explicit reserve fraction required')
    target = int(max_bytes * fraction)
    video = int(target * 8 / duration_s) - audio_bps
    if video <= 0:
        raise ValueError('audio alone exceeds reserved mobile budget')
    return {'status': 'ESTIMATE_ONLY', 'max_bytes': max_bytes, 'target_bytes': target,
            'audio_bps': audio_bps, 'video_bps_estimate': video, 'duration_s': duration_s,
            'master_changed': False, 'encoded': False,
            'note': 'Actual output bytes and audiovisual quality must be measured; no size guarantee.'}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__); sub = p.add_subparsers(dest='cmd', required=True)
    d = sub.add_parser('plan'); d.add_argument('--input', type=Path, required=True)
    for name in ('reading-pack', 'check-reading'):
        x = sub.add_parser(name)
        for k in ('skill', 'routes'):
            x.add_argument('--'+k, type=Path, required=True)
        for k in ('stage', 'actor', 'scope'):
            x.add_argument('--'+k, required=True)
        if name == 'check-reading':
            x.add_argument('--receipt', type=Path, required=True)
    x = sub.add_parser('env-check'); x.add_argument('--profile', type=Path, required=True)
    x = sub.add_parser('authorize'); x.add_argument('--role', required=True); x.add_argument('--action', required=True)
    x = sub.add_parser('mobile-plan'); x.add_argument('--duration', type=float, required=True)
    x.add_argument('--max-bytes', type=int, required=True); x.add_argument('--audio-bps', type=int, default=128_000)
    a = p.parse_args(); code = 0
    try:
        if a.cmd == 'plan':
            result = plan_dispatch(json.loads(a.input.read_text()))
        elif a.cmd in ('reading-pack', 'check-reading'):
            routes = json.loads(a.routes.read_text())
            if a.cmd == 'reading-pack':
                result = reading_pack(a.skill, routes, a.stage, a.actor, a.scope)
            else:
                errors = check_reading(a.skill, routes, json.loads(a.receipt.read_text()), a.stage, a.actor, a.scope)
                result = {'status': 'BLOCKED' if errors else 'READING_RECORD_OK', 'blockers': errors}
                code = 2 if errors else 0
        elif a.cmd == 'env-check':
            result = environment_check(json.loads(a.profile.read_text())); code = 2 if result['blockers'] else 0
        elif a.cmd == 'authorize':
            ok = authorize(a.role, a.action); result = {'allowed': ok, 'role': a.role, 'action': a.action,
                'warning': 'Host must supply authenticated role and enforce tool/secret isolation.'}; code = 0 if ok else 2
        else:
            result = mobile_plan(a.duration, a.max_bytes, a.audio_bps)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        result = {'status': 'BLOCKED', 'error': str(exc)}; code = 2
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)); return code


if __name__ == '__main__':
    raise SystemExit(main())
