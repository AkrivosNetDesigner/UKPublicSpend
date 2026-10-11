import csv
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import devolved as D  # noqa: E402
import ni as NI  # noqa: E402

POP = {"W06000015": {"name": "Cardiff", "pop": 380000.0, "age0_17": 80000.0, "age65": 60000.0}, "W06000011": {"name": "Swansea", "pop": 250000.0, "age0_17": 50000.0, "age65": 50000.0},
       "W92000004": {"name": "Wales", "pop": 630000.0, "age0_17": 130000.0, "age65": 110000.0}}


class Names(unittest.TestCase):
    def test_norm_treats_and_and_ampersand_alike(self):
        self.assertEqual(D.norm("Perth & Kinross"), D.norm("Perth and Kinross"))


class Scotland(unittest.TestCase):
    def test_discover_picks_the_la_level_workbook_from_the_newest_publication(self):
        pages = {"https://www.gov.scot/publications/scottish-local-government-finance-statistics-2025-26/documents/": None,
                 "https://www.gov.scot/publications/scottish-local-government-finance-statistics-2024-25/documents/":
                 '<a href="/binaries/x/LA%2BLevel%2B-%2BNet%2BRevenue%2BExpenditure%2Band%2BIncome%2Bby%2BService%2Band%2BType%2B-%2B2026-01-09.xlsx">x</a>'}

        def get(u):
            if pages.get(u) is None:
                raise OSError("404")
            return pages[u]
        url, year = D.discover_scotland(get, today=__import__("datetime").date(2026, 10, 11))
        self.assertEqual(year, "2024-25")
        self.assertTrue(url.startswith("https://www.gov.scot/binaries/"))


class Wales(unittest.TestCase):
    def test_read_and_check(self):
        rows = [("Education", "Cardiff", 100.0), ("Social services", "Cardiff", 50.0), ("Revenue expenditure", "Cardiff", 150.0),
                ("Education", "Swansea", 60.0), ("Social services", "Swansea", 40.0), ("Revenue expenditure", "Swansea", 100.0),
                ("Education", "Total Unitary Authorities", 160.0), ("Social services", "Total Unitary Authorities", 90.0), ("Revenue expenditure", "Total Unitary Authorities", 250.0)]
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "w.csv"
            with open(p, "w", newline="") as f:
                w = csv.writer(f)
                w.writerow(["Data values", "Data description", "Year", "Service", "Authority", "Notes"])
                for s, a, v in rows:
                    w.writerow([v, "£ thousand", "2024-25", s, a, ""])
                    w.writerow([v * 1000 / 380000, "£ per head", "2024-25", s, a, ""])
            cs, totals, ph = D.read_wales(p, POP)
            self.assertEqual(set(cs), {"W06000015", "W06000011"})
            self.assertEqual(cs["W06000015"]["y"]["2024-25"]["tot"], 150.0)
            cks = {c["id"]: c for c in D.wales_checks(cs, totals, ph, POP, "2024-25")}
            self.assertEqual(cks["dev_wa_services"]["status"], "pass")
            self.assertEqual(cks["dev_wa_councils"]["status"], "pass")


NI_TEXT = """
TABLE 3 - RATE STATISTICS 2026/2027
COMPARISION OF ESTIMATED NET EXPENDITURE ON SERVICES
                       Net Expenditure   Net Expenditure   Actual Increase   % Change
District Council           2025/2026         2026/2027
Antrim and Newtownabbey       64,307,987        67,152,661       2,844,674         4.42%
Ards and North Down           69,247,500        72,899,100       3,651,600         5.27%
Armagh, Banbridge and
Craigavon                     92,828,591        96,065,591       3,237,000         3.49%
Belfast                      220,081,480       227,760,695       7,679,215         3.49%
Causeway Coast and Glens      66,005,705        68,686,917       2,681,212         4.06%
Derry and Strabane            82,200,422        85,869,326       3,668,904         4.46%
Fermanagh and Omagh           48,981,462        50,556,311       1,574,849         3.22%
Lisburn and Castlereagh       66,681,509        69,232,215       2,550,706         3.83%
Mid and East Antrim           75,215,328        78,035,801       2,820,473         3.75%
Mid Ulster                    60,567,471        61,429,080        861,609          1.42%
Newry, Mourne and Down        76,737,337        79,938,294       3,200,957         4.17%
NI TOTAL/AVERAGE             922,854,792       957,625,991       34,771,199        3.77%
TABLE 4 - RATE STATISTICS 2026/2027
"""


class NorthernIreland(unittest.TestCase):
    def test_table_3_parses_with_wrapped_names_and_ties_to_the_printed_total(self):
        py, cy, rows, total = NI.parse_table3(NI_TEXT)
        self.assertEqual((py, cy), ("2025/2026", "2026/2027"))
        self.assertEqual(len(rows), 11)
        self.assertEqual(rows["N09000002"], (92828591, 96065591))
        self.assertEqual(sum(b for _, b in rows.values()), total[1])

    def test_unknown_council_is_an_error_not_a_silent_skip(self):
        with self.assertRaises(RuntimeError):
            NI.parse_table3(NI_TEXT.replace("Belfast ", "Belfastx "))


if __name__ == "__main__":
    unittest.main()
