import unittest

import opportunity_benchmark_evidence_runtime as evidence


class OpportunityBenchmarkEvidenceTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
