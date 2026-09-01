import unittest
from unittest.mock import patch

import push_runtime as push


class OpportunityPushDispatchTests(unittest.TestCase):
    def test_early_opportunity_high_maps_to_push_payload(self):
        event = push._opportunity_push_event({
            "id": 42,
            "ticker": "XPLRA",
            "label": "EARLY_OPPORTUNITY_HIGH",
            "score": 82,
            "reversal_score": 78,
            "volume_ratio": 1.8,
            "insider_label": "POSITIVE",
            "independent_buyers": 3,
            "buy_value_nok": 1_500_000,
            "created_at": "2026-08-30T03:10:00+00:00",
        })
        self.assertIsNotNone(event)
        self.assertEqual(event["event_key"], "opportunity:42")
        self.assertEqual(event["ticker"], "XPLRA")
        self.assertIn("Sterk Early Opportunity", event["title"])
        self.assertIn("score 82", event["body"])
        self.assertIn("reversal 78", event["body"])
        self.assertIn("volum 1.8×", event["body"])
        self.assertIn("3 kjøpere", event["body"])
        self.assertEqual(event["url"], "/stock?ticker=XPLRA")

    def test_weak_watch_is_not_pushed(self):
        event = push._opportunity_push_event({
            "id": 43,
            "ticker": "LSG",
            "label": "WATCH_CONFLUENCE",
            "score": 55,
            "reversal_score": 60,
            "volume_ratio": 1.1,
            "insider_label": "NONE",
            "independent_buyers": 0,
            "buy_value_nok": 0,
            "created_at": "2026-08-30T03:10:00+00:00",
        })
        self.assertIsNone(event)

    def test_strong_watch_with_positive_insider_is_pushed(self):
        event = push._opportunity_push_event({
            "id": 44,
            "ticker": "LSG",
            "label": "WATCH_CONFLUENCE",
            "score": 61,
            "reversal_score": 64,
            "volume_ratio": 1.2,
            "insider_label": "POSITIVE",
            "independent_buyers": 4,
            "buy_value_nok": 0,
            "created_at": "2026-08-30T03:10:00+00:00",
        })
        self.assertIsNotNone(event)
        self.assertIn("Opportunity Watch", event["title"])

    def test_dispatch_once_sends_new_opportunity_event_and_records_delivery(self):
        subscription = {
            "endpoint_hash": "abc",
            "created_at": "2026-08-30T03:00:00+00:00",
        }
        event = {
            "event_key": "opportunity:42",
            "ticker": "XPLRA",
            "title": "XPLRA · Sterk Early Opportunity",
            "body": "score 82 · reversal 78 · volum 1.8×",
            "url": "/stock?ticker=XPLRA",
            "created_at": "2026-08-30T03:10:00+00:00",
        }
        with (
            patch.object(push, "_ready", return_value=True),
            patch.object(push, "_subscriptions", return_value=[subscription]),
            patch.object(push, "_event_rows", return_value=[event]),
            patch.object(push, "_delivered", return_value=False),
            patch.object(push, "_retry_allowed", return_value=True),
            patch.object(push, "_send", return_value=(True, "sent")) as sender,
            patch.object(push, "_record_attempt") as attempt_recorder,
            patch.object(push, "_record_delivery") as recorder,
        ):
            result = push.dispatch_once()

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["attempted"], 1)
        self.assertEqual(result["sent"], 1)
        sender.assert_called_once()
        attempt_recorder.assert_called_once_with("opportunity:42", "abc", "sent")
        recorder.assert_called_once_with("opportunity:42", "abc", "sent")

    def test_dispatch_once_deduplicates_already_delivered_event(self):
        subscription = {
            "endpoint_hash": "abc",
            "created_at": "2026-08-30T03:00:00+00:00",
        }
        event = {
            "event_key": "opportunity:42",
            "ticker": "XPLRA",
            "title": "XPLRA · Sterk Early Opportunity",
            "body": "score 82 · reversal 78 · volum 1.8×",
            "url": "/stock?ticker=XPLRA",
            "created_at": "2026-08-30T03:10:00+00:00",
        }
        with (
            patch.object(push, "_ready", return_value=True),
            patch.object(push, "_subscriptions", return_value=[subscription]),
            patch.object(push, "_event_rows", return_value=[event]),
            patch.object(push, "_delivered", return_value=True),
            patch.object(push, "_retry_allowed") as retry_allowed,
            patch.object(push, "_send") as sender,
            patch.object(push, "_record_attempt") as attempt_recorder,
            patch.object(push, "_record_delivery") as recorder,
        ):
            result = push.dispatch_once()

        self.assertEqual(result["attempted"], 0)
        self.assertEqual(result["sent"], 0)
        retry_allowed.assert_not_called()
        sender.assert_not_called()
        attempt_recorder.assert_not_called()
        recorder.assert_not_called()

    def test_transient_failure_records_attempt_but_not_terminal_delivery(self):
        subscription = {"endpoint_hash": "abc", "created_at": "2026-08-30T03:00:00+00:00"}
        event = {
            "event_key": "trend:91",
            "title": "DNB · Høy aktivitet",
            "body": "volum 2.0× normalt",
            "url": "/stock?ticker=DNB",
            "created_at": "2026-08-30T03:10:00+00:00",
        }
        with (
            patch.object(push, "_ready", return_value=True),
            patch.object(push, "_subscriptions", return_value=[subscription]),
            patch.object(push, "_event_rows", return_value=[event]),
            patch.object(push, "_delivered", return_value=False),
            patch.object(push, "_retry_allowed", return_value=True),
            patch.object(push, "_send", return_value=(False, "http_503")),
            patch.object(push, "_record_attempt") as attempt_recorder,
            patch.object(push, "_record_delivery") as recorder,
        ):
            result = push.dispatch_once()

        self.assertEqual(result["attempted"], 1)
        self.assertEqual(result["sent"], 0)
        attempt_recorder.assert_called_once_with("trend:91", "abc", "http_503")
        recorder.assert_not_called()

    def test_permanent_failure_is_terminal_for_event_endpoint_pair(self):
        subscription = {"endpoint_hash": "abc", "created_at": "2026-08-30T03:00:00+00:00"}
        event = {
            "event_key": "trend:92",
            "title": "DNB · Signalendring",
            "body": "ny signalstatus",
            "url": "/stock?ticker=DNB",
            "created_at": "2026-08-30T03:10:00+00:00",
        }
        with (
            patch.object(push, "_ready", return_value=True),
            patch.object(push, "_subscriptions", return_value=[subscription]),
            patch.object(push, "_event_rows", return_value=[event]),
            patch.object(push, "_delivered", return_value=False),
            patch.object(push, "_retry_allowed", return_value=True),
            patch.object(push, "_send", return_value=(False, "http_401")),
            patch.object(push, "_record_attempt") as attempt_recorder,
            patch.object(push, "_record_delivery") as recorder,
        ):
            result = push.dispatch_once()

        self.assertEqual(result["attempted"], 1)
        self.assertEqual(result["sent"], 0)
        attempt_recorder.assert_called_once_with("trend:92", "abc", "http_401")
        recorder.assert_called_once_with("trend:92", "abc", "http_401")

    def test_retry_budget_blocks_dispatch_without_calling_sender(self):
        subscription = {"endpoint_hash": "abc", "created_at": "2026-08-30T03:00:00+00:00"}
        event = {
            "event_key": "trend:93",
            "title": "DNB · Høy aktivitet",
            "body": "volum 2.0× normalt",
            "url": "/stock?ticker=DNB",
            "created_at": "2026-08-30T03:10:00+00:00",
        }
        with (
            patch.object(push, "_ready", return_value=True),
            patch.object(push, "_subscriptions", return_value=[subscription]),
            patch.object(push, "_event_rows", return_value=[event]),
            patch.object(push, "_delivered", return_value=False),
            patch.object(push, "_retry_allowed", return_value=False),
            patch.object(push, "_send") as sender,
            patch.object(push, "_record_attempt") as attempt_recorder,
            patch.object(push, "_record_delivery") as recorder,
        ):
            result = push.dispatch_once()

        self.assertEqual(result["attempted"], 0)
        self.assertEqual(result["sent"], 0)
        sender.assert_not_called()
        attempt_recorder.assert_not_called()
        recorder.assert_not_called()


if __name__ == "__main__":
    unittest.main()
