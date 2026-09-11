from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch

import capital_flow_runtime as c

ROOT = Path(__file__).resolve().parents[1]


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


def test_news_derived_flow_requires_explicit_ticker_link():
    feed = {
        "items": [
            {
                "ticker": None,
                "title": "Foreign investors increase stake in unrelated market",
                "summary": "Foreign investors increase stake",
                "published_at": "2026-09-11T07:30:00+00:00",
                "official": False,
                "publisher": "Newswire",
            },
            {
                "ticker": "AKER",
                "title": "International fund increases stake in AKER",
                "summary": "International fund increases stake in AKER",
                "published_at": "2026-09-11T07:31:00+00:00",
                "official": False,
                "publisher": "Media",
            },
        ]
    }
    captured = []
    with patch.object(c.general_news_runtime, "general_market_news", return_value=feed), patch.object(c, "_upsert", side_effect=captured.append):
        count = c._ingest_market_news()
    assert count == 1
    assert len(captured) == 1
    assert captured[0]["ticker"] == "AKER"
    assert captured[0]["evidence_level"] == "reported"


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
    assert data["policy"]["news_admission"] == "explicit_ticker_link_required"


def test_capital_flow_status_does_not_claim_daily_ownership_feed():
    data = c.status()
    assert data["score_effect"] == "none"
    assert data["daily_ownership_feed"] is False
    assert "ticker_linked_media_context_reported" in data["coverage"]


def test_capital_flow_product_contract_is_wired_everywhere():
    worker = (ROOT / "worker.js").read_text(encoding="utf-8")
    shell = (ROOT / "frontend" / "ui_shell.js").read_text(encoding="utf-8")
    mobile = (ROOT / "frontend" / "mobile_learning_nav.js").read_text(encoding="utf-8")
    page = (ROOT / "frontend" / "capital-flow.html").read_text(encoding="utf-8")
    client = (ROOT / "frontend" / "capital-flow.js").read_text(encoding="utf-8")
    alerts = (ROOT / "frontend" / "alerts.html").read_text(encoding="utf-8")
    sitecustomize = (ROOT / "backend" / "sitecustomize.py").read_text(encoding="utf-8")

    assert '["/capital-flow", "/capital-flow.html"]' in worker
    assert 'href="/capital-flow"' in shell
    assert "'/api/capital-flow?state=NEW&limit=40'" in mobile
    assert 'href="/capital-flow"' in mobile
    assert 'data-state="NEW"' in page and 'data-state="HISTORICAL"' in page
    assert '/api/capital-flow?' in client
    assert 'data-type="CAPITAL_FLOW"' in alerts
    assert 'capital_flow_runtime' in sitecustomize
    assert 'capital_flow_push_bridge_runtime' in sitecustomize


def test_retired_system_surface_has_no_mobile_residue():
    ui = (ROOT / "frontend" / "ui_shell.js").read_text(encoding="utf-8")
    mobile = (ROOT / "frontend" / "mobile_nav.js").read_text(encoding="utf-8")
    worker = (ROOT / "worker.js").read_text(encoding="utf-8")
    assert 'href="/development"' not in ui
    assert 'href="/development"' not in mobile
    assert '["/development",' not in worker
    assert not (ROOT / "frontend" / "test_system_hero.mjs").exists()
    assert (ROOT / "frontend" / "test_intro_risk_gate.mjs").exists()
