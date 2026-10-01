"""Contract/gate tests use synthetic local records, not generated model imagery."""
from __future__ import annotations
import copy
import json
import tempfile
import unittest
from pathlib import Path
import continuity_tools as t

ROOT = Path(__file__).resolve().parents[1]


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.scene = t.load_json(ROOT/'examples/scene.json')
        self.shot = t.load_json(ROOT/'examples/shot.json')
        self.profile = t.load_json(ROOT/'templates/runtime-profile.json')
        self.scene['status'] = 'accepted'
        self.shot.update(planning_status='locked', camera_locked=True, protection={'method':'none'})
        self.shot['qa_required'] = sorted(t.IMAGE_CHECKS)
        self.profile.update(backend='synthetic-test-backend', model_id='synthetic-not-a-real-model',
                            runtime_verified=True, max_reference_images=10,
                            prompt_rewrite_policy='disabled_verified',
                            parameter_map={k:'fixture.'+k for k in ('prompt','images','width','height')})
        self.profile['features'] = {k:'verified' for k in self.profile['features']}
        self.profile['verification_evidence'] = self.record('probe.json', b'{"synthetic":true}')
        for i, r in enumerate(self.shot['references']):
            r.update(self.record(f'ref{i}.bin', f'synthetic-reference-{i}'.encode()), status='accepted')
        self.scene['views'][0].update(path=self.shot['references'][0]['path'],
                                     sha256=self.shot['references'][0]['sha256'], status='accepted')
        artifact = self.record('output.bin', b'synthetic-contract-test-not-an-image')
        evidence = self.record('inspection.txt', b'synthetic reviewer record; no real image was examined')
        self.report = {'schema_version':'1.0', 'shot_id':self.shot['shot_id'],
            'contract_sha256':t.digest_job(self.scene,self.shot,self.profile), 'stage':'image',
            'artifact':artifact, 'reviewer':{'kind':'vision_model','id':'synthetic-checker','version':'test'},
            'coverage':{'kind':'image','basis':'full_image'},
            'checks':[{'id':k,'result':'PASS','observation':'Synthetic contract fixture, not a visual finding.',
                       'evidence':[copy.deepcopy(evidence)]} for k in self.shot['qa_required']], 'findings':[]}

    def tearDown(self):
        self.temp.cleanup()

    def record(self,name,data):
        path=self.root/name; path.parent.mkdir(parents=True,exist_ok=True); path.write_bytes(data)
        return {'path':name,'sha256':t.digest_file(path)}

    def errors(self):
        return t.validate(self.scene,self.shot,self.profile,self.root,True)

    def gate(self, refresh=False):
        if refresh:
            self.report['contract_sha256']=t.digest_job(self.scene,self.shot,self.profile)
        return t.quality_gate(self.scene,self.shot,self.profile,self.report,self.root)

    def attach_ensemble_review(self):
        bundle=t.load_json(ROOT/'examples/ensemble-demo.json')
        for key in ('shot_id','scene_id','scene_version','view_id'):
            bundle['scope'][key]=self.shot[key]
        self.shot['ensemble']=bundle
        observation={'shot_id':self.shot['shot_id'],
            'ensemble_sha256':t._ensemble.digest(bundle),
            'media_sha256':self.report['artifact']['sha256'],
            'windows':[{'window_id':window['window_id'],'full_frame_result':'PASS',
                'unexpected_visible_entities':[],
                'entities':{eid:{'result':'PASS','observation':'Synthetic full-frame state check, not actual footage.'}
                    for eid in bundle['start_state']['entities']}}
                for window in bundle['view_plan']['windows']]}
        self.report['ensemble_review']={'shots':[observation]}
        return observation

    def test_ensemble_gate_requires_full_cast_observation(self):
        self.attach_ensemble_review()
        self.report.pop('ensemble_review')
        self.assertEqual(self.gate(True)['status'],'BLOCKED')

    def test_ensemble_gate_accepts_current_complete_observation(self):
        self.attach_ensemble_review()
        self.assertEqual(self.gate(True)['status'],'ACCEPTED')

    def test_local_repair_cannot_ignore_missing_person_or_changed_prop(self):
        observation=self.attach_ensemble_review()
        for eid in ('CHAR_B','PROP_CUP','DOOR'):
            with self.subTest(entity=eid):
                observation['windows'][0]['entities'][eid]['result']='FAIL'
                self.assertEqual(self.gate(True)['status'],'REJECTED')
                observation['windows'][0]['entities'][eid]['result']='PASS'

    def test_local_repair_cannot_reuse_old_media_observation(self):
        self.attach_ensemble_review()
        self.report['artifact']=self.record('repaired.bin',b'synthetic repaired output, not media')
        self.assertEqual(self.gate(True)['status'],'BLOCKED')

    def test_ensemble_gate_missing_entity_is_not_a_full_frame_pass(self):
        observation=self.attach_ensemble_review()
        del observation['windows'][0]['entities']['CHAR_B']
        self.assertEqual(self.gate(True)['status'],'BLOCKED')

    def test_video_ensemble_review_covers_later_windows_and_time(self):
        self.shot.update(mode='video_i2v',video={'duration_s':4,'fps':24,
            'action_beats':[{'start_s':0,'end_s':4,'action':'保持人物与物件原状态。'}],
            'end_state_description':'保持原有站位与持物。'})
        self.shot['output']['media_kind']='video'
        self.shot['qa_required']=sorted(t.VIDEO_CHECKS)
        evidence=self.report['checks'][0]['evidence']
        self.report.update(stage='video',
            coverage={'kind':'video','basis':'full_frames','total_frames':96,
                'frame_ranges':[[0,95]],'temporal_reviewed':True},
            checks=[{'id':cid,'result':'PASS','observation':'Synthetic full-interval check.',
                'evidence':copy.deepcopy(evidence)} for cid in self.shot['qa_required']])
        observation=self.attach_ensemble_review()
        bundle=self.shot['ensemble']
        bundle['events']=[]
        bundle['end_state']['entities']=copy.deepcopy(bundle['start_state']['entities'])
        first=bundle['view_plan']['windows'][0]
        first['end_s']=2
        second=copy.deepcopy(first)
        second.update(window_id='W02',start_s=2,end_s=4)
        bundle['view_plan']['windows'].append(second)
        observation['ensemble_sha256']=t._ensemble.digest(bundle)
        observation['temporal_basis']='Synthetic observation covers both full windows.'
        self.assertEqual(self.gate(True)['status'],'BLOCKED')
        second_review=copy.deepcopy(observation['windows'][0])
        second_review['window_id']='W02'
        observation['windows'].append(second_review)
        self.assertEqual(self.gate(True)['status'],'ACCEPTED')
        observation.pop('temporal_basis')
        self.assertEqual(self.gate(True)['status'],'BLOCKED')

    def test_valid_production_contract(self): self.assertEqual(self.errors(),[])
    def test_example_is_structurally_valid(self):
        s=t.load_json(ROOT/'examples/scene.json'); j=t.load_json(ROOT/'examples/shot.json')
        self.assertEqual(t.validate(s,j,self.profile),[])
    def test_missing_example_assets_block_production(self):
        s=t.load_json(ROOT/'examples/scene.json'); j=t.load_json(ROOT/'examples/shot.json')
        self.assertTrue(t.validate(s,j,self.profile,self.root,True))
    def test_dry_run_never_ready(self):
        r=t.compile_package(self.scene,self.shot,self.profile,self.root)
        self.assertEqual(r['status'],'DRAFT'); self.assertFalse(r['executed'])
    def test_ready_means_inputs_only(self):
        r=t.compile_package(self.scene,self.shot,self.profile,self.root,True)
        self.assertEqual(r['status'],'READY'); self.assertFalse(r['visual_quality_verified'])
    def test_prompt_maps_reference_roles(self):
        p=t.render_prompt(self.scene,self.shot)
        self.assertIn('图片1',p); self.assertIn('图片2',p); self.assertIn('不镜像',p)
    def test_scene_version_mismatch(self):
        self.shot['scene_version']='other'; self.assertTrue(self.errors())
    def test_duplicate_view_ids(self):
        self.scene['views'].append(copy.deepcopy(self.scene['views'][0])); self.assertTrue(self.errors())
    def test_missing_view(self):
        self.shot['view_id']='UNKNOWN'; self.assertTrue(self.errors())
    def test_bad_output_size_and_bool(self):
        for x in (0,-1,True,None):
            with self.subTest(x=x):
                self.shot['output']['width']=x; self.assertTrue(self.errors())
    def test_qa_cannot_be_removed(self):
        self.shot['qa_required']=[]; self.assertTrue(self.errors())
    def test_unlocked_storyboard(self):
        self.shot['camera_locked']=False; self.assertTrue(self.errors())
    def test_unverified_runtime(self):
        self.profile['runtime_verified']=False; self.assertTrue(self.errors())
    def test_missing_runtime_probe(self):
        self.profile['verification_evidence']=None; self.assertTrue(self.errors())
    def test_duplicate_upload_indices(self):
        self.shot['references'][1]['upload_index']=1; self.assertTrue(self.errors())
    def test_multiple_primary_images(self):
        self.shot['references'][1]['primary']=True; self.assertTrue(self.errors())
    def test_non_base_primary_rejected(self):
        self.shot['references'][0]['role']='identity'; self.assertTrue(self.errors())
    def test_missing_actual_reference(self):
        (self.root/'ref0.bin').unlink(); self.assertTrue(self.errors())
    def test_modified_reference_hash(self):
        (self.root/'ref1.bin').write_bytes(b'changed'); self.assertTrue(self.errors())
    def test_path_escape_rejected(self):
        self.shot['references'][1]['path']='../outside'; self.assertTrue(self.errors())
    def test_absolute_path_rejected(self):
        self.shot['references'][1]['path']=str(self.root/'ref1.bin'); self.assertTrue(self.errors())
    def test_symlink_escape_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            outside=Path(d)/'secret'; outside.write_text('secret')
            (self.root/'link').symlink_to(outside)
            with self.assertRaises(ValueError): t.resolve_in_root(self.root,'link')
    def test_reference_limit_rejected(self):
        self.profile['max_reference_images']=1; self.assertTrue(self.errors())
    def test_reference_capability_not_assumed(self):
        self.profile['features']['multi_reference']='unknown'; self.assertTrue(self.errors())
    def test_primary_master_lineage_mismatch(self):
        self.shot['references'][0]['asset_id']='wrong-master'; self.assertTrue(self.errors())
    def test_primary_state_mismatch(self):
        self.shot['references'][0]['state_id']='other-state'; self.assertTrue(self.errors())
    def test_start_frame_requires_master_hash(self):
        self.shot['references'][0]['role']='start_frame'; self.assertTrue(self.errors())
        self.shot['references'][0]['scene_anchor_sha256']=self.scene['views'][0]['sha256']
        self.assertEqual(self.errors(),[])
    def test_unknown_rewrite_blocked(self):
        self.profile['prompt_rewrite_policy']='unknown'; self.assertTrue(self.errors())
    def test_audited_rewrite_valid_and_stale(self):
        p=t.render_prompt(self.scene,self.shot)
        self.profile['prompt_rewrite_policy']='audited'
        self.shot['rewrite_audit']={'passed':True,'source_prompt_sha256':t.digest_text(p),
          'final_prompt':p,'final_prompt_sha256':t.digest_text(p),'evidence':self.record('audit.txt',b'synthetic audit')}
        self.assertEqual(self.errors(),[])
        self.shot['change_request']+='changed'; self.assertTrue(self.errors())

    def test_final_rewrite_reuses_existing_contradiction_check(self):
        original = t.render_prompt(self.scene, self.shot)
        self.profile['prompt_rewrite_policy'] = 'audited'
        for addition, expected in (
                ('Keep the cup fixed; simultaneously move the same cup to the right.', 'DRAFT'),
                ('Keep the cup still, then lift it and place it to the right.', 'READY'),
                ('Keep the cup fixed for the first two seconds. Then open the box and simultaneously move the same cup to the right.', 'READY'),
                ('Keep the cup fixed initially, then open the box and simultaneously move the same cup to the right.', 'READY')):
            with self.subTest(addition=addition):
                final = original + '\n' + addition
                self.shot['rewrite_audit'] = {
                    'passed': True, 'source_prompt_sha256': t.digest_text(original),
                    'final_prompt': final, 'final_prompt_sha256': t.digest_text(final),
                    'evidence': self.record('audit.txt', b'synthetic audit')}
                result = t.compile_package(self.scene, self.shot, self.profile, self.root, True)
                self.assertEqual(result['status'], expected)
                if expected == 'DRAFT':
                    self.assertIn('prompt: simultaneous fixed/move contradiction', result['blockers'])
                    self.assertNotEqual(result['prompt'], final)

    def test_bound_speech_is_not_a_visual_motion_instruction(self):
        from fixtures_v42 import intent
        spoken = 'He gave contradictory orders: keep the cup fixed and simultaneously move the same cup to the right. I refused.'
        visual = 'Keep the cup fixed; simultaneously move the same cup to the right.'
        for speech_format in ('native', 'literal', 'colon'):
            with self.subTest(speech_format=speech_format):
                if speech_format == 'native':
                    shot = t.load_json(ROOT/'examples/video-shot.json')
                    line = {'line_id': 'L1', 'speaker_description': '青衣青年',
                            'voice_description': '平稳男声', 'text_spoken': spoken}
                    shot['audio_plan'] = {'native_spoken_lines': [line], 'post_voices': []}
                    profile = {}
                else:
                    ir, backend = intent()
                    backend['speech_format'] = speech_format
                    clause = {'id': 'line', 'kind': 'speech', 'speaker': '青衣青年',
                              'text': '青衣青年说：' + spoken, 'text_spoken': spoken, 'required': True}
                    ir['clauses'].append(clause)
                    ir['priority']['hard'].append('line')
                    shot = {'mode': 'video_i2v', 'policy_version': '4.2.0', 'prompt_ir': ir,
                            'references': [{'asset_id': 'REF'}],
                            'locked_prompt': t._prompt_contract.compile_ir(ir, backend)['prompt']}
                    profile = {'prompt_backend': backend}
                prompt = t.render_prompt(self.scene, shot, profile)
                self.assertIn(spoken, prompt)
                self.assertEqual(t.inspect_final_prompt(shot, prompt, profile), [])
                # Audited final text uses the same guard; only the exact bound speech is exempt.
                self.assertTrue(t.inspect_final_prompt(shot, prompt + '\n' + visual, profile))
                if speech_format == 'native':
                    line['delivery_note'] = visual
                else:
                    clause['delivery'] = visual
                    with self.assertRaisesRegex(ValueError, 'fixed/move contradiction'):
                        t._prompt_contract.compile_ir(ir, backend)
                    clause.pop('delivery')
                    clause['text'] = spoken + '\n' + spoken
                    with self.assertRaisesRegex(ValueError, 'fixed/move contradiction'):
                        t._prompt_contract.compile_ir(ir, backend)
                    continue
                with self.assertRaisesRegex(ValueError, 'fixed/move contradiction'):
                    t.render_prompt(self.scene, shot, profile)

    def test_repeated_final_speech_fragment_is_not_guessed(self):
        from fixtures_v42 import intent
        spoken = 'Keep the cup fixed; simultaneously move the same cup to the right.'
        for speech_format in ('native', 'literal', 'colon'):
            with self.subTest(speech_format=speech_format):
                if speech_format == 'native':
                    shot = t.load_json(ROOT/'examples/video-shot.json')
                    line = {'line_id': 'L1', 'speaker_description': '青衣青年',
                            'voice_description': '平稳男声', 'text_spoken': spoken}
                    shot['audio_plan'] = {'native_spoken_lines': [line], 'post_voices': []}
                    profile = {}
                    fragment = t._prompt_nine.render_native_line(line)
                else:
                    ir, backend = intent()
                    backend['speech_format'] = speech_format
                    ir['clauses'].append({'id': 'line', 'kind': 'speech', 'speaker': '青衣青年',
                                          'text': spoken, 'text_spoken': spoken, 'required': True})
                    ir['priority']['hard'].append('line')
                    shot = {'mode': 'video_i2v', 'policy_version': '4.2.0', 'prompt_ir': ir,
                            'references': [{'asset_id': 'REF'}],
                            'locked_prompt': t._prompt_contract.compile_ir(ir, backend)['prompt']}
                    profile = {'prompt_backend': backend}
                    fragment = spoken if speech_format == 'literal' else '青衣青年 says: ' + spoken
                prompt = t.render_prompt(self.scene, shot, profile)
                self.assertEqual(t.inspect_final_prompt(shot, prompt, profile), [])
                ambiguous = prompt + '\nVisual action, not speech: ' + fragment
                self.assertIn('prompt: simultaneous fixed/move contradiction',
                              t.inspect_final_prompt(shot, ambiguous, profile))
    def test_dimension_alignment(self):
        self.profile['dimension_multiple']=32; self.shot['output']['width']=1537
        self.assertTrue(self.errors())
    def test_mask_missing_blocks(self):
        self.shot['protection']={'method':'external_composite','allowed_mask':None}
        self.assertTrue(self.errors())
    def new_view(self):
        self.shot.update(mode='new_view',view_id='VIEW-B',source_view_id='VIEW-A')
        self.scene['views'].append({'view_id':'VIEW-B','description':'从东墙朝西，北墙门投影在画面右侧。',
            'asset_id':'MASTER-B-1','state_id':'STATE-000','status':'candidate','path':None,'sha256':None})
    def test_new_view_requires_existing_source(self):
        self.new_view()
        self.assertEqual(self.errors(),[])
        self.shot['source_view_id']='VIEW-MISSING'; self.assertTrue(self.errors())
    def test_new_view_requires_source_master_not_a_derived_frame(self):
        self.new_view()
        source=copy.deepcopy(self.shot['references'][0])
        self.assertEqual(self.errors(),[])
        for role in ('start_frame','previous_end'):
            with self.subTest(role=role):
                self.shot['references'][0]={**source,**self.record(role+'.bin',b'synthetic derived frame'),
                    'asset_id':'DERIVED-FRAME','role':role,'scene_anchor_sha256':source['sha256']}
                self.assertTrue(t.validate(self.scene,self.shot,self.profile,self.root,False))
                self.assertEqual(t.compile_package(self.scene,self.shot,self.profile,self.root,True)['status'],'DRAFT')
    def test_video_i2v_still_accepts_verified_derived_frames(self):
        self.shot.update(mode='video_i2v',video={'duration_s':4,'fps':24,
            'action_beats':[{'start_s':0,'end_s':4,'action':'人物自然呼吸。'}],'end_state_description':'保持原位。'})
        self.shot['output']['media_kind']='video';self.shot['qa_required']=sorted(t.VIDEO_CHECKS)
        source=copy.deepcopy(self.shot['references'][0])
        for role in ('start_frame','previous_end'):
            with self.subTest(role=role):
                self.shot['references'][0]={**source,**self.record(role+'.bin',b'synthetic derived frame'),
                    'asset_id':'DERIVED-FRAME','role':role,'scene_anchor_sha256':source['sha256']}
                self.assertEqual(self.errors(),[])
                self.assertEqual(t.compile_package(self.scene,self.shot,self.profile,self.root,True)['status'],'READY')
    def test_new_view_style_preserves_design_and_allows_target_view(self):
        self.new_view()
        self.shot['style_lock']={'style_id':'STYLE','version':'1','status':'locked',
            'prompt_sentence':'EXACT_LOCKED_STYLE_SENTENCE'}
        prompt=t.render_prompt(self.scene,self.shot,self.profile)
        self.assertIn('EXACT_LOCKED_STYLE_SENTENCE',prompt)
        self.assertIn('共同场景设计',prompt)
        self.assertIn('仅采用已声明的目标机位',prompt)
        self.assertNotIn('不授权重绘场景或改变机位',prompt)
        self.shot['mode']='edit_same_view'
        self.assertIn('不授权重绘场景或改变机位',t.render_prompt(self.scene,self.shot,self.profile))
    def test_new_view_requires_registered_target_design(self):
        self.new_view()
        self.shot['view_id']='VIEW-UNKNOWN'
        self.assertTrue(self.errors())
        self.assertEqual(t.compile_package(self.scene,self.shot,self.profile,self.root,True)['status'],'DRAFT')
        self.shot['view_id']='VIEW-B';self.scene['views'][-1]['description']=''
        self.assertTrue(self.errors())
    def test_new_view_transmits_geometry_and_tracks_layout_changes(self):
        self.new_view()
        self.scene['unknown_geometry']=['HIDDEN_WORLD_NOT_MODEL_INPUT']
        original=t.render_prompt(self.scene,self.shot,self.profile)
        descriptions=[self.scene['coordinate_system']]+[row['description'] for row in self.scene['invariants']]
        descriptions += [row['description'] for row in self.scene['views']]
        for description in descriptions:self.assertIn(description,original)
        self.assertNotIn('HIDDEN_WORLD_NOT_MODEL_INPUT',original)
        for owner,key in [(self.scene,'coordinate_system'),(self.scene['invariants'][0],'description'),
                          (self.scene['views'][0],'description'),(self.scene['views'][1],'description')]:
            with self.subTest(field=key,original=owner[key]):
                saved=owner[key];owner[key]='CHANGED_GEOMETRY_'+saved
                changed=t.render_prompt(self.scene,self.shot,self.profile)
                self.assertNotEqual(original,changed);self.assertIn(owner[key],changed)
                owner[key]=saved
    def test_new_view_locked_prompt_cannot_omit_or_stale_geometry(self):
        self.new_view()
        original=t.render_prompt(self.scene,self.shot,self.profile)
        self.shot['locked_prompt']=original
        self.assertEqual(t.render_prompt(self.scene,self.shot,self.profile),original)
        self.shot['locked_prompt']='Generate the same room from the other side.'
        self.assertTrue(self.errors())
        self.assertEqual(self.shot['locked_prompt'],'Generate the same room from the other side.')
        self.shot['locked_prompt']=original
        self.scene['invariants'][0]['description']='北墙门改到东墙。'
        self.assertTrue(self.errors())
    def test_new_view_audited_rewrite_cannot_drop_geometry(self):
        self.new_view()
        original=t.render_prompt(self.scene,self.shot,self.profile)
        self.profile['prompt_rewrite_policy']='audited'
        self.shot['rewrite_audit']={'passed':True,'source_prompt_sha256':t.digest_text(original),
            'final_prompt':original,'final_prompt_sha256':t.digest_text(original),
            'evidence':self.record('new-view-audit.txt',b'synthetic audit; no real image reviewed')}
        self.assertEqual(self.errors(),[])
        rewritten='Generate the same room from the other side.'
        self.shot['rewrite_audit'].update(final_prompt=rewritten,final_prompt_sha256=t.digest_text(rewritten))
        self.assertTrue(self.errors())
        self.assertEqual(t.compile_package(self.scene,self.shot,self.profile,self.root,True)['status'],'DRAFT')
    def test_new_view_nine_remains_video_only(self):
        self.new_view()
        self.shot['prompt9']=t.load_json(ROOT/'examples/video-shot-nine.json')['prompt9']
        self.assertTrue(self.errors())
        with self.assertRaisesRegex(ValueError,'applies to video only'):
            t.render_prompt(self.scene,self.shot,self.profile)
    def test_gate_passes_complete_synthetic_report(self):
        r=self.gate(); self.assertEqual(r['status'],'ACCEPTED'); self.assertFalse(r['guarantees_zero_visual_errors'])
    def test_unknown_schema_versions_block(self):
        self.report['schema_version']='99'; self.assertEqual(self.gate()['status'],'BLOCKED')
        self.profile['schema_version']='99'; self.assertTrue(self.errors())
    def test_minor_findings_block_by_default(self):
        self.report['findings']=[{'severity':'minor','resolved':False,'description':'Noncritical residual issue.'}]
        self.assertEqual(self.gate()['status'],'REJECTED')
    def test_explicit_minor_waiver_is_disclosed(self):
        self.shot['quality_policy']={'allow_minor_findings':True}
        self.report['findings']=[{'severity':'minor','resolved':False,'description':'Noncritical residual issue.'}]
        r=self.gate(refresh=True); self.assertEqual(r['status'],'ACCEPTED'); self.assertTrue(r['warnings'])
    def test_gate_stale_contract(self):
        self.shot['change_request']+='new'; self.assertEqual(self.gate()['status'],'BLOCKED')
    def test_gate_modified_output(self):
        (self.root/'output.bin').write_bytes(b'modified'); self.assertEqual(self.gate()['status'],'BLOCKED')
    def test_gate_unknown_check(self):
        self.report['checks'][0]['result']='UNKNOWN'; self.assertEqual(self.gate()['status'],'BLOCKED')
    def test_gate_failed_check(self):
        self.report['checks'][0]['result']='FAIL'; self.assertEqual(self.gate()['status'],'REJECTED')
    def test_gate_missing_check(self):
        self.report['checks'].pop(); self.assertEqual(self.gate()['status'],'BLOCKED')
    def test_gate_duplicate_check(self):
        self.report['checks'].append(copy.deepcopy(self.report['checks'][0])); self.assertEqual(self.gate()['status'],'BLOCKED')
    def test_gate_evidence_missing(self):
        self.report['checks'][0]['evidence']=[]; self.assertEqual(self.gate()['status'],'BLOCKED')
    def test_gate_evidence_tampered(self):
        (self.root/'inspection.txt').write_text('changed'); self.assertEqual(self.gate()['status'],'BLOCKED')
    def test_gate_major_finding_overrides_pass(self):
        self.report['findings']=[{'severity':'major','resolved':False,'description':'Third hand found.'}]
        self.assertEqual(self.gate()['status'],'REJECTED')
    def test_gate_review_identity_required(self):
        self.report['reviewer']['kind']='prompt_compiler'; self.assertEqual(self.gate()['status'],'BLOCKED')
    def test_gate_stage_mismatch(self):
        self.report['stage']='video'; self.assertEqual(self.gate()['status'],'BLOCKED')
    def test_video_contract_and_gapped_beats(self):
        v=t.load_json(ROOT/'examples/video-shot.json')
        self.assertEqual(t.validate(self.scene,v,self.profile),[])
        v['video']['action_beats'][1]['start_s']=2.1
        self.assertTrue(t.validate(self.scene,v,self.profile))
    def test_video_nonfinite_duration_rejected(self):
        v=t.load_json(ROOT/'examples/video-shot.json'); v['video']['duration_s']=float('nan')
        self.assertTrue(t.validate(self.scene,v,self.profile))
    def test_video_sampled_coverage_rejected(self):
        self.assertTrue(t.check_coverage({'kind':'video','basis':'sampled','total_frames':96,'frame_ranges':[[0,0],[95,95]],'temporal_reviewed':True},'video'))
    def test_video_full_coverage_accepted(self):
        self.assertEqual(t.check_coverage({'kind':'video','basis':'full_frames','total_frames':96,'frame_ranges':[[0,47],[48,95]],'temporal_reviewed':True},'video'),[])
    def test_video_frame_gap_or_overlap_rejected(self):
        for ranges in ([[0,47],[49,95]],[[0,48],[48,95]],[[0,96]]):
            with self.subTest(ranges=ranges):
                self.assertTrue(t.check_coverage({'kind':'video','basis':'full_frames','total_frames':96,'frame_ranges':ranges,'temporal_reviewed':True},'video'))
    def test_json_duplicate_keys_rejected(self):
        p=self.root/'bad.json'; p.write_text('{"a":1,"a":2}')
        with self.assertRaises(ValueError):t.load_json(p)
    def test_json_nonfinite_rejected(self):
        p=self.root/'bad.json'; p.write_text('{"a":NaN}')
        with self.assertRaises(ValueError):t.load_json(p)
    def test_digest_key_order_stable(self):
        self.assertEqual(t.digest_value({'a':1,'b':2}),t.digest_value({'b':2,'a':1}))


class SchemaTests(unittest.TestCase):
    def test_bundled_examples_match_schema(self):
        try: import jsonschema
        except ImportError: self.skipTest('Optional jsonschema package not available')
        pairs=[('examples/scene.json','schemas/scene.schema.json'),
               ('examples/shot.json','schemas/shot.schema.json'),
               ('examples/video-shot.json','schemas/shot.schema.json'),
               ('templates/review-report.json','schemas/review.schema.json')]
        for f,s in pairs:
            with self.subTest(file=f):
                schema=t.load_json(ROOT/s)
                jsonschema.Draft202012Validator.check_schema(schema)
                jsonschema.validate(t.load_json(ROOT/f),schema)


if __name__=='__main__': unittest.main()
