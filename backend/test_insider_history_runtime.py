import sqlite3

import insider_history_runtime as history_runtime


def _connect_factory(path):
    def connect():
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        return conn
    return connect


def test_persisted_history_keeps_transfer_context(tmp_path, monkeypatch):
    monkeypatch.setattr(history_runtime, "connect", _connect_factory(str(tmp_path / "insider-history.db")))
    history_runtime.ensure_table()

    inserted = history_runtime.persist_items([
        {
            "ticker": "TEST",
            "company": "Test ASA",
            "person": "Example Insider",
            "related_primary_insider": "Example Insider",
            "role": "Board member",
            "direction": "buy",
            "activity_type": "primary_insider_trade",
            "shares": 160000,
            "price": 26.75,
            "trade_date": "2026-08-20",
            "internal_transfer": True,
            "economic_exposure_unchanged": True,
            "title": "Internal transfer",
            "summary": "Combined direct and indirect economic exposure is unchanged.",
            "source": "Euronext Oslo Børs Newspoint",
            "url": "https://example.test/transfer",
            "node_id": "123",
        }
    ])
    assert inserted == 1

    rows = history_runtime.history(ticker="TEST")
    assert len(rows) == 1
    row = rows[0]
    assert row["actor"] == "Example Insider"
    assert row["internal_transfer"] == 1
    assert row["economic_exposure_unchanged"] == 1
    assert "unchanged" in row["summary"].lower()


def test_history_deduplicates_same_verified_trade(tmp_path, monkeypatch):
    monkeypatch.setattr(history_runtime, "connect", _connect_factory(str(tmp_path / "dedupe.db")))
    history_runtime.ensure_table()
    trade = {
        "ticker": "TEST",
        "person": "Example Insider",
        "direction": "buy",
        "shares": 1000,
        "price": 20.0,
        "trade_date": "2026-08-20",
        "url": "https://example.test/trade",
        "node_id": "456",
    }
    assert history_runtime.persist_items([trade]) == 1
    assert history_runtime.persist_items([trade]) == 0
    assert len(history_runtime.history(ticker="TEST")) == 1
