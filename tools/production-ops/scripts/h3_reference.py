"""MiniMax H3 reference-video contract and offline native payload export.

Matches the inspected local h3studio Client.submit_video contract. No HTTP,
credentials, submission, or implicit conversion to a keyframe occurs here.
"""
from __future__ import annotations
import base64
import math
import re
from pathlib import Path


def is_reference(request: dict) -> bool:
    return request.get('video_input') == 'references' or request.get('mode') == 'video_reference'


def reference_errors(request: dict) -> list[str]:
    errors = []
    refs = request.get('inputs', request.get('references'))
    if not isinstance(refs, list) or not 1 <= len(refs) <= 6 or any(not isinstance(r, dict) for r in refs):
        return ['H3 references: 1..6 ordered asset images required']
    if request.get('video_input', 'references') != 'references' or request.get('image_mode', 'reference') != 'reference':
        errors.append('H3 references: conflicting video/image input mode')
    if request.get('mode') != 'video_reference':
        errors.append('H3 references: explicit mode=video_reference required; conflicting/unknown modes are forbidden')
    if any(key in request for key in ('start_frame', 'frame', 'previous_end', 'end_frame')):
        errors.append('H3 references: frame inputs are forbidden')
    if any(type(r.get('upload_index')) is not int for r in refs) or [r.get('upload_index') for r in refs] != list(range(1, len(refs) + 1)):
        errors.append('H3 references: array order must equal contiguous upload_index 1..N')
    if any(r.get('role') != 'asset_ref' or r.get('primary') is True for r in refs):
        errors.append('H3 references: asset_ref inputs only, no primary/start frame')
    ids = [r.get('asset_id') for r in refs]
    required = request.get('required_asset_ids')
    if (any(not isinstance(x, str) or not x for x in ids) or len(set(ids)) != len(ids)
            or not isinstance(required, list) or not required
            or any(not isinstance(x, str) or not x for x in required)
            or len(set(required)) != len(required) or set(required) != set(ids)):
        errors.append('H3 references: all frozen required_asset_ids must occur exactly once')
    prompt = request.get('prompt', request.get('locked_prompt', ''))
    if not isinstance(prompt, str): prompt = ''
    pictures = {int(n) for n in re.findall(r'<Picture ([0-9]+)>', prompt)}
    if pictures != set(range(1, len(refs) + 1)):
        errors.append('H3 references: prompt must identify every uploaded <Picture N> without unknown indices')
    motion = request.get('background_motion')
    if not isinstance(motion, str) or not motion.strip() or motion not in prompt:
        errors.append('H3 references: literal background_motion must appear in prompt')
    return errors


def native_payload(request: dict, root: Path) -> dict:
    """Export local bytes; no server profile/capability lookup or spend authorization."""
    from brain_handoff import verify_record
    errors = reference_errors(request)
    if errors: raise ValueError('; '.join(errors))
    out = request.get('output_spec', {})
    for key in ('profile', 'res', 'aspect'):
        if (not isinstance(out.get(key), str) or not out[key].strip()
                or re.search(r'\{\{|\$\{|<[^>]+>|\b(?:UNKNOWN|TODO|TBD|UNVERIFIED|PLACEHOLDER|REPLACE[_ -]?ME)\b|待(?:确认|填写|核实)|请(?:填写|替换)|未(?:设置|确认|核实)',out[key],re.IGNORECASE)):
            raise ValueError('H3 requires explicit non-placeholder output_spec.' + key)
    seconds = out.get('seconds')
    if type(seconds) not in (int, float) or not math.isfinite(seconds) or seconds <= 0:
        raise ValueError('H3 requires positive finite output_spec.seconds')
    seed = out.get('seed', 0)
    if type(seed) is not int: raise ValueError('H3 output_spec.seed must be integer')
    root = root.resolve(strict=True)
    images = []
    for ref in request['inputs']:
        errors = verify_record(ref, root)
        if errors: raise ValueError('; '.join(errors))
        data = (root / ref['path']).read_bytes()
        if data.startswith(b'\x89PNG\r\n\x1a\n'): mime = 'image/png'
        elif data.startswith(b'\xff\xd8\xff'): mime = 'image/jpeg'
        elif data[:4] == b'RIFF' and data[8:12] == b'WEBP': mime = 'image/webp'
        else: raise ValueError('H3 reference must contain PNG, JPEG or WebP image bytes')
        images.append('data:' + mime + ';base64,' + base64.b64encode(data).decode())
    return {'prompt': request['prompt'], 'profile': out['profile'], 'aspect': out['aspect'],
            'res': out['res'], 'seconds': float(seconds), 'seed': seed,
            'image_mode': 'reference', 'images': images}
