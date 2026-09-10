from market_coverage_runtime import EXPANDED_UNIVERSE


def test_observed_symbols_are_unique():
    tickers = [row[0] for row in EXPANDED_UNIVERSE]
    assert tickers == ["DVD", "AKER"]
    assert len(tickers) == len(set(tickers))
