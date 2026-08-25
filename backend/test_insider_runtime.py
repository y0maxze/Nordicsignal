import unittest
from insider_runtime import parse_trade, issuer_ok, canonical_url


class InsiderRuntimeTests(unittest.TestCase):
    def test_buy_trade_extracts_shares_and_person(self):
        body = 'Lerøy Seafood Group ASA. CEO John Example purchased 15 000 shares at NOK 48 per share on 2026-08-24.'
        row = parse_trade(body, 'LSG', 'Primary insider transaction', 'Euronext Oslo Børs', 'https://live.euronext.com/en/foo')
        self.assertEqual(row['direction'], 'buy')
        self.assertEqual(row['shares'], 15000)
        self.assertEqual(row['date'], '2026-08-24')
        self.assertEqual(row['insider'], 'John Example')
        self.assertTrue(row['verified_detail'])

    def test_sell_trade_is_not_misclassified_as_buy(self):
        body = 'Lerøy Seafood Group ASA. CFO Jane Example sold 2 500 shares on 2026-08-20.'
        row = parse_trade(body, 'LSG', 'Primary insider transaction', 'Euronext Oslo Børs', 'https://live.euronext.com/en/foo')
        self.assertEqual(row['direction'], 'sell')
        self.assertEqual(row['shares'], 2500)

    def test_unrelated_issuer_is_rejected(self):
        self.assertFalse(issuer_ok('Equinor ASA John Example purchased 100 shares', 'LSG', 'Lerøy Seafood Group ASA'))

    def test_euronext_language_variants_collapse_to_same_url(self):
        a = canonical_url('https://live.euronext.com/en/news/abc?foo=1')
        b = canonical_url('https://live.euronext.com/nb/news/abc?foo=1')
        self.assertEqual(a, b)


if __name__ == '__main__':
    unittest.main()
