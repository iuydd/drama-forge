"""Reference route regressions; synthetic local fixtures, no model/network call."""
from copy import deepcopy
import base64
import json
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest
import h3_reference as h
import brain_handoff as b
import preproduction as p
import test_v43_preproduction as old
import test_ensemble_gate as ensemble

VISUAL = Path(__file__).resolve().parents[2] / 'visual-continuity-prompter/scripts'
sys.path.insert(0, str(VISUAL))
import continuity_tools as c
import test_continuity_tools as compiler


def request():
    return {'kind':'video','shot_id':'S1','mode':'video_reference','video_input':'references',
            'inputs':[{'asset_id':'REF','role':'asset_ref','upload_index':1,'file':{'$asset':'REF','field':'file'}}],
            'required_asset_ids':['REF'],'background_motion':'树叶全程轻摆。',
            'prompt':'<Picture 1>提供已锁定场景设计。树叶全程轻摆。',
            'output_spec':{'profile':'SYNTHETIC_PROFILE','res':'SYNTHETIC_RES','aspect':'16:9','seconds':4,'width':8}}


def plan():
    req, part = old.fixture()
    part['manifest'] = [row for row in part['manifest'] if row['id'] not in {'A1','T1'}]
    part['records'] = [row for row in part['records'] if row['id'] not in {'A1','T1'}]
    old.modify(part,'T2',lambda t:t.update(depends_on=[],request_template=request()))
    return p.assemble([part],req)


class ReferenceRouteTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name)
        self.registry,self.record=old.media_registry(self.root)
        # A known 1x1 PNG, used only to exercise transport bytes and hashes.
        self.png=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a2ioAAAAASUVORK5CYII=')
        (self.root/'ref.bin').write_bytes(self.png)
        review=json.loads((self.root/'review.json').read_text());review['subject']=self.record('ref.bin')
        (self.root/'review.json').write_text(json.dumps(review))
        self.registry['assets'][0].update(file=self.record('ref.bin'),review=self.record('review.json'))
    def tearDown(self):self.tmp.cleanup()
    def bound(self):return p.bind_task(plan(),'T2',self.registry,self.root)
    def test_assets_directly_bind_without_start_frame(self):
        value=self.bound();self.assertEqual(value['request']['inputs'][0]['path'],'ref.bin')
        self.assertFalse(value['ready_for_submission']);self.assertEqual(value['request']['video_input'],'references')
    def test_exact_native_reference_payload(self):
        payload=h.native_payload(self.bound()['request'],self.root)
        self.assertEqual(payload['image_mode'],'reference');self.assertNotIn('frame',payload)
        self.assertEqual(base64.b64decode(payload['images'][0].split(',')[1]),self.png)
    def test_payload_preserves_real_array_order(self):
        value=self.bound()['request'];(self.root/'second.png').write_bytes(self.png+b'SYNTHETIC ORDER MARKER')
        value['inputs'].append(dict(self.record('second.png'),asset_id='SECOND',role='asset_ref',upload_index=2))
        value['required_asset_ids'].append('SECOND');value['prompt']+=' <Picture 2>提供道具。'
        payload=h.native_payload(value,self.root)
        self.assertNotEqual(payload['images'][0],payload['images'][1])
        self.assertEqual(base64.b64decode(payload['images'][1].split(',')[1]),self.png+b'SYNTHETIC ORDER MARKER')
    def test_no_silent_sort(self):
        value=request();value['inputs'][0]['upload_index']=2
        self.assertTrue(h.reference_errors(value))
    def test_missing_supporting_asset_blocks(self):
        value=request();value['required_asset_ids'].append('SUPPORTING_ACTOR');self.assertTrue(h.reference_errors(value))
    def test_primary_and_previous_frame_block(self):
        for change in ({'primary':True},{'role':'previous_end'},{'role':'start_frame'}):
            value=request();value['inputs'][0].update(change);self.assertTrue(h.reference_errors(value))
    def test_oversized_reference_set_blocks(self):
        value=request();value['inputs']*=7;self.assertTrue(h.reference_errors(value))
    def test_unknown_picture_or_missing_background_blocks(self):
        for prompt in ('<Picture 2>树叶全程轻摆。','<Picture 1>静态房间'):
            value=request();value['prompt']=prompt;self.assertTrue(h.reference_errors(value))
    def test_candidate_cannot_export(self):
        review=json.loads((self.root/'review.json').read_text());review['status']='CANDIDATE'
        (self.root/'review.json').write_text(json.dumps(review));self.registry['assets'][0]['review']=self.record('review.json')
        self.assertRaises(ValueError,self.bound)
    def test_missing_profile_cannot_export(self):
        for key in ('profile','res','aspect'):
            for missing in (None,'UNKNOWN','TODO','UNVERIFIED','{{profile}}','PLACEHOLDER','待确认','REPLACE_ME'):
                with self.subTest(key=key,value=missing):
                    value=self.bound()['request'];value['output_spec'][key]=missing
                    self.assertRaisesRegex(ValueError,'non-placeholder',h.native_payload,value,self.root)
    def test_missing_unknown_or_conflicting_mode_cannot_export(self):
        for mode in (None,'new_view','video_i2v','video_t2v','UNKNOWN'):
            value=request()
            if mode is None:value.pop('mode')
            else:value['mode']=mode
            self.assertTrue(h.reference_errors(value))
            self.assertRaisesRegex(ValueError,'mode=video_reference',h.native_payload,value,self.root)
    def test_changed_file_cannot_export(self):
        value=self.bound()['request'];(self.root/'ref.bin').write_bytes(b'changed')
        self.assertRaises(ValueError,h.native_payload,value,self.root)
    def test_asset_slot_cannot_bind_another_identity(self):
        value=plan();value['records']['T2']['request_template']['inputs'][0]['file']['$asset']='VIDEO'
        self.assertTrue(p.plan_errors(value))
    def test_keyframe_is_explicit_legacy_compatibility(self):
        req,part=old.fixture();self.assertEqual(p.assemble([part],req)['status'],'PLAN_COMPLETE')
    def test_legacy_snapshot_without_explicit_mode_stays_compatible(self):
        shot={'mode':'video_i2v','shot_id':'S1','references':[],'output':{}}
        self.assertNotIn('video_input',b.request_snapshot({},shot,{},'SYNTHETIC'))
        shot['video_input']='keyframe'
        self.assertEqual(b.request_snapshot({},shot,{},'SYNTHETIC')['video_input'],'keyframe')
    def test_explicit_keyframe_computed_snapshot_binds(self):
        req,part=old.fixture()
        ref={'asset_id':'REF','role':'start_frame','upload_index':1,
             'path':{'$asset':'REF','field':'path'},'sha256':{'$asset':'REF','field':'sha256'}}
        execution={'scene':{'id':'ROOM'},'shot':{'mode':'video_i2v','shot_id':'S1',
            'references':[ref],'output':{'width':8,'height':6}},'runtime_profile':{}}
        template=b.request_snapshot(execution['scene'],execution['shot'],execution['runtime_profile'],'SYNTHETIC literal video.')
        template.update(video_input='keyframe',image_mode='keyframe',configuration_sha256='COMPUTE_FROM_EXECUTION_TEMPLATE')
        old.modify(part,'T2',lambda task:task.update(request_template=template,execution_template=execution))
        value=p.assemble([part],req);self.assertEqual(p.plan_errors(value),[])
        bound=p.bind_task(value,'T2',self.registry,self.root);actual=bound['execution_inputs']
        self.assertEqual(bound['request'],b.request_snapshot(actual['scene'],actual['shot'],actual['runtime_profile'],template['prompt']))
        self.assertEqual(bound['request']['video_input'],'keyframe')
        self.assertEqual(bound['request']['image_mode'],'keyframe')
        self.assertNotIn('video_input',value['records']['T2']['execution_template']['shot'])
    def test_reference_computed_snapshot_keeps_explicit_provider_mode(self):
        value=plan();template=value['records']['T2']['request_template']
        template.update(image_mode='reference',configuration_sha256='COMPUTE_FROM_EXECUTION_TEMPLATE')
        ref={'asset_id':'REF','role':'asset_ref','upload_index':1,
             'path':{'$asset':'REF','field':'path'},'sha256':{'$asset':'REF','field':'sha256'}}
        execution={'scene':{'id':'ROOM'},'shot':{'mode':'video_reference','shot_id':'S1',
            'references':[ref],'output':deepcopy(template['output_spec']),
            'required_asset_ids':['REF'],'background_motion':template['background_motion']},'runtime_profile':{}}
        value['records']['T2']['execution_template']=execution
        self.assertEqual(p.plan_errors(value),[])
        bound=p.bind_task(value,'T2',self.registry,self.root);actual=bound['execution_inputs']
        self.assertEqual(bound['request'],b.request_snapshot(actual['scene'],actual['shot'],actual['runtime_profile'],template['prompt']))
        self.assertEqual(bound['request']['image_mode'],'reference')
        self.assertEqual(h.native_payload(bound['request'],self.root)['image_mode'],'reference')
    def test_reference_route_cannot_schedule_unnecessary_start_frame(self):
        req,part=old.fixture()
        old.modify(part,'T2',lambda t:t.update(depends_on=[],request_template=request()))
        self.assertRaises(ValueError,p.assemble,[part],req)
    def test_export_cli_binds_and_writes_without_submission(self):
        (self.root/'plan.json').write_text(json.dumps(plan()))
        (self.root/'registry.json').write_text(json.dumps(self.registry))
        output=self.root/'native.json'
        proc=subprocess.run([sys.executable,str(Path(p.__file__)),'export-h3',
            '--plan',str(self.root/'plan.json'),'--registry',str(self.root/'registry.json'),
            '--task','T2','--root',str(self.root),'--out',str(output)],capture_output=True,text=True)
        self.assertEqual(proc.returncode,0,proc.stdout+proc.stderr)
        value=json.loads(output.read_text());self.assertEqual(value['endpoint'],'/api/v1/generate')
        self.assertEqual(value['native_payload']['image_mode'],'reference')
        self.assertFalse(value['production_started']);self.assertFalse(value['ready_for_submission'])


class ReferenceCompilerTests(unittest.TestCase):
    def setUp(self):
        self.old=compiler.ContractTests('test_valid_production_contract');self.old.setUp()
        self.shot=self.old.shot;self.shot.update(mode='video_reference',video_input='references',
            background_motion='窗帘全程轻摆。',required_asset_ids=[r['asset_id'] for r in self.shot['references']],
            video={'duration_s':4,'fps':24,'action_beats':[{'start_s':0,'end_s':4,'action':'人物自然呼吸，窗帘轻摆'}],'end_state_description':'保持身份与房间布局'})
        for ref in self.shot['references']:ref.pop('primary');ref['role']='asset_ref'
        self.shot['output']['media_kind']='video';self.shot['qa_required']=sorted(c.VIDEO_CHECKS)
        self.old.profile['features']['reference_to_video']='verified'
        self.old.profile['parameter_map'].update({k:k for k in ('res','aspect','image_mode')})
    def tearDown(self):self.old.tearDown()
    def test_compiler_accepts_no_primary_and_renders_picture_roles(self):
        self.assertEqual(self.old.errors(),[])
        out=c.compile_package(self.old.scene,self.shot,self.old.profile,self.old.root,True)
        self.assertEqual(out['status'],'READY');self.assertIn('<Picture 1>',out['prompt'])
        self.assertIn('窗帘全程轻摆。',out['prompt']);self.assertNotIn('从输入图片?',out['prompt'])
    def test_reference_capability_is_not_inferred_from_i2v(self):
        del self.old.profile['features']['reference_to_video'];self.assertTrue(self.old.errors())
    def test_reference_style_preserves_scene_design_and_locked_sentence(self):
        self.shot['style_lock']={'style_id':'STYLE','version':'1','status':'locked',
            'prompt_sentence':'EXACT_LOCKED_STYLE_SENTENCE'}
        prompt=c.render_prompt(self.old.scene,self.shot,self.old.profile)
        self.assertIn('EXACT_LOCKED_STYLE_SENTENCE',prompt)
        self.assertIn('现有画风与场景设计',prompt)
        self.assertIn('呈现目标机位及已锁定的镜头运动',prompt)
        self.assertNotIn('重建空间',prompt)
        self.assertEqual(self.old.errors(),[])
    def test_reference_video_requires_exact_target_scene_master(self):
        source=deepcopy(self.shot['references'][0])
        replacements=[{'asset_id':'ARBITRARY-SCENE'}, {'scene_id':'ANOTHER-SCENE'},
            {'scene_version':'OTHER-VERSION'}, {'view_id':'ANOTHER-VIEW'}, {'state_id':'OTHER-STATE'},
            self.old.record('other-master.bin',b'synthetic different scene image')]
        for change in replacements:
            with self.subTest(change=change):
                self.shot['references'][0]={**source,**change,'primary':False}
                self.shot['required_asset_ids']=[r['asset_id'] for r in self.shot['references']]
                self.assertTrue(self.old.errors())
                self.assertEqual(c.compile_package(self.old.scene,self.shot,self.old.profile,self.old.root,True)['status'],'DRAFT')
        for key in ('scene_id','scene_version','view_id','state_id'):
            with self.subTest(missing=key):
                self.shot['references'][0]=deepcopy(source);self.shot['references'][0].pop(key)
                self.assertTrue(self.old.errors())
    def test_reference_video_cannot_relabel_another_registered_view(self):
        other={**deepcopy(self.old.scene['views'][0]),'view_id':'VIEW-B','asset_id':'MASTER-B-1',
            **self.old.record('view-b.bin',b'synthetic other approved view')}
        self.old.scene['views'].append(other)
        self.shot['view_id']='VIEW-B'
        self.assertTrue(self.old.errors())
        self.shot['references'][0]['view_id']='VIEW-B'
        self.assertTrue(self.old.errors())
        self.shot['references'][0].update(asset_id=other['asset_id'],path=other['path'],sha256=other['sha256'])
        self.shot['required_asset_ids']=[r['asset_id'] for r in self.shot['references']]
        self.assertEqual(self.old.errors(),[])
        self.shot['view_id']='VIEW-UNKNOWN';self.assertTrue(self.old.errors())
    def test_reference_video_master_state_is_not_only_a_label(self):
        self.old.scene['views'][0]['state_id']='OTHER-STATE'
        self.assertTrue(self.old.errors())
    def test_schema_accepts_reference_role_without_primary(self):
        import jsonschema
        schema=json.loads((VISUAL.parent/'schemas/shot.schema.json').read_text())
        jsonschema.Draft202012Validator(schema).validate(self.shot)


class ReferencePreflightTests(unittest.TestCase):
    def setUp(self):
        self.old=ensemble.EnsembleGateTests('test_complete_record_integrity_only');self.old.setUp()
        root=self.old.root;registry,record=old.media_registry(root)
        self.request=request();self.request['inputs'][0].pop('file');self.request['inputs'][0].update(record('ref.bin'))
        self.old.put('request.json',self.request);self.old.put('registry.json',registry)
        self.old.s['video_input']='references'
        self.old.binding.update(media=record('request.json'),asset_registry=record('registry.json'))
        self.old.shot.update(mode='video_reference',video_input='references',references=deepcopy(self.request['inputs']),
            required_asset_ids=['REF'],background_motion=self.request['background_motion'],
            entity_asset_ids={eid:'REF' for eid in ensemble.eg.module().visible_ids(self.old.b)})
        self.old.r=[r for r in self.old.r if r['check_id'] not in {'start_frame_gate','ensemble_continuity'}]
        row=deepcopy(self.old.r[0]);row.update(check_id='reference_assets',details={'shot_ids':['S1']})
        self.old.r.append(row);self.old.refresh()
    def tearDown(self):self.old.tearDown()
    def test_reference_preflight_does_not_require_start_frame(self):
        self.assertEqual(self.old.gate()['status'],'ACCEPTED')
    def test_visible_actor_mapping_cannot_be_omitted(self):
        self.old.shot['entity_asset_ids'].pop(next(iter(self.old.shot['entity_asset_ids'])))
        self.old.refresh();self.assertEqual(self.old.gate()['status'],'BLOCKED')
    def test_actual_uploaded_order_must_match_contract(self):
        self.old.shot['references'][0]['upload_index']=2;self.old.refresh()
        self.assertEqual(self.old.gate()['status'],'BLOCKED')
    def test_reference_gate_still_requires_acceptance(self):
        self.old.binding.pop('asset_registry');self.old.refresh();self.assertEqual(self.old.gate()['status'],'BLOCKED')


if __name__=='__main__':unittest.main()
