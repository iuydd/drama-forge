#!/usr/bin/env python3
"""Local submission-intent and cost ledger. Does NOT send requests or grant consent.

Only a trusted, real user-confirmation event may authorize a metered batch.
A returned SEND_ONCE must be consumed once by the actual provider adapter.
A lost response always requires reconciliation; this library never auto-resubmits.
Single-machine local SQLite only; keep this DB outside ephemeral worker storage.
"""
from __future__ import annotations
from contextlib import contextmanager
from datetime import datetime, timezone
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
from typing import Any

TERMINAL = {'SUCCEEDED', 'FAILED', 'CANCELLED', 'CONFIRMED_NOT_CREATED'}
REMOTE_STATES = {'SUBMITTED', 'RUNNING', 'SUCCEEDED', 'FAILED', 'CANCELLED'}


def canonical(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(obj: Any) -> str:
    return hashlib.sha256(canonical(obj).encode()).hexdigest()


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_time(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if dt.tzinfo is None:
        raise ValueError('timestamp must include timezone')
    return dt


def text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def money(value: Any) -> bool:
    return type(value) is int and value >= 0


class Ledger:
    def __init__(self, path: Path):
        self.path = Path(path)
        if self.path.is_symlink() or not self.path.parent.is_dir():
            raise ValueError('use an existing trusted local parent and non-symlink DB')
        self.db = sqlite3.connect(self.path, isolation_level=None, timeout=10)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS batches (
            batch_id TEXT PRIMARY KEY, scope_json TEXT NOT NULL, scope_sha TEXT NOT NULL,
            mode TEXT NOT NULL, currency TEXT NOT NULL, cap_minor INTEGER NOT NULL,
            expires_at TEXT NOT NULL, approval_json TEXT, halted INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS jobs (
            job_id TEXT PRIMARY KEY, batch_id TEXT NOT NULL REFERENCES batches(batch_id),
            logical_id TEXT NOT NULL, attempt INTEGER NOT NULL, request_json TEXT NOT NULL,
            request_sha TEXT NOT NULL, ceiling_minor INTEGER NOT NULL,
            reserved_minor INTEGER NOT NULL DEFAULT 0, actual_minor INTEGER,
            state TEXT NOT NULL, provider TEXT NOT NULL, account_scope TEXT NOT NULL,
            remote_task_id TEXT, result_json TEXT, UNIQUE(logical_id, attempt),
            UNIQUE(provider, account_scope, remote_task_id)
        );
        CREATE TABLE IF NOT EXISTS events (
            seq INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL,
            subject TEXT NOT NULL, event_type TEXT NOT NULL, body_json TEXT NOT NULL
        );
        ''')

    def close(self) -> None:
        self.db.close()

    @contextmanager
    def transaction(self):
        self.db.execute('BEGIN IMMEDIATE')
        try:
            yield
            self.db.execute('COMMIT')
        except BaseException:
            if self.db.in_transaction:
                self.db.execute('ROLLBACK')
            raise

    def event(self, subject: str, kind: str, body: dict) -> None:
        self.db.execute('INSERT INTO events(created_at,subject,event_type,body_json) VALUES(?,?,?,?)',
                        (now(), subject, kind, canonical(body)))

    def _job(self, job_id: str) -> sqlite3.Row:
        row = self.db.execute('SELECT * FROM jobs WHERE job_id=?', (job_id,)).fetchone()
        if row is None:
            raise ValueError('unknown job')
        return row

    def prepare(self, scope: dict) -> dict:
        """Persist an immutable proposed batch; returns stable IDs, never approval."""
        if not isinstance(scope, dict):
            raise ValueError('scope object required')
        for k in ('batch_id', 'currency', 'expires_at', 'quote_source'):
            if not text(scope.get(k)):
                raise ValueError(f'{k} required')
        if parse_time(scope['expires_at']) <= datetime.now(timezone.utc):
            raise ValueError('quote already expired')
        if scope.get('mode') not in {'metered', 'verified_free', 'local_no_api_charge'}:
            raise ValueError('unknown charge mode blocks production')
        cap = scope.get('cap_minor')
        if not money(cap):
            raise ValueError('integer nonnegative cap_minor required')
        items = scope.get('items')
        if not isinstance(items, list) or not items:
            raise ValueError('explicit nonempty job list required')
        job_rows, keys = [], set()
        for item in items:
            if not isinstance(item, dict):
                raise ValueError('invalid batch item')
            logical, attempt, req, cost = (item.get('logical_id'), item.get('attempt'),
                                          item.get('request'), item.get('ceiling_minor'))
            if not text(logical) or type(attempt) is not int or attempt < 1 or not money(cost):
                raise ValueError('invalid job identity/attempt/cost')
            if (logical, attempt) in keys:
                raise ValueError('duplicate attempt within batch')
            keys.add((logical, attempt))
            if not isinstance(req, dict):
                raise ValueError('request object required')
            for k in ('provider', 'account_scope', 'model_id', 'project_id', 'shot_id', 'stage'):
                if not text(req.get(k)):
                    raise ValueError(f'request.{k} required')
            if not isinstance(req.get('parameters'), dict) or not isinstance(req.get('input_hashes'), list):
                raise ValueError('exact parameters and input_hashes required')
            if not text(req.get('prompt_sha256')):
                raise ValueError('exact prompt_sha256 required; no secrets in stored request')
            if scope['mode'] != 'metered' and cost != 0:
                raise ValueError('free/local API charge must be explicitly zero')
            jid = digest({'logical_id': logical, 'attempt': attempt})
            job_rows.append((jid, scope['batch_id'], logical, attempt, canonical(req),
                             digest(req), cost, 'PREPARED', req['provider'], req['account_scope']))
        if sum(row[6] for row in job_rows) > cap:
            raise ValueError('quoted individual ceilings exceed batch cap')
        if scope['mode'] != 'metered' and cap != 0:
            raise ValueError('free/local batch must have zero API charge cap')
        sha = digest(scope)
        with self.transaction():
            existing = self.db.execute('SELECT scope_sha FROM batches WHERE batch_id=?',
                                       (scope['batch_id'],)).fetchone()
            if existing:
                if existing['scope_sha'] != sha:
                    raise ValueError('immutable batch changed; use new scope and confirmation')
                return {'batch_id': scope['batch_id'], 'scope_sha256': sha,
                        'job_ids': [r[0] for r in job_rows], 'reused': True}
            self.db.execute('INSERT INTO batches(batch_id,scope_json,scope_sha,mode,currency,cap_minor,expires_at) VALUES(?,?,?,?,?,?,?)',
                            (scope['batch_id'], canonical(scope), sha, scope['mode'], scope['currency'], cap, scope['expires_at']))
            try:
                self.db.executemany('INSERT INTO jobs(job_id,batch_id,logical_id,attempt,request_json,request_sha,ceiling_minor,state,provider,account_scope) VALUES(?,?,?,?,?,?,?,?,?,?)', job_rows)
            except sqlite3.IntegrityError as exc:
                raise ValueError('existing attempt: reconcile it instead of creating another batch') from exc
            self.event(scope['batch_id'], 'BATCH_PROPOSED', {'scope_sha256': sha})
        return {'batch_id': scope['batch_id'], 'scope_sha256': sha,
                'job_ids': [r[0] for r in job_rows], 'reused': False}

    def record_authorization(self, batch_id: str, event: dict) -> None:
        """Caller must supply a genuine consent/free-channel verification event."""
        if not isinstance(event, dict):
            raise ValueError('real authorization event required')
        with self.transaction():
            b = self.db.execute('SELECT * FROM batches WHERE batch_id=?', (batch_id,)).fetchone()
            if b is None:
                raise ValueError('unknown batch')
            expected = 'user_confirmation' if b['mode'] == 'metered' else 'free_channel_verification'
            if event.get('kind') != expected or event.get('scope_sha256') != b['scope_sha']:
                raise ValueError('authorization kind or exact scope mismatch')
            if not text(event.get('source_ref')) or not text(event.get('principal')):
                raise ValueError('actual source message/record and principal required')
            if parse_time(b['expires_at']) <= datetime.now(timezone.utc):
                raise ValueError('expired quote')
            if b['halted']:
                raise ValueError('halted batch cannot silently resume')
            if b['approval_json'] is not None and b['approval_json'] != canonical(event):
                raise ValueError('approval record immutable')
            self.db.execute('UPDATE batches SET approval_json=? WHERE batch_id=?',
                            (canonical(event), batch_id))
            self.event(batch_id, 'AUTHORIZATION_RECORDED', event)

    def claim_submission(self, job_id: str) -> dict:
        """Atomically grant at most one initial send permission. No network call."""
        with self.transaction():
            job = self._job(job_id)
            if job['state'] != 'PREPARED':
                return {'action': 'RECONCILE_ONLY', 'state': job['state'],
                        'remote_task_id': job['remote_task_id'], 'job_id': job_id}
            b = self.db.execute('SELECT * FROM batches WHERE batch_id=?', (job['batch_id'],)).fetchone()
            if b['halted'] or not b['approval_json'] or parse_time(b['expires_at']) <= datetime.now(timezone.utc):
                return {'action': 'BLOCKED', 'reason': 'missing/expired approval or halted batch'}
            exposure = self.db.execute('SELECT COALESCE(SUM(COALESCE(actual_minor,reserved_minor)),0) FROM jobs WHERE batch_id=?',
                                       (job['batch_id'],)).fetchone()[0]
            if exposure + job['ceiling_minor'] > b['cap_minor']:
                return {'action': 'BLOCKED', 'reason': 'batch cap reached'}
            self.db.execute('UPDATE jobs SET state=?,reserved_minor=? WHERE job_id=?',
                            ('SUBMITTING', job['ceiling_minor'], job_id))
            self.event(job_id, 'SUBMISSION_INTENT_DURABLE', {'request_sha256': job['request_sha']})
            return {'action': 'SEND_ONCE', 'job_id': job_id,
                    'request_sha256': job['request_sha'],
                    'idempotency_key': digest({'job_id': job_id, 'request_sha': job['request_sha']}),
                    'request': json.loads(job['request_json']),
                    'notice': 'Verify provider idempotency support; this permission is not proof of remote execution.'}

    def attach_remote(self, job_id: str, task_id: str, evidence_ref: str) -> None:
        if not text(task_id) or not text(evidence_ref):
            raise ValueError('actual task ID and response evidence required')
        with self.transaction():
            job = self._job(job_id)
            if job['state'] not in {'SUBMITTING', 'SUBMISSION_UNKNOWN', 'SUBMITTED', 'RUNNING', 'CANCEL_PENDING'}:
                raise ValueError('cannot attach response to this job state')
            if job['remote_task_id'] and job['remote_task_id'] != task_id:
                raise ValueError('conflicting remote task IDs: investigate duplicates')
            next_state = job['state'] if job['state'] in {'RUNNING', 'CANCEL_PENDING'} else 'SUBMITTED'
            try:
                self.db.execute('UPDATE jobs SET remote_task_id=?,state=? WHERE job_id=?', (task_id, next_state, job_id))
            except sqlite3.IntegrityError as exc:
                raise ValueError('remote task already belongs to another attempt') from exc
            self.event(job_id, 'REMOTE_ATTACHED', {'task_id': task_id, 'evidence_ref': evidence_ref})

    def mark_unknown(self, job_id: str, evidence_ref: str) -> None:
        if not text(evidence_ref):
            raise ValueError('interruption evidence required')
        with self.transaction():
            j = self._job(job_id)
            if j['state'] not in {'SUBMITTING', 'SUBMITTED', 'RUNNING', 'SUBMISSION_UNKNOWN'}:
                raise ValueError('not an in-flight job')
            self.db.execute('UPDATE jobs SET state=? WHERE job_id=?', ('SUBMISSION_UNKNOWN', job_id))
            self.event(job_id, 'INTERRUPTION_RECONCILE_REQUIRED', {'evidence_ref': evidence_ref})

    def reconcile(self, job_id: str, state: str, task_id: str | None, evidence_ref: str,
                  result: dict | None = None) -> None:
        if state not in REMOTE_STATES | {'CONFIRMED_NOT_CREATED'} or not text(evidence_ref):
            raise ValueError('verified canonical remote state/evidence required')
        with self.transaction():
            j = self._job(job_id)
            if j['state'] == 'PREPARED':
                raise ValueError('no submission intent to reconcile')
            if j['state'] in TERMINAL and j['state'] != state:
                raise ValueError('conflicting terminal state: investigate, do not overwrite')
            if state == 'CONFIRMED_NOT_CREATED':
                if task_id is not None or j['remote_task_id'] is not None:
                    raise ValueError('existing task cannot be declared not created')
            elif not text(task_id) or (j['remote_task_id'] and task_id != j['remote_task_id']):
                raise ValueError('actual matching remote task required')
            self.db.execute('UPDATE jobs SET state=?,remote_task_id=?,result_json=? WHERE job_id=?',
                            (state, task_id, canonical(result or {}), job_id))
            self.event(job_id, 'RECONCILED', {'state': state, 'task_id': task_id, 'evidence_ref': evidence_ref})
            # Even a failed/cancelled job may be billed. No automatic refund/resubmit.

    def settle(self, job_id: str, actual_minor: int, billing_evidence_ref: str) -> None:
        if not money(actual_minor) or not text(billing_evidence_ref):
            raise ValueError('actual nonnegative integer amount and billing evidence required')
        with self.transaction():
            j = self._job(job_id)
            if j['state'] not in TERMINAL:
                raise ValueError('final billing settlement requires terminal reconciliation')
            if j['actual_minor'] is not None and j['actual_minor'] != actual_minor:
                raise ValueError('settlement immutable; record refunds separately in external billing ledger')
            self.db.execute('UPDATE jobs SET actual_minor=? WHERE job_id=?', (actual_minor, job_id))
            if actual_minor > j['ceiling_minor']:
                self.db.execute('UPDATE batches SET halted=1 WHERE batch_id=?', (j['batch_id'],))
            self.event(job_id, 'SETTLED', {'actual_minor': actual_minor, 'evidence_ref': billing_evidence_ref})

    def stop_batch(self, batch_id: str, user_event_ref: str) -> None:
        if not text(user_event_ref):
            raise ValueError('stop event required')
        with self.transaction():
            if self.db.execute('SELECT 1 FROM batches WHERE batch_id=?', (batch_id,)).fetchone() is None:
                raise ValueError('unknown batch')
            self.db.execute('UPDATE batches SET halted=1 WHERE batch_id=?', (batch_id,))
            self.event(batch_id, 'STOP_NEW_SUBMISSIONS', {'event_ref': user_event_ref,
                        'remote_cancellation_confirmed': False})

    def summary(self, batch_id: str) -> dict:
        b = self.db.execute('SELECT * FROM batches WHERE batch_id=?', (batch_id,)).fetchone()
        if b is None:
            raise ValueError('unknown batch')
        rows = self.db.execute('SELECT job_id,state,ceiling_minor,reserved_minor,actual_minor,remote_task_id FROM jobs WHERE batch_id=?',
                               (batch_id,)).fetchall()
        unresolved = [r['job_id'] for r in rows if r['state'] in {'SUBMITTING', 'SUBMISSION_UNKNOWN', 'CANCEL_PENDING'}]
        return {'batch_id': batch_id, 'currency': b['currency'], 'approved': bool(b['approval_json']),
                'halted': bool(b['halted']), 'cap_minor': b['cap_minor'],
                'settled_actual_minor': sum(r['actual_minor'] or 0 for r in rows),
                'unsettled_commitment_minor': sum(r['reserved_minor'] for r in rows if r['actual_minor'] is None),
                'unsettled_job_ids': [r['job_id'] for r in rows if r['state'] != 'PREPARED' and r['actual_minor'] is None],
                'reconcile_required': unresolved, 'jobs': [dict(r) for r in rows],
                'network_requests_executed_by_tool': False}


def file_digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def store_without_overwrite(source: Path, root: Path, relative: str, expected_sha256: str) -> dict:
    """Copy a validated local download to a new path atomically, never replace.

    Call the real media decoder before promotion. File contents are NOT decoded here.
    Requires local same-filesystem hard-link support; fails closed when unsupported.
    """
    root, source = Path(root).resolve(strict=True), Path(source)
    if not root.is_dir() or source.is_symlink() or not source.is_file():
        raise ValueError('trusted root and real source file required')
    p = Path(relative)
    if not isinstance(relative, str) or not relative or p.is_absolute() or any(x in {'', '.', '..'} for x in relative.replace('\\', '/').split('/')):
        raise ValueError('unsafe relative destination')
    dest = root/p
    if not dest.resolve().is_relative_to(root) or dest.is_symlink():
        raise ValueError('destination escapes trusted root')
    dest.parent.mkdir(parents=True, exist_ok=True)
    if file_digest(source) != expected_sha256:
        raise ValueError('download checksum mismatch')
    if dest.exists():
        if dest.is_file() and file_digest(dest) == expected_sha256:
            return {'status': 'REUSED', 'path': str(dest), 'sha256': expected_sha256}
        raise FileExistsError('destination conflict; original file preserved')
    fd, tmp = tempfile.mkstemp(prefix='.recover-', suffix='.partial', dir=dest.parent)
    temp = Path(tmp)
    try:
        with os.fdopen(fd, 'wb') as out, source.open('rb') as inp:
            shutil.copyfileobj(inp, out)
            out.flush(); os.fsync(out.fileno())
        if file_digest(temp) != expected_sha256:
            raise ValueError('staged copy checksum mismatch')
        try:
            os.link(temp, dest)  # Atomic no-clobber promotion; os.replace is intentionally not used.
        except FileExistsError:
            if dest.is_symlink() or not dest.is_file() or file_digest(dest) != expected_sha256:
                raise FileExistsError('concurrent destination conflict; no overwrite')
            return {'status': 'REUSED', 'path': str(dest), 'sha256': expected_sha256}
        if hasattr(os, 'O_DIRECTORY'):
            directory_fd = os.open(dest.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        return {'status': 'STORED_CANDIDATE_NOT_MEDIA_APPROVAL', 'path': str(dest), 'sha256': expected_sha256}
    finally:
        temp.unlink(missing_ok=True)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--db', type=Path, required=True)
    p.add_argument('--batch', required=True)
    args = p.parse_args()
    if not args.db.is_file():
        p.error('status CLI only opens an existing DB; use reviewed Ledger API to propose jobs')
    ledger = None
    try:
        ledger = Ledger(args.db)
        print(json.dumps(ledger.summary(args.batch), ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, sqlite3.Error) as exc:
        print(json.dumps({'status': 'BLOCKED', 'error': str(exc)}, ensure_ascii=False))
        return 2
    finally:
        if ledger:
            ledger.close()

if __name__ == '__main__':
    raise SystemExit(main())
