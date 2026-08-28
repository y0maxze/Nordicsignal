import unittest

from signal_evidence_runtime import summarize_samples, backtest_history


class SignalEvidenceRuntimeTests(unittest.TestCase):
    def test_summary_reports_directional_hit_rate(self):
        samples = [
            {"event":"Trend snur opp","direction":"up","forward_return_pct":{"5":2.0,"20":5.0,"60":8.0}},
            {"event":"Trend snur opp","direction":"up","forward_return_pct":{"5":-1.0,"20":3.0,"60":4.0}},
            {"event":"Trend snur ned","direction":"down","forward_return_pct":{"5":-2.0,"20":-4.0,"60":-6.0}},
            {"event":"Trend snur ned","direction":"down","forward_return_pct":{"5":1.0,"20":-1.0,"60":2.0}},
        ]
        result = summarize_samples(samples)
        self.assertEqual(result["sample_count"], 4)
        self.assertEqual(result["maturity"], "insufficient")
        self.assertEqual(result["overall"]["horizons"]["5"]["directional_hit_rate_pct"], 50.0)
        self.assertEqual(result["overall"]["horizons"]["20"]["directional_hit_rate_pct"], 100.0)
        self.assertEqual(len(result["by_event"]), 2)

    def test_backtest_does_not_require_future_rows_for_last_observation(self):
        rows = []
        # Stable baseline, then a decisive upward turn with volume expansion.
        for i in range(120):
            if i < 70:
                close = 100 - i * 0.08
            else:
                close = 94.4 + (i - 70) * 0.45
            volume = 1000
            if i in (70, 71, 72, 73, 74):
                volume = 2600
            rows.append({"timestamp": i + 1, "date": f"2026-01-{(i % 28) + 1:02d}T00:00:00+00:00", "close": close, "volume": volume})
        samples = backtest_history(rows)
        self.assertIsInstance(samples, list)
        for sample in samples:
            self.assertIn(sample["direction"], ("up", "down", "neutral"))
            self.assertIn("5", sample["forward_return_pct"])
            self.assertIn("20", sample["forward_return_pct"])
            self.assertIn("60", sample["forward_return_pct"])


if __name__ == "__main__":
    unittest.main()
