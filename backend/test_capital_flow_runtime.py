from datetime import datetime, timezone, timedelta

import capital_flow_runtime as c


def test_classifies_major_holding_and_institutional_flows():
    kind, direction = c._classify_news({"title": "Disclosure of major shareholdings after fund purchase"})
    assert kind == "LARGE_HOLDING"
    assert direction == "buy"

    kind, direction = c._classify_news({"title": "International investors increase stake in issuer"})
    assert kind == "FOREIGN_OWNERSHIP"
    assert direction == "buy"

    kind, direction = c._classify_news({"title": "Alfred Berg fund buys shares in company"})
    assert kind == "INSTITUTIONAL_FLOW"
    assert direction == "buy"


def test_irrelevant_news_is_not_capital_flow():
    assert c._classify_news({"title": "Company reports quarterly revenue growth"}) is None


def test_new_active_historical_buckets():
    now = datetime.now(timezone.utc)
    assert c._bucket((now - timedelta(hours=6)).isoformat()) == "NEW"
    assert c._bucket((now - timedelta(days=8)).isoformat()) == "ACTIVE"
    assert c._bucket((now - timedelta(days=45)).isoformat()) == "HISTORICAL"


def test_policy_is_observational_only():
    data = c.list_events(limit=1)
    assert data["policy"]["score_effect"] == "none"
    assert data["policy"]["new_hours"] == 48
    assert data["policy"]["active_days"] == 30
