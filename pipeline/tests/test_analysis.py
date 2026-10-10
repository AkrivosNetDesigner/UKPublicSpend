import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import analysis as A  # noqa: E402

YEARS = ["2021-22", "2022-23", "2023-24", "2024-25", "2025-26"]


def seg(code, vals, dept="Dept", group="G", ctrl="DEL"):
    return {"name": code, "vals": dict(zip(YEARS, vals)), "dept": {y: dept for y in YEARS}, "group": group, "ctrl": ctrl}


def quiet_peers(n=60):
    """Many boringly stable lines so the peer distribution is tight."""
    return {f"P{i}": seg(f"P{i}", [1e5 * (1 + 0.02 * k) for k in range(5)]) for i in range(n)}


class SegmentFlags(unittest.TestCase):
    def test_jump_detected_and_quiet_lines_not_flagged(self):
        segs = quiet_peers()
        segs["X"] = seg("X", [1e5, 1e5, 9e5, 9e5, 9e5])
        flags = A.segment_flags(segs, YEARS)
        self.assertTrue(any(f["code"] == "X" and f["type"] == "jump" and f["year"] == "2023-24" for f in flags))
        self.assertFalse(any(f["code"].startswith("P") and f["type"] == "jump" for f in flags))

    def test_new_and_closed_lines(self):
        segs = quiet_peers()
        segs["N"] = seg("N", [0, 5e5, 5e5, 5e5, 5e5])
        segs["C"] = seg("C", [5e5, 5e5, 0, 0, 0])
        types = {(f["code"], f["type"]) for f in A.segment_flags(segs, YEARS)}
        self.assertIn(("N", "new_line"), types)
        self.assertIn(("C", "closed_line"), types)

    def test_identical_round_signflip(self):
        segs = quiet_peers()
        segs["I"] = seg("I", [123456, 123456, 99999, 88888, 77777])
        segs["R"] = seg("R", [50000, 61234, 71234, 81234, 91234])  # 50000 = exact £50m
        segs["S"] = seg("S", [90000, -90000, -80000, -70000, -60000])
        types = {(f["code"], f["type"]) for f in A.segment_flags(segs, YEARS)}
        self.assertIn(("I", "identical"), types)
        self.assertIn(("R", "round"), types)
        self.assertIn(("S", "sign_flip"), types)

    def test_below_materiality_ignored(self):
        segs = quiet_peers()
        segs["T"] = seg("T", [100, 5000, 100, 5000, 100])  # £0.1m <-> £5m
        self.assertFalse(any(f["code"] == "T" for f in A.segment_flags(segs, YEARS)))


class Revisions(unittest.TestCase):
    def test_restatement_and_offsets(self):
        a = {"A": seg("A", [1e6] * 5), "B": seg("B", [1e6] * 5), "C": seg("C", [1e6] * 5)}
        b = {"A": seg("A", [1.5e6] * 5), "B": seg("B", [0.5e6] * 5), "C": seg("C", [2e6] * 5)}
        fl = A.revision_flags(["r1", "r2"], {"r1": a, "r2": b})
        by = {f["code"]: f for f in fl if f["year"] == "2023-24"}
        self.assertIn("offset_with", by["A"])      # A +0.5bn cancels B -0.5bn
        self.assertEqual(by["A"]["sev"], 1)
        self.assertNotIn("offset_with", by["C"])   # C +1bn has no counterpart
        self.assertGreaterEqual(by["C"]["sev"], 2)

    def test_new_code_is_structural_not_alarming(self):
        a = {"A": seg("A", [1e6] * 5)}
        b = {"A": seg("A", [1e6] * 5), "Z": seg("Z", [3e6] * 5)}
        fl = [f for f in A.revision_flags(["r1", "r2"], {"r1": a, "r2": b}) if f["code"] == "Z"]
        self.assertTrue(fl and all(f["sev"] == 1 and f["structural"] for f in fl))


class Benford(unittest.TestCase):
    def test_first_digit(self):
        self.assertEqual([A.first_digit(x) for x in (0.0042, 7, 99.9, 12345, -310)], [4, 7, 9, 1, 3])

    def test_benford_vs_uniform(self):
        import random
        random.seed(1)
        benf = [{"dept": "B", "amount": 10 ** random.uniform(0, 6)} for _ in range(3000)]
        flat = [{"dept": "F", "amount": random.uniform(1, 9.99)} for _ in range(3000)]
        res = {d["dept"]: d for d in A.benford_by_dept(benf + flat)["depts"]}
        self.assertEqual(res["B"]["label"], "close")
        self.assertEqual(res["F"]["label"], "nonconforming")


class Checks(unittest.TestCase):
    def test_check_pass_and_warn(self):
        self.assertEqual(A._check("x", "t", [("y", 100, 100.5)], 1)["status"], "pass")
        self.assertEqual(A._check("x", "t", [("y", 100, 105)], 1)["status"], "warn")


if __name__ == "__main__":
    unittest.main()
