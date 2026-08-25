import unittest
from datetime import datetime, timezone

from extra_api import _parse_date, _xirr


class PaperLogicTests(unittest.TestCase):
    def test_parse_date_assumes_utc(self):
        dt = _parse_date("2026-01-02", "start")
        self.assertEqual(dt.tzinfo, timezone.utc)
        self.assertEqual(dt.day, 2)

    def test_xirr_for_simple_one_year_double(self):
        start = datetime(2025, 1, 1, tzinfo=timezone.utc)
        end = datetime(2026, 1, 1, tzinfo=timezone.utc)
        result = _xirr([(start, -100.0), (end, 200.0)])
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result, 1.0, delta=0.002)

    def test_xirr_requires_both_cashflow_signs(self):
        start = datetime(2025, 1, 1, tzinfo=timezone.utc)
        end = datetime(2026, 1, 1, tzinfo=timezone.utc)
        self.assertIsNone(_xirr([(start, -100.0), (end, -50.0)]))


if __name__ == "__main__":
    unittest.main()
