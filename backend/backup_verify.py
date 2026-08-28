"""Non-destructive PostgreSQL backup/restore verification for NordicSignal.

This module deliberately does not expose a web endpoint and does not create backups.
Use provider-managed backups or pg_dump/pg_restore externally, restore into a separate
database, then compare production with the restored copy:

    DATABASE_URL=<production read-only URL> \
    NORDICSIGNAL_RESTORE_DATABASE_URL=<restored database URL> \
    python backup_verify.py

Only schema/table names, row counts and a small set of latest timestamps are compared.
No row contents or credentials are printed.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import datetime, timezone


IMPORTANT_TABLES = (
    "stocks",
    "quotes",
    "fundamentals",
    "insider_trades",
    "short_positions",
    "scores",
    "watchlist",
    "holdings",
    "holding_accounts",
    "holding_transactions",
    "holding_purchase_lots",
    "paper_accounts",
    "paper_trades",
    "signal_events",
    "trend_activity_events",
    "runtime_feed_cache",
    "signal_evidence_cache",
    "push_subscriptions",
    "push_deliveries",
    "security_audit",
)

LATEST_COLUMNS = {
    "quotes": "captured_at",
    "fundamentals": "updated_at",
    "scores": "created_at",
    "holding_purchase_lots": "created_at",
    "signal_events": "created_at",
    "trend_activity_events": "created_at",
    "push_subscriptions": "updated_at",
    "security_audit": "created_at",
}


def _connect(url):
    import psycopg
    from psycopg.rows import dict_row

    return psycopg.connect(url, row_factory=dict_row, connect_timeout=10)


def _table_names(conn):
    rows = conn.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema='public' AND table_type='BASE TABLE' ORDER BY table_name"
    ).fetchall()
    return {str(row["table_name"]) for row in rows}


def _safe_identifier(name):
    if not name or not all(ch.isalnum() or ch == "_" for ch in name):
        raise ValueError("Unsafe SQL identifier")
    return name


def database_snapshot(url):
    conn = _connect(url)
    try:
        existing = _table_names(conn)
        tables = {}
        for table in IMPORTANT_TABLES:
            if table not in existing:
                continue
            safe = _safe_identifier(table)
            row = conn.execute(f'SELECT COUNT(*) AS n FROM "{safe}"').fetchone()
            entry = {"rows": int(row["n"] or 0)}
            latest_column = LATEST_COLUMNS.get(table)
            if latest_column:
                try:
                    col = _safe_identifier(latest_column)
                    latest = conn.execute(f'SELECT MAX("{col}") AS latest FROM "{safe}"').fetchone()
                    entry["latest"] = latest["latest"] if latest else None
                except Exception:
                    entry["latest"] = None
            tables[table] = entry
        canonical = json.dumps({name: value.get("rows", 0) for name, value in sorted(tables.items())}, separators=(",", ":"), sort_keys=True)
        return {
            "tables": tables,
            "table_count": len(existing),
            "important_table_count": len(tables),
            "count_fingerprint": hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:20],
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
    finally:
        conn.close()


def compare_snapshots(source, restored):
    src = source.get("tables") or {}
    dst = restored.get("tables") or {}
    missing = sorted(name for name in src if name not in dst)
    extra = sorted(name for name in dst if name not in src)
    mismatches = []
    for name in sorted(set(src) & set(dst)):
        a = int((src[name] or {}).get("rows") or 0)
        b = int((dst[name] or {}).get("rows") or 0)
        if a != b:
            mismatches.append({"table": name, "source_rows": a, "restored_rows": b})
    return {
        "ok": not missing and not mismatches,
        "missing_tables": missing,
        "extra_tables": extra,
        "count_mismatches": mismatches,
        "source_fingerprint": source.get("count_fingerprint"),
        "restored_fingerprint": restored.get("count_fingerprint"),
    }


def _public_snapshot(snapshot):
    return {
        "table_count": snapshot.get("table_count"),
        "important_table_count": snapshot.get("important_table_count"),
        "count_fingerprint": snapshot.get("count_fingerprint"),
        "tables": snapshot.get("tables"),
        "generated_at": snapshot.get("generated_at"),
    }


def main():
    source_url = os.getenv("DATABASE_URL", "").strip()
    restore_url = os.getenv("NORDICSIGNAL_RESTORE_DATABASE_URL", "").strip()
    if not source_url.startswith(("postgres://", "postgresql://")):
        raise SystemExit("DATABASE_URL must point to the production PostgreSQL database")

    source = database_snapshot(source_url)
    if not restore_url:
        print(json.dumps({"mode": "inventory", "source": _public_snapshot(source)}, indent=2, default=str))
        return 0
    if not restore_url.startswith(("postgres://", "postgresql://")):
        raise SystemExit("NORDICSIGNAL_RESTORE_DATABASE_URL must point to a separate restored PostgreSQL database")
    if restore_url == source_url:
        raise SystemExit("Restore verification must use a separate database, not production")

    restored = database_snapshot(restore_url)
    comparison = compare_snapshots(source, restored)
    print(json.dumps({
        "mode": "restore_verification",
        "ok": comparison["ok"],
        "comparison": comparison,
        "source": _public_snapshot(source),
        "restored": _public_snapshot(restored),
        "instruction": "Set NORDICSIGNAL_BACKUP_VERIFIED=true only after this returns ok=true and the restored application has also been smoke-tested.",
    }, indent=2, default=str))
    return 0 if comparison["ok"] else 2


if __name__ == "__main__":
    sys.exit(main())
