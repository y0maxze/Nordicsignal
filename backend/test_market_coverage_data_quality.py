from market_coverage_data_quality import insider_detail_quality


def test_missing_price_and_value_is_explicitly_partial():
    assert insider_detail_quality({"shares": 1_700_000, "price": None, "transaction_value": None}) == "partial_missing_price_value"


def test_complete_when_value_is_known_without_unit_price():
    assert insider_detail_quality({"shares": 1_700_000, "price": None, "transaction_value": 35_360_000}) == "complete"
