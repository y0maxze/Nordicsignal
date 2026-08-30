from datetime import datetime, timedelta, timezone
import json
import sqlite3

import opportunity_data_coverage_runtime as coverage
import opportunity_tracking_runtime as tracking


def _connect_factory(path):
    def connect():
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        return conn
    return connect


def _result(label, ticker="TEST", score=85):
    return {
        "ticker": ticker,
        "status": "ok",
        "generated_at": "2026-08-30T08:00:00+00:00",
        "opportunity": {
            "label": label,
            "score": score,
            "components": {
                "reversal_score": 81,
                "volume_ratio": 1.8,
                "insider_label": "POSITIVE",
                "independent_buyers": 3,
                "buy_value_nok": 1_200_000,
            },
        },
        "reversal": {"metrics": {"close": 101.0, "close_date": "2026-08-28"}},
    }


def _init_test_db(connect):
    conn = connect()
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS stocks (ticker TEXT PRIMARY KEY,name TEXT NOT NULL,sector TEXT,exchange TEXT,active INTEGER DEFAULT 1)"
        )
        conn.commit()
    finally:
        conn.close()
    tracking._ensure_schema()


def test_first_observed_qualifying_state_becomes_forward_event(tmp_path, monkeypatch):
    connect = _connect_factory(str(tmp_path / "first_seen.db"))
    monkeypatch.setattr(tracking, "connect", connect)
    _init_test_db(connect)

    first = coverage._record_first_observed(_result("EARLY_OPPORTUNITY"), "Test ASA")
    second = coverage._record_first_observed(_result("EARLY_OPPORTUNITY"), "Test ASA")

    assert first["emitted"] is True
    assert first["event_kind"] == "first_observed_qualifying_state"
    assert second["emitted"] is False

    conn = connect()
    try:
        rows = conn.execute("SELECT * FROM opportunity_events ORDER BY id").fetchall()
    finally:
        conn.close()
    assert len(rows) == 1
    assert rows[0]["previous_label"] is None
    assert rows[0]["label"] == "EARLY_OPPORTUNITY"
    assert rows[0]["event_key"] == "2026-08-28:FIRST_OBSERVED->EARLY_OPPORTUNITY"
    payload = json.loads(rows[0]["payload"])
    assert payload["tracking_meta"]["event_kind"] == "first_observed_qualifying_state"


def test_first_observed_nonqualifying_state_remains_baseline(tmp_path, monkeypatch):
    connect = _connect_factory(str(tmp_path / "baseline.db"))
    monkeypatch.setattr(tracking, "connect", connect)
    _init_test_db(connect)

    result = coverage._record_first_observed(_result("REVERSAL_CANDIDATE", score=45), "Test ASA")
    assert result["emitted"] is False

    conn = connect()
    try:
        count = conn.execute("SELECT COUNT(*) AS n FROM opportunity_events").fetchone()["n"]
        state = conn.execute("SELECT label FROM opportunity_state WHERE ticker='TEST'").fetchone()["label"]
    finally:
        conn.close()
    assert count == 0
    assert state == "REVERSAL_CANDIDATE"


def _history(turnover=5_000_000.0, bars=100, end=None):
    end = end or datetime(2026, 8, 30, tzinfo=timezone.utc)
    close = 10.0
    volume = turnover / close
    start = end - timedelta(days=bars - 1)
    return [
        {
            "date": (start + timedelta(days=i)).isoformat(),
            "close": close,
            "volume": volume,
        }
        for i in range(bars)
    ]


def test_market_quality_requires_history_recency_and_liquidity():
    now = datetime(2026, 8, 30, tzinfo=timezone.utc)
    good = coverage._market_quality(_history(), now=now)
    thin = coverage._market_quality(_history(turnover=250_000.0), now=now)
    short = coverage._market_quality(_history(bars=30), now=now)
    stale = coverage._market_quality(_history(end=datetime(2026, 7, 1, tzinfo=timezone.utc)), now=now)

    assert good["qualified"] is True
    assert good["median_daily_turnover_nok"] >= coverage.MIN_MEDIAN_DAILY_TURNOVER_NOK
    assert thin["reason"] == "below_turnover_floor"
    assert short["reason"] == "insufficient_history"
    assert stale["reason"] == "stale_market_data"


class _FakeProvider:
    BASES = ("https://fake.yahoo",)
    BASE = BASES[0]

    def _get(self, url, params=None):
        return {
            "quotes": [
                {
                    "quoteType": "EQUITY",
                    "symbol": "DISC.OL",
                    "longname": "Liquid Discovery ASA",
                    "exchange": "OSL",
                    "exchDisp": "Oslo",
                    "market": "no_market",
                }
            ]
        }

    def historical(self, ticker, period="6m"):
        assert ticker == "DISC"
        return _history()


def test_discovery_adds_only_screened_inactive_metadata(tmp_path, monkeypatch):
    connect = _connect_factory(str(tmp_path / "discovery.db"))
    monkeypatch.setattr(tracking, "connect", connect)
    _init_test_db(connect)
    conn = connect()
    try:
        conn.execute(
            "INSERT INTO stocks(ticker,name,sector,exchange,active) VALUES(?,?,?,?,1)",
            ("CORE", "Core ASA", "Core", "Oslo Børs"),
        )
        conn.commit()
    finally:
        conn.close()

    monkeypatch.setattr(
        coverage.insider_market_v2_runtime,
        "_announcements",
        lambda days: ([{"company": "Liquid Discovery ASA", "ticker": None}], {"source": "test"}),
    )
    rows, meta = coverage._build_discovery_universe(provider=_FakeProvider())

    assert [row["ticker"] for row in rows] == ["DISC"]
    assert rows[0]["quality"]["qualified"] is True
    assert meta["qualified"] == 1

    conn = connect()
    try:
        discovery = conn.execute("SELECT ticker,name,active FROM stocks WHERE ticker='DISC'").fetchone()
        core = conn.execute("SELECT active FROM stocks WHERE ticker='CORE'").fetchone()
    finally:
        conn.close()
    assert discovery["name"] == "Liquid Discovery ASA"
    assert discovery["active"] == 0
    assert core["active"] == 1


def test_rotating_discovery_slice_limits_provider_load(monkeypatch):
    monkeypatch.setattr(coverage, "_DISCOVERY_CURSOR", 0)
    rows = [{"ticker": f"T{i}"} for i in range(20)]
    first = coverage._rotating_discovery_slice(rows)
    second = coverage._rotating_discovery_slice(rows)
    assert len(first) == coverage.DISCOVERY_PER_SCAN
    assert len(second) == coverage.DISCOVERY_PER_SCAN
    assert {row["ticker"] for row in first}.isdisjoint({row["ticker"] for row in second})
