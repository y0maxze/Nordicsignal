import sqlite3

import opportunity_performance_v2_runtime as performance
import opportunity_tracking_runtime as tracking


def _connect_factory(path):
    def connect():
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        return conn
    return connect


def test_stats_reports_median_and_small_sample_warning():
    result = performance._stats([1.0, 3.0, 10.0], 5)
    assert result["n"] == 3
    assert result["mean_return_pct"] == 4.667
    assert result["median_return_pct"] == 3.0
    assert result["positive_rate_pct"] == 100.0
    assert result["settled_event_pct"] == 60.0
    assert result["sample_status"] == "insufficient"
    assert result["minimum_sample_size"] == 20


def test_performance_groups_returns_by_opportunity_label(tmp_path, monkeypatch):
    monkeypatch.setattr(tracking, "connect", _connect_factory(str(tmp_path / "performance.db")))
    tracking._ensure_schema()

    conn = tracking.connect()
    try:
        events = [
            ("AAA", "AAA ASA", "NONE", "WATCH_CONFLUENCE", 61, 100.0, 65, 1.6, "POSITIVE", 3, 0, "{}", "2026-01-02T10:00:00+00:00", "2026-01-02T10:00:00+00:00", "a"),
            ("BBB", "BBB ASA", "WATCH_CONFLUENCE", "EARLY_OPPORTUNITY_HIGH", 88, 200.0, 82, 2.1, "STRONG", 4, 1_500_000, "{}", "2026-01-02T10:00:00+00:00", "2026-01-02T10:00:00+00:00", "b"),
        ]
        for values in events:
            conn.execute(
                "INSERT INTO opportunity_events(ticker,name,previous_label,label,score,entry_price,reversal_score,volume_ratio,insider_label,independent_buyers,buy_value_nok,payload,observed_at,created_at,event_key) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                values,
            )
        ids = conn.execute("SELECT id,label FROM opportunity_events ORDER BY id").fetchall()
        conn.execute(
            "INSERT INTO opportunity_forward_returns(event_id,horizon_days,target_date,target_price,return_pct,settled_at) VALUES(?,?,?,?,?,?)",
            (ids[0]["id"], 5, "2026-01-09", 102.0, 2.0, "2026-01-09T18:00:00+00:00"),
        )
        conn.execute(
            "INSERT INTO opportunity_forward_returns(event_id,horizon_days,target_date,target_price,return_pct,settled_at) VALUES(?,?,?,?,?,?)",
            (ids[1]["id"], 5, "2026-01-09", 210.0, 5.0, "2026-01-09T18:00:00+00:00"),
        )
        conn.execute(
            "INSERT INTO opportunity_forward_returns(event_id,horizon_days,target_date,target_price,return_pct,settled_at) VALUES(?,?,?,?,?,?)",
            (ids[1]["id"], 1, "2026-01-05", 204.0, 2.0, "2026-01-05T18:00:00+00:00"),
        )
        conn.commit()
    finally:
        conn.close()

    report = performance.opportunity_performance()
    assert report["events"] == 2
    assert list(report["horizons"].keys()) == ["1", "5", "10", "20", "60"]
    assert report["horizons"]["5"]["n"] == 2
    assert report["horizons"]["5"]["mean_return_pct"] == 3.5
    assert report["horizons"]["5"]["median_return_pct"] == 3.5
    assert report["by_label"]["WATCH_CONFLUENCE"]["horizons"]["5"]["mean_return_pct"] == 2.0
    assert report["by_label"]["EARLY_OPPORTUNITY_HIGH"]["horizons"]["5"]["mean_return_pct"] == 5.0
    assert report["by_label"]["EARLY_OPPORTUNITY_HIGH"]["horizons"]["1"]["n"] == 1
    assert report["calibration"]["ready"] is False
    assert report["calibration"]["minimum_sample_size"] == 20


def test_install_extends_tracker_without_changing_signal_thresholds():
    performance.install()
    assert tracking.HORIZONS == (1, 5, 10, 20, 60)
    assert tracking.opportunity_performance is performance.opportunity_performance
