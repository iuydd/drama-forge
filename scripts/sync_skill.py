#!/usr/bin/env python3
"""Synchronize derived skill documents. No production stage or review is run."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools/production-ops/scripts'))
from execution_control import parse_sections

MODULES = [
    [
        "r00",
        "00-contract.md",
        "工作契约"
    ],
    [
        "r01",
        "01-story.md",
        "故事与优势"
    ],
    [
        "r02",
        "02-opening-causality.md",
        "开头与因果"
    ],
    [
        "r03",
        "03-performance.md",
        "对白与表演"
    ],
    [
        "r04",
        "04-adaptation.md",
        "原著改编"
    ],
    [
        "r05",
        "05-space-assets.md",
        "空间与素材"
    ],
    [
        "r06",
        "06-storyboard-prompts.md",
        "分镜与提示词"
    ],
    [
        "r07",
        "07-animatic-audio.md",
        "预演与声音"
    ],
    [
        "r08",
        "08-editing.md",
        "剪辑与后期"
    ],
    [
        "r09",
        "09-review-repair.md",
        "审核与返修"
    ],
    [
        "r10",
        "10-execution.md",
        "调度与费用"
    ],
    [
        "r11",
        "11-handoff.md",
        "资料与交接"
    ],
    [
        "runtime-blind-brief",
        "blind-review.md",
        "隔离盲看"
    ]
]
ROUTES = frozenset(('startup', 'story_original', 'story_adapt', 'story_review',
                    'board', 'assets', 'prompt_image', 'prompt_video', 'dispatch',
                    'recover', 'review', 'blind', 'edit', 'delivery'))


def entry_versions(root):
    """Read the entrypoint's flat version metadata without a YAML dependency."""
    entry = (root / 'SKILL.md').read_text(encoding='utf-8')
    front = re.match(r'\A---\n(.*?)\n---(?:\n|\Z)', entry, re.S)
    blocks = re.findall(r'^metadata:[ \t]*\n((?:[ \t]+[^\n]*\n|[ \t]*\n)*)',
                        front[1] + '\n' if front else '', re.M)
    if len(blocks) != 1:
        raise ValueError('SKILL.md: one metadata block required')
    rows = re.findall(r'^  (version|package_version|content_version):[ \t]*(.*)$',
                      blocks[0], re.M)
    if len(rows) != 3 or {key for key, _ in rows} != {'version', 'package_version', 'content_version'}:
        raise ValueError('SKILL.md: unique version, package_version and content_version required')
    versions = {}
    for key, value in rows:
        scalar = re.fullmatch(r'''(['"]?)([A-Za-z0-9][A-Za-z0-9.+-]*)\1[ \t]*(?:#.*)?''', value)
        if not scalar:
            raise ValueError('SKILL.md: invalid ' + key)
        versions[key] = scalar[2]
    if versions['version'] != versions['package_version']:
        raise ValueError('SKILL.md: version must match package_version')
    return versions


def expected_files(root):
    """Derive all outputs before writing, so malformed sources cannot half-sync."""
    raw_map = (root / 'config/stage-reading-map.v3.json').read_bytes()
    config = json.loads(raw_map)
    stages = config['stages']
    names = {anchor: (name, title) for anchor, name, title in MODULES}
    sections = {}
    for anchor, name, _ in MODULES:
        text = (root / 'references' / name).read_text(encoding='utf-8')
        parsed = parse_sections(text)
        if set(parsed) != {anchor} or parsed[anchor]['text'] != text or not text.endswith('\n'):
            raise ValueError('chapter must start with its sole anchor and end with newline: ' + name)
        sections[anchor] = parsed[anchor]
    if set(stages) != ROUTES:
        raise ValueError('expected 12 modules, blind brief and 14 routes')
    if config.get('schema_version') != 'reading-map-1':
        raise ValueError('unsupported reading map')
    for stage, anchors in stages.items():
        if (not isinstance(anchors, list) or not anchors or
                any(not isinstance(a, str) or a not in names for a in anchors) or
                len(anchors) != len(set(anchors))):
            raise ValueError('invalid route: ' + stage)
        if (stage == 'blind') != ('runtime-blind-brief' in anchors):
            raise ValueError('blind instructions must stay isolated')
    if stages['blind'] != ['runtime-blind-brief']:
        raise ValueError('blind route must contain only its independent brief')

    seen = set()

    entry = '# 章节阅读路线\n\n当前一体流程先读 [执行阅读清单](agent-reading-guide.md)。本表由 config/stage-reading-map.v3.json 生成，供阶段阅读凭据兼容用途；具体动作见 config/role-reading-map.json。当前章节是可编辑规则来源，历史原稿只用于追溯。\n\n只读当前阶段；独立盲看只接收自己的指令。\n\n| 阶段 | 完整模块 |\n|---|---|\n' + ''.join('| `' + stage + '` | pending |\n' for stage in stages)
    seen.clear()
    def entry_row(match):
        stage = match[1]
        if stage not in stages or stage in seen:
            raise ValueError('unknown or duplicate entry route: ' + stage)
        seen.add(stage)
        links = []
        for anchor in stages[stage]:
            name, title = names[anchor]
            label = '独立盲看' if anchor == 'runtime-blind-brief' else anchor[1:] + ' ' + title
            links.append('[' + label + '](' + name + '#' + anchor + ')')
        return '| `' + stage + '` | ' + '、'.join(links) + ' |'
    entry = re.sub(r'^\| `([a-z_]+)` \| [^\n]+$', entry_row, entry, flags=re.M)
    if seen != ROUTES:
        raise ValueError('entry route table is incomplete')
    from role_reading import safe_file, load_map
    role_map = load_map(root)
    versions = entry_versions(root)
    for key in ('package_version', 'content_version'):
        role_map[key] = versions[key]
    version = role_map['content_version']
    readme, count = re.subn(r'^(当前版本 \*\*)[^*\n]+(\*\*)',
                           lambda match: match[1] + versions['package_version'] + match[2],
                           (root / 'README.md').read_text(encoding='utf-8'), flags=re.M)
    if count != 1:
        raise ValueError('README.md: one current version marker required')
    source = ('---\nversion: "' + version + '"\n---\n\n'
              '# 当前生产规则汇编\n\n此文件由 scripts/sync_skill.py 从 references/00–11 和 blind-review.md 生成。请编辑章节后同步，不要在此修改。\n\n'
              + ''.join(sections[anchor]['text'] for anchor, _, _ in MODULES))
    outputs = {'assets/source.md': source.encode(), 'README.md': readme.encode(),
               'references/reading-routes.md': entry.encode(),
               'tools/production-ops/templates/stage-reading-map.json': raw_map}
    # Refresh identities from current files; never restore old content over edits.
    for document in role_map['documents'].values():
        document['sha256'] = hashlib.sha256(safe_file(root, document['path']).read_bytes()).hexdigest()
    outputs['config/role-reading-map.json'] = (json.dumps(role_map, ensure_ascii=False, indent=2) + '\n').encode()
    return outputs


def synchronize(root, write=False):
    outputs = expected_files(root)
    changed = [name for name, data in outputs.items()
               if not (root / name).is_file() or (root / name).read_bytes() != data]
    if write:
        for name in changed:
            (root / name).write_bytes(outputs[name])
    return changed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--check', action='store_true')
    mode.add_argument('--write', action='store_true')
    args = parser.parse_args()
    try:
        changed = synchronize(ROOT, write=args.write)
    except (ValueError, KeyError, TypeError, OSError) as exc:
        parser.exit(2, str(exc) + '\n')
    print(json.dumps({'status': 'UPDATED' if args.write and changed else
                      ('DRIFT' if changed else 'IN_SYNC'), 'files': changed},
                     ensure_ascii=False))
    return 1 if changed and args.check else 0


if __name__ == '__main__':
    raise SystemExit(main())
