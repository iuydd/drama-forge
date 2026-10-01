#!/usr/bin/env python3
"""Report dependencies for selected operations; never install or contact services."""
import argparse
import importlib.util
import json
import shutil
import sys

DEPENDENCIES = {
    'text': (),
    'image': (('python', 'PIL', 'Pillow'),),
    'schema': (('python', 'jsonschema', 'jsonschema'),),
    'probe': (('command', 'ffprobe', 'ffprobe'),),
    'media': (('command', 'ffmpeg', 'ffmpeg'), ('command', 'ffprobe', 'ffprobe')),
}


def check(operations):
    selected = sorted({item for operation in operations for item in DEPENDENCIES[operation]})
    checks = []
    for kind, lookup, name in selected:
        found = (importlib.util.find_spec(lookup) is not None if kind == 'python'
                 else shutil.which(lookup) is not None)
        checks.append({'dependency': name, 'available': found})
    return {'status': 'AVAILABLE' if all(c['available'] for c in checks) else 'MISSING',
            'operations': list(dict.fromkeys(operations)), 'python': sys.executable,
            'checks': checks, 'installed': False, 'connected': False,
            'scope': 'Dependency discovery only; not runtime or production verification.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operations', nargs='+', choices=tuple(DEPENDENCIES))
    result = check(parser.parse_args().operations)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['status'] == 'AVAILABLE' else 1


if __name__ == '__main__':
    raise SystemExit(main())

