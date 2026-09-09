import ipo_prelisting_profile_runtime as profile


def candidate(**overrides):
    row = {
        "candidate_id": "abc123",
        "company": "Example ASA",
        "ticker": "EX",
        "market": "Euronext Oslo Børs",
        "listing_type": "ipo",
        "expected_listing_date_text": "18 June 2026",
        "offer_price_nok": 20.0,
        "source_url": "https://live.euronext.com/en/node/123",
    }
    row.update(overrides)
    return row


def research():
    return {
        "financialData": {
            "totalRevenue": 1_000_000_000,
            "ebitda": 150_000_000,
            "netIncomeToCommon": 80_000_000,
            "freeCashflow": 60_000_000,
            "totalDebt": 100_000_000,
        },
        "defaultKeyStatistics": {"sharesOutstanding": 50_000_000},
        "summaryDetail": {"marketCap": 900_000_000},
    }


def test_profile_keeps_unknown_ownership_and_capital_use_unknown():
    result = profile.build_profile(candidate(), research=research())
    assert result["ownership"]["status"] == "unknown"
    assert result["offering"]["status"] == "unknown"
    assert result["coverage"]["fields"]["ownership"] is False
    assert result["coverage"]["fields"]["capital_use"] is False


def test_offer_price_valuation_is_measured_not_guessed():
    result = profile.build_profile(candidate(), research=research())
    assert result["valuation"]["implied_market_cap_nok"] == 1_000_000_000
    assert result["valuation"]["price_to_sales_at_offer"] == 1.0
    assert round(result["valuation"]["ev_to_ebitda_at_offer"], 3) == 7.333
    assert result["financials"]["profitable"] is True
    assert result["financials"]["ebitda_margin_pct"] == 15.0


def test_missing_research_fails_closed():
    class MissingProvider:
        def research(self, ticker):
            raise RuntimeError("not listed")

    result = profile.build_profile(candidate(), provider=MissingProvider())
    assert result["market_data_status"] == "not_yet_available"
    assert result["valuation"]["implied_market_cap_nok"] is None
    assert result["status"] == "insufficient"
    assert "Utilstrekkelig" in result["assessment"]


def test_no_offer_price_means_no_implied_valuation():
    result = profile.build_profile(candidate(offer_price_nok=None), research=research())
    assert result["valuation"]["implied_market_cap_nok"] is None
    assert result["valuation"]["price_to_sales_at_offer"] is None


def test_policy_never_changes_stock_score():
    result = profile.build_profile(candidate(), research=research())
    assert "No stock-score change" in result["policy"]
    assert result["coverage"]["pct"] < 100
