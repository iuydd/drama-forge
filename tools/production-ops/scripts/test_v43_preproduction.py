"""Synthetic preproduction exchange/acceptance probes; no model/network calls."""
from copy import deepcopy
from pathlib import Path
import hashlib
import json
import sys
import tempfile
import unittest
from unittest.mock import patch
import brain_handoff as b
import preproduction as p
import brain_transport as tr


def fixture():
    request={'project_id':'SYNTHETIC-P','request_id':'REQUEST-1','user_brief':'SYNTHETIC two-shot test, not a real drama','episode_ids':['EP1'],'source_texts':[],'existing_assets':[{'asset_id':'REF'}],'media_profiles':{},'quality_limits':{'width':8}}
    request['legacy_brain_compatibility']=True
    risks={k:'SYNTHETIC explicitly not applicable or invariant under this test' for k in p.RISKS}
    def task(tid,kind,produces,depends=None,refs=None):
        return {'task_id':tid,'episode_id':'EP1','shot_id':'S1','kind':kind,'depends_on':depends or [],'produces':produces,
                'request_template':{'kind':kind,'shot_id':'S1','prompt':'SYNTHETIC complete literal instruction, no real scene.','inputs':refs or [],'output_spec':{'width':8,'height':6},'mode':'test',**({'video_input':'keyframe'} if kind=='video' else {})},
                'requirements':deepcopy(risks),'state':{'in':{'object':'same'},'out':{'object':'same'},'allowed_changes':[],'transition':'same-view synthetic state'},'acceptance':['SYNTHETIC required observable state'],'execution_template':None}
    ref={'asset_id':'REF','role':'identity','upload_index':1,'file':{'$asset':'REF','field':'file'}}
    records=[('W','world',None,{'characters':[],'locations':[{'id':'ROOM'}],'initial_state':{'object':'same'},'events':[],'continuity_rules':['same state']}),
             ('E1','episode','EP1',{'episode_id':'EP1','script':'Synthetic complete script: an object remains on a table. This is test data, not footage.','shot_ids':['S1'],'dialogue':[],'edit_plan':{'order':['S1']},'qa_targets':['SYNTHETIC object remains']}),
             ('A0','asset',None,{'asset_id':'REF','description':'SYNTHETIC existing reference','media_kind':'image','producer_task_id':None,'existing':True,'acceptance':['identity']}),
             ('A1','asset','EP1',{'asset_id':'FRAME','description':'SYNTHETIC first frame','media_kind':'image','producer_task_id':'T1','existing':False,'acceptance':['same state']}),
             ('A2','asset','EP1',{'asset_id':'VIDEO','description':'SYNTHETIC output','media_kind':'video','producer_task_id':'T2','existing':False,'acceptance':['same state']}),
             ('T1','task','EP1',task('T1','start_frame',['FRAME'],refs=[ref])),
             ('T2','task','EP1',task('T2','video',['VIDEO'],depends=['T1'],refs=[{'asset_id':'FRAME','role':'start_frame','upload_index':1,'file':{'$asset':'FRAME','field':'file'}}])),
             ('D','delivery',None,{'episode_order':['EP1'],'production_order':'finish_episode_then_next','required_gates':['G0','G1','G2','G3','G4'],'max_attempts_per_failure_chain':3,'auto_publish':False,'stop_conditions':['unresolved hard failure'],'audio_and_edit':{}})]
    part={'schema_version':'brain-preproduction-response-1','workflow_mode':'upfront_only',**{k:request[k] for k in ('project_id','request_id','episode_ids')},'plan_id':'PLAN','revision':'1','status':'COMPLETE','part_index':1,
          'manifest':[{'id':i,'kind':k,'episode_id':ep} for i,k,ep,v in records],
          'records':[{'id':i,'content':json.dumps(v,ensure_ascii=False)} for i,k,ep,v in records],
          'assumptions':[],'execution_blockers':[],'invalidates':[]}
    return request,part


def modify(part,rid,fn):
    row=next(x for x in part['records'] if x['id']==rid);data=json.loads(row['content']);fn(data);row['content']=json.dumps(data)


def media_registry(root):
    (root/'ref.bin').write_bytes(b'SYNTHETIC BYTES ONLY')
    (root/'evidence.txt').write_text('SYNTHETIC observation, not real media evidence')
    def record(name):return {'path':name,'sha256':hashlib.sha256((root/name).read_bytes()).hexdigest()}
    report={'status':'ACCEPTED','subject':record('ref.bin'),'reviewer_role':'production_reviewer','reviewer_id':'TEST_REVIEWER','observation':'SYNTHETIC fixture','full_required_scope_observed':True,'evidence':[record('evidence.txt')]}
    (root/'review.json').write_text(json.dumps(report))
    return {'schema_version':'accepted-asset-registry-1','assets':[{'asset_id':'REF','file':record('ref.bin'),'review':record('review.json')}]},record


class Preproduction43Tests(unittest.TestCase):
    def setUp(self):self.req,self.part=fixture()
    def plan(self):return p.assemble([self.part],self.req)
    def rejects(self):
        with self.assertRaises(ValueError):self.plan()
    def test_prepare_includes_full_brain_and_task(self):
        m=p.prepare(self.req);self.assertIn('upfront_only',m['instructions']);self.assertIn(self.req['user_brief'],m['input']);self.assertEqual(m['tools'],[])
    def test_prepare_explicit_scope(self):
        self.req['episode_ids']=[]
        with self.assertRaises(ValueError):p.prepare(self.req)
    def test_complete_not_media_or_money_approval(self):
        x=self.plan();self.assertEqual(x['status'],'PLAN_COMPLETE');self.assertFalse(x['media_approved']);self.assertFalse(x['spending_authorized'])
    def test_strict_duplicate_keys(self):
        with self.assertRaises(ValueError):p.strict_json('{"a":1,"a":2}')
    def test_strict_nonfinite(self):
        with self.assertRaises(ValueError):p.strict_json('{"a":NaN}')
    def test_unknown_outer_field_blocks(self):self.part['invented']=1;self.rejects()
    def test_wrong_project_blocks(self):self.part['project_id']='OTHER';self.rejects()
    def test_wrong_episode_scope_blocks(self):self.part['episode_ids']=['EP2'];self.rejects()
    def test_missing_scope_not_filled_by_agent(self):self.part['records']=[r for r in self.part['records'] if r['id']!='E1'];self.assertEqual(self.plan()['status'],'INCOMPLETE')
    def test_partials_assemble_only_when_complete(self):
        a=deepcopy(self.part);a['status']='PARTIAL';a['records']=a['records'][:3]
        c=deepcopy(self.part);c['part_index']=2;c['records']=c['records'][3:]
        self.assertEqual(p.assemble([a],self.req)['status'],'INCOMPLETE');self.assertEqual(p.assemble([a,c],self.req)['status'],'PLAN_COMPLETE')
    def test_duplicate_part_idempotent(self):self.assertEqual(p.assemble([self.part,self.part],self.req)['status'],'PLAN_COMPLETE')
    def test_conflicting_part_blocks(self):
        other=deepcopy(self.part);other['assumptions']=['new']
        with self.assertRaises(ValueError):p.assemble([self.part,other],self.req)
    def test_missing_index_blocks(self):self.part['part_index']=2;self.rejects()
    def test_blocked_response_never_complete(self):self.part['status']='BLOCKED';self.assertEqual(self.plan()['status'],'BLOCKED')
    def test_mixed_manifest_blocks(self):
        a=deepcopy(self.part);a['status']='PARTIAL';c=deepcopy(self.part);c['part_index']=2;c['manifest'].reverse()
        with self.assertRaises(ValueError):p.assemble([a,c],self.req)
    def test_missing_start_frame_blocks(self):modify(self.part,'T1',lambda x:x.update(kind='asset_image',request_template={**x['request_template'],'kind':'asset_image'}));self.rejects()
    def test_missing_video_blocks(self):modify(self.part,'T2',lambda x:x.update(kind='audio',request_template={**x['request_template'],'kind':'audio'}));self.rejects()
    def test_dependency_cycle_blocks(self):modify(self.part,'T1',lambda x:x.update(depends_on=['T2']));self.rejects()
    def test_unknown_input_asset_blocks(self):modify(self.part,'T2',lambda x:x['request_template']['inputs'][0]['file'].update({'$asset':'UNKNOWN'}));self.rejects()
    def test_producer_dependency_cannot_be_omitted(self):modify(self.part,'T2',lambda x:x.update(depends_on=[]));self.rejects()
    def test_asset_requires_producer(self):modify(self.part,'A1',lambda x:x.update(producer_task_id='MISSING'));self.rejects()
    def test_new_asset_cannot_claim_existing(self):modify(self.part,'A1',lambda x:x.update(existing=True,producer_task_id=None));self.rejects()
    def test_prompt_placeholder_blocks(self):modify(self.part,'T2',lambda x:x['request_template'].update(prompt='{{fill this}}'));self.rejects()
    def test_missing_risk_basis_blocks(self):modify(self.part,'T2',lambda x:x['requirements'].pop('gaze'));self.rejects()
    def test_dialogue_completion_cannot_replace_end_state(self):
        modify(self.part,'T2',lambda x:x['state'].update(out={'lines_done':['LINE-1']}))
        with self.assertRaisesRegex(ValueError,'end state lost fact: object'):self.plan()
    def test_nested_held_object_cannot_disappear_from_end_state(self):
        modify(self.part,'T2',lambda x:x['state'].update(
            **{'in':{'actor':{'present':True,'holding':'FOLDER'}},
               'out':{'actor':{'present':True}}}))
        with self.assertRaisesRegex(ValueError,'end state lost fact: actor.holding'):self.plan()
    def test_entity_object_cannot_be_replaced_to_hide_its_facts(self):
        for replacement in (None,'gone',[]):
            with self.subTest(replacement=replacement):
                modify(self.part,'T2',lambda x:x['state'].update(
                    **{'in':{'actor':{'present':True,'holding':'FOLDER'}},
                       'out':{'actor':replacement}}))
                with self.assertRaisesRegex(ValueError,'end state lost fact: actor'):self.plan()
    def test_explicit_exit_and_release_preserve_state_facts(self):
        modify(self.part,'T2',lambda x:x['state'].update(
            **{'in':{'actor':{'present':True,'holding':'FOLDER'}},
               'out':{'actor':{'present':False,'holding':None},'lines_done':['LINE-1']},
               'allowed_changes':['actor exits after returning the folder'],
               'transition':'actor puts folder down and exits through the door'}))
        self.assertEqual(self.plan()['status'],'PLAN_COMPLETE')
    def test_changed_quality_blocks(self):modify(self.part,'T2',lambda x:x['request_template']['output_spec'].update(width=4));self.rejects()
    def test_no_silent_publish(self):modify(self.part,'D',lambda x:x.update(auto_publish=True));self.rejects()
    def test_all_gates_required(self):modify(self.part,'D',lambda x:x.update(required_gates=['G4']));self.rejects()
    def test_empty_script_blocks(self):modify(self.part,'E1',lambda x:x.update(script=''));self.rejects()
    def test_runtime_blocker_keeps_design_but_no_bind(self):
        self.part['execution_blockers']=['Actual provider not configured'];plan=self.plan()
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError,'execution blockers'):p.bind_task(plan,'T1',{},Path(d))
    def test_plan_cannot_claim_actual_media_pass(self):x=self.plan();x['media_approved']=True;self.assertTrue(p.plan_errors(x))


class NewViewBindingTests(unittest.TestCase):
    def setUp(self):
        request, part = fixture()
        self.plan = p.assemble([part], request)
        task = deepcopy(self.plan['records']['T1'])
        task.update(task_id='T-ROOM-B', kind='asset_image', shot_id='ROOM-B', produces=['ROOM-B'])
        task['request_template'].update(kind='asset_image', shot_id='ROOM-B', mode='new_view', inputs=[])
        asset = deepcopy(self.plan['records']['A1'])
        asset.update(asset_id='ROOM-B', producer_task_id='T-ROOM-B')
        self.plan['records'].update(ROOM=asset, ROOM_TASK=task)
        self.plan['manifest'].extend([
            {'id':'ROOM','kind':'asset','episode_id':'EP1'},
            {'id':'ROOM_TASK','kind':'task','episode_id':'EP1'}])

    def test_new_view_cannot_bind_as_unstructured_text_only_asset(self):
        self.assertTrue(any('new_view' in e for e in p.plan_errors(self.plan)))
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, 'new_view'):
                p.bind_task(self.plan, 'T-ROOM-B', {'schema_version':'accepted-asset-registry-1','assets':[]}, Path(directory))

    def test_identity_reference_is_not_a_scene_source(self):
        task = self.plan['records']['ROOM_TASK']
        task['request_template']['inputs'] = deepcopy(self.plan['records']['T1']['request_template']['inputs'])
        task['execution_template'] = {'scene':{}, 'shot':{'mode':'new_view'}, 'runtime_profile':{}}
        task['request_template']['configuration_sha256'] = 'COMPUTE_FROM_EXECUTION_TEMPLATE'
        self.assertTrue(any('new_view' in e for e in p.plan_errors(self.plan)))

    def structured_view(self):
        visual = p.ROOT / 'tools/visual-continuity-prompter'
        if str(visual / 'scripts') not in sys.path:
            sys.path.insert(0, str(visual / 'scripts'))
        import continuity_tools as compiler
        scene = json.loads((visual / 'examples/scene.json').read_text())
        shot = json.loads((visual / 'examples/shot.json').read_text())
        profile = json.loads((visual / 'templates/runtime-profile.json').read_text())
        source = scene['views'][0]
        source.update(asset_id='REF', path={'$asset':'REF','field':'path'},
                      sha256={'$asset':'REF','field':'sha256'})
        target = deepcopy(source)
        target.update(view_id='VIEW-B', asset_id='ROOM-B', path=None, sha256=None,
                      status='candidate', description='Synthetic camera on the east side, looking west at the same room.')
        scene['views'].append(target)
        scene['unknown_geometry'] = []
        reference = deepcopy(shot['references'][0])
        reference.update(asset_id='REF', path={'$asset':'REF','field':'path'},
                         sha256={'$asset':'REF','field':'sha256'})
        shot.update(shot_id='ROOM-B', mode='new_view', source_view_id=source['view_id'],
                    view_id='VIEW-B', references=[reference], protection={'method':'none'},
                    change_request='Create the registered synthetic VIEW-B empty room candidate.')
        shot['output'].update(width=8, height=6)
        prompt = compiler.render_prompt(scene, shot, profile)
        request = b.request_snapshot(scene, shot, profile, prompt)
        request['configuration_sha256'] = 'COMPUTE_FROM_EXECUTION_TEMPLATE'
        self.plan['records']['ROOM_TASK'].update(request_template=request,
            execution_template={'scene':scene, 'shot':shot, 'runtime_profile':profile})
        return scene

    def test_shared_scene_view_binds_without_generating_media(self):
        self.structured_view()
        self.assertEqual(p.plan_errors(self.plan), [])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry, _ = media_registry(root)
            bound = p.bind_task(self.plan, 'T-ROOM-B', registry, root)
            self.assertFalse(bound['ready_for_submission'])
            self.assertEqual(bound['request']['inputs'][0]['asset_id'], 'REF')

    def test_changed_layout_cannot_keep_the_old_final_prompt(self):
        scene = self.structured_view()
        scene['invariants'][0]['description'] += ' Synthetic updated door position.'
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry, _ = media_registry(root)
            with self.assertRaisesRegex(ValueError, 'new_view'):
                p.bind_task(self.plan, 'T-ROOM-B', registry, root)


class Binding43Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);r,part=fixture();self.plan=p.assemble([part],r);self.reg,self.record=media_registry(self.root)
    def tearDown(self):self.tmp.cleanup()
    def bind(self):return p.bind_task(self.plan,'T1',self.reg,self.root)
    def test_file_only_bind_has_no_brain_media_claim(self):
        out=self.bind();self.assertEqual(out['request']['inputs'][0]['path'],'ref.bin');self.assertFalse(out['brain_media_review_performed']);self.assertFalse(out['ready_for_submission'])
    def test_missing_actual_file_blocks(self):(self.root/'ref.bin').unlink();self.assertRaises(ValueError,self.bind)
    def test_hash_changed_blocks(self):(self.root/'ref.bin').write_bytes(b'CHANGED');self.assertRaises(ValueError,self.bind)
    def test_candidate_blocks(self):
        r=b.read_json(self.root/'review.json');r['status']='CANDIDATE';(self.root/'review.json').write_text(json.dumps(r));self.reg['assets'][0]['review']=self.record('review.json');self.assertRaises(ValueError,self.bind)
    def test_old_brain_role_is_not_runtime_observation(self):
        r=b.read_json(self.root/'review.json');r['reviewer_role']='chatgpt_brain';(self.root/'review.json').write_text(json.dumps(r));self.reg['assets'][0]['review']=self.record('review.json');self.assertRaises(ValueError,self.bind)
    def test_no_evidence_blocks(self):
        r=b.read_json(self.root/'review.json');r['evidence']=[];(self.root/'review.json').write_text(json.dumps(r));self.reg['assets'][0]['review']=self.record('review.json');self.assertRaises(ValueError,self.bind)
    def test_unknown_registry_asset_blocks(self):self.reg['assets']=[];self.assertRaises(ValueError,self.bind)
    def test_path_escape_blocks(self):self.reg['assets'][0]['file']['path']='../ref.bin';self.assertRaises(ValueError,self.bind)
    def test_symlink_blocks(self):
        (self.root/'alias').symlink_to(self.root/'ref.bin');self.reg['assets'][0]['file']['path']='alias';self.assertRaises(ValueError,self.bind)
    def test_prompt_not_rewritten_by_binding(self):self.assertEqual(self.bind()['request']['prompt'],self.plan['records']['T1']['request_template']['prompt'])
    def test_unapproved_arbitrary_slot_field(self):self.plan['records']['T1']['request_template']['inputs'][0]['file']['field']='prompt';self.assertRaises(ValueError,self.bind)
    def test_unknown_task_blocks(self):self.assertRaises(ValueError,p.bind_task,self.plan,'UNKNOWN',self.reg,self.root)


class Transport43Tests(unittest.TestCase):
    def setUp(self):self.req,self.part=fixture()
    def response(self,part=None):return {'id':'SYNTHETIC','status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':json.dumps(part or self.part)}]}]}
    def test_no_default_model(self):self.assertRaises(ValueError,tr.payload_for,p.prepare(self.req),'',100)
    def test_text_only_payload(self):x=tr.payload_for(p.prepare(self.req),'EXPLICIT_TEST_MODEL',100);self.assertEqual(x['tools'],[]);self.assertFalse(x['store']);self.assertEqual(x['text']['format']['type'],'json_object')
    def test_incomplete_api_response_blocks(self):r=self.response();r['status']='incomplete';self.assertRaises(ValueError,tr.extract_part,r)
    def test_refusal_blocks(self):r=self.response();r['output'][0]['content']=[{'type':'refusal','refusal':'test'}];self.assertRaises(ValueError,tr.extract_part,r)
    def test_extract_preserves_full_json(self):self.assertEqual(tr.extract_part(self.response()),self.part)
    def test_collect_single_call(self):
        with tempfile.TemporaryDirectory() as d:
            x=tr.collect(self.req,model='TEST',max_calls=1,max_output_tokens=100,state_dir=Path(d),authorized=True,sender=lambda payload:self.response());self.assertEqual(x['status'],'PLAN_COMPLETE')
    def test_collect_auto_continues_without_user_message(self):
        a=deepcopy(self.part);a['status']='PARTIAL';a['records']=a['records'][:3];c=deepcopy(self.part);c['part_index']=2;c['records']=c['records'][3:];calls=[]
        def send(payload):calls.append(payload);return self.response(a if len(calls)==1 else c)
        with tempfile.TemporaryDirectory() as d:
            x=tr.collect(self.req,model='TEST',max_calls=2,max_output_tokens=100,state_dir=Path(d),authorized=True,sender=send)
        self.assertEqual(x['status'],'PLAN_COMPLETE');self.assertEqual(len(calls),2);self.assertIn('missing_records',calls[1]['input'])
    def test_call_cap_no_infinite_loop(self):
        a=deepcopy(self.part);a['status']='PARTIAL';a['records']=a['records'][:1]
        with tempfile.TemporaryDirectory() as d:
            self.assertRaises(ValueError,tr.collect,self.req,model='TEST',max_calls=1,max_output_tokens=100,state_dir=Path(d),authorized=True,sender=lambda payload:self.response(a))
    def test_no_permission_no_sender_call(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertRaises(ValueError,tr.collect,self.req,model='TEST',max_calls=1,max_output_tokens=100,state_dir=Path(d),authorized=False,sender=lambda payload:self.fail('network should not be called'))
    def test_no_legacy_opt_in_no_sender_call(self):
        self.req.pop('legacy_brain_compatibility')
        with tempfile.TemporaryDirectory() as d:
            self.assertRaisesRegex(ValueError,'explicit legacy',tr.collect,self.req,model='TEST',max_calls=1,max_output_tokens=100,state_dir=Path(d),authorized=True,sender=lambda payload:self.fail('network should not be called'))
    def test_timeout_claim_prevents_resend(self):
        with tempfile.TemporaryDirectory() as d,patch.dict('os.environ',{'OPENAI_API_KEY':'SYNTHETIC_NOT_A_KEY'}):
            def fail(*args,**kwargs):raise TimeoutError()
            self.assertRaises(RuntimeError,tr.post_once,{'test':1},Path(d),authorized=True,opener=fail)
            self.assertRaises(ValueError,tr.post_once,{'test':1},Path(d),authorized=True,opener=lambda *a,**k:self.fail('duplicate request'))

if __name__=='__main__':unittest.main()
