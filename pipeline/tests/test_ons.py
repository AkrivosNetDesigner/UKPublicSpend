import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ons as O  # noqa: E402


def months(n, start=(2020, 4)):
    out, y, m = [], *start
    for _ in range(n):
        out.append(f"{y}-{m:02d}")
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return out


class Sums(unittest.TestCase):
    def test_fy_sums_only_complete_years(self):
        m = months(14)                      # Apr 2020 .. May 2021
        s = O.fy_sums(m, [1.0] * 14)
        self.assertEqual(s, {"2020-21": 12.0})   # 2021-22 has only 2 months

    def test_stocks_are_not_flows(self):
        self.assertIn("KSE6", O.STOCKS)
        self.assertIn(("J5II", "Net borrowing", "Public sector (excluding banks)", -1), O.SERIES)


class Checks(unittest.TestCase):
    def fake(self, tme, rec, borrow_ons_sign):
        n = len(tme)
        def s(vals, stock=False): return {"label": "", "group": "", "title": "", "sign": 1, "stock": stock, "values": vals}
        series = {c: s([100.0] * n) for c, *_ in O.SERIES}
        series["KX5Q"], series["JW2O"] = s(tme), s(rec)
        series["J5II"] = s([borrow_ons_sign * (a - b) for a, b in zip(tme, rec)])   # already sign-flipped by the parser
        series["MF6U"], series["MF6S"], series["MF6T"] = s([110.0] * n), s([100.0] * n), s([10.0] * n)
        return {"months": months(n), "series": series}

    def test_identities_pass_and_detect_break(self):
        ok = O.ons_checks(self.fake([120.0] * 24, [100.0] * 24, 1), [])
        self.assertEqual({c["id"]: c["status"] for c in ok}["ons_borrow"], "pass")
        bad = self.fake([120.0] * 24, [100.0] * 24, 1)
        bad["series"]["J5II"]["values"][5] += 50
        res = {c["id"]: c["status"] for c in O.ons_checks(bad, [])}
        self.assertEqual(res["ons_borrow"], "warn")


class Flags(unittest.TestCase):
    def test_near_zero_series_not_screened_and_old_months_dropped(self):
        n = 120
        m = months(n, (2010, 4))
        vals = [10000 + 30 * i for i in range(n)]
        vals[20] = 40000                      # spike in 2012: before FLAG_FROM, must be dropped
        vals[100] = 40000                     # spike in 2018: reported
        def s(v): return {"label": "Spend", "group": "", "title": "", "sign": 1, "stock": False, "values": v}
        ons = {"months": m, "series": {"X": s(vals), "J5II": {**s(vals), "label": "Net borrowing"}}}
        fl = O.ons_flags(ons)
        self.assertTrue(any(f["month"] == m[100] for f in fl))
        self.assertFalse(any(f["month"] == m[20] for f in fl))
        self.assertFalse(any(f["tax"] == "Net borrowing" for f in fl))


if __name__ == "__main__":
    unittest.main()
