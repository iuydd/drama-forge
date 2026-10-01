#!/usr/bin/env python3
"""Local FFmpeg helpers: measured animatic, ASR work-copy extraction, loudness.

No model download, ASR/TTS, paid request, lip-sync or upload. Requires real FFmpeg.
All outputs are new versioned files; no source/output overwrite is permitted.
"""
from __future__ import annotations
import argparse
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from typing import Any
from job_ledger import file_digest, store_without_overwrite


def run(args: list[str], timeout: int = 120) -> subprocess.CompletedProcess:
    if not shutil.which(args[0]):
        raise RuntimeError(f'required executable not installed: {args[0]}')
    p = subprocess.run(args, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=timeout)
    if p.returncode:
        raise RuntimeError(f'{args[0]} failed ({p.returncode}): {p.stderr[-4000:]}')
    return p


def probe(path: Path) -> dict:
    p = Path(path)
    if not p.is_file():
        raise ValueError('actual media file required')
    return json.loads(run(['ffprobe', '-v', 'error', '-show_streams', '-show_format',
                           '-of', 'json', str(p)]).stdout)


def check_ref(root: Path, record: dict) -> Path:
    if not isinstance(record, dict) or not isinstance(record.get('path'), str):
        raise ValueError('actual file reference required')
    raw = record['path']
    rel = Path(raw)
    if not raw or rel.is_absolute() or '\\' in raw or any(x in {'', '.', '..'} for x in raw.split('/')):
        raise ValueError('unsafe relative input path')
    p = root/rel
    if p.is_symlink() or not p.resolve().is_relative_to(root) or not p.is_file():
        raise ValueError('input missing or outside project')
    if file_digest(p) != record.get('sha256'):
        raise ValueError('input hash mismatch')
    return p


def duration(info: dict) -> float:
    try:
        n = float(info['format']['duration'])
    except (KeyError, TypeError, ValueError) as e:
        raise ValueError('actual media duration unavailable') from e
    if not math.isfinite(n) or n <= 0:
        raise ValueError('invalid actual media duration')
    return n


def output_available(root: Path, relative: str) -> None:
    p = Path(relative)
    if (not relative or p.is_absolute() or '\\' in relative
            or any(x in {'', '.', '..'} for x in relative.split('/'))):
        raise ValueError('unsafe output path')
    dest = root/p
    if dest.is_symlink() or not dest.resolve().is_relative_to(root):
        raise ValueError('output outside root')
    if dest.exists():
        raise FileExistsError('output already exists; choose a new version, never overwrite')


def animatic(manifest: dict, root: Path, output: str) -> dict:
    root = Path(root).resolve(strict=True)
    output_available(root, output)
    if manifest.get('schema_version') != 'animatic-1':
        raise ValueError('unsupported animatic schema')
    fps, width, height = (manifest.get('fps'), manifest.get('width'), manifest.get('height'))
    if type(fps) is not int or not 1 <= fps <= 120:
        raise ValueError('explicit integer preview fps required')
    if any(type(x) is not int or x <= 0 or x % 2 for x in (width, height)):
        raise ValueError('positive even preview dimensions required')
    shots = manifest.get('shots')
    if not isinstance(shots, list) or not shots:
        raise ValueError('nonempty ordered shots required')
    paths, ids, frame_counts = [], [], []
    for s in shots:
        if not isinstance(s, dict) or not isinstance(s.get('shot_id'), str) or not s['shot_id']:
            raise ValueError('shot_id required')
        if s['shot_id'] in ids or type(s.get('frames')) is not int or s['frames'] < 1:
            raise ValueError('unique shot IDs and positive integer frame counts required')
        ids.append(s['shot_id']); frame_counts.append(s['frames'])
        paths.append(check_ref(root, s.get('image')))
    audio = check_ref(root, manifest.get('temp_audio'))
    audio_probe = probe(audio)
    if not any(s.get('codec_type') == 'audio' for s in audio_probe.get('streams', [])):
        raise ValueError('real temporary dialogue track required')
    planned = sum(frame_counts)/fps
    if abs(duration(audio_probe)-planned) > 2/fps:
        raise ValueError('temporary track duration differs from plan; fix timeline, do not silently truncate')
    root.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.animatic-', dir=root) as temp_name:
        temp = Path(temp_name)
        for i, (image, frames) in enumerate(zip(paths, frame_counts)):
            vf = (f'scale={width}:{height}:force_original_aspect_ratio=decrease,'
                  f'pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1')
            run(['ffmpeg', '-hide_banner', '-nostdin', '-n', '-v', 'error',
                 '-loop', '1', '-framerate', str(fps), '-i', str(image), '-an',
                 '-vf', vf, '-frames:v', str(frames), '-c:v', 'libx264',
                 '-preset', 'veryfast', '-crf', '20', '-pix_fmt', 'yuv420p',
                 str(temp/f'part{i:06d}.mp4')])
        concat = temp/'sequence.txt'
        concat.write_text(''.join(f"file 'part{i:06d}.mp4'\n" for i in range(len(paths))), encoding='utf-8')
        final = temp/'preview.mp4'
        run(['ffmpeg', '-hide_banner', '-nostdin', '-n', '-v', 'error',
             '-f', 'concat', '-safe', '1', '-i', str(concat), '-i', str(audio),
             '-map', '0:v:0', '-map', '1:a:0', '-c:v', 'copy', '-c:a', 'aac',
             '-b:a', '192k', '-ar', '48000', '-af', 'apad', '-t', f'{planned:.9f}',
             '-movflags', '+faststart', str(final)])
        actual = probe(final)
        vs = next((s for s in actual.get('streams', []) if s.get('codec_type') == 'video'), {})
        if vs.get('width') != width or vs.get('height') != height or abs(duration(actual)-planned) > 2/fps+0.05:
            raise ValueError('rendered animatic does not match planned dimensions/duration')
        n = vs.get('nb_frames')
        if n is None or int(n) != sum(frame_counts):
            raise ValueError('rendered frame count differs from plan')
        stored = store_without_overwrite(final, root, output, file_digest(final))
    return {'status': 'ANIMATIC_RENDERED_NOT_REVIEWED', 'artifact': stored,
            'shot_ids': ids, 'frames': sum(frame_counts), 'fps': fps,
            'planned_duration_s': planned, 'actual_duration_s': duration(actual),
            'temp_audio': manifest['temp_audio'], 'temporary_voice_only': True,
            'comprehension_reviewed': False, 'motion_quality_reviewed': False}


def extract_audio(source: Path, root: Path, output: str) -> dict:
    """Create a mono 16 kHz PCM ASR work copy; preserve original media untouched."""
    root = Path(root).resolve(strict=True)
    output_available(root, output)
    if Path(output).suffix.lower() != '.wav':
        raise ValueError('ASR work copy must use .wav')
    info = probe(source)
    if not any(s.get('codec_type') == 'audio' for s in info.get('streams', [])):
        raise ValueError('actual source has no audio track')
    with tempfile.TemporaryDirectory(prefix='.audio-', dir=root) as td:
        p = Path(td)/'asr-work.wav'
        run(['ffmpeg', '-hide_banner', '-nostdin', '-n', '-v', 'error',
             '-i', str(Path(source).resolve()), '-map', '0:a:0', '-vn',
             '-ac', '1', '-ar', '16000', '-c:a', 'pcm_s16le', str(p)])
        result = store_without_overwrite(p, root, output, file_digest(p))
    return {'status': 'WORK_COPY_ONLY', 'artifact': result,
            'source_sha256': file_digest(Path(source)), 'original_audio_preserved': True,
            'note': 'Not a final mix. Adapter must retain source stream timing offsets.'}


def loudness(source: Path) -> dict:
    p = run(['ffmpeg', '-hide_banner', '-nostdin', '-n', '-i', str(Path(source).resolve()),
             '-vn', '-af', 'loudnorm=I=-16:TP=-1:LRA=7:print_format=json', '-f', 'null', '-'])
    candidates = re.findall(r'\{\s*"input_i".*?\}', p.stderr, flags=re.S)
    if not candidates:
        raise ValueError('loudness measurement JSON missing')
    raw = json.loads(candidates[-1])
    vals = {k: float(raw[k]) for k in ('input_i', 'input_tp', 'input_lra', 'input_thresh')}
    if not all(math.isfinite(v) for v in vals.values()):
        raise ValueError('nonfinite measurement (for example silence); do not mark PASS')
    return {'status': 'MEASURED_NOT_LISTENING_APPROVAL', 'source_sha256': file_digest(Path(source)),
            'integrated_lufs': vals['input_i'], 'true_peak_dbtp': vals['input_tp'],
            'lra_lu': vals['input_lra'], 'raw': raw,
            'note': 'Null output; no media modified. -16/-1 are filter working settings, not platform requirements.'}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='command', required=True)
    a = sub.add_parser('animatic')
    a.add_argument('--manifest', type=Path, required=True)
    a.add_argument('--root', type=Path, required=True)
    a.add_argument('--out', required=True)
    a = sub.add_parser('extract-audio')
    a.add_argument('--source', type=Path, required=True)
    a.add_argument('--root', type=Path, required=True)
    a.add_argument('--out', required=True)
    a = sub.add_parser('loudness'); a.add_argument('--source', type=Path, required=True)
    a = sub.add_parser('probe'); a.add_argument('--source', type=Path, required=True)
    a = p.parse_args()
    try:
        if a.command == 'animatic':
            result = animatic(json.loads(a.manifest.read_text(encoding='utf-8')), a.root, a.out)
        elif a.command == 'extract-audio':
            result = extract_audio(a.source, a.root, a.out)
        elif a.command == 'loudness':
            result = loudness(a.source)
        else:
            result = probe(a.source)
    except (OSError, ValueError, TypeError, KeyError, RuntimeError, StopIteration, subprocess.TimeoutExpired) as exc:
        print(json.dumps({'status': 'BLOCKED', 'error': str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
