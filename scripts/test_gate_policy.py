"""门的降级策略：只有 HARD_ERRORS 里的门拦截，其余 error 降为 warn。"""
import unittest

import shots_tool


class GatePolicy(unittest.TestCase):
    def test_soft_codes_become_warn(self):
        f = shots_tool.Findings()
        f.add("G02", "error", "EP001-S01", "x")
        f.add("G53", "error", "EP001-S01", "x")
        f.add("G10", "error", "EP001-S01", "x")
        self.assertEqual([x["code"] for x in f.errors()], ["G10"])
        self.assertEqual(sorted(x["code"] for x in f.warns()), ["G02", "G53"])


class SpecLock(unittest.TestCase):
    def test_spec_and_scene_lock(self):
        F = shots_tool.Findings()
        full = {k: "v" for k in shots_tool.SPEC_KEYS}
        data = {"camera_setups": {"A": {"plate": "IMG-P", "lock": "LOCKTEXT"}}}
        shots = [{"id": "S1", "camera_setup": "A", "frame_prompt": "x LOCKTEXT", "frame_refs": ["IMG-P"], "spec": full},
                 {"id": "S2", "camera_setup": "A", "start_from_prev": "S1", "spec": full},
                 {"id": "S3", "camera_setup": "A", "frame_prompt": "no", "frame_refs": [], "spec": {}},
                 {"id": "S4", "camera_setup": "B", "spec": full, "start_from_prev": "S1"}]
        shots_tool.spec_lock_findings(F, data, shots)
        bad = {(f["code"], f["shot"]) for f in F.errors()}
        self.assertNotIn(("G55", "S1"), bad)
        self.assertNotIn(("G55", "S2"), bad)
        self.assertIn(("G55", "S3"), bad)
        self.assertIn(("G56", "S3"), bad)
        self.assertIn(("G56", "S4"), bad)

    def test_old_projects_unaffected(self):
        F = shots_tool.Findings()
        shots_tool.spec_lock_findings(F, {}, [{"id": "S1"}])
        self.assertEqual(F.items, [])


if __name__ == "__main__":
    unittest.main()
