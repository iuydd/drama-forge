#!/usr/bin/env python3
"""Offline review planning only. No image recognition, video decoding or API calls."""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any

HIGH_FLAGS = {'new_scene', 'critical_evidence', 'new_view', 'new_identity', 'first_use', 'handoff', 'stairs_in_motion',
              'occlusion', 'reflection', 'multi_actor_contact', 'fast_motion',
              'recent_defect', 'unclassified'}
MEDIUM_FLAGS = {'routine_motion', 'lighting_change', 'camera_motion'}
KNOWN_FLAGS = HIGH_FLAGS | MEDIUM_FLAGS
MINOR_CATEGORIES = {'noncritical_texture_variation', 'noncritical_edge_noise'}
CACHE_FIELDS = ('check_id', 'scope_sha256', 'dependency_sha256',
                'criteria_sha256', 'policy_sha256', 'reviewer_sha256')


def _integer(x: Any) -> bool:
    return type(x) is int


def _ranges(value: Any, n: int) -> list[list[int]]:
    if not isinstance(value, list):
        raise ValueError('Frame ranges must be an array.')
    result = []
    for pair in value:
        if (not isinstance(pair, list) or len(pair) != 2 or
                not all(_integer(i) for i in pair) or not 0 <= pair[0] <= pair[1] < n):
            raise ValueError('Invalid or out-of-bounds inclusive frame range.')
        result.append(pair[:])
    return result


def merge_ranges(ranges: list[list[int]]) -> list[list[int]]:
    merged: list[list[int]] = []
    for start, end in sorted(ranges):
        if merged and start <= merged[-1][1] + 1:
            merged[-1][1] = max(end, merged[-1][1])
        else:
            merged.append([start, end])
    return merged


def covers(actual: list[list[int]], required: list[list[int]]) -> bool:
    merged = merge_ranges(actual)
    return all(any(a <= s and b >= e for a, b in merged) for s, e in required)


def make_video_plan(total_frames: int, risk_flags: list[str],
                    event_ranges: list[list[int]], padding_frames: int = 2,
                    sampling_version: str = 'balanced-1') -> dict:
    """Frame indices come from actual decoded metadata, not duration * assumed fps.

    event_ranges are inclusive intervals containing ALL risky action/anomaly frames;
    they are not just a single guessed contact timestamp. Add actual PTS upstream.
    """
    if not _integer(total_frames) or not 1 <= total_frames <= 10_000_000:
        raise ValueError('Verified total_frames must be a positive bounded integer.')
    if not isinstance(risk_flags, list) or any(not isinstance(f, str) or f not in KNOWN_FLAGS for f in risk_flags):
        raise ValueError('Unknown risk flag. Use unclassified rather than silently low risk.')
    if not _integer(padding_frames) or not 0 <= padding_frames <= 1000:
        raise ValueError('Invalid padding_frames.')
    if sampling_version != 'balanced-1':
        raise ValueError('Unsupported sampling plan version.')
    events = merge_ranges(_ranges(event_ranges, total_frames))
    tier = 'high' if set(risk_flags) & HIGH_FLAGS else ('medium' if risk_flags else 'low')
    count = {'low': 5, 'medium': 9, 'high': 12}[tier]
    count = min(count, total_frames)
    points = sorted({round(i * (total_frames - 1) / max(1, count - 1)) for i in range(count)})
    dense = [[max(0, a-padding_frames), min(total_frames-1, b+padding_frames)] for a, b in events]
    # High risk without trusted localization cannot take the sparse path.
    if tier == 'high' and not events:
        dense = [[0, total_frames-1]]
    required = merge_ranges([[i, i] for i in points] + dense)
    return {'sampling_version': sampling_version, 'total_frames': total_frames,
            'risk_flags': sorted(set(risk_flags)), 'risk_tier': tier,
            'event_ranges': events, 'padding_frames': padding_frames,
            'required_semantic_ranges': required,
            'required_semantic_frame_count': sum(b-a+1 for a, b in required),
            'requires_full_decode': True, 'requires_temporal_overview': True,
            'guarantees_zero_missed_defects': False}


def validate_plan(plan: Any) -> list[str]:
    if not isinstance(plan, dict):
        return ['video_review_plan: missing object']
    try:
        expected = make_video_plan(plan.get('total_frames'), plan.get('risk_flags'),
                                   plan.get('event_ranges'), plan.get('padding_frames'),
                                   plan.get('sampling_version'))
    except (ValueError, TypeError) as exc:
        return [f'video_review_plan: {exc}']
    if expected != plan:
        return ['video_review_plan: modified/incomplete derived fields; recompute the plan']
    return []


def check_policy(policy: Any, kind: str) -> list[str]:
    if policy is None:
        return []  # Legacy projects remain strict unless explicitly migrated.
    if not isinstance(policy, dict):
        return ['quality_policy must be an object']
    mode = policy.get('review_mode', 'strict')
    if mode not in ('strict', 'balanced'):
        return ['quality_policy.review_mode: unknown mode']
    if 'allow_minor_findings' in policy and type(policy['allow_minor_findings']) is not bool:
        return ['quality_policy.allow_minor_findings: boolean required']
    errors = []
    if mode == 'balanced':
        categories = policy.get('allowed_minor_categories', [])
        if not isinstance(categories, list) or any(not isinstance(c, str) or c not in MINOR_CATEGORIES for c in categories):
            errors.append('quality_policy: unsupported minor waiver category')
        if kind == 'video':
            errors += validate_plan(policy.get('video_review_plan'))
    return errors


def check_balanced_coverage(coverage: Any, policy: dict) -> list[str]:
    errors = check_policy(policy, 'video')
    if errors:
        return errors
    if not isinstance(coverage, dict) or coverage.get('kind') != 'video' or coverage.get('basis') != 'risk_based':
        return ['coverage: explicit risk_based video report required']
    plan = policy['video_review_plan']
    n = plan['total_frames']
    if coverage.get('total_frames') != n or type(coverage.get('total_frames')) is not int:
        errors.append('coverage: actual frame count does not match frozen plan')
    try:
        decoded = _ranges(coverage.get('decoded_frame_ranges'), n)
        semantic = _ranges(coverage.get('semantic_frame_ranges'), n)
        if not covers(decoded, [[0, n-1]]):
            errors.append('coverage: full technical decode incomplete')
        if not covers(semantic, plan['required_semantic_ranges']):
            errors.append('coverage: planned semantic frames or critical event interval missing')
    except ValueError as exc:
        errors.append(f'coverage: {exc}')
    if coverage.get('temporal_reviewed') is not True or coverage.get('temporal_overview_scope') != 'entire_clip':
        errors.append('coverage: entire-clip temporal overview missing')
    if coverage.get('temporal_method') not in ('human_playback', 'native_video', 'sequential_frames'):
        errors.append('coverage: unknown temporal review method')
    if not isinstance(coverage.get('sampling_disclosure'), str) or not coverage['sampling_disclosure'].strip():
        errors.append('coverage: disclose actual temporal sampler; do not claim every frame was seen')
    # The caller MUST also verify these files and hashes, not just their presence.
    for key in ('decode_evidence', 'temporal_evidence', 'sampling_evidence'):
        if not isinstance(coverage.get(key), dict):
            errors.append(f'coverage: {key} missing')
    return errors


def may_waive_minor(finding: dict, policy: dict, required_checks: list[str]) -> bool:
    if policy.get('allow_minor_findings') is not True:
        return False
    if policy.get('review_mode', 'strict') != 'balanced':
        return True  # Preserve the legacy explicit waiver contract.
    check_id = finding.get('check_id')
    if not isinstance(check_id, str) or not check_id or check_id in required_checks:
        return False
    category = finding.get('category')
    allowed = policy.get('allowed_minor_categories', [])
    if (not isinstance(allowed, list) or not isinstance(category, str)
            or category not in MINOR_CATEGORIES or category not in allowed):
        return False
    if any(finding.get(key) is not False for key in (
        'normal_playback_noticeable', 'violates_lock', 'affects_narrative', 'affects_identity_or_geometry')):
        return False
    return isinstance(finding.get('waiver_evidence'), dict)


def cache_reusable(previous: dict, current: dict) -> bool:
    """A valid cache key is necessary, not visual evidence or permission to copy reports.

    scope_sha256 must be COMPUTED on unchanged bytes/ROI + transform, not supplied
    by the generator from a previous file. Global changed frames cannot be reused.
    """
    if previous.get('result') != 'PASS' or previous.get('evidence_verified') is not True:
        return False
    for key in CACHE_FIELDS:
        old = previous.get(key)
        if not isinstance(old, str) or not old or old != current.get(key):
            return False
        if key.endswith('sha256') and not re.fullmatch('[0-9a-f]{64}', old):
            return False
    return True


def pick_spot_checks(item_ids: list[str], batch_seed: str, fraction: float = 0.10) -> list[str]:
    """Pick extra deep checks; all items must already have their baseline checks.

    Freeze seed before the batch; do not resample after seeing candidate quality.
    At least one nonempty-batch item is selected even when fraction is zero.
    """
    if (not isinstance(item_ids, list) or any(not isinstance(i, str) or not i for i in item_ids)
            or len(set(item_ids)) != len(item_ids)):
        raise ValueError('Unique nonempty stable item IDs required.')
    if not isinstance(batch_seed, str) or not batch_seed:
        raise ValueError('A frozen batch seed is required.')
    if type(fraction) not in (int, float) or not math.isfinite(fraction) or not 0 <= fraction <= 1:
        raise ValueError('fraction must be finite in [0, 1].')
    count = min(len(item_ids), max(1, math.ceil(len(item_ids)*fraction))) if item_ids else 0
    return sorted(item_ids, key=lambda i: hashlib.sha256((batch_seed+'\0'+i).encode()).hexdigest())[:count]


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--frames', type=int, required=True)
    p.add_argument('--flags', default='[]', help='JSON array of risk flags')
    p.add_argument('--events', default='[]', help='JSON inclusive frame intervals')
    p.add_argument('--padding', type=int, default=2)
    args = p.parse_args()
    try:
        plan = make_video_plan(args.frames, json.loads(args.flags), json.loads(args.events), args.padding)
    except (ValueError, TypeError) as exc:
        p.exit(2, f'BLOCKED: {exc}\n')
    print(json.dumps(plan, ensure_ascii=False, indent=2, allow_nan=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
