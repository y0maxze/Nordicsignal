import smart_capital_research as research


def sample(i, excess):
    return {
        "event_id": f"e{i}",
        "published_at": f"2026-01-{i:02d}T08:00:00Z",
        "forward_return_pct": {"5": excess + 1, "20": excess + 2, "60": excess + 3},
        "excess_return_pct": {"5": excess, "20": excess, "60": excess},
        "max_drawdown_pct": -abs(excess),
    }


def test_research_summary_is_score_neutral_and_uses_required_horizons():
    result = research.summarize([sample(i, float(i % 3 - 1)) for i in range(1, 21)])
    assert set(result["horizons"]) == {"5", "20", "60"}
    assert result["horizons"]["5"]["n"] == 20
    assert result["horizons"]["5"]["evidence_status"] == "research_ready"
    assert "No production score" in result["policy"]


def test_small_sample_stays_insufficient():
    result = research.summarize([sample(1, 2.0), sample(2, -1.0)])
    assert result["horizons"]["20"]["evidence_status"] == "insufficient"


def test_hit_rate_and_confidence_interval_are_reported():
    result = research.summarize([sample(i, 1.0 if i <= 15 else -1.0) for i in range(1, 21)])
    assert result["horizons"]["5"]["excess_hit_rate_pct"] == 75.0
    assert len(result["horizons"]["5"]["mean_excess_ci95_pct"]) == 2


def test_holdout_is_chronological_not_random():
    samples = [sample(i, 0.0) for i in range(1, 9)]
    train, holdout = research.holdout_split(list(reversed(samples)), 0.25)
    assert [x["event_id"] for x in train] == [f"e{i}" for i in range(1, 7)]
    assert [x["event_id"] for x in holdout] == ["e7", "e8"]
