import unittest
from insider_runtime import parse_trade, issuer_ok, canonical_url


class InsiderRuntimeTests(unittest.TestCase):
    def test_buy_trade_extracts_shares_person_role_price_and_value(self):
        body = 'Lerøy Seafood Group ASA. CEO John Example purchased 15 000 shares at NOK 48 per share on 2026-08-24.'
        row = parse_trade(body, 'LSG', 'Primary insider transaction', 'Euronext Oslo Børs', 'https://live.euronext.com/en/foo')
        self.assertEqual(row['direction'], 'buy')
        self.assertEqual(row['shares'], 15000)
        self.assertEqual(row['date'], '2026-08-24')
        self.assertEqual(row['insider'], 'John Example')
        self.assertEqual(row['person'], 'John Example')
        self.assertEqual(row['role'].upper(), 'CEO')
        self.assertEqual(row['actor_type'], 'person')
        self.assertAlmostEqual(row['price'], 48.0)
        self.assertAlmostEqual(row['transaction_value'], 720000.0)
        self.assertTrue(row['verified_detail'])

    def test_sell_trade_is_not_misclassified_as_buy(self):
        body = 'Lerøy Seafood Group ASA. CFO Jane Example sold 2 500 shares on 2026-08-20.'
        row = parse_trade(body, 'LSG', 'Primary insider transaction', 'Euronext Oslo Børs', 'https://live.euronext.com/en/foo')
        self.assertEqual(row['direction'], 'sell')
        self.assertEqual(row['shares'], 2500)
        self.assertEqual(row['insider'], 'Jane Example')

    def test_company_actor_is_extracted(self):
        body = 'Lerøy Seafood Group ASA. Nordbrand Invest AS purchased 20 000 shares at NOK 50.25 per share on 2026-08-22.'
        row = parse_trade(body, 'LSG', 'Mandatory notification of trade', 'Euronext Oslo Børs', 'https://live.euronext.com/en/foo')
        self.assertEqual(row['direction'], 'buy')
        self.assertEqual(row['shares'], 20000)
        self.assertEqual(row['entity'], 'Nordbrand Invest AS')
        self.assertEqual(row['insider'], 'Nordbrand Invest AS')
        self.assertEqual(row['actor_type'], 'company')
        self.assertAlmostEqual(row['price'], 50.25)
        self.assertAlmostEqual(row['transaction_value'], 1005000.0)

    def test_norwegian_price_with_decimal_comma(self):
        body = 'Lerøy Seafood Group ASA. Konsernsjef Ola Nordmann kjøpte 1 000 aksjer til kurs NOK 42,50 den 24.08.2026.'
        row = parse_trade(body, 'LSG', 'Meldepliktig handel for primærinnsidere', 'Euronext Oslo Børs', 'https://live.euronext.com/nb/foo')
        self.assertEqual(row['direction'], 'buy')
        self.assertEqual(row['shares'], 1000)
        self.assertEqual(row['insider'], 'Ola Nordmann')
        self.assertAlmostEqual(row['price'], 42.5)
        self.assertAlmostEqual(row['transaction_value'], 42500.0)

    def test_unrelated_issuer_is_rejected(self):
        self.assertFalse(issuer_ok('Equinor ASA John Example purchased 100 shares', 'LSG', 'Lerøy Seafood Group ASA'))

    def test_euronext_language_variants_collapse_to_same_url(self):
        a = canonical_url('https://live.euronext.com/en/news/abc?foo=1')
        b = canonical_url('https://live.euronext.com/nb/news/abc?foo=1')
        self.assertEqual(a, b)


if __name__ == '__main__':
    unittest.main()
