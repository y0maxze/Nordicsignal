import json
import subprocess
import sys
import unittest


class RuntimeRouteRegistrationTests(unittest.TestCase):
    def test_required_runtime_routes_are_registered_in_fresh_process(self):
        code = (
            "import json, main; "
            "print(json.dumps(sorted({route.path for route in main.app.routes})))"
        )
        proc = subprocess.run(
            [sys.executable, '-c', code],
            check=True,
            capture_output=True,
            text=True,
        )
        paths = set(json.loads(proc.stdout.strip().splitlines()[-1]))
        required = {
            '/api/reports/{ticker}',
            '/api/dividends/{ticker}',
            '/api/intelligence/{ticker}',
            '/api/market-pressure/{ticker}',
            '/api/readiness/{symbol}',
            '/api/paper/history',
            '/api/paper/dashboard',
            '/api/paper/account',
            '/api/paper/portfolio',
            '/api/paper/trades',
            '/api/paper/backtest',
            '/api/paper/instrument-order',
            '/api/holdings',
            '/api/holdings/{holding_id}',
            '/api/holdings/{holding_id}/purchases',
            '/api/holding-purchases/{purchase_id}',
            '/api/holdings/account-tax',
            '/api/holdings/transactions',
            '/api/holdings/transactions/{transaction_id}',
            '/api/calendar',
            '/api/holdings/calendar',
            '/api/instruments/search',
            '/api/holdings/instrument-meta',
            '/api/holdings/cash',
            '/api/holdings/cash/{cash_id}',
            '/api/instrument/{symbol}',
            '/api/instrument/{symbol}/history',
            '/api/instrument/{symbol}/news',
            '/api/instrument/{symbol}/distributions',
            '/api/instrument/{symbol}/analytics',
            '/api/instrument-signals/register',
            '/api/instrument-signals',
            '/api/signal-events',
            '/api/dashboard-home',
            '/api/performance',
        }
        missing = sorted(required - paths)
        self.assertFalse(missing, f'Missing runtime API routes: {missing}')

    def test_purchase_lot_route_supports_edit_and_delete(self):
        code = (
            "import json, main; "
            "print(json.dumps(sorted({m for r in main.app.routes if r.path=='/api/holding-purchases/{purchase_id}' for m in (r.methods or set())})))"
        )
        proc = subprocess.run(
            [sys.executable, '-c', code],
            check=True,
            capture_output=True,
            text=True,
        )
        methods = set(json.loads(proc.stdout.strip().splitlines()[-1]))
        self.assertIn('PUT', methods)
        self.assertIn('DELETE', methods)


if __name__ == '__main__':
    unittest.main()
