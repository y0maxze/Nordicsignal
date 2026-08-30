import sqlite3

import opportunity_tracking_runtime as tracking


def _connect_factory(path):
    def connect():
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        return conn
    return connect


def _result(label, score=85, ticker="TEST"):
    return {
        "ticker": ticker,
        "status": "ok",
        "generated_at": "2026-01-02T16:30:00+00:00",
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
        "reversal": {"metrics": {"close": 123.45}},
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
    assert row["entry_price"] == 123.45
    assert row["reversal_score"] == 80
    assert row["volume_ratio"] == 2.1


def test_forward_returns_settle_on_trading_day_horizons(tmp_path, monkeypatch):
    monkeypatch.setattr(tracking, "connect", _connect_factory(str(tmp_path / "forward.db")))
    tracking._ensure_schema()
    tracking.record_opportunity(_result("REVERSAL_CANDIDATE", 45), "Test ASA")
    tracking.record_opportunity(_result("EARLY_OPPORTUNITY_HIGH", 95), "Test ASA")

    # Use monotonic synthetic dates to avoid depending on calendar semantics; the
    # settlement logic counts rows as trading sessions after the matched signal row.
    rows = [{"date": f"2026-{1 + (i // 28):02d}-{1 + (i % 28):02d}", "close": 123.45 + i} for i in range(70)]

    settled = tracking.settle_forward_returns("TEST", rows=rows)
    assert settled == 4

    conn = tracking.connect()
    try:
        values = conn.execute("SELECT horizon_days,return_pct FROM opportunity_forward_returns ORDER BY horizon_days").fetchall()
    finally:
        conn.close()
    assert [row["horizon_days"] for row in values] == [5, 10, 20, 60]
    assert all(row["return_pct"] > 0 for row in values)
