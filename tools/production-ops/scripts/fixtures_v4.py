"""Synthetic local test data only. Never use this as a production approval."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import brain_handoff as b
import fidelity_contract as f


def contract(categories=None):
    categories = list(f.CATEGORIES) if categories is None else categories
    expected = {
      'direction': dict(subject_id='CAR', world_heading='+X', screen_heading='right',
          screen_motion='stationary', view_id='CAM', axis_side='A', transition_basis='same-side, no turn'),
      'gaze': dict(actor_id='PERSON', target_id='PAPER', trigger='writing', body='toward desk',
          head='down toward paper', eyes='pen contact', permitted_deviation='natural blink only during key action'),
      'action': dict(actor_id='PERSON', effector='right hand pen', target_id='PAPER', precondition='blank',
          contact='tip touches', change='ink follows tip', postcondition='ink remains', persistence='same ink next view', release_required=True),
      'text': dict(text_id='TEXT', prop_id='PAPER', side='front', exact_text='请轻放', appearance='handwritten',
          method='tracked_texture', reveal_rule='stroke path follows actual tip', legibility_window='result'),
      'placement': dict(prop_id='POSTER', surface_id='WALL_A', local_anchor='MARK_A',
          reference_landmarks='left of door seam', size='same physical size', rotation='upright', persistence='unchanged'),
      'performance': dict(speaker_id='ELDER', line_ids=['L1','L2'], trigger='realization', before='greeting',
          after='doubt', listener_id='PERSON', visible_response='brows narrow and glance back')}
    requirements = []
    for category in sorted(categories):
        points = {'start_frame': ['initial_state'], 'video': ['observed_state'], 'final': ['combined_event']}
        equals = {}
        if category == 'direction':
            equals = {'video': {'observed_state': {'screen_heading': 'right', 'world_heading': '+X'}}}
        elif category == 'gaze':
            equals = {'video': {'observed_state': {'target_id': 'PAPER'}}}
        elif category == 'action':
            points['video'] = ['precondition','contact','change','result','after_release']
            equals = {'video': {'change': {'visible_change': True}, 'after_release': {'persistent_result': True}}}
        elif category == 'text':
            points['final'] = ['readable_text']
        elif category == 'placement':
            equals = {'video': {'observed_state': {'surface_id': 'WALL_A', 'local_anchor': 'MARK_A'}}}
        elif category == 'performance':
            points = {'video': ['before','trigger','after','contrast'], 'final': ['audible_contrast']}
            equals = {'video': {'after': {'intent': 'doubt'}, 'contrast': {'audible_change': True}}}
        requirements.append({'id': category.upper(), 'category': category,
            'expected': expected[category], 'points': points, 'equals': equals})
    return {'schema_version':'shot-fidelity-1','status':'LOCKED','example_only':False,
        'episode_id':'EP001','shot_id':'S1','scene_id':'ROOM','view_id':'CAM','revision':'TEST_ONLY',
        'risks':{c:{'applicable':c in categories,'basis':'SYNTHETIC TEST, not a real shot decision'} for c in sorted(f.CATEGORIES)},
        'requirements':requirements}


class Fixture:
    def __init__(self, root, categories=None, media_name='media.bin'):
        self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True)
        self.media_name=media_name
        if not (self.root/media_name).exists():
            (self.root/media_name).write_bytes(b'SYNTHETIC NON-MEDIA TEST BYTES')
        (self.root/'proof.md').write_text('SYNTHETIC TEST ONLY. Not a real approval or media observation.')
        self.contract=contract(categories);self.save_contract()
        self.request={'kind':'video','shot_id':'S1','prompt':'Synthetic frozen prompt; not production.',
            'inputs':[dict(self.record(media_name),asset_id='REF',role='start_frame',upload_index=1)],
            'output_spec':{'width':8,'height':6,'media_kind':'video'},'mode':'video_i2v',
            'configuration_sha256':'0'*64}
        self.packet={'schema_version':'brain-packet-1','policy_version':'4.0.0',
            'packet_id':'TEST_PACKET','revision':'1','episode_id':'EP001','phase':'video',
            'status':'LOCKED','decision_owner':'chatgpt_brain','example_only':False,
            'approval_evidence':self.record('proof.md'),'reviewed_inputs':deepcopy(self.request['inputs']),
            'blocking_questions':[], 'tasks':[{'task_id':'TASK1','status':'READY',
              'request':self.request,'request_sha256':b.digest(self.request),'fidelity_contract':self.record('fidelity.json')}]}
        self.save_packet()
    def put(self,name,data):
        (self.root/name).write_text(json.dumps(data,ensure_ascii=False,allow_nan=False))
    def record(self,name):
        return {'path':name,'sha256':hashlib.sha256((self.root/name).read_bytes()).hexdigest()}
    def save_contract(self):
        self.put('fidelity.json',self.contract)
    def save_packet(self):
        self.put('packet.json',self.packet)
        self.binding={'packet':self.record('packet.json'),'task_id':'TASK1'}
    def sync_request(self):
        self.packet['tasks'][0]['request']=deepcopy(self.request)
        self.packet['tasks'][0]['request_sha256']=b.digest(self.request)
        self.packet['tasks'][0]['fidelity_contract']=self.record('fidelity.json')
        self.packet['reviewed_inputs']=deepcopy(self.request['inputs'])
        self.save_packet()
    def context(self):
        return {'S1':{'contract':self.contract,'record':self.record('fidelity.json'),
                     'media':self.record(self.media_name)}}
    def review(self,stage='video'):
        media=self.record(self.media_name)['sha256'];requirements=[]
        for req in self.contract['requirements']:
            if stage not in req['points']:continue
            points=[]
            for index,name in enumerate(req['points'][stage]):
                values=deepcopy(req.get('equals',{}).get(stage,{}).get(name,{}))
                if req['category']=='text' and stage=='final' and name=='readable_text':
                    values['text']=req['expected']['exact_text']
                point={'id':name,'result':'PASS','observation':'Synthetic test observation only.',
                    'media_sha256':media,'evidence':[self.record('proof.md')],
                    'locator':({'kind':'image','region':'synthetic full image'} if stage=='start_frame'
                               else {'kind':'frames','start':0,'end':100,'clock':'subject'}),
                    'modality':'audio_video' if req['category']=='performance' else ('image' if stage=='start_frame' else 'video'),
                    'values':values}
                if req['category']=='action' and stage=='video':point['event_frame']=index*10
                points.append(point)
            requirements.append({'id':req['id'],'points':points})
        return {'stage':stage,'subject_sha256':media,'shots':[{'shot_id':'S1',
            'contract_sha256':self.record('fidelity.json')['sha256'],'media_sha256':media,
            'requirements':requirements}]}
    def point(self,review,category,point=None):
        req=next(r for r in review['shots'][0]['requirements'] if r['id']==category.upper())
        return next(p for p in req['points'] if p['id']==point) if point else req['points'][0]
