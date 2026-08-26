from datetime import datetime, timezone
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


if __name__ == '__main__':
    unittest.main()
