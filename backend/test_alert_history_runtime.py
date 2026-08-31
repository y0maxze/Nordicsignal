from concurrent.futures import ThreadPoolExecutor
import sqlite3

import alert_history_runtime as history


def _db_factory(path):
    def connect():
        conn = sqlite3.connect(path, timeout=30)
        conn.row_factory = sqlite3.Row
        return conn
    return connect


def test_insider_mobile_notification_is_classified():
    payload = {
        "tag": "local:moreld|2026-08-31",
        "title": "MORELD ASA · Insideraktivitet",
        "body": "4 kjøp · 1 salg · a close associate of Geir Austigard, Jonathan William Logan",
        "url": "/insider",
    }
    assert history._classify(payload) == "INSIDER"


def test_managers_transaction_notification_is_insider():
    payload = {
        "tag": "local:magnora|2026-08-31",
        "title": "MAGNORA DATA CENTER ASA",
        "body": "2 kjøp · 0 salg · Managers' transaction Lars Schedin",
        "url": "/insider",
    }
    assert history._classify(payload) == "INSIDER"


def test_high_activity_push_is_activity():
    payload = {
        "tag": "trend:42",
        "title": "DNB · Høy aktivitet · positivt kursmomentum",
        "body": "5d +1.8% · volum 2.3× normalt",
        "url": "/stock?ticker=DNB",
    }
    assert history._classify(payload) == "ACTIVITY"
    assert history._ticker_from_payload(payload) == "DNB"


def test_opportunity_has_priority_over_generic_insider_words():
    payload = {
        "tag": "opportunity:9",
        "title": "LSG · Early Opportunity",
        "body": "score 72 · insider strong · 3 kjøpere",
        "url": "/stock?ticker=LSG",
    }
    assert history._classify(payload) == "OPPORTUNITY"


def test_successful_payload_is_idempotent_across_devices(tmp_path, monkeypatch):
    monkeypatch.setattr(history, "connect", _db_factory(tmp_path / "alerts.sqlite"))
    monkeypatch.setattr(history, "USING_POSTGRES", False)
    history._ensure_schema()
    payload = {
        "tag": "trend:101",
        "title": "AKRBP · Høy aktivitet · positivt kursmomentum",
        "body": "5d +1.9% · volum 1.9× normalt",
        "url": "/stock?ticker=AKRBP",
        "timestamp": "2026-08-31T17:30:00+00:00",
    }
    assert history._record_successful_payload(payload) is True
    assert history._record_successful_payload(payload) is True
    data = history.list_alerts(limit=20)
    assert data["total"] == 1
    assert data["unread"] == 1
    assert data["items"][0]["ticker"] == "AKRBP"
    assert data["items"][0]["delivery_count"] == 2

    alert_id = data["items"][0]["id"]
    history.mark_read(alert_id)
    assert history.list_alerts(limit=20)["unread"] == 0


def test_successful_payload_counts_concurrent_deliveries_atomically(tmp_path, monkeypatch):
    monkeypatch.setattr(history, "connect", _db_factory(tmp_path / "alerts.sqlite"))
    monkeypatch.setattr(history, "USING_POSTGRES", False)
    history._ensure_schema()
    payload = {
        "tag": "opportunity:501",
        "title": "LSG · Early Opportunity",
        "body": "score 74 · reversal 81 · volum 2.1×",
        "url": "/stock?ticker=LSG",
        "timestamp": "2026-09-01T00:15:00+00:00",
    }
    deliveries = 12
    with ThreadPoolExecutor(max_workers=deliveries) as pool:
        results = list(pool.map(lambda _: history._record_successful_payload(payload), range(deliveries)))

    assert results == [True] * deliveries
    data = history.list_alerts(limit=20)
    assert data["total"] == 1
    assert data["items"][0]["event_key"] == "opportunity:501"
    assert data["items"][0]["delivery_count"] == deliveries


def test_test_push_is_not_persisted(tmp_path, monkeypatch):
    monkeypatch.setattr(history, "connect", _db_factory(tmp_path / "alerts.sqlite"))
    monkeypatch.setattr(history, "USING_POSTGRES", False)
    history._ensure_schema()
    assert history._record_successful_payload({
        "tag": "push-test:1",
        "title": "NordicSignal test",
        "body": "Push-varsler fungerer.",
        "url": "/mobile",
    }) is False
    assert history.list_alerts()["total"] == 0


def test_external_click_url_is_not_stored():
    assert history._safe_url("https://example.com/steal") == "/alerts"
    assert history._safe_url("//example.com") == "/alerts"
    assert history._safe_url("/stock?ticker=LSG") == "/stock?ticker=LSG"
