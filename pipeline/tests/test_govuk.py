import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import govuk as G  # noqa: E402

DOC = {"title": "Tables", "details": {"attachments": [
    {"title": "Detailed local authority level tables: financial year 2023-24 (revised)", "url": "https://x/a.ods"},
    {"title": "Detailed local authority level tables: financial year 2024-25", "url": "https://x/b.ods"},
    {"title": "Table P151: speed", "url": "https://x/p151.ods"},
    {"title": "Main findings", "url": "/government/statistics/x"}]}}


class Govuk(unittest.TestCase):
    def test_pick_first_match(self):
        self.assertEqual(G.pick(DOC, r"^Table P151"), "https://x/p151.ods")

    def test_pick_newest_financial_year(self):
        self.assertEqual(G.pick(DOC, r"financial year", G.fy_key), "https://x/b.ods")

    def test_internal_links_are_not_files(self):
        self.assertEqual([u for _, u in G.attachments(DOC)].count("/government/statistics/x"), 0)

    def test_missing_raises(self):
        with self.assertRaises(LookupError):
            G.pick(DOC, r"nonexistent")

    def test_latest_document(self):
        col = {"links": {"documents": [{"title": "Fostering in England 2025", "base_path": "/a"}, {"title": "Local authority inspection outcomes as at 31 March 2026", "base_path": "/b"}]}}
        self.assertEqual(G.latest_document(col, r"inspection outcomes"), "/b")


if __name__ == "__main__":
    unittest.main()
