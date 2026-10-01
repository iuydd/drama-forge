from __future__ import annotations
from copy import deepcopy
from fractions import Fraction
import json
import math
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest
import wave
import edit_timeline as e


def fixture():
    color={'space':'bt709','primaries':'bt709','transfer':'bt709','range':'tv'}
    sources=[]
    for sid in ('S1','S2'):
        sources.append({'id':sid,'kind':'video','path':sid+'.mkv','sha256':'0'*64,
                        'review':{'path':sid+'-review.json','sha256':'0'*64},'units':48,
                        'fps':'24/1','width':64,'height':64,'pixel_format':'yuv420p','color':color.copy()})
    sources.append({'id':'SA','kind':'audio','path':'SA.wav','sha256':'0'*64,
                    'review':{'path':'SA-review.json','sha256':'0'*64},'units':96000,'sample_rate':48000,'channels':2})
    video=[{'id':'V1','shot_id':'SHOT1','source_id':'S1','src_in':6,'src_out':30,'dst_in':0,
            'role':'action','cut_reason':'Show the action before its reaction','transition':'cut','speed':'1/1','visible_dialogue':True},
           {'id':'V2','shot_id':'SHOT2','source_id':'S2','src_in':12,'src_out':36,'dst_in':24,
            'role':'reaction','cut_reason':'The listener reacts to the revealed fact','transition':'cut','speed':'1/1','visible_dialogue':False}]
    audio=[{'id':'A1','source_id':'SA','src_in':12000,'src_out':60000,'dst_in':12000,'role':'dialogue',
            'gain_db':0,'fade_in_samples':0,'fade_out_samples':0,'line_ids':['L1']},
           {'id':'A2','source_id':'SA','src_in':0,'src_out':24000,'dst_in':72000,'role':'dialogue',
            'gain_db':0,'fade_in_samples':0,'fade_out_samples':0,'line_ids':['L2']}]
    events=[{'event_id':'EV1','kind':'video','source_id':'S1','src_in':18,'src_out':24,'required':True,'allow_repeat':False},
            {'event_id':'EV2','kind':'video','source_id':'S2','src_in':18,'src_out':24,'required':True,'allow_repeat':False},
            {'event_id':'EL1','kind':'audio','source_id':'SA','src_in':30000,'src_out':48000,'required':True,'allow_repeat':False,'line_id':'L1'}]
    # A second source record is the same WAV content, with a distinct calibrated identity role.
    s=deepcopy(sources[-1]);s['id']='SB';s['path']='SB.wav';s['review']['path']='SB-review.json';sources.append(s)
    audio[1]['source_id']='SB'
    events.append({'event_id':'EL2','kind':'audio','source_id':'SB','src_in':0,'src_out':24000,'required':True,'allow_repeat':False,'line_id':'L2'})
    return {'schema_version':'edit-timeline-1','status':'LOCKED','episode_id':'EP-TEST','revision':'1',
            'fps':'24/1','sample_rate':48000,'channels':2,'width':64,'height':64,'pixel_format':'yuv420p',
            'color':color,'duration_frames':48,'audio_intent':'sound','sources':sources,
            'video':video,'audio':audio,'events':events,'event_orders':[{'before':'EV1','after':'EV2'}],
            'sync_links':[{'video_clip':'V1','audio_clip':'A1','source_frame':12,'source_sample':12000,'tolerance_samples':0}],
            'allowed_dialogue_overlaps':[],
            'render_policy':{'video_codec':'ffv1','audio_codec':'pcm_s24le','container':'mkv'},
            'note':'Synthetic test fixture only. No human speech, user footage or real approvals.'}


class TimelineStructureTests(unittest.TestCase):
    def setUp(self):self.t=fixture()
    def blocked(self):self.assertEqual(e.validate(self.t)['status'],'BLOCKED')
    def test_valid(self):self.assertEqual(e.validate(self.t)['status'],'STRUCTURE_OK')
    def test_structural_check_not_visual_acceptance(self):self.assertFalse(e.validate(self.t)['semantic_quality_verified'])
    def test_required_event_count(self):self.assertEqual(len(e.validate(self.t)['required_event_ids']),4)
    def test_cut_id(self):self.assertEqual(e.validate(self.t)['cut_ids'],['V1__V2'])
    def test_no_implicit_native_audio(self):self.t['audio']=[];self.blocked()
    def test_picture_gap(self):self.t['video'][1]['dst_in']=25;self.blocked()
    def test_picture_overlap(self):self.t['video'][1]['dst_in']=23;self.blocked()
    def test_source_out_of_bounds(self):self.t['video'][1]['src_out']=49;self.blocked()
    def test_float_frame_rejected(self):self.t['video'][0]['src_in']=6.0;self.blocked()
    def test_bool_frame_rejected(self):self.t['video'][0]['src_in']=True;self.blocked()
    def test_wrong_fps(self):self.t['sources'][0]['fps']='25/1';self.blocked()
    def test_wrong_color(self):self.t['sources'][0]['color']['transfer']='smpte2084';self.blocked()
    def test_no_implicit_resize(self):self.t['sources'][0]['width']=128;self.blocked()
    def test_no_silent_effect_drop(self):self.t['video'][0]['effects']=['zoom'];self.blocked()
    def test_no_unsupported_transition(self):self.t['video'][0]['transition']='dissolve';self.blocked()
    def test_no_retime(self):self.t['video'][0]['speed']='2/1';self.blocked()
    def test_unknown_top_field(self):self.t['subtitles']=['oops'];self.blocked()
    def test_missing_required_visual(self):self.t['events'][0]['src_in']=31;self.t['events'][0]['src_out']=35;self.blocked()
    def test_partial_visual_event(self):self.t['events'][0]['src_out']=31;self.blocked()
    def test_partial_dialogue(self):self.t['events'][2]['src_out']=60001;self.blocked()
    def test_line_label_not_audible_event(self):self.t['audio'][0]['line_ids']=['GHOST'];self.blocked()
    def test_wrong_order(self):self.t['event_orders'][0]={'before':'EV2','after':'EV1'};self.blocked()
    def test_unapproved_speech_overlap(self):self.t['audio'][1]['dst_in']=50000;self.blocked()
    def test_approved_speech_overlap(self):
        self.t['audio'][1]['dst_in']=50000
        self.t['allowed_dialogue_overlaps']=[{'clips':['A1','A2'],'reason':'Script explicitly permits interruption'}]
        self.assertEqual(e.validate(self.t)['status'],'STRUCTURE_OK')
    def test_audio_beyond_end(self):self.t['audio'][1]['dst_in']=80000;self.blocked()
    def test_gain_nonfinite(self):self.t['audio'][0]['gain_db']=float('nan');self.blocked()
    def test_fade_exceeds_range(self):self.t['audio'][0]['fade_in_samples']=50000;self.blocked()
    def test_sync_shift(self):self.t['audio'][0]['dst_in']+=100;self.blocked()
    def test_visible_speech_anchor_required(self):self.t['sync_links']=[];self.blocked()
    def test_anchor_outside_source(self):self.t['sync_links'][0]['source_sample']=0;self.blocked()
    def test_rational_sample_rounding(self):self.assertEqual(e.sample_at(30000,Fraction(30000,1001),48000),48048000)
    def test_half_open_range(self):self.assertTrue(e.ranges_cover([[0,10],[10,20]],5,20))
    def test_range_hole(self):self.assertFalse(e.ranges_cover([[0,9],[10,20]],5,20))
    def test_malformed_range(self):self.assertFalse(e.ranges_cover([[0,'20']],5,20))
    def test_repeat_event(self):
        self.t['video'][1].update(source_id='S1',src_in=6,src_out=30)
        self.t['events']=[self.t['events'][0]];self.t['event_orders']=[]
        self.t['audio'][0]['line_ids']=[];self.t['audio'][1]['line_ids']=[]
        self.blocked()
    def test_draft_not_production(self):
        self.t['status']='DRAFT'
        with tempfile.TemporaryDirectory() as td:
            self.assertIn('production timeline is not LOCKED',e.verify_sources(self.t,Path(td))['errors'])
    def test_unsafe_path(self):
        with tempfile.TemporaryDirectory() as td:
            for p in ('../bad','/tmp/bad','x/../bad','a\\b','x//a'):
                with self.assertRaises(ValueError):e.safe_path(Path(td),p,False)
    def test_symlink_path(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);(root/'link').symlink_to('/tmp',target_is_directory=True)
            with self.assertRaises(ValueError):e.safe_path(root,'link/test',False)


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'real FFmpeg required')
class EditRealMediaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.root=Path(cls.tmp.name)
        cls.t=fixture()
        for sid,pattern in [('S1','testsrc2'),('S2','testsrc')]:
            e.run(['ffmpeg','-v','error','-nostdin','-n','-f','lavfi','-i',f'{pattern}=size=64x64:rate=24:duration=2',
                   '-vf','format=yuv420p','-c:v','ffv1','-colorspace','bt709','-color_primaries','bt709',
                   '-color_trc','bt709','-color_range','tv',str(cls.root/(sid+'.mkv'))],30)
        # Use actual decoded tags, never pretend the encoder preserved tags it dropped.
        actual_color=e._color(e.probe(cls.root/'S1.mkv')['streams'][0])
        cls.t['color']=actual_color
        for source in cls.t['sources']:
            if source['kind']=='video': source['color']=actual_color.copy()
        cls.samples={}
        for sid,freq in [('SA',440),('SB',880)]:
            values=[int(3000*math.sin(2*math.pi*freq*i/48000)) for i in range(96000)]
            cls.samples[sid]=values
            with wave.open(str(cls.root/(sid+'.wav')),'wb') as f:
                f.setnchannels(2);f.setsampwidth(2);f.setframerate(48000)
                f.writeframes(b''.join(struct.pack('<hh',v,v) for v in values))
        ev=cls.root/'synthetic-evidence.txt';ev.write_text('SYNTHETIC ENGINEERING DATA. Not real visual/audio inspection.')
        for s in cls.t['sources']:
            s['sha256']=e.file_sha(cls.root/s['path'])
            report={'schema_version':'edit-source-review-1','status':'PASS','source_sha256':s['sha256'],
                    'kind':s['kind'],'reviewer':'synthetic-fixture-not-human-acceptance',
                    'accepted_ranges':[[0,s['units']]],'evidence':[{'path':ev.name,'sha256':e.file_sha(ev)}]}
            p=cls.root/s['review']['path'];p.write_text(json.dumps(report))
            s['review']['sha256']=e.file_sha(p)
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def test_verified_media(self):self.assertEqual(e.verify_sources(self.t,self.root)['status'],'INPUTS_VERIFIED')
    def test_real_render_and_lcut_audio(self):
        r=e.render(self.t,self.root,'out/master.mkv','out/render.json',40)
        self.assertEqual(r['status'],'RENDERED_NOT_ACCEPTED');self.assertEqual(r['duration_frames'],48)
        self.assertEqual(r['duration_samples'],96000);self.assertEqual(r['semantic_review'],'NOT_RUN')
        raw=self.root/'out/check.pcm'
        e.run(['ffmpeg','-v','error','-n','-i',str(self.root/'out/master.mkv'),'-map','0:a:0','-c:a','pcm_s16le','-f','s16le',str(raw)],30)
        values=struct.unpack('<'+'h'*(raw.stat().st_size//2),raw.read_bytes())[::2]
        self.assertEqual(set(values[:12000]),{0})
        # A1 continues across the visual cut at sample 48000; no duplicate native sound.
        self.assertEqual(list(values[47000:50000]),self.samples['SA'][47000:50000])
        self.assertEqual(list(values[72000:73000]),self.samples['SB'][:1000])
        self.assertEqual(set(values[60000:72000]),{0})
    def test_real_jcut_audio_precedes_picture(self):
        t=deepcopy(self.t)
        t['audio']=[t['audio'][1]];t['audio'][0]['dst_in']=36000
        t['events']=[v for v in t['events'] if v['event_id']!='EL1']
        t['video'][0]['visible_dialogue']=False;t['video'][1]['visible_dialogue']=True
        t['sync_links']=[{'video_clip':'V2','audio_clip':'A2','source_frame':12,'source_sample':12000,'tolerance_samples':0}]
        r=e.render(t,self.root,'out/jcut.mkv','out/jcut.json',40)
        raw=self.root/'out/jcut.pcm'
        e.run(['ffmpeg','-v','error','-n','-i',str(self.root/'out/jcut.mkv'),'-map','0:a:0','-c:a','pcm_s16le','-f','s16le',str(raw)],30)
        values=struct.unpack('<'+'h'*(raw.stat().st_size//2),raw.read_bytes())[::2]
        self.assertEqual(list(values[36000:37000]),self.samples['SB'][:1000])
        self.assertEqual(set(values[:36000]),{0})
        self.assertEqual(r['duration_frames'],48)
    def test_actual_irregular_timestamps_blocked(self):
        p=self.root/'vfr.mkv'
        e.run(['ffmpeg','-v','error','-n','-i',str(self.root/'S1.mkv'),'-vf',
               'setpts=if(gte(N\\,24)\\,PTS+0.2/TB\\,PTS)','-fps_mode','passthrough','-c:v','ffv1',str(p)],30)
        t=deepcopy(self.t);s=t['sources'][0];s['path']=p.name;s['sha256']=e.file_sha(p)
        info=e.probe(p)['streams'][0];s['color']=e._color(info)
        # Hash-binding is updated to this synthetic fixture, not a real approval.
        r={'schema_version':'edit-source-review-1','status':'PASS','source_sha256':s['sha256'],
           'kind':'video','reviewer':'synthetic-test','accepted_ranges':[[0,48]],
           'evidence':[{'path':'synthetic-evidence.txt','sha256':e.file_sha(self.root/'synthetic-evidence.txt')}]}
        rp=self.root/'vfr-review.json';rp.write_text(json.dumps(r));s['review']={'path':rp.name,'sha256':e.file_sha(rp)}
        self.assertEqual(e.verify_sources(t,self.root)['status'],'BLOCKED')
    def test_exact_video_selection(self):
        e.render(self.t,self.root,'out/picture.mkv','out/picture.json',40)
        paths=[]
        for sid,lo,hi in [('S1',6,30),('S2',12,36)]:
            dst=self.root/f'{sid}.raw';paths.append(dst)
            e.run(['ffmpeg','-v','error','-n','-i',str(self.root/(sid+'.mkv')),'-vf',f'trim=start_frame={lo}:end_frame={hi}',
                   '-an','-c:v','rawvideo','-pix_fmt','yuv420p','-f','rawvideo',str(dst)],30)
        dst=self.root/'actual.raw'
        e.run(['ffmpeg','-v','error','-n','-i',str(self.root/'out/picture.mkv'),'-an','-c:v','rawvideo','-pix_fmt','yuv420p','-f','rawvideo',str(dst)],30)
        self.assertEqual(dst.read_bytes(),b''.join(p.read_bytes() for p in paths))
    def test_existing_output_unchanged(self):
        p=self.root/'old.mkv';p.write_bytes(b'preserve')
        with self.assertRaises(FileExistsError):e.render(self.t,self.root,'old.mkv','old.json',30)
        self.assertEqual(p.read_bytes(),b'preserve')
    def test_wrong_hash_blocks(self):
        t=deepcopy(self.t);t['sources'][0]['sha256']='1'*64
        self.assertEqual(e.verify_sources(t,self.root)['status'],'BLOCKED')
    def test_actual_frame_count_mismatch(self):
        t=deepcopy(self.t);t['sources'][0]['units']=49
        self.assertEqual(e.verify_sources(t,self.root)['status'],'BLOCKED')
    def test_missing_review(self):
        t=deepcopy(self.t);t['sources'][0]['review']['path']='missing.json'
        self.assertEqual(e.verify_sources(t,self.root)['status'],'BLOCKED')
    def test_review_range_does_not_cover_tail(self):
        t=deepcopy(self.t);s=t['sources'][0]
        r=json.loads((self.root/s['review']['path']).read_text());r['accepted_ranges']=[[0,20]]
        p=self.root/'short-review.json';p.write_text(json.dumps(r))
        s['review']={'path':p.name,'sha256':e.file_sha(p)}
        self.assertEqual(e.verify_sources(t,self.root)['status'],'BLOCKED')
    def test_native_track_not_automapped(self):
        command=e.build_command(self.t,self.root,self.root/'candidate.mkv')
        self.assertNotIn('0:a',command);self.assertIn('[aout]',command)
    def test_no_shell_and_no_overwrite_switch(self):
        command=e.build_command(self.t,self.root,self.root/'candidate.mkv')
        self.assertIn('-n',command);self.assertNotIn('-y',command);self.assertNotIn('-shortest',command)
    def test_unsupported_effect_never_renders(self):
        t=deepcopy(self.t);t['video'][0]['transition']='dissolve'
        with self.assertRaises(ValueError):e.render(t,self.root,'bad.mkv','bad.json',30)
        self.assertFalse((self.root/'bad.mkv').exists())


if __name__=='__main__':unittest.main()
