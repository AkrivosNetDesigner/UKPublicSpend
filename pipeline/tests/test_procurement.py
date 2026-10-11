import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import procurement as P  # noqa: E402


def rec(i=0, av=100_000, pm="selective", pmd="Open procedure", buyer="Test Council", sup="Acme Ltd", scheme="GB-COH", sid="00000001",
        pub="2026-03-10", aw="2026-03-01", cs="2026-04-01", ce="2028-04-01", tv=None, title="Widgets", **kw):
    r = {"id": f"a{i}", "ocid": f"o{i}", "tag": ["award"], "pub": pub, "aw": aw, "buyer": buyer, "buyer_id": "B1", "title": title, "cpv": "30000000",
         "cpvd": "Office machinery", "cat": "goods", "pm": pm, "pmd": pmd, "tv": tv, "tmin": None, "av": av, "cur": "GBP",
         "sups": [{"name": sup, "scheme": scheme, "id": sid, "scale": "sme"}], "sme": True, "vcse": False, "cs": cs, "ce": ce, "te": "", "url": "https://x/y"}
    r.update(kw)
    return r


class Classification(unittest.TestCase):
    def test_method_classes(self):
        cases = [("selective", "Call-off from a framework agreement", "framework"), ("direct", "Direct award", "direct"),
                 (None, "Single tender action (below threshold)", "direct"), (None, "Other - Waiver", "direct"),
                 ("open", "Open procedure (above threshold)", "competitive"), (None, "Competitive quotation (below threshold)", "competitive"),
                 (None, "Not specified", "unspecified"), (None, "Other - Not Specified", "unspecified"), (None, "Other - ", "unspecified"),
                 (None, "Other - Direct Award via Framework", "framework"), ("selective", "Something unusual", "other")]
        for pm, pmd, want in cases:
            self.assertEqual(P.method_class(pm, pmd), want, (pm, pmd))

    def test_supplier_naming_privacy(self):
        self.assertTrue(P.is_organisation({"name": "Acme Ltd"}))
        self.assertTrue(P.is_organisation({"name": "Jane Q Public", "scheme": "GB-COH", "id": "1"}))   # has a registration
        self.assertFalse(P.is_organisation({"name": "Jane Q Public"}))                                    # an individual: never named
        self.assertEqual(P.norm_name("ACME Limited."), P.norm_name("Acme Ltd"))

    def test_individual_supplier_never_in_output(self):
        rows = [rec(i, sup="Jane Q Public", scheme=None, sid=None, av=2_000_000, pm="direct", pmd="Direct award") for i in range(3)]
        out, _ = P.build(rows)
        text = repr(out)
        self.assertNotIn("Jane Q Public", text)


class Prepare(unittest.TestCase):
    def test_amendments_to_older_awards_are_not_analysed(self):
        new = rec(1, pub="2026-04-10", rel="2026-04-10")
        old_amended = rec(2, pub="2023-05-02", rel="2026-04-20", av=9_999_999)       # an old award amended in the window
        later = rec(3, pub="2026-05-12", rel="2026-05-12")
        rows, ex = P.prepare([new, old_amended, later])
        self.assertEqual(sorted(r["id"] for r in rows), ["a1", "a3"])
        self.assertEqual(ex["amendments to awards first published before the window"], 1)

    def test_dedupe_keeps_newest_and_excludes_unvalued(self):
        a = rec(1, av=100, pub="2026-01-01")
        b = dict(a, av=500, pub="2026-02-01")        # an update of the same award
        c = rec(2, av=None)
        rows, ex = P.prepare([a, b, c])
        self.assertEqual([r["av"] for r in rows], [500])
        self.assertEqual(ex["no value"], 1)


class Flags(unittest.TestCase):
    def flags(self, *rows):
        prepared, _ = P.prepare(list(rows))
        return P.record_flags(prepared)

    def test_direct_award_severity_by_size(self):
        fl = self.flags(rec(1, av=300_000, pm="direct", pmd="Direct award"), rec(2, av=6_000_000, pm="direct", pmd="Direct award"),
                        rec(3, av=6_000_000), rec(4, av=100_000, pm="direct", pmd="Direct award"))
        by = {f["value"]: f["sev"] for f in fl if f["type"] == "proc_direct"}
        self.assertEqual(by, {300_000: 1, 6_000_000: 3})      # competitive and small awards are ignored

    def test_late_publication(self):
        fl = self.flags(rec(1, av=500_000, pub="2026-09-01", aw="2026-01-01"), rec(2, av=500_000, pub="2026-03-10", aw="2026-03-01"))
        self.assertEqual([f["type"] for f in fl if f["type"] == "proc_late"], ["proc_late"])

    def test_estimate_ratio(self):
        fl = self.flags(rec(1, av=3_000_000, tv=500_000), rec(2, av=520_000, tv=500_000))
        self.assertEqual([f["value"] for f in fl if f["type"] == "proc_estimate"], [3_000_000])

    def test_repeat_awards_exclude_frameworks(self):
        rows = [rec(i, av=80_000, aw=f"2026-03-{i+1:02d}") for i in range(4)]
        prepared, _ = P.prepare(rows)
        self.assertEqual(len(P.repeat_award_flags(prepared)), 1)
        fw = [rec(i, av=80_000, aw=f"2026-03-{i+1:02d}", pmd="Call-off from a framework agreement") for i in range(4)]
        prepared, _ = P.prepare(fw)
        self.assertEqual(P.repeat_award_flags(prepared), [])


class Buyers(unittest.TestCase):
    def test_concentration_and_unspecified(self):
        rows = [rec(i, av=1_000_000, sup="BigCo Ltd", sid="1") for i in range(15)] + [rec(100 + i, av=100_000, sup=f"Other{i} Ltd", sid=str(10 + i), pm=None, pmd="Not specified") for i in range(10)]
        prepared, _ = P.prepare(rows)
        _, fl = P.buyer_table(prepared)
        types = {f["type"] for f in fl}
        self.assertIn("proc_conc", types)
        self.assertIn("proc_unspec", types)      # 10 of 25 notices (40%) do not state the procedure


class Bunching(unittest.TestCase):
    def test_detects_excess_just_below_threshold(self):
        random.seed(2)
        rows = [rec(i, av=random.uniform(20_000, 400_000)) for i in range(4000)]
        rows += [rec(10_000 + i, av=random.uniform(94_500, 99_900)) for i in range(250)]      # a pile just under £100k
        prepared, _ = P.prepare(rows)
        res = {b["threshold"]: b for b in P.bunching(prepared)}
        self.assertTrue(res[100_000]["flag"])
        self.assertFalse(res.get(200_000, {"flag": False})["flag"])

class Implausible(unittest.TestCase):
    def test_huge_value_flagged_and_left_out_of_totals(self):
        recs = [rec(1, av=200_000_000_000), rec(2, av=50_000)]
        out, _ = P.build(recs)
        self.assertEqual(out["summary"]["total_value"], 50_000)
        self.assertEqual(out["summary"]["quality"]["excluded"]["value of £10bn or more (looks like a data-entry error)"], 1)
        self.assertIn("proc_implausible", out["flag_counts"])


class FindTenderRecords(unittest.TestCase):
    def test_late_test_is_not_applied_to_find_a_tender(self):
        recs = [rec(1, av=500_000, aw="2025-01-01", pub="2026-03-10", src="fts"), rec(2, av=500_000, aw="2025-01-01", pub="2026-03-10")]
        out, _ = P.build(recs)
        late = [f for f in out["flags"] if f["type"] == "proc_late"]
        self.assertEqual(len(late), 1)

    def test_reason_for_direct_award_appears_in_flag(self):
        out, _ = P.build([rec(1, av=2_000_000, pm="limited", pmd="Award procedure without prior publication of a call for competition", why="extreme urgency", src="fts")])
        d = [f for f in out["flags"] if f["type"] == "proc_direct"][0]
        self.assertIn("extreme urgency", d["detail"])


if __name__ == "__main__":
    unittest.main()
