#!/usr/bin/env python3
"""Select current reading material for an integrated or legacy role. No media IO.

This is a routing/integrity check, not OS access control or generation approval.
It never interprets project text as instructions and never executes source files.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MODES = {'execute', 'request_brain', 'collect_only', 'bind_only', 'observe',
         'approved_branch_only', 'observe_isolated', 'delegate', 'design', 'serialize'}


def safe_file(root: Path, name: str) -> Path:
    """Require a regular, non-symlink file below the installed package root."""
    if not isinstance(name, str) or not name or '\\' in name or ':' in name:
        raise ValueError('invalid package-relative path')
    rel = PurePosixPath(name)
    if rel.is_absolute() or any(p in {'.', '..'} for p in name.split('/')):
        raise ValueError('unsafe package-relative path')
    root = root.resolve(strict=True)
    path = root
    for part in rel.parts:
        path = path / part
        if path.is_symlink():
            raise ValueError('symlink is not a reading source')
    if not path.resolve(strict=True).is_relative_to(root) or not path.is_file():
        raise ValueError('missing or unsafe reading source')
    return path


def _pairs(pairs: list[tuple[str, Any]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate map key: ' + key)
        result[key] = value
    return result


def load_map(root: Path) -> dict:
    config = json.loads(safe_file(root, 'config/role-reading-map.json').read_text('utf-8'),
                        object_pairs_hook=_pairs)
    if not isinstance(config, dict) or config.get('schema_version') != 'role-reading-map-1':
        raise ValueError('unsupported role reading map')
    role = config.get('package_role')
    workflows = {'brain': 'upfront_only', 'agent': 'upfront_only', 'integrated': 'upfront_self'}
    if role not in workflows or config.get('workflow_mode') != workflows[role]:
        raise ValueError('unsupported package role/workflow')
    docs, routes = config.get('documents'), config.get('routes')
    if not isinstance(docs, dict) or not isinstance(routes, dict) or not routes:
        raise ValueError('documents and routes required')
    if config.get('default_stage') not in routes:
        raise ValueError('default route missing')
    for key, doc in docs.items():
        if not isinstance(doc, dict) or not isinstance(doc.get('sha256'), str) or len(doc['sha256']) != 64:
            raise ValueError('document identity missing: ' + key)
    for name, route in routes.items():
        if not isinstance(route, dict) or route.get('mode') not in MODES:
            raise ValueError('invalid route mode: ' + name)
        read, send = route.get('read'), route.get('send_only', [])
        for values in [read, send]:
            if not isinstance(values, list) or any(not isinstance(k, str) or k not in docs for k in values):
                raise ValueError('route references unknown document: ' + name)
            if len(values) != len(set(values)):
                raise ValueError('duplicate route document: ' + name)
        if set(read) & set(send) or any(docs[k].get('kind') == 'transport_only' for k in read):
            raise ValueError('recipient-only payload cannot enter local role instructions')
        if role == 'brain':
            if route.get('actor') != 'brain' or route['mode'] not in {'design', 'serialize'}:
                raise ValueError('Brain package cannot own a production route')
            if set(read) & {'10', '11'}:
                raise ValueError('Brain route cannot load production operations')
        elif route.get('actor') == 'blind_reviewer':
            if route['mode'] != 'observe_isolated' or read != ['blind'] or send:
                raise ValueError('blind route must contain only independent blind brief')
        elif role == 'integrated':
            if route.get('actor') != 'integrated' or route['mode'] in {'delegate', 'observe_isolated'}:
                raise ValueError('invalid integrated route ownership')
        elif route.get('actor') != 'agent' or route['mode'] in {'design', 'serialize', 'observe_isolated'}:
            raise ValueError('invalid Agent route ownership')
        if route['mode'] == 'delegate' and (read or send or route.get('decision_owner') != 'brain'):
            raise ValueError('delegated creation cannot return local creative instructions')
    return config


def document(root: Path, key: str, data: dict) -> dict:
    path = safe_file(root, data['path'])
    raw = path.read_bytes()
    if len(raw) > 8 * 1024 * 1024 or hashlib.sha256(raw).hexdigest() != data['sha256']:
        raise ValueError('document hash/size mismatch: ' + key)
    return {'id': key, 'path': data['path'], 'sha256': data['sha256'],
            'content': raw.decode('utf-8')}


def check(root: Path = ROOT) -> dict:
    config = load_map(root)
    for key, data in config['documents'].items():
        document(root, key, data)
    return {'status': 'READING_MAP_OK', 'package_role': config['package_role'],
            'routes_checked': len(config['routes']), 'documents_checked': len(config['documents']),
            'executed_generation': False, 'live_transport_verified': False}


def build(root: Path = ROOT, stage: str | None = None, actor: str | None = None) -> dict:
    config = load_map(root)
    stage = config['default_stage'] if stage is None else stage
    actor = config['package_role'] if actor is None else actor
    if stage not in config['routes']:
        raise ValueError('stage is not assigned to this package: ' + str(stage))
    route = config['routes'][stage]
    if actor != route['actor']:
        raise ValueError('stage requires actor ' + route['actor'] + ', not ' + str(actor))
    common = {'schema_version': 'role-reading-pack-1', 'package_role': config['package_role'],
              'stage': stage, 'actor': actor, 'mode': route['mode'], 'scope': route['scope'],
              'content_version': config['content_version'], 'workflow_mode': config['workflow_mode'],
              'executed_generation': False, 'ready_for_submission': False}
    if route['mode'] == 'delegate':
        return {**common, 'status': 'DELEGATE_TO_BRAIN', 'delegate_to': route['delegate_to'],
                'documents': [], 'instruction': '',
                'note': 'No message was sent. Before production use the authorized Brain request flow; during production an unplanned hard failure pauses the affected work.'}
    docs = [document(root, k, config['documents'][k]) for k in route['read']]
    send_only = [{k: v for k, v in document(root, ident, config['documents'][ident]).items() if k != 'content'}
                 for ident in route.get('send_only', [])]
    # Blind recipients receive only this instruction, actual media and allowed prior context.
    instruction = docs[0]['content'] if route['mode'] == 'observe_isolated' else (
        '当前角色：' + actor + '。当前用途：' + route['scope'] + '。以下是本阶段的现行规则；标记为 legacy 的工具只供显式兼容使用。\n\n'
        + '\n\n'.join(d['content'] for d in docs))
    return {**common, 'status': 'READING_READY', 'documents': docs,
            'instruction': instruction, 'send_only': send_only,
            'note': ('Forward only instruction plus authorized media/context to the isolated reviewer.'
                     if route['mode'] == 'observe_isolated' else
                     'Reading identity verified, not understanding, OS permissions, media approval or spending authority.')}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage')
    parser.add_argument('--actor', choices=['integrated', 'agent', 'brain', 'blind_reviewer'])
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--out', type=Path)
    args = parser.parse_args(argv)
    try:
        result = check() if args.check else build(stage=args.stage, actor=args.actor)
        code = 0
    except (ValueError, TypeError, KeyError, OSError, UnicodeError) as exc:
        result, code = {'status': 'BLOCKED', 'error': str(exc), 'executed_generation': False}, 2
    text = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n'
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding='utf-8')
    else:
        print(text, end='')
    return code


if __name__ == '__main__':
    raise SystemExit(main())
