#!/usr/bin/env python3
"""Optional synchronous OpenAI Responses transport for upfront TEXT ONLY.

No default model, no browser automation, no media tools. CLI requires explicit
API-call authorization; credentials stay in the environment. A durable claim
prevents a blind resend after timeout. Not executed during package creation.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import urllib.request
import urllib.error
from brain_handoff import read_json, digest, text
from preproduction import ROOT, MAX_BYTES, strict_json, part_errors, prepare, assemble

ENDPOINT='https://api.openai.com/v1/responses'


def payload_for(message: dict, model: str, max_output_tokens: int) -> dict:
    if not text(model): raise ValueError('explicit verified API model required; no model substitution')
    if type(max_output_tokens) is not int or max_output_tokens<1: raise ValueError('positive output token cap required')
    if not text(message.get('instructions')) or not text(message.get('input')): raise ValueError('complete brain message required')
    return {'model':model,'instructions':message['instructions'],'input':message['input'],
            'text':{'format':{'type':'json_object'}},'tools':[],
            'max_output_tokens':max_output_tokens,'store':False}


def extract_part(response: dict) -> dict:
    if not isinstance(response,dict) or response.get('status')!='completed':
        raise ValueError('API response incomplete/failed; not a complete production plan')
    texts=[]
    for item in response.get('output',[]):
        if item.get('type')!='message': continue
        for c in item.get('content',[]):
            if c.get('type')=='refusal': raise ValueError('brain refusal; no production')
            if c.get('type')=='output_text': texts.append(c.get('text',''))
    if not texts: raise ValueError('no completed textual brain output')
    part=strict_json(''.join(texts));errors=part_errors(part)
    if errors: raise ValueError('; '.join(errors))
    return part


def post_once(payload: dict, state_dir: Path, *, authorized: bool, opener=None) -> dict:
    if authorized is not True: raise ValueError('API call permission missing')
    api_key=os.environ.get('OPENAI_API_KEY')
    if not api_key: raise ValueError('OPENAI_API_KEY missing')
    if state_dir.is_symlink(): raise ValueError('state directory cannot be symbolic link')
    state_dir.mkdir(parents=True,exist_ok=True,mode=0o700)
    key=digest(payload);claim=state_dir/(key+'.claim');saved=state_dir/(key+'.response.json')
    if saved.exists():
        if saved.is_symlink(): raise ValueError('unsafe saved response')
        return read_json(saved)
    if claim.exists(): raise ValueError('request already claimed or outcome unknown; reconcile, do not resend')
    with claim.open('x',encoding='utf-8') as f:
        json.dump({'status':'SUBMISSION_UNKNOWN_UNTIL_RECEIPT','payload_sha256':key},f);f.flush();os.fsync(f.fileno())
    request=urllib.request.Request(ENDPOINT,data=json.dumps(payload,ensure_ascii=False,allow_nan=False).encode(),headers={'Authorization':'Bearer '+api_key,'Content-Type':'application/json'},method='POST')
    if opener is None:
        # Refuse redirects so an API key cannot be forwarded to an unapproved host.
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self,*a,**kw): return None
        opener=urllib.request.build_opener(NoRedirect()).open
    try:
        with opener(request,timeout=240) as response:
            raw=response.read(MAX_BYTES+1)
        if len(raw)>MAX_BYTES: raise ValueError('brain response exceeds safe local cap')
        value=strict_json(raw.decode('utf-8'))
        temp=state_dir/(key+'.response.tmp')
        with temp.open('x',encoding='utf-8') as f:
            json.dump(value,f,ensure_ascii=False,allow_nan=False);f.flush();os.fsync(f.fileno())
        temp.replace(saved)
        # Only receipt identity/usage metadata; no API key or private reasoning in logs.
        (state_dir/(key+'.receipt.json')).write_text(json.dumps({'response_id':value.get('id'),'status':value.get('status'),'usage':value.get('usage'),'payload_sha256':key},ensure_ascii=False),encoding='utf-8')
        return value
    except Exception as ex:
        # Deliberately no automatic retry, even if a provider's idempotency is unknown.
        raise RuntimeError('brain call unresolved/failed ('+type(ex).__name__+'); saved claim prevents duplicate spending') from None


def collect(request: dict, *, model: str, max_calls: int, max_output_tokens: int,
            state_dir: Path, authorized: bool, sender=None) -> dict:
    if authorized is not True: raise ValueError('brain API not authorized')
    if type(max_calls) is not int or not 1<=max_calls<=100: raise ValueError('explicit finite brain call cap required (1..100)')
    message=prepare(request);parts=[]
    send=sender or (lambda payload:post_once(payload,state_dir,authorized=authorized))
    for index in range(1,max_calls+1):
        payload=payload_for(message,model,max_output_tokens)
        part=extract_part(send(payload))
        if part['part_index']!=index: raise ValueError('brain continuation part order mismatch')
        parts.append(part);plan=assemble(parts,request)
        if plan['status']=='PLAN_COMPLETE': return plan
        if plan['status']=='BLOCKED': raise ValueError('brain explicitly blocked text plan')
        continuation={'project_id':request['project_id'],'request_id':request['request_id'],
                      'plan_id':part['plan_id'],'revision':part['revision'],'next_part_index':index+1,
                      'manifest':part['manifest'],'missing_records':plan['missing_records'],
                      'accepted_records':plan['records'],'episode_ids':part['episode_ids']}
        # With store:false explicitly supply previous content; no hidden conversation memory.
        base=prepare(request)
        note=(ROOT/'prompts/agent-to-brain-continue.txt').read_text(encoding='utf-8').replace('{{CONTINUATION_JSON}}',json.dumps(continuation,ensure_ascii=False))
        message={**base,'input':base['input']+'\n\n'+note}
    raise ValueError('upfront text incomplete at authorized call cap; no media generation')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--request',type=Path,required=True)
    p.add_argument('--model',required=True);p.add_argument('--max-calls',type=int,required=True)
    p.add_argument('--max-output-tokens',type=int,required=True);p.add_argument('--state-dir',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True);p.add_argument('--allow-brain-api',action='store_true')
    a=p.parse_args()
    try:
        if a.out.exists(): raise ValueError('output exists; do not overwrite project plan')
        plan=collect(read_json(a.request),model=a.model,max_calls=a.max_calls,max_output_tokens=a.max_output_tokens,state_dir=a.state_dir,authorized=a.allow_brain_api)
        a.out.parent.mkdir(parents=True,exist_ok=True)
        with a.out.open('x',encoding='utf-8') as f: json.dump(plan,f,ensure_ascii=False,indent=2,allow_nan=False)
        print(json.dumps({'status':'PLAN_COMPLETE','output':str(a.out),'media_generated':False,'media_approved':False}))
        return 0
    except (OSError,ValueError,RuntimeError,KeyError,TypeError) as ex:
        print(json.dumps({'status':'BLOCKED','error':str(ex),'media_generated':False},ensure_ascii=False));return 2

if __name__=='__main__': raise SystemExit(main())
