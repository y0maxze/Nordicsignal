import unittest

import opportunity_statistical_confidence_runtime as confidence
import opportunity_statistical_gate_runtime as gate_runtime


class OpportunityStatisticalConfidenceTests(unittest.TestCase):
    def test_wilson_95_lower_bound_rejects_14_of_20_but_accepts_15(self):
        weak = confidence._wilson_interval(14, 20)
        stronger = confidence._wilson_interval(15, 20)
        self.assertLess(weak["lower_pct"], 50.0)
        self.assertGreater(stronger["lower_pct"], 50.0)

    def test_exact_median_interval_requires_more_than_15_of_20_positive(self):
        fifteen_positive = [-2.0] * 5 + [1.0] * 15
        sixteen_positive = [-2.0] * 4 + [1.0] * 16
        weak = confidence._median_interval(fifteen_positive)
        strong = confidence._median_interval(sixteen_positive)
        self.assertLessEqual(weak["lower"], 0.0)
        self.assertGreater(strong["lower"], 0.0)
        self.assertGreaterEqual(strong["coverage"], 0.95)

    def test_gate_requires_two_horizons_with_raw_and_alpha_support(self):
        rows = []
        for horizon in (5, 10):
            for index in range(20):
                value = -1.0 if index < 4 else 2.0
                alpha = -0.5 if index < 4 else 1.0
                rows.append({"horizon_days": horizon, "return_pct": value, "excess_return_pct": alpha})
        for index in range(20):
            value = -1.0 if index < 8 else 2.0
            rows.append({"horizon_days": 20, "return_pct": value, "excess_return_pct": value})

        result = confidence.confidence_gate(rows, (5, 10, 20), 20)
        self.assertTrue(result["ready"])
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["passing_horizons"], [5, 10])
        self.assertTrue(result["horizons"]["5"]["raw_return"]["direction_supported"])
        self.assertTrue(result["horizons"]["5"]["market_adjusted_alpha"]["direction_supported"])
        self.assertEqual(result["horizons"]["20"]["status"], "REVIEW")

    def test_strong_raw_return_does_not_pass_when_alpha_is_uncertain(self):
        rows = []
        for horizon in (5, 10, 20):
            for index in range(20):
                raw = -1.0 if index < 2 else 2.0
                alpha = -1.0 if index < 10 else 1.0
                rows.append({"horizon_days": horizon, "return_pct": raw, "excess_return_pct": alpha})

        result = confidence.confidence_gate(rows, (5, 10, 20), 20)
        self.assertFalse(result["ready"])
        self.assertEqual(result["passing_horizons"], [])
        self.assertTrue(result["horizons"]["5"]["raw_return"]["direction_supported"])
        self.assertFalse(result["horizons"]["5"]["market_adjusted_alpha"]["direction_supported"])

    def test_learning_policy_changes_without_resetting_signal_model(self):
        previous = gate_runtime._BASE_IDENTITY()
        current = gate_runtime._current_identity()
        self.assertEqual(current["signal_model_id"], previous["signal_model_id"])
        self.assertNotEqual(current["learning_policy_id"], previous["learning_policy_id"])
        self.assertEqual(current["learning_policy_version"], gate_runtime.LEARNING_POLICY_VERSION)
        self.assertIn("statistical_confidence_policy", current["identity_scope"])


if __name__ == "__main__":
    unittest.main()
