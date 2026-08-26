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


if __name__ == '__main__':
    unittest.main()
