#!/usr/bin/env python3
"""Offline prompt contracts and evidence gates; does NOT run a generative/VLM model.

Python 3.10+, standard library only. Production checks validate local paths/hashes,
not the truth of visual observations. No network or shell commands are executed.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import re
import sys
from pathlib import Path
from typing import Any

# Load only the reviewed sibling file; supports both CLI and import-by-file-path hosts.
import importlib.util as _importlib_util
_review_spec = _importlib_util.spec_from_file_location(
    '_ai_drama_review_efficiency', Path(__file__).with_name('review_efficiency.py'))
if _review_spec is None or _review_spec.loader is None:
    raise ImportError('The bundled review_efficiency.py module is required.')
_review_efficiency = _importlib_util.module_from_spec(_review_spec)
_review_spec.loader.exec_module(_review_efficiency)

_nine_spec = _importlib_util.spec_from_file_location(
    '_ai_drama_prompt_nine', Path(__file__).with_name('prompt_nine.py'))
if _nine_spec is None or _nine_spec.loader is None:
    raise ImportError('The bundled prompt_nine.py module is required.')
_prompt_nine = _importlib_util.module_from_spec(_nine_spec)
_nine_spec.loader.exec_module(_prompt_nine)

_ensemble_spec = _importlib_util.spec_from_file_location(
    '_ai_drama_scene_continuity', Path(__file__).with_name('scene_continuity.py'))
if _ensemble_spec is None or _ensemble_spec.loader is None:
    raise ImportError('The bundled scene_continuity.py module is required.')
_ensemble = _importlib_util.module_from_spec(_ensemble_spec)
_ensemble_spec.loader.exec_module(_ensemble)

IMAGE_CHECKS = {'scene_structure', 'subject_integrity', 'contacts', 'composition', 'technical', 'narrative'}
VIDEO_CHECKS = IMAGE_CHECKS | {'temporal', 'cut_continuity'}
ROLES = {'scene_base', 'identity', 'costume', 'prop', 'previous_end', 'start_frame', 'layout', 'mask', 'asset_ref'}
MODES = {'edit_same_view', 'new_view', 'video_i2v', 'video_reference'}
VIDEO_MODES = {'video_i2v', 'video_reference'}
HASH_RE = re.compile(r'^[0-9a-f]{64}$')

# The reviewed sibling tools own v4 request and detail-evidence contracts.
_OPS = Path(__file__).resolve().parents[2] / 'production-ops/scripts'
if str(_OPS) not in sys.path:
    sys.path.insert(0, str(_OPS))
import brain_handoff as _brain
import fidelity_contract as _fidelity
import sequence_continuity as _sequence
import prompt_contract as _prompt_contract
import h3_reference as _h3
import ensemble_gate as _ensemble_gate



def load_json(path: str | Path) -> dict[str, Any]:
    def reject_constant(s: str) -> None:
        raise ValueError(f'Non-finite JSON number is not allowed: {s}')
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        d: dict[str, Any] = {}
        for k, v in pairs:
            if k in d:
                raise ValueError(f'Duplicate JSON key: {k}')
            d[k] = v
        return d
    value = json.loads(Path(path).read_text(encoding='utf-8'),
                       parse_constant=reject_constant, object_pairs_hook=reject_duplicates)
    if not isinstance(value, dict):
        raise ValueError('Top-level JSON must be an object')
    return value


def text(x: Any) -> bool:
    return isinstance(x, str) and bool(x.strip())


def positive_int(x: Any) -> bool:
    return type(x) is int and x > 0


def finite_number(x: Any) -> bool:
    return type(x) in (float, int) and math.isfinite(x)


def digest_value(value: Any) -> str:
    b = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf-8')
    return hashlib.sha256(b).hexdigest()


def digest_job(scene: dict, shot: dict, profile: dict) -> str:
    return digest_value({'scene': scene, 'shot': shot, 'runtime_profile': profile})


def digest_text(value: str) -> str:
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def digest_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def resolve_in_root(root: Path, rel: Any) -> Path:
    if not text(rel) or Path(rel).is_absolute():
        raise ValueError('Asset paths must be nonempty and relative to --root')
    root = root.resolve(strict=True)
    p = (root / rel).resolve(strict=True)
    if not p.is_relative_to(root) or not p.is_file():
        raise ValueError(f'Path escapes project root or is not a file: {rel}')
    return p


def verify_record(record: Any, root: Path | None, label: str) -> list[str]:
    errors = []
    if not isinstance(record, dict):
        return [f'{label}: file record is missing']
    if not text(record.get('path')):
        errors.append(f'{label}: actual path missing')
    if not isinstance(record.get('sha256'), str) or not HASH_RE.fullmatch(record['sha256']):
        errors.append(f'{label}: valid sha256 missing')
    if root is None:
        errors.append(f'{label}: --root is required to verify files')
    if errors:
        return errors
    try:
        p = resolve_in_root(root, record['path'])
        if digest_file(p) != record['sha256']:
            errors.append(f'{label}: file hash mismatch')
    except (OSError, ValueError) as e:
        errors.append(f'{label}: {e}')
    return errors


def validate_scene(scene: dict) -> list[str]:
    errors: list[str] = []
    for k in ('schema_version', 'scene_id', 'scene_version', 'coordinate_system'):
        if not text(scene.get(k)):
            errors.append(f'scene.{k}: nonempty string required')
    if scene.get('schema_version') != '1.0':
        errors.append('scene: unsupported schema_version')
    if scene.get('status') not in ('planned', 'candidate', 'accepted'):
        errors.append('scene.status: invalid')
    items = scene.get('invariants')
    if not isinstance(items, list) or not items:
        errors.append('scene.invariants: nonempty array required')
    else:
        ids: set[str] = set()
        for v in items:
            if not isinstance(v, dict) or not text(v.get('id')) or not text(v.get('description')):
                errors.append('scene.invariants: id and description required')
            elif v['id'] in ids:
                errors.append('scene.invariants: duplicate id')
            else:
                ids.add(v['id'])
    views = scene.get('views')
    if not isinstance(views, list) or not views:
        errors.append('scene.views: nonempty array required')
    else:
        seen: set[str] = set()
        for v in views:
            if not isinstance(v, dict):
                errors.append('scene.views: each view must be an object'); continue
            for k in ('view_id', 'description', 'asset_id', 'state_id'):
                if not text(v.get(k)):
                    errors.append(f'scene.view.{k}: required')
            vid = v.get('view_id')
            if text(vid):
                if vid in seen:
                    errors.append('scene.views: duplicate view_id')
                seen.add(vid)
            if v.get('status') not in ('candidate', 'accepted'):
                errors.append('scene.view.status: invalid')
    return errors


def new_view_geometry(scene: dict, shot: dict) -> str:
    """Freeze only the shared scene geometry and the two declared view designs."""
    errors = validate_scene(scene)
    if shot.get('scene_id') != scene.get('scene_id') or shot.get('scene_version') != scene.get('scene_version'):
        errors.append('new_view: scene ID/version mismatch')
    views = scene.get('views', [])
    views = views if isinstance(views, list) else []
    source = next((v for v in views if isinstance(v, dict) and v.get('view_id') == shot.get('source_view_id')), None)
    target = next((v for v in views if isinstance(v, dict) and v.get('view_id') == shot.get('view_id')), None)
    if source is None:
        errors.append('new_view: registered source view design required')
    if target is None:
        errors.append('new_view: registered target view design required')
    if errors:
        raise ValueError('; '.join(errors))
    return '\n'.join([
        f'同一空景几何：{scene["scene_id"]}，版本{scene["scene_version"]}。',
        '世界坐标：' + scene['coordinate_system'],
        *[f'固定空间约束 {row["id"]}：{row["description"]}' for row in scene['invariants']],
        f'源机位 {source["view_id"]}：{source["description"]}',
        f'目标机位 {target["view_id"]}：{target["description"]}',
    ])


def inspect_final_prompt(shot: dict, prompt: str, profile: dict | None = None,
                         scene: dict | None = None) -> list[str]:
    """Use verified backend speech boundaries before visual identity checks."""
    checked = prompt
    if shot.get('policy_version') == '4.2.0':
        backend = (profile or {}).get('prompt_backend')
        errors = _prompt_contract.validate_shot_ir(shot, backend)
        if errors:
            return errors
        for clause in shot['prompt_ir']['clauses']:
            if clause['kind'] != 'speech':
                continue
            spoken = clause['text_spoken']
            if backend.get('speech_format') == 'colon':
                prefix = clause['speaker'] + ' says: '
                suffix = '\nDelivery, not spoken: ' + clause['delivery'] if text(clause.get('delivery')) else ''
                original = prefix + spoken + suffix
                redacted = prefix + '[已锁定对白]' + suffix
            else:
                original = clause['text']
                # Literal authors control punctuation. An ambiguous repeated
                # payload has no reliable span, so do not guess an exemption.
                if original.count(spoken) != 1:
                    continue
                redacted = original.replace(spoken, '[已锁定对白]', 1)
            if prompt.count(original) == 1:
                checked = checked.replace(original, redacted, 1)
            checked += '\n' + clause['speaker']
            if text(clause.get('delivery')):
                checked += '\n' + clause['delivery']
    else:
        audio = shot.get('audio_plan', {})
        if isinstance(audio, dict) and isinstance(audio.get('native_spoken_lines', []), list):
            for line in audio.get('native_spoken_lines', []):
                if isinstance(line, dict) and all(text(line.get(k)) for k in ('speaker_description', 'voice_description', 'text_spoken')):
                    original = _prompt_nine.render_native_line(line)
                    redacted = _prompt_nine.render_native_line({**line, 'text_spoken': '[已锁定对白]'})
                    if prompt.count(original) == 1:
                        checked = checked.replace(original, redacted, 1)
    errors = _prompt_nine.inspect_prompt(shot, checked) + _prompt_contract.obvious_contradictions(checked)
    if shot.get('mode') == 'new_view':
        try:
            if new_view_geometry(scene or {}, shot) not in checked:
                errors.append('new_view: frozen scene geometry block missing or changed in final prompt')
        except ValueError as exc:
            errors.append(str(exc))
    return errors


def render_prompt(scene: dict, shot: dict, profile: dict | None = None) -> str:
    if shot.get('policy_version') == '4.2.0':
        errors = _prompt_contract.validate_shot_ir(shot, (profile or {}).get('prompt_backend'))
        if errors: raise ValueError('; '.join(errors))
    if shot.get('locked_prompt') is not None:
        if not text(shot['locked_prompt']):
            raise ValueError('locked_prompt must be nonempty final brain-authored text')
        errors = inspect_final_prompt(shot, shot['locked_prompt'], profile, scene)
        if errors:
            raise ValueError('; '.join(errors))
        return shot['locked_prompt']
    if shot.get('prompt9') is not None:
        prompt = _prompt_nine.render_nine(shot)
        errors = inspect_final_prompt(shot, prompt, profile, scene)
        if errors:
            raise ValueError('; '.join(errors))
        return prompt
    refs = shot.get('references', [])
    parts: list[str] = []
    primary = next((r for r in refs if r.get('primary') is True), None)
    idx = primary['upload_index'] if primary else '?'
    mode = shot.get('mode')
    if mode == 'edit_same_view':
        parts.append(f'在输入图片{idx}上进行局部编辑。它是当前场景与机位的底图，不是风格示例；不是重新设计一个相似空间。')
    elif mode == 'new_view':
        parts.append('为已批准的同一空间建立指定新机位的背景候选；不是最终剧情镜头。严格按给出的空间关系处理新视角。')
        parts.append(new_view_geometry(scene, shot))
    elif mode == 'video_reference':
        parts.append('以下图片只提供人物、道具、场景设计参考。根据描述直接生成一个连续镜头，不以参考图片作为起始帧。')
        parts.append(shot.get('background_motion', ''))
    else:
        parts.append(f'从输入图片{idx}的已验收起始状态开始，执行已锁定的单镜头动作，不重新设计场景。')
    if shot.get('style_lock'):
        parts.append(shot['style_lock']['prompt_sentence'])
        if mode == 'new_view':
            parts.append('沿用已验收源母版的现有画风和共同场景设计；仅采用已声明的目标机位，不改门窗、结构和固定陈设。')
        elif mode == 'video_reference':
            parts.append('沿用已验收素材的现有画风与场景设计，呈现目标机位及已锁定的镜头运动。')
        else:
            parts.append('沿用已验收底图的现有画风；以上风格约束不授权重绘场景或改变机位。')
    for r in sorted(refs, key=lambda r: r['upload_index']):
        label = f'<Picture {r["upload_index"]}>' if mode == 'video_reference' else f'图片{r["upload_index"]}'
        parts.append(f'{label}的用途：{r["purpose"]}')
    parts.append(f'本次变化：{shot["change_request"]}')
    if shot.get('relations'):
        parts.append('空间与接触：' + '；'.join(shot['relations']) + '。')
    if shot.get('preserve'):
        parts.append('必须保留：' + '；'.join(shot['preserve']) + '。')
    if shot.get('camera_motion', 'fixed') == 'fixed':
        parts.append('保持该镜头已锁定的固定机位、透视和构图；不镜像，不临时改变视角。')
    else:
        parts.append('只采用已经规划的镜头运动：' + shot.get('camera_motion_description', '未填写'))
    if mode in VIDEO_MODES:
        video = shot.get('video', {})
        for beat in video.get('action_beats', []):
            parts.append(f'{beat["start_s"]}–{beat["end_s"]}秒：{beat["action"]}')
        parts.append('结束状态：' + video.get('end_state_description', '未填写'))
        audio_plan = shot.get('audio_plan', {})
        for line in audio_plan.get('native_spoken_lines', []):
            parts.append(_prompt_nine.render_native_line(line))
        for line in ([] if shot.get('insert_policy') else audio_plan.get('post_voices', [])):
            if line['source_kind'] == 'inner':
                parts.append('后期心声来自' + line['speaker_description'] +
                             '；本次不生成这段心声录音，不把心声演成嘴部逐字发声。正常呼吸和表情保留。')
            else:
                parts.append('另有后期' + line['source_kind'] +
                             '声轨；本次不生成该声轨，也不让镜中人物代说。')
    else:
        parts.append('只输出一张本镜起始状态图，不做分格、不同时表现多个连续动作。')
    if shot.get('narrative_must_show'):
        parts.append('必须清楚可见：' + '；'.join(shot['narrative_must_show']) + '。')
    if shot.get('ensemble') is not None:
        parts.append(_ensemble.render_clauses(shot['ensemble'], image=shot.get('mode') not in VIDEO_MODES))
    prompt = '\n'.join(parts)
    errors = inspect_final_prompt(shot, prompt, profile, scene)
    if errors:
        raise ValueError('; '.join(errors))
    return prompt


def _validate_results(scene: dict, shot: dict, profile: dict, root: Path | None = None,
             production: bool = False) -> tuple[list[str], list[str]]:
    e = validate_scene(scene)
    if shot.get('locked_prompt') is not None and not text(shot['locked_prompt']):
        e.append('locked_prompt: nonempty text required')
    if shot.get('policy_version') not in (None, '4.0.0', '4.1.0', '4.2.0'):
        e.append('unsupported shot policy_version')
    production_prefix = []
    e += _prompt_nine.validate_nine(shot)
    e += _ensemble.validate_shot(shot)
    style = shot.get('style_lock')
    if style is not None:
        if not isinstance(style, dict) or any(not text(style.get(k)) for k in ('style_id', 'version', 'prompt_sentence')):
            e.append('style_lock: style_id, version and exact prompt_sentence required')
        elif production and style.get('status') != 'locked':
            production_prefix.append((len(e), 'production: style not locked'))
    e += _prompt_nine.validate_delivery_notes(shot)
    audio_plan = shot.get('audio_plan')
    if audio_plan is not None:
        if shot.get('mode') not in VIDEO_MODES or not isinstance(audio_plan, dict):
            e.append('audio_plan: only valid as an object for a video mode')
        else:
            line_ids = set()
            for group in ('native_spoken_lines', 'post_voices'):
                lines = audio_plan.get(group)
                if not isinstance(lines, list):
                    e.append('audio_plan: both line arrays required'); continue
                for line in lines:
                    if not isinstance(line, dict) or any(not text(line.get(k)) for k in ('line_id', 'speaker_description', 'text_spoken')):
                        e.append('audio_plan: complete line identity/text/speaker required'); continue
                    if line['line_id'] in line_ids:
                        e.append('audio_plan: duplicate or double-routed line')
                    line_ids.add(line['line_id'])
                    if group == 'native_spoken_lines' and not text(line.get('voice_description')):
                        e.append('audio_plan: native voice description required')
                    if group == 'post_voices' and line.get('source_kind') not in ('inner', 'voiceover', 'system'):
                        e.append('audio_plan: invalid post-production source kind')
            if (production and audio_plan.get('native_spoken_lines') and
                    profile.get('features', {}).get('native_audio_video') != 'verified'):
                production_prefix.append((len(e), 'production: native_audio_video capability not verified'))
    for k in ('schema_version', 'shot_id', 'source_scene_id', 'scene_id', 'scene_version', 'scene_state_id', 'view_id', 'change_request'):
        if not text(shot.get(k)):
            e.append(f'shot.{k}: nonempty string required')
    if shot.get('schema_version') != '1.0':
        e.append('shot: unsupported schema_version')
    if shot.get('mode') not in MODES:
        e.append('shot.mode: unsupported')
    if shot.get('scene_id') != scene.get('scene_id') or shot.get('scene_version') != scene.get('scene_version'):
        e.append('shot: scene ID/version mismatch')
    if shot.get('planning_status') not in ('candidate', 'locked'):
        e.append('shot.planning_status: invalid')
    if type(shot.get('camera_locked')) is not bool:
        e.append('shot.camera_locked: boolean required')
    if shot.get('camera_motion', 'fixed') not in ('fixed', 'planned_path'):
        e.append('shot.camera_motion: invalid')
    if shot.get('camera_motion') == 'planned_path' and not text(shot.get('camera_motion_description')):
        e.append('shot.camera_motion_description: required for planned motion')
    out = shot.get('output')
    if not isinstance(out, dict):
        e.append('shot.output: object required'); out = {}
    for k in ('width', 'height'):
        if not positive_int(out.get(k)):
            e.append(f'shot.output.{k}: positive integer required')
    expected_kind = 'video' if shot.get('mode') in VIDEO_MODES else 'image'
    e += _review_efficiency.check_policy(shot.get('quality_policy'), expected_kind)
    if out.get('media_kind') != expected_kind:
        e.append('shot.output.media_kind: does not match mode')
    for key in ('preserve', 'relations', 'narrative_must_show'):
        arr = shot.get(key)
        if not isinstance(arr, list) or any(not text(x) for x in arr):
            e.append(f'shot.{key}: string array required')
    for key in ('state_in', 'state_out'):
        if not isinstance(shot.get(key), dict):
            e.append(f'shot.{key}: object required')
    checks = shot.get('qa_required')
    must = set(VIDEO_CHECKS if expected_kind == 'video' else IMAGE_CHECKS)
    if isinstance(shot.get('protection'), dict) and shot['protection'].get('method') == 'external_composite':
        must.add('protected_pixels')
    if not isinstance(checks, list) or any(not text(c) for c in checks):
        e.append('shot.qa_required: nonempty string array required')
    elif len(set(checks)) != len(checks) or not must.issubset(set(checks)):
        e.append('shot.qa_required: duplicates or missing mandatory checks')
    budget = shot.get('repair_budget')
    if not isinstance(budget, dict) or any(type(budget.get(k)) is not int or budget[k] < 0 for k in ('generation_attempts', 'local_repairs')):
        e.append('shot.repair_budget: nonnegative integer limits required')
    refs = shot.get('references')
    valid_refs: list[dict] = []
    if not isinstance(refs, list) or not refs:
        e.append('shot.references: actual ordered references required')
    else:
        for r in refs:
            if not isinstance(r, dict):
                e.append('shot.references: object required'); continue
            valid_refs.append(r)
            for k in ('asset_id', 'purpose'):
                if not text(r.get(k)):
                    e.append(f'reference.{k}: required')
            if r.get('role') not in ROLES:
                e.append('reference.role: invalid')
            if not positive_int(r.get('upload_index')):
                e.append('reference.upload_index: positive integer required')
            if shot.get('mode') != 'video_reference' and type(r.get('primary')) is not bool:
                e.append('reference.primary: boolean required')
            if r.get('status') not in ('missing', 'candidate', 'accepted'):
                e.append('reference.status: invalid')
        indices = [r.get('upload_index') for r in valid_refs]
        if all(type(i) is int for i in indices) and sorted(indices) != list(range(1, len(indices)+1)):
            e.append('references: upload indices must be unique and contiguous from 1')
        asset_ids = [r.get('asset_id') for r in valid_refs]
        if all(text(a) for a in asset_ids) and len(set(asset_ids)) != len(asset_ids):
            e.append('references: duplicate asset_id')
        primary = [r for r in valid_refs if r.get('primary') is True]
        if shot.get('mode') == 'video_reference':
            if primary: e.append('references: reference video must not designate a primary image')
            try:
                e += _h3.reference_errors({**shot, 'prompt': render_prompt(scene, shot, profile)})
            except (ValueError, KeyError, TypeError) as exc:
                e.append('references: ' + str(exc))
        elif len(primary) != 1:
            e.append('references: exactly one primary image required')
        elif shot.get('mode') == 'new_view' and primary[0].get('role') != 'scene_base':
            e.append('references: new_view primary must be the actual source scene_base')
        elif primary[0].get('role') not in ('scene_base', 'previous_end', 'start_frame'):
            e.append('references: primary must be a scene/start/previous-end image')
    view_id = shot.get('source_view_id') if shot.get('mode') == 'new_view' else shot.get('view_id')
    views = scene.get('views', [])
    view = next((v for v in views if isinstance(v, dict) and v.get('view_id') == view_id), None) if isinstance(views, list) else None
    if view is None:
        e.append('shot: corresponding source view/master not found')
    if shot.get('mode') in VIDEO_MODES:
        v = shot.get('video')
        if not isinstance(v, dict):
            e.append('shot.video: required'); v = {}
        duration = v.get('duration_s')
        if not finite_number(duration) or duration <= 0:
            e.append('video.duration_s: positive finite number required')
        if not positive_int(v.get('fps')):
            e.append('video.fps: positive integer required')
        if not text(v.get('end_state_description')):
            e.append('video.end_state_description: required')
        beats = v.get('action_beats')
        cursor = 0.0
        if not isinstance(beats, list) or not beats:
            e.append('video.action_beats: required')
        else:
            for beat in beats:
                if not isinstance(beat, dict) or not all(finite_number(beat.get(k)) for k in ('start_s', 'end_s')):
                    e.append('video beat: finite start/end required'); continue
                if abs(beat['start_s'] - cursor) > 1e-6 or beat['end_s'] <= beat['start_s'] or not text(beat.get('action')):
                    e.append('video beats: gaps, overlaps, nonpositive duration or empty action')
                cursor = beat['end_s']
            if finite_number(duration) and abs(cursor-duration) > 1e-6:
                e.append('video beats: timeline does not end at duration_s')
    prot = shot.get('protection')
    if not isinstance(prot, dict) or prot.get('method') not in ('none', 'external_composite'):
        e.append('shot.protection: valid method required')
    elif prot.get('method') == 'external_composite' and shot.get('mode') != 'edit_same_view':
        e.append('protection: this compositor only handles same-view still images')
    before_insert = len(e)
    if not e and (shot.get('mode') == 'new_view' or shot.get('prompt9') is not None or shot.get('insert_policy') is not None or shot.get('locked_prompt') is not None or shot.get('policy_version') == '4.2.0'):
        try:
            render_prompt(scene, shot, profile)
        except (ValueError, KeyError, TypeError) as exc:
            e.append('insert prompt validation: ' + str(exc))
    structural = e.copy()
    if not production:
        return structural, structural
    # Early production errors previously suppressed insert rendering. Preserve
    # that behavior and the original error order while checking structure once.
    if production_prefix:
        e = e[:before_insert]
        for index, message in reversed(production_prefix):
            e.insert(index, message)
    if profile.get('schema_version') != '1.0':
        e.append('profile: unsupported schema_version')
    if root is None:
        e.append('production: --root required')
    if scene.get('status') != 'accepted':
        e.append('production: scene design not accepted')
    if shot.get('planning_status') != 'locked' or shot.get('camera_locked') is not True:
        e.append('production: storyboard/camera not locked')
    if profile.get('runtime_verified') is not True or not text(profile.get('backend')) or not text(profile.get('model_id')):
        e.append('production: backend/model runtime not verified')
    e += verify_record(profile.get('verification_evidence'), root, 'runtime verification evidence')
    features = profile.get('features', {})
    if not isinstance(features, dict):
        features = {}; e.append('profile.features: object required')
    required_features = ['reference_to_video' if shot.get('mode') == 'video_reference' else 'image_to_video' if expected_kind == 'video' else 'image_edit']
    if len(valid_refs) > 1:
        required_features.append('multi_reference')
    if any(r.get('role') in ('layout', 'mask') for r in valid_refs):
        required_features.append('spatial_reference')
    if isinstance(prot, dict) and prot.get('method') == 'external_composite':
        required_features.append('external_composite')
        e += verify_record(prot.get('allowed_mask'), root, 'allowed_mask')
        if prot.get('blend_mask') is not None:
            e += verify_record(prot['blend_mask'], root, 'blend_mask')
    for feature in required_features:
        if features.get(feature) != 'verified':
            e.append(f'production: capability not verified: {feature}')
    limit = profile.get('max_reference_images')
    if not positive_int(limit) or len(valid_refs) > limit:
        e.append('production: reference limit unknown or exceeded')
    parameter_map = profile.get('parameter_map')
    parameter_keys = ('prompt', 'images', 'res', 'aspect', 'image_mode') if shot.get('mode') == 'video_reference' else ('prompt', 'images', 'width', 'height')
    if not isinstance(parameter_map, dict) or any(not text(parameter_map.get(k)) for k in parameter_keys):
        e.append('production: parameter mapping incomplete')
    multiple = profile.get('dimension_multiple')
    if multiple is not None:
        if not positive_int(multiple):
            e.append('profile.dimension_multiple: invalid')
        elif all(positive_int(out.get(k)) for k in ('width', 'height')) and any(out[k] % multiple for k in ('width', 'height')):
            e.append('production: output dimensions violate backend alignment')
    if view:
        if view.get('status') != 'accepted':
            e.append('production: source view master not accepted')
        e += verify_record(view, root, 'view master')
        if shot.get('mode') == 'video_reference' and not any(
                r.get('role') == 'asset_ref' and r.get('asset_id') == view.get('asset_id') for r in valid_refs):
            e.append('production: target view master reference required')
    for r in valid_refs:
        if r.get('status') != 'accepted':
            e.append(f'production: reference not accepted: {r.get("asset_id")}')
        e += verify_record(r, root, f'reference {r.get("asset_id")}')
        target_master = shot.get('mode') == 'video_reference' and view and r.get('asset_id') == view.get('asset_id')
        if r.get('primary') is True or target_master:
            label = 'target view reference' if target_master else 'primary image'
            if r.get('scene_id') != scene.get('scene_id') or r.get('scene_version') != scene.get('scene_version') or r.get('view_id') != view_id:
                e.append(f'production: {label} scene/version/view mismatch')
            if r.get('state_id') != shot.get('scene_state_id') or (target_master and r.get('state_id') != view.get('state_id')):
                e.append(f'production: {label} state mismatch')
            if target_master and r.get('sha256') != view.get('sha256'):
                e.append('production: target view reference differs from registered view master')
            if view and r.get('role') == 'scene_base' and (r.get('sha256') != view.get('sha256') or r.get('asset_id') != view.get('asset_id')):
                e.append('production: scene_base differs from registered view master')
            if view and r.get('role') in ('start_frame', 'previous_end') and r.get('scene_anchor_sha256') != view.get('sha256'):
                e.append('production: motion/start image lacks correct master lineage')
    rewrite_policy = profile.get('prompt_rewrite_policy')
    if rewrite_policy not in ('disabled_verified', 'audited'):
        e.append('production: actual prompt rewrite behavior unknown')
    elif rewrite_policy == 'audited':
        audit = shot.get('rewrite_audit')
        if not isinstance(audit, dict) or audit.get('passed') is not True or not text(audit.get('final_prompt')):
            e.append('production: final rewritten prompt has not been audited')
        elif not e:
            original = render_prompt(scene, shot, profile)
            if audit.get('source_prompt_sha256') != digest_text(original) or audit.get('final_prompt_sha256') != digest_text(audit['final_prompt']):
                e.append('production: rewrite audit is stale or hash mismatched')
            e += verify_record(audit.get('evidence'), root, 'rewrite audit evidence')
            e += inspect_final_prompt(shot, audit['final_prompt'], profile, scene)
    if shot.get('policy_version') in {'4.0.0', '4.1.0', '4.2.0'}:
        for flag in ('brain_required', 'fidelity_required'):
            if shot.get(flag) is not True:
                e.append('v4: cannot disable required ' + flag)
    if shot.get('fidelity_required') is True:
        if root is None:
            e.append('fidelity: project root required')
        else:
            try:
                _, detail_errors = _fidelity.check_file(shot.get('fidelity_contract'),
                    Path(root).resolve(), _brain.verify_record, shot)
                e.extend(detail_errors)
            except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
                e.append('fidelity binding unavailable: ' + str(exc))
    if shot.get('policy_version') in {'4.1.0', '4.2.0'} and shot.get('continuity_required') is not True:
        e.append('v4.1: cannot disable required continuity state inheritance')
    if shot.get('continuity_required') is True:
        if root is None:
            e.append('sequence: project root required')
        else:
            try:
                exact_prompt = (shot['rewrite_audit']['final_prompt']
                    if rewrite_policy == 'audited' and not e else render_prompt(scene, shot, profile))
                _, se = _sequence.check_file(shot.get('continuity_plan'), Path(root).resolve(),
                    _brain.verify_record, shot, exact_prompt)
                e.extend(se)
            except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
                e.append('sequence: plan unavailable: ' + str(exc))
    if shot.get('brain_required') is True:
        try:
            final_prompt = (shot['rewrite_audit']['final_prompt']
                if rewrite_policy == 'audited' and not e else render_prompt(scene, shot, profile))
            e.extend(_brain.check_compiled(scene, shot, profile, final_prompt, root))
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
            e.append('brain binding unavailable: ' + str(exc))
    return structural, e


def validate(scene: dict, shot: dict, profile: dict, root: Path | None = None,
             production: bool = False) -> list[str]:
    structural, blockers = _validate_results(scene, shot, profile, root, production)
    return blockers if production else structural


def compile_package(scene: dict, shot: dict, profile: dict, root: Path | None = None,
                    production: bool = False) -> dict:
    structural, blockers = _validate_results(scene, shot, profile, root, production=True)
    prompt = '' if structural else render_prompt(scene, shot, profile)
    if not blockers and profile.get('prompt_rewrite_policy') == 'audited':
        prompt = shot['rewrite_audit']['final_prompt']
    ready = production and not blockers and not structural
    return {
        'status': 'READY' if ready else 'DRAFT',
        'executed': False, 'visual_quality_verified': False,
        'readiness': {'contract': 'INPUT_READY' if ready else 'BLOCKED', 'semantic': 'REVIEW_RECORD_BOUND' if ready and shot.get('policy_version') == '4.2.0' else 'NOT_ESTABLISHED', 'media': 'NOT_REVIEWED', 'host_submission': 'NOT_EXECUTED'},
        'shot_id': shot.get('shot_id'), 'contract_sha256': digest_job(scene, shot, profile),
        'prompt': prompt, 'prompt_sha256': digest_text(prompt),
        'input_order': sorted(shot.get('references', []), key=lambda r: r.get('upload_index', 0)) if not structural else [],
        'output_spec': shot.get('output'), 'mode': shot.get('mode'),
        'qa_required': shot.get('qa_required'), 'protection': shot.get('protection'),
        'post_audio_cues': (shot['audio_plan'].get('post_voices', []) if isinstance(shot.get('audio_plan'), dict) else []),
        'prompt9_used': shot.get('prompt9') is not None,
        'prompt_ir_used': shot.get('policy_version') == '4.2.0' and shot.get('prompt_ir') is not None,
        'ensemble_used': shot.get('ensemble') is not None,
        'ensemble_sha256': digest_value(shot['ensemble']) if shot.get('ensemble') is not None else None,
        'blockers': list(dict.fromkeys(structural + blockers)),
        'policy_version': shot.get('policy_version', 'legacy'),
        'brain_binding': shot.get('brain_binding'),
        'fidelity_contract': shot.get('fidelity_contract'),
        'continuity_plan': shot.get('continuity_plan'),
        'brain_request': (_brain.request_snapshot(scene, shot, profile, prompt)
                          if shot.get('brain_required') is True and not structural else None),
        'notice': 'Model-independent job package, not a native API request. READY is input readiness only.'
    }


def check_coverage(coverage: Any, kind: str) -> list[str]:
    if not isinstance(coverage, dict) or coverage.get('kind') != kind:
        return ['coverage: media kind mismatch or missing']
    if kind == 'image':
        return [] if coverage.get('basis') == 'full_image' else ['coverage: full_image review required']
    e = []
    if coverage.get('basis') != 'full_frames' or coverage.get('temporal_reviewed') is not True:
        e.append('coverage: full_frames plus temporal review required')
    n = coverage.get('total_frames')
    if not positive_int(n):
        return e + ['coverage: verified total_frames required']
    ranges = coverage.get('frame_ranges')
    if not isinstance(ranges, list) or not ranges:
        return e + ['coverage: nonempty inspected frame_ranges required']
    cursor = 0
    for item in ranges:
        if not isinstance(item, list) or len(item) != 2 or any(type(x) is not int for x in item):
            e.append('coverage: invalid frame range'); continue
        start, end = item
        if start != cursor or end < start or end >= n:
            e.append('coverage: gap, overlap or out-of-bounds frames')
        cursor = end + 1
    if cursor != n:
        e.append('coverage: frames remain unchecked')
    return e


def quality_gate(scene: dict, shot: dict, profile: dict, report: dict, root: Path | None) -> dict:
    blockers = validate(scene, shot, profile, root, production=True)
    failures: list[str] = []
    warnings: list[str] = []
    if report.get('schema_version') != '1.0':
        blockers.append('review: unsupported schema_version')
    if report.get('shot_id') != shot.get('shot_id'):
        blockers.append('review: shot_id mismatch')
    if report.get('contract_sha256') != digest_job(scene, shot, profile):
        blockers.append('review: stale contract hash')
    kind = 'video' if shot.get('mode') in VIDEO_MODES else 'image'
    stage = 'view_asset' if shot.get('mode') == 'new_view' else kind
    if report.get('stage') != stage:
        blockers.append('review: stage mismatch')
    blockers += verify_record(report.get('artifact'), root, 'reviewed output')
    if isinstance(shot.get('protection'), dict) and shot['protection'].get('method') == 'external_composite' and root is not None:
        try:
            from pixel_lock import compare
            primary = next(r for r in shot.get('references', []) if r.get('primary') is True)
            pixel_result = compare(resolve_in_root(root, primary['path']),
                                   resolve_in_root(root, report['artifact']['path']),
                                   resolve_in_root(root, shot['protection']['allowed_mask']['path']))
            if not pixel_result['protected_rgba_identical']:
                failures.append('actual pixel check: protected background changed')
        except (ImportError, SystemExit, OSError, ValueError, KeyError, TypeError, StopIteration) as exc:
            blockers.append(f'actual pixel check could not complete: {exc}')
    reviewer = report.get('reviewer')
    if not isinstance(reviewer, dict) or reviewer.get('kind') not in ('vision_model', 'human') or not text(reviewer.get('id')) or not text(reviewer.get('version')):
        blockers.append('review: actual reviewer identity/version required')
    quality_policy = shot.get('quality_policy', {})
    if not isinstance(quality_policy, dict):
        quality_policy = {}
    coverage = report.get('coverage')
    if (kind == 'video' and quality_policy.get('review_mode') == 'balanced'
            and isinstance(coverage, dict) and coverage.get('basis') == 'risk_based'):
        blockers += _review_efficiency.check_balanced_coverage(coverage, quality_policy)
        for key in ('decode_evidence', 'temporal_evidence', 'sampling_evidence'):
            blockers += verify_record(coverage.get(key), root, f'coverage.{key}')
    else:
        # Legacy strict and explicit full-frame reviews keep their original checks.
        blockers += check_coverage(coverage, kind)
    checks = report.get('checks')
    found: dict[str, dict] = {}
    if not isinstance(checks, list):
        blockers.append('review: checks array required'); checks = []
    for c in checks:
        if not isinstance(c, dict) or not text(c.get('id')):
            blockers.append('review: invalid check'); continue
        if c['id'] in found:
            blockers.append('review: duplicate check ID')
        found[c['id']] = c
        if c.get('result') == 'FAIL':
            failures.append(f'failed check: {c["id"]}')
        elif c.get('result') != 'PASS':
            blockers.append(f'check not passed: {c["id"]}')
        if not text(c.get('observation')):
            blockers.append(f'observation missing: {c["id"]}')
        evidence = c.get('evidence')
        if not isinstance(evidence, list) or not evidence:
            blockers.append(f'evidence missing: {c["id"]}')
        else:
            for item in evidence:
                blockers += verify_record(item, root, f'evidence {c["id"]}')
    for cid in shot.get('qa_required', []):
        if cid not in found:
            blockers.append(f'required check missing: {cid}')
    findings = report.get('findings')
    if not isinstance(findings, list):
        blockers.append('review.findings: array required'); findings = []
    for f in findings:
        if not isinstance(f, dict) or f.get('severity') not in ('critical', 'major', 'minor') or type(f.get('resolved')) is not bool or not text(f.get('description')):
            blockers.append('review.findings: malformed finding'); continue
        if not f['resolved'] and f['severity'] in ('critical', 'major'):
            failures.append(f'unresolved {f["severity"]}: {f["description"]}')
        elif not f['resolved']:
            warnings.append(f'unresolved minor: {f["description"]}')
            if not _review_efficiency.may_waive_minor(f, quality_policy, shot.get('qa_required', [])):
                failures.append(f'unwaived minor finding: {f["description"]}')
            elif quality_policy.get('review_mode') == 'balanced':
                blockers += verify_record(f.get('waiver_evidence'), root, 'minor tolerance evidence')
    if shot.get('fidelity_required') is True:
        if root is None:
            blockers.append('fidelity: actual review project root missing')
        else:
            try:
                detail, de = _fidelity.check_file(shot.get('fidelity_contract'),
                    Path(root).resolve(), _brain.verify_record, shot)
                blockers.extend(de)
                if detail:
                    context = {shot['shot_id']: {'contract': detail,
                        'record': shot['fidelity_contract'], 'media': report.get('artifact')}}
                    de, df = _fidelity.check_review(report.get('fidelity_review'), context,
                        'video' if kind == 'video' else 'start_frame',
                        report.get('artifact', {}).get('sha256'), Path(root).resolve(),
                        _brain.verify_record)
                    blockers.extend(de); failures.extend(df)
            except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
                blockers.append('fidelity review unavailable: ' + str(exc))
    if shot.get('ensemble') is not None:
        details = report.get('ensemble_review')
        if not isinstance(details, dict):
            blockers.append('ensemble: actual whole-frame entity observations required')
        else:
            try:
                context = {shot['shot_id']: {'bundle': shot['ensemble'], 'media': report.get('artifact', {})}}
                ee, ef = _ensemble_gate.check_details(details, context, kind == 'image')
                blockers.extend(ee); failures.extend(ef)
            except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
                blockers.append('ensemble review unavailable: ' + str(exc))
    if shot.get('policy_version') in {'4.1.0', '4.2.0'} and shot.get('continuity_required') is not True:
        blockers.append('v4.1: continuity gate cannot be disabled')
    if shot.get('continuity_required') is True:
        try:
            if root is None: raise ValueError('actual project root missing')
            ctx, se = _sequence.check_file(shot.get('continuity_plan'), Path(root).resolve(),
                _brain.verify_record, shot)
            blockers.extend(se)
            if ctx:
                ctx.update(record=shot['continuity_plan'], media=report.get('artifact'))
                se, sf = _sequence.check_review(report.get('continuity_review'),
                    {shot['shot_id']: ctx}, 'video' if kind == 'video' else 'start_frame',
                    report.get('artifact', {}).get('sha256'), Path(root).resolve(), _brain.verify_record)
                blockers.extend(se); failures.extend(sf)
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
            blockers.append('sequence review unavailable: ' + str(exc))
    status = 'REJECTED' if failures else ('BLOCKED' if blockers else 'ACCEPTED')
    return {'status': status, 'shot_id': shot.get('shot_id'),
            'failures': list(dict.fromkeys(failures)), 'blockers': list(dict.fromkeys(blockers)),
            'warnings': warnings,
            'review_mode': quality_policy.get('review_mode', 'strict'),
            'coverage_basis': coverage.get('basis') if isinstance(coverage, dict) else None,
            'guarantees_zero_visual_errors': False,
            'scope': 'Checks local evidence integrity and declared review results; no model/vision inference is performed.'}


def save_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Explicit output only. Never overwrite an input path through the CLI.
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('check', 'compile', 'digest', 'gate'):
        p = sub.add_parser(name)
        p.add_argument('--scene', required=True, type=Path)
        p.add_argument('--shot', required=True, type=Path)
        p.add_argument('--profile', required=True, type=Path)
        p.add_argument('--root', type=Path)
        if name in ('check', 'compile'):
            p.add_argument('--production', action='store_true')
        if name == 'compile':
            p.add_argument('--out', required=True, type=Path)
        if name == 'gate':
            p.add_argument('--report', required=True, type=Path)
    a = parser.parse_args()
    try:
        scene, shot, profile = map(load_json, (a.scene, a.shot, a.profile))
        if a.command == 'digest':
            print(digest_job(scene, shot, profile)); return 0
        if a.command == 'check':
            errors = validate(scene, shot, profile, a.root, a.production)
            result = {'status': 'FAIL' if errors else 'CONTRACT_OK', 'production_check': a.production,
                      'visual_quality_verified': False, 'errors': errors}
            code = 2 if errors else 0
        elif a.command == 'compile':
            if a.out.resolve() in {a.scene.resolve(), a.shot.resolve(), a.profile.resolve()}:
                raise ValueError('Output must not overwrite an input contract')
            result = compile_package(scene, shot, profile, a.root, a.production)
            save_json(a.out, result)
            code = 2 if a.production and result['status'] != 'READY' else 0
        else:
            result = quality_gate(scene, shot, profile, load_json(a.report), a.root)
            code = 0 if result['status'] == 'ACCEPTED' else 2
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        return code
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as e:
        print(json.dumps({'status': 'BLOCKED', 'error': str(e)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
