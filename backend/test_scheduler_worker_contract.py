from pathlib import Path
import unittest


class SchedulerWorkerContractTests(unittest.TestCase):
    def test_hourly_market_refresh_uses_internal_auth_path(self):
        root = Path(__file__).resolve().parent.parent
        worker = (root / "scheduler_worker.js").read_text(encoding="utf-8")
        wrangler = (root / "wrangler.toml").read_text(encoding="utf-8")
        self.assertIn('const REFRESH_PATH = "/api/refresh"', worker)
        self.assertIn('controller.cron === "17 * * * *"', worker)
        self.assertIn('x-nordicsignal-internal-token', worker)
        self.assertIn('"17 * * * *"', wrangler)
        self.assertIn('"*/10 * * * *"', wrangler)


if __name__ == "__main__":
    unittest.main()
