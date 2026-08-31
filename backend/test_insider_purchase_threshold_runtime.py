import insider_purchase_threshold_runtime as runtime


def row(person, value, action="buy", day="2026-08-30"):
    return {
        "person": person,
        "transaction_type": action,
        "trade_date": day,
        "display_transaction_value": value,
        "shares": 1000,
        "price": value / 1000 if value else 0,
    }


def test_small_buys_below_100k_do_not_count_as_signal():
    result = runtime.strict_analyze({"items": [row("A One", 36_000), row("B Two", 99_999)]})
    signal = result["insider_signal_v2"]
    assert signal["buy_count"] == 0
    assert signal["independent_buyers"] == 0
    assert signal["buy_value_nok"] == 0
    assert signal["ignored_small_buy_count"] == 2
    assert signal["ignored_small_buy_value_nok"] == 135_999
    assert signal["label"] == "NONE"


def test_100k_is_qualified_but_not_meaningful():
    result = runtime.strict_analyze({"items": [row("A One", 100_000)]})
    signal = result["insider_signal_v2"]
    assert signal["buy_count"] == 1
    assert signal["independent_buyers"] == 1
    assert signal["buy_value_nok"] == 100_000
    assert signal["meaningful_buy_count"] == 0
    assert signal["points"] == 1


def test_500k_is_meaningful_purchase():
    result = runtime.strict_analyze({"items": [row("A One", 500_000)]})
    signal = result["insider_signal_v2"]
    assert signal["meaningful_buy_count"] == 1
    assert signal["buy_value_nok"] == 500_000
    assert signal["points"] == 2
    assert any("500k" in reason for reason in signal["reasons"])


def test_cluster_counts_only_qualified_buyers():
    result = runtime.strict_analyze({"items": [
        row("A One", 36_000),
        row("B Two", 100_000),
        row("C Three", 150_000),
        row("D Four", 500_000),
    ]})
    signal = result["insider_signal_v2"]
    assert signal["independent_buyers"] == 3
    assert signal["buy_count"] == 3
    assert signal["ignored_small_buy_count"] == 1
    assert signal["buy_value_nok"] == 750_000
    assert signal["meaningful_buy_count"] == 1
    assert signal["points"] == 4
    assert signal["label"] == "POSITIVE"


def test_total_qualified_value_over_1m_gets_strong_value_points():
    result = runtime.strict_analyze({"items": [row("A One", 550_000), row("B Two", 550_000)]})
    signal = result["insider_signal_v2"]
    assert signal["buy_value_nok"] == 1_100_000
    assert signal["meaningful_buy_count"] == 2
    assert signal["points"] == 4
    assert any("NOK 1m" in reason for reason in signal["reasons"])


def test_threshold_policy_has_no_main_score_effect():
    signal = runtime.strict_analyze({"items": [row("A One", 500_000)]})["insider_signal_v2"]
    assert signal["minimum_signal_buy_nok"] == 100_000
    assert signal["meaningful_buy_threshold_nok"] == 500_000
    assert signal["score_effect"] == 0
