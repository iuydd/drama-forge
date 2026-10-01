"""General person leakage vs legitimate offscreen technical/environment wording."""
import unittest
import prompt_nine as p

class Insert42Tests(unittest.TestCase):
    def setUp(self):self.shot={'insert_policy':{'kind':'object_only','visible_entity_ids':['KEY'],'offscreen_aliases':['PRIVATE_NAME'],'post_audio_separate':True},'audio_plan':{},'references':[]}
    def test_offscreen_light_is_not_a_person(self):self.assertEqual(p.inspect_insert(self.shot,'钥匙静置，画外光源形成柔和高光。'),[])
    def test_offscreen_rain_is_not_a_person(self):self.assertEqual(p.inspect_insert(self.shot,'钥匙静置。画外传来连续的雨声。'),[])
    def test_english_environment_is_not_a_person(self):self.assertEqual(p.inspect_insert(self.shot,'A key rests still. Off-screen rain, soft illumination.'),[])
    def test_generic_chinese_person_still_blocked(self):self.assertTrue(p.inspect_insert(self.shot,'有人站在画外。'))
    def test_generic_english_person_still_blocked(self):self.assertTrue(p.inspect_insert(self.shot,'An off-screen person waits.'))
    def test_private_alias_still_blocked_without_location_word(self):self.assertTrue(p.inspect_insert(self.shot,'Do not include PRIVATE_NAME.'))

if __name__=='__main__':unittest.main()
