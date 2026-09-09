import ipo_document_facts_runtime as facts
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
        "title": "Example ASA IPO",
        "source_url": "https://live.euronext.com/en/node/123",
        "raw_payload": "{}",
    }
    row.update(overrides)
    return row


def research():
    return {
        "financialData": {"totalRevenue": 1_000_000_000, "ebitda": 150_000_000, "netIncomeToCommon": 80_000_000, "freeCashflow": 60_000_000, "totalDebt": 100_000_000},
        "defaultKeyStatistics": {"sharesOutstanding": 50_000_000},
        "summaryDetail": {"marketCap": 900_000_000},
    }


def test_extracts_only_explicit_labelled_facts():
    text = (
        "Gross proceeds NOK 600 million. Secondary sale NOK 150 million. "
        "Founders will retain 64.5%. Lock-up period 12 months. "
        "Use of proceeds: expansion of production capacity and repayment of debt."
    )
    result = facts.extract_facts(text)
    assert result["new_capital_nok"] == 600_000_000
    assert result["secondary_sale_nok"] == 150_000_000
    assert result["founder_retention_pct"] == 64.5
    assert result["lockup_months"] == 12.0
    assert "expansion of production capacity" in result["use_of_proceeds"]


def test_rejects_untrusted_source_host():
    result = facts.collect(candidate(source_url="https://example.com/prospectus"), fetch_text=lambda _: "ignored")
    assert result["source_verified"] is False
    assert result["page_status"] == "not_fetched"
    assert result["documents"] == []


def test_discovers_only_official_document_links():
    html = '''<html><body>
      <a href="/files/example-prospectus.pdf">Prospectus</a>
      <a href="https://evil.example/prospectus.pdf">Prospectus mirror</a>
    </body></html>'''
    result = facts.collect(candidate(), fetch_text=lambda _: html)
    assert result["page_status"] == "available"
    assert len(result["documents"]) == 1
    assert result["documents"][0]["url"].startswith("https://live.euronext.com/")


def test_verified_document_facts_raise_coverage_without_changing_score_policy():
    doc = {
        "status": "facts_available",
        "documents": [{"kind": "prospectus", "url": "https://live.euronext.com/p.pdf"}],
        "facts": {"founder_retention_pct": 70.0, "lockup_months": 12.0, "new_capital_nok": 500_000_000, "secondary_sale_nok": None, "total_offer_size_nok": None, "new_shares": None, "existing_shares_offered": None, "use_of_proceeds": "growth"},
    }
    result = profile.build_profile(candidate(), research=research(), document_facts=doc)
    assert result["ownership"]["founder_retention_pct"] == 70.0
    assert result["offering"]["new_capital_nok"] == 500_000_000
    assert result["coverage"]["fields"]["ownership"] is True
    assert result["coverage"]["fields"]["capital_use"] is True
    assert result["coverage"]["pct"] == 100.0
    assert "stock score" in result["policy"].lower()
