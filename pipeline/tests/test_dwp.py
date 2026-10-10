import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import dwp as D  # noqa: E402


def benefit(name, total, exp, measured, pct):
    return {"name": name, "measured": measured, "measured_end": None, "months_since": D.months_between(D.parse_measured_end(measured), D.LATEST_END) if measured else None,
            "expenditure": exp, "total": {"est": total, "lo": total * .9, "hi": total * 1.1}, "fraud": {"est": total / 2, "lo": 0, "hi": 0},
            "claimant": {"est": 0, "lo": 0, "hi": 0}, "official": {"est": 0, "lo": 0, "hi": 0}, "pct": {"est": pct, "lo": 0, "hi": 0}, "cases_pct": None, "pct_series": []}


class Helpers(unittest.TestCase):
    def test_labels_and_dates(self):
        self.assertEqual(D.fy_label(2026), "2025-26")
        self.assertEqual(D.parse_measured_end("November 2024 - October 2025"), (2025, 10))
        self.assertEqual(D.parse_measured_end("March 2024 - September 2024"), (2024, 9))
        self.assertIsNone(D.parse_measured_end(None))
        self.assertEqual(D.months_between((2021, 8), (2026, 3)), 55)

    def test_num_markers(self):
        for m in ("x", "w", "z", None, ""):
            self.assertIsNone(D._num(m))
        self.assertEqual(D._num(9900000000), 9.9e9)


class Flags(unittest.TestCase):
    def data(self):
        return {"releases": ["2025", "2026"], "revisions": [], "benefits": [
            benefit("Fresh", 100, 20000, "November 2024 - October 2025", 0.5),
            benefit("Stale big", 400, 8000, "October 2020 - August 2021", 5.0),
            benefit("Stale small", 5, 300, "October 2017 - September 2018", 1.0),
            benefit("Bad rate", 700, 8000, "November 2024 - October 2025", 8.8),
            benefit("Unreviewed excluding Council Tax Benefit", 30, 7100, None, None)]}

    def test_stale_rate_and_unreviewed(self):
        fl = D.dwp_flags(self.data())
        by = {(f["type"], f["benefit"]): f for f in fl}
        self.assertIn(("dwp_stale", "Stale big"), by)
        self.assertNotIn(("dwp_stale", "Stale small"), by)         # below £1bn spend: not material
        self.assertNotIn(("dwp_stale", "Fresh"), by)
        self.assertEqual(by[("dwp_rate", "Bad rate")]["sev"], 3)
        self.assertIn(("dwp_stale", "Unreviewed excluding Council Tax Benefit"), by)

    def test_revision_outside_interval_is_flagged_small_noise_is_not(self):
        d = self.data()
        d["revisions"] = [{"benefit": "X", "line": "Total", "by_fye": {
            "2023-24": {"2025": {"est": 1000, "lo": 900, "hi": 1100}, "2026": {"est": 1010, "lo": 900, "hi": 1100}},      # +10: noise
            "2024-25": {"2025": {"est": 1000, "lo": 950, "hi": 1050}, "2026": {"est": 1300, "lo": 1200, "hi": 1400}}}}]   # +300, outside
        rv = [f for f in D.dwp_flags(d) if f["type"] == "dwp_revision"]
        self.assertEqual([f["year"] for f in rv], ["2024-25"])
        self.assertGreaterEqual(rv[0]["sev"], 2)


if __name__ == "__main__":
    unittest.main()
