import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import outcomes2 as O2  # noqa: E402


def planning_sheet():
    q = ["April to June 2025", "July to September 2025", "October to December 2025", "January to March 2026"]
    labels = [None, None]
    for name in q:
        labels += [name, None, None, None, None, None]
    head = ["Local planning authority", "ONS code"]
    for _ in q:
        head += ["Major decisions", "within 13 weeks", "PPA", "within agreed", "Imputed", None]
    row = ["Testshire", "E07000001"]
    for _ in q:
        row += [10.0, 5.0, 4.0, 3.0, None, None]
    return {"Table_P151a": [[], labels, head, [], row, ["Bad", "not-a-code"] + [1.0] * 24]}


class Planning(unittest.TestCase):
    def test_on_time_share_over_four_quarters(self):
        with mock.patch.object(O2.ods, "read_ods", return_value=planning_sheet()):
            out = O2.read_planning_speed("x.ods", 2026)
        pct, n = out["E07000001"]
        self.assertEqual(n, 40.0)
        self.assertAlmostEqual(pct, 100 * (5 + 3) * 4 / 40)

    def test_quarters_not_in_table_give_nothing(self):
        with mock.patch.object(O2.ods, "read_ods", return_value=planning_sheet()):
            self.assertEqual(O2.read_planning_speed("x.ods", 2030), {})


class Ofsted(unittest.TestCase):
    def test_grades_are_ordinal_and_unknown_skipped(self):
        sheet = {"Inspections_as_at_31_March": [["Web link", "Local authority area code", "Local authority name", "Ofsted region", "Inspection date", "Publication date", "Overall effectiveness"],
                                                 ["l", "E09000002", "Barking and Dagenham", "London", "2023-07-10", "2023-09-04", "Requires improvement to be good"],
                                                 ["l", "E09000003", "Barnet", "London", "2024-06-10", "2024-07-23", "Outstanding"],
                                                 ["l", "E09000004", "Bexley", "London", "2024-06-10", "2024-07-23", "None"]]}
        with mock.patch.object(O2.ods, "read_ods", return_value=sheet):
            out = O2.read_ofsted("x.ods")
        self.assertEqual({k: v["grade"] for k, v in out.items()}, {"E09000002": 2, "E09000003": 4})


class Homelessness(unittest.TestCase):
    def test_ta_rate_per_thousand_households(self):
        row = ["E06000001", "Hartlepool", None, None, "130.0", "40.0"]
        with mock.patch.object(O2.ods, "read_ods", return_value={"TA1": [["x"], row, ["E92000001", "ENGLAND", None, None, "1", "1"]]}):
            out = O2.read_temporary_accommodation("x.ods")
        self.assertEqual(out, {"E06000001": 130.0 / 40.0})


if __name__ == "__main__":
    unittest.main()
