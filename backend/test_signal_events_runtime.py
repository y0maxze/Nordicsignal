import unittest

from signal_events_runtime import build_stock_events


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

    def test_two_point_move_is_material_inside_same_band(self):
        rows = [
            {"ticker": "AAA", "name": "Alpha", "total": 67, "created_at": "2026-08-26T00:20:00+00:00"},
            {"ticker": "AAA", "name": "Alpha", "total": 65, "created_at": "2026-08-26T00:10:00+00:00"},
        ]
        events = build_stock_events(rows)
        self.assertEqual(len(events), 1)
        self.assertIn("2", events[0]["event"])


if __name__ == '__main__':
    unittest.main()
