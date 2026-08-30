import sqlite3

import opportunity_tracking_runtime as tracking
import opportunity_performance_v2_runtime  # noqa: F401 - installs measurement v2


def _connect_factory(path):
    def connect():
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        return conn
    return connect


def _result(label, score=85, ticker="TEST", close_date="2026-01-02"):
    return {
        "ticker": ticker,
        "status": "ok",
        # Deliberately later than the market close date to cover weekend/after-close scans.
        "generated_at": "2026-01-04T16:30:00+00:00",
        "opportunity": {
            "label": label,
            "score": score,
            "components": {
                "reversal_score": 80,
                "volume_ratio": 2.1,
                "insider_label": "STRONG",
                "independent_buyers": 4,
                "buy_value_nok": 1_500_000,
            },
        },
        "reversal": {"metrics": {"close": 123.45, "close_date": close_date}},
    }


def test_first_observation_is_baseline_then_transition_emits(tmp_path, monkeypatch):
    monkeypatch.setattr(tracking, "connect", _connect_factory(str(tmp_path / "opportunity.db")))
    tracking._ensure_schema()

    first = tracking.record_opportunity(_result("REVERSAL_CANDIDATE", 45), "Test ASA")
    assert first["emitted"] is False

    second = tracking.record_opportunity(_result("EARLY_OPPORTUNITY_HIGH", 95), "Test ASA")
    assert second["emitted"] is True

    conn = tracking.connect()
    try:
        row = conn.execute("SELECT * FROM opportunity_events").fetchone()
    finally:
        conn.close()
    assert row["previous_label"] == "REVERSAL_CANDIDATE"
    assert row["label"] == "EARLY_OPPORTUNITY_HIGH"
    assert row["name"] == "Test ASA"
    assert row["entry_price"] == 123.45
    assert row["reversal_score"] == 80
    assert row["volume_ratio"] == 2.1
    assert row["event_key"].startswith("2026-01-02:")


def test_forward_returns_anchor_to_market_close_date_not_scan_date(tmp_path, monkeypatch):
    monkeypatch.setattr(tracking, "connect", _connect_factory(str(tmp_path / "forward.db")))
    tracking._ensure_schema()
    tracking.record_opportunity(_result("REVERSAL_CANDIDATE", 45), "Test ASA")
    tracking.record_opportunity(_result("EARLY_OPPORTUNITY_HIGH", 95), "Test ASA")

    rows = [
        {"date": f"2026-{1 + (i // 28):02d}-{1 + (i % 28):02d}", "close": 122.45 + i}
        for i in range(70)
    ]
    # 2026-01-02 is index 1 and has close 123.45, matching the stored entry price.
    settled = tracking.settle_forward_returns("TEST", rows=rows)
    assert settled == 5

    conn = tracking.connect()
    try:
        values = conn.execute(
            "SELECT horizon_days,target_date,target_price,return_pct FROM opportunity_forward_returns ORDER BY horizon_days"
        ).fetchall()
    finally:
        conn.close()
    assert [row["horizon_days"] for row in values] == [1, 5, 10, 20, 60]
    assert values[0]["target_date"] == rows[2]["date"]
    assert values[1]["target_date"] == rows[6]["date"]
    assert all(row["return_pct"] > 0 for row in values)


def test_scan_one_calls_tracked_live_once(monkeypatch):
    calls = []

    def fake_live(ticker):
        calls.append(ticker)
        return {"ticker": ticker, "status": "ok"}

    monkeypatch.setattr(tracking.opportunity, "live_opportunity", fake_live)
    result = tracking._scan_one({"ticker": "TEST", "name": "Test ASA"})
    assert result["ticker"] == "TEST"
    assert calls == ["TEST"]
