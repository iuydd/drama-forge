from __future__ import annotations
import math
from pathlib import Path
import shutil
import struct
import tempfile
import unittest
import wave
from job_ledger import file_digest
import media_tools as m

@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'real FFmpeg required')
class RealFFmpegSmokeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        for i,c in enumerate((60,180)):
            (self.root/f'frame{i}.ppm').write_bytes(b'P6\n16 16\n255\n'+bytes([c,c,c])*256)
        with wave.open(str(self.root/'temporary-tone.wav'),'wb') as f:
            f.setnchannels(2);f.setsampwidth(2);f.setframerate(48000)
            f.writeframes(b''.join(struct.pack('<hh',*(int(3000*math.sin(2*math.pi*440*n/48000)),)*2)
                                  for n in range(96000)))
        def ref(n):return {'path':n,'sha256':file_digest(self.root/n)}
        self.manifest={'schema_version':'animatic-1','fps':24,'width':64,'height':64,
                       'shots':[{'shot_id':'TEST-S1','frames':24,'image':ref('frame0.ppm')},
                                {'shot_id':'TEST-S2','frames':24,'image':ref('frame1.ppm')}],
                       'temp_audio':ref('temporary-tone.wav')}
    def tearDown(self):self.tmp.cleanup()
    def test_real_animatic_two_seconds_48_frames(self):
        r=m.animatic(self.manifest,self.root,'previs/v1.mp4')
        self.assertEqual(r['status'],'ANIMATIC_RENDERED_NOT_REVIEWED')
        self.assertEqual(r['frames'],48);self.assertFalse(r['comprehension_reviewed'])
        self.assertAlmostEqual(r['actual_duration_s'],2,delta=.1)
    def test_real_asr_work_copy_not_master(self):
        src=self.root/'temporary-tone.wav';old=file_digest(src)
        r=m.extract_audio(src,self.root,'audio/work.wav');info=m.probe(self.root/'audio/work.wav')
        self.assertEqual(info['streams'][0]['sample_rate'],'16000')
        self.assertEqual(info['streams'][0]['channels'],1)
        self.assertEqual(file_digest(src),old);self.assertEqual(r['status'],'WORK_COPY_ONLY')
    def test_real_loudness_measurement(self):
        r=m.loudness(self.root/'temporary-tone.wav')
        self.assertTrue(math.isfinite(r['integrated_lufs']))
        self.assertEqual(r['status'],'MEASURED_NOT_LISTENING_APPROVAL')
    def test_silence_not_finite_pass(self):
        p=self.root/'silence.wav'
        with wave.open(str(p),'wb') as f:
            f.setnchannels(1);f.setsampwidth(2);f.setframerate(48000);f.writeframes(b'\0'*192000)
        with self.assertRaises(ValueError):m.loudness(p)
    def test_overlong_audio_not_silently_cut(self):
        self.manifest['shots'][0]['frames']=1
        with self.assertRaises(ValueError):m.animatic(self.manifest,self.root,'bad.mp4')
    def test_existing_output_preserved(self):
        p=self.root/'old.mp4';p.write_bytes(b'accepted-old')
        with self.assertRaises(FileExistsError):m.animatic(self.manifest,self.root,'old.mp4')
        self.assertEqual(p.read_bytes(),b'accepted-old')

if __name__=='__main__':unittest.main()
