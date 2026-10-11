import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import fetch_find_tender as F  # noqa: E402


def release(pmd="Open procedure", pm="open", rationale_ids=(), text="", value=100000):
    return {"ocid": "ocds-h6vhtk-1", "id": "000001-2026", "date": "2026-10-01T10:00:00+01:00", "tag": ["award"], "description": text,
            "tender": {"title": "Works", "procurementMethod": pm, "procurementMethodDetails": pmd, "procurementMethodRationale": text,
                       "procurementMethodRationaleClassifications": [{"id": i} for i in rationale_ids], "mainProcurementCategory": "works"},
            "buyer": {"id": "GB-FTS-1", "name": "Test Council"},
            "awards": [{"id": "000001-2026-1", "suppliers": [{"id": "GB-COH-1", "name": "Acme Ltd"}]}],
            "contracts": [{"awardID": "000001-2026-1", "value": {"amount": value, "currency": "GBP"}, "dateSigned": "2026-09-01T00:00:00+01:00"}],
            "parties": [{"id": "GB-COH-1", "name": "Acme Ltd", "identifier": {"scheme": "GB-COH", "id": "1"}, "details": {"scale": "sme"}}]}


class FindTender(unittest.TestCase):
    def test_open_procedure_unchanged(self):
        r = F.compact(release())[0]
        self.assertEqual((r["pmd"], r["av"], r["src"], r["aw"]), ("Open procedure", 100000, "fts", "2026-09-01"))

    def test_outside_scope_with_framework_is_a_call_off_not_a_direct_award(self):
        r = F.compact(release(F.NO_CALL, "limited", [F.OUTSIDE], "Procured using the G-Cloud 14 Framework Agreement"))[0]
        self.assertEqual(r["pmd"], "Call-off from a framework agreement")

    def test_outside_scope_without_framework_is_not_direct(self):
        r = F.compact(release(F.NO_CALL, "limited", [F.OUTSIDE]))[0]
        self.assertNotIn("without prior publication", r["pmd"].lower())

    def test_real_direct_award_keeps_reason(self):
        r = F.compact(release(F.NO_CALL, "limited", ["D_EXTREME_URGENCY"]))[0]
        self.assertEqual((r["pmd"], r["why"]), (F.NO_CALL, "extreme urgency"))

    def test_contact_people_are_not_kept(self):
        rel = release()
        rel["parties"][0]["contactPoint"] = {"name": "Private Person", "email": "p@example.org"}
        self.assertNotIn("Private Person", str(F.compact(rel)))

    def test_dedupe_keeps_latest_version(self):
        import json
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "c.jsonl"
            p.write_text(json.dumps({"id": "a", "rel": "2026-01-01", "av": 1}) + "\n" + json.dumps({"id": "a", "rel": "2026-02-01", "av": 2}) + "\n")
            self.assertEqual(F.dedupe(p), 1)
            self.assertEqual(json.loads(p.read_text())["av"], 2)


if __name__ == "__main__":
    unittest.main()
