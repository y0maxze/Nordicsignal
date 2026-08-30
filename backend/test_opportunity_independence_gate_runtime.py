import opportunity_independence_gate_runtime as gate


def _rows(count, tickers, sectors):
    out = []
    for i in range(count):
        out.append({
            "ticker": tickers[i % len(tickers)],
            "sector": sectors[i % len(sectors)],
        })
    return out


def test_independence_gate_passes_balanced_sample():
    rows = _rows(
        24,
        ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF", "GGG", "HHH"],
        ["Energy", "Financials", "Seafood", "Technology"],
    )
    result = gate._independence_stats(rows, minimum_sample=20)
    assert result["status"] == "PASS"
    assert result["unique_tickers"] == 8
    assert result["unique_sectors"] == 4
    assert result["largest_ticker_share_pct"] <= 25
    assert result["largest_sector_share_pct"] <= 50


def test_independence_gate_rejects_single_ticker_concentration():
    rows = [{"ticker": "AAA", "sector": "Energy"} for _ in range(8)]
    rows += _rows(
        12,
        ["BBB", "CCC", "DDD", "EEE", "FFF", "GGG", "HHH"],
        ["Financials", "Seafood", "Technology", "Industrials"],
    )
    result = gate._independence_stats(rows, minimum_sample=20)
    assert result["status"] == "REVIEW"
    assert result["checks"]["ticker_concentration"] is False
    assert result["largest_ticker"] == "AAA"
    assert result["largest_ticker_share_pct"] == 40.0


def test_independence_gate_rejects_sector_concentration():
    tickers = ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF", "GGG", "HHH", "III", "JJJ"]
    rows = [{"ticker": tickers[i % len(tickers)], "sector": "Energy"} for i in range(14)]
    rows += _rows(6, tickers, ["Financials", "Seafood", "Technology"])
    result = gate._independence_stats(rows, minimum_sample=20)
    assert result["status"] == "REVIEW"
    assert result["checks"]["unique_tickers"] is True
    assert result["checks"]["sector_concentration"] is False
    assert result["largest_sector"] == "Energy"
    assert result["largest_sector_share_pct"] == 70.0


def test_independence_gate_stays_collecting_below_sample_floor():
    rows = _rows(
        19,
        ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF", "GGG", "HHH"],
        ["Energy", "Financials", "Seafood", "Technology"],
    )
    result = gate._independence_stats(rows, minimum_sample=20)
    assert result["status"] == "COLLECTING_DATA"
    assert result["checks"]["minimum_sample"] is False
