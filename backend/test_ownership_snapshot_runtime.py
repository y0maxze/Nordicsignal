import uuid

import pytest

import ownership_snapshot_runtime as o


def _ticker():
    return "T" + uuid.uuid4().hex[:7].upper()


def test_source_and_model_policy_are_explicit():
    status = o.status()
    assert status["policy"]["score_effect"] == "none"
    assert status["policy"]["opportunity_effect"] == "none"
    assert status["daily_marketwide_coverage"] is False
    assert "euronext_securities_top_shareholders" in status["sources"]
    assert "skatteetaten_aksjonaerregisteret" in status["sources"]


def test_first_snapshot_is_baseline_not_fake_entered_events():
    ticker = _ticker()
    first = o.ingest_snapshot("test_provider", ticker, "2026-09-01", [
        {"name":"Fund Alpha","holder_type":"fund","country":"NO","shares":1000,"ownership_pct":1.0,"rank":1},
        {"name":"Investor Beta","holder_type":"institution","country":"SE","shares":500,"ownership_pct":0.5,"rank":2},
    ])
    assert first["status"] == "stored"
    assert first["previous_date"] is None
    data = o.ownership(ticker)
    assert data["status"] == "ok"
    assert data["changes"] == []


def test_snapshot_ingestion_is_point_in_time_and_computes_delta():
    ticker = _ticker()
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


def test_corrected_historical_snapshot_rebuilds_following_delta():
    ticker = _ticker()
    provider = "correction_provider"
    o.ingest_snapshot(provider, ticker, "2026-09-01", [{"holder_id":"A1","name":"Fund Alpha","shares":100}])
    o.ingest_snapshot(provider, ticker, "2026-09-02", [{"holder_id":"A1","name":"Fund Alpha","shares":150}])
    o.ingest_snapshot(provider, ticker, "2026-09-03", [{"holder_id":"A1","name":"Fund Alpha","shares":200}])

    corrected = o.ingest_snapshot(provider, ticker, "2026-09-02", [{"holder_id":"A1","name":"Fund Alpha","shares":120}])
    assert corrected["recomputed_next_date"] == "2026-09-03"

    latest = o.ownership(ticker)
    assert latest["as_of_date"] == "2026-09-03"
    assert len(latest["changes"]) == 1
    change = latest["changes"][0]
    assert change["shares_before"] == 120
    assert change["shares_after"] == 200
    assert change["shares_delta"] == 80
    assert change["change_kind"] == "INCREASED"


def test_holder_id_survives_country_correction_without_false_entry_exit():
    ticker = _ticker()
    provider = "identity_provider"
    o.ingest_snapshot(provider, ticker, "2026-09-01", [
        {"holder_id":"stable-1","name":"Global Fund","country":"NO","shares":500,"ownership_pct":0.5}
    ])
    o.ingest_snapshot(provider, ticker, "2026-09-02", [
        {"holder_id":"stable-1","name":"Global Fund","country":"SE","shares":500,"ownership_pct":0.5}
    ])
    assert o.ownership(ticker)["changes"] == []


def test_snapshot_date_must_be_real_iso_date():
    with pytest.raises(ValueError):
        o.ingest_snapshot("test_provider", _ticker(), "2026-99-99", [{"name":"Fund Alpha","shares":100}])
