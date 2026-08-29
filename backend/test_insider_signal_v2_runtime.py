from insider_signal_v2_runtime import analyze


def test_cluster_buy_is_strong_and_transfer_is_excluded():
    result = analyze({
        "items": [
            {"transaction_type": "buy", "trade_date": "2026-08-19", "actor": "CEO", "role": "CEO", "shares": 37500, "price": 26.65},
            {"transaction_type": "buy", "trade_date": "2026-08-19", "actor": "CFO", "role": "CFO", "shares": 8000, "price": 26.91},
            {"transaction_type": "buy", "trade_date": "2026-08-19", "actor": "COO", "role": "COO", "shares": 4000, "price": 26.86},
            {"transaction_type": "buy", "trade_date": "2026-08-19", "actor": "Board", "role": "Board member", "shares": 160000, "price": 26.75, "economic_exposure_unchanged": True},
        ]
    })
    signal = result["insider_signal_v2"]
    assert signal["label"] == "STRONG"
    assert signal["independent_buyers"] == 3
    assert signal["excluded_transfer_like_count"] == 1
    assert signal["buy_value_nok"] < 2_000_000
    assert signal["score_effect"] == 0


def test_single_small_buy_is_not_strong():
    signal = analyze({"items": [
        {"transaction_type": "buy", "trade_date": "2026-08-20", "actor": "Director", "shares": 100, "price": 20.0}
    ]})["insider_signal_v2"]
    assert signal["label"] == "MIXED"
    assert signal["points"] == 1


def test_net_selling_reduces_signal():
    signal = analyze({"items": [
        {"transaction_type": "buy", "trade_date": "2026-08-20", "actor": "CEO", "role": "CEO", "shares": 1000, "price": 20.0},
        {"transaction_type": "sell", "trade_date": "2026-08-20", "actor": "CFO", "role": "CFO", "shares": 5000, "price": 20.0},
    ]})["insider_signal_v2"]
    assert signal["points"] < 1
    assert signal["sell_value_nok"] > signal["buy_value_nok"]
