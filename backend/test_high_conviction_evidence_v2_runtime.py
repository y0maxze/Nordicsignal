import high_conviction_evidence_v2_runtime as v2


def test_trend_dimension_uses_point_in_time_opportunity_payload():
    opp={"payload":{"reversal":{"score":64,"regime":"REVERSAL_CANDIDATE","confidence":"low","metrics":{"close_date":"2026-09-08","rsi14":69.55,"volume_confirmation":"NONE","drawdown_pct":-21.43,"higher_low":True}}}}
    out=v2._trend_dimension(opp)
    assert out["available"] is True
    assert out["regime"] == "REVERSAL_CANDIDATE"
    assert out["rsi14"] == 69.55
    assert out["higher_low"] is True


def test_maturity_is_fixed_and_not_tuned():
    assert v2._maturity(19) == "insufficient"
    assert v2._maturity(20) == "early"
    assert v2._maturity(49) == "early"
    assert v2._maturity(50) == "useful_history"


def test_shadow_remains_disabled_with_strong_measured_inputs(monkeypatch):
    monkeypatch.setattr(v2, "_BASE_BUILD", lambda ticker:{"status":"collecting_evidence","ticker":"KOG","dimensions":{},"blockers":[],"activation":{"enabled":False}})
    monkeypatch.setattr(v2.shadow, "_opportunity", lambda ticker:{"payload":{"reversal":{"score":80,"regime":"REVERSAL_CANDIDATE","metrics":{}}}})
    monkeypatch.setattr(v2, "_recent_event_risk", lambda ticker:{"available":True,"count":0,"critical_count":0,"has_critical_event_risk":False,"items":[]})
    monkeypatch.setattr(v2, "_opportunity_evidence", lambda ticker:{"available":True,"sample_n":80,"benchmark_sample_n":80,"maturity":"useful_history","mean_excess_return_pct":4.2,"regime_counts":{"RISK_ON":30,"NEUTRAL":30,"RISK_OFF":20},"regime_coverage_pct":100.0})
    out=v2.build_shadow("KOG")
    assert out["activation"]["enabled"] is False
    assert out["model"] == "high_conviction_shadow_v2"
    assert "no buy/sell signal" in out["policy"]


def test_critical_event_is_explicit_blocker(monkeypatch):
    monkeypatch.setattr(v2, "_BASE_BUILD", lambda ticker:{"status":"collecting_evidence","ticker":"KOG","dimensions":{},"blockers":[],"activation":{"enabled":False}})
    monkeypatch.setattr(v2.shadow, "_opportunity", lambda ticker:{"payload":{"reversal":{"score":70,"regime":"BOTTOMING","metrics":{}}}})
    monkeypatch.setattr(v2, "_recent_event_risk", lambda ticker:{"available":True,"count":1,"critical_count":1,"has_critical_event_risk":True,"items":[]})
    monkeypatch.setattr(v2, "_opportunity_evidence", lambda ticker:{"available":False,"sample_n":0,"benchmark_sample_n":0,"maturity":"insufficient","regime_counts":{},"regime_coverage_pct":0.0})
    out=v2.build_shadow("KOG")
    assert "current_critical_event_risk" in out["blockers"]
    assert out["activation"]["enabled"] is False


def test_missing_event_archive_fails_closed_without_creating_risk(monkeypatch):
    class BrokenConn:
        def execute(self,*args,**kwargs):
            raise RuntimeError("db unavailable")
        def close(self):
            pass
    monkeypatch.setattr(v2, "connect", lambda: BrokenConn())
    out=v2._recent_event_risk("KOG")
    assert out["available"] is False
    assert out["has_critical_event_risk"] is False
