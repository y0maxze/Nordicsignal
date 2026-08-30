import unittest
from unittest.mock import patch

import opportunity_autoscan_runtime as autoscan


class OpportunityAutoscanRuntimeTests(unittest.TestCase):
    def test_scheduler_status_reports_external_readiness(self):
        status = autoscan.scheduler_status()
        self.assertTrue(status["external_scheduler_ready"])
        self.assertEqual(status["scan_interval_seconds"], 600)
        self.assertTrue(status["in_process_fallback"])

    def test_guarded_scan_path_is_reused(self):
        with patch.object(autoscan.tracking, "_maybe_schedule_scan", return_value="scheduled") as trigger:
            state = autoscan.tracking._maybe_schedule_scan()
        self.assertEqual(state, "scheduled")
        trigger.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
