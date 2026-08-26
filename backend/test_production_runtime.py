import unittest

import main
import production


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


if __name__ == '__main__':
    unittest.main()
