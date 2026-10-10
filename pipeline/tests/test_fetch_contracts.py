import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import fetch_contracts as F  # noqa: E402


class Plan(unittest.TestCase):
    def test_newest_first_and_skips_done_past_days(self):
        days = F.plan(date(2026, 10, 1), date(2026, 10, 5), {"2026-10-02", "2026-10-03"})
        self.assertEqual(days, [date(2026, 10, 5), date(2026, 10, 4), date(2026, 10, 1)])

    def test_today_is_always_refetched_even_if_marked_done(self):
        days = F.plan(date(2026, 10, 4), date(2026, 10, 5), {"2026-10-05", "2026-10-04"})
        self.assertEqual(days, [date(2026, 10, 5)])

    def test_nothing_new_after_a_complete_run_except_today(self):
        done = {f"2026-10-0{d}" for d in range(1, 5)}
        self.assertEqual(F.plan(date(2026, 10, 1), date(2026, 10, 5), done), [date(2026, 10, 5)])


class Windows(unittest.TestCase):
    def test_one_day_window_has_an_exclusive_end_at_next_midnight(self):
        self.assertEqual(F.windows(date(2026, 4, 30)), [("2026-04-30T00:00:00", "2026-05-01T00:00:00")])

    def test_split_windows_tile_the_day_without_gaps(self):
        w = F.windows(date(2026, 4, 30), 4)
        self.assertEqual(len(w), 4)
        self.assertEqual(w[0][0], "2026-04-30T00:00:00")
        self.assertEqual(w[-1][1], "2026-05-01T00:00:00")
        for (a1, b1), (a2, b2) in zip(w, w[1:]):
            self.assertEqual(b1, a2)


class Privacy(unittest.TestCase):
    def test_contact_people_are_dropped(self):
        rel = {"ocid": "o", "date": "2026-04-01T00:00:00Z", "tag": ["award"], "tender": {"title": "T", "procurementMethodDetails": "Open procedure"},
               "buyer": {"id": "B", "name": "A Council"},
               "parties": [{"id": "B", "name": "A Council", "roles": ["buyer"], "contactPoint": {"name": "Jane Doe", "email": "jane@x.gov.uk", "telephone": "0123"}}],
               "awards": [{"id": "a1", "date": "2026-03-30T00:00:00Z", "datePublished": "2026-04-01T00:00:00Z", "value": {"amount": 1000, "currency": "GBP"}, "suppliers": []}]}
        text = repr(F.compact(rel))
        for secret in ("Jane Doe", "jane@x.gov.uk", "0123"):
            self.assertNotIn(secret, text)


if __name__ == "__main__":
    unittest.main()
