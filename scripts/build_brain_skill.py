#!/usr/bin/env python3
"""Build the explicitly legacy Brain export for old, split-role projects.

Current production reads editable references through role_reading.py. This
compatibility export intentionally retains the original theory and cannot
overwrite those references or assets/source.md.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
THEORY_KEYS = tuple(f'r{i:02}' for i in range(10)) + ('runtime-blind-brief',)
LEGACY_NOTICE = ('> LEGACY COMPATIBILITY EXPORT — 仅供明确选择旧版 Brain/Agent 分离流程的历史项目。\n'
                 '> 不代表当前一体流程、剧本规则或 MiniMax-Hailuo 参考图视频路径；当前流程不要读取或发送此文件。\n\n').encode('utf-8')


def original_theory(root: Path) -> bytes:
    raw = (root / 'assets/legacy-integrated-3.1.2-public.md').read_bytes()
    provenance = json.loads((root / 'THEORY_PROVENANCE.json').read_text(encoding='utf-8'))
    if hashlib.sha256(raw).hexdigest() != provenance['source_sha256']:
        raise ValueError('original integrated source differs from the restoration baseline')
    parts = {m[1]: m[0] for m in re.finditer(
        rb'<a id="([^"]+)"></a>.*?(?=<a id="|\Z)', raw, re.S)}
    recorded = {row['anchor']: row for row in provenance['sections']}
    selected = []
    for key in THEORY_KEYS:
        piece = parts[key.encode('ascii')]
        row = recorded[key]
        if len(piece) != row['bytes'] or hashlib.sha256(piece).hexdigest() != row['sha256']:
            raise ValueError('original chapter drift: ' + key)
        selected.append(piece)
    result = b''.join(selected)
    if hashlib.sha256(result).hexdigest() != provenance['theory_sha256']:
        raise ValueError('original theory manifest mismatch')
    return result


def expected(root: Path) -> bytes:
    theory = original_theory(root)
    if (root / 'assets/legacy-theory-3.1.2-public.md').read_bytes() != theory:
        raise ValueError('verbatim theory copy has been abbreviated or modified')
    result = (
        LEGACY_NOTICE + (root / 'assets/brain-intro.md').read_bytes()
        + (root / 'assets/brain-workflow.md').read_bytes()
        + theory
    )
    # The standalone upload does not need unuploaded local files.
    if re.search(rb'\]\((?!https?://|#)[^)]+\)', result):
        raise ValueError('standalone brain unexpectedly contains external local links')
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--write', action='store_true')
    mode.add_argument('--check', action='store_true')
    args = parser.parse_args()
    try:
        data = expected(ROOT)
        path = ROOT / 'assets/brain-skill.md'
        changed = not path.exists() or path.read_bytes() != data
        if args.write and changed:
            path.write_bytes(data)
    except (OSError, KeyError, TypeError, ValueError) as exc:
        parser.exit(2, str(exc) + '\n')
    print('UPDATED' if changed and args.write else ('DRIFT' if changed else 'IN_SYNC'))
    return 1 if changed and args.check else 0


if __name__ == '__main__':
    raise SystemExit(main())
