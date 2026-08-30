import unittest
from unittest.mock import patch

import opportunity_shadow_dataset_runtime as shadow


class _ExistingConnection:
    def __init__(self, row=None):
        self.row = row
        self.queries = []

    def execute(self, sql, params=()):
        self.queries.append((sql, params))
        return self

    def fetchone(self):
        return self.row

    def close(self):
        pass


class OpportunityShadowDatasetTests(unittest.TestCase):
    def _result(self, label="NO_OPPORTUNITY"):
        return {
            "status": "ok",
            "ticker": "TEST",
            "generated_at": "2026-08-30T07:00:00+00:00",
            "reversal": {
                "score": 58.0,
                "regime": "BOTTOMING",
                "metrics": {"close": 100.0, "close_date": "2026-08-29"},
            },
            "opportunity": {
                "label": label,
                "score": 19.0,
                "confidence": "low",
                "components": {
                    "reversal_score": 58.0,
                    "reversal_regime": "BOTTOMING",
                    "volume_ratio": 1.2,
                    "volume_state": "NONE",
                    "insider_label": "POSITIVE",
                    "insider_points": 12.0,
                    "independent_buyers": 3,
                    "buy_value_nok": 250000.0,
                    "evidence_count": 1,
                },
            },
        }

    def test_market_date_uses_observed_trading_close_date(self):
        self.assertEqual(shadow._market_date(self._result()), "2026-08-29")

    def test_feature_snapshot_preserves_no_opportunity_and_raw_components(self):
        identity = {
            "signal_model_id": "model:test",
            "signal_version": "v-test",
            "learning_policy_id": "policy:test",
        }
        context = {
            "benchmark_entry_date": "2026-08-29",
            "benchmark_entry_close": 1000.0,
            "regime_asof_date": "2026-08-28",
            "regime": "NEUTRAL",
            "benchmark_ret20_pct": 0.5,
            "benchmark_ma50_gap_pct": -0.2,
        }
        with patch.object(shadow.tracking, "_stock_name", return_value="Test ASA"):
            item = shadow._feature_snapshot(self._result(), identity, "^OSEBX", context)

        self.assertEqual(item["opportunity_label"], "NO_OPPORTUNITY")
        self.assertEqual(item["signal_model_id"], "model:test")
        self.assertEqual(item["market_date"], "2026-08-29")
        self.assertEqual(item["entry_price"], 100.0)
        self.assertEqual(item["reversal_score"], 58.0)
        self.assertEqual(item["volume_ratio"], 1.2)
        self.assertEqual(item["insider_label"], "POSITIVE")
        self.assertEqual(item["independent_buyers"], 3)
        self.assertEqual(item["market_regime"], "NEUTRAL")

    def test_existing_daily_snapshot_is_reused_before_benchmark_lookup(self):
        connection = _ExistingConnection({"id": 42})
        identity = {"signal_model_id": "model:test"}
        with patch.object(shadow.identity_runtime, "_current_identity", return_value=identity), \
             patch.object(shadow.tracking, "connect", return_value=connection), \
             patch.object(shadow, "_context_for_result", side_effect=AssertionError("benchmark should not be queried")):
            result = shadow.capture_snapshot(self._result())

        self.assertFalse(result["captured"])
        self.assertEqual(result["reason"], "already_captured")
        self.assertEqual(result["snapshot_id"], 42)

    def test_forward_measurements_compute_raw_return_and_osebx_alpha(self):
        stock_rows = [
            {"date": f"2026-01-{day:02d}", "close": 100.0 + day - 1}
            for day in range(1, 32)
        ] + [
            {"date": f"2026-02-{day:02d}", "close": 131.0 + day - 1}
            for day in range(1, 30)
        ]
        benchmark_rows = [
            {"date": f"2026-01-{day:02d}", "close": 1000.0 + 2.0 * (day - 1)}
            for day in range(1, 32)
        ] + [
            {"date": f"2026-02-{day:02d}", "close": 1062.0 + 2.0 * (day - 1)}
            for day in range(1, 30)
        ]
        snapshot = {
            "market_date": "2026-01-01",
            "entry_price": 100.0,
            "benchmark_entry_close": 1000.0,
        }
        rows = shadow._forward_measurements(snapshot, stock_rows, benchmark_rows, horizons=(5, 10, 20))
        by_horizon = {row["horizon_days"]: row for row in rows}

        self.assertEqual(set(by_horizon), {5, 10, 20})
        self.assertAlmostEqual(by_horizon[5]["return_pct"], 5.0, places=6)
        self.assertAlmostEqual(by_horizon[5]["benchmark_return_pct"], 1.0, places=6)
        self.assertAlmostEqual(by_horizon[5]["excess_return_pct"], 4.0, places=6)
        self.assertAlmostEqual(by_horizon[10]["return_pct"], 10.0, places=6)
        self.assertAlmostEqual(by_horizon[10]["benchmark_return_pct"], 2.0, places=6)
        self.assertAlmostEqual(by_horizon[10]["excess_return_pct"], 8.0, places=6)

    def test_settle_wrapper_reuses_supplied_stock_history(self):
        supplied = [{"date": "2026-01-01", "close": 100.0}]
        seen = {}

        def fake_event_settle(ticker, rows=None):
            seen["event_rows"] = rows
            return 7

        def fake_shadow_settle(ticker, rows=None):
            seen["shadow_rows"] = rows
            return 3

        with patch.object(shadow, "_BASE_SETTLE", side_effect=fake_event_settle), \
             patch.object(shadow, "settle_shadow_returns", side_effect=fake_shadow_settle), \
             patch.object(shadow.tracking, "_history", side_effect=AssertionError("history should not be refetched")):
            count = shadow._settle_with_shadow("TEST", supplied)

        self.assertEqual(count, 7)
        self.assertIs(seen["event_rows"], supplied)
        self.assertIs(seen["shadow_rows"], supplied)


if __name__ == "__main__":
    unittest.main()
