#!/usr/bin/env python3
"""Supplemental production gates. Validates local records, not media semantics.

Usage: production_gates.py --spec spec.json --reports reports.json --root PROJECT
Do not replace the existing visual gate with this gate. Require BOTH where stated.
A PASS report must originate from a real inspector. Hashes do not prove honesty.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

REQUIRED = {
    'pre_video': {'input_gate', 'start_frame_gate', 'voice_plan', 'style_lock',
                  'animatic', 'comprehension', 'recovery_check', 'batch_authorization'},
    'shot_edit': {'visual_video', 'dialogue', 'speaker_source', 'lip_sync', 'burnt_text'},
    'final_delivery': {'shot_coverage', 'final_comprehension', 'dialogue_coverage', 'mix',
                       'burnt_text_subtitles', 'delivery_spec', 'rights_manifest'},
    'publish': {'delivery_gate', 'release_policy', 'ai_disclosure',
                'publication_authorization', 'rights_clearance'},
}


def digest(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False,
                         separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def file_sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda: f.read(1024*1024), b''):
            h.update(b)
    return h.hexdigest()


def finite(x: Any) -> bool:
    return type(x) in (float, int) and math.isfinite(x)


def _verify_record(record: Any, root: Path, digest_file) -> list[str]:
    if not isinstance(record, dict) or not isinstance(record.get('path'), str):
        return ['file record missing']
    raw = record['path']
    p = Path(raw)
    if (not raw or p.is_absolute() or '\\' in raw
            or any(v in {'', '.', '..'} for v in raw.split('/'))):
        return ['unsafe file path']
    target = root/p
    if target.is_symlink() or not target.resolve().is_relative_to(root):
        return ['file path escapes project']
    if not target.is_file() or target.stat().st_size == 0:
        return ['file missing or empty: ' + raw]
    sha = record.get('sha256')
    if not isinstance(sha, str) or digest_file(target) != sha:
        return ['file hash mismatch: ' + raw]
    return []



def verify_record(record: Any, root: Path) -> list[str]:
    return _verify_record(record, root, file_sha)


class _DigestSnapshot:
    """Reuse bytes only within one gate; a changing input invalidates the gate."""

    def __init__(self):
        self.files = {}

    @staticmethod
    def fingerprint(path):
        s = path.stat()
        return (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)

    def __call__(self, path):
        path = path.absolute()
        before = self.fingerprint(path)
        if path in self.files:
            previous, digest = self.files[path]
            if before != previous:
                raise ValueError('file changed during gate: ' + str(path))
            return digest
        digest = file_sha(path)
        if self.fingerprint(path) != before:
            raise ValueError('file changed during gate: ' + str(path))
        self.files[path] = (before, digest)
        return digest

    def check_unchanged(self):
        for path, (before, _) in self.files.items():
            if self.fingerprint(path) != before:
                raise ValueError('file changed during gate: ' + str(path))


def strings(value: Any, name: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(s, str) or not s for s in value):
        raise ValueError(name + ': string list required')
    if len(value) != len(set(value)):
        raise ValueError(name + ': duplicates')
    return value


def gate(spec: dict, reports: list, root: Path) -> dict:
    root = Path(root).resolve(strict=True)
    if not root.is_dir() or not isinstance(spec, dict) or not isinstance(reports, list):
        raise ValueError('project directory, spec object, and reports array required')
    if spec.get('schema_version') != 'production-ops-1' or spec.get('action') not in REQUIRED:
        raise ValueError('unsupported schema/action')
    digests = _DigestSnapshot()

    def verify(record, project_root):
        return _verify_record(record, project_root, digests)

    action = spec['action']
    blockers = verify(spec.get('subject'), root)
    subject = spec.get('subject') if isinstance(spec.get('subject'), dict) else {}
    contracts = spec.get('contracts')
    if not isinstance(contracts, list) or not contracts:
        blockers.append('frozen contract files required')
    else:
        for c in contracts:
            blockers.extend(verify(c, root))
    if type(spec.get('is_adaptation')) is not bool or type(spec.get('uses_upscale')) is not bool:
        blockers.append('explicit adaptation/upscale routing required')
    lines = strings(spec.get('line_ids'), 'line_ids')
    shot_ids = strings(spec.get('shot_ids'), 'shot_ids')
    facts = strings(spec.get('comprehension_fact_ids'), 'comprehension_fact_ids')
    if action in {'pre_video', 'final_delivery'} and (not shot_ids or not facts):
        blockers.append('episode/batch shots and essential comprehension facts required')
    req = set(REQUIRED[action])
    reference_preflight = action == 'pre_video' and spec.get('video_input') == 'references'
    if reference_preflight:
        req.remove('start_frame_gate')
        req.add('reference_assets')
        if spec.get('ensemble_required') is not True:
            blockers.append('reference video requires whole-shot asset bindings')
    policy = spec.get('policy_version')
    if policy not in (None, '4.0.0', '4.1.0', '4.2.0'):
        blockers.append('unsupported production policy_version')
    fidelity_context = {}
    fidelity_required = spec.get('fidelity_required', False)
    if type(fidelity_required) is not bool:
        blockers.append('fidelity_required must be boolean')
    fidelity_action = fidelity_required is True and action in {'pre_video', 'shot_edit', 'final_delivery'}
    if policy in {'4.0.0', '4.1.0', '4.2.0'} and action in {'pre_video', 'shot_edit', 'final_delivery'}:
        for flag in ('brain_required', 'fidelity_required', 'execution_required'):
            if spec.get(flag) is not True:
                blockers.append('v4: cannot disable required ' + flag)
        if action in {'pre_video', 'shot_edit'} and spec.get('ensemble_required') is not True:
            blockers.append('v4: cannot disable ensemble gate')
        if action == 'final_delivery':
            for flag in ('editing_required', 'bridges_required', 'presentation_required'):
                if spec.get(flag) is not True:
                    blockers.append('v4: cannot disable required ' + flag)
    continuity_context = {}
    continuity_required = spec.get('continuity_required', False)
    if type(continuity_required) is not bool:
        blockers.append('continuity_required must be boolean')
    continuity_action = continuity_required is True and action in {'pre_video', 'shot_edit', 'final_delivery'}
    if policy in {'4.1.0', '4.2.0'} and action in {'pre_video', 'shot_edit', 'final_delivery'}:
        if continuity_required is not True:
            blockers.append('v4.1: cannot disable required continuity state gate')
    if continuity_action:
        if fidelity_action is not True:
            blockers.append('sequence: existing fidelity gate is required')
        try:
            from sequence_continuity import load_bindings as load_sequence
            continuity_context, se = load_sequence(spec, root, verify)
            blockers.extend(se)
        except (ImportError, OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
            blockers.append('sequence binding unavailable: ' + str(exc))
    if fidelity_action:
        if action == 'final_delivery' and spec.get('editing_required') is not True:
            blockers.append('fidelity: final review requires existing edit_cut_review')
        try:
            from fidelity_contract import load_bindings as load_fidelity
            fidelity_context, fe = load_fidelity(spec, root, verify)
            blockers.extend(fe)
        except (ImportError, OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
            blockers.append('fidelity binding unavailable: ' + str(exc))
    if spec.get('is_adaptation') and action in {'pre_video', 'final_delivery'}:
        req.add('adaptation_trace')
    if spec.get('uses_upscale') and action == 'final_delivery':
        req.add('upscale_review')
    editing = spec.get('editing_required', False)
    if type(editing) is not bool:
        blockers.append('editing_required must be explicit boolean when present')
    editing_action = editing is True and action == 'final_delivery'
    edit_sha = None
    if editing_action:
        req.update({'edit_timeline', 'edit_cut_review'})
        edit_record = spec.get('edit_timeline')
        blockers.extend(verify(edit_record, root))
        if isinstance(edit_record, dict):
            edit_sha = edit_record.get('sha256')
        cut_ids = strings(spec.get('cut_ids'), 'cut_ids')
        event_ids = strings(spec.get('required_event_ids'), 'required_event_ids')
        if not event_ids:
            blockers.append('edit required events must be frozen before final review')
        if not blockers:
            try:
                from edit_timeline import validate as validate_edit
                timeline = json.loads((root/edit_record['path']).read_text(encoding='utf-8'))
                edit_result = validate_edit(timeline)
                if timeline.get('status') != 'LOCKED' or edit_result['status'] != 'STRUCTURE_OK':
                    blockers.append('actual edit timeline invalid or unlocked')
                elif edit_result['cut_ids'] != cut_ids or edit_result['required_event_ids'] != event_ids:
                    blockers.append('cut/event scope differs from actual frozen timeline')
            except (ImportError, OSError, ValueError, TypeError, KeyError) as exc:
                blockers.append('cannot verify actual edit timeline: ' + str(exc))
    # v3.1: bind event/UI/subtitle presentation inside the same edit_cut_review.
    presentation_context = {}
    presentation_required = spec.get('presentation_required', False)
    if type(presentation_required) is not bool:
        blockers.append('presentation_required must be boolean')
    presentation_action = presentation_required is True and action == 'final_delivery'
    if presentation_action:
        if editing is not True:
            blockers.append('presentation requires the existing editing gate')
        pr_errors = verify(spec.get('edit_timeline'), root)
        blockers.extend(pr_errors)
        if not pr_errors:
            try:
                from presentation_checks import resolve
                pt = json.loads((root/spec['edit_timeline']['path']).read_text(encoding='utf-8'))
                resolved = resolve(pt)
                if resolved['status'] != 'STRUCTURE_OK' or pt.get('presentation',{}).get('status') != 'LOCKED':
                    blockers.extend(['presentation invalid or unlocked'] + resolved['errors'])
                else:
                    expected_cues = strings(spec.get('presentation_cue_ids'), 'presentation_cue_ids')
                    expected_orders = strings(spec.get('presentation_order_ids'), 'presentation_order_ids')
                    if expected_cues != resolved['cue_ids'] or expected_orders != resolved['order_ids']:
                        blockers.append('presentation scope differs from frozen production specification')
                    presentation_context = {'timeline':pt, 'resolved':resolved}
            except (ImportError, OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
                blockers.append('presentation binding unavailable: '+str(exc))
    # v2.8: paired observations reuse the existing edit_cut_review; no new model call.
    bridge_context = {}
    bridges_required = spec.get('bridges_required', False)
    if type(bridges_required) is not bool:
        blockers.append('bridges_required must be boolean')
    bridge_action = bridges_required is True and action == 'final_delivery'
    if bridge_action:
        if editing is not True:
            blockers.append('paired bridges require the existing editing gate')
        try:
            from cut_bridges import load_binding
            bridge_context, be = load_binding(spec, root, verify)
            blockers.extend(be)
        except (ImportError, OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
            blockers.append('paired bridges binding unavailable: ' + str(exc))
    # v2.7 per-shot scene continuity. Aggregate inside existing G1/G2 checks;
    # not an additional visual-model call. Old specs remain explicitly legacy.
    ensemble_context = {}
    ensemble_required = spec.get('ensemble_required', False)
    if type(ensemble_required) is not bool:
        blockers.append('ensemble_required must be boolean')
    ensemble_action = ensemble_required is True and action in {'pre_video', 'shot_edit'}
    if ensemble_action:
        if not reference_preflight: req.add('ensemble_continuity')
        try:
            from ensemble_gate import load_bindings
            ensemble_context, ee = load_bindings(spec, root, verify)
            blockers.extend(ee)
        except (ImportError, OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
            blockers.append('ensemble: actual bindings could not be verified: ' + str(exc))
    # Optional v2.4 path; new templates turn it on. Legacy projects are not
    # silently relabelled as complying with the new execution policy.
    execution_required = spec.get('execution_required', False)
    if type(execution_required) is not bool:
        blockers.append('execution_required must be boolean')
    if execution_required is True:
        binding_record = spec.get('execution_binding')
        binding_errors = verify(binding_record, root)
        blockers += ['execution: ' + e for e in binding_errors]
        if not binding_errors:
            try:
                from execution_control import check_reading
                binding = json.loads((root/binding_record['path']).read_text(encoding='utf-8'))
                if binding.get('schema_version') != 'execution-binding-1':
                    blockers.append('execution: invalid binding schema')
                if (not spec.get('episode_id') or binding.get('active_episode') != spec.get('episode_id')
                        or binding.get('target_episode') != spec.get('episode_id')):
                    blockers.append('execution: current-episode scope mismatch')
                if binding.get('actor_role') != 'coordinator':
                    blockers.append('execution: only trusted coordinator may commit production action')
                expected_stage = {'pre_video':'dispatch', 'shot_edit':'review',
                                  'final_delivery':'delivery', 'publish':'delivery'}[action]
                if binding.get('stage') != expected_stage:
                    blockers.append('execution: wrong reading stage')
                file_errors = []
                for field in ('skill', 'routes', 'reading_receipt'):
                    file_errors += verify(binding.get(field), root)
                blockers += ['execution: ' + e for e in file_errors]
                if not file_errors:
                    skill_path = root/binding['skill']['path']
                    routes = json.loads((root/binding['routes']['path']).read_text(encoding='utf-8'))
                    receipt = json.loads((root/binding['reading_receipt']['path']).read_text(encoding='utf-8'))
                    blockers += ['execution: ' + e for e in check_reading(skill_path, routes, receipt,
                        expected_stage, binding.get('actor_id',''), binding.get('task_scope',''))]
                if action == 'pre_video':
                    packages = binding.get('video_prompt_packages')
                    if not isinstance(packages, list) or not packages:
                        blockers.append('execution: compiled nine-dimension video packages missing')
                    else:
                        package_shots = []
                        for record in packages:
                            pe = verify(record, root)
                            blockers += ['execution: ' + e for e in pe]
                            if pe:
                                continue
                            package = json.loads((root/record['path']).read_text(encoding='utf-8'))
                            package_shots.append(package.get('shot_id'))
                            if spec.get('brain_required') is True:
                                from brain_handoff import check_request
                                if package.get('policy_version') != (policy or '4.0.0'):
                                    blockers.append('brain: legacy prompt package cannot pass v4 dispatch')
                                br = check_request(package.get('brain_binding'),
                                    package.get('brain_request'), root, verify)
                                blockers.extend(br['errors'])
                                actual = package.get('brain_request')
                                if not isinstance(actual, dict) or actual.get('prompt') != package.get('prompt'):
                                    blockers.append('brain: actual package prompt differs from approved request')
                                if isinstance(actual, dict):
                                    actual_inputs = [{k: ref.get(k) for k in
                                        ('asset_id','role','upload_index','path','sha256')}
                                        for ref in package.get('input_order', []) if isinstance(ref, dict)]
                                    if (actual.get('inputs') != actual_inputs or
                                            actual.get('output_spec') != package.get('output_spec') or
                                            actual.get('shot_id') != package.get('shot_id') or
                                            actual.get('mode') != package.get('mode')):
                                        blockers.append('brain: package input/output scope differs from frozen request')
                                if fidelity_action:
                                    fc = fidelity_context.get(package.get('shot_id'), {})
                                    if package.get('fidelity_contract') != fc.get('record'):
                                        blockers.append('brain: compiled/observed fidelity contract differs')
                            if continuity_action:
                                cc = continuity_context.get(package.get('shot_id'), {})
                                if package.get('continuity_plan') != cc.get('record'):
                                    blockers.append('sequence: compiled/observed plan differs')
                                elif cc and cc['shots'][package['shot_id']]['continuity_clause'] not in package.get('prompt', ''):
                                    blockers.append('sequence: actual compiled prompt lost frozen spatial clause')
                            if ensemble_action:
                                ec = ensemble_context.get(package.get('shot_id'), {})
                                if reference_preflight and package.get('brain_request') != ec.get('request'):
                                    blockers.append('ensemble: reference preflight reviewed a different exact request')
                                if (not ec or package.get('ensemble_used') is not True
                                        or package.get('ensemble_sha256') != digest(ec['bundle'])):
                                    blockers.append('ensemble: video prompt package lacks matching whole-scene context')
                            if (package.get('status') != 'READY' or not (package.get('prompt9_used') is True or (policy == '4.2.0' and package.get('prompt_ir_used') is True))
                                    or not isinstance(package.get('prompt'), str) or not package['prompt'].strip()):
                                blockers.append('execution: video package not ready or missing nine dimensions')
                        if package_shots != shot_ids:
                            blockers.append('execution: ordered video package coverage mismatch')
            except (ImportError, OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
                blockers.append('execution binding could not be verified: ' + str(exc))
    snapshot = digest(spec)
    found, failures = {}, []
    for r in reports:
        if not isinstance(r, dict) or not isinstance(r.get('check_id'), str):
            blockers.append('malformed report'); continue
        cid = r['check_id']
        if cid in found:
            blockers.append('duplicate report: ' + cid)
        found[cid] = r
        if cid not in req:
            continue  # Nonblocking suggestions do not become mandatory checks.
        if r.get('status') == 'FAIL':
            failures.append('failed: ' + cid)
        elif r.get('status') != 'PASS':
            blockers.append('unknown/unreviewed: ' + cid)
        if r.get('snapshot_sha256') != snapshot:
            blockers.append('stale snapshot: ' + cid)
        if r.get('subject_sha256') != subject.get('sha256'):
            blockers.append('wrong reviewed subject: ' + cid)
        if not isinstance(r.get('observation'), str) or not r['observation'].strip():
            blockers.append('actual observation missing: ' + cid)
        ev = r.get('evidence')
        if not isinstance(ev, list) or not ev:
            blockers.append('actual evidence missing: ' + cid)
        else:
            for item in ev:
                blockers += [cid + ': ' + msg for msg in verify(item, root)]
        d = r.get('details')
        if not isinstance(d, dict):
            blockers.append('details object required: ' + cid); d = {}
        # References have no composite frame to visually inspect before generation.
        # Contracts stay bound; their actual scene/action observations occur at shot_edit.
        fidelity_report_id = {'pre_video': 'start_frame_gate', 'shot_edit': 'visual_video',
                              'final_delivery': 'edit_cut_review'}.get(action)
        if fidelity_action and cid == fidelity_report_id:
            try:
                from fidelity_contract import check_review as check_fidelity
                stage = {'pre_video': 'start_frame', 'shot_edit': 'video',
                         'final_delivery': 'final'}[action]
                if not fidelity_context:
                    blockers.append('fidelity: no bound contract context')
                else:
                    fe, ff = check_fidelity(d.get('fidelity_review'), fidelity_context,
                        stage, subject.get('sha256'), root, verify)
                    blockers.extend(fe); failures.extend(ff)
            except (ImportError, OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
                blockers.append('fidelity observations unavailable: ' + str(exc))
        if continuity_action and cid == fidelity_report_id:
            try:
                from sequence_continuity import check_review as check_sequence
                stage = {'pre_video': 'start_frame', 'shot_edit': 'video', 'final_delivery': 'final'}[action]
                actual_timeline = None
                if stage == 'final':
                    te = verify(spec.get('edit_timeline'), root)
                    blockers.extend(te)
                    if not te:
                        from brain_handoff import read_json
                        actual_timeline = read_json(root / spec['edit_timeline']['path'])
                if not continuity_context:
                    blockers.append('sequence: actual plan context missing')
                else:
                    se, sf = check_sequence(d.get('continuity_review'), continuity_context,
                        stage, subject.get('sha256'), root, verify, actual_timeline)
                    blockers.extend(se); failures.extend(sf)
            except (ImportError, OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
                blockers.append('sequence observations unavailable: ' + str(exc))
        if ensemble_action and cid == 'ensemble_continuity':
            try:
                from ensemble_gate import check_details
                ee, ef = check_details(d, ensemble_context, action == 'pre_video')
                blockers.extend(ee); failures.extend(ef)
            except (ImportError, OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
                blockers.append('ensemble: observations could not be verified: ' + str(exc))
        if cid in {'dialogue', 'speaker_source', 'dialogue_coverage'}:
            if d.get('line_ids') != lines:
                blockers.append('full ordered line coverage missing: ' + cid)
            if d.get('unresolved_line_ids') != [] or d.get('unassigned_speech_segment_ids') != []:
                blockers.append('unresolved or unaccounted speech: ' + cid)
            if lines and cid in {'dialogue', 'dialogue_coverage'}:
                if d.get('listening_review') == 'FAIL':
                    failures.append('actual speech listening failed: ' + cid)
                elif d.get('listening_review') != 'PASS':
                    blockers.append('actual speech listening required; matching ASR is insufficient: ' + cid)
        if cid in {'shot_coverage', 'animatic', 'reference_assets'} and d.get('shot_ids') != shot_ids:
            blockers.append('full ordered shot coverage missing: ' + cid)
        if cid in {'comprehension', 'final_comprehension'}:
            if d.get('blind_context_clean') is not True:
                blockers.append('viewer was not isolated from answers: ' + cid)
            fact_results = d.get('essential_fact_results')
            if not isinstance(fact_results, dict):
                fact_results = {}
            for fact in facts:
                result = fact_results.get(fact)
                if result in {'missing', 'contradicted'}:
                    failures.append('essential fact misunderstood: ' + fact)
                elif result != 'clear':
                    blockers.append('essential fact not verified: ' + fact)
            if not isinstance(d.get('retelling'), str) or not d['retelling'].strip():
                blockers.append('actual blind retelling required')
        if cid == 'recovery_check' and d.get('unreconciled_attempt_ids') != []:
            blockers.append('unreconciled submission; do not resubmit')
        if cid in {'batch_authorization', 'publication_authorization'}:
            if d.get('authorization_verified') is not True or not d.get('source_event_ref'):
                blockers.append('actual scoped authorization missing: ' + cid)
        if cid == 'mix':
            target = spec.get('audio_targets', {})
            keys = ('integrated_lufs', 'integrated_tolerance_lu', 'max_true_peak_dbtp')
            if not isinstance(target, dict) or any(not finite(target.get(k)) for k in keys):
                blockers.append('approved numerical audio targets required')
            elif not finite(d.get('integrated_lufs')) or not finite(d.get('true_peak_dbtp')):
                blockers.append('actual finite final audio measurements required')
            else:
                if target['integrated_tolerance_lu'] < 0:
                    blockers.append('negative loudness tolerance')
                if abs(d['integrated_lufs']-target['integrated_lufs']) > target['integrated_tolerance_lu']:
                    failures.append('integrated loudness outside approved target')
                if d['true_peak_dbtp'] > target['max_true_peak_dbtp']:
                    failures.append('true peak exceeds approved target')
                if d.get('listening_review') != 'PASS':
                    blockers.append('listening review cannot be replaced by LUFS')
        if editing_action and cid in {'edit_timeline', 'edit_cut_review'}:
            if d.get('timeline_sha256') != edit_sha:
                blockers.append('stale edit timeline binding: ' + cid)
            if d.get('cut_ids') != cut_ids or d.get('required_event_ids') != event_ids:
                blockers.append('edit cut/event coverage mismatch: ' + cid)
            if d.get('unresolved_event_ids') != [] or d.get('unresolved_cut_ids') != []:
                blockers.append('unresolved edit event/cut: ' + cid)
            if cid == 'edit_cut_review' and d.get('av_cut_review') != 'PASS':
                blockers.append('actual audiovisual cut review required')
        if bridge_action and cid == 'edit_cut_review':
            if not bridge_context:
                blockers.append('paired bridges context unavailable')
            else:
                try:
                    from cut_bridges import check_review
                    be, bf = check_review(d.get('bridge_review'), bridge_context['bundle'],
                        bridge_context['timeline'], root, verify)
                    blockers.extend(be); failures.extend(bf)
                except (ImportError, OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
                    blockers.append('paired cut observations unavailable: ' + str(exc))
        if presentation_action and cid == 'edit_cut_review':
            if not presentation_context:
                blockers.append('presentation context unavailable')
            else:
                from presentation_checks import check_review as check_presentation_review
                pe, pf = check_presentation_review(d.get('presentation_review'),
                    presentation_context['resolved'], presentation_context['timeline'],
                    subject.get('sha256'), root, verify)
                blockers.extend(pe); failures.extend(pf)
        if cid == 'delivery_spec':
            target = spec.get('delivery', {})
            if (not isinstance(target, dict)
                    or any(type(target.get(k)) is not int or target[k] <= 0 for k in ('width', 'height'))):
                blockers.append('explicit final dimensions required')
            elif any(d.get(k) != target[k] for k in ('width', 'height')):
                failures.append('actual delivery dimensions mismatch')
            if d.get('av_sync_review') != 'PASS':
                blockers.append('final AV sync not verified')
    blockers += ['required report missing: ' + r for r in sorted(req-set(found))]
    digests.check_unchanged()
    return {'status': 'REJECTED' if failures else ('BLOCKED' if blockers else 'ACCEPTED'),
            'action': action, 'policy_version': spec.get('policy_version', 'legacy'), 'snapshot_sha256': snapshot, 'required_checks': sorted(req),
            'failures': list(dict.fromkeys(failures)), 'blockers': list(dict.fromkeys(blockers)),
            'scope': 'Local report integrity and encoded gate policy only; no audio/vision/ASR/semantic inference.',
            'uploaded': False, 'guarantees_zero_errors': False}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('spec', 'reports', 'root'):
        p.add_argument('--'+name, type=Path, required=True)
    a = p.parse_args()
    try:
        result = gate(json.loads(a.spec.read_text(encoding='utf-8')),
                      json.loads(a.reports.read_text(encoding='utf-8')), a.root)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(json.dumps({'status': 'BLOCKED', 'error': str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return {'ACCEPTED': 0, 'REJECTED': 1, 'BLOCKED': 2}[result['status']]

if __name__ == '__main__':
    raise SystemExit(main())
