import unittest
from unittest.mock import patch

import opportunity_shadow_quality_runtime as quality


def _dataset(days=40, tickers=24, complete=True, context=True, settled=True):
    snapshots = []
    returns = []
    sid = 1
    dates = [f"2026-07-{day:02d}" if day <= 31 else f"2026-08-{day-31:02d}" for day in range(1, days + 1)]
    for date_index, market_date in enumerate(dates):
        for ticker_index in range(tickers):
            row = {
                "id": sid,
                "ticker": f"T{ticker_index:02d}",
                "market_date": market_date,
                "entry_price": 100.0 if complete else None,
                "opportunity_score": 30.0 if complete else None,
                "reversal_score": 45.0 if complete else None,
                "volume_state": "NORMAL" if complete else "",
                "insider_label": "NONE" if complete else "",
                "market_regime": "NEUTRAL" if context else None,
            }
            snapshots.append(row)
            if settled:
                for horizon in quality.REQUIRED_RETURN_HORIZONS:
                    if date_index + horizon < days:
                        returns.append({"snapshot_id": sid, "horizon_days": horizon})
            sid += 1
    return snapshots, returns


class ShadowQualityGateTests(unittest.TestCase):
    def _run(self, snapshots, returns, active=24, duplicates=0):
        with patch.object(quality.identity_runtime, "_current_identity", return_value={"signal_model_id": "model-test"}), patch.object(
            quality, "_rows", return_value=(snapshots, returns, active, duplicates)
        ):
            return quality.quality_gate()

    def test_complete_dataset_passes(self):
        snapshots, returns = _dataset()
        gate = self._run(snapshots, returns)
        self.assertEqual(gate["status"], "PASS")
        self.assertTrue(gate["ready_for_counterfactual_research"])
        self.assertTrue(all(gate["checks"].values()))
        self.assertEqual(gate["forward_returns"]["20"]["coverage_pct"], 100.0)

    def test_too_little_history_collects(self):
        snapshots, returns = _dataset(days=20)
        gate = self._run(snapshots, returns)
        self.assertEqual(gate["status"], "COLLECTING_DATA")
        self.assertFalse(gate["checks"]["minimum_market_days"])
        self.assertFalse(gate["ready_for_counterfactual_research"])

    def test_partial_universe_fails_coverage(self):
        snapshots, returns = _dataset(tickers=12)
        gate = self._run(snapshots, returns, active=24)
        self.assertEqual(gate["status"], "REVIEW")
        self.assertFalse(gate["checks"]["daily_universe_coverage"])

    def test_missing_features_and_context_fail(self):
        snapshots, returns = _dataset(complete=False, context=False)
        gate = self._run(snapshots, returns)
        self.assertFalse(gate["checks"]["feature_completeness"])
        self.assertFalse(gate["checks"]["market_context_coverage"])
        self.assertFalse(gate["ready_for_counterfactual_research"])

    def test_missing_matured_returns_fail(self):
        snapshots, _ = _dataset(settled=False)
        gate = self._run(snapshots, [])
        self.assertFalse(gate["checks"]["matured_forward_return_coverage"])
        self.assertEqual(gate["forward_returns"]["5"]["coverage_pct"], 0.0)

    def test_duplicate_groups_fail_even_if_other_checks_pass(self):
        snapshots, returns = _dataset()
        gate = self._run(snapshots, returns, duplicates=1)
        self.assertFalse(gate["checks"]["no_duplicate_snapshot_groups"])
        self.assertFalse(gate["ready_for_counterfactual_research"])


if __name__ == "__main__":
    unittest.main()
