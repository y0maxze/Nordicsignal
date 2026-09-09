from datetime import datetime, timezone

import event_outcome_runtime as outcomes


def test_after_close_event_moves_to_next_market_day():
    # 15:00 UTC = 17:00 Oslo during summer, after the 16:20 close.
    assert outcomes._target_market_date("2026-09-09T15:00:00+00:00") == "2026-09-10"


def test_before_close_event_can_use_same_day_close():
    # 10:00 UTC = 12:00 Oslo during summer.
    assert outcomes._target_market_date("2026-09-09T10:00:00+00:00") == "2026-09-09"


def test_start_index_uses_first_available_trading_day():
    rows = [
        {"date": "2026-09-11", "close": 100.0},
        {"date": "2026-09-14", "close": 101.0},
    ]
    assert outcomes._start_index(rows, "2026-09-12") == 1


def test_path_stats_are_measured_from_entry_close():
    rows = [
        {"date": "2026-01-01", "close": 100.0},
        {"date": "2026-01-02", "close": 95.0},
        {"date": "2026-01-03", "close": 110.0},
    ]
    dd, ru = outcomes._path_stats(rows, 0, 2)
    assert round(dd, 6) == -5.0
    assert round(ru, 6) == 10.0


def test_benchmark_return_uses_same_trading_horizon():
    rows = [
        {"date": "2026-01-01", "close": 100.0},
        {"date": "2026-01-02", "close": 102.0},
        {"date": "2026-01-05", "close": 104.0},
    ]
    assert round(outcomes._benchmark_return(rows, "2026-01-01", 2), 6) == 4.0


def test_build_event_evidence_keeps_measurement_policy(monkeypatch):
    monkeypatch.setattr(outcomes, "settle_event_outcomes", lambda ticker="", provider=None, benchmark_rows=None: 0)
    monkeypatch.setattr(outcomes, "evidence_samples", lambda ticker="": [])
    result = outcomes.build_event_evidence("KOG", settle=True, provider=object())
    assert result["ticker"] == "KOG"
    assert result["benchmark"] == "OSEBX"
    assert result["maturity"] == "insufficient"
    assert "does not change NordicSignal scores" in result["policy"]
    assert "after-close announcements use the next trading session" in result["method"]
