import capital_flow_quality as q


def item(**changes):
    base = {
        "ticker": "LSG",
        "event_type": "LARGE_HOLDING",
        "direction": "buy",
        "actor": "Holder AS",
        "event_at": "2026-09-17T08:00:00Z",
        "title": "Mandatory disclosure of large shareholding",
        "evidence_level": "reported",
        "official": False,
        "source_url": "https://example.test/a",
    }
    base.update(changes)
    return base


def test_same_semantic_event_has_same_key_despite_punctuation_and_time():
    a = item(title="Mandatory disclosure of large shareholding!")
    b = item(title="mandatory disclosure of large shareholding", event_at="2026-09-17T17:00:00Z")
    assert q.dedupe_key(a) == q.dedupe_key(b)


def test_verified_official_representation_outranks_reported_duplicate():
    reported = item()
    verified = item(evidence_level="verified", official=True)
    assert q.presentation_rank(verified) > q.presentation_rank(reported)


def test_different_dates_are_not_collapsed():
    assert q.dedupe_key(item()) != q.dedupe_key(item(event_at="2026-09-18T08:00:00Z"))
