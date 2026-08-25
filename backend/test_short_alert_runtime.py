import unittest

from short_alert_runtime import _short_change_from_cache


class FakeShortProvider:
    def __init__(self, events):
        self._short_cache=[{'isin':'NO123','events':events}]


class ShortAlertRuntimeTests(unittest.TestCase):
    def test_short_increase_triggers_elevated_alert(self):
        provider=FakeShortProvider([
            {'date':'2026-08-25','shortPercent':1.20},
            {'date':'2026-08-24','shortPercent':1.05},
        ])
        result=_short_change_from_cache(provider,{'items':[{'isin':'NO123','date':'2026-08-25','short_percent':1.20}]})
        self.assertAlmostEqual(result['short_change_pp'],0.15,places=8)
        self.assertEqual(result['short_alert_level'],'elevated')

    def test_large_short_increase_triggers_high_alert(self):
        provider=FakeShortProvider([
            {'date':'2026-08-25','shortPercent':2.00},
            {'date':'2026-08-24','shortPercent':1.40},
        ])
        result=_short_change_from_cache(provider,{'items':[{'isin':'NO123','date':'2026-08-25','short_percent':2.00}]})
        self.assertAlmostEqual(result['short_change_pp'],0.60,places=8)
        self.assertEqual(result['short_alert_level'],'high')

    def test_drop_below_public_threshold_does_not_invent_exact_delta(self):
        provider=FakeShortProvider([
            {'date':'2026-08-25','shortPercent':'< 0.5%'},
            {'date':'2026-08-24','shortPercent':0.60},
        ])
        result=_short_change_from_cache(provider,{'items':[{'isin':'NO123','date':'2026-08-25','short_percent':'< 0.5%'}]})
        self.assertIsNone(result['short_change_pp'])
        self.assertEqual(result['short_alert_level'],'none')


if __name__=='__main__':
    unittest.main()
