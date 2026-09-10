from datetime import date
import uuid

import ownership_snapshot_runtime as o


def test_source_and_model_policy_are_explicit():
    status = o.status()
    assert status["policy"]["score_effect"] == "none"
    assert status["policy"]["opportunity_effect"] == "none"
    assert "euronext_securities_top_shareholders" in status["sources"]
    assert "skatteetaten_aksjonaerregisteret" in status["sources"]


def test_snapshot_ingestion_is_point_in_time_and_computes_delta():
    ticker = "T" + uuid.uuid4().hex[:7].upper()
    provider = "test_provider"
    first = o.ingest_snapshot(provider, ticker, "2026-09-01", [
        {"name":"Fund Alpha","holder_type":"fund","country":"NO","shares":1000,"ownership_pct":1.0,"rank":1},
        {"name":"Investor Beta","holder_type":"institution","country":"SE","shares":500,"ownership_pct":0.5,"rank":2},
    ])
    assert first["status"] == "stored"
    same = o.ingest_snapshot(provider, ticker, "2026-09-01", [
        {"name":"Fund Alpha","holder_type":"fund","country":"NO","shares":1000,"ownership_pct":1.0,"rank":1},
        {"name":"Investor Beta","holder_type":"institution","country":"SE","shares":500,"ownership_pct":0.5,"rank":2},
    ])
    assert same["status"] == "unchanged"

    second = o.ingest_snapshot(provider, ticker, "2026-09-02", [
        {"name":"Fund Alpha","holder_type":"fund","country":"NO","shares":1400,"ownership_pct":1.4,"rank":1},
        {"name":"New Global Fund","holder_type":"fund","country":"US","shares":300,"ownership_pct":0.3,"rank":2},
    ])
    assert second["previous_date"] == "2026-09-01"
    data = o.ownership(ticker)
    assert data["status"] == "ok"
    assert data["as_of_date"] == "2026-09-02"
    kinds = {x["holder_name"]: x["change_kind"] for x in data["changes"]}
    assert kinds["Fund Alpha"] == "INCREASED"
    assert kinds["Investor Beta"] == "EXITED"
    assert kinds["New Global Fund"] == "ENTERED"
