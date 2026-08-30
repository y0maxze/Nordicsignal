import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import opportunity_autoscan_runtime as autoscan


class OpportunityAutoscanRuntimeTests(unittest.TestCase):
    def test_scheduler_status_reports_external_readiness(self):
        heartbeat = {
            "last_external_trigger_at": "2026-08-30T02:30:00+00:00",
            "last_scan_state": "scheduled",
            "external_trigger_count": 4,
            "scheduler_state_updated_at": "2026-08-30T02:30:00+00:00",
        }
        with patch.object(autoscan, "_persistent_status", return_value=heartbeat):
            status = autoscan.scheduler_status()
        self.assertTrue(status["external_scheduler_ready"])
        self.assertEqual(status["scan_interval_seconds"], 600)
        self.assertTrue(status["in_process_fallback"])
        self.assertEqual(status["last_scan_state"], "scheduled")
        self.assertEqual(status["external_trigger_count"], 4)

    def test_guarded_scan_path_is_reused(self):
        with patch.object(autoscan.tracking, "_maybe_schedule_scan", return_value="scheduled") as trigger:
            state = autoscan.tracking._maybe_schedule_scan()
        self.assertEqual(state, "scheduled")
        trigger.assert_called_once_with()

    def test_external_trigger_heartbeat_is_persisted(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "scheduler.db"

            def connect_test_db():
                conn = sqlite3.connect(db_path)
                conn.row_factory = sqlite3.Row
                return conn

            with patch.object(autoscan, "connect", side_effect=connect_test_db):
                autoscan._ensure_scheduler_schema()
                _, first_count = autoscan._record_external_trigger("scheduled")
                _, second_count = autoscan._record_external_trigger("fresh")
                status = autoscan._persistent_status()

        self.assertEqual(first_count, 1)
        self.assertEqual(second_count, 2)
        self.assertEqual(status["external_trigger_count"], 2)
        self.assertEqual(status["last_scan_state"], "fresh")
        self.assertTrue(status["last_external_trigger_at"])


if __name__ == "__main__":
    unittest.main()
