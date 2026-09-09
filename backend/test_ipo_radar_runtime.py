import ipo_radar_runtime as ipo


def official(title, summary=None):
    return {
        "official": True,
        "source_type": "exchange",
        "company": "Example ASA",
        "ticker": "EX",
        "title": title,
        "summary": summary or title,
        "topic": "",
        "published_at": "2026-06-08T08:00:00+00:00",
        "url": "https://live.euronext.com/en/node/123",
    }


def test_detects_verified_oslo_ipo_announcement():
    row = ipo.classify_listing(official(
        "EXAMPLE ASA: ANNOUNCEMENT OF TERMS FOR THE INITIAL PUBLIC OFFERING",
        "Shares expected to commence trading on Euronext Oslo Børs on or about 18 June 2026. Offer Price of NOK 31.00.",
    ))
    assert row is not None
    assert row["listing_type"] == "ipo"
    assert row["market"] == "Euronext Oslo Børs"
    assert row["offer_price_nok"] == 31.0
    assert row["expected_listing_date_text"] == "18 June 2026"
    assert row["assessment"] == "Utilstrekkelig data for investeringsvurdering"


def test_detects_growth_listing():
    row = ipo.classify_listing(official(
        "EXAMPLE: INTENTION TO FLOAT ON EURONEXT GROWTH OSLO",
        "The company announces its planned listing on Euronext Growth Oslo.",
    ))
    assert row is not None
    assert row["market"] == "Euronext Growth Oslo"


def test_rejects_media_even_when_title_mentions_ipo():
    item = official("EXAMPLE plans IPO and listing on Euronext Oslo Børs")
    item["official"] = False
    item["source_type"] = "media"
    assert ipo.classify_listing(item) is None


def test_rejects_delisting_false_positive():
    assert ipo.classify_listing(official(
        "EXAMPLE: termination of listing on Euronext Oslo Børs",
        "The company will be delisted from Euronext Oslo Børs.",
    )) is None


def test_does_not_change_stock_score_policy():
    class Feed:
        @staticmethod
        def general_market_news(provider=None, limit=50):
            return {"items": [official(
                "EXAMPLE ASA: ANNOUNCEMENT OF TERMS FOR THE INITIAL PUBLIC OFFERING",
                "Expected listing on Euronext Oslo Børs on or about 18 June 2026.",
            )]}
    old = ipo.general_news_runtime
    ipo.general_news_runtime = Feed
    try:
        result = ipo.build_ipo_radar(provider=object(), force=True)
    finally:
        ipo.general_news_runtime = old
    assert result["count"] == 1
    assert "does not change NordicSignal scores" in result["policy"]
