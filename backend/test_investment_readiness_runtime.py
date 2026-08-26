import unittest

from investment_readiness_runtime import _news_pulse, _status


class InvestmentReadinessTests(unittest.TestCase):
    def test_positive_news_pulse(self):
        out = _news_pulse([
            {"title": "Company raises guidance after strong results", "official": True},
            {"title": "Major contract award announced", "official": True},
        ])
        self.assertGreater(out["score"], 0)
        self.assertTrue(out["positive_headlines"])
        self.assertFalse(out["severe_risk_flag"])

    def test_severe_risk_news_caps_conviction(self):
        out = _news_pulse([
            {"title": "Company issues profit warning and lowers guidance", "official": True},
        ])
        self.assertLess(out["score"], 0)
        self.assertTrue(out["risk_headlines"])
        self.assertTrue(out["severe_risk_flag"])

    def test_low_coverage_waits_for_more_data(self):
        code, label, tone = _status(88, 40, False)
        self.assertEqual(code, "WAIT_FOR_DATA")
        self.assertEqual(label, "Vent på mer data")
        self.assertEqual(tone, "watch")

    def test_high_score_is_more_ready_only_with_coverage(self):
        code, label, tone = _status(74, 80, False)
        self.assertEqual(code, "MORE_READY")
        self.assertEqual(label, "Mer investeringsklart")
        self.assertEqual(tone, "positive")

    def test_severe_news_overrides_high_score(self):
        code, label, tone = _status(82, 90, True)
        self.assertEqual(code, "ELEVATED_RISK")
        self.assertEqual(label, "Forhøyet risiko")
        self.assertEqual(tone, "risk")


if __name__ == "__main__":
    unittest.main()
