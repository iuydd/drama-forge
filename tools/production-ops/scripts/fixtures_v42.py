"""Synthetic v4.2 test helpers. Never production permissions or quality evidence."""
from copy import deepcopy
from datetime import datetime,timedelta,timezone
from pathlib import Path
import hashlib
import json
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
import brain_handoff as b
import prompt_contract as p
from trusted_runtime import sign


def keys():
    private=Ed25519PrivateKey.generate()
    raw=private.private_bytes(serialization.Encoding.Raw,serialization.PrivateFormat.Raw,serialization.NoEncryption())
    pub=private.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)
    return raw,{'TEST_KEY':{'public_hex':pub.hex(),'purposes':['creative','budget']}}


def signed(raw,purpose,**fields):
    now=datetime.now(timezone.utc)
    return sign({'purpose':purpose,'issued_at':(now-timedelta(seconds=1)).isoformat(),'expires_at':(now+timedelta(hours=1)).isoformat(),**fields},raw,'TEST_KEY')


def intent(mode='video_i2v'):
    strategy={'video_i2v':'motion_focused','image_edit':'edit_delta','image_new':'full_scene','video_t2v':'full_scene'}[mode]
    backend={'schema_version':'prompt-backend-1','profile_id':'SYNTHETIC_TEST_ADAPTER','mode':mode,'strategy':strategy,'native_audio':True,'speech_format':'literal','max_prompt_bytes':None}
    ir={'schema_version':'prompt-ir-1','mode':mode,'backend_profile_id':backend['profile_id'],'primary_goal':'SYNTHETIC: readable state, not actual footage',
        'dimensions':{k:'SYNTHETIC same-state plan' for k in sorted(p.DIMENSIONS)},'unresolved_conflicts':[],
        'clauses':[{'id':'context','kind':'context','text':'SYNTHETIC approved scene context.','required':False,'provided_by_reference':True,'reference_asset_id':'REF'},
                   {'id':'lock','kind':'invariant','text':'SYNTHETIC fixed cup position.','required':True,'read_keys':['CUP.anchor'],'write_keys':[]},
                   {'id':'camera','kind':'camera','text':'SYNTHETIC fixed camera.','required':True}],
        'priority':{'hard':['lock','camera'],'soft':['context']},'must_show':['lock'],'invariant_keys':['CUP.anchor'],'resources':[]}
    return ir,backend


def seed_return(root:Path):
    from PIL import Image
    root.mkdir(parents=True,exist_ok=True)
    Image.new('RGB',(12,8)).save(root/'image.png')
    (root/'receipt.json').write_text('{"test_only":true,"job_id":"JOB"}')
    request={'kind':'start_frame','shot_id':'S1','prompt':'SYNTHETIC frozen prompt','inputs':[],'output_spec':{'width':12,'height':8}}
    packet={'schema_version':'brain-packet-1','policy_version':'4.2.0','packet_id':'P','episode_id':'EP001','phase':'start_frames','status':'LOCKED',
            'tasks':[{'task_id':'T','request':request,'request_sha256':b.digest(request)}]}
    (root/'packet.json').write_text(json.dumps(packet))
    def record(n):return {'path':n,'sha256':hashlib.sha256((root/n).read_bytes()).hexdigest()}
    r={'schema_version':'brain-return-2','return_id':'R','episode_id':'EP001','phase':'start_frames','base_packet_id':'P','base_packet':record('packet.json'),
       'status':'NEEDS_BRAIN_REVIEW','outputs':[{'asset_id':'A','task_id':'T','file':record('image.png'),'media_kind':'image','status':'CANDIDATE'}],
       'actual_requests':[{'task_id':'T','job_id':'JOB','request':request,'request_sha256':b.digest(request),'receipt':record('receipt.json')}],
       'observations':[],'issues':[],'decisions_needed':['SYNTHETIC review needed'],
       'cost_and_retry_state':{'settled_minor':0,'reserved_minor':0,'unknown_job_ids':[]}}
    return r,packet
