import unittest

import opportunity_edge_summary_runtime as summary


class OpportunityEdgeSummaryTests(unittest.TestCase):
    def test_horizon_row_combines_absolute_edge_and_risk(self):
        result = {
            "horizons": {"20": {"n": 25, "mean_return_pct": 4.2, "median_return_pct": 3.1, "positive_rate_pct": 68.0}},
            "risk_path": {"horizons": {"20": {"n": 25, "median_max_drawdown_pct": -2.3, "worst_max_drawdown_pct": -8.0, "median_max_runup_pct": 6.4, "best_max_runup_pct": 18.0}}},
            "benchmark_edge": {"horizons": {"20": {"n": 25, "mean_excess_return_pct": 2.0, "median_excess_return_pct": 1.6, "outperformance_rate_pct": 64.0, "evidence_status": "usable"}}},
        }
        row = summary._horizon_row(result, 20)
        self.assertEqual(row["n"], 25)
        self.assertEqual(row["median_return_pct"], 3.1)
        self.assertEqual(row["median_excess_return_pct"], 1.6)
        self.assertEqual(row["median_max_drawdown_pct"], -2.3)
        self.assertEqual(row["evidence_status"], "usable")


if __name__ == "__main__":
    unittest.main()
