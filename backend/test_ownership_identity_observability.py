import sqlite3

import ownership_identity_registry as registry
import ownership_observability as observability


def _memory_conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE stocks (ticker TEXT PRIMARY KEY, name TEXT NOT NULL, active INTEGER DEFAULT 1)")
    conn.execute("INSERT INTO stocks(ticker,name,active) VALUES('LSG','Lerøy Seafood Group ASA',1)")
    return conn


def test_verified_identity_registry_never_guesses(monkeypatch):
    conn = _memory_conn()
    monkeypatch.setattr(registry, "connect", lambda: conn)
    monkeypatch.setattr(registry, "USING_POSTGRES", False)
    assert registry.resolve_identifier("ISIN", "NO0000000001") is None
    registry.register_verified_identifier("ISIN", "NO0000000001", "LSG", source_ref="authorized-sample-row-1")
    assert registry.resolve_identifier("ISIN", "NO0000000001") == "LSG"


def test_verified_mapping_requires_source_and_known_active_ticker(monkeypatch):
    conn = _memory_conn()
    monkeypatch.setattr(registry, "connect", lambda: conn)
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


def test_conflicting_identifier_mapping_is_blocked(monkeypatch):
    conn = _memory_conn()
    conn.execute("INSERT INTO stocks(ticker,name,active) VALUES('DNB','DNB Bank ASA',1)")
    monkeypatch.setattr(registry, "connect", lambda: conn)
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


def test_observability_reports_no_coverage_without_connected_feed(monkeypatch):
    monkeypatch.setattr(observability.snapshots, "_ensure_schema", lambda: None)
    monkeypatch.setattr(observability.identities, "identity_status", lambda: {
        "registry_rows": 0, "verified_rows": 0, "verified_isin_rows": 0, "inference_enabled": False
    })
    monkeypatch.setattr(observability.adapters, "adapter_status", lambda: {
        "official": {"machine_ingest": True, "connection_ready": False}
    })
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
      CREATE TABLE ownership_snapshots(id INTEGER, as_of_date TEXT);
      CREATE TABLE ownership_positions(snapshot_id INTEGER);
      CREATE TABLE ownership_changes(id INTEGER);
    """)
    monkeypatch.setattr(observability, "connect", lambda: conn)
    result = observability.status()
    assert result["coverage_active"] is False
    assert result["authorized_machine_feeds"] == []
    assert result["snapshot_count"] == 0
    assert "No authorized daily ownership feed" in result["message"]
    assert result["model_policy"]["score_effect"] == "none"
