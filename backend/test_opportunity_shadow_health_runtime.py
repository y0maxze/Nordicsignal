import unittest
from unittest.mock import patch

import opportunity_shadow_health_runtime as shadow_health


class ShadowPipelineHealthTests(unittest.TestCase):
    def _status(self, *, snapshots=240, latest_pct=100.0, feature_pct=100.0, context_pct=100.0, duplicates=0, research_status="COLLECTING_DATA"):
        return {
            "active_model_snapshots": snapshots,
            "active_model_tickers": 24 if snapshots else 0,
            "first_market_date": "2026-08-01" if snapshots else None,
            "last_market_date": "2026-08-10" if snapshots else None,
            "quality_gate": {
                "status": research_status,
                "ready_for_counterfactual_research": research_status == "PASS",
                "duplicate_snapshot_groups": duplicates,
                "feature_completeness_pct": feature_pct,
                "market_context_coverage_pct": context_pct,
                "thresholds": {
                    "daily_universe_coverage_pct": 90.0,
                    "feature_completeness_pct": 98.0,
                    "market_context_coverage_pct": 95.0,
                },
                "daily_coverage": ([{"market_date":"2026-08-10","tickers":24,"coverage_pct":latest_pct}] if snapshots else []),
            },
        }

    def test_collecting_research_can_be_operationally_healthy(self):
        with patch.object(shadow_health.shadow, "shadow_status", return_value=self._status(research_status="COLLECTING_DATA")):
            check = shadow_health.shadow_collection_check()
        self.assertEqual(check["status"], "PASS")
        self.assertEqual(check["research_quality_status"], "COLLECTING_DATA")
        self.assertFalse(check["research_ready"])

    def test_low_latest_universe_coverage_warns(self):
        with patch.object(shadow_health.shadow, "shadow_status", return_value=self._status(latest_pct=50.0)):
            check = shadow_health.shadow_collection_check()
        self.assertEqual(check["status"], "WARN")
        self.assertFalse(check["checks"]["latest_universe_coverage"])

    def test_missing_features_or_context_warns(self):
        with patch.object(shadow_health.shadow, "shadow_status", return_value=self._status(feature_pct=90.0, context_pct=80.0)):
            check = shadow_health.shadow_collection_check()
        self.assertEqual(check["status"], "WARN")
        self.assertFalse(check["checks"]["feature_completeness"])
        self.assertFalse(check["checks"]["market_context_coverage"])

    def test_duplicate_groups_fail(self):
        with patch.object(shadow_health.shadow, "shadow_status", return_value=self._status(duplicates=1)):
            check = shadow_health.shadow_collection_check()
        self.assertEqual(check["status"], "FAIL")
        self.assertFalse(check["checks"]["no_duplicate_groups"])

    def test_no_snapshots_warns_but_does_not_fake_research_failure(self):
        with patch.object(shadow_health.shadow, "shadow_status", return_value=self._status(snapshots=0)):
            check = shadow_health.shadow_collection_check()
        self.assertEqual(check["status"], "WARN")
        self.assertFalse(check["checks"]["has_snapshots"])


if __name__ == "__main__":
    unittest.main()
