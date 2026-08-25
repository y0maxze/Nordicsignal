import unittest
from unittest.mock import patch

from insider_enrichment_runtime import enrich_item


class InsiderEnrichmentTests(unittest.TestCase):
    def test_labelled_primary_insider_table_is_parsed(self):
        item={
            'ticker':'LSG',
            'title':'Lerøy Seafood Group ASA: Primary Insider Transaction',
            'summary':(
                'Name of person discharging managerial responsibilities: Ola Nordmann; '
                'Position/status: CFO; Nature of transaction: Purchase; '
                'Price: NOK 44,50; Aggregated volume: 20 000; '
                'Following the transaction Ola Nordmann holds 120 000 shares.'
            ),
        }
        with patch('insider_enrichment_runtime._shares_outstanding', return_value=600_000_000):
            x=enrich_item(item,'LSG')
        self.assertEqual(x['direction'],'buy')
        self.assertEqual(x['shares'],20000)
        self.assertAlmostEqual(x['price'],44.5)
        self.assertEqual(x['person'],'Ola Nordmann')
        self.assertEqual(x['holding_after_shares'],120000)
        self.assertAlmostEqual(x['transaction_value'],890000)
        self.assertAlmostEqual(x['ownership_pct'],0.02)
        self.assertEqual(x['ownership_pct_source'],'estimated_from_latest_annual_share_count')

    def test_disclosed_ownership_percentage_wins_over_estimate(self):
        item={
            'summary':'Nature of transaction: Sale; Volume: 5 000; Price: NOK 50.00; Holding after transaction: 90 000 shares; Ownership after transaction: 0.015%',
        }
        with patch('insider_enrichment_runtime._shares_outstanding', return_value=1):
            x=enrich_item(item,'LSG')
        self.assertEqual(x['direction'],'sell')
        self.assertEqual(x['shares'],5000)
        self.assertAlmostEqual(x['ownership_pct'],0.015)
        self.assertEqual(x['ownership_pct_source'],'disclosed')

    def test_company_actor_is_parsed(self):
        item={'summary':'Person closely associated: Havglimt Invest AS; Nature of transaction: Purchase; Number of shares: 10 000; Price: NOK 42.25'}
        x=enrich_item(item,'LSG')
        self.assertEqual(x['entity'],'Havglimt Invest AS')
        self.assertEqual(x['actor_type'],'company')
        self.assertEqual(x['shares'],10000)
        self.assertAlmostEqual(x['transaction_value'],422500)


if __name__=='__main__':
    unittest.main()
