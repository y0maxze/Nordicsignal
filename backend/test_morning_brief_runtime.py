from datetime import datetime, timezone

import morning_brief_runtime as brief


def test_previous_close_handles_monday_morning():
    now = datetime(2026, 9, 7, 6, 0, tzinfo=timezone.utc)  # Monday 08:00 Oslo
    close = brief._previous_oslo_close(now)
    assert close.weekday() == 4
    assert close.hour == 16 and close.minute == 20
    assert close.date().isoformat() == "2026-09-04"


def test_report_tomorrow_is_critical():
    assert brief._risk({"event_type": "report", "days_until": 1}) == "critical"
    assert brief._risk({"event_type": "report", "days_until": 3}) == "high"
    assert brief._risk({"event_type": "report", "days_until": 7}) == "watch"


def test_build_brief_prioritizes_events_and_filters_overnight_news(monkeypatch):
    now = datetime(2026, 9, 7, 6, 0, tzinfo=timezone.utc)

    monkeypatch.setattr(brief.market_calendar_runtime, "build_calendar", lambda **kwargs: {
        "status": "live",
        "source": "Euronext test",
        "errors": [],
        "items": [
            {"ticker": "AKRBP", "company": "Aker BP", "event_type": "report", "event_label": "Q3-rapport", "days_until": 1, "tracked": True},
            {"ticker": "DNB", "company": "DNB", "event_type": "dividend", "event_label": "Utbytte", "days_until": 2, "tracked": True},
        ],
    })
    monkeypatch.setattr(brief.general_news_runtime, "general_market_news", lambda **kwargs: {
        "source": "news test",
        "items": [
            {"ticker": "AKRBP", "title": "Fresh", "publisher": "Euronext", "published_at": "2026-09-06T20:00:00+00:00"},
            {"ticker": "DNB", "title": "Old", "publisher": "Euronext", "published_at": "2026-09-04T10:00:00+00:00"},
        ],
    })
    monkeypatch.setattr(brief, "_market_snapshot", lambda provider: ([
        {"label": "Brent", "change_pct": -2.2, "status": "live"},
        {"label": "S&P 500", "change_pct": 0.4, "status": "live"},
    ], []))

    result = brief.build_morning_brief(now=now, provider=object())
    assert result["must_know"][0]["ticker"] == "AKRBP"
    assert result["must_know"][0]["risk"] == "critical"
    assert [x["title"] for x in result["overnight_news"]] == ["Fresh"]
    assert [x["label"] for x in result["notable_markets"]] == ["Brent"]
    assert "does not change NordicSignal scores" in result["policy"]


def test_partial_calendar_degrades_without_changing_policy(monkeypatch):
    monkeypatch.setattr(brief.market_calendar_runtime, "build_calendar", lambda **kwargs: {
        "status": "partial", "source": "Euronext", "errors": ["page failed"], "items": []
    })
    monkeypatch.setattr(brief.general_news_runtime, "general_market_news", lambda **kwargs: {"source": "news", "items": []})
    monkeypatch.setattr(brief, "_market_snapshot", lambda provider: ([], ["Brent unavailable"]))
    result = brief.build_morning_brief(now=datetime(2026, 9, 7, 6, 0, tzinfo=timezone.utc), provider=object())
    assert result["status"] == "partial"
    assert "page failed" in result["errors"]
    assert "Brent unavailable" in result["errors"]
    assert "thresholds" in result["policy"]
