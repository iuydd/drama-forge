#!/usr/bin/env python3
"""Host-side signed approval and one-send gateway, not an installed service.

The trusted host owns keys/credentials/database/code and registers callbacks.
Workers only receive public keys. Same-UID files cannot provide isolation from
an unrestricted worker: deployment must enforce a separate account/container.
No vendor adapter, private key, or paid submission is installed by this module.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
import base64
import hashlib
import json
from pathlib import Path
from typing import Any, Callable, Protocol
from brain_handoff import digest, load_task, verify_record
from job_ledger import Ledger, parse_time


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False,sort_keys=True,separators=(',', ':'),allow_nan=False).encode()


def sign(payload: dict, private_key: bytes, key_id: str) -> dict:
    """For the protected approval process only; never call with worker-supplied keys."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    body={'schema_version':'signed-scope-1','key_id':key_id,'payload':payload}
    signature=Ed25519PrivateKey.from_private_bytes(private_key).sign(canonical(body))
    return dict(body,signature=base64.b64encode(signature).decode('ascii'))


def verify(envelope: dict, trusted_keys: dict, purpose: str, now: datetime | None = None) -> dict:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    from cryptography.exceptions import InvalidSignature
    if not isinstance(envelope,dict) or set(envelope)!={'schema_version','key_id','payload','signature'} or envelope['schema_version']!='signed-scope-1':
        raise ValueError('invalid signed envelope')
    key=trusted_keys.get(envelope['key_id'])
    if not isinstance(key,dict) or purpose not in key.get('purposes',[]): raise ValueError('untrusted key/role')
    body={k:envelope[k] for k in ('schema_version','key_id','payload')}
    try:
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(key['public_hex'])).verify(base64.b64decode(envelope['signature'],validate=True),canonical(body))
    except (InvalidSignature,ValueError,TypeError,KeyError) as exc: raise ValueError('signature verification failed') from exc
    payload=envelope['payload']
    if not isinstance(payload,dict) or payload.get('purpose')!=purpose: raise ValueError('approval purpose mismatch')
    current=now or datetime.now(timezone.utc)
    if current.tzinfo is None: raise ValueError('timezone-aware clock required')
    if not parse_time(payload['issued_at']) <= current < parse_time(payload['expires_at']): raise ValueError('expired/future approval')
    return payload


class Adapter(Protocol):
    def submit(self, request: dict, idempotency_key: str) -> dict: ...


@dataclass(frozen=True)
class RegisteredAdapter:
    adapter: Adapter
    implementation_sha256: str
    provider: str
    account_scope: str


class Gateway:
    """One managed submission entry. The HOST, not the agent, constructs this.

    validator is registered trusted code that re-reads media-bound production
    gates. Tests can supply a synthetic validator, but it is never shipped as a
    valid real-production receipt. Callbacks execute synchronously in this call.
    """
    def __init__(self, root: Path, ledger: Ledger, trusted_keys: dict,
                 adapters: dict[str,RegisteredAdapter], validator: Callable[[dict,dict],dict]):
        self.root=Path(root).resolve(strict=True);self.ledger=ledger
        self.keys=trusted_keys;self.adapters=adapters;self.validator=validator

    def dispatch(self, *, job_id: str, binding: dict, creative_approval: dict,
                 cost_approval: dict, adapter_id: str) -> dict:
        task,packet,errors=load_task(binding,self.root)
        if errors: raise ValueError('; '.join(errors))
        if packet.get('policy_version')!='4.2.0': raise ValueError('gateway enforces policy 4.2.0; no legacy downgrade')
        creative=verify(creative_approval,self.keys,'creative')
        expected={'packet':binding['packet'],'task_id':binding['task_id'],'request_sha256':task['request_sha256']}
        if creative.get('scope')!=expected: raise ValueError('creative approval is for another exact request')
        job=self.ledger._job(job_id)
        scope=self.ledger.db.execute('SELECT * FROM batches WHERE batch_id=?',(job['batch_id'],)).fetchone()
        budget=verify(cost_approval,self.keys,'budget')
        if budget.get('scope_sha256')!=scope['scope_sha'] or not budget.get('source_ref'): raise ValueError('budget scope/evidence differs')
        stored=json.loads(job['request_json'])
        native_sha=digest(stored)
        if native_sha!=job['request_sha']: raise ValueError('durable native request digest differs')
        if task.get('native_request_sha256')!=native_sha: raise ValueError('native request was not frozen in the creative task')
        if stored.get('brain_request_sha256')!=task['request_sha256']: raise ValueError('ledger request is not brain-approved request')
        route=self.adapters.get(adapter_id)
        if not route or (stored.get('provider'),stored.get('account_scope'))!=(route.provider,route.account_scope):
            raise ValueError('unregistered adapter/provider/account')
        if stored.get('adapter_sha256')!=route.implementation_sha256: raise ValueError('adapter implementation changed')
        if stored.get('prompt_sha256')!=hashlib.sha256(task['request']['prompt'].encode()).hexdigest():
            raise ValueError('native request changed final prompt')
        # Native adapter parameters are signed by budget and approved semantic scope;
        # trusted validator checks full mapping, not just a prompt string.
        gate=self.validator(task,stored)
        if (not isinstance(gate,dict) or gate.get('status')!='PASS' or
            gate.get('brain_request_sha256')!=task['request_sha256'] or gate.get('native_request_sha256')!=digest(stored)):
            raise ValueError('current media/capability/native-mapping gate not passed')
        event={'kind':'user_confirmation' if scope['mode']=='metered' else 'free_channel_verification',
               'scope_sha256':scope['scope_sha'],'source_ref':budget['source_ref'],'principal':cost_approval['key_id']}
        self.ledger.record_authorization(job['batch_id'],event)
        permission=self.ledger.claim_submission(job_id)
        if permission['action']!='SEND_ONCE': return permission
        try:
            response=route.adapter.submit(permission['request'],permission['idempotency_key'])
            if not isinstance(response,dict) or not isinstance(response.get('task_id'),str) or not response['task_id'].strip():
                raise ValueError('provider returned no actual task ID')
            receipt={'schema_version':'submission-receipt-1','job_id':job_id,'remote_task_id':response['task_id'],
                     'provider':route.provider,'account_scope':route.account_scope,
                     'brain_request_sha256':task['request_sha256'],'native_request_sha256':native_sha,
                     'response_sha256':digest(response),'submitted_at':datetime.now(timezone.utc).isoformat()}
            folder=self.root/'host-receipts'
            if folder.is_symlink(): raise ValueError('unsafe receipt folder')
            folder.mkdir(mode=0o700,exist_ok=True)
            if not folder.resolve().is_relative_to(self.root): raise ValueError('receipt escapes root')
            name=digest(receipt)+'.json';path=folder/name
            # Only a whitelisted, bounded receipt is written, never credentials/raw response.
            with path.open('xb') as out: out.write(canonical(receipt))
            receipt_record={'path':str(path.relative_to(self.root)),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
            evidence='file:'+receipt_record['path']+'#sha256='+receipt_record['sha256']
            self.ledger.attach_remote(job_id,response['task_id'],evidence)
        except BaseException as exc:
            self.ledger.mark_unknown(job_id,'host-interruption:'+type(exc).__name__)
            # No automatic resend and no exception messages containing credentials.
            if isinstance(exc,(KeyboardInterrupt,SystemExit)): raise
            return {'action':'RECONCILE_ONLY','state':'SUBMISSION_UNKNOWN','job_id':job_id}
        return {'action':'SUBMITTED','job_id':job_id,'remote_task_id':response['task_id'],
                'request_sha256':permission['request_sha256'],'evidence_ref':evidence,'receipt':receipt_record,
                'media_quality_verified':False}


def protected_path_errors(path: Path, *, worker_uid: int, host_uid: int) -> list[str]:
    """POSIX mode sanity check, not proof about external ACLs or network access."""
    errors=[];p=Path(path)
    if worker_uid==host_uid: errors.append('worker and protected host share UID')
    if p.is_symlink() or not p.exists(): return errors+['protected path missing or symbolic link']
    st=p.stat()
    if st.st_uid!=host_uid: errors.append('protected path not owned by host')
    if st.st_mode & 0o022: errors.append('protected path group/world writable')
    return errors
