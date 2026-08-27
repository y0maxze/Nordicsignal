import unittest

from signal_events_runtime import (
    _trend_event_candidate,
    analyze_trend_activity,
    build_stock_events,
)


class SignalEventsRuntimeTests(unittest.TestCase):
    def test_latest_feed_contains_changes_not_current_ranking_duplicates(self):
        rows = [
            {"ticker": "AAA", "name": "Alpha", "sector": "Tech", "total": 82, "created_at": "2026-08-26T00:20:00+00:00", "source": "live"},
            {"ticker": "AAA", "name": "Alpha", "sector": "Tech", "total": 78, "created_at": "2026-08-26T00:10:00+00:00", "source": "live"},
            {"ticker": "BBB", "name": "Beta", "sector": "Energy", "total": 66, "created_at": "2026-08-26T00:19:00+00:00", "source": "live"},
            {"ticker": "BBB", "name": "Beta", "sector": "Energy", "total": 65, "created_at": "2026-08-26T00:09:00+00:00", "source": "live"},
            {"ticker": "CCC", "name": "Gamma", "sector": "Finance", "total": 70, "created_at": "2026-08-26T00:18:00+00:00", "source": "live"},
            {"ticker": "CCC", "name": "Gamma", "sector": "Finance", "total": 69, "created_at": "2026-08-26T00:08:00+00:00", "source": "live"},
        ]
        events = build_stock_events(rows)
        self.assertEqual([x["ticker"] for x in events], ["AAA", "CCC"])
        self.assertEqual(events[0]["previous_signal"], "Watch")
        self.assertEqual(events[0]["signal"], "Strong")
        self.assertEqual(events[0]["score_delta"], 4)
        self.assertEqual(events[1]["previous_signal"], "Neutral")
        self.assertEqual(events[1]["signal"], "Watch")
        self.assertEqual(events[1]["score_delta"], 1)
        self.assertTrue(all(x["event_type"] == "score_change" for x in events))

    def test_two_point_move_is_material_inside_same_band(self):
        rows = [
            {"ticker": "AAA", "name": "Alpha", "total": 67, "created_at": "2026-08-26T00:20:00+00:00"},
            {"ticker": "AAA", "name": "Alpha", "total": 65, "created_at": "2026-08-26T00:10:00+00:00"},
        ]
        events = build_stock_events(rows)
        self.assertEqual(len(events), 1)
        self.assertIn("2", events[0]["event"])

    @staticmethod
    def history(closes, last_volume=1000):
        rows = []
        for i, close in enumerate(closes):
            rows.append({
                "timestamp": 1_700_000_000 + i * 86400,
                "date": f"2026-08-{(i % 28) + 1:02d}T16:00:00+00:00",
                "close": close,
                "volume": last_volume if i == len(closes) - 1 else 1000,
            })
        return rows

    def test_upward_reversal_with_volume_is_combined_signal(self):
        closes = [100.0] * 20 + [98.0, 99.0, 101.0, 103.0, 105.0]
        metrics = analyze_trend_activity(self.history(closes, last_volume=2600))
        self.assertTrue(metrics["eligible"])
        self.assertEqual(metrics["trend_state"], "up")
        self.assertEqual(metrics["previous_trend_state"], "neutral")
        self.assertTrue(metrics["cross_up"])
        self.assertEqual(metrics["activity_state"], "high")
        self.assertEqual(metrics["activity_direction"], "up")
        self.assertGreater(metrics["volume_ratio"], 2.5)

        candidate = _trend_event_candidate(metrics, {"trend_state": "neutral", "activity_state": "normal"})
        self.assertEqual(candidate["kind"], "trend_activity")
        self.assertEqual(candidate["direction"], "up")
        self.assertEqual(candidate["signal"], "Strong")
        self.assertEqual(candidate["event"], "Trend snur opp · høy aktivitet")

    def test_downward_reversal_with_volume_is_risk_signal(self):
        closes = [100.0] * 20 + [102.0, 101.0, 99.0, 97.0, 95.0]
        metrics = analyze_trend_activity(self.history(closes, last_volume=2700))
        self.assertEqual(metrics["trend_state"], "down")
        self.assertTrue(metrics["cross_down"])
        self.assertEqual(metrics["activity_state"], "high")
        candidate = _trend_event_candidate(metrics, {"trend_state": "neutral", "activity_state": "normal"})
        self.assertEqual(candidate["direction"], "down")
        self.assertEqual(candidate["signal"], "Risk")
        self.assertEqual(candidate["event"], "Trend snur ned · høy aktivitet")

    def test_activity_surge_can_signal_without_false_trend_reversal(self):
        closes = [100.0] * 24 + [101.5]
        metrics = analyze_trend_activity(self.history(closes, last_volume=2200))
        self.assertEqual(metrics["trend_state"], "neutral")
        self.assertEqual(metrics["activity_state"], "high")
        self.assertEqual(metrics["activity_direction"], "up")
        candidate = _trend_event_candidate(metrics, {"trend_state": "neutral", "activity_state": "normal"})
        self.assertEqual(candidate["kind"], "activity_surge")
        self.assertEqual(candidate["event"], "Høy aktivitet · positivt kursmomentum")

    def test_same_state_does_not_emit_duplicate_signal(self):
        closes = [100.0] * 20 + [98.0, 99.0, 101.0, 103.0, 105.0]
        metrics = analyze_trend_activity(self.history(closes, last_volume=2600))
        candidate = _trend_event_candidate(metrics, {"trend_state": "up", "activity_state": "high"})
        self.assertIsNone(candidate)


if __name__ == '__main__':
    unittest.main()
