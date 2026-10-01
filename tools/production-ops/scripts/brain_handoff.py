#!/usr/bin/env python3
"""Offline v4 brain-packet/request binding; no generation, network, or authentication.

The host must restrict who can register an approved packet. A matching file/hash
proves identity, not that ChatGPT or the user really approved its contents.
"""
from __future__ import annotations
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from typing import Any

POLICY = '4.2.0'
SUPPORTED_POLICIES = {'4.0.0', '4.1.0', POLICY}
PHASE_KINDS = {'assets': {'asset_image'}, 'start_frames': {'start_frame'},
               'video': {'video'}, 'audio': {'audio'}, 'edit': {'edit'},
               'repair': {'asset_image', 'start_frame', 'video', 'audio', 'edit'}}


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
        separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()


def text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def read_json(path: Path) -> Any:
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('duplicate JSON key: ' + key)
            result[key] = value
        return result
    def constant(value):
        raise ValueError('non-finite JSON number: ' + value)
    return json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=pairs,
                      parse_constant=constant)


def verify_record(record: Any, root: Path) -> list[str]:
    root = Path(root).resolve(strict=True)
    if not isinstance(record, dict) or not text(record.get('path')):
        return ['file record missing']
    raw = record['path']
    path = Path(raw)
    if (path.is_absolute() or '\\' in raw or
            any(part in {'', '.', '..'} for part in raw.split('/'))):
        return ['unsafe file path']
    target = root / path
    if target.is_symlink() or not target.resolve().is_relative_to(root):
        return ['file path escapes project']
    if not target.is_file() or target.stat().st_size == 0:
        return ['missing/empty file: ' + raw]
    h = hashlib.sha256()
    with target.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    if h.hexdigest() != record.get('sha256'):
        return ['file hash mismatch: ' + raw]
    return []


def request_snapshot(scene: dict, shot: dict, profile: dict, prompt: str) -> dict:
    """The single excluded field is the external binding, avoiding a hash cycle."""
    frozen_shot = deepcopy(shot)
    frozen_shot.pop('brain_binding', None)
    input_mode = shot.get('video_input')
    expected_input = {'video_i2v': 'keyframe', 'video_reference': 'references'}.get(shot.get('mode'))
    if input_mode is not None and input_mode != expected_input:
        raise ValueError('video_input conflicts with shot mode')
    image_mode = shot.get('image_mode')
    expected_image = {'video_i2v': 'keyframe', 'video_reference': 'reference'}.get(shot.get('mode'))
    if image_mode is not None and image_mode != expected_image:
        raise ValueError('image_mode conflicts with shot mode')
    return {
        **({'image_mode': image_mode} if image_mode is not None else {}),
        **({key: deepcopy(shot.get(key)) for key in ('video_input', 'required_asset_ids', 'background_motion')}
           if shot.get('mode') == 'video_reference' else {'video_input': input_mode} if input_mode is not None else {}),
        'kind': {'video_i2v': 'video', 'video_reference': 'video', 'new_view': 'asset_image'}.get(shot.get('mode'), 'start_frame'),
        'shot_id': shot.get('shot_id'), 'prompt': prompt,
        'inputs': [{key: ref.get(key) for key in
                    ('asset_id', 'role', 'upload_index', 'path', 'sha256')}
                   for ref in sorted(shot.get('references', []),
                                     key=lambda item: item.get('upload_index', 0))],
        'output_spec': deepcopy(shot.get('output')),
        'mode': shot.get('mode'),
        'configuration_sha256': digest({'scene': scene, 'shot': frozen_shot,
                                       'profile': profile})}


def load_task(binding: Any, root: Path, verify=verify_record) -> tuple[dict, dict, list[str]]:
    """Return only a fully bound task; no implicit approval of missing inputs."""
    errors: list[str] = []
    if not isinstance(binding, dict) or not text(binding.get('task_id')):
        return {}, {}, ['brain: binding/task_id missing']
    record = binding.get('packet')
    errors += verify(record, root)
    if errors:
        return {}, {}, ['brain: ' + error for error in errors]
    packet = read_json(Path(root) / record['path'])
    if not isinstance(packet, dict):
        return {}, {}, ['brain: packet must be an object']
    delegated = packet.get('schema_version') == 'execution-packet-1'
    if packet.get('schema_version') not in {'brain-packet-1', 'execution-packet-1'} or packet.get('policy_version') not in SUPPORTED_POLICIES:
        errors.append('brain: unsupported packet/policy version')
    expected_owner = 'production_supervisor' if delegated else 'chatgpt_brain'
    if packet.get('status') != 'LOCKED' or packet.get('decision_owner') != expected_owner:
        errors.append('brain: packet not locked by the designated decision role')
    for key in ('packet_id', 'revision', 'episode_id'):
        if not text(packet.get(key)):
            errors.append('brain: missing ' + key)
    if packet.get('example_only') is not False:
        errors.append('brain: example/unclassified packet is not production approval')
    if packet.get('blocking_questions') != []:
        errors.append('brain: unresolved creative questions')
    errors += ['brain approval: ' + e for e in verify(packet.get('approval_evidence'), root)]
    tasks = packet.get('tasks')
    if not isinstance(tasks, list) or not tasks or any(not isinstance(t, dict) for t in tasks):
        return {}, packet, errors + ['brain: nonempty task objects required']
    ids = [t.get('task_id') for t in tasks]
    if any(not text(i) for i in ids) or len(ids) != len(set(ids)):
        return {}, packet, errors + ['brain: invalid/duplicate task IDs']
    selected = [t for t in tasks if t['task_id'] == binding['task_id']]
    if len(selected) != 1:
        return {}, packet, errors + ['brain: task not in frozen packet']
    task = selected[0]
    if task.get('status') != 'READY':
        errors.append('brain: task is not READY')
    request = task.get('request')
    if not isinstance(request, dict) or not request:
        return {}, packet, errors + ['brain: exact request missing']
    kind = request.get('kind')
    if kind not in PHASE_KINDS.get(packet.get('phase'), set()):
        errors.append('brain: request kind does not match frozen phase')
    if task.get('request_sha256') != digest(request):
        errors.append('brain: exact request digest mismatch')
    if kind != 'edit' and not text(request.get('prompt')):
        errors.append('brain: final prompt missing')
    inputs = request.get('inputs')
    reviews = packet.get('reviewed_inputs')
    if not isinstance(inputs, list) or not isinstance(reviews, list):
        return {}, packet, errors + ['brain: actual input/review arrays required']
    for item in inputs + reviews:
        errors += ['brain input: ' + e for e in verify(item, root)]
    reviewed = {(r.get('path'), r.get('sha256')) for r in reviews if isinstance(r, dict)}
    if kind in {'start_frame', 'video'} and not inputs:
        errors.append('brain: populated start/reference inputs required')
    if kind in {'asset_image', 'start_frame', 'video'}:
        for item in inputs:
            if isinstance(item, dict) and (item.get('path'), item.get('sha256')) not in reviewed:
                errors.append('brain: actual image/reference has no bound review')
    if kind in {'start_frame', 'video'}:
        errors += ['brain fidelity: ' + e for e in verify(task.get('fidelity_contract'), root)]
    if packet.get('policy_version') in {'4.1.0', '4.2.0'} and kind in {'start_frame', 'video', 'edit'}:
        errors += ['brain sequence: ' + e for e in verify(task.get('continuity_plan'), root)]
    if delegated:
        if packet.get('policy_version') != '4.2.0':
            errors.append('delegation cannot downgrade current media quality policy')
        from preproduction import delegated_packet_errors
        errors += delegated_packet_errors(packet, task, root)
    if packet.get('policy_version') == '4.2.0':
        from prompt_contract import semantic_review_errors
        errors += semantic_review_errors(task, root)
    return ({} if errors else task), packet, errors


def check_request(binding: Any, actual: dict, root: Path, verify=verify_record) -> dict:
    task, packet, errors = load_task(binding, root, verify)
    if task and task['request'] != actual:
        errors.append('brain: actual request differs from frozen brain request')
    return {'status': 'INPUT_READY' if not errors else 'BLOCKED',
            'errors': errors, 'packet_id': packet.get('packet_id'),
            'executed': False, 'authority_authenticated': False,
            'media_quality_verified': False}


def check_compiled(scene: dict, shot: dict, profile: dict, prompt: str,
                   root: Path | None) -> list[str]:
    if root is None:
        return ['brain: project root required']
    task, packet, errors = load_task(shot.get('brain_binding'), root)
    if not task:
        return errors
    expected = request_snapshot(scene, shot, profile, prompt)
    if task['request'] != expected:
        errors.append('brain: compiled prompt/inputs/configuration changed after freeze')
    if packet.get('episode_id') != shot.get('episode_id'):
        errors.append('brain: episode mismatch')
    if task.get('fidelity_contract') != shot.get('fidelity_contract'):
        errors.append('brain: fidelity contract differs from brain-approved contract')
    if shot.get('policy_version') != packet.get('policy_version'):
        errors.append('brain: shot/packet policy version differs')
    if shot.get('policy_version') in {'4.1.0', '4.2.0'} and task.get('continuity_plan') != shot.get('continuity_plan'):
        errors.append('brain: sequence plan differs from brain-approved plan')
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binding', type=Path, required=True)
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--root', type=Path, required=True)
    args = parser.parse_args()
    try:
        result = check_request(read_json(args.binding), read_json(args.request), args.root)
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
        result = {'status': 'BLOCKED', 'errors': [str(exc)], 'executed': False}
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return 0 if result['status'] == 'INPUT_READY' else 2


if __name__ == '__main__':
    raise SystemExit(main())
