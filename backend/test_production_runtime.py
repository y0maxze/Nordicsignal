from datetime import datetime, timedelta, timezone
import unittest
from unittest.mock import patch

import main
import production


class _FakeConn:
    def __init__(self, row):
        self.row = row
    def execute(self, *_args, **_kwargs):
        return self
    def fetchone(self):
        return self.row
    def close(self):
        pass


class ProductionRuntimeTests(unittest.TestCase):
    def test_render_entrypoint_replaces_blocking_main_startup(self):
        handlers = list(production.app.router.on_startup)
        self.assertNotIn(main.startup, handlers)
        self.assertIn(production.production_startup, handlers)

    def test_index_plan_contains_core_query_indexes(self):
        joined = '\n'.join(production._INDEXES)
        self.assertIn('scores(ticker,id)', joined)
        self.assertIn('holding_transactions', joined)
        self.assertIn('signal_events', joined)

    def test_production_route_table_has_no_exact_duplicates(self):
        keys = []
        for route in production.app.router.routes:
            path = getattr(route, 'path', None)
            methods = getattr(route, 'methods', None)
            if path and methods:
                keys.append((path, tuple(sorted(methods))))
        self.assertEqual(len(keys), len(set(keys)))

    def test_seed_rows_never_suppress_market_warmup(self):
        row = {'oldest': datetime.now(timezone.utc).isoformat(), 'n': len(main.TICKERS), 'live_n': 0}
        with patch.object(production, 'connect', return_value=_FakeConn(row)):
            self.assertFalse(production._latest_scores_fresh())

    def test_recent_live_rows_can_skip_redundant_warmup(self):
        row = {
            'oldest': datetime.now(timezone.utc).isoformat(),
            'n': len(main.TICKERS),
            'live_n': len(main.TICKERS),
        }
        with patch.object(production, 'connect', return_value=_FakeConn(row)):
            self.assertTrue(production._latest_scores_fresh())

    def test_only_fresh_partial_rows_can_be_upgraded_with_insider_data(self):
        fresh = {
            'fundamentals': 30,
            'valuation': 14,
            'sentiment': 11,
            'created_at': datetime.now(timezone.utc).isoformat(),
            'source': 'partial_live',
        }
        with patch.object(production, 'connect', return_value=_FakeConn(fresh)):
            self.assertEqual(
                production._fresh_partial_components('LSG'),
                {'fundamentals': 30, 'valuation': 14, 'sentiment': 11},
            )

        stale = dict(fresh)
        stale['created_at'] = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        with patch.object(production, 'connect', return_value=_FakeConn(stale)):
            self.assertIsNone(production._fresh_partial_components('LSG'))

        old_live = dict(fresh)
        old_live['source'] = 'live'
        with patch.object(production, 'connect', return_value=_FakeConn(old_live)):
            self.assertIsNone(production._fresh_partial_components('LSG'))

    def test_stale_warmup_runs_yahoo_once_then_insider_only(self):
        with patch.object(production.time, 'sleep'), \
             patch.object(production, '_latest_scores_fresh', return_value=False), \
             patch.object(main, 'refresh_all', return_value=[]) as refresh_all, \
             patch.object(production, '_refresh_insiders_only', return_value=[]) as insiders_only:
            production._market_warmup()
        refresh_all.assert_called_once_with(include_insider=False)
        insiders_only.assert_called_once_with()

    def test_fresh_warmup_skips_all_provider_work(self):
        with patch.object(production.time, 'sleep'), \
             patch.object(production, '_latest_scores_fresh', return_value=True), \
             patch.object(main, 'refresh_all') as refresh_all, \
             patch.object(production, '_refresh_insiders_only') as insiders_only:
            production._market_warmup()
        refresh_all.assert_not_called()
        insiders_only.assert_not_called()


if __name__ == '__main__':
    unittest.main()
