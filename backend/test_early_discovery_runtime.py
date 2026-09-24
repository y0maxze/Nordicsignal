import json
import early_discovery_runtime as rt

def sample(label="WATCH",score=55):
    return {"status":"ok","label":label,"score":score,"as_of":"2026-09-18","components":{"volume_acceleration_5v20":1.3},"reasons":["test"],"version":"test-v1","score_effect":0}

def test_record_is_idempotent(monkeypatch,tmp_path):
    import database
    # Runtime uses the shared test database configured by the suite.
    rt._ensure_schema()
    ticker="ZZEARLYTEST"
    a=rt.record(ticker,sample())
    b=rt.record(ticker,sample())
    assert a["score_effect"]==0
    assert b["stored"] is False

def test_latest_is_research_only():
    rt._ensure_schema()
    rt.record("ZZEARLYLIST",sample("EARLY_BUILDUP",70))
    rows=rt.latest(200,["EARLY_BUILDUP"])
    row=next(x for x in rows if x["ticker"]=="ZZEARLYLIST")
    assert row["score_effect"]==0
    assert row["policy"]=="research_watchlist_only_no_production_signal_effect"
    assert isinstance(row["components"],dict)
    assert isinstance(row["reasons"],list)

def test_history_is_point_in_time_and_research_only():
    rt._ensure_schema()
    rt.record("ZZEARLYHIST",sample("WATCH",55),observed_at="2026-09-18T12:00:00+00:00")
    rows=rt.history("ZZEARLYHIST",30)
    assert rows
    assert rows[0]["market_date"]=="2026-09-18"
    assert rows[0]["score_effect"]==0
    assert rows[0]["policy"]=="research_watchlist_only_no_production_signal_effect"
