#!/usr/bin/env python3
"""Offline reference asset contracts and handoff checks. No generation or visual AI.

Python 3.10+. Pillow is needed only for real image checks. Evidence checks establish
file/version integrity, NOT that a human or VLM observation is true.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import sys
import warnings
from pathlib import Path
from typing import Any

KINDS = {
    'character': {'identity', 'costume'}, 'costume': {'costume'},
    'scene': {'scene_base'}, 'prop': {'prop'}, 'layout': {'layout'}, 'mask': {'mask'}
}
BASE_CHECKS = {'technical', 'spec_match', 'reference_clarity'}
EXTRA_CHECKS = {
    'character': {'identity', 'anatomy', 'use_test'},
    'costume': {'costume_design', 'anatomy', 'use_test'},
    'scene': {'layout', 'camera', 'empty_scene', 'use_test'},
    'prop': {'prop_geometry', 'use_test'},
    'layout': {'spatial_alignment'}, 'mask': {'spatial_alignment'}
}
ASSET_FIELDS = ('asset_id', 'entity_id', 'kind', 'version', 'view_id', 'state_id',
                'scene_context', 'format', 'canonical_parent', 'dependencies', 'allowed_roles', 'spec')
CTX_FIELDS = ('scene_id', 'scene_version', 'view_id', 'state_id')
HASH = re.compile(r'^[0-9a-f]{64}$')


def nonempty(x: Any) -> bool:
    return isinstance(x, str) and bool(x.strip())


def string_list(x: Any) -> bool:
    return isinstance(x, list) and all(nonempty(y) for y in x)


def positive_int(x: Any) -> bool:
    return type(x) is int and x > 0


def digest_value(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()


def file_digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def load_json(path: str | Path) -> dict:
    def pairs(items: list) -> dict:
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('Duplicate JSON key: ' + key)
            result[key] = value
        return result
    def reject(value: str) -> None:
        raise ValueError('Non-finite JSON: ' + value)
    data = json.loads(Path(path).read_text(encoding='utf-8'), object_pairs_hook=pairs,
                      parse_constant=reject)
    if not isinstance(data, dict):
        raise ValueError('Top-level JSON must be an object')
    return data


def resolve_file(root: Path, rel: Any) -> Path:
    if not nonempty(rel) or Path(rel).is_absolute():
        raise ValueError('file path must be nonempty and relative to project root')
    root = root.resolve(strict=True)
    path = (root / rel).resolve(strict=True)
    if not path.is_relative_to(root) or not path.is_file():
        raise ValueError('path escapes root or is not a regular file: ' + rel)
    return path


def verify_file(record: Any, root: Path, label: str) -> list[str]:
    if not isinstance(record, dict):
        return [label + ': missing file record']
    if not nonempty(record.get('path')) or not isinstance(record.get('sha256'), str) or not HASH.fullmatch(record['sha256']):
        return [label + ': actual path and valid sha256 required']
    try:
        if file_digest(resolve_file(root, record['path'])) != record['sha256']:
            return [label + ': file hash mismatch']
    except (OSError, ValueError) as exc:
        return [label + ': ' + str(exc)]
    return []


def spec_digest(manifest: dict, asset: dict) -> str:
    return digest_value({'project_id': manifest['project_id'], 'canon_version': manifest['canon_version'],
                         'asset': {key: asset.get(key) for key in ASSET_FIELDS}})


def asset_index(manifest: dict) -> dict[str, dict]:
    return {a['asset_id']: a for a in manifest['assets']}


def order_assets(manifest: dict) -> list[str]:
    """Stable Kahn ordering; caller validates types/IDs first."""
    index = asset_index(manifest)
    done: list[str] = []
    remaining = list(index)
    while remaining:
        ready = [key for key in remaining if set(index[key]['dependencies']).issubset(set(done))]
        if not ready:
            raise ValueError('Dependency cycle or missing dependency')
        done.extend(ready)
        remaining = [key for key in remaining if key not in ready]
    return done


def check_manifest(manifest: Any) -> list[str]:
    if not isinstance(manifest, dict):
        return ['manifest must be an object']
    errors: list[str] = []
    if manifest.get('schema_version') != '1.0':
        errors.append('schema_version must be 1.0')
    for key in ('project_id', 'canon_version'):
        if not nonempty(manifest.get(key)):
            errors.append(key + ': nonempty string required')
    assets = manifest.get('assets')
    if not isinstance(assets, list) or not assets:
        return errors + ['assets: nonempty array required']
    seen = set()
    for a in assets:
        if not isinstance(a, dict):
            errors.append('asset: object required'); continue
        label = str(a.get('asset_id', '?'))
        for key in ('asset_id', 'entity_id', 'kind', 'version', 'view_id', 'state_id'):
            if not nonempty(a.get(key)):
                errors.append(label + ': nonempty ' + key + ' required')
        aid = a.get('asset_id')
        if nonempty(aid):
            if aid in seen: errors.append(label + ': duplicate asset_id')
            seen.add(aid)
        kind = a.get('kind')
        if not isinstance(kind, str) or kind not in KINDS:
            errors.append(label + ': invalid kind')
        if a.get('status') not in ('planned', 'candidate', 'accepted', 'rejected', 'stale'):
            errors.append(label + ': invalid status')
        if a.get('format') not in ('single', 'diagram', 'contact_sheet'):
            errors.append(label + ': invalid format')
        deps = a.get('dependencies')
        if not string_list(deps) or len(set(deps)) != len(deps):
            errors.append(label + ': dependencies must be unique string array')
        elif aid in deps:
            errors.append(label + ': self-dependency')
        parent = a.get('canonical_parent')
        if parent is not None and (not nonempty(parent) or not isinstance(deps, list) or parent not in deps):
            errors.append(label + ': canonical_parent must be a direct dependency or null')
        roles = a.get('allowed_roles')
        if not string_list(roles) or not roles or len(set(roles)) != len(roles):
            errors.append(label + ': allowed_roles must be nonempty unique string array')
        elif isinstance(kind, str) and kind in KINDS and not set(roles).issubset(KINDS[kind]):
            errors.append(label + ': role incompatible with asset kind')
        ctx = a.get('scene_context')
        if kind == 'scene':
            if not isinstance(ctx, dict) or any(not nonempty(ctx.get(k)) for k in CTX_FIELDS):
                errors.append(label + ': scene_context required')
            elif ctx['view_id'] != a.get('view_id') or ctx['state_id'] != a.get('state_id'):
                errors.append(label + ': scene context conflicts with asset view/state')
        elif ctx is not None and not isinstance(ctx, dict):
            errors.append(label + ': scene_context must be null or object')
        spec = a.get('spec')
        if not isinstance(spec, dict):
            errors.append(label + ': spec required'); continue
        for key in ('subject', 'view'):
            if not nonempty(spec.get(key)): errors.append(label + ': spec.' + key + ' required')
        for key in ('width', 'height'):
            if not positive_int(spec.get(key)): errors.append(label + ': positive integer ' + key + ' required')
        if type(spec.get('requires_transparency')) is not bool:
            errors.append(label + ': requires_transparency must be boolean')
        for key in ('immutable', 'critical_unknowns'):
            if not string_list(spec.get(key)): errors.append(label + ': spec.' + key + ' must be string array')
        if not spec.get('immutable'): errors.append(label + ': immutable requirements cannot be empty')
        for key in ('file', 'review'):
            if not isinstance(a.get(key), dict): errors.append(label + ': ' + key + ' must be object')
    for a in assets:
        if isinstance(a, dict) and string_list(a.get('dependencies')):
            for dep in a['dependencies']:
                if dep not in seen: errors.append(str(a.get('asset_id')) + ': missing dependency ' + dep)
    if errors:
        return errors
    try:
        ordered = order_assets(manifest)
    except ValueError as exc:
        return [str(exc)]

    index = asset_index(manifest)
    scene_roots: dict[str, str] = {}
    roots_by_scene: dict[tuple[str, str], set[str]] = {}
    for aid in ordered:
        asset = index[aid]
        if asset['kind'] != 'scene':
            continue
        context = asset['scene_context']
        scene = (context['scene_id'], context['scene_version'])
        parent_id = asset.get('canonical_parent')
        root_id = aid
        if parent_id is not None:
            parent = index[parent_id]
            parent_context = parent.get('scene_context')
            if (parent['kind'] not in ('scene', 'layout')
                    or not isinstance(parent_context, dict)
                    or (parent_context.get('scene_id'), parent_context.get('scene_version')) != scene):
                errors.append(aid + ': canonical_parent must be a scene or layout asset with matching scene_context')
                continue
            if parent['kind'] == 'layout':
                root_id = parent_id
            else:
                root_id = scene_roots.get(parent_id)
                if root_id is None:
                    continue  # An invalid ancestor already blocks this manifest.
                if parent['view_id'] != asset['view_id'] and parent_id != root_id:
                    errors.append(aid + ': cross-view canonical_parent must be the shared canonical root')
        scene_roots[aid] = root_id
        roots_by_scene.setdefault(scene, set()).add(root_id)
    for (scene_id, scene_version), roots in roots_by_scene.items():
        if len(roots) > 1:
            errors.append(f'{scene_id}@{scene_version}: scene assets must share one canonical root; found '
                          + ', '.join(sorted(roots)))
    return errors


def inspect_image(path: Path) -> dict:
    try:
        from PIL import Image
    except ImportError as exc:
        raise ValueError('Pillow is required for production image checks; install separately') from exc
    with warnings.catch_warnings():
        warnings.simplefilter('error', Image.DecompressionBombWarning)
        try:
            opened = Image.open(path)
        except Image.DecompressionBombError as exc:
            raise ValueError('Image exceeds safe decoding size') from exc
        with opened as im:
            im.load()
            alpha_present = 'A' in im.getbands() or 'transparency' in im.info
            alpha = im.convert('RGBA').getchannel('A')
            lo, hi = alpha.getextrema()
            return {'width': im.width, 'height': im.height, 'mode': im.mode, 'format': im.format,
                    'alpha_present': alpha_present, 'alpha_min': lo, 'alpha_max': hi,
                    'orientation': im.getexif().get(274, 1), 'frames': getattr(im, 'n_frames', 1)}


def required_checks(asset: dict) -> set[str]:
    return BASE_CHECKS | EXTRA_CHECKS[asset['kind']]


def _check_asset(manifest: dict, a: dict, root: Path) -> list[str]:
    name = a['asset_id']
    errors: list[str] = []
    if a['status'] != 'accepted': errors.append(name + ': not accepted')
    if a['format'] == 'contact_sheet': errors.append(name + ': contact sheet is review-only')
    if a['format'] != 'single' and a['kind'] not in ('layout', 'mask'):
        errors.append(name + ': production subject/base must be single image')
    if a['spec']['critical_unknowns']: errors.append(name + ': unresolved critical geometry/design')
    fe = verify_file(a['file'], root, name)
    errors += fe
    if not fe:
        try:
            meta = inspect_image(resolve_file(root, a['file']['path']))
            if (meta['width'], meta['height']) != (a['spec']['width'], a['spec']['height']):
                errors.append(name + ': decoded dimensions do not match spec')
            if meta['orientation'] not in (None, 1): errors.append(name + ': unnormalized EXIF orientation')
            if meta['frames'] != 1: errors.append(name + ': reference must be a single static image')
            if a['spec']['requires_transparency'] and (not meta['alpha_present'] or meta['alpha_min'] == 255 or meta['alpha_max'] == 0):
                errors.append(name + ': requires nonempty actual transparency, not opaque/empty image')
        except (OSError, ValueError, Warning) as exc:
            errors.append(name + ': image decode/check failed: ' + str(exc))
    rev = a['review']
    if rev.get('decision') != 'PASS' or not nonempty(rev.get('reviewer')):
        errors.append(name + ': PASS review with reviewer required')
    if rev.get('spec_sha256') != spec_digest(manifest, a): errors.append(name + ': stale specification review')
    if rev.get('file_sha256') != a['file'].get('sha256'): errors.append(name + ': stale image review')
    snapshots = rev.get('dependency_snapshots')
    idx = asset_index(manifest)
    expected = {dep: {'file_sha256': idx[dep]['file'].get('sha256'),
                      'spec_sha256': spec_digest(manifest, idx[dep])} for dep in a['dependencies']}
    if snapshots != expected: errors.append(name + ': stale dependency snapshots')
    checks = rev.get('checks')
    if not isinstance(checks, list): return errors + [name + ': checks array required']
    observed = set()
    for item in checks:
        if not isinstance(item, dict) or not nonempty(item.get('name')):
            errors.append(name + ': malformed check'); continue
        check = item['name']
        if check in observed: errors.append(name + ': duplicate check ' + check)
        observed.add(check)
        if item.get('result') != 'PASS': errors.append(name + ': check not PASS: ' + check)
        if not nonempty(item.get('observation')): errors.append(name + ': missing observation: ' + check)
        errors += verify_file(item.get('evidence'), root, name + ' evidence ' + check)
    if not required_checks(a).issubset(observed):
        errors.append(name + ': missing checks ' + ','.join(sorted(required_checks(a) - observed)))
    if rev.get('open_issues') != []: errors.append(name + ': unresolved issues or missing open_issues')
    return errors


def gate_assets(manifest: dict, asset_ids: list[str], root: Path) -> list[str]:
    errors = check_manifest(manifest)
    if errors: return errors
    idx = asset_index(manifest)
    if not asset_ids: return ['no selected asset IDs']
    for key in asset_ids:
        if key not in idx: errors.append('unknown asset: ' + str(key))
    if errors: return errors
    required = set(asset_ids)
    todo = list(asset_ids)
    while todo:
        for dep in idx[todo.pop()]['dependencies']:
            if dep not in required: required.add(dep); todo.append(dep)
    for key in order_assets(manifest):
        if key in required: errors += _check_asset(manifest, idx[key], root)
    return errors


def select_references(manifest: dict, request: dict, profile: dict, root: Path) -> dict:
    errors = check_manifest(manifest)
    idx = asset_index(manifest) if not errors else {}
    if not nonempty(request.get('target_shot_id')): errors.append('target_shot_id required')
    ctx = request.get('scene_context')
    if not isinstance(ctx, dict) or any(not nonempty(ctx.get(k)) for k in CTX_FIELDS):
        errors.append('request scene_context incomplete')
    output = request.get('output')
    if not isinstance(output, dict) or any(not positive_int(output.get(k)) for k in ('width', 'height')):
        errors.append('request output width/height required')
    bindings = request.get('bindings')
    if not isinstance(bindings, list) or not bindings:
        errors.append('bindings must be nonempty array'); bindings = []
    valid: list[dict] = []
    for b in bindings:
        if not isinstance(b, dict): errors.append('binding must be object'); continue
        valid.append(b)
        if not nonempty(b.get('asset_id')) or b.get('asset_id') not in idx:
            errors.append('binding asset is unknown')
        else:
            a = idx[b['asset_id']]
            if not isinstance(b.get('role'), str) or b['role'] not in a['allowed_roles']:
                errors.append('binding role incompatible with allowed_roles')
            if b.get('role') == 'scene_base':
                if a['scene_context'] != ctx: errors.append('scene/view/state mismatch')
                if isinstance(output, dict) and (a['spec']['width'], a['spec']['height']) != (output.get('width'), output.get('height')):
                    errors.append('scene base dimensions do not match requested canvas')
        if type(b.get('primary')) is not bool: errors.append('binding primary must be boolean')
        if not nonempty(b.get('purpose')): errors.append('binding purpose required')
    ids = [b.get('asset_id') for b in valid]
    if all(nonempty(x) for x in ids) and len(set(ids)) != len(ids): errors.append('duplicate asset bindings')
    if (not valid or valid[0].get('role') != 'scene_base' or valid[0].get('primary') is not True
            or sum(b.get('primary') is True for b in valid) != 1
            or sum(b.get('role') == 'scene_base' for b in valid) != 1):
        errors.append('first input must be the unique primary scene_base')
    if profile.get('runtime_verified') is not True or not nonempty(profile.get('backend')) or not nonempty(profile.get('model_id')):
        errors.append('runtime backend/model not verified')
    errors += verify_file(profile.get('verification_evidence'), root, 'runtime evidence')
    limit = profile.get('max_reference_images')
    if not positive_int(limit) or len(valid) > limit: errors.append('reference limit unknown or exceeded')
    features = profile.get('features', {})
    if not isinstance(features, dict): features = {}
    needed = {'image_edit'}
    if len(valid) > 1: needed.add('multi_reference')
    if any(b.get('role') in ('layout', 'mask') for b in valid): needed.add('spatial_reference')
    for feature in needed:
        if features.get(feature) != 'verified': errors.append('runtime feature not verified: ' + feature)
    if not errors: errors += gate_assets(manifest, ids, root)
    refs = []
    if not errors:
        for i, b in enumerate(valid, 1):
            a = idx[b['asset_id']]
            row = {'asset_id': a['asset_id'], 'role': b['role'], 'primary': b['primary'],
                   'purpose': b['purpose'], 'upload_index': i, **a['file'], 'status': 'accepted'}
            if b['role'] == 'scene_base': row.update(a['scene_context'])
            refs.append(row)
    return {'schema_version': '1.0', 'status': 'BLOCKED' if errors else 'READY',
            'target_shot_id': request.get('target_shot_id'), 'executed': False,
            'visual_quality_verified_by_this_tool': False, 'references': refs,
            'manifest_sha256': digest_value(manifest), 'request_sha256': digest_value(request),
            'profile_sha256': digest_value(profile), 'blockers': list(dict.fromkeys(errors)),
            'notice': 'READY means file/spec/reported-review checks passed; no model executed and no visual truth proven.'}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='command', required=True)
    for name in ('check', 'plan', 'spec-digest', 'gate', 'select'):
        s = sub.add_parser(name)
        s.add_argument('--manifest', required=True)
        if name in ('spec-digest', 'gate'): s.add_argument('--asset-id', required=True)
        if name in ('gate', 'select'): s.add_argument('--root', type=Path, required=True)
        if name == 'select':
            s.add_argument('--request', required=True)
            s.add_argument('--profile', required=True)
            s.add_argument('--out', type=Path)
            s.add_argument('--overwrite', action='store_true')
    args = p.parse_args()
    try:
        m = load_json(args.manifest)
        errors = check_manifest(m)
        if errors: result = {'status': 'BLOCKED', 'blockers': errors}
        elif args.command == 'check':
            result = {'status': 'CONTRACT_OK', 'asset_count': len(m['assets']),
                      'visual_quality_verified_by_this_tool': False, 'executed': False}
        elif args.command == 'plan':
            result = {'status': 'PLANNED', 'execution_order': order_assets(m), 'executed': False}
        elif args.command == 'spec-digest':
            if args.asset_id not in asset_index(m): raise ValueError('Unknown asset ID')
            result = {'asset_id': args.asset_id, 'spec_sha256': spec_digest(m, asset_index(m)[args.asset_id])}
        elif args.command == 'gate':
            errors = gate_assets(m, [args.asset_id], args.root)
            result = {'status': 'BLOCKED' if errors else 'ASSET_READY', 'blockers': errors,
                      'visual_quality_verified_by_this_tool': False}
        else:
            result = select_references(m, load_json(args.request), load_json(args.profile), args.root)
        text = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)
        if args.command == 'select' and args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            with args.out.open('w' if args.overwrite else 'x', encoding='utf-8') as stream:
                stream.write(text + '\n')
        print(text)
        return 2 if result.get('status') == 'BLOCKED' else 0
    except (OSError, ValueError, TypeError) as exc:
        print(json.dumps({'status': 'BLOCKED', 'error': str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
