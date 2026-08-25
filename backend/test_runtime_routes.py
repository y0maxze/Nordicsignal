import unittest

import main


class RuntimeRouteRegistrationTests(unittest.TestCase):
    def test_required_runtime_routes_are_registered(self):
        paths = {route.path for route in main.app.routes}
        required = {
            '/api/reports/{ticker}',
            '/api/dividends/{ticker}',
            '/api/intelligence/{ticker}',
            '/api/paper/history',
            '/api/paper/dashboard',
            '/api/paper/account',
            '/api/paper/portfolio',
            '/api/paper/trades',
            '/api/paper/backtest',
        }
        missing = sorted(required - paths)
        self.assertFalse(missing, f'Missing runtime API routes: {missing}')


if __name__ == '__main__':
    unittest.main()
