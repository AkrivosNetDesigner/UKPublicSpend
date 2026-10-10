import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import borrowing as B  # noqa: E402


def months(n, start=(2012, 4)):
    out, y, m = [], *start
    for _ in range(n):
        out.append(f"{y}-{m:02d}")
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return out


class Holdings(unittest.TestCase):
    def test_groups_sum_the_right_columns(self):
        h = {"quarters": ["2026 Q1"], "cols": {c: [float(c)] for c in B.HOLDER_COLS}}
        g = {x["name"]: x["values"][0] for x in B.holder_groups(h)}
        self.assertEqual(g["Overseas investors"], 10.0)
        self.assertEqual(g["Households, companies and public bodies"], 2 + 3 + 7 + 8 + 9)
        self.assertEqual(g["Bank of England"], 13.0)

    def test_missing_column_gives_none_not_a_wrong_sum(self):
        h = {"quarters": ["1987 Q1"], "cols": {c: [1.0] for c in B.HOLDER_COLS}}
        h["cols"][8] = [None]
        g = {x["name"]: x["values"][0] for x in B.holder_groups(h)}
        self.assertIsNone(g["Households, companies and public bodies"])


class Yields(unittest.TestCase):
    def write(self, d, name, text):
        p = Path(d) / name
        p.write_text(text)
        return p

    def test_merges_files_and_averages_by_month(self):
        with tempfile.TemporaryDirectory() as d:
            a = self.write(d, "a.csv", "DATE,IUDMNPY\n01 Oct 2026,5.0\n02 Oct 2026,6.0\n\n05 Nov 2026,4.0\n")
            b = self.write(d, "b.csv", "DATE,IUDSIZC\n01 Oct 2026,3.0\n")
            y = B.parse_yields([a, b])
        self.assertEqual(y["months"], ["2026-10", "2026-11"])
        self.assertEqual(y["monthly"]["IUDMNPY"], [5.5, 4.0])
        self.assertEqual(y["monthly"]["IUDSIZC"], [3.0, None])
        self.assertEqual(y["latest"]["date"], "2026-11-05")


class Flags(unittest.TestCase):
    def test_spike_flagged_once_and_rebound_ignored(self):
        m = months(96)
        b = [10000.0 + (i % 12) * 100 for i in range(96)]
        b[60] = 60000.0           # a shock
        b[72] = 10000.0 + 0       # next year: back to normal, which looks like a fall versus the shock
        fl = B.borrowing_flags(m, b, from_month="2012-01")
        months_flagged = [f["month"] for f in fl]
        self.assertIn(m[60], months_flagged)
        self.assertNotIn(m[72], months_flagged)

    def test_small_changes_are_not_flagged(self):
        m = months(96)
        b = [10000.0 + (i % 12) * 100 + (200 if i % 5 == 0 else 0) for i in range(96)]
        self.assertEqual(B.borrowing_flags(m, b, from_month="2012-01"), [])


if __name__ == "__main__":
    unittest.main()
