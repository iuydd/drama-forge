#!/usr/bin/env python3
"""Offline v4.2 entry points. Never submits generation or installs dependencies."""
from __future__ import annotations
import argparse
import importlib.metadata
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools/production-ops/scripts'))
from brain_handoff import read_json, verify_record, SUPPORTED_POLICIES


def doctor(project:Path|None=None)->dict:
    names={'jsonschema':'jsonschema','cryptography':'cryptography','PIL':'Pillow','numpy':'numpy','fontTools':'fonttools'}
    dependencies={}
    for module,package in names.items():
        installed=importlib.util.find_spec(module) is not None
        try:version=importlib.metadata.version(package) if installed else None
        except importlib.metadata.PackageNotFoundError:version=None
        dependencies[package]={'available':installed,'version':version}
    schema=read_json(ROOT/'tools/visual-continuity-prompter/schemas/shot.schema.json')
    blockers=[]
    if set(schema['properties']['policy_version']['enum'])!=SUPPORTED_POLICIES:blockers.append('schema/runtime policy mismatch')
    if sys.version_info<(3,10):blockers.append('Python 3.10+ required')
    blockers.extend('missing dependency: '+k for k,v in dependencies.items() if not v['available'])
    executables={n:shutil.which(n) for n in ('ffmpeg','ffprobe')}
    live={'status':'NOT_CONFIGURED','checks':{},'verified_real_generation':False}
    if project is not None:
        project=Path(project).resolve(strict=True);config=project/'deployment.json'
        if config.is_file():
            value=read_json(config)
            if value.get('schema_version')!='drama-deployment-1':blockers.append('unknown deployment schema')
            checks={}
            for name in ('protected_host','submission_adapter','brain_media_input','reviewer_calibration','blind_isolation','text_route','pilot_episode'):
                record=value.get('checks',{}).get(name,{})
                has_evidence=isinstance(record,dict) and not verify_record(record.get('evidence'),project)
                checks[name]={'reported_status':record.get('status','NOT_RUN') if isinstance(record,dict) else 'NOT_RUN',
                              'evidence_file_verified':has_evidence,'independently_reexecuted':False}
            live={'status':'RECORDS_PRESENT_LIVE_VERIFICATION_REQUIRED','checks':checks,'verified_real_generation':False}
    return {'schema_version':'drama-doctor-1','policy_version':'4.2.0','offline_status':'READY' if not blockers else 'BLOCKED',
            'blockers':blockers,'dependencies':dependencies,'media_executables':executables,'live_deployment':live,
            'note':'Dependency/file checks only. No service connection, paid action, model calibration or host isolation is implied.'}


def main(argv=None)->int:
    p=argparse.ArgumentParser(description=__doc__);subs=p.add_subparsers(dest='command',required=True)
    d=subs.add_parser('doctor');d.add_argument('--project',type=Path)
    d=subs.add_parser('compile-prompt');d.add_argument('--ir',type=Path,required=True);d.add_argument('--backend',type=Path,required=True)
    for name in ('validate-return','pack-return'):
        d=subs.add_parser(name);d.add_argument('--file',type=Path,required=True);d.add_argument('--root',type=Path,required=True)
        if name=='pack-return':d.add_argument('--out',type=Path,required=True)
    d=subs.add_parser('unpack-return');d.add_argument('--capsule',type=Path,required=True);d.add_argument('--root',type=Path,required=True)
    d=subs.add_parser('diff-scopes');d.add_argument('--before',type=Path,required=True);d.add_argument('--after',type=Path,required=True)
    d=subs.add_parser('metrics');d.add_argument('--file',type=Path,required=True);d.add_argument('--root',type=Path)
    d=subs.add_parser('probe-media');d.add_argument('--file',type=Path,required=True);d.add_argument('--kind',choices=['image','video','audio'],required=True)
    args=p.parse_args(argv)
    try:
        if args.command=='doctor':result=doctor(args.project)
        elif args.command=='compile-prompt':
            from prompt_contract import compile_ir
            result=compile_ir(read_json(args.ir),read_json(args.backend))
        elif args.command in ('validate-return','pack-return'):
            from brain_exchange import validate_return,export_return
            value=read_json(args.file)
            if args.command=='validate-return':
                errors=validate_return(value,args.root);result={'status':'BLOCKED' if errors else 'PENDING_BRAIN_REVIEW','errors':errors,'accepted':False}
            else:result=export_return(value,args.root,args.out)
        elif args.command=='unpack-return':
            from brain_exchange import unpack_return
            result={'status':'PENDING_BRAIN_REVIEW','return':unpack_return(args.capsule,args.root),'accepted':False}
        elif args.command=='diff-scopes':
            from workflow_support import diff_scopes
            result=diff_scopes(read_json(args.before),read_json(args.after))
        elif args.command=='metrics':
            from evaluation_tools import paired_comparison
            result=paired_comparison(read_json(args.file),args.root)
        else:
            from media_validation import probe_media
            result=probe_media(args.file,args.kind)
        print(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False))
        return 2 if result.get('status')=='BLOCKED' or result.get('offline_status')=='BLOCKED' else 0
    except (ValueError,TypeError,KeyError,AttributeError,OSError,subprocess.SubprocessError,zipfile.BadZipFile) as exc:
        print(json.dumps({'status':'BLOCKED','error':str(exc),'executed_generation':False},ensure_ascii=False))
        return 2

if __name__=='__main__':raise SystemExit(main())
