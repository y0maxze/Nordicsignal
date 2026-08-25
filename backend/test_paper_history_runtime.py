import unittest

from paper_history_runtime import enrich_history


class PaperHistoryRuntimeTests(unittest.TestCase):
    def test_fifo_realized_profit_and_summary(self):
        trades = [
            {'id': 1, 'ticker': 'LSG', 'side': 'buy', 'shares': 10, 'price': 100, 'fee': 10, 'executed_at': '2026-01-01T10:00:00+00:00'},
            {'id': 2, 'ticker': 'LSG', 'side': 'buy', 'shares': 5, 'price': 120, 'fee': 5, 'executed_at': '2026-01-02T10:00:00+00:00'},
            {'id': 3, 'ticker': 'LSG', 'side': 'sell', 'shares': 12, 'price': 130, 'fee': 12, 'executed_at': '2026-01-03T10:00:00+00:00'},
        ]
        out = enrich_history(trades)
        sell = next(x for x in out['items'] if x['side'] == 'sell')
        # FIFO cost: first 10 shares cost 1010, next 2 cost 2/5 of 605 = 242.
        self.assertAlmostEqual(sell['cost_basis_sold'], 1252.0, places=8)
        self.assertAlmostEqual(sell['net_proceeds'], 1548.0, places=8)
        self.assertAlmostEqual(sell['realized_pnl'], 296.0, places=8)
        self.assertAlmostEqual(out['summary']['realized_pnl'], 296.0, places=8)
        self.assertEqual(out['summary']['winners'], 1)
        self.assertEqual(out['summary']['losers'], 0)
        self.assertEqual(out['summary']['win_rate'], 100.0)
        self.assertAlmostEqual(out['summary']['fees_total'], 27.0, places=8)

    def test_loss_and_breakeven_statistics(self):
        trades = [
            {'id': 1, 'ticker': 'A', 'side': 'buy', 'shares': 1, 'price': 100, 'fee': 0},
            {'id': 2, 'ticker': 'A', 'side': 'sell', 'shares': 1, 'price': 90, 'fee': 0},
            {'id': 3, 'ticker': 'B', 'side': 'buy', 'shares': 1, 'price': 50, 'fee': 0},
            {'id': 4, 'ticker': 'B', 'side': 'sell', 'shares': 1, 'price': 50, 'fee': 0},
        ]
        s = enrich_history(trades)['summary']
        self.assertEqual(s['winners'], 0)
        self.assertEqual(s['losers'], 1)
        self.assertEqual(s['breakeven'], 1)
        self.assertEqual(s['closed_trade_count'], 2)
        self.assertEqual(s['win_rate'], 0.0)
        self.assertAlmostEqual(s['realized_pnl'], -10.0, places=8)

    def test_legacy_oversell_is_marked_unknown_not_invented(self):
        trades = [
            {'id': 1, 'ticker': 'LSG', 'side': 'buy', 'shares': 1, 'price': 100, 'fee': 0},
            {'id': 2, 'ticker': 'LSG', 'side': 'sell', 'shares': 2, 'price': 110, 'fee': 0},
        ]
        out = enrich_history(trades)
        sell = out['items'][0]
        self.assertEqual(sell['accounting_status'], 'insufficient_history')
        self.assertIsNone(sell['realized_pnl'])
        self.assertEqual(out['summary']['closed_trade_count'], 0)

    def test_items_return_newest_first(self):
        trades = [
            {'id': 1, 'ticker': 'LSG', 'side': 'buy', 'shares': 1, 'price': 100, 'fee': 0},
            {'id': 2, 'ticker': 'LSG', 'side': 'sell', 'shares': 1, 'price': 110, 'fee': 0},
        ]
        out = enrich_history(trades)
        self.assertEqual([x['id'] for x in out['items']], [2, 1])


if __name__ == '__main__':
    unittest.main()
