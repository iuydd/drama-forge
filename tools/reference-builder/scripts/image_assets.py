#!/usr/bin/env python3
"""Inspect or explicitly crop existing local images. No image generation/recognition."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from reference_tools import inspect_image, file_digest


def crop_image(source: Path, box: list[int], out: Path, overwrite: bool = False) -> dict:
    from PIL import Image
    if source.resolve() == out.resolve(): raise ValueError('Never overwrite the source image')
    if out.suffix.lower() != '.png': raise ValueError('Crop output must be PNG')
    if out.exists() and not overwrite: raise FileExistsError('Output already exists')
    inspect_image(source)
    with Image.open(source) as im:
        if im.getexif().get(274, 1) not in (None, 1):
            raise ValueError('Normalize EXIF orientation and review before cropping')
        if len(box) != 4 or any(type(x) is not int for x in box): raise ValueError('Box requires four integers')
        x0, y0, x1, y1 = box
        if not (0 <= x0 < x1 <= im.width and 0 <= y0 < y1 <= im.height):
            raise ValueError('Crop box outside source or empty')
        result = im.crop(tuple(box))
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open('wb' if overwrite else 'xb') as stream:
            result.save(stream, format='PNG')
    return {'status': 'CANDIDATE', 'source_sha256': file_digest(source), 'crop_box_xyxy': box,
            'path': str(out), 'sha256': file_digest(out), 'review_required': True,
            'notice': 'Geometric crop only; no new viewpoint or visual correctness claimed'}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='command', required=True)
    s = sub.add_parser('inspect'); s.add_argument('image', type=Path)
    s = sub.add_parser('crop'); s.add_argument('image', type=Path)
    s.add_argument('--box', nargs=4, type=int, required=True)
    s.add_argument('--out', type=Path, required=True); s.add_argument('--overwrite', action='store_true')
    args = p.parse_args()
    try:
        r = inspect_image(args.image) if args.command == 'inspect' else crop_image(args.image, args.box, args.out, args.overwrite)
        print(json.dumps(r, ensure_ascii=False, indent=2)); return 0
    except (OSError, ValueError, ImportError) as exc:
        print(json.dumps({'status': 'BLOCKED', 'error': str(exc)}, ensure_ascii=False)); return 2

if __name__ == '__main__': raise SystemExit(main())
