"""Truthful ownership research readiness/coverage status."""
from __future__ import annotations

from database import connect
import ownership_feed_adapters as adapters
import ownership_identity_registry as identities
import ownership_snapshot_runtime as snapshots


def status() -> dict:
    """Report what exists without turning adapter readiness into fake coverage."""
    snapshots._ensure_schema()
    identity = identities.identity_status()
    conn = connect()
    try:
        snapshot_count = int(conn.execute("SELECT COUNT(*) AS n FROM ownership_snapshots").fetchone()["n"] or 0)
        position_count = int(conn.execute("SELECT COUNT(*) AS n FROM ownership_positions").fetchone()["n"] or 0)
        change_count = int(conn.execute("SELECT COUNT(*) AS n FROM ownership_changes").fetchone()["n"] or 0)
        latest = conn.execute("SELECT MAX(as_of_date) AS latest FROM ownership_snapshots").fetchone()["latest"]
    finally:
        conn.close()

    catalog = adapters.adapter_status()
    connected = [key for key, item in catalog.items() if item["connection_ready"]]
    machine_ready = [key for key, item in catalog.items() if item["machine_ingest"] and item["connection_ready"]]
    return {
        "coverage_active": bool(machine_ready and snapshot_count),
        "authorized_machine_feeds": machine_ready,
        "connected_adapters": connected,
        "snapshot_count": snapshot_count,
        "position_count": position_count,
        "change_count": change_count,
        "latest_as_of_date": latest,
        "identity_registry": identity,
        "adapters": catalog,
        "model_policy": snapshots.MODEL_POLICY,
        "message": (
            "Authorized point-in-time ownership coverage is active."
            if machine_ready and snapshot_count
            else "No authorized daily ownership feed is currently producing coverage."
        ),
    }
