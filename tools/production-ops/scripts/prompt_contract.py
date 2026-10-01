#!/usr/bin/env python3
"""Brain-authored intent -> backend-specific text, without creative rewriting.

Not a semantic model. Checks only explicit facts/resources, conservative obvious
contradictions and completeness of a separately media-bound human/model review.
No network calls. JSON IDs are never silently substituted for visual prose.
"""
from __future__ import annotations
from copy import deepcopy
import math
import re
from typing import Any
from brain_handoff import digest, text, verify_record

DIMENSIONS = {'subject', 'camera_motion', 'lighting', 'choreography', 'framing',
              'space', 'style', 'sound', 'stability'}
KINDS = {'context', 'camera', 'action', 'gaze', 'performance', 'speech',
         'ambient', 'invariant', 'evidence', 'preference'}
MODES = {'image_new', 'image_edit', 'video_i2v', 'video_reference', 'video_t2v'}
STRATEGIES = {'full_scene', 'edit_delta', 'motion_focused'}
SEMANTIC_COVERAGE = {'prompt_state', 'priority_conflicts', 'reference_roles',
                     'action_feasibility', 'visible_inventory', 'backend_fit'}


def obvious_contradictions(prompt: str) -> list[str]:
    """Deliberately narrow lint. Absence of findings does NOT prove consistency."""
    if not isinstance(prompt, str): return ['prompt: text required']
    errors = []
    # Same explicitly named object, frozen side, simultaneous opposed relocation.
    freeze = re.search(r'([\u4e00-\u9fffA-Za-z0-9_]{1,16})保持在([^。；\n]{0,32})(左|右)侧[，, ]*位置不变', prompt)
    if freeze:
        obj, side = freeze.group(1), freeze.group(3)
        other = '右' if side == '左' else '左'
        if re.search(r'同时[^。\n]{0,8}(?:同一个|同一只|同一辆|同一张)?' + re.escape(obj) + r'[^。\n]{0,20}移到[^。\n]{0,20}' + other + r'侧', prompt):
            errors.append('prompt: same object simultaneously fixed and moved to opposite side')
    # Only an immediate simultaneous connector is unambiguous; do not cross a later action.
    if re.search(r'\bkeep\s+the\s+(\w+)\s+fixed\b[ \t]*[,;:]?[ \t]*(?:(?:and|while)[ \t]+)?simultaneously\s+move\s+(?:that|the same)\s+\1\b', prompt, re.I):
        errors.append('prompt: simultaneous fixed/move contradiction')
    return errors


def valid_ids(value: Any, nonempty: bool = False) -> bool:
    return isinstance(value, list) and (bool(value) or not nonempty) and all(text(v) for v in value) and len(value) == len(set(value))


def resource_conflicts(rows: Any) -> list[str]:
    """One exclusive effector cannot perform unrelated simultaneous operations.

    A brain-approved shared group allows coordinated actions such as a thumb
    and index finger holding one assembly. Natural nonexclusive motion is not
    incorrectly treated as a grasp. Time is relative planning time, not evidence.
    """
    if not isinstance(rows, list): return ['resources: array required']
    errors, valid = [], []
    for row in rows:
        if not isinstance(row, dict): errors.append('resources: malformed operation'); continue
        if any(not text(row.get(k)) for k in ('actor_id', 'effector', 'action_id')):
            errors.append('resources: actor/effector/action required'); continue
        a, b = row.get('start'), row.get('end')
        if any(type(t) not in (float, int) or not math.isfinite(t) for t in (a, b)) or not 0 <= a < b:
            errors.append('resources: invalid half-open interval'); continue
        if type(row.get('exclusive')) is not bool: errors.append('resources: explicit exclusivity required'); continue
        valid.append(row)
    for i, a in enumerate(valid):
        for b in valid[i+1:]:
            if (a['actor_id'], a['effector']) != (b['actor_id'], b['effector']): continue
            if not (a['exclusive'] and b['exclusive']): continue
            if max(a['start'], b['start']) >= min(a['end'], b['end']): continue
            group = a.get('shared_group')
            shared = text(group) and group == b.get('shared_group') and text(a.get('shared_approval')) and a.get('shared_approval') == b.get('shared_approval')
            if a['action_id'] != b['action_id'] and not shared:
                errors.append('resources: conflicting exclusive operations on ' + a['actor_id'] + '/' + a['effector'])
    return errors


def validate_ir(ir: Any, backend: Any) -> list[str]:
    errors = []
    if not isinstance(ir, dict) or ir.get('schema_version') != 'prompt-ir-1': return ['prompt IR: unsupported/missing intent']
    if not isinstance(backend, dict) or backend.get('schema_version') != 'prompt-backend-1': return ['prompt IR: explicit backend adapter required']
    if not text(backend.get('profile_id')) or ir.get('backend_profile_id') != backend.get('profile_id'):
        errors.append('prompt IR: backend identity mismatch')
    if ir.get('mode') not in MODES or backend.get('mode') != ir.get('mode'):
        errors.append('prompt IR: generation mode mismatch')
    strategy = backend.get('strategy')
    if strategy not in STRATEGIES: errors.append('prompt IR: unsupported adapter strategy')
    if strategy == 'motion_focused' and ir.get('mode') not in {'video_i2v', 'video_reference'}: errors.append('prompt IR: motion-only route requires image-to-video')
    if strategy == 'edit_delta' and ir.get('mode') != 'image_edit': errors.append('prompt IR: edit route requires image editing')
    if type(backend.get('native_audio')) is not bool: errors.append('prompt IR: native audio ability unresolved')
    if backend.get('speech_format', 'literal') not in {'literal', 'colon'}: errors.append('prompt IR: unsupported speech serialization')
    if not text(ir.get('primary_goal')): errors.append('prompt IR: primary on-screen goal missing')
    dimensions = ir.get('dimensions')
    if not isinstance(dimensions, dict) or set(dimensions) != DIMENSIONS or any(not text(v) for v in dimensions.values()):
        errors.append('prompt IR: nine internal decisions must reference facts or explain non-applicability')
    if ir.get('unresolved_conflicts') != []: errors.append('prompt IR: resolve competing hard requirements before freeze')
    clauses = ir.get('clauses')
    if not isinstance(clauses, list) or not clauses or any(not isinstance(c, dict) for c in clauses):
        return errors + ['prompt IR: authored clauses required']
    ids = [c.get('id') for c in clauses]
    if not valid_ids(ids, True): return errors + ['prompt IR: unique clause IDs required']
    for c in clauses:
        if c.get('kind') not in KINDS or not text(c.get('text')) or type(c.get('required')) is not bool:
            errors.append('prompt IR: typed authored clause/text/requirement missing')
        for k in ('read_keys', 'write_keys'):
            if not valid_ids(c.get(k, [])): errors.append('prompt IR: malformed fact binding')
        if c.get('provided_by_reference') is True and not text(c.get('reference_asset_id')):
            errors.append('prompt IR: reference-covered context needs actual asset ID')
        if c.get('kind') == 'speech':
            if not backend.get('native_audio'): errors.append('prompt IR: native speech unsupported; choose approved post route')
            if not text(c.get('text_spoken')) or not text(c.get('speaker')):
                errors.append('prompt IR: exact spoken text and speaker required')
            elif c['text_spoken'] not in c['text']:
                errors.append('prompt IR: speech clause must preserve exact text')
            elif backend.get('speech_format') == 'colon':
                # Convert only known wrappers; never discard unstructured direction.
                spoken, speaker = c['text_spoken'], c['speaker']
                wrappers = [spoken, '只说：' + spoken, speaker + '说：' + spoken,
                            speaker + ' says: ' + spoken]
                if text(c.get('delivery')):
                    wrappers += [w + '\nDelivery, not spoken: ' + c['delivery'] for w in wrappers]
                if c['text'] not in wrappers:
                    errors.append('prompt IR: colon speech requires an exact supported wrapper; '
                                  'move extra guidance to speaker/delivery or separate clauses: ' + c['id'])
        if ir.get('mode', '').startswith('image') and c.get('kind') in {'action', 'speech'}:
            errors.append('prompt IR: still image must represent one state, not animate/speak')
    priority = ir.get('priority', {})
    if not isinstance(priority, dict): return errors + ['prompt IR: priority object required']
    hard, soft = priority.get('hard', []), priority.get('soft', [])
    required = {c['id'] for c in clauses if c.get('required') is True}
    if not valid_ids(hard, True) or not valid_ids(soft) or set(hard) != required or set(hard) & set(soft) or not set(soft).issubset(ids):
        errors.append('prompt IR: priorities must preserve all hard clauses and not contradict them')
    must_show = ir.get('must_show', [])
    if not valid_ids(must_show, True) or not set(must_show).issubset(required):
        errors.append('prompt IR: core visible evidence must be a hard clause')
    invariant_keys = set(ir.get('invariant_keys', [])) if valid_ids(ir.get('invariant_keys', [])) else set()
    for c in clauses:
        if invariant_keys.intersection(c.get('write_keys', [])):
            errors.append('prompt IR: approved invariant also mutated: ' + c['id'])
    errors += resource_conflicts(ir.get('resources', []))
    visual_texts = []
    for c in clauses:
        content = c.get('text', '')
        if not text(content): continue
        spoken = c.get('text_spoken')
        if c.get('kind') == 'speech':
            # Exempt only the uniquely bound payload, never surrounding direction.
            if text(spoken) and content.count(spoken) == 1:
                content = content.replace(spoken, '[已锁定对白]', 1)
            visual_texts.extend(c[k] for k in ('speaker', 'delivery') if text(c.get(k)))
        visual_texts.append(content)
    errors += obvious_contradictions('\n'.join(visual_texts))
    return sorted(set(errors))


def compile_ir(ir: dict, backend: dict) -> dict:
    errors = validate_ir(ir, backend)
    if errors: raise ValueError('; '.join(errors))
    emitted, omitted, texts = [], [], []
    for c in ir['clauses']:
        omit = (backend['strategy'] in {'motion_focused', 'edit_delta'} and c['kind'] == 'context'
                and c.get('provided_by_reference') is True and c['required'] is False)
        if omit:
            omitted.append({'id': c['id'], 'reason': 'already visually supplied by approved reference', 'asset_id': c['reference_asset_id']}); continue
        content = c['text']
        if c['kind'] == 'speech' and backend.get('speech_format') == 'colon':
            # The words are NOT rewritten; only the backend-specific wrapper changes.
            content = c['speaker'] + ' says: ' + c['text_spoken']
        if c['kind'] == 'speech' and text(c.get('delivery')):
            directive = 'Delivery, not spoken: ' + c['delivery']
            spoken_spans = [m.span() for m in re.finditer(re.escape(c['text_spoken']), content)]
            # Deduplicate only the complete serialized block outside spoken text.
            # A substring or a line spoken as dialogue is not delivery guidance.
            existing = any(not any(a <= m.start() and m.end() <= b for a, b in spoken_spans)
                           for m in re.finditer(r'(?m)^' + re.escape(directive) + r'$', content))
            if not existing:
                content += '\n' + directive
        emitted.append(c['id'])
        if content not in texts: texts.append(content)  # exact-only de-duplication
    if not set(ir['priority']['hard']).issubset(emitted): raise ValueError('prompt IR: adapter lost hard requirement')
    prompt = '\n'.join(texts)
    if any(c['kind'] == 'speech' and c['text_spoken'] not in prompt for c in ir['clauses']):
        raise ValueError('prompt IR: adapter altered speech')
    limit = backend.get('max_prompt_bytes')
    if limit is not None and (type(limit) is not int or limit <= 0): raise ValueError('prompt IR: verified positive prompt limit required')
    if limit is not None and len(prompt.encode('utf-8')) > limit:
        raise ValueError('prompt IR: input exceeds backend limit; return to brain, never truncate hard facts')
    return {'prompt': prompt, 'prompt_sha256': digest(prompt), 'intent_sha256': digest(ir),
            'adapter_sha256': digest(backend), 'emitted': emitted, 'omitted': omitted,
            'semantic_quality_verified': False, 'real_model_tested': False}


def validate_shot_ir(shot: dict, backend: dict) -> list[str]:
    ir = shot.get('prompt_ir')
    errors = validate_ir(ir, backend)
    if errors: return errors
    aliases = {'video_i2v':'video_i2v', 'video_reference':'video_reference', 'edit_same_view':'image_edit', 'new_view':'image_new'}
    if ir['mode'] != aliases.get(shot.get('mode')): errors.append('prompt IR: shot execution mode differs')
    uploaded = {r.get('asset_id') for r in shot.get('references', [])}
    for c in ir['clauses']:
        if c.get('provided_by_reference') is True and c['reference_asset_id'] not in uploaded:
            errors.append('prompt IR: context omitted without corresponding uploaded reference')
    result = compile_ir(ir, backend)
    if result['prompt'] != shot.get('locked_prompt'): errors.append('prompt IR: frozen text differs from deterministic backend compilation')
    return errors


def semantic_review_errors(task: dict, root) -> list[str]:
    r = task.get('semantic_review')
    if not isinstance(r, dict): return ['brain: v4.2 requires a real semantic review record']
    errors = []
    if r.get('request_sha256') != task.get('request_sha256') or r.get('result') != 'PASS': errors.append('brain: semantic review missing/failed/stale')
    if not text(r.get('reviewer_id')) or not text(r.get('observation')): errors.append('brain: actual semantic review details required')
    if not isinstance(r.get('coverage'), list) or not SEMANTIC_COVERAGE.issubset(r['coverage']): errors.append('brain: semantic coverage incomplete')
    errors += ['brain semantic evidence: ' + e for e in verify_record(r.get('evidence'), root)]
    return errors
