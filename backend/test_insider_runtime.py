import unittest
from insider_runtime import parse_trade, parse_trades, issuer_ok, canonical_url, date_of, ISSUER_RELEASE_FEEDS


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

    def test_text_month_dates_are_supported(self):
        self.assertEqual(date_of('25. august 2026'), '2026-08-25')
        self.assertEqual(date_of('25 August 2026'), '2026-08-25')
        self.assertEqual(date_of('August 25, 2026'), '2026-08-25')

    def test_leroy_plural_release_returns_both_disclosed_buyers(self):
        body = (
            'Lerøy Seafood Group ASA: Primærinsidetransaksjoner. '
            'Sjur Malm, CFO i Lerøy Seafood Group ASA, har den 25. august 2026 kjøpt 14 500 aksjer i Lerøy Seafood Group ASA. '
            'Etter transaksjonen eier Sjur Malm 57 000 aksjer i Lerøy Seafood Group ASA. '
            'Ivar Wulff, COO Market Operations i Lerøy Seafood Group ASA, har den 25. august 2026 kjøpt 11 500 aksjer i Lerøy Seafood Group ASA. '
            'Etter transaksjonen eier Ivar Wulff 23 500 aksjer i Lerøy Seafood Group ASA.'
        )
        rows = parse_trades(body, 'LSG', 'Lerøy Seafood Group ASA: Primærinsidetransaksjoner', 'GlobeNewswire issuer release', 'https://example.test/lsg')
        self.assertEqual(len(rows), 2)
        by_name = {x['insider']: x for x in rows}
        self.assertEqual(by_name['Sjur Malm']['shares'], 14500)
        self.assertEqual(by_name['Sjur Malm']['role'], 'CFO')
        self.assertEqual(by_name['Sjur Malm']['date'], '2026-08-25')
        self.assertEqual(by_name['Ivar Wulff']['shares'], 11500)
        self.assertEqual(by_name['Ivar Wulff']['role'], 'COO Market Operations')
        self.assertEqual(by_name['Ivar Wulff']['direction'], 'buy')

    def test_leroy_represented_company_trade_keeps_company_actor(self):
        body = (
            'Lerøy Seafood Group ASA. FERD AS, representert i styret i Lerøy Seafood Group ASA ved Are Dragesund, '
            'har den 21.08.2026 kjøpt 357 542 aksjer i Lerøy Seafood Group ASA.'
        )
        rows = parse_trades(body, 'LSG', 'Primærinsidetransaksjon', 'GlobeNewswire issuer release', 'https://example.test/ferd')
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row['entity'], 'FERD AS')
        self.assertEqual(row['insider'], 'FERD AS')
        self.assertEqual(row['shares'], 357542)
        self.assertEqual(row['date'], '2026-08-21')
        self.assertIn('Are Dragesund', row['role'])

    def test_leroy_has_stable_issuer_release_fallback(self):
        self.assertIn('LSG', ISSUER_RELEASE_FEEDS)
        self.assertIn('globenewswire.com', ISSUER_RELEASE_FEEDS['LSG'])

    def test_unrelated_issuer_is_rejected(self):
        self.assertFalse(issuer_ok('Equinor ASA John Example purchased 100 shares', 'LSG', 'Lerøy Seafood Group ASA'))

    def test_euronext_language_variants_collapse_to_same_url(self):
        a = canonical_url('https://live.euronext.com/en/news/abc?foo=1')
        b = canonical_url('https://live.euronext.com/nb/news/abc?foo=1')
        self.assertEqual(a, b)


if __name__ == '__main__':
    unittest.main()