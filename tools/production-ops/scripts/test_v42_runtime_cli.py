"""Actual CLI/media/transport smoke tests; all local fixtures are synthetic."""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
import wave
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
import text_composite as t
import media_validation as m
import brain_exchange as e
import brain_handoff as b
from fixtures_v42 import seed_return,keys,signed
ROOT=Path(__file__).resolve().parents[3]
CLI=ROOT/'scripts/runtime.py'


def synthetic_font(path):
    fb=FontBuilder(1000,isTTF=True);fb.setupGlyphOrder(['.notdef','A'])
    glyphs={}
    for name in ['.notdef','A']:
        pen=TTGlyphPen(None)
        if name=='A':
            pen.moveTo((100,0));pen.lineTo((300,700));pen.lineTo((500,0));pen.closePath()
        glyphs[name]=pen.glyph()
    fb.setupCharacterMap({65:'A'});fb.setupGlyf(glyphs);fb.setupHorizontalMetrics({g:(600,0) for g in glyphs})
    fb.setupHorizontalHeader(ascent=800,descent=-200);fb.setupNameTable({'familyName':'SyntheticOnly','styleName':'Regular','uniqueFontIdentifier':'test','fullName':'SyntheticOnly','psName':'SyntheticOnly'})
    fb.setupOS2(sTypoAscender=800,sTypoDescender=-200,usWinAscent=800,usWinDescent=200)
    fb.setupPost();fb.setupMaxp();fb.save(path)

class Texture42Tests(unittest.TestCase):
    def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.font=self.root/'synthetic.ttf';synthetic_font(self.font)
    def tearDown(self):self.tmp.cleanup()
    def test_actual_font_render_and_hash(self):
        im,r=t.make_texture('A',self.font,20,(64,32));self.assertTrue(im.getbbox());self.assertEqual(r['exact_text'],'A');self.assertEqual(r['font_sha256'],hashlib.sha256(self.font.read_bytes()).hexdigest())
    def test_missing_glyph_rejected_instead_of_tofu(self):
        with self.assertRaises(ValueError):t.make_texture('B',self.font,20,(64,32))
    def test_canvas_too_small_never_silently_shrinks(self):
        with self.assertRaises(ValueError):t.make_texture('AAAA',self.font,20,(2,2))

class CLI42Tests(unittest.TestCase):
    def run_cli(self,*args):
        proc=subprocess.run([sys.executable,str(CLI),*map(str,args)],capture_output=True,text=True,timeout=30)
        return proc,json.loads(proc.stdout)
    def test_doctor_does_not_claim_connected_service(self):
        proc,r=self.run_cli('doctor');self.assertEqual(proc.returncode,0);self.assertFalse(r['live_deployment']['verified_real_generation'])
    def test_bad_return_reports_blocked_json(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'bad.json').write_text('{}')
            proc,r=self.run_cli('validate-return','--file',root/'bad.json','--root',root)
            self.assertEqual(proc.returncode,2);self.assertEqual(r['status'],'BLOCKED')
    def test_corrupt_capsule_returns_blocked_not_traceback(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'bad.zip').write_bytes(b'not a zip')
            proc,r=self.run_cli('unpack-return','--capsule',root/'bad.zip','--root',root)
            self.assertEqual(proc.returncode,2);self.assertEqual(r['status'],'BLOCKED');self.assertNotIn('Traceback',proc.stderr)
    def test_actual_capsule_cli_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);ret,_=seed_return(root);(root/'return-input.json').write_text(json.dumps(ret));dest=root/'destination';dest.mkdir()
            proc,_=self.run_cli('pack-return','--file',root/'return-input.json','--root',root,'--out',root/'cap.zip');self.assertEqual(proc.returncode,0,proc.stderr)
            proc,r=self.run_cli('unpack-return','--capsule',root/'cap.zip','--root',dest);self.assertEqual(proc.returncode,0,proc.stderr);self.assertFalse(r['accepted'])
            self.assertEqual((dest/'image.png').read_bytes(),(root/'image.png').read_bytes())

@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'actual local video smoke needs ffmpeg/ffprobe')
class LocalMedia42Tests(unittest.TestCase):
    def test_real_local_video_audio_return_and_signed_acceptance(self):
        # Procedural test pattern, NOT model generation or actual user footage.
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);ret,packet=seed_return(root)
            with wave.open(str(root/'sound.wav'),'wb') as wav:
                wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(8000);wav.writeframes(b'\0\0'*8000)
            subprocess.run(['ffmpeg','-v','error','-loop','1','-i',str(root/'image.png'),'-i',str(root/'sound.wav'),'-t','1','-r','8','-pix_fmt','yuv420p','-c:v','libx264','-c:a','aac',str(root/'clip.mp4')],check=True,capture_output=True,timeout=30)
            r=m.probe_media(root/'clip.mp4','video');self.assertEqual(len(r['streams']),2);self.assertFalse(r['semantic_quality_verified'])
            request=ret['actual_requests'][0]['request'];request['kind']='video';packet['phase']='video';packet['tasks'][0].update(request=request,request_sha256=b.digest(request))
            (root/'packet.json').write_text(json.dumps(packet));ret.update(phase='video',base_packet=e.file_record(root,'packet.json'))
            ret['actual_requests'][0].update(request=request,request_sha256=b.digest(request));ret['outputs'][0].update(file=e.file_record(root,'clip.mp4'),media_kind='video')
            self.assertEqual(e.validate_return(ret,root),[])
            raw,trusted=keys();db=e.WorkflowStore(root/'state.sqlite')
            try:
                db.register_packet(packet,ret['base_packet'],signed(raw,'creative',scope={'packet':ret['base_packet'],'packet_id':'P','episode_id':'EP001'}),trusted)
                self.assertEqual(db.ingest(ret,root)['status'],'PENDING_BRAIN_REVIEW')
                (root/'review.json').write_text('{"scope":"SYNTHETIC codec/transport fixture only","real_visual_review":false}')
                accepted=[{'asset_id':'A','sha256':ret['outputs'][0]['file']['sha256']}]
                result=db.apply_decision(signed(raw,'creative',operation='accept_return_outputs',scope={'return_id':'R','return_sha256':b.digest(ret),'accepted':accepted},reviewed_subjects=accepted,review_evidence=[e.file_record(root,'review.json')]),trusted)
                self.assertEqual(result['status'],'ACCEPTED_BY_SIGNED_DECISION')
            finally:db.close()

if __name__=='__main__':unittest.main()
