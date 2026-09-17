import capital_flow_quality as q


def event(**overrides):
    base = {
        "ticker": "LSG",
        "event_type": "PRIMARY_INSIDER",
        "direction": "buy",
        "actor": "Example Holder",
        "event_at": "2026-09-17T08:00:00+00:00",
        "title": "Primary insider purchase",
        "source_url": "https://example.test/evidence",
        "evidence_level": "verified",
        "official": True,
        "shares": 1000,
    }
    base.update(overrides)
    return base


def test_verified_official_primary_insider_is_high_quality():
    item = q.enrich(event())
    assert item["research_quality"] >= 85
    assert item["quality_band"] == "HIGH"


def test_unlinked_reported_context_cannot_look_high_quality():
    item = q.enrich(event(
        ticker=None,
        event_type="OWNERSHIP_CHANGE",
        actor=None,
        source_url=None,
        evidence_level="reported",
        official=False,
        shares=None,
    ))
    assert item["quality_band"] == "CONTEXT"


def test_dedupe_key_is_normalized_and_date_scoped():
    a = event(title="  Primary   Insider PURCHASE! ")
    b = event(title="primary insider purchase", event_at="2026-09-17T18:00:00Z")
    assert q.dedupe_key(a) == q.dedupe_key(b)


def test_quality_layer_has_no_signal_policy_constants():
    forbidden = {"opportunity", "high_conviction", "position_size", "score_threshold"}
    assert not forbidden.intersection(set(q.__dict__))
