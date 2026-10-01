#!/usr/bin/env python3
"""Nine-dimension prompt compiler and insert-shot text guard; no model calls.

The nine dimensions are this project's schema, not a claimed WanPE API.
String checks cannot prove semantic consistency or inspect reference pixels.
"""
from __future__ import annotations
import hashlib
import json
import re
from typing import Any

from pathlib import Path
import importlib.util as _importlib_util
_es = _importlib_util.spec_from_file_location(
    '_ai_drama_nine_ensemble', Path(__file__).with_name('scene_continuity.py'))
if _es is None or _es.loader is None:
    raise ImportError('scene_continuity.py is required')
_ensemble = _importlib_util.module_from_spec(_es)
_es.loader.exec_module(_ensemble)

DIMENSIONS = ('subject', 'camera_motion', 'lighting', 'choreography', 'framing',
              'space', 'style', 'sound', 'stability')
DERIVED = {'camera_motion': 'camera_motion', 'choreography': 'video.action_beats',
           'style': 'style_lock.prompt_sentence', 'sound': 'audio_plan'}
FREE_TEXT = ('subject', 'lighting', 'framing', 'space', 'stability')
LABELS = {'subject': '画内主体', 'lighting': '光影', 'framing': '景别与构图',
          'space': '画内空间', 'stability': '本镜保持项'}
# Detect person/location claims, not the bare word “offscreen”. Known private
# entities are checked separately by exact aliases. Ambient rain or illumination
# is not a person leak. This lexical guard is deliberately not a semantic model.
OFFSCREEN_PERSON = re.compile(
    r'(?:有人|某人|人物|人影|男人|女人|男孩|女孩|演员|他|她)[^。；\n]{0,14}(?:画外|镜头外|镜外)'
    r'|(?:画外|镜头外|镜外)[^。；\n]{0,14}(?:有人|某人|人物|人影|男人|女人|男孩|女孩|演员|站着|坐着|他|她)'
    r'|(?:off[ -]?screen|outside\s+(?:the\s+)?(?:frame|shot))[^.;\n]{0,20}\b(?:person|people|character|actor|actress|man|woman|boy|girl|someone|he|she)\b'
    r'|\b(?:person|people|character|actor|actress|man|woman|boy|girl|someone|he|she)\b[^.;\n]{0,20}(?:off[ -]?screen|outside\s+(?:the\s+)?(?:frame|shot))', re.I)


def nonempty(x: Any) -> bool:
    return isinstance(x, str) and bool(x.strip())


def validate_delivery_notes(shot: dict) -> list[str]:
    """Check optional notes only. No inference about emotions or backend support."""
    errors = []
    audio = shot.get('audio_plan')
    if not isinstance(audio, dict):
        return errors
    for group in ('native_spoken_lines', 'post_voices'):
        lines = audio.get(group, [])
        if not isinstance(lines, list):
            continue  # The parent validator reports the malformed array.
        for line in lines:
            if not isinstance(line, dict):
                continue
            note = line.get('delivery_note')
            if note is not None and not nonempty(note):
                errors.append('audio_plan: delivery_note must be null or nonblank text')
    return sorted(set(errors))


def render_native_line(line: dict) -> str:
    """Compile direction separately from exact speech, without vendor API claims."""
    note = line.get('delivery_note')
    if note is not None and not nonempty(note):
        raise ValueError('audio_plan: delivery_note must be null or nonblank text')
    prefix = '原生开口对白：' + line['speaker_description'] + '；声线：' + line['voice_description']
    if note is not None:
        prefix += '；单句语气指导（不朗读）：' + note
    return prefix + '；只说：' + json.dumps(line['text_spoken'], ensure_ascii=False)


def source_digest(shot: dict) -> str:
    # Rewrite audit is downstream of this compilation. All actual shot inputs
    # including insertion scope, ordered refs, audio and style remain bound.
    # External brain_binding is excluded to avoid a packet/hash cycle; the final
    # compiler/production gate verifies that binding against the full request.
    value = {k: v for k, v in shot.items() if k not in ('prompt9', 'rewrite_audit', 'brain_binding')}
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
        separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def insert_config_errors(shot: dict) -> list[str]:
    p = shot.get('insert_policy')
    if p is None:
        return []
    if not isinstance(p, dict) or p.get('kind') not in ('object_only', 'visible_part'):
        return ['insert_policy: object_only or visible_part required']
    errors = []
    aliases = p.get('offscreen_aliases')
    visible = p.get('visible_entity_ids')
    if not isinstance(aliases, list) or any(not nonempty(x) for x in aliases):
        errors.append('insert_policy: explicit offscreen_aliases array required, may be empty')
    if not isinstance(visible, list) or not visible or any(not nonempty(x) for x in visible):
        errors.append('insert_policy: nonempty visible_entity_ids required')
    if p.get('post_audio_separate') is not True:
        errors.append('insert_policy: off-picture audio must remain a separate post track')
    audio = shot.get('audio_plan', {})
    if not isinstance(audio, dict) or audio.get('native_spoken_lines'):
        errors.append('insert_policy: native spoken lines unsupported; preserve them as post audio')
    refs = shot.get('references', [])
    if not isinstance(refs, list):
        errors.append('insert_policy: reference list required')
    else:
        for ref in refs:
            if not isinstance(ref, dict):
                errors.append('insert_policy: malformed reference'); continue
            if ref.get('role') in ('identity', 'costume'):
                if p['kind'] == 'object_only' or ref.get('visible_part_only') is not True:
                    errors.append('insert_policy: irrelevant full-character reference')
    return errors


def inspect_insert(shot: dict, generated_prompt: str) -> list[str]:
    errors = insert_config_errors(shot)
    p = shot.get('insert_policy')
    if p is None or not isinstance(p, dict):
        return errors
    if not isinstance(generated_prompt, str):
        return errors + ['insert_policy: actual final prompt must be text']
    if OFFSCREEN_PERSON.search(generated_prompt):
        errors.append('insert_policy: off-frame person/location wording in model-facing prompt')
    aliases = p.get('offscreen_aliases', [])
    if isinstance(aliases, list):
        for alias in aliases:
            if nonempty(alias) and alias.casefold() in generated_prompt.casefold():
                # Keep the private alias out of the error text sent to models.
                errors.append('insert_policy: a private off-frame alias leaked into final prompt')
    return sorted(set(errors))


def inspect_prompt(shot: dict, generated_prompt: str) -> list[str]:
    """Retain frozen visible blocks and guard explicit invisible aliases.

    Exact native dialogue may mention an unseen person. Only that compiler-owned
    speech payload is exempt; captions, negative instructions and direction are
    still visual input. No people are inferred from arbitrary Chinese words.
    """
    errors = inspect_insert(shot, generated_prompt) + _ensemble.validate_shot(shot)
    bundle = shot.get('ensemble')
    if errors or bundle is None:
        return sorted(set(errors))
    if not isinstance(generated_prompt, str):
        return ['ensemble: actual final prompt must be text']
    windows = bundle['view_plan']['windows']
    image = shot.get('mode') not in {'video_i2v', 'video_reference'}
    if image:
        windows = windows[:1]
    visible = {r['entity_id'] for w in windows for r in w['entities']
               if r['visibility'] in _ensemble.VISIBLE}
    entities = bundle['start_state']['entities']
    private_aliases = {a.casefold() for eid, entity in entities.items()
                       if eid not in visible and entity['kind'] in {'character', 'group'}
                       for a in entity.get('aliases', [])}
    visual_prompt = generated_prompt
    audio = shot.get('audio_plan', {})
    if isinstance(audio, dict) and isinstance(audio.get('native_spoken_lines', []), list):
        for line in audio.get('native_spoken_lines', []):
            if isinstance(line, dict) and nonempty(line.get('text_spoken')):
                speech = '只说：' + json.dumps(line['text_spoken'], ensure_ascii=False)
                visual_prompt = visual_prompt.replace(speech, '只说：[已锁定对白]')
    # Frozen inventory can otherwise vanish from locked/audited prompt routes.
    # Check authored blocks, not guessed names; dialogue cannot stand in for
    # visual direction. Legal rewrites must be frozen in the source rows first.
    cursor = 0
    for index, block in enumerate(_ensemble.render_blocks(bundle, image), 1):
        position = visual_prompt.find(block, cursor)
        if position < 0:
            errors.append('ensemble: frozen visible block missing/changed/out of order: ' + str(index))
        else:
            cursor = position + len(block)
    folded = visual_prompt.casefold()
    for alias in private_aliases:
        # English identifier boundaries keep Ann distinct from Anna while
        # allowing adjacent Chinese direction, such as “不要画出Ann”.
        pattern = re.escape(alias) if not alias.isascii() else r'(?<![A-Za-z0-9_])' + re.escape(alias) + r'(?![A-Za-z0-9_])'
        checked = folded
        for window in windows:
            for row in window['entities']:
                if (row['visibility'] in _ensemble.VISIBLE
                        and alias in {a.casefold() for a in entities[row['entity_id']].get('aliases', [])}):
                    # A named photograph/reflection permits only its explicitly
                    # bound visible clause, never that person's name everywhere.
                    clause = _ensemble.render_entity_clause(row, image).casefold()
                    checked = checked.replace(clause, re.sub(pattern, '[已绑定可见内容]', clause))
        if re.search(pattern, checked):
            errors.append('ensemble: private invisible alias leaked into model-facing visual prompt')
    return sorted(set(errors))


def validate_nine(shot: dict) -> list[str]:
    errors = insert_config_errors(shot) + _ensemble.validate_shot(shot) + validate_delivery_notes(shot)
    p = shot.get('prompt9')
    if p is None:
        return errors
    if not isinstance(p, dict) or p.get('schema_version') != 'prompt9-1':
        return errors + ['prompt9: invalid schema']
    if shot.get('mode') not in {'video_i2v', 'video_reference'}:
        errors.append('prompt9: applies to video only, keep still frame prompts static')
    if p.get('status') != 'locked' or p.get('source_contract_sha256') != source_digest(shot):
        errors.append('prompt9: unlocked or stale source contract')
    dims = p.get('dimensions')
    if not isinstance(dims, dict) or set(dims) != set(DIMENSIONS):
        return errors + ['prompt9: exactly nine dimension records required']
    for key, item in dims.items():
        if not isinstance(item, dict) or item.get('state') not in ('locked', 'fillable', 'not_applicable'):
            errors.append('prompt9: invalid state: ' + key); continue
        if not nonempty(item.get('source')):
            errors.append('prompt9: source missing: ' + key)
        if key in DERIVED:
            if item.get('state') != 'locked' or item.get('source') != DERIVED[key] or item.get('text') not in (None, ''):
                errors.append('prompt9: derived dimension must not duplicate source text: ' + key)
        elif item.get('state') == 'not_applicable':
            if key == 'subject' or not nonempty(item.get('reason')) or item.get('text') not in (None, ''):
                errors.append('prompt9: invalid not_applicable dimension: ' + key)
        elif not nonempty(item.get('text')):
            errors.append('prompt9: empty applicable dimension: ' + key)
    style = shot.get('style_lock')
    if not isinstance(style, dict) or style.get('status') != 'locked' or not nonempty(style.get('prompt_sentence')):
        errors.append('prompt9: locked style sentence required')
    if not isinstance(shot.get('audio_plan'), dict):
        errors.append('prompt9: explicit audio_plan required, including silent cases')
    ambient = p.get('ambient_sound', '')
    if not isinstance(ambient, str):
        errors.append('prompt9: ambient_sound must be text; post dialogue stays out')
    if not errors:
        try:
            errors += inspect_prompt(shot, render_nine(shot, validate=False))
        except (KeyError, TypeError, ValueError) as exc:
            errors.append('prompt9: malformed source fields: ' + str(exc))
    return sorted(set(errors))


def render_nine(shot: dict, validate: bool = True) -> str:
    if validate:
        errors = validate_nine(shot)
        if errors:
            raise ValueError('; '.join(errors))
    p = shot['prompt9']; d = p['dimensions']
    refs = sorted(shot.get('references', []), key=lambda r: r['upload_index'])
    primary = next((r for r in refs if r.get('primary') is True), None)
    if shot.get('mode') == 'video_reference':
        parts = ['以下图片仅为独立资产参考，按镜头描述直接生成连续视频，不从任一图片起始。', shot.get('background_motion', '')]
        parts += [f'<Picture {r["upload_index"]}>的用途：{r["purpose"]}' for r in refs]
    elif primary is None:
        raise ValueError('prompt9: actual primary reference required')
    else:
        parts = [f'从输入图片{primary["upload_index"]}的已验收状态开始。只生成当前已锁定的单一连续镜头。']
        parts += [f'图片{r["upload_index"]}的用途：{r["purpose"]}' for r in refs]
    parts.append(LABELS['subject'] + '：' + d['subject']['text'])
    if shot.get('ensemble') is not None:
        parts.append(_ensemble.render_clauses(shot['ensemble']))
    if shot.get('camera_motion', 'fixed') == 'fixed':
        parts.append('镜头轨迹：保持已锁定固定机位和构图。')
    else:
        parts.append('镜头轨迹：' + shot['camera_motion_description'])
    for key in ('lighting', 'framing', 'space'):
        if d[key]['state'] != 'not_applicable':
            parts.append(LABELS[key] + '：' + d[key]['text'])
    if shot.get('relations'):
        parts.append('空间与接触锁：' + '；'.join(shot['relations']))
    if shot.get('preserve'):
        parts.append('必须保留：' + '；'.join(shot['preserve']))
    parts.append('画风：' + shot['style_lock']['prompt_sentence'])
    video = shot['video']
    for beat in video['action_beats']:
        parts.append(f'{beat["start_s"]}–{beat["end_s"]}秒：{beat["action"]}')
    parts.append('结束状态：' + video['end_state_description'])
    native = shot['audio_plan'].get('native_spoken_lines', [])
    if native:
        for line in native:
            parts.append(render_native_line(line))
    else:
        parts.append('本段不生成语音对白。')
    if p.get('ambient_sound'):
        parts.append('环境声音：' + p['ambient_sound'])
    if d['stability']['state'] != 'not_applicable':
        parts.append(LABELS['stability'] + '：' + d['stability']['text'])
    if shot.get('narrative_must_show'):
        parts.append('必须清楚可见：' + '；'.join(shot['narrative_must_show']))
    parts.append(f'时长：{video["duration_s"]}秒。沿用锁定画幅，不增加镜头或转场。')
    return '\n'.join(parts)
