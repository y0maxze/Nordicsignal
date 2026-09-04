import unittest
from unittest.mock import patch

import opportunity_benchmark_evidence_runtime as evidence


class OpportunityBenchmarkEvidenceTests(unittest.TestCase):
    def tearDown(self):
        evidence._reset_benchmark_cache_for_tests()

    def test_stats_reports_excess_edge(self):
        result = evidence._stats([2.0, -1.0, 3.0, 1.0])
        self.assertEqual(result["n"], 4)
        self.assertEqual(result["mean_excess_return_pct"], 1.25)
        self.assertEqual(result["median_excess_return_pct"], 1.5)
        self.assertEqual(result["outperformance_rate_pct"], 75.0)
        self.assertEqual(result["evidence_status"], "insufficient")

    def test_stats_maturity_gate(self):
        self.assertEqual(evidence._stats([1.0] * 8)["evidence_status"], "early")
        self.assertEqual(evidence._stats([1.0] * 20)["evidence_status"], "usable")

    def test_benchmark_history_is_reused_within_ttl(self):
        rows = [{"date": "2026-09-01", "close": 100.0}]
        with patch.object(evidence, "_load_benchmark_rows", return_value=rows) as loader:
            first = evidence._benchmark_rows()
            second = evidence._benchmark_rows()
        self.assertIs(first, second)
        loader.assert_called_once_with()

    def test_force_refresh_bypasses_cache(self):
        with patch.object(evidence, "_load_benchmark_rows", side_effect=[
            [{"date": "2026-09-01", "close": 100.0}],
            [{"date": "2026-09-02", "close": 101.0}],
        ]) as loader:
            evidence._benchmark_rows()
            result = evidence._benchmark_rows(force=True)
        self.assertEqual(result[0]["date"], "2026-09-02")
        self.assertEqual(loader.call_count, 2)


if __name__ == "__main__":
    unittest.main()
