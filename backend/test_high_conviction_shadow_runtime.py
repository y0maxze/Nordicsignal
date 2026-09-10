import high_conviction_shadow_runtime as shadow


def test_shadow_never_activates(monkeypatch):
    monkeypatch.setattr(shadow, "_latest_score", lambda ticker: {"ticker":ticker,"total":84,"fundamentals":31,"valuation":14,"sentiment":16,"insider":9,"source":"live"})
    monkeypatch.setattr(shadow, "_opportunity", lambda ticker: {"ticker":ticker,"label":"EARLY_OPPORTUNITY_HIGH","score":88,"observed_at":"2026-09-10T04:00:00+00:00"})
    monkeypatch.setattr(shadow, "_event_evidence_count", lambda ticker, horizon=20: 80)
    out = shadow.build_shadow("KOG")
    assert out["status"] == "research_ready"
    assert out["activation"]["enabled"] is False
    assert "No buy/sell signal" in out["policy"]


def test_shadow_requires_evidence_maturity(monkeypatch):
    monkeypatch.setattr(shadow, "_latest_score", lambda ticker: {"ticker":ticker,"total":80,"source":"live"})
    monkeypatch.setattr(shadow, "_opportunity", lambda ticker: {"ticker":ticker,"label":"EARLY_OPPORTUNITY","score":75})
    monkeypatch.setattr(shadow, "_event_evidence_count", lambda ticker, horizon=20: 12)
    out = shadow.build_shadow("KOG.OL")
    assert out["ticker"] == "KOG"
    assert out["status"] == "collecting_evidence"
    assert out["dimensions"]["event_evidence"]["maturity"] == "insufficient"
    assert "insufficient_20d_event_evidence" in out["blockers"]


def test_shadow_fails_closed_when_inputs_missing(monkeypatch):
    monkeypatch.setattr(shadow, "_latest_score", lambda ticker: None)
    monkeypatch.setattr(shadow, "_opportunity", lambda ticker: None)
    monkeypatch.setattr(shadow, "_event_evidence_count", lambda ticker, horizon=20: 0)
    out = shadow.build_shadow("TEST")
    assert out["status"] == "missing_inputs"
    assert out["activation"]["enabled"] is False
