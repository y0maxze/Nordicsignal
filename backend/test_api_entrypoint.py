import unittest

import api_entrypoint
import production


class ApiEntrypointTests(unittest.TestCase):
    def test_provider_warmup_handler_is_not_registered(self):
        self.assertNotIn(production.production_startup, api_entrypoint.app.router.on_startup)
        self.assertIn(api_entrypoint.api_startup, api_entrypoint.app.router.on_startup)

    def test_api_startup_does_not_call_refresh(self):
        original_init = production.main.init_db
        original_seed = production.main.seed_db
        original_indexes = production.ensure_indexes
        original_refresh = production.main.refresh_all
        calls = []
        try:
            production.main.init_db = lambda: calls.append("init")
            production.main.seed_db = lambda: calls.append("seed")
            production.ensure_indexes = lambda: calls.append("indexes")
            production.main.refresh_all = lambda *a, **k: calls.append("refresh")
            api_entrypoint.api_startup()
        finally:
            production.main.init_db = original_init
            production.main.seed_db = original_seed
            production.ensure_indexes = original_indexes
            production.main.refresh_all = original_refresh
        self.assertEqual(calls, ["init", "seed", "indexes"])


if __name__ == "__main__":
    unittest.main()
