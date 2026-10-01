"""Actual synthetic pixel tests; not representative generative video success."""
from pathlib import Path
import json
import tempfile
import unittest
import zipfile
from PIL import Image
import numpy as np
import text_composite as t
import media_validation as m
from brain_exchange import file_record


class Media42Tests(unittest.TestCase):
    def setUp(self):self.base=Image.new('RGBA',(20,20),(255,255,255,255));self.texture=Image.new('RGBA',(5,5),(0,0,0,255));self.mask=Image.new('L',(20,20),0)
    def test_planar_overlay_applies_to_target_quad(self):
        out=t.planar_overlay(self.base,self.texture,[[5,5],[10,5],[10,10],[5,10]],self.mask,surface_model='plane')
        self.assertEqual(out.getpixel((7,7)),(0,0,0,255));self.assertEqual(out.getpixel((1,1)),(255,255,255,255))
    def test_occluding_hand_mask_preserves_underlying_base(self):
        self.mask.paste(255,(0,0,20,20));out=t.planar_overlay(self.base,self.texture,[[5,5],[10,5],[10,10],[5,10]],self.mask,surface_model='plane')
        self.assertEqual(out.tobytes(),self.base.tobytes())
    def test_curved_surface_rejected_not_faked_planar(self):
        with self.assertRaises(ValueError):t.planar_overlay(self.base,self.texture,[[5,5],[10,5],[10,10],[5,10]],self.mask,surface_model='curved')
    def test_crossed_quad_rejected(self):
        with self.assertRaises(ValueError):t.planar_overlay(self.base,self.texture,[[5,5],[10,10],[10,5],[5,10]],self.mask,surface_model='plane')
    def test_missing_occlusion_plan_rejected(self):
        with self.assertRaises(ValueError):t.planar_overlay(self.base,self.texture,[[5,5],[10,5],[10,10],[5,10]],None,surface_model='plane')
    def test_pen_detached_from_ink_rejected(self):
        with self.assertRaises(ValueError):t.stroke_reveal(self.texture,[(0,0),(4,0)],(4,4),width_px=1,tip_tolerance_px=0.1)
    def test_nan_pen_tip_cannot_fake_contact(self):
        with self.assertRaises(ValueError):t.stroke_reveal(self.texture,[(0,0)],(float('nan'),0),width_px=1,tip_tolerance_px=1)
    def test_nonfinite_tolerance_cannot_disable_contact_check(self):
        with self.assertRaises(ValueError):t.stroke_reveal(self.texture,[(0,0)],(4,4),width_px=1,tip_tolerance_px=float('inf'))
    def test_incomplete_glyph_cannot_pop_in_as_finished(self):
        with self.assertRaises(ValueError):t.stroke_reveal(self.texture,[(0,0),(4,0)],(4,0),width_px=1,tip_tolerance_px=0,complete=True)
    def test_stroke_history_is_monotonic(self):
        first,mask=t.stroke_reveal(self.texture,[(0,0),(4,0)],(4,0),width_px=1,tip_tolerance_px=0)
        second,_=t.stroke_reveal(self.texture,[(0,1),(4,1)],(4,1),width_px=1,tip_tolerance_px=0,previous_mask=mask)
        self.assertTrue((np.asarray(second.getchannel('A'))>=np.asarray(first.getchannel('A'))).all())
    def test_blind_capsule_has_no_script_filename(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);self.base.save(root/'spoiler-character-wins.png');rec=file_record(root,'spoiler-character-wins.png');rec['media_kind']='image'
            out=m.blind_capsule([rec],'Describe only what you actually see.',root,root/'blind.zip')
            self.assertFalse(out['reviewer_memory_isolation_verified'])
            with zipfile.ZipFile(root/'blind.zip') as z:self.assertFalse(any('wins' in n for n in z.namelist()))
    def test_blind_capsule_rejects_target_answers(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'answers.md').write_text('target answers');rec=file_record(root,'answers.md');rec['media_kind']='document'
            with self.assertRaises(ValueError):m.blind_capsule([rec],'Review',root,root/'blind.zip')
    def test_picture_probe_reports_dimensions_not_quality(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'p.png';self.base.save(path);r=m.probe_media(path,'image');self.assertEqual(r['width'],20);self.assertFalse(r['semantic_quality_verified'])


if __name__=='__main__':unittest.main()
