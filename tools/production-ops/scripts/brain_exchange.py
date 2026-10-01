#!/usr/bin/env python3
"""Validated content-addressed return capsules and transactional pending state.

Import is NEVER creative acceptance. Approval requires a protected host signature.
Does not connect ChatGPT or submit generation jobs. No executable from a capsule
is run. The same return can be imported twice without duplicating work.
"""
from __future__ import annotations
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import sqlite3
import stat
import tempfile
import zipfile
from typing import Any
from brain_handoff import digest, read_json, verify_record, text
from job_ledger import store_without_overwrite
from trusted_runtime import verify as verify_signature

PHASES={'assets','start_frames','video','audio','edit','repair'}


def file_record(root: Path, relative: str) -> dict:
    path=Path(root)/relative
    record={'path':relative,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    errors=verify_record(record,root)
    if errors: raise ValueError('; '.join(errors))
    return record


def records_in(value: Any) -> list[dict]:
    found={}
    def walk(v):
        if isinstance(v,dict):
            if 'path' in v and 'sha256' in v:
                rec={'path':v['path'],'sha256':v['sha256']};key=rec['path']
                if not isinstance(key,str): raise ValueError('invalid file reference')
                if key in found and found[key]!=rec: raise ValueError('one path claims different file contents')
                found[key]=rec
            else:
                for x in v.values(): walk(x)
        elif isinstance(v,list):
            for x in v: walk(x)
    walk(value)
    return list(found.values())


def validate_return(value: Any, root: Path) -> list[str]:
    errors=[]
    if not isinstance(value,dict) or value.get('schema_version')!='brain-return-2': return ['return: unsupported/missing version']
    for k in ('return_id','episode_id','base_packet_id'):
        if not text(value.get(k)): errors.append('return: missing '+k)
    if value.get('phase') not in PHASES: errors.append('return: unknown phase')
    if value.get('status') not in {'NEEDS_BRAIN_REVIEW','PARTIAL','BLOCKED'}: errors.append('return: execution report cannot grant creative acceptance')
    for k in ('outputs','actual_requests','observations','issues','decisions_needed'):
        if not isinstance(value.get(k),list): errors.append('return: array required: '+k)
    if errors: return errors
    for rec in records_in(value): errors += verify_record(rec,root)
    if errors: return errors
    base=read_json(Path(root)/value['base_packet']['path'])
    if (base.get('packet_id')!=value['base_packet_id'] or base.get('episode_id')!=value['episode_id']
            or base.get('phase')!=value['phase']): errors.append('return: active packet/episode/phase mismatch')
    if base.get('schema_version')!='brain-packet-1' or base.get('status')!='LOCKED' or base.get('policy_version')!='4.2.0':
        errors.append('return: unsupported/unlocked active packet')
    tasks={t['task_id']:t for t in base.get('tasks',[])}
    actual={}
    for req in value['actual_requests']:
        if not isinstance(req,dict) or req.get('task_id') not in tasks: errors.append('return: unknown executed task'); continue
        tid=req['task_id']
        if tid in actual: errors.append('return: duplicate actual request'); continue
        actual[tid]=req
        frozen=tasks[tid]
        if req.get('request')!=frozen.get('request') or req.get('request_sha256')!=digest(req.get('request')):
            errors.append('return: executed request differs from frozen task')
        if not text(req.get('job_id')) or not isinstance(req.get('receipt'),dict): errors.append('return: actual job ID/receipt required')
    outputs=set()
    for output in value['outputs']:
        if not isinstance(output,dict): errors.append('return: malformed output'); continue
        key=(output.get('asset_id'),output.get('file',{}).get('sha256'))
        if not text(key[0]) or key in outputs: errors.append('return: invalid/duplicate output identity')
        outputs.add(key)
        if output.get('task_id') not in actual: errors.append('return: output lacks actual approved request')
        if output.get('status')!='CANDIDATE': errors.append('return: new media is candidate until actual brain review')
        if output.get('media_kind') not in {'image','video','audio','document'}: errors.append('return: output media type required')
        if not isinstance(output.get('file'),dict): errors.append('return: output file missing')
        elif output.get('media_kind') in {'image','video','audio','document'}:
            try:
                from media_validation import probe_media
                probe_media(Path(root)/output['file']['path'],output['media_kind'])
            except (ValueError,OSError,KeyError) as exc:
                errors.append('return: output did not decode as declared media: '+type(exc).__name__)
    known_sha={o.get('file',{}).get('sha256') for o in value['outputs'] if isinstance(o,dict)}
    for observation in value['observations']:
        if not isinstance(observation,dict) or observation.get('subject_sha256') not in known_sha: errors.append('return: observation refers to wrong/unknown output'); continue
        if observation.get('result') not in {'PASS','FAIL','UNKNOWN'} or not text(observation.get('observation')):
            errors.append('return: actual observation/result required')
        if not observation.get('evidence'): errors.append('return: observation evidence missing')
    budget=value.get('cost_and_retry_state')
    if not isinstance(budget,dict): errors.append('return: actual budget/recovery state required')
    else:
        for k in ('settled_minor','reserved_minor'):
            v=budget.get(k)
            if v is not None and (type(v) is not int or v<0): errors.append('return: cost must be nonnegative integer minor units or explicitly unknown')
        if not isinstance(budget.get('unknown_job_ids'),list): errors.append('return: interrupted jobs must be explicit')
    return list(dict.fromkeys(errors))


def _safe_name(name: str) -> bool:
    return (isinstance(name,str) and bool(name) and '\\' not in name and '\x00' not in name
            and not name.startswith('/') and all(p not in {'','.','..'} for p in name.split('/')))


def export_return(value: dict, root: Path, destination: Path) -> dict:
    errors=validate_return(value,root)
    if errors: raise ValueError('; '.join(errors))
    destination=Path(destination)
    if destination.exists(): raise FileExistsError('return capsule destination exists')
    records=records_in(value)
    manifest={'schema_version':'brain-capsule-1','return_sha256':digest(value),'files':records}
    # Fixed hash names prevent narrative filenames exposing answers to other roles.
    with zipfile.ZipFile(destination,'x',compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr('return.json',json.dumps(value,ensure_ascii=False,indent=2))
        z.writestr('manifest.json',json.dumps(manifest,ensure_ascii=False,indent=2))
        seen=set()
        for rec in records:
            if rec['sha256'] not in seen:
                z.write(Path(root)/rec['path'],'objects/'+rec['sha256']);seen.add(rec['sha256'])
    return {'path':str(destination),'return_sha256':digest(value),'files':len(records),'objects':len(seen),'accepted':False}


def unpack_return(capsule: Path, destination: Path, *, max_uncompressed_bytes: int = 8*1024**3) -> dict:
    """Safe no-overwrite import, with explicit configurable transport quota."""
    dest=Path(destination).resolve(strict=True)
    with zipfile.ZipFile(capsule) as z:
        infos=z.infolist();names=[i.filename for i in infos]
        if len(names)!=len(set(names)) or len(names)>10000: raise ValueError('duplicate or excessive capsule members')
        if any(not _safe_name(i.filename) or stat.S_ISLNK(i.external_attr>>16) for i in infos): raise ValueError('unsafe capsule member')
        if sum(i.file_size for i in infos)>max_uncompressed_bytes: raise ValueError('capsule exceeds configured transport quota')
        with tempfile.TemporaryDirectory(prefix='drama-capsule-') as td:
            temp=Path(td)
            # Parse strict JSON using the same duplicate-key rejection as project files.
            for name in ('manifest.json','return.json'):
                (temp/name).write_bytes(z.read(name))
            manifest=read_json(temp/'manifest.json');value=read_json(temp/'return.json')
            if manifest.get('schema_version')!='brain-capsule-1' or manifest.get('return_sha256')!=digest(value): raise ValueError('capsule return digest mismatch')
            expected=records_in(value)
            if manifest.get('files')!=expected: raise ValueError('capsule omitted/added reference')
            object_names={'objects/'+r['sha256'] for r in expected}
            if set(names)!=object_names|{'return.json','manifest.json'}: raise ValueError('capsule contains undeclared files')
            for rec in expected:
                if not _safe_name(rec['path']) or len(rec['sha256'])!=64 or any(c not in '0123456789abcdef' for c in rec['sha256']): raise ValueError('unsafe capsule reference')
                path=temp/rec['path'];path.parent.mkdir(parents=True,exist_ok=True)
                if rec['path'] in {'return.json','manifest.json'}: raise ValueError('reserved capsule path')
                with z.open('objects/'+rec['sha256']) as src,path.open('wb') as out:
                    while block:=src.read(1024*1024): out.write(block)
            errors=validate_return(value,temp)
            if errors: raise ValueError('; '.join(errors))
            # Validate all destination conflicts BEFORE publishing anything.
            for rec in expected:
                target=dest/rec['path']
                if target.exists() and verify_record(rec,dest): raise FileExistsError('existing file differs: '+rec['path'])
                if not target.resolve().is_relative_to(dest) or target.is_symlink(): raise ValueError('unsafe destination')
            for rec in expected: store_without_overwrite(temp/rec['path'],dest,rec['path'],rec['sha256'])
    return value


class WorkflowStore:
    def __init__(self, path: Path):
        path=Path(path)
        if path.is_symlink(): raise ValueError('workflow database may not be a symbolic link')
        self.root=path.parent.resolve(strict=True)
        self.db=sqlite3.connect(path,isolation_level=None,timeout=10);self.db.row_factory=sqlite3.Row
        self.db.executescript('''PRAGMA journal_mode=WAL; PRAGMA synchronous=FULL;
        CREATE TABLE IF NOT EXISTS active(episode_id TEXT PRIMARY KEY,packet_sha TEXT NOT NULL,packet_id TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS returns_seen(return_id TEXT PRIMARY KEY,sha TEXT NOT NULL,episode_id TEXT NOT NULL,payload TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS candidates(asset_id TEXT NOT NULL,sha TEXT NOT NULL,return_id TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'PENDING',PRIMARY KEY(asset_id,sha));
        CREATE TABLE IF NOT EXISTS decisions(decision_sha TEXT PRIMARY KEY,payload TEXT NOT NULL);
        ''')
    def close(self): self.db.close()
    @contextmanager
    def transaction(self):
        self.db.execute('BEGIN IMMEDIATE')
        try: yield;self.db.execute('COMMIT')
        except BaseException:
            if self.db.in_transaction:self.db.execute('ROLLBACK')
            raise
    def register_packet(self,packet:dict,record:dict,signed:dict,keys:dict):
        approval=verify_signature(signed,keys,'creative')
        errors=verify_record(record,self.root)
        if errors: raise ValueError('; '.join(errors))
        if read_json(self.root/record['path'])!=packet: raise ValueError('activation packet bytes differ')
        if packet.get('policy_version')!='4.2.0' or packet.get('status')!='LOCKED': raise ValueError('only frozen 4.2 packets can become active')
        if approval.get('scope')!={'packet':record,'packet_id':packet['packet_id'],'episode_id':packet['episode_id']}:
            raise ValueError('packet activation requires protected creative approval')
        with self.transaction():
            old=self.db.execute('SELECT * FROM active WHERE episode_id=?',(packet['episode_id'],)).fetchone()
            if old and old['packet_sha']!=record['sha256'] and approval.get('previous_packet_sha256')!=old['packet_sha']:
                raise ValueError('stale packet activation, refresh base')
            self.db.execute('INSERT OR REPLACE INTO active VALUES(?,?,?)',(packet['episode_id'],record['sha256'],packet['packet_id']))
    def ingest(self,value:dict,root:Path)->dict:
        errors=validate_return(value,root)
        if errors:raise ValueError('; '.join(errors))
        sha=digest(value)
        with self.transaction():
            old=self.db.execute('SELECT sha FROM returns_seen WHERE return_id=?',(value['return_id'],)).fetchone()
            if old:
                if old['sha']!=sha: raise ValueError('return ID reused with different contents')
                return {'status':'ALREADY_IMPORTED','accepted':False}
            active=self.db.execute('SELECT * FROM active WHERE episode_id=?',(value['episode_id'],)).fetchone()
            if not active or (active['packet_sha'],active['packet_id'])!=(value['base_packet']['sha256'],value['base_packet_id']):
                raise ValueError('return has stale or unknown active base packet')
            self.db.execute('INSERT INTO returns_seen VALUES(?,?,?,?)',(value['return_id'],sha,value['episode_id'],json.dumps(value,ensure_ascii=False)))
            for o in value['outputs']:
                self.db.execute('INSERT OR IGNORE INTO candidates(asset_id,sha,return_id) VALUES(?,?,?)',(o['asset_id'],o['file']['sha256'],value['return_id']))
        return {'status':'PENDING_BRAIN_REVIEW','return_sha256':sha,'accepted':False}
    def apply_decision(self,signed:dict,keys:dict)->dict:
        d=verify_signature(signed,keys,'creative');scope=d.get('scope',{});sha=digest(d)
        if d.get('operation')!='accept_return_outputs' or not isinstance(scope,dict): raise ValueError('wrong creative decision operation')
        with self.transaction():
            if self.db.execute('SELECT 1 FROM decisions WHERE decision_sha=?',(sha,)).fetchone(): return {'status':'ALREADY_APPLIED'}
            r=self.db.execute('SELECT * FROM returns_seen WHERE return_id=?',(scope.get('return_id'),)).fetchone()
            if not r or r['sha']!=scope.get('return_sha256'): raise ValueError('decision for another return version')
            actual=json.loads(r['payload']);active=self.db.execute('SELECT * FROM active WHERE episode_id=?',(r['episode_id'],)).fetchone()
            if not active or active['packet_sha']!=actual['base_packet']['sha256']: raise ValueError('creative decision base is stale')
            accepted=scope.get('accepted')
            if not isinstance(accepted,list) or not accepted: raise ValueError('explicit accepted artifact versions required')
            review=d.get('review_evidence')
            if not isinstance(review,list) or not review: raise ValueError('signed media decision lacks actual review evidence')
            for record in review:
                errors=verify_record(record,self.root)
                if errors: raise ValueError('; '.join(errors))
            if d.get('reviewed_subjects')!=accepted: raise ValueError('reviewed and accepted artifact scopes differ')
            available={(o['asset_id'],o['file']['sha256']) for o in actual['outputs']}
            if any(not isinstance(o,dict) or (o.get('asset_id'),o.get('sha256')) not in available for o in accepted): raise ValueError('decision invents artifact')
            for o in accepted:self.db.execute("UPDATE candidates SET status='ACCEPTED' WHERE asset_id=? AND sha=?",(o['asset_id'],o['sha256']))
            self.db.execute('INSERT INTO decisions VALUES(?,?)',(sha,json.dumps(d,ensure_ascii=False)))
        return {'status':'ACCEPTED_BY_SIGNED_DECISION','artifacts':accepted}
