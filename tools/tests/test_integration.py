"""Contract-only integration with synthetic small images, NOT a model generation run."""
import copy
import importlib.util
import json
import sys
import unittest
from pathlib import Path
SUITE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(SUITE/'reference-builder/scripts'))
import reference_tools as refs
import test_reference_tools as fixtures
spec=importlib.util.spec_from_file_location('suite_continuity',SUITE/'visual-continuity-prompter/scripts/continuity_tools.py')
continuity=importlib.util.module_from_spec(spec);spec.loader.exec_module(continuity)

class SuiteIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.ReferenceTests();self.f.setUp()
    def tearDown(self): self.f.tearDown()
    def build(self):
        selection=self.f.select()
        primary=selection['references'][0]
        scene={'schema_version':'1.0','scene_id':primary['scene_id'],'scene_version':primary['scene_version'],
               'status':'accepted','coordinate_system':'synthetic nonvisual fixture',
               'invariants':[{'id':'SYNTHETIC','description':'synthetic requirement, not observed scene geometry'}],
               'views':[{'view_id':primary['view_id'],'description':'synthetic view','asset_id':primary['asset_id'],
                         'state_id':primary['state_id'],'path':primary['path'],'sha256':primary['sha256'],'status':'accepted'}]}
        shot=json.loads((SUITE/'visual-continuity-prompter/examples/shot.json').read_text())
        shot.update(shot_id='SHOT-TEST',scene_id=primary['scene_id'],scene_version=primary['scene_version'],
                    scene_state_id=primary['state_id'],view_id=primary['view_id'],planning_status='locked',camera_locked=True,
                    output={'width':8,'height':6,'media_kind':'image'},references=selection['references'],
                    protection={'method':'none'})
        shot['qa_required']=[x for x in shot['qa_required'] if x!='protected_pixels']
        profile=json.loads((SUITE/'visual-continuity-prompter/templates/runtime-profile.json').read_text())
        profile.update(self.f.profile);profile.update(prompt_rewrite_policy='disabled_verified',dimension_multiple=1,
            parameter_map={'prompt':'prompt','images':'image','width':'width','height':'height'})
        return scene,shot,profile
    def test_reference_export_compiles_in_existing_tool(self):
        scene,shot,profile=self.build()
        packet=continuity.compile_package(scene,shot,profile,self.f.root,production=True)
        self.assertEqual(packet['status'],'READY',packet['blockers'])
        self.assertFalse(packet['executed']);self.assertFalse(packet['visual_quality_verified'])
    def test_reference_version_mismatch_blocked_by_existing_tool(self):
        scene,shot,profile=self.build();shot['references'][0]['scene_version']='different'
        self.assertEqual(continuity.compile_package(scene,shot,profile,self.f.root,production=True)['status'],'DRAFT')
    def test_missing_asset_blocks_new_selector(self):
        (self.f.root/self.f.scene['file']['path']).unlink()
        packet=self.f.select();self.assertEqual(packet['status'],'BLOCKED');self.assertEqual(packet['references'],[])
    def test_unverified_actual_runtime_does_not_become_ready(self):
        scene,shot,profile=self.build();profile['runtime_verified']=False
        self.assertEqual(continuity.compile_package(scene,shot,profile,self.f.root,production=True)['status'],'DRAFT')

if __name__=='__main__': unittest.main()
