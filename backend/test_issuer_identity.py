import issuer_identity


def test_normalization_removes_legal_suffix_without_fuzzy_matching():
    assert issuer_identity.normalize_issuer_name("Example ASA") == "example"
    assert issuer_identity.normalize_issuer_name("Example N.V.") == "example"


def test_exact_unique_match_resolves(monkeypatch):
    monkeypatch.setattr(issuer_identity, "canonical_issuers", lambda: [("ABC", "Example ASA"), ("XYZ", "Other AS")])
    result = issuer_identity.resolve_exact_name("Example ASA")
    assert result == {"ticker": "ABC", "name": "Example ASA", "method": "canonical_exact_name", "verified": True}


def test_partial_or_fuzzy_name_does_not_resolve(monkeypatch):
    monkeypatch.setattr(issuer_identity, "canonical_issuers", lambda: [("ABC", "Example Technology ASA")])
    assert issuer_identity.resolve_exact_name("Example") is None


def test_ambiguous_normalized_name_fails_closed(monkeypatch):
    monkeypatch.setattr(issuer_identity, "canonical_issuers", lambda: [("AAA", "Example ASA"), ("BBB", "Example AS")])
    assert issuer_identity.resolve_exact_name("Example ASA") is None
