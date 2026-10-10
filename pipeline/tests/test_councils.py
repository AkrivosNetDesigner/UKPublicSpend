import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import councils as C  # noqa: E402


def row(year, code, name, cls, tot, status="submitted", **extra):
    v = {k: None for k in ["totsx", "netrev", "resunall", "resoth", "resoth_adj", "resdsg", "resdsgadj", "intpay", "intinc", "invcost", "invinc"] + [s[0] for s in C.SERVICES]}
    v.update({"totsx": tot, "netrev": tot, "asc": tot}, **extra)
    return {"year": year, "code": code, "name": name, "cls": cls, "status": status, "v": v}


class Councils(unittest.TestCase):
    def test_fy_label(self):
        self.assertEqual(C.fy_label("202503"), "2024-25")

    def test_peer_year_needs_most_councils_submitted(self):
        rows = [row("2024-25", f"E06{i}", "x", "Unitary Authority", 1) for i in range(10)]
        rows += [row("2025-26", f"E06{i}", "x", "Unitary Authority", 1, status="submitted" if i < 5 else "not submitted") for i in range(10)]
        self.assertEqual(C.peer_year(rows), "2024-25")

    def test_outlier_and_missing_flagged(self):
        rows, pop = [], {}
        for i in range(30):
            code = f"E060{i:05d}"
            tot = 50e6 / 1000 * (6 if i == 0 else 1)
            rows.append(row("2024-25", code, f"C{i}", "Unitary Authority", tot, asc=tot))
            pop[code] = {"name": f"C{i}", "pop": 100000, "age0_17": 20000, "age65": 20000}
        rows.append(row("2024-25", "E06X", "Gone", "Unitary Authority", 0, status="not submitted"))
        rows.append(row("2025-26", "E06X", "Gone", "Unitary Authority", 0, status="not submitted"))
        rows += [row("2025-26", f"E060{i:05d}", f"C{i}", "Unitary Authority", 50e3) for i in range(30)]
        _, _, py, _, _, flags = C.build(rows, pop)
        types = {(f["type"], f["council"]) for f in flags}
        self.assertEqual(py, "2025-26")
        self.assertIn(("lc_missing", "Gone"), types)

    def test_council_with_no_row_this_year_counts_as_not_submitted(self):
        rows = [row(y, f"E06{i}", f"C{i}", "Unitary Authority", 1) for y in ("2023-24", "2024-25") for i in range(10)]
        rows += [row("2024-25", f"E06{i}", f"C{i}", "Unitary Authority", 1) for i in range(0)]
        rows = [r for r in rows if not (r["year"] == "2024-25" and r["code"] == "E069")]
        cs, _, py, *_ = C.build(rows, {})
        self.assertEqual(cs["E069"]["missing"], ["2024-25"])

    def test_checks_service_sum(self):
        rows = [row("2024-25", "E06A", "A", "Unitary Authority", 100, asc=60)]
        cks = C.checks(rows, {}, {})
        svc = next(c for c in cks if c["id"] == "lc_services")
        self.assertEqual(svc["status"], "warn")
        self.assertEqual(svc["source"], "Local councils")


if __name__ == "__main__":
    unittest.main()
