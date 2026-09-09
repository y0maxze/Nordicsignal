import event_evidence_runtime as evidence


def test_event_id_is_stable_and_point_in_time():
    item={"ticker":"KOG","published_at":"2026-09-09T06:00:00+00:00","title":"KOG: contract award","url":"https://example.test/1"}
    assert evidence._event_id(item) == evidence._event_id(dict(item))
    changed=dict(item,title="KOG: changed")
    assert evidence._event_id(item) != evidence._event_id(changed)


def test_maturity_thresholds_match_existing_evidence_policy():
    assert evidence._maturity(19) == "insufficient"
    assert evidence._maturity(20) == "early"
    assert evidence._maturity(49) == "early"
    assert evidence._maturity(50) == "useful_history"


def test_summary_reports_forward_and_benchmark_excess_returns():
    samples=[
        {"event_type":"contract","materiality_label":"Stor relativt til omsetning","forward_return_pct":{"1":2.0,"5":5.0},"excess_return_pct":{"1":1.0,"5":3.0},"max_drawdown_pct":-1.5,"max_runup_pct":6.0},
        {"event_type":"contract","materiality_label":"Stor relativt til omsetning","forward_return_pct":{"1":-1.0,"5":3.0},"excess_return_pct":{"1":-2.0,"5":1.0},"max_drawdown_pct":-3.0,"max_runup_pct":4.0},
    ]
    out=evidence.summarize_samples(samples)
    h1=out["overall"]["horizons"]["1"]
    h5=out["overall"]["horizons"]["5"]
    assert h1["n"] == 2
    assert h1["positive_rate_pct"] == 50.0
    assert h1["median_excess_return_pct"] == -0.5
    assert h5["median_return_pct"] == 4.0
    assert out["overall"]["median_max_drawdown_pct"] == -2.25
    assert out["overall"]["median_max_runup_pct"] == 5.0
    assert out["maturity"] == "insufficient"
    assert "does not change nordicsignal scores" in out["policy"].lower()


def test_summary_groups_by_event_and_materiality():
    samples=[
        {"event_type":"contract","materiality_label":"Stor","forward_return_pct":{},"excess_return_pct":{}},
        {"event_type":"contract","materiality_label":"Stor","forward_return_pct":{},"excess_return_pct":{}},
        {"event_type":"acquisition","materiality_label":"Ukjent materialitet","forward_return_pct":{},"excess_return_pct":{}},
    ]
    out=evidence.summarize_samples(samples)
    first=out["by_event_materiality"][0]
    assert first["event_type"] == "contract"
    assert first["materiality_label"] == "Stor"
    assert first["sample_count"] == 2


def test_archive_rejects_media_and_unclassified_items(monkeypatch):
    stored=[]
    class FakeRow(dict):
        pass
    class FakeConn:
        def executescript(self,*args): pass
        def execute(self,sql,args=()):
            if sql.startswith("SELECT event_id"):
                return NoneResult()
            if sql.startswith("INSERT"):
                stored.append(args); return NoneResult()
            return NoneResult()
        def commit(self): pass
        def close(self): pass
    class NoneResult:
        def fetchone(self): return None
        def fetchall(self): return []
    monkeypatch.setattr(evidence,"connect",lambda:FakeConn())
    count=evidence.record_events([
        {"ticker":"KOG","title":"Media story","source_type":"media","official":False,"event_type":"contract"},
        {"ticker":"KOG","title":"Official but irrelevant","source_type":"exchange","official":True},
    ])
    assert count == 0
    assert stored == []
