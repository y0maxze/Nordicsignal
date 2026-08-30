from trend_reversal_runtime import calculate_reversal


def _rows(closes, volumes=None):
    if volumes is None:
        volumes = [100_000] * len(closes)
    return [{"close": c, "volume": v} for c, v in zip(closes, volumes)]


def test_insufficient_history_is_explicit():
    result = calculate_reversal(_rows([10 + i * 0.1 for i in range(20)]))
    assert result["score"] is None
    assert result["regime"] == "INSUFFICIENT_DATA"


def test_strong_recovery_scores_as_reversal_or_uptrend():
    falling = [100 - i * 1.5 for i in range(35)]
    base = [48, 47, 46.5, 47, 47.5, 48, 48.5, 49, 49.5, 50]
    recovery = [51, 52, 53, 54, 55, 56, 57, 58, 59, 61, 63, 65, 67, 69, 71]
    closes = falling + base + recovery
    volumes = [100_000] * (len(closes) - 1) + [230_000]
    result = calculate_reversal(_rows(closes, volumes))
    assert result["score"] >= 55
    assert result["regime"] in ("EARLY_REVERSAL", "CONFIRMED_UPTREND")
    assert result["metrics"]["volume_ratio"] >= 2.0
    assert result["metrics"]["raw_volume_ratio"] >= 2.0
    assert result["metrics"]["volume_confirmation"] == "STRONG"
    assert result["metrics"]["bullish_day"] is True


def test_high_volume_red_day_is_not_bullish_confirmation():
    closes = [50 + i * 0.2 for i in range(59)] + [59.0]
    volumes = [100_000] * 59 + [250_000]
    result = calculate_reversal(_rows(closes, volumes))
    assert result["metrics"]["raw_volume_ratio"] >= 2.0
    assert result["metrics"]["volume_ratio"] is None
    assert result["metrics"]["volume_confirmation"] == "NONE"
    assert result["metrics"]["bullish_day"] is False
    assert "Strong bullish volume expansion" not in result["reasons"]


def test_weak_falling_series_does_not_get_false_positive():
    closes = [120 - i * 0.7 for i in range(60)]
    result = calculate_reversal(_rows(closes))
    assert result["score"] < 35
    assert result["regime"] == "FALLING_OR_WEAK"
