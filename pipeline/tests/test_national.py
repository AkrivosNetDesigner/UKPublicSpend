import gzip
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import national as N  # noqa: E402


def ks2(year, subject, pct, level="National", group="All state funded"):
    r = {"time_period": year, "geographic_level": level, "establishment_type_group": group, "subject": subject, "expected_standard_pupil_percent": pct}
    r.update({c: "Total" for c in N.TOTALS})
    return r


class National(unittest.TestCase):
    def test_academic_year_label(self):
        self.assertEqual(N.ay("201617"), "2016-17")

    def test_suppressed_values_are_none(self):
        self.assertIsNone(N.num("x"))
        self.assertEqual(N.num("61"), 61.0)

    def test_ks2_picks_headline_rows_only(self):
        rows = [ks2("201617", "Reading, writing and maths", "61"), ks2("201617", "Maths", "75"), ks2("201617", "Reading, writing and maths", "99", level="Regional"),
                ks2("201920", "Reading, writing and maths", "x")]
        self.assertEqual(N.ks2_series(rows), {"2016-17": 61.0})

    def test_gzip_is_transparent(self):
        raw = gzip.compress("a,b\n1,2\n".encode())
        self.assertEqual(N.rows_from_csv_bytes(raw), [{"a": "1", "b": "2"}])

    def test_build_joins_spending_to_pupils(self):
        pupils = [{"geographic_level": "National", "phase_type_grouping": "Total", "fsm_breakdown": "All pupils", "fsm_eligibility": "Total", "time_period": "201617", "pupil_count": "1000000", "pupil_percent": "100"}]
        out = N.build([], [], pupils, ["2016-17"], [100.0])
        self.assertEqual(out["per_pupil"]["2016-17"], 100000)


if __name__ == "__main__":
    unittest.main()
