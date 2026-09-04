import unittest

import opportunity_evidence_v3_runtime as evidence


class OpportunityEvidenceV3Tests(unittest.TestCase):
    def test_path_stats_reports_adverse_and_favorable_excursion(self):
        rows = [
            {"date":"2026-01-01","close":100.0},
            {"date":"2026-01-02","close":97.0},
            {"date":"2026-01-03","close":104.0},
            {"date":"2026-01-04","close":101.0},
            {"date":"2026-01-05","close":108.0},
            {"date":"2026-01-06","close":106.0},
        ]
        stats = evidence._path_stats(rows, 0, 5, 100.0)
        self.assertAlmostEqual(stats["max_drawdown_pct"], -3.0)
        self.assertAlmostEqual(stats["max_runup_pct"], 8.0)

    def test_path_stats_requires_mature_horizon(self):
        rows = [{"date":"2026-01-01","close":100.0}, {"date":"2026-01-02","close":101.0}]
        self.assertIsNone(evidence._path_stats(rows, 0, 5, 100.0))

    def test_risk_stats_uses_median_and_extremes(self):
        rows = [
            {"max_drawdown_pct":-2.0,"max_runup_pct":4.0},
            {"max_drawdown_pct":-5.0,"max_runup_pct":9.0},
            {"max_drawdown_pct":-1.0,"max_runup_pct":2.0},
        ]
        result = evidence._risk_stats(rows)
        self.assertEqual(result["n"], 3)
        self.assertEqual(result["median_max_drawdown_pct"], -2.0)
        self.assertEqual(result["worst_max_drawdown_pct"], -5.0)
        self.assertEqual(result["median_max_runup_pct"], 4.0)
        self.assertEqual(result["best_max_runup_pct"], 9.0)


if __name__ == "__main__":
    unittest.main()
