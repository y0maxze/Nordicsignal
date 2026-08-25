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
            '/api/paper/history',
            '/api/paper/dashboard',
            '/api/paper/account',
            '/api/paper/portfolio',
            '/api/paper/trades',
            '/api/paper/backtest',
            '/api/holdings',
            '/api/holdings/{holding_id}',
            '/api/holdings/account-tax',
            '/api/holdings/transactions',
            '/api/holdings/transactions/{transaction_id}',
            '/api/instruments/search',
            '/api/holdings/instrument-meta',
            '/api/holdings/cash',
            '/api/holdings/cash/{cash_id}',
        }
        missing = sorted(required - paths)
        self.assertFalse(missing, f'Missing runtime API routes: {missing}')


if __name__ == '__main__':
    unittest.main()
