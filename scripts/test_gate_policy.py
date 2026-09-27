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


if __name__ == "__main__":
    unittest.main()
