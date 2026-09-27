#!/usr/bin/env python3
"""adversary_plan 高风险判定回归：只看 motion；拿物件、张嘴、推门不算；物理动作与身体接触算。"""
import unittest
import adversary_plan as ap


class T(unittest.TestCase):
    def hr(self, motion, **kw):
        return ap.high_risk({"motion": motion, **kw})

    def test_physical(self):
        self.assertTrue(self.hr("0.5 秒汤从碗沿泼出，落进空盘"))
        self.assertTrue(self.hr("她脚下一滑，滑倒在瓷砖上"))

    def test_body_contact(self):
        self.assertTrue(self.hr("沈静隔着桌面握住林瑶端碗那只手的手腕"))
        self.assertTrue(self.hr("她的掌心整个盖在他压在台角上的拿手机的手背上"))

    def test_not_risky(self):
        self.assertFalse(self.hr("她双手握着手机贴耳，嘴微张说完一句"))
        self.assertFalse(self.hr("林砚推门进来，站在门垫上，剪刀张开卡在花杆上"))
        self.assertFalse(self.hr("三人坐着看画左", multi_person=True, must_show_ids=["MS1"]))
        self.assertFalse(self.hr("", keyframe="沈静握住林瑶手腕"))   # 只看 motion

    def test_override(self):
        self.assertTrue(self.hr("看着她", adversary=True))
        self.assertFalse(self.hr("汤泼出来", adversary=False))


if __name__ == "__main__":
    unittest.main()
