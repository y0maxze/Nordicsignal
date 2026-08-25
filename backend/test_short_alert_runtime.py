import unittest

from short_alert_runtime import _short_change_from_cache, _long_proxy


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

    def test_long_proxy_high_on_strong_volume_and_price_move(self):
        result=_long_proxy(3.4,2.3,{'short_change_pp':-0.30})
        self.assertEqual(result['level'],'high')
        self.assertIn('LONG-proxy',result['message'])
        self.assertGreaterEqual(result['score'],4)

    def test_long_proxy_elevated_on_moderate_buying_pressure(self):
        result=_long_proxy(2.2,1.1,{'short_change_pp':0.0})
        self.assertEqual(result['level'],'elevated')
        self.assertIsNotNone(result['message'])

    def test_long_proxy_does_not_fire_on_price_fall(self):
        result=_long_proxy(4.0,-2.0,{'short_change_pp':-0.5})
        self.assertEqual(result['level'],'none')
        self.assertIsNone(result['message'])


if __name__=='__main__':
    unittest.main()
