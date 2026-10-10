import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import hmrc as H  # noqa: E402


def months(n, start=(2017, 4)):
    out, y, m = [], *start
    for _ in range(n):
        out.append(f"{y}-{m:02d}")
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return out


class Helpers(unittest.TestCase):
    def test_labels(self):
        self.assertEqual(H.month_key("April 2017"), "2017-04")
        self.assertEqual(H.fy_key("2024 to 2025"), "2024-25")
        self.assertEqual(H.fy_of("2018-03"), "2017-18")
        self.assertEqual(H.fy_of("2018-04"), "2018-19")
        self.assertEqual(H.month_label("2021-05"), "May 2021")

    def test_num(self):
        self.assertEqual(H._num("14.1%"), 14.1)
        self.assertEqual(H._num("<0.1"), 0.05)
        self.assertIsNone(H._num("[X]"))
        self.assertEqual(H._num(3), 3.0)


class MonthlyFlags(unittest.TestCase):
    def series(self, shock=None):
        n = 60
        vals = [10000 + 40 * i + (300 if i % 12 == 0 else 0) for i in range(n)]
        if shock:
            for i, v in shock.items():
                vals[i] = v
        return months(n), {"Tax": vals}

    def test_flags_one_off_spike(self):
        m, c = self.series({40: 20000})
        fl = H.monthly_flags(m, c)
        self.assertTrue(any(f["month"] == m[40] for f in fl))

    def test_base_effect_not_double_counted(self):
        # drop at month 30 then recovery at month 42: only the drop should be reported
        m, c = self.series({30: 2000})
        c["Tax"][42] = 10000 + 40 * 42
        fl = H.monthly_flags(m, c)
        self.assertTrue(any(f["month"] == m[30] for f in fl))
        self.assertFalse(any(f["month"] == m[42] for f in fl))

    def test_quiet_series_not_flagged(self):
        m, c = self.series()
        self.assertEqual(H.monthly_flags(m, c), [])


class TaxGapRevisions(unittest.TestCase):
    def test_summary_and_bias(self):
        rev = {"years": ["2021-22", "2022-23"], "rows": [
            {"labels": ["MTG 2026"], "values": [6.0, 6.6]},
            {"labels": ["MTG 2025"], "values": [5.5, 5.7]},
            {"labels": ["MTG 2024"], "values": [4.8, 4.8]}]}
        s = H.taxgap_revision_summary(rev)
        by = {x["year"]: x for x in s}
        self.assertAlmostEqual(by["2022-23"]["revision_pp"], 1.8)
        self.assertEqual(by["2022-23"]["first_pub"], "MTG 2024")
        self.assertEqual(by["2021-22"]["n_pubs"], 3)
        b = H.recent_bias(s)
        self.assertEqual((b["n_up"], b["n"]), (2, 2))
        self.assertEqual(len(H.taxgap_flags(s)), 2)   # +1.8pp and +1.2pp both exceed the 1.0pp threshold


if __name__ == "__main__":
    unittest.main()
