from opportunity_confluence_runtime import calculate_opportunity, _sanitize_value_rows


def _rev(score, volume, regime="EARLY_REVERSAL", raw_volume=None):
    metrics = {"volume_ratio": volume}
    if raw_volume is not None:
        metrics["raw_volume_ratio"] = raw_volume
    return {"score": score, "regime": regime, "metrics": metrics}


def _ins(label, buyers=0, value=0, points=0):
    return {"label": label, "independent_buyers": buyers, "buy_value_nok": value, "points": points}


def test_high_opportunity_requires_three_way_confluence():
    result = calculate_opportunity(_rev(82, 2.2), _ins("STRONG", buyers=4, value=1_600_000, points=6))
    assert result["label"] == "EARLY_OPPORTUNITY_HIGH"
    assert result["score"] >= 80
    assert result["components"]["evidence_count"] == 3
    assert result["score_effect"] == 0


def test_reversal_and_volume_without_insider_is_opportunity_not_high():
    result = calculate_opportunity(_rev(78, 1.7), _ins("NONE"))
    assert result["label"] == "EARLY_OPPORTUNITY"
    assert result["components"]["evidence_count"] == 2
    assert result["score"] < 80


def test_raw_high_volume_without_bullish_confirmation_does_not_count():
    result = calculate_opportunity(_rev(78, None, raw_volume=2.5), _ins("NONE"))
    assert result["components"]["volume_state"] == "NONE"
    assert result["components"]["evidence_count"] == 1
    assert result["label"] == "REVERSAL_CANDIDATE"


def test_insider_cluster_cannot_rescue_weak_trend_by_itself():
    result = calculate_opportunity(_rev(30, 2.1), _ins("STRONG", buyers=5, value=2_000_000, points=7))
    assert result["label"] == "NO_OPPORTUNITY"


def test_70_plus_with_one_confirmation_is_watch_confluence():
    result = calculate_opportunity(_rev(72, 1.6), _ins("NONE"))
    assert result["label"] == "WATCH_CONFLUENCE"


def test_insufficient_reversal_data_is_explicit():
    result = calculate_opportunity({"score": None, "metrics": {}}, _ins("STRONG", 3, 1_000_000, 5))
    assert result["score"] is None
    assert result["label"] == "INSUFFICIENT_DATA"


def test_implausible_insider_price_keeps_trade_but_rejects_value():
    rows = [{
        "person": "Example CEO",
        "transaction_type": "buy",
        "trade_date": "2026-08-20",
        "shares": 37500,
        "price": 1_445_401.70,
        "transaction_value": 54_202_563_750.0,
    }]
    history = [
        {"date": "2026-08-19", "close": 24.65},
        {"date": "2026-08-20", "close": 23.50},
    ]
    safe, rejected = _sanitize_value_rows(rows, history)
    assert len(safe) == 1
    assert len(rejected) == 1
    assert safe[0]["transaction_type"] == "buy"
    assert safe[0]["shares"] == 37500
    assert safe[0]["price"] is None
    assert safe[0]["transaction_value"] is None
    assert safe[0]["value_quality"] == "rejected_market_price_outlier"


def test_corrupt_explicit_value_falls_back_to_plausible_shares_times_price():
    rows = [{
        "person": "Example CEO",
        "transaction_type": "buy",
        "trade_date": "2026-08-20",
        "shares": 37500,
        "price": 26.65,
        "transaction_value": 54_202_563_750.0,
        "display_transaction_value": 54_202_563_750.0,
    }]
    history = [{"date": "2026-08-20", "close": 23.50}]
    safe, rejected = _sanitize_value_rows(rows, history)
    assert len(rejected) == 1
    assert rejected[0]["reason"] == "value_inconsistent_with_shares_price"
    assert safe[0]["price"] == 26.65
    assert safe[0]["transaction_value"] is None
    assert safe[0]["display_transaction_value"] is None
    assert safe[0]["shares"] * safe[0]["price"] == 999375.0
    assert safe[0]["value_quality"] == "rejected_value_inconsistent_with_shares_price"


def test_plausible_insider_price_preserves_value():
    rows = [{
        "person": "Example CEO",
        "transaction_type": "buy",
        "trade_date": "2026-08-20",
        "shares": 37500,
        "price": 26.65,
        "transaction_value": 999375.0,
    }]
    history = [{"date": "2026-08-20", "close": 23.50}]
    safe, rejected = _sanitize_value_rows(rows, history)
    assert rejected == []
    assert safe[0]["price"] == 26.65
    assert safe[0]["transaction_value"] == 999375.0
    assert safe[0]["value_quality"] == "market_price_plausible"
