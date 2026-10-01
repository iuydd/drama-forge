"""Integrated reading routes and isolated legacy/independent roles; no API calls."""
from pathlib import Path
import hashlib
import importlib.util
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('role_reading_433',ROOT/'scripts/role_reading.py')
r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
sys.path.insert(0,str(ROOT/'tools/production-ops/scripts'))
import preproduction

class RoleRoutesTests(unittest.TestCase):
    def copied(self):
        t=tempfile.TemporaryDirectory();self.addCleanup(t.cleanup)
        p=Path(t.name)
        for d in ['config','references','prompts','schemas','assets']:
            shutil.copytree(ROOT/d,p/d)
        return p
    def mutate(self,p,fn):
        f=p/'config/role-reading-map.json';d=json.loads(f.read_text());fn(d)
        f.write_text(json.dumps(d,ensure_ascii=False))
    def test_all_routes_and_document_hashes_validate(self):
        self.assertEqual(r.check(ROOT)['status'],'READING_MAP_OK')
    def test_default_integrated_agent_reads_startup(self):
        a=r.build(ROOT);self.assertEqual(a['actor'],'integrated');self.assertEqual(a['stage'],'startup')
        self.assertEqual(a['workflow_mode'],'upfront_self')
        self.assertEqual([d['id'] for d in a['documents']],['00','10','11'])
        self.assertFalse(a['ready_for_submission'])
    def test_all_creation_tasks_read_current_rules_for_local_design(self):
        for stage in ['story_original','story_adapt','story_review','board','asset_design','new_prompt','sound_design','edit_design','qa_repair_plan']:
            with self.subTest(stage=stage):
                a=r.build(ROOT,stage);self.assertEqual(a['status'],'READING_READY')
                self.assertEqual(a['mode'],'design');self.assertTrue(a['documents'])
                self.assertNotIn('delegate_to',a);self.assertFalse(a['executed_generation'])
    def test_prompt_stages_allow_current_local_authorship(self):
        for stage in ['prompt_image','prompt_video']:
            self.assertEqual(r.build(ROOT,stage)['mode'],'design')
    def test_upfront_reads_all_ten_current_chapters(self):
        a=r.build(ROOT,'upfront')
        self.assertEqual([d['id'] for d in a['documents']],[f'{i:02}' for i in range(10)])
        self.assertNotIn('brain_payload',[d['id'] for d in a['documents']])
    def test_only_preapproved_repairs(self):
        self.assertEqual(r.build(ROOT,'repair')['mode'],'approved_branch_only')
    def test_recipient_brain_payload_not_local_instructions(self):
        a=r.build(ROOT,'request_brain')
        self.assertNotIn('brain_payload',[d['id'] for d in a['documents']])
        self.assertIn('brain_payload',[d['id'] for d in a['send_only']])
        self.assertNotIn('## 01｜先写成一场戏',a['instruction'])
        self.assertNotIn('content',a['send_only'][0])
    def test_wrong_role_cannot_run_production(self):
        with self.assertRaisesRegex(ValueError,'requires actor'):
            r.build(ROOT,'video','brain')
    def test_unknown_stage_does_not_fallback_to_full_theory(self):
        with self.assertRaisesRegex(ValueError,'not assigned'):
            r.build(ROOT,'make_up_new_story_here')
    def test_main_agent_cannot_impersonate_blind_reviewer(self):
        with self.assertRaisesRegex(ValueError,'requires actor'):
            r.build(ROOT,'blind')
    def test_blind_instruction_exact_no_other_role_rules(self):
        a=r.build(ROOT,'blind','blind_reviewer')
        self.assertEqual(a['instruction'],(ROOT/'references/blind-review.md').read_text())
        self.assertEqual([d['id'] for d in a['documents']],['blind'])
        self.assertEqual(a['send_only'],[])
    def test_each_generated_document_contains_exact_original(self):
        a=r.build(ROOT,'startup')
        for d in a['documents']:
            self.assertEqual(d['content'].encode(),(ROOT/d['path']).read_bytes())
    def test_active_references_match_current_map_identities(self):
        config=r.load_map(ROOT)
        for key in [f'{i:02}' for i in range(12)]+['blind']:
            row=config['documents'][key]
            with self.subTest(path=row['path']):
                self.assertEqual(hashlib.sha256((ROOT/row['path']).read_bytes()).hexdigest(),row['sha256'])
    def test_changed_read_document_is_blocked(self):
        p=self.copied();(p/'references/00-contract.md').write_text('changed')
        with self.assertRaisesRegex(ValueError,'hash/size mismatch'):r.build(p)
    def test_missing_selected_file_is_blocked(self):
        p=self.copied();(p/'references/10-execution.md').unlink()
        with self.assertRaises(OSError):r.build(p)
    def test_changed_brain_transmission_payload_is_blocked(self):
        p=self.copied();(p/'assets/brain-skill.md').write_text('abridged')
        with self.assertRaisesRegex(ValueError,'hash/size mismatch'):r.build(p,'request_brain')
    def test_path_traversal_is_blocked(self):
        p=self.copied();self.mutate(p,lambda c:c['documents']['00'].update(path='../outside.md'))
        with self.assertRaisesRegex(ValueError,'unsafe'):r.build(p)
    def test_symlink_reference_is_blocked(self):
        p=self.copied();f=p/'references/00-contract.md';raw=f.read_bytes();f.unlink()
        (p/'outside.md').write_bytes(raw);f.symlink_to(p/'outside.md')
        with self.assertRaisesRegex(ValueError,'symlink'):r.build(p)
    def test_brain_cannot_be_inserted_into_agent_read_scope(self):
        p=self.copied();self.mutate(p,lambda c:c['routes']['request_brain']['read'].append('brain_payload'))
        with self.assertRaisesRegex(ValueError,'recipient-only'):r.load_map(p)
    def test_blind_route_rejects_answer_context(self):
        p=self.copied();self.mutate(p,lambda c:c['routes']['blind']['read'].append('01'))
        with self.assertRaisesRegex(ValueError,'only independent blind brief'):r.load_map(p)
    def test_creation_route_cannot_impersonate_another_role(self):
        p=self.copied();self.mutate(p,lambda c:c['routes']['board'].update(actor='brain'))
        with self.assertRaisesRegex(ValueError,'ownership'):r.load_map(p)
    def test_integrated_creation_cannot_silently_delegate(self):
        p=self.copied();self.mutate(p,lambda c:c['routes']['board'].update(mode='delegate'))
        with self.assertRaisesRegex(ValueError,'ownership'):r.load_map(p)
    def test_duplicate_config_keys_rejected(self):
        p=self.copied();(p/'config/role-reading-map.json').write_text('{"schema_version":"a","schema_version":"b"}')
        with self.assertRaisesRegex(ValueError,'duplicate map key'):r.load_map(p)
    def test_actual_prepare_keeps_original_and_recipient_roles(self):
        req={'project_id':'SYNTHETIC','request_id':'R433','user_brief':'保持旧版创作要求，只分职责。','episode_ids':['EP001','EP002'],'source_texts':[],'existing_assets':[],'media_profiles':{},'quality_limits':{},'legacy_brain_compatibility':True}
        a=preproduction.prepare(req)
        self.assertIn('接收者是Brain，只执行前期设计',a['instructions'])
        self.assertIn('爽、新颖、情感和可理解性共同成立。',a['instructions'])
        self.assertIn('接收者角色固定为Brain',a['input'])
        self.assertIn(json.dumps(req,ensure_ascii=False,indent=2),a['input'])
        self.assertIn((ROOT/'assets/legacy-theory-3.1.2-public.md').read_text(),a['instructions'])
        self.assertFalse(a['production_started']);self.assertEqual(a['tools'],[])
    def test_entry_guide_and_machine_map_are_reachable(self):
        text=(ROOT/'SKILL.md').read_text()
        self.assertIn('references/agent-reading-guide.md',text)
        guide=(ROOT/'references/agent-reading-guide.md').read_text()
        self.assertIn('config/role-reading-map.json',guide)
        self.assertEqual(r.load_map(ROOT)['package_role'],'integrated')
    def test_chapter_map_points_to_current_entry_and_explicit_compatibility(self):
        text=(ROOT/'references/reading-routes.md').read_text()
        self.assertIn('兼容用途',text);self.assertIn('agent-reading-guide.md',text)
    def test_cli_fails_wrong_actor_without_action(self):
        p=subprocess.run([sys.executable,str(ROOT/'scripts/role_reading.py'),'--stage','video','--actor','brain'],capture_output=True,text=True)
        self.assertEqual(p.returncode,2);d=json.loads(p.stdout)
        self.assertEqual(d['status'],'BLOCKED');self.assertFalse(d['executed_generation'])
    def test_cli_designs_locally_without_network(self):
        p=subprocess.run([sys.executable,str(ROOT/'scripts/role_reading.py'),'--stage','board'],capture_output=True,text=True)
        self.assertEqual(p.returncode,0);self.assertEqual(json.loads(p.stdout)['status'],'READING_READY')
        self.assertEqual(json.loads(p.stdout)['mode'],'design')

if __name__=='__main__':unittest.main()
