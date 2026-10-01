from pathlib import Path
import copy
import importlib.util
import json
import sys
import unittest

ROOT=Path(__file__).resolve().parents[2]
VIS=ROOT/'visual-continuity-prompter'
sys.path.insert(0,str(VIS/'scripts'))
import continuity_tools as ct

class PromptExtensions(unittest.TestCase):
    def setUp(self):
        self.scene=json.loads((VIS/'examples/scene.json').read_text())
        self.shot=json.loads((VIS/'examples/shot.json').read_text())
        self.profile=json.loads((VIS/'templates/runtime-profile.json').read_text())
        ext=json.loads((ROOT/'production-ops/examples/compiler-extensions.json').read_text())
        self.style=ext['style_lock'];self.audio=ext['audio_plan']
    def video(self):
        self.shot['mode']='video_i2v'
        self.shot['output']['media_kind']='video'
        self.shot['video']={'action_beats':[], 'end_state_description':'保持状态'}
        self.shot['audio_plan']=copy.deepcopy(self.audio)
    def test_style_sentence_preserved_once(self):
        self.shot['style_lock']=self.style
        text=ct.render_prompt(self.scene,self.shot)
        self.assertEqual(text.count(self.style['prompt_sentence']),1)
    def test_old_no_style_stays_compatible(self):
        self.assertNotIn(self.style['prompt_sentence'],ct.render_prompt(self.scene,self.shot))
    def test_native_exact_words(self):
        self.video();text=ct.render_prompt(self.scene,self.shot)
        self.assertIn('钥匙在我手里。',text)
    def test_inner_actual_text_not_sent_as_native(self):
        self.video();text=ct.render_prompt(self.scene,self.shot)
        self.assertNotIn('还不能让他知道。',text)
        self.assertIn('不把心声演成嘴部逐字发声',text)
    def test_duplicate_audio_line_rejected(self):
        self.video();self.shot['audio_plan']['post_voices'][0]['line_id']='DEMO-L01'
        self.assertTrue(any('double-routed' in x for x in ct.validate(self.scene,self.shot,self.profile)))
    def test_audio_plan_on_image_rejected(self):
        self.shot['audio_plan']=self.audio
        self.assertTrue(any('only valid' in x for x in ct.validate(self.scene,self.shot,self.profile)))
    def test_empty_style_rejected(self):
        self.shot['style_lock']={}
        self.assertTrue(any('style_lock' in x for x in ct.validate(self.scene,self.shot,self.profile)))
    def test_native_missing_voice_rejected(self):
        self.video();self.shot['audio_plan']['native_spoken_lines'][0]['voice_description']=''
        self.assertTrue(any('voice description' in x for x in ct.validate(self.scene,self.shot,self.profile)))
    def test_source_kind_invalid_rejected(self):
        self.video();self.shot['audio_plan']['post_voices'][0]['source_kind']='spoken'
        self.assertTrue(any('source kind' in x for x in ct.validate(self.scene,self.shot,self.profile)))
    def test_null_audio_array_rejected(self):
        self.video();self.shot['audio_plan']['post_voices']=None
        self.assertTrue(any('arrays required' in x for x in ct.validate(self.scene,self.shot,self.profile)))
if __name__=='__main__':unittest.main()
