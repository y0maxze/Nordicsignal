import ipo_archive_runtime as archive
import ipo_push_bridge_runtime as bridge


def candidate(**overrides):
    row = {"official":True,"company":"Example ASA","ticker":"EX","listing_type":"ipo","market":"Euronext Oslo Børs","expected_listing_date_text":"18 June 2026","offer_price_nok":31.0,"title":"Example ASA IPO","source_url":"https://live.euronext.com/en/node/123","published_at":"2026-06-08T08:00:00+00:00"}
    row.update(overrides)
    return row


def test_candidate_id_is_stable():
    first = archive._candidate_id(candidate())
    assert first == archive._candidate_id(candidate())
    assert len(first) == 32


def test_candidate_id_changes_for_different_source():
    assert archive._candidate_id(candidate()) != archive._candidate_id(candidate(source_url="https://live.euronext.com/en/node/456"))


def test_ipo_push_event_contains_stable_key_and_context():
    event = bridge._ipo_push_event(candidate(candidate_id="abc123", first_seen_at="2026-06-08T09:00:00+00:00"))
    assert event["event_key"] == "ipo:abc123"
    assert event["title"] == "Ny børsnotering · Example ASA"
    assert "Euronext Oslo Børs" in event["body"]
    assert "18 June 2026" in event["body"]
    assert "31.00 kr" in event["body"]
    assert event["url"] == "/ipo-radar"


def test_ipo_push_event_requires_candidate_id():
    assert bridge._ipo_push_event(candidate()) is None


def test_archive_rejects_unverified_candidates(monkeypatch):
    calls = []
    class FakeConn:
        def executescript(self, *_): pass
        def commit(self): pass
        def close(self): pass
        def execute(self, sql, params=()):
            calls.append((sql, params))
            class Result:
                def fetchone(self): return None
            return Result()
    monkeypatch.setattr(archive, "connect", lambda: FakeConn())
    assert archive.record_candidates([candidate(official=False)]) == 0
    assert not any("INSERT INTO ipo_candidates" in sql for sql, _ in calls)
