import early_discovery_research as ed

def history(n=100, start=10.0, drift=0.001, volume=1000):
    rows=[]; price=start
    for i in range(n):
        price*=1+drift
        rows.append({"date":f"2026-01-{(i%28)+1:02d}","close":price,"volume":volume})
    return rows

def test_insufficient_history_fails_closed():
    r=ed.analyze(history(40))
    assert r["status"]=="insufficient_data"
    assert r["score"] is None
    assert r["policy"]=="research_watchlist_only"

def test_research_layer_has_zero_production_effect():
    rows=history()
    for row in rows[-5:]: row["volume"]=1600
    r=ed.analyze(rows, history(drift=0.0001))
    assert r["status"]=="ok"
    assert r["score_effect"]==0
    assert "no_production_signal_effect" in r["policy"]
    assert r["label"] in {"NORMAL","WATCH","EARLY_BUILDUP"}

def test_volume_acceleration_is_point_in_time():
    rows=history()
    before=ed.analyze(rows)
    changed=[dict(x) for x in rows]
    for row in changed[-5:]: row["volume"]=2000
    after=ed.analyze(changed)
    assert before["components"]["volume_acceleration_5v20"]==1.0
    assert after["components"]["volume_acceleration_5v20"]==2.0
    assert after["score"]>=before["score"]

def test_benchmark_relative_strength_is_optional_and_explicit():
    stock=history(drift=0.003)
    benchmark=history(drift=0.0005)
    with_benchmark=ed.analyze(stock,benchmark)
    without=ed.analyze(stock)
    assert with_benchmark["components"]["excess_return_20d_pct"]>0
    assert without["components"]["excess_return_20d_pct"] is None
