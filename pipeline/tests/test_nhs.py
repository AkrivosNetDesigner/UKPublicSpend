import datetime
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import nhs as N  # noqa: E402


def row(d, waiting, pct=0.9):
    r = [None] * 60
    r[2] = d
    r[8] = pct
    r[22] = waiting
    return tuple(r)


class Nhs(unittest.TestCase):
    def test_financial_year_slugs(self):
        self.assertEqual(N.fy_slugs(datetime.date(2026, 10, 10))[0], "rtt-data-2026-27")
        self.assertEqual(N.fy_slugs(datetime.date(2026, 2, 1))[0], "rtt-data-2025-26")

    def test_finds_overview_link(self):
        h = '<a href="https://x/y/Other.xlsx">Something else</a> <a href="https://x/y/RTT-Overview.xlsx">RTT Overview Timeseries Including Estimates for Missing Trusts Aug26 (XLS, 139K)</a>'
        self.assertEqual(N.find_file_link(h), "https://x/y/RTT-Overview.xlsx")

    def test_discover_falls_back_to_previous_year(self):
        pages = {N.BASE + "rtt-data-2026-27": [], N.BASE + "rtt-data-2025-26": [{"content": {"rendered": '<a href="https://x/o.xlsx">RTT Overview Timeseries Including Estimates for Missing Trusts Mar26</a>'}}]}
        self.assertEqual(N.discover(lambda u: pages.get(u, []), datetime.date(2026, 5, 1)), "https://x/o.xlsx")

    def test_parse_skips_months_without_waiting_list(self):
        rows = [row(datetime.datetime(2007, 4, 1), "-"), row(datetime.datetime(2008, 3, 1), 3_000_000.0, 0.66), ("note",)]
        out = N.parse_rows(rows)
        self.assertEqual(list(out), ["2008-03"])
        self.assertAlmostEqual(out["2008-03"]["within18_pct"], 66.0)

    def test_build_uses_march_as_financial_year_end(self):
        s = N.parse_rows([row(datetime.datetime(2008, 3, 1), 3_000_000.0), row(datetime.datetime(2008, 4, 1), 3_100_000.0)])
        out = N.build(s, ["2007-08"], [160.0], [6.0])
        self.assertEqual(out["waiting_year_end_m"], {"2007-08": 3.0})


if __name__ == "__main__":
    unittest.main()
