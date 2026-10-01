#!/usr/bin/env python3
"""File-bound scene continuity extension. Does not inspect pixels or infer geometry."""
from __future__ import annotations
import importlib.util
import json
from pathlib import Path
from typing import Any, Callable
from h3_reference import reference_errors


def module():
    path = Path(__file__).resolve().parents[2]/'visual-continuity-prompter/scripts/scene_continuity.py'
    spec = importlib.util.spec_from_file_location('_scene_ensemble_gate', path)
    if spec is None or spec.loader is None:
        raise ImportError('Full bundle requires scene_continuity.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_bindings(spec: dict, root: Path, verify: Callable) -> tuple[dict, list[str]]:
    errors, context = [], {}
    bindings = spec.get('ensemble_bindings')
    if not isinstance(bindings, list) or not bindings:
        return {}, ['ensemble: file bindings missing']
    ids = []
    m = module()
    for binding in bindings:
        if not isinstance(binding, dict):
            errors.append('ensemble: malformed binding'); continue
        sid = binding.get('shot_id')
        ids.append(sid)
        errs = []
        for field in ('shot_contract', 'media', 'previous_state', 'view_evidence', 'inventory_evidence'):
            errs += verify(binding.get(field), root)
        errors += ['ensemble: ' + e for e in errs]
        if errs:
            continue
        shot = json.loads((root/binding['shot_contract']['path']).read_text(encoding='utf-8'))
        if not isinstance(shot, dict) or shot.get('shot_id') != sid:
            errors.append('ensemble: shot scope mismatch'); continue
        bundle = shot.get('ensemble')
        if shot.get('ensemble_required') is not True or bundle is None:
            errors.append('ensemble: explicit enabled bundle required'); continue
        errs = m.validate_shot(shot)
        errors += errs
        if errs:
            continue
        if bundle.get('example_only') is not False:
            errors.append('ensemble: demo/unclassified bundle cannot enter production')
        if bundle['scope']['episode_id'] != spec.get('episode_id'):
            errors.append('ensemble: episode binding mismatch')
        previous = json.loads((root/binding['previous_state']['path']).read_text(encoding='utf-8'))
        if previous != bundle['previous_state']:
            errors.append('ensemble: predecessor source differs from frozen previous state')
        if spec['action'] == 'pre_video' and spec.get('video_input') == 'references':
            from preproduction import validate_registry
            # media is the frozen request JSON in this stage, never a pretend first frame.
            request = json.loads((root/binding['media']['path']).read_text(encoding='utf-8'))
            errors.extend(reference_errors(request))
            if shot.get('mode') != 'video_reference' or shot.get('video_input') != 'references':
                errors.append('ensemble: reference gate requires a reference-video shot')
            keys = ('asset_id','role','upload_index','path','sha256')
            actual = [{k:r.get(k) for k in keys} for r in request.get('inputs',[]) if isinstance(r,dict)]
            expected = [{k:r.get(k) for k in keys} for r in shot.get('references',[]) if isinstance(r,dict)]
            if actual != expected or request.get('shot_id') != sid:
                errors.append('ensemble: actual uploaded assets/order differ from shot contract')
            visible = m.visible_ids(bundle)
            entity_assets = shot.get('entity_asset_ids')
            if (not isinstance(entity_assets,dict) or set(entity_assets) != visible
                    or any(not isinstance(a,str) or a not in request.get('required_asset_ids',[]) for a in entity_assets.values())):
                errors.append('ensemble: every visible entity needs its frozen input asset mapping')
            for key in ('required_asset_ids', 'background_motion'):
                if request.get(key) != shot.get(key): errors.append('ensemble: request changed '+key)
            registry_errors = verify(binding.get('asset_registry'), root)
            errors.extend(registry_errors)
            if not registry_errors:
                registry = json.loads((root/binding['asset_registry']['path']).read_text(encoding='utf-8'))
                accepted = validate_registry(registry, root, set(request.get('required_asset_ids',[])))
                for ref in request.get('inputs',[]):
                    if ref.get('asset_id') in accepted and any(ref.get(k) != accepted[ref['asset_id']]['file'][k] for k in ('path','sha256')):
                        errors.append('ensemble: actual reference differs from accepted asset file')
        elif spec['action'] == 'pre_video':
            if shot.get('mode') == 'video_reference':
                errors.append('ensemble: reference video requires video_input=references in gate spec')
            primary = [r for r in shot.get('references', []) if r.get('primary') is True]
            if (len(primary) != 1 or primary[0].get('role') not in {'start_frame', 'previous_end'}
                    or any(primary[0].get(k) != binding['media'].get(k) for k in ('path','sha256'))):
                errors.append('ensemble: reviewed populated start frame must be actual primary video input')
        elif len(spec.get('shot_ids', [])) == 1 and binding['media'] != spec.get('subject'):
            errors.append('ensemble: reviewed video differs from actual gate subject')
        if isinstance(sid, str):
            context[sid] = {'bundle': bundle, 'media': binding['media']}
            if spec['action'] == 'pre_video' and spec.get('video_input') == 'references':
                context[sid]['request'] = request
    if ids != spec.get('shot_ids') or len(context) != len(ids):
        errors.append('ensemble: ordered shot coverage mismatch')
    return context, errors


def check_details(details: dict, context: dict, first_frame: bool) -> tuple[list[str], list[str]]:
    errors, failures = [], []
    reports = details.get('shots')
    if not isinstance(reports, list) or [r.get('shot_id') for r in reports if isinstance(r, dict)] != list(context):
        return ['ensemble: per-shot actual observations missing'], []
    m = module()
    for report in reports:
        item = context[report['shot_id']]
        if report.get('media_sha256') != item['media']['sha256']:
            errors.append('ensemble: observations refer to another media version')
        errors += m.check_observation(item['bundle'], report, first_frame)
        for window in report.get('windows', []):
            if not isinstance(window, dict):
                continue
            if window.get('full_frame_result') == 'FAIL' or window.get('unexpected_visible_entities'):
                failures.append('ensemble: actual full-frame/extra-entity failure')
            entities = window.get('entities', {})
            if isinstance(entities, dict) and any(isinstance(v, dict) and v.get('result') == 'FAIL' for v in entities.values()):
                failures.append('ensemble: confirmed missing/wrong/state-inconsistent entity')
    return errors, failures
