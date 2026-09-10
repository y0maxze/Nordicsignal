import event_radar_hardening_runtime as hardening


def test_order_term_does_not_match_border():
    item = {"title": "Company expands border operations"}
    assert hardening._classify(item) is None


def test_order_term_matches_standalone_order():
    item = {"title": "Company receives new order from customer"}
    out = hardening._classify(item)
    assert out is not None
    assert out[0] == "contract"


def test_newest_first_within_same_priority():
    items = [
        {"priority": "watch", "published_at": "2026-09-01T08:00:00+00:00", "title": "old"},
        {"priority": "watch", "published_at": "2026-09-09T08:00:00+00:00", "title": "new"},
        {"priority": "high", "published_at": "2026-08-01T08:00:00+00:00", "title": "high"},
    ]
    ordered = hardening._sort_items(items)
    assert [x["title"] for x in ordered] == ["high", "new", "old"]


def test_wrapper_sorts_before_applying_limit(monkeypatch):
    monkeypatch.setattr(
        hardening,
        "_ORIGINAL_BUILD",
        lambda **kwargs: {
            "status": "live",
            "items": [
                {"priority": "watch", "published_at": "2026-09-01T08:00:00+00:00", "title": "old"},
                {"priority": "watch", "published_at": "2026-09-09T08:00:00+00:00", "title": "new"},
            ],
            "count": 2,
        },
    )
    result = hardening.build_event_radar(limit=1)
    assert result["count"] == 1
    assert result["items"][0]["title"] == "new"
