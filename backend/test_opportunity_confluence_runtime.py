from opportunity_confluence_runtime import calculate_opportunity


def _rev(score, volume, regime="EARLY_REVERSAL"):
    return {"score": score, "regime": regime, "metrics": {"volume_ratio": volume}}


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
