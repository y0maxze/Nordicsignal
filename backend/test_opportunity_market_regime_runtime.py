from datetime import date, timedelta

import opportunity_market_regime_runtime as regime


def _rows(count=90, start=100.0, step=0.5):
    first = date(2026, 1, 1)
    return [
        {"date": (first + timedelta(days=i)).isoformat(), "close": start + step * i}
        for i in range(count)
    ]


def _event(event_date):
    return {
        "id": 1,
        "observed_at": f"{event_date}T12:00:00+00:00",
        "payload": "{}",
    }


def test_regime_uses_only_days_before_event_no_lookahead(monkeypatch):
    rows = _rows(count=81, start=100.0, step=0.6)
    event_date = rows[-1]["date"]
    monkeypatch.setattr(regime.tracking, "_entry_date_from_event", lambda event: event_date)

    baseline = regime._classify_regime(_event(event_date), rows)
    assert baseline["regime"] == "RISK_ON"
    assert baseline["regime_asof_date"] == rows[-2]["date"]

    # Event-day close is not known when the signal is generated and must not affect
    # the regime label. An absurd event-day move therefore leaves classification unchanged.
    mutated = [dict(row) for row in rows]
    mutated[-1]["close"] = 1.0
    after = regime._classify_regime(_event(event_date), mutated)
    assert after["regime"] == baseline["regime"]
    assert after["benchmark_ret20_pct"] == baseline["benchmark_ret20_pct"]
    assert after["benchmark_ma50_gap_pct"] == baseline["benchmark_ma50_gap_pct"]


def test_regime_detects_risk_off(monkeypatch):
    rows = _rows(count=81, start=160.0, step=-0.6)
    event_date = rows[-1]["date"]
    monkeypatch.setattr(regime.tracking, "_entry_date_from_event", lambda event: event_date)
    result = regime._classify_regime(_event(event_date), rows)
    assert result["regime"] == "RISK_OFF"
    assert result["benchmark_ret20_pct"] < -regime.REGIME_RETURN_THRESHOLD_PCT
    assert result["benchmark_ma50_gap_pct"] < 0


def test_regime_gate_passes_two_supported_regimes():
    rows = ([{"regime": "RISK_ON"}] * 10) + ([{"regime": "NEUTRAL"}] * 10)
    result = regime._regime_stats(rows, minimum_sample=20)
    assert result["status"] == "PASS"
    assert result["supported_regimes"] == ["NEUTRAL", "RISK_ON"]
    assert result["largest_regime_share_pct"] == 50.0


def test_regime_gate_rejects_concentrated_market_environment():
    rows = ([{"regime": "RISK_ON"}] * 16) + ([{"regime": "NEUTRAL"}] * 4)
    result = regime._regime_stats(rows, minimum_sample=20)
    assert result["status"] == "REVIEW"
    assert result["checks"]["supported_regimes"] is False
    assert result["checks"]["regime_concentration"] is False
    assert result["largest_regime_share_pct"] == 80.0


def test_regime_gate_collects_until_context_sample_is_complete():
    rows = ([{"regime": "RISK_ON"}] * 10) + ([{"regime": "NEUTRAL"}] * 9) + [{"regime": None}]
    result = regime._regime_stats(rows, minimum_sample=20)
    assert result["status"] == "COLLECTING_DATA"
    assert result["observations"] == 20
    assert result["classified_observations"] == 19
    assert result["checks"]["classified_sample"] is False


def test_market_adjusted_alpha_summary():
    rows = [
        {"excess_return_pct": 2.0, "benchmark_return_pct": 1.0},
        {"excess_return_pct": -1.0, "benchmark_return_pct": 2.0},
        {"excess_return_pct": 3.0, "benchmark_return_pct": -0.5},
    ]
    result = regime._alpha_stats(rows)
    assert result["n"] == 3
    assert result["median_excess_return_pct"] == 2.0
    assert result["positive_excess_rate_pct"] == 66.67


def test_market_return_matches_close_to_close_window():
    rows = [
        {"date": "2026-01-01", "close": 100.0},
        {"date": "2026-01-02", "close": 102.0},
        {"date": "2026-01-03", "close": 105.0},
    ]
    target, value = regime._market_return_for_target(100.0, "2026-01-03", rows)
    assert target["date"] == "2026-01-03"
    assert round(value, 6) == 5.0
