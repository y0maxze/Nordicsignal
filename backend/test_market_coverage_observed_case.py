from market_coverage_data_quality import insider_detail_quality


def test_observed_dvd_capture_is_partial_until_price_or_value_is_verified():
    observed = {"ticker": "DVD", "actor": "Gunnar Hvammen", "direction": "buy", "shares": 1_700_000, "price": None, "transaction_value": None}
    assert observed["direction"] == "buy"
    assert observed["shares"] == 1_700_000
    assert insider_detail_quality(observed) == "partial_missing_price_value"
