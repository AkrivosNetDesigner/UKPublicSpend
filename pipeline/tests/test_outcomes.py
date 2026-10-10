import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import outcomes as O  # noqa: E402


class Stats(unittest.TestCase):
    def test_rank_ties(self):
        self.assertEqual(O.rank([10, 20, 20, 30]), [1.0, 2.5, 2.5, 4.0])

    def test_spearman_monotonic(self):
        self.assertAlmostEqual(O.spearman([1, 2, 3, 4, 5], [1, 4, 9, 16, 100]), 1.0)
        self.assertAlmostEqual(O.spearman([1, 2, 3, 4, 5], [5, 4, 3, 2, 1]), -1.0)

    def test_residuals_remove_linear_effect(self):
        x = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]
        y = [2 * v + 1 for v in x]
        self.assertTrue(all(abs(r) < 1e-9 for r in O.residuals_multi(y, [x])))

    def test_confounder_explains_correlation(self):
        # spend and result both just follow a third factor; once it is allowed for there is no relationship left
        c = [float(i) for i in range(1, 41)]
        noise = [((i * 7919) % 13) - 6 for i in range(40)]
        noise2 = [((i * 104729) % 11) - 5 for i in range(40)]
        a = [v + 0.3 * n for v, n in zip(c, noise)]
        b = [v + 0.3 * n for v, n in zip(c, noise2)]
        self.assertGreater(O.spearman(a, b), 0.9)
        self.assertLess(abs(O.partial_spearman(a, b, [c])), 0.35)

    def test_analyse_needs_enough_councils(self):
        pts = [{"code": f"E{i}", "name": f"C{i}", "x": float(i), "y": float(i), "imd": 1.0} for i in range(5)]
        self.assertIsNone(O.analyse(pts, 1))

    def test_analyse_flags_high_spend_poor_result(self):
        import random
        random.seed(3)
        pts = [{"code": f"E{i}", "name": f"C{i}", "x": random.random() * 100, "y": random.random() * 100, "imd": random.random() * 50} for i in range(60)]
        pts.append({"code": "Eodd", "name": "Odd", "x": 1000.0, "y": 0.0, "imd": 25.0})
        res, _ = O.analyse(pts, 1)
        self.assertIn("Odd", [p["name"] for p in res["high_spend_poor"]])


if __name__ == "__main__":
    unittest.main()
