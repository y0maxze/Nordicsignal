from unittest.mock import patch

import pytest

import ownership_feed_adapters as a


def test_provider_catalog_is_truthful_about_unconnected_feeds():
    status = a.adapter_status()
    assert status["euronext_securities_top_shareholder_information"]["machine_ingest"] is True
    assert status["euronext_securities_top_shareholder_information"]["connection_ready"] is False
    assert status["euronext_securities_organisational_shareholders"]["connection_ready"] is False
    assert status["euronext_public_shareholder_portal"]["machine_ingest"] is False
    assert status["skatteetaten_aksjonaerregisteret"]["frequency"] == "annual"


def test_prepare_batches_requires_explicit_real_field_mapping_and_stable_scope():
    rows = [
        {"symbol": "AKER.OL", "date": "2026-09-10", "owner": "Fund Alpha", "owner_id": "A1", "shares": "1 250", "pct": "1,25%", "rank": "1"},
        {"symbol": "AKER.OL", "date": "2026-09-10", "owner": "Fund Beta", "owner_id": "B1", "shares": "500", "pct": "0,50%", "rank": "2"},
    ]
    field_map = {
        "ticker": "symbol",
        "as_of_date": "date",
        "holder_name": "owner",
        "holder_id": "owner_id",
        "shares": "shares",
        "ownership_pct": "pct",
        "rank": "rank",
    }
    batches = a.prepare_snapshot_batches(
        a.EURONEXT_TOP_SHAREHOLDER_INFORMATION,
        rows,
        field_map,
        scope_id="top200",
        source_ref="licensed-file-2026-09-10.csv",
        decimal_comma=True,
    )
    assert len(batches) == 1
    batch = batches[0]
    assert batch.provider == "euronext_securities_top_shareholder_information:top200"
    assert batch.ticker == "AKER"
    assert batch.as_of_date == "2026-09-10"
    assert batch.source_ref == "licensed-file-2026-09-10.csv"
    assert batch.holders[0]["shares"] == 1250.0
    assert batch.holders[0]["ownership_pct"] == 1.25


def test_different_snapshot_depths_are_never_same_provider_identity():
    rows = [{"symbol": "AKER", "date": "2026-09-10", "owner": "Fund Alpha"}]
    mapping = {"ticker": "symbol", "as_of_date": "date", "holder_name": "owner"}
    top20 = a.prepare_snapshot_batches(a.EURONEXT_TOP_SHAREHOLDER_INFORMATION, rows, mapping, scope_id="top20")
    top200 = a.prepare_snapshot_batches(a.EURONEXT_TOP_SHAREHOLDER_INFORMATION, rows, mapping, scope_id="top200")
    assert top20[0].provider != top200[0].provider


def test_ticker_resolver_and_file_date_support_is_explicit():
    rows = [{"isin": "NO0010000001", "owner": "Fund Alpha", "shares": 100}]
    mapping = {"holder_name": "owner", "shares": "shares"}
    batches = a.prepare_snapshot_batches(
        a.EURONEXT_ORGANISATIONAL_SHAREHOLDERS,
        rows,
        mapping,
        scope_id="full-organisations",
        default_as_of_date="2026-09-10",
        ticker_resolver=lambda row: "AKER" if row["isin"] == "NO0010000001" else "",
    )
    assert batches[0].ticker == "AKER"
    assert batches[0].as_of_date == "2026-09-10"


def test_adapter_does_not_guess_missing_provider_fields():
    with pytest.raises(ValueError, match="holder_name"):
        a.prepare_snapshot_batches(
            a.EURONEXT_TOP_SHAREHOLDER_INFORMATION,
            [{"symbol": "AKER", "date": "2026-09-10", "owner": "Fund Alpha"}],
            {"ticker": "symbol", "as_of_date": "date"},
            scope_id="top20",
        )


def test_unconnected_licensed_feed_cannot_ingest():
    batch = a.SnapshotBatch(
        provider="euronext_securities_top_shareholder_information:top20",
        ticker="AKER",
        as_of_date="2026-09-10",
        holders=({"name": "Fund Alpha", "shares": 100},),
        source_ref="licensed-file.csv",
    )
    with pytest.raises(PermissionError, match="no authorized feed connection"):
        a.ingest_snapshot_batches(a.EURONEXT_TOP_SHAREHOLDER_INFORMATION, [batch])


def test_interactive_public_portal_cannot_be_promoted_to_machine_feed():
    batch = a.SnapshotBatch(
        provider="euronext_public_shareholder_portal:manual",
        ticker="AKER",
        as_of_date="2026-09-10",
        holders=({"name": "Fund Alpha", "shares": 100},),
        source_ref="manual-verification",
    )
    with pytest.raises(PermissionError, match="not approved for automated ingestion"):
        a.ingest_snapshot_batches(a.EURONEXT_PUBLIC_SHAREHOLDER_PORTAL, [batch], connection_ready=True)


def test_authorized_connection_calls_canonical_snapshot_runtime_only_after_enablement():
    batch = a.SnapshotBatch(
        provider="euronext_securities_top_shareholder_information:top20",
        ticker="AKER",
        as_of_date="2026-09-10",
        holders=({"holder_id": "A1", "name": "Fund Alpha", "shares": 100},),
        source_ref="licensed-file.csv",
    )
    with patch.object(a.ownership_runtime, "ingest_snapshot", return_value={"status": "stored", "snapshot_id": 42, "holders": 1}) as ingest:
        result = a.ingest_snapshot_batches(a.EURONEXT_TOP_SHAREHOLDER_INFORMATION, [batch], connection_ready=True)
    ingest.assert_called_once_with(
        "euronext_securities_top_shareholder_information:top20",
        "AKER",
        "2026-09-10",
        [{"holder_id": "A1", "name": "Fund Alpha", "shares": 100}],
        source_ref="licensed-file.csv",
    )
    assert result[0]["snapshot_id"] == 42
