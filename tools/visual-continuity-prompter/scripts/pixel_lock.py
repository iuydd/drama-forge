#!/usr/bin/env python3
"""Same-canvas, lossless PNG region protection. Requires Pillow, no model calls.

This proves only that decoded RGBA pixels outside the explicit allowed mask stay
unchanged. It does not prove semantic correctness, lighting, masks, or anatomy.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
from typing import Any
try:
    from PIL import Image, ImageChops
except ImportError as e:
    raise SystemExit('Pillow is required for pixel_lock.py; install it in your chosen environment first.') from e


def file_hash(p: Path) -> str:
    h = hashlib.sha256()
    with p.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def open_image(p: Path) -> Image.Image:
    with Image.open(p) as image:
        if getattr(image, 'n_frames', 1) != 1:
            raise ValueError('Animated/multi-frame input is not supported by this still-image tool')
        if image.getexif().get(274, 1) != 1:
            raise ValueError('Normalize EXIF orientation before creating canonical assets/masks')
        image.load()
        result = image.convert('RGBA')
        result.info.update(image.info)
        return result


def open_mask(p: Path, size: tuple[int, int], binary: bool) -> Image.Image:
    with Image.open(p) as image:
        if image.size != size:
            raise ValueError('Mask size must exactly match the canvas; no implicit resizing')
        if image.mode not in ('1', 'L'):
            raise ValueError('Mask must be grayscale L or 1; no automatic RGB interpretation')
        if image.getexif().get(274, 1) != 1:
            raise ValueError('Mask EXIF orientation must be normalized')
        mask = image.convert('L')
        if binary and any(value not in (0, 255) for _, value in mask.getcolors(256)):
            raise ValueError('Allowed mask must be binary: white=editable, black=protected')
        return mask


def difference_stats(base: Image.Image, candidate: Image.Image, allowed: Image.Image) -> dict[str, Any]:
    if base.size != candidate.size or base.size != allowed.size:
        raise ValueError('Images and masks must use the same canvas')
    delta = ImageChops.difference(base.convert('RGBA'), candidate.convert('RGBA'))
    bands = delta.split()
    max_channel = bands[0]
    for band in bands[1:]:
        max_channel = ImageChops.lighter(max_channel, band)
    changed = max_channel.point(lambda x: 255 if x else 0)
    protected = ImageChops.invert(allowed)
    protected_change = ImageChops.multiply(changed, protected)
    protected_delta = ImageChops.multiply(max_channel, protected)
    pixels = base.width * base.height
    editable = allowed.histogram()[255]
    count = protected_change.histogram()[255]
    return {'canvas': [base.width, base.height], 'editable_pixels': editable,
            'protected_pixels': pixels-editable, 'editable_fraction': editable/pixels,
            'changed_protected_pixels': count,
            'max_protected_channel_error': protected_delta.getextrema()[1],
            'protected_rgba_identical': count == 0,
            'semantic_quality_verified': False}


def compose(base_path: Path, candidate_path: Path, allowed_path: Path, out_path: Path,
            blend_path: Path | None = None, mode: str = 'patch') -> dict:
    sources = [base_path, candidate_path, allowed_path] + ([blend_path] if blend_path else [])
    if out_path.resolve() in {p.resolve() for p in sources}:
        raise ValueError('Output must not overwrite a source or mask')
    if out_path.suffix.lower() != '.png':
        raise ValueError('Output must be lossless .png, not JPEG or video')
    if mode not in ('patch', 'overlay'):
        raise ValueError('mode must be patch or overlay')
    base, candidate = open_image(base_path), open_image(candidate_path)
    if base.size != candidate.size:
        raise ValueError('Base and candidate size mismatch; no implicit scaling/warping')
    for key in ('icc_profile',):
        a, b = base.info.get(key), candidate.info.get(key)
        if a and b and a != b:
            raise ValueError('Different embedded color profiles; normalize explicitly before canonicalizing')
    allowed = open_mask(allowed_path, base.size, binary=True)
    if allowed.getextrema() == (255, 255):
        raise ValueError('All-white mask protects nothing; refuse the scene-lock claim')
    blend = open_mask(blend_path, base.size, binary=False) if blend_path else allowed
    outside = ImageChops.multiply(blend, ImageChops.invert(allowed))
    if outside.getextrema()[1] != 0:
        raise ValueError('Feather/blend mask extends outside the approved editable region')
    if mode == 'patch':
        nonopaque = ImageChops.invert(candidate.getchannel('A'))
        if ImageChops.multiply(nonopaque, blend.point(lambda x: 255 if x else 0)).getextrema()[1]:
            raise ValueError('Patch candidate must be opaque in edited region; use overlay for RGBA foreground')
        patch = candidate
    else:
        patch = Image.alpha_composite(base, candidate)
    result = Image.composite(patch, base, blend)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    kwargs = {'icc_profile': base.info['icc_profile']} if base.info.get('icc_profile') else {}
    result.save(out_path, format='PNG', **kwargs)
    roundtrip = open_image(out_path)
    stats = difference_stats(base, roundtrip, allowed)
    if not stats['protected_rgba_identical']:
        raise RuntimeError('Protected region invariant failed after PNG round trip')
    stats.update({'mode': mode, 'output': str(out_path), 'output_sha256': file_hash(out_path),
                  'base_sha256': file_hash(base_path), 'candidate_sha256': file_hash(candidate_path),
                  'allowed_mask_sha256': file_hash(allowed_path),
                  'blend_mask_sha256': file_hash(blend_path) if blend_path else None,
                  'scope': 'Decoded RGBA pixels outside allowed mask only; masks/alignment/visual quality are not certified.'})
    return stats


def compare(base_path: Path, candidate_path: Path, allowed_path: Path) -> dict:
    base, candidate = open_image(base_path), open_image(candidate_path)
    if base.size != candidate.size:
        raise ValueError('Same-view same-canvas comparison only')
    allowed = open_mask(allowed_path, base.size, binary=True)
    if allowed.getextrema() == (255, 255):
        raise ValueError('No protected region')
    return difference_stats(base, candidate, allowed)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='command', required=True)
    for name in ('compose', 'compare'):
        a = sub.add_parser(name)
        a.add_argument('--base', required=True, type=Path)
        a.add_argument('--candidate', required=True, type=Path)
        a.add_argument('--allowed-mask', required=True, type=Path)
        a.add_argument('--report', type=Path)
        if name == 'compose':
            a.add_argument('--blend-mask', type=Path)
            a.add_argument('--out', required=True, type=Path)
            a.add_argument('--mode', choices=('patch', 'overlay'), default='patch')
    a = p.parse_args()
    try:
        # Avoid report paths overwriting any input, mask or composed output.
        forbidden = [a.base, a.candidate, a.allowed_mask]
        if a.command == 'compose':
            forbidden += [a.out] + ([a.blend_mask] if a.blend_mask else [])
        if a.report and a.report.resolve() in {v.resolve() for v in forbidden}:
            raise ValueError('Report must not overwrite an image or mask')
        if a.command == 'compose':
            r = compose(a.base, a.candidate, a.allowed_mask, a.out, a.blend_mask, a.mode)
        else:
            r = compare(a.base, a.candidate, a.allowed_mask)
        if a.report:
            a.report.parent.mkdir(parents=True, exist_ok=True)
            a.report.write_text(json.dumps(r, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        print(json.dumps(r, ensure_ascii=False, indent=2))
        return 0 if r['protected_rgba_identical'] else 2
    except (OSError, ValueError, RuntimeError) as e:
        print(json.dumps({'status': 'BLOCKED', 'error': str(e)}, ensure_ascii=False))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
