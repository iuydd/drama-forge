"""Synthetic engineering tests. These are NOT generated character/scene evaluations."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from PIL import Image
import reference_tools as r
from image_assets import crop_image


class ReferenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root/'evidence.txt').write_text('SYNTHETIC TEST FIXTURE; not a real visual review', encoding='utf-8')
        self.ev = {'path':'evidence.txt','sha256':r.file_digest(self.root/'evidence.txt')}
        source = Path(__file__).resolve().parents[1]/'examples/reference-manifest.planned.json'
        m = r.load_json(source)
        self.m = {'schema_version':'1.0','project_id':'TEST','canon_version':'1','assets':[]}
        for i in (0,1,3,5):
            a=copy.deepcopy(m['assets'][i]);a['status']='accepted';a['spec']['width']=8;a['spec']['height']=6
            p=self.root/(a['asset_id']+'.png');Image.new('RGB',(8,6),(10,20,30)).save(p)
            a['file']={'path':p.name,'sha256':r.file_digest(p)};self.m['assets'].append(a)
        self.char=self.m['assets'][0];self.full=self.m['assets'][1]
        self.prop=self.m['assets'][2];self.scene=self.m['assets'][3]
        self.refresh_reviews()
        self.request={'target_shot_id':'SHOT-TEST','scene_context':copy.deepcopy(self.scene['scene_context']),
                      'output':{'width':8,'height':6},'bindings':[
            {'asset_id':self.scene['asset_id'],'role':'scene_base','primary':True,'purpose':'actual test base'},
            {'asset_id':self.full['asset_id'],'role':'identity','primary':False,'purpose':'identity only'},
            {'asset_id':self.prop['asset_id'],'role':'prop','primary':False,'purpose':'prop design only'}]}
        self.profile={'runtime_verified':True,'backend':'synthetic-test','model_id':'NOT-A-REAL-MODEL',
                      'verification_evidence':self.ev,'max_reference_images':3,
                      'features':{'image_edit':'verified','multi_reference':'verified','spatial_reference':'verified'}}
    def tearDown(self): self.tmp.cleanup()
    def refresh_reviews(self):
        idx=r.asset_index(self.m)
        for a in self.m['assets']:
            a['review']={'decision':'PASS','reviewer':'synthetic-test-fixture',
                'spec_sha256':r.spec_digest(self.m,a),'file_sha256':a['file']['sha256'],
                'dependency_snapshots':{d:{'file_sha256':idx[d]['file']['sha256'],'spec_sha256':r.spec_digest(self.m,idx[d])} for d in a['dependencies']},
                'checks':[{'name':k,'result':'PASS','observation':'Synthetic declared observation only','evidence':copy.deepcopy(self.ev)} for k in sorted(r.required_checks(a))],
                'open_issues':[]}
    def gate(self,a=None): return r.gate_assets(self.m,[(a or self.full)['asset_id']],self.root)
    def select(self): return r.select_references(self.m,self.request,self.profile,self.root)
    def test_valid_manifest(self): self.assertEqual(r.check_manifest(self.m),[])
    def test_valid_gate(self): self.assertEqual(self.gate(),[])
    def test_valid_selection(self):
        p=self.select();self.assertEqual(p['status'],'READY');self.assertEqual(len(p['references']),3)
        self.assertFalse(p['executed']);self.assertFalse(p['visual_quality_verified_by_this_tool'])
    def test_export_upload_order(self): self.assertEqual([x['upload_index'] for x in self.select()['references']],[1,2,3])
    def test_export_scene_metadata(self):
        a=self.select()['references'][0];self.assertEqual(a['view_id'],'VIEW-N');self.assertEqual(a['state_id'],'DAY')
    def test_dependency_order(self):
        order=r.order_assets(self.m);self.assertLess(order.index(self.char['asset_id']),order.index(self.full['asset_id']))
    def test_duplicate_id(self):
        self.m['assets'].append(copy.deepcopy(self.char));self.assertTrue(r.check_manifest(self.m))
    def test_missing_dependency(self):
        self.full['dependencies'].append('ABSENT');self.assertTrue(r.check_manifest(self.m))
    def test_self_dependency(self):
        self.char['dependencies']=[self.char['asset_id']];self.assertTrue(r.check_manifest(self.m))
    def test_cycle(self):
        self.char['dependencies']=[self.full['asset_id']];self.assertTrue(r.check_manifest(self.m))
    def test_wrong_parent(self):
        self.full['canonical_parent']='ABSENT';self.assertTrue(r.check_manifest(self.m))
    def test_nonstring_dependency(self):
        self.full['dependencies']=[{}];self.assertTrue(r.check_manifest(self.m))
    def test_incompatible_role(self):
        self.char['allowed_roles']=['scene_base'];self.assertTrue(r.check_manifest(self.m))
    def test_invalid_dimensions(self):
        self.char['spec']['width']=True;self.assertTrue(r.check_manifest(self.m))
    def test_unknown_critical(self):
        self.full['spec']['critical_unknowns']=['unseen critical face'];self.refresh_reviews();self.assertTrue(self.gate())
    def test_candidate_does_not_pass(self):
        self.full['status']='candidate';self.assertTrue(self.gate())
    def test_stale_parent_does_not_pass(self):
        self.char['status']='stale';self.assertTrue(self.gate())
    def test_contact_sheet_not_production(self):
        self.full['format']='contact_sheet';self.refresh_reviews();self.assertTrue(self.gate())
    def test_missing_file(self):
        (self.root/self.full['file']['path']).unlink();self.assertTrue(self.gate())
    def test_file_hash_change(self):
        (self.root/self.full['file']['path']).write_bytes(b'changed');self.assertTrue(self.gate())
    def test_non_image_file(self):
        self.full['file']=copy.deepcopy(self.ev);self.refresh_reviews();self.assertTrue(self.gate())
    def test_absolute_path_rejected(self):
        self.full['file']['path']=str(self.root/self.full['file']['path']);self.assertTrue(self.gate())
    def test_parent_escape_rejected(self):
        self.full['file']['path']='../outside.png';self.assertTrue(self.gate())
    def test_symlink_escape_rejected(self):
        with tempfile.TemporaryDirectory() as external:
            out=Path(external)/'x.png';Image.new('RGB',(8,6)).save(out)
            (self.root/'link.png').symlink_to(out)
            self.full['file']={'path':'link.png','sha256':r.file_digest(out)}
            self.refresh_reviews();self.assertTrue(self.gate())
    def test_wrong_decoded_dimensions(self):
        self.full['spec']['width']=9;self.refresh_reviews();self.assertTrue(self.gate())
    def test_stale_specification(self):
        self.full['spec']['immutable'].append('changed');self.assertTrue(self.gate())
    def test_stale_canon(self):
        self.m['canon_version']='2';self.assertTrue(self.gate())
    def test_stale_image_review(self):
        self.full['review']['file_sha256']='0'*64;self.assertTrue(self.gate())
    def test_stale_dependency_snapshot(self):
        self.full['review']['dependency_snapshots']={};self.assertTrue(self.gate())
    def test_parent_respec_invalidates_child(self):
        self.char['spec']['subject']='different';old=copy.deepcopy(self.full['review']);self.refresh_reviews();self.full['review']=old
        self.assertTrue(self.gate())
    def test_unknown_check_blocks(self):
        self.full['review']['checks'][0]['result']='UNKNOWN';self.assertTrue(self.gate())
    def test_fail_check_blocks(self):
        self.full['review']['checks'][0]['result']='FAIL';self.assertTrue(self.gate())
    def test_missing_use_test(self):
        self.full['review']['checks']=[x for x in self.full['review']['checks'] if x['name']!='use_test'];self.assertTrue(self.gate())
    def test_duplicate_check(self):
        self.full['review']['checks'].append(copy.deepcopy(self.full['review']['checks'][0]));self.assertTrue(self.gate())
    def test_empty_observation(self):
        self.full['review']['checks'][0]['observation']='';self.assertTrue(self.gate())
    def test_missing_evidence(self):
        self.full['review']['checks'][0]['evidence']={'path':None,'sha256':None};self.assertTrue(self.gate())
    def test_evidence_hash_stale(self):
        (self.root/'evidence.txt').write_text('modified evidence');self.assertTrue(self.gate())
    def test_open_issue_blocks(self):
        self.full['review']['open_issues']=['known extra finger'];self.assertTrue(self.gate())
    def test_runtime_unknown_blocks(self):
        self.profile['runtime_verified']=False;self.assertEqual(self.select()['status'],'BLOCKED')
    def test_runtime_feature_unknown_blocks(self):
        self.profile['features']['multi_reference']='unknown';self.assertEqual(self.select()['status'],'BLOCKED')
    def test_reference_limit_blocks(self):
        self.profile['max_reference_images']=2;self.assertEqual(self.select()['status'],'BLOCKED')
    def test_wrong_scene_view(self):
        self.request['scene_context']['view_id']='OTHER';self.assertEqual(self.select()['status'],'BLOCKED')
    def test_wrong_scene_state(self):
        self.request['scene_context']['state_id']='NIGHT';self.assertEqual(self.select()['status'],'BLOCKED')
    def test_wrong_canvas(self):
        self.request['output']['width']=10;self.assertEqual(self.select()['status'],'BLOCKED')
    def test_wrong_binding_order(self):
        self.request['bindings'].reverse();self.assertEqual(self.select()['status'],'BLOCKED')
    def test_duplicate_binding(self):
        self.request['bindings'].append(copy.deepcopy(self.request['bindings'][1]));self.assertEqual(self.select()['status'],'BLOCKED')
    def test_wrong_binding_role(self):
        self.request['bindings'][1]['role']='prop';self.assertEqual(self.select()['status'],'BLOCKED')
    def test_missing_binding_purpose(self):
        self.request['bindings'][1]['purpose']='';self.assertEqual(self.select()['status'],'BLOCKED')
    def test_unknown_binding_asset(self):
        self.request['bindings'][1]['asset_id']='ABSENT';p=self.select();self.assertEqual(p['status'],'BLOCKED');self.assertEqual(p['references'],[])
    def test_wrong_primary(self):
        self.request['bindings'][1]['primary']=True;self.assertEqual(self.select()['status'],'BLOCKED')
    def test_valid_real_alpha(self):
        p=self.root/self.prop['file']['path'];im=Image.new('RGBA',(8,6),(10,20,30,0));im.putpixel((2,2),(10,20,30,255));im.save(p)
        self.prop['file']['sha256']=r.file_digest(p);self.prop['spec']['requires_transparency']=True;self.refresh_reviews()
        self.assertEqual(self.gate(self.prop),[])
    def test_opaque_rgba_rejected(self):
        p=self.root/self.prop['file']['path'];Image.new('RGBA',(8,6),(10,20,30,255)).save(p)
        self.prop['file']['sha256']=r.file_digest(p);self.prop['spec']['requires_transparency']=True;self.refresh_reviews();self.assertTrue(self.gate(self.prop))
    def test_empty_alpha_rejected(self):
        p=self.root/self.prop['file']['path'];Image.new('RGBA',(8,6),(10,20,30,0)).save(p)
        self.prop['file']['sha256']=r.file_digest(p);self.prop['spec']['requires_transparency']=True;self.refresh_reviews();self.assertTrue(self.gate(self.prop))
    def test_crop_correct_pixels(self):
        p=self.root/self.prop['file']['path'];out=self.root/'crop.png';report=crop_image(p,[1,1,6,5],out)
        self.assertEqual(report['status'],'CANDIDATE');self.assertEqual(Image.open(out).size,(5,4))
    def test_crop_no_new_view_claim(self):
        p=self.root/self.prop['file']['path'];report=crop_image(p,[0,0,4,3],self.root/'crop.png');self.assertTrue(report['review_required'])
    def test_crop_outside_fails(self):
        with self.assertRaises(ValueError): crop_image(self.root/self.prop['file']['path'],[0,0,99,99],self.root/'crop.png')
    def test_crop_overwrite_source_fails(self):
        p=self.root/self.prop['file']['path']
        with self.assertRaises(ValueError): crop_image(p,[0,0,4,3],p,True)
    def test_crop_overwrite_candidate_requires_optin(self):
        p=self.root/self.prop['file']['path'];out=self.root/'crop.png';crop_image(p,[0,0,4,3],out)
        with self.assertRaises(FileExistsError): crop_image(p,[0,0,4,3],out)
    def test_duplicate_json_keys(self):
        p=self.root/'bad.json';p.write_text('{"a":1,"a":2}')
        with self.assertRaises(ValueError): r.load_json(p)
    def test_nan_json_rejected(self):
        p=self.root/'bad.json';p.write_text('{"a":NaN}')
        with self.assertRaises(ValueError): r.load_json(p)
    def test_top_array_rejected(self):
        p=self.root/'bad.json';p.write_text('[]')
        with self.assertRaises(ValueError): r.load_json(p)
    def test_planned_example_has_no_actual_paths(self):
        p=Path(__file__).resolve().parents[1]/'examples/reference-manifest.planned.json';m=r.load_json(p)
        self.assertEqual(r.check_manifest(m),[]);self.assertTrue(all(a['file']['path'] is None for a in m['assets']))
    def test_schema_templates(self):
        try: import jsonschema
        except ImportError: self.skipTest('optional jsonschema unavailable')
        root=Path(__file__).resolve().parents[1];schema=r.load_json(root/'schemas/reference-manifest.schema.json')
        for name in ('examples/reference-manifest.planned.json','templates/reference-manifest.json'):
            jsonschema.validate(r.load_json(root/name),schema)

class SceneLineageTests(unittest.TestCase):
    """Manifest relationships only; no images or declared visual approvals."""

    def setUp(self):
        self.m = {'schema_version': '1.0', 'project_id': 'TEST',
                  'canon_version': '1', 'assets': []}
        self.root = self.add_scene('ROOT', 'VIEW-N')

    def add_scene(self, asset_id, view_id, parent=None, *, scene_id='ROOM',
                  scene_version='1', state_id='DAY'):
        asset = {
            'asset_id': asset_id, 'entity_id': scene_id, 'kind': 'scene',
            'version': '1', 'view_id': view_id, 'state_id': state_id,
            'scene_context': {'scene_id': scene_id, 'scene_version': scene_version,
                              'view_id': view_id, 'state_id': state_id},
            'format': 'single', 'status': 'planned', 'canonical_parent': parent,
            'dependencies': [parent] if parent else [], 'allowed_roles': ['scene_base'],
            'spec': {'subject': 'The same room', 'view': view_id,
                     'width': 8, 'height': 6, 'requires_transparency': False,
                     'immutable': ['Door and window keep their world positions'],
                     'critical_unknowns': []},
            'file': {'path': None, 'sha256': None}, 'review': {},
        }
        self.m['assets'].append(asset)
        return asset

    def test_independent_views_cannot_claim_the_same_scene(self):
        other = self.add_scene('MASTER-B', 'VIEW-E')
        for dependencies in ([], ['ROOT']):
            with self.subTest(dependencies=dependencies):
                other['dependencies'] = dependencies
                self.assertTrue(r.check_manifest(self.m))

    def test_views_can_share_one_scene_root(self):
        self.add_scene('MASTER-A', 'VIEW-E', 'ROOT')
        self.add_scene('MASTER-B', 'VIEW-S', 'ROOT')
        self.assertEqual(r.check_manifest(self.m), [])

    def test_scene_parent_cannot_be_a_character_or_prop(self):
        self.add_scene('MASTER-A', 'VIEW-E', 'ROOT')
        for kind, role in (('character', 'identity'), ('prop', 'prop')):
            with self.subTest(kind=kind):
                self.root.update(kind=kind, allowed_roles=[role], scene_context=None)
                self.assertTrue(r.check_manifest(self.m))

    def test_scene_parent_must_match_scene_and_version(self):
        child = self.add_scene('MASTER-A', 'VIEW-E', 'ROOT')
        for scene_id, version in (('OTHER-ROOM', '1'), ('ROOM', '2')):
            with self.subTest(scene_id=scene_id, version=version):
                child['scene_context'].update(scene_id=scene_id, scene_version=version)
                self.assertTrue(r.check_manifest(self.m))

    def test_cross_view_chain_must_return_to_the_root(self):
        self.add_scene('MASTER-A', 'VIEW-E', 'ROOT')
        self.add_scene('MASTER-B', 'VIEW-S', 'MASTER-A')
        self.assertTrue(r.check_manifest(self.m))

    def test_same_view_state_and_local_revisions_remain_valid(self):
        self.add_scene('MASTER-A', 'VIEW-E', 'ROOT')
        self.add_scene('MASTER-A-NIGHT', 'VIEW-E', 'MASTER-A', state_id='NIGHT')
        revision = self.add_scene('MASTER-A-FIX', 'VIEW-E', 'MASTER-A-NIGHT', state_id='NIGHT')
        revision['version'] = '2'
        self.assertEqual(r.check_manifest(self.m), [])
        self.add_scene('MASTER-B', 'VIEW-S', 'MASTER-A-FIX', state_id='NIGHT')
        self.assertTrue(r.check_manifest(self.m))

    def test_shared_layout_parent_has_explicit_matching_scene_context(self):
        self.root.update(kind='layout', format='diagram', allowed_roles=['layout'])
        self.add_scene('MASTER-A', 'VIEW-E', 'ROOT')
        self.add_scene('MASTER-B', 'VIEW-S', 'ROOT')
        self.assertEqual(r.check_manifest(self.m), [])
        for context in (None, {}, {'scene_id': 'OTHER', 'scene_version': '1'},
                        {'scene_id': 'ROOM', 'scene_version': '2'}):
            with self.subTest(context=context):
                self.root['scene_context'] = context
                self.assertTrue(r.check_manifest(self.m))

    def test_separate_layouts_do_not_create_a_shared_root(self):
        self.root.update(kind='layout', format='diagram', allowed_roles=['layout'])
        layout_b = self.add_scene('LAYOUT-B', 'PLAN')
        layout_b.update(kind='layout', format='diagram', allowed_roles=['layout'])
        self.add_scene('MASTER-A', 'VIEW-E', 'ROOT')
        self.add_scene('MASTER-B', 'VIEW-S', 'LAYOUT-B')
        self.assertTrue(r.check_manifest(self.m))

    def test_different_scenes_and_scene_versions_keep_separate_roots(self):
        self.add_scene('ROOT-V2', 'VIEW-N', scene_version='2')
        self.add_scene('ROOT-OTHER', 'VIEW-N', scene_id='OTHER')
        self.add_scene('MASTER-V2', 'VIEW-E', 'ROOT-V2', scene_version='2')
        self.add_scene('MASTER-OTHER', 'VIEW-E', 'ROOT-OTHER', scene_id='OTHER')
        self.assertEqual(r.check_manifest(self.m), [])

    def test_non_scene_assets_keep_their_existing_parent_rules(self):
        for kind, role in (('character', 'identity'), ('prop', 'prop')):
            first = self.add_scene(kind + '-A', 'FRONT')
            second = self.add_scene(kind + '-B', 'SIDE', kind + '-A')
            third = self.add_scene(kind + '-C', 'BACK', kind + '-B')
            for asset in (first, second, third):
                asset.update(kind=kind, allowed_roles=[role], scene_context=None)
        self.assertEqual(r.check_manifest(self.m), [])

    def test_scene_dependency_cycle_is_still_rejected(self):
        self.add_scene('MASTER-A', 'VIEW-N', 'ROOT')
        self.root.update(canonical_parent='MASTER-A', dependencies=['MASTER-A'])
        self.assertTrue(any('cycle' in error.lower() for error in r.check_manifest(self.m)))


if __name__=='__main__': unittest.main()
