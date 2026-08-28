import inspect
import unittest
from datetime import datetime, timezone, timedelta

import data_quality_runtime as dq


class DataQualityRuntimeTests(unittest.TestCase):
    def test_age_seconds_handles_current_timestamp(self):
        value=(datetime.now(timezone.utc)-timedelta(seconds=5)).isoformat()
        age=dq._age_seconds(value)
        self.assertIsNotNone(age)
        self.assertGreaterEqual(age, 0)
        self.assertLess(age, 30)

    def test_check_keeps_warning_severity(self):
        row=dq._check('freshness', False, 'stale', severity='warning')
        self.assertFalse(row['ok'])
        self.assertEqual(row['severity'],'warning')

    def test_persisted_quote_age_is_not_reported_as_live_price_age(self):
        source=inspect.getsource(dq.data_quality_snapshot)
        self.assertIn('"mode": "live_on_request"', source)
        self.assertIn('freshness["persisted_price_snapshot"]', source)
        self.assertNotIn('quote_age = freshness["prices"]', source)


if __name__=='__main__':
    unittest.main()
