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
    def setUp(self):
        production._reset_refresh_guard_for_tests()

    def tearDown(self):
        production._reset_refresh_guard_for_tests()

    def test_render_entrypoint_replaces_blocking_main_startup(self):
        handlers = list(production.app.router.on_startup)
        self.assertNotIn(main.startup, handlers)
        self.assertIn(production.production_startup, handlers)

    def test_production_replaces_unbounded_refresh_implementation(self):
        self.assertIs(main.refresh_all, production._production_refresh_all)
        self.assertGreaterEqual(production._PROVIDER_WORKERS, 1)
        self.assertLessEqual(production._PROVIDER_WORKERS, 4)

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
        stale['created_at'] = (datetime.now(timezone.utc) - timedelta(minutes=15)).isoformat()
        with patch.object(production, 'connect', return_value=_FakeConn(stale)):
            self.assertIsNone(production._fresh_partial_components('LSG'))

        old_live = dict(fresh)
        old_live['source'] = 'live'
        with patch.object(production, 'connect', return_value=_FakeConn(old_live)):
            self.assertIsNone(production._fresh_partial_components('LSG'))

    def test_refresh_guard_rejects_overlap(self):
        allowed, reason, retry_after = production._begin_provider_refresh(enforce_cooldown=True)
        self.assertTrue(allowed)
        self.assertEqual(reason, 'ok')
        self.assertEqual(retry_after, 0)

        allowed, reason, retry_after = production._begin_provider_refresh(enforce_cooldown=True)
        self.assertFalse(allowed)
        self.assertEqual(reason, 'in_progress')
        self.assertGreaterEqual(retry_after, 1)
        production._finish_provider_refresh(mark_finished=True)

    def test_refresh_guard_enforces_cooldown_after_attempt(self):
        allowed, _, _ = production._begin_provider_refresh(enforce_cooldown=True)
        self.assertTrue(allowed)
        production._finish_provider_refresh(mark_finished=True)

        allowed, reason, retry_after = production._begin_provider_refresh(enforce_cooldown=True)
        self.assertFalse(allowed)
        self.assertEqual(reason, 'cooldown')
        self.assertGreaterEqual(retry_after, 1)

    def test_startup_refresh_can_ignore_cooldown_but_not_overlap(self):
        allowed, _, _ = production._begin_provider_refresh(enforce_cooldown=True)
        self.assertTrue(allowed)
        production._finish_provider_refresh(mark_finished=True)

        allowed, reason, _ = production._begin_provider_refresh(enforce_cooldown=False)
        self.assertTrue(allowed)
        self.assertEqual(reason, 'ok')

        second, second_reason, _ = production._begin_provider_refresh(enforce_cooldown=False)
        self.assertFalse(second)
        self.assertEqual(second_reason, 'in_progress')
        production._finish_provider_refresh(mark_finished=True)

    def test_stale_warmup_runs_yahoo_once_then_insider_only(self):
        with patch.object(production.time, 'sleep'), \
             patch.object(production, '_latest_scores_fresh', return_value=False), \
             patch.object(main, 'refresh_all', return_value=[]) as refresh_all, \
             patch.object(production, '_refresh_insiders_only', return_value=[]) as insiders_only:
            production._market_warmup()
        refresh_all.assert_called_once_with(include_insider=False)
        insiders_only.assert_called_once_with()

    def test_warmup_skips_when_manual_refresh_already_owns_slot(self):
        allowed, _, _ = production._begin_provider_refresh(enforce_cooldown=True)
        self.assertTrue(allowed)
        with patch.object(production.time, 'sleep'), \
             patch.object(production, '_latest_scores_fresh', return_value=False), \
             patch.object(main, 'refresh_all') as refresh_all, \
             patch.object(production, '_refresh_insiders_only') as insiders_only:
            production._market_warmup()
        refresh_all.assert_not_called()
        insiders_only.assert_not_called()
        production._finish_provider_refresh(mark_finished=True)

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
