import high_conviction_validation_runtime as hc


def _row(i, ticker, day, match=True, buyers=0, volume="NONE", regime="NEUTRAL"):
    return {
        "id": i,
        "ticker": ticker,
        "market_date": day,
        "opportunity_label": "EARLY_OPPORTUNITY" if match else "NO_OPPORTUNITY",
        "reversal_regime": "EARLY_REVERSAL" if match else "FALLING_OR_WEAK",
        "critical_event_count": 0,
        "independent_buyers": buyers,
        "volume_confirmation": volume,
        "market_regime": regime,
    }


def test_core_rule_uses_existing_states_and_blocks_critical_event():
    row = _row(1, "KOG", "2026-09-07")
    assert hc._matches(row, "hc_core_v1") is True
    row["critical_event_count"] = 1
    assert hc._matches(row, "hc_core_v1") is False


def test_confluence_requires_two_buyers_and_volume_confirmation():
    row = _row(1, "KOG", "2026-09-07", buyers=2, volume="CONFIRMED")
    assert hc._matches(row, "hc_confluence_v1") is True
    row["independent_buyers"] = 1
    assert hc._matches(row, "hc_confluence_v1") is False


def test_episode_decorrelation_collapses_contiguous_matching_days():
    rows = [
        _row(1, "KOG", "2026-09-04"),
        _row(2, "KOG", "2026-09-07"),
        _row(3, "KOG", "2026-09-08", match=False),
        _row(4, "KOG", "2026-09-09"),
    ]
    episodes = hc._episodes(rows, "hc_core_v1")
    assert len(episodes) == 2
    assert episodes[0]["first_snapshot_id"] == 1
    assert episodes[0]["snapshot_ids"] == [1, 2]
    assert episodes[1]["first_snapshot_id"] == 4


def test_different_tickers_are_independent_episodes():
    rows = [_row(1, "KOG", "2026-09-07"), _row(2, "TEL", "2026-09-07")]
    episodes = hc._episodes(rows, "hc_core_v1")
    assert len(episodes) == 2


def test_framework_is_hard_disabled_and_walk_forward_required():
    out = hc.framework_status()
    assert out["activation_enabled"] is False
    assert out["automatic_threshold_changes"] is False
    assert out["fixed_research_gates"]["walk_forward_required"] is True
    assert out["fixed_research_gates"]["min_independent_episodes"] == 50
