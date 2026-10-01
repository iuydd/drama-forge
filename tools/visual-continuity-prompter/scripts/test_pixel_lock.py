"""Small synthetic pixel fixtures; not AI image/video quality tests."""
from __future__ import annotations
import copy
import tempfile
import unittest
from pathlib import Path
try:
    from PIL import Image
    import pixel_lock as p
except (ImportError, SystemExit):
    Image = None


@unittest.skipIf(Image is None, 'Pillow not available')
class PixelTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.r=Path(self.tmp.name)
        self.base=self.r/'base.png';self.candidate=self.r/'candidate.png';self.mask=self.r/'mask.png';self.out=self.r/'out.png'
        Image.new('RGB',(8,6),(30,70,110)).save(self.base)
        Image.new('RGB',(8,6),(200,180,160)).save(self.candidate)
        m=Image.new('L',(8,6),0)
        for y in range(2,4):
            for x in range(2,5):m.putpixel((x,y),255)
        m.save(self.mask)
    def tearDown(self):self.tmp.cleanup()
    def run_compose(self,**kw):return p.compose(self.base,self.candidate,self.mask,self.out,**kw)
    def test_patch_preserves_protected_rgba(self):
        s=self.run_compose();self.assertEqual(s['changed_protected_pixels'],0);self.assertEqual(s['protected_pixels'],42)
        with Image.open(self.out) as im:self.assertEqual(im.getpixel((3,2)),(200,180,160,255))
    def test_raw_candidate_drift_detected(self):
        s=p.compare(self.base,self.candidate,self.mask);self.assertEqual(s['changed_protected_pixels'],42)
    def test_canvas_mismatch_rejected(self):
        Image.new('RGB',(7,6)).save(self.candidate)
        with self.assertRaises(ValueError):self.run_compose()
    def test_mask_size_mismatch_rejected(self):
        Image.new('L',(3,4)).save(self.mask)
        with self.assertRaises(ValueError):self.run_compose()
    def test_allwhite_mask_rejected(self):
        Image.new('L',(8,6),255).save(self.mask)
        with self.assertRaises(ValueError):self.run_compose()
    def test_allblack_mask_returns_base(self):
        Image.new('L',(8,6),0).save(self.mask)
        s=self.run_compose();self.assertEqual(s['protected_pixels'],48);self.assertTrue(s['protected_rgba_identical'])
    def test_nonbinary_allowed_rejected(self):
        Image.new('L',(8,6),128).save(self.mask)
        with self.assertRaises(ValueError):self.run_compose()
    def test_rgb_mask_rejected(self):
        Image.new('RGB',(8,6)).save(self.mask)
        with self.assertRaises(ValueError):self.run_compose()
    def test_feather_outside_allowed_rejected(self):
        b=self.r/'blend.png';Image.new('L',(8,6),128).save(b)
        with self.assertRaises(ValueError):self.run_compose(blend_path=b)
    def test_feather_inside_preserves_background(self):
        b=self.r/'blend.png'
        with Image.open(self.mask) as m:m.point(lambda v:128 if v else 0).save(b)
        self.assertTrue(self.run_compose(blend_path=b)['protected_rgba_identical'])
    def test_input_overwrite_rejected(self):
        with self.assertRaises(ValueError):p.compose(self.base,self.candidate,self.mask,self.base)
    def test_jpeg_output_rejected(self):
        with self.assertRaises(ValueError):p.compose(self.base,self.candidate,self.mask,self.r/'out.jpg')
    def test_transparent_patch_rejected(self):
        Image.new('RGBA',(8,6),(220,10,10,0)).save(self.candidate)
        with self.assertRaises(ValueError):self.run_compose()
    def test_rgba_overlay_preserves_background(self):
        Image.new('RGBA',(8,6),(220,10,10,128)).save(self.candidate)
        self.assertTrue(self.run_compose(mode='overlay')['protected_rgba_identical'])
    def test_alpha_difference_is_detected(self):
        Image.new('RGBA',(8,6),(30,70,110,100)).save(self.candidate)
        self.assertFalse(p.compare(self.base,self.candidate,self.mask)['protected_rgba_identical'])
    def test_exif_rotation_rejected(self):
        im=Image.new('RGB',(8,6)); ex=im.getexif();ex[274]=6;im.save(self.candidate,exif=ex)
        with self.assertRaises(ValueError):self.run_compose()
    def test_different_color_profiles_rejected(self):
        Image.new('RGB',(8,6)).save(self.base,icc_profile=b'profile-a')
        Image.new('RGB',(8,6)).save(self.candidate,icc_profile=b'profile-b')
        with self.assertRaises(ValueError):self.run_compose()
    def test_gate_checks_real_pixels_despite_pass_report(self):
        import continuity_tools as t
        root=Path(__file__).resolve().parents[1]
        scene=t.load_json(root/'examples/scene.json');shot=t.load_json(root/'examples/shot.json');profile=t.load_json(root/'templates/runtime-profile.json')
        def rec(path):return {'path':path.name,'sha256':t.digest_file(path)}
        # This fixture uses actual synthetic PNGs to exercise the gate's pixel check.
        scene['status']='accepted';scene['views'][0].update(rec(self.base),status='accepted')
        shot.update(planning_status='locked',camera_locked=True,output={'width':8,'height':6,'media_kind':'image'})
        shot['references']=shot['references'][:1];shot['references'][0].update(rec(self.base),status='accepted')
        shot['protection']['allowed_mask']=rec(self.mask)
        profile.update(backend='synthetic',model_id='synthetic',runtime_verified=True,max_reference_images=1,prompt_rewrite_policy='disabled_verified',verification_evidence=rec(self.base),parameter_map={k:k for k in ('prompt','images','width','height')})
        profile['features']={k:'verified' for k in profile['features']}
        report={'schema_version':'1.0','shot_id':shot['shot_id'],'stage':'image','contract_sha256':t.digest_job(scene,shot,profile),'artifact':rec(self.candidate),'reviewer':{'kind':'vision_model','id':'synthetic','version':'1'},'coverage':{'kind':'image','basis':'full_image'},'checks':[{'id':k,'result':'PASS','observation':'Synthetic gate claim for testing only.','evidence':[rec(self.base)]} for k in shot['qa_required']],'findings':[]}
        self.assertEqual(t.quality_gate(scene,shot,profile,report,self.r)['status'],'REJECTED')
        self.run_compose();report['artifact']=rec(self.out)
        self.assertEqual(t.quality_gate(scene,shot,profile,report,self.r)['status'],'ACCEPTED')


if __name__=='__main__':unittest.main()
