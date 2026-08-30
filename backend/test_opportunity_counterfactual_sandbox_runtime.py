import unittest
from unittest.mock import patch

import opportunity_counterfactual_sandbox_runtime as sandbox


class CounterfactualSandboxTests(unittest.TestCase):
    def test_locked_gate_never_loads_research_rows(self):
        locked = {"status": "COLLECTING_DATA", "ready_for_counterfactual_research": False}
        with patch.object(sandbox.quality, "quality_gate", return_value=locked), patch.object(
            sandbox.identity_runtime, "_current_identity", return_value={"signal_model_id": "model-test"}
        ), patch.object(sandbox, "_load_rows") as load_rows:
            report = sandbox.sandbox_report()
        self.assertEqual(report["status"], "LOCKED")
        self.assertFalse(report["quality_gate_ready"])
        load_rows.assert_not_called()

    def test_open_sandbox_uses_later_chronological_holdout_and_fixed_order(self):
        gate = {"status": "PASS", "ready_for_counterfactual_research": True}
        snapshots = []
        returns = []
        for index in range(40):
            snapshot_id = index + 1
            market_date = f"2026-07-{index + 1:02d}" if index < 31 else f"2026-08-{index - 30:02d}"
            snapshots.append({
                "id": snapshot_id,
                "ticker": f"T{index:02d}",
                "market_date": market_date,
                "reversal_score": 80.0,
                "volume_ratio": 2.0,
                "insider_label": "STRONG",
            })
            for horizon in sandbox.HORIZONS:
                returns.append({
                    "snapshot_id": snapshot_id,
                    "horizon_days": horizon,
                    "return_pct": 2.0,
                    "excess_return_pct": 1.0,
                })
        with patch.object(sandbox.quality, "quality_gate", return_value=gate), patch.object(
            sandbox.identity_runtime, "_current_identity", return_value={"signal_model_id": "model-test"}
        ), patch.object(sandbox, "_load_rows", return_value=(snapshots, returns)):
            report = sandbox.sandbox_report()

        self.assertEqual(report["status"], "OPEN_RESEARCH_ONLY")
        self.assertLess(report["development_end"], report["holdout_start"])
        self.assertEqual(report["development_market_days"], 28)
        self.assertEqual(report["holdout_market_days"], 12)
        self.assertFalse(report["automatic_candidate_ranking"])
        self.assertFalse(report["automatic_threshold_changes"])
        self.assertEqual(
            [item["candidate"]["id"] for item in report["results"]],
            [item["id"] for item in sandbox.CANDIDATES],
        )
        baseline = report["results"][0]
        self.assertEqual(baseline["development_selected"], 28)
        self.assertEqual(baseline["holdout_selected"], 12)
        self.assertEqual(baseline["holdout"]["5"]["raw_return"]["median_pct"], 2.0)
        self.assertEqual(baseline["holdout"]["5"]["market_adjusted_alpha"]["median_pct"], 1.0)
        self.assertFalse(baseline["holdout"]["5"]["sample_sufficient"])

    def test_candidate_filters_are_pre_registered_and_not_runtime_parameters(self):
        ids = [candidate["id"] for candidate in sandbox.CANDIDATES]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(ids[0], "baseline_rev75_vol150")
        self.assertTrue(all("reversal_min" in candidate and "volume_min" in candidate for candidate in sandbox.CANDIDATES))


if __name__ == "__main__":
    unittest.main()
