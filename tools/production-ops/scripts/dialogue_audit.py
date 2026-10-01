#!/usr/bin/env python3
"""Compare already acquired speech observations. No ASR or voice inference is done.

Usage: python3 dialogue_audit.py dialogue-contract.json observations.json
Exit 0 = no text/coverage discrepancies in supplied records, NOT audio approval.
Exit 1 = targeted review required. Exit 2 = malformed input.
"""
from __future__ import annotations
import argparse
from difflib import SequenceMatcher
import json
import math
from pathlib import Path
import re
import unicodedata
from typing import Any

PUNCT = set('，。！？；：、,!?;:"\'“”‘’（）()【】[]《》<>…')
KINDS = {'spoken', 'inner', 'voiceover', 'system'}


def normalize(text: str) -> str:
    """Conservative typography-only normalization. Preserve signs and decimals."""
    if not isinstance(text, str):
        raise ValueError('text must be a string')
    text = unicodedata.normalize('NFKC', text)
    result = []
    for i, char in enumerate(text):
        decimal = (char == '.' and i > 0 and i+1 < len(text)
                   and text[i-1].isdigit() and text[i+1].isdigit())
        if char.isspace() or char in PUNCT or (char == '.' and not decimal):
            continue
        result.append(char)
    return ''.join(result)


def compare_text(expected: str, observed: str) -> dict:
    a, b = normalize(expected), normalize(observed)
    differences = []
    for tag, i, j, k, l in SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag != 'equal':
            differences.append({'type': tag, 'expected_span': [i, j],
                                'observed_span': [k, l], 'expected': a[i:j],
                                'observed': b[k:l]})
    return {'match': a == b, 'normalized_expected': a, 'normalized_observed': b,
            'differences': differences,
            'note': 'Diff spans are normalized text indices, not audio timestamps or CER.'}


def finite(value: Any) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


def audit(contract: dict, observations: dict) -> dict:
    if not isinstance(contract, dict) or not isinstance(observations, dict):
        raise ValueError('objects required')
    lines = contract.get('lines')
    rows = observations.get('lines')
    if not isinstance(lines, list) or not isinstance(rows, list):
        raise ValueError('lines arrays required')
    issues, output = [], []
    expected_ids, by_id, used = set(), {}, set()
    raw_ids = observations.get('speech_segment_ids')
    if not isinstance(raw_ids, list) or any(not isinstance(x, str) or not x for x in raw_ids):
        raise ValueError('speech_segment_ids: nonempty strings required (array may be empty)')
    if len(raw_ids) != len(set(raw_ids)):
        raise ValueError('duplicate raw speech segment IDs')
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get('line_id'), str):
            raise ValueError('invalid observation line')
        if row['line_id'] in by_id:
            raise ValueError('duplicate line observation')
        by_id[row['line_id']] = row
    for line in lines:
        if not isinstance(line, dict):
            raise ValueError('invalid expected line')
        lid = line.get('line_id')
        if not isinstance(lid, str) or not lid or lid in expected_ids:
            raise ValueError('unique nonempty expected line IDs required')
        expected_ids.add(lid)
        if line.get('source_kind') not in KINDS or not normalize(line.get('text_spoken')):
            raise ValueError('source_kind and nonempty text_spoken required')
        for key in ('speaker_id', 'voice_id'):
            if not isinstance(line.get(key), str) or not line[key]:
                raise ValueError(f'expected {key} required')
        if type(line.get('lipsync_required')) is not bool:
            raise ValueError('lipsync_required must be explicit')
        if line['source_kind'] == 'inner' and line['lipsync_required']:
            raise ValueError('inner speech cannot require spoken-word lip sync')
        row = by_id.get(lid)
        local = []
        if row is None:
            output.append({'line_id': lid, 'text_match': False, 'issues': ['missing_line']})
            issues.append(f'{lid}: missing_line')
            continue
        if not isinstance(row.get('text_observed'), str):
            raise ValueError('text_observed required')
        cmp = compare_text(line['text_spoken'], row['text_observed'])
        if not cmp['match']:
            local.append('text_difference_requires_listen')
        correction = row.get('asr_correction_reason')
        if correction is not None:
            if not isinstance(correction, str) or not correction.strip():
                local.append('asr_correction_reason_missing')
            evidence = row.get('targeted_listening_evidence')
            if not isinstance(evidence, list) or not evidence or any(
                    not isinstance(item, dict) or not isinstance(item.get('path'), str) or not item['path'].strip()
                    or not isinstance(item.get('sha256'), str) or not re.fullmatch(r'[0-9a-f]{64}', item['sha256'])
                    for item in evidence):
                local.append('asr_correction_listening_evidence_missing')
        for key in ('speaker_id', 'voice_id', 'source_kind'):
            if row.get(key) is None:
                local.append(key + '_unknown')
            elif row.get(key) != line[key]:
                local.append(key + '_mismatch')
        if row.get('speaker_verified') is not True:
            local.append('speaker_evidence_missing')
        if row.get('source_verified') is not True:
            local.append('source_evidence_missing')
        if line['lipsync_required'] and row.get('mouth_review') != 'PASS':
            local.append('lipsync_not_verified')
        if line['source_kind'] == 'inner' and row.get('inner_mouth_not_speaking') is not True:
            local.append('inner_mouth_behavior_not_verified')
        start, end = row.get('start_s'), row.get('end_s')
        if not finite(start) or not finite(end) or start < 0 or end <= start:
            local.append('invalid_audio_timing')
        else:
            window = line.get('allowed_window_s')
            if window is not None:
                if (not isinstance(window, list) or len(window) != 2
                        or not all(finite(v) for v in window) or window[0] < 0 or window[1] <= window[0]):
                    raise ValueError('allowed_window_s invalid')
                if start < window[0] or end > window[1]:
                    local.append('outside_frozen_time_window')
        segs = row.get('segment_ids')
        if not isinstance(segs, list) or not segs:
            local.append('alignment_segments_missing')
        else:
            for sid in segs:
                if not isinstance(sid, str) or sid not in raw_ids:
                    local.append('alignment_segment_unknown')
                    continue
                if sid in used:
                    local.append('alignment_segment_reused')
                used.add(sid)
        output.append({'line_id': lid, 'text_match': cmp['match'],
                       'differences': cmp['differences'], 'start_s': start,
                       'end_s': end, 'issues': sorted(set(local))})
        issues.extend(f'{lid}: {item}' for item in sorted(set(local)))
    for lid in sorted(set(by_id)-expected_ids):
        issues.append(f'{lid}: unexpected_line')
    unassigned = sorted(set(raw_ids)-used)
    if unassigned:
        issues.append('unassigned_speech_segments')
    if observations.get('whole_audio_transcribed') is not True:
        issues.append('whole_audio_coverage_missing')
    if observations.get('review_status') == 'FAIL':
        issues.append('listening_review_failed')
    if observations.get('unexpected_speech'):
        issues.append('unexpected_speech_requires_listen')
    return {'status': 'REVIEW_REQUIRED' if issues else 'RECORDS_MATCH_NOT_AUDIO_APPROVAL',
            'lines': output, 'unassigned_speech_segments': unassigned,
            'issues': issues, 'audio_was_listened_to_by_this_tool': False,
            'guarantees_correct_speech': False,
            'note': 'ASR differences need targeted listening; matching text cannot prove pronunciation, intelligibility, speaker or lip correctness. Listening evidence references are shape-checked only; no files or audio are examined by this tool.'}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('contract', type=Path)
    p.add_argument('observations', type=Path)
    args = p.parse_args()
    try:
        result = audit(json.loads(args.contract.read_text(encoding='utf-8')),
                       json.loads(args.observations.read_text(encoding='utf-8')))
    except (OSError, ValueError, TypeError) as exc:
        print(json.dumps({'status': 'BLOCKED', 'error': str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return 1 if result['issues'] else 0

if __name__ == '__main__':
    raise SystemExit(main())
