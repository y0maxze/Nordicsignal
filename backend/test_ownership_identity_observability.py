import sqlite3

import ownership_identity_registry as registry
import ownership_observability as observability


def _db_factory(tmp_path, *, include_dnb=False):
    path = tmp_path / "ownership-test.db"
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE stocks (ticker TEXT PRIMARY KEY, name TEXT NOT NULL, active INTEGER DEFAULT 1)")
    conn.execute("INSERT INTO stocks(ticker,name,active) VALUES('LSG','Lerøy Seafood Group ASA',1)")
    if include_dnb:
        conn.execute("INSERT INTO stocks(ticker,name,active) VALUES('DNB','DNB Bank ASA',1)")
    conn.commit()
    conn.close()

    def factory():
        c = sqlite3.connect(path)
        c.row_factory = sqlite3.Row
        return c

    return factory


def test_verified_identity_registry_never_guesses(monkeypatch, tmp_path):
    monkeypatch.setattr(registry, "connect", _db_factory(tmp_path))
    monkeypatch.setattr(registry, "USING_POSTGRES", False)
    assert registry.resolve_identifier("ISIN", "NO0000000001") is None
    registry.register_verified_identifier("ISIN", "NO0000000001", "LSG", source_ref="authorized-sample-row-1")
    assert registry.resolve_identifier("ISIN", "NO0000000001") == "LSG"


def test_verified_mapping_requires_source_and_known_active_ticker(monkeypatch, tmp_path):
    monkeypatch.setattr(registry, "connect", _db_factory(tmp_path))
    monkeypatch.setattr(registry, "USING_POSTGRES", False)
    try:
        registry.register_verified_identifier("ISIN", "NO1", "LSG", source_ref="")
        assert False, "missing source must fail"
    except ValueError as exc:
        assert "source_ref" in str(exc)
    try:
        registry.register_verified_identifier("ISIN", "NO2", "FAKE", source_ref="verified")
        assert False, "unknown ticker must fail"
    except ValueError as exc:
        assert "unknown/inactive" in str(exc)


def test_conflicting_identifier_mapping_is_blocked(monkeypatch, tmp_path):
    monkeypatch.setattr(registry, "connect", _db_factory(tmp_path, include_dnb=True))
    monkeypatch.setattr(registry, "USING_POSTGRES", False)
    registry.register_verified_identifier("ISIN", "NO0000000001", "LSG", source_ref="source-a")
    try:
        registry.register_verified_identifier("ISIN", "NO0000000001", "DNB", source_ref="source-b")
        assert False, "conflicting mapping must fail"
    except ValueError as exc:
        assert "conflicting verified identifier mapping" in str(exc)


def test_adapter_row_resolver_requires_verified_mapping(monkeypatch):
    monkeypatch.setattr(registry, "resolve_identifier", lambda scheme, identifier: None)
    resolver = registry.make_row_resolver("ISIN")
    try:
        resolver({"ISIN": "NO0000000001", "Issuer": "Something"})
        assert False, "resolver must not fall back to issuer name"
    except ValueError as exc:
        assert "no verified ticker mapping" in str(exc)


def test_observability_reports_no_coverage_without_connected_feed(monkeypatch, tmp_path):
    monkeypatch.setattr(observability.snapshots, "_ensure_schema", lambda: None)
    monkeypatch.setattr(observability.identities, "identity_status", lambda: {
        "registry_rows": 0, "verified_rows": 0, "verified_isin_rows": 0, "inference_enabled": False
    })
    monkeypatch.setattr(observability.adapters, "adapter_status", lambda: {
        "official": {"machine_ingest": True, "connection_ready": False}
    })
    path = tmp_path / "observability.db"
    conn = sqlite3.connect(path)
    conn.executescript("""
      CREATE TABLE ownership_snapshots(id INTEGER, as_of_date TEXT);
      CREATE TABLE ownership_positions(snapshot_id INTEGER);
      CREATE TABLE ownership_changes(id INTEGER);
    """)
    conn.commit()
    conn.close()

    def factory():
        c = sqlite3.connect(path)
        c.row_factory = sqlite3.Row
        return c

    monkeypatch.setattr(observability, "connect", factory)
    result = observability.status()
    assert result["coverage_active"] is False
    assert result["authorized_machine_feeds"] == []
    assert result["snapshot_count"] == 0
    assert "No authorized daily ownership feed" in result["message"]
    assert result["model_policy"]["score_effect"] == "none"
