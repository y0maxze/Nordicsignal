"""Operational health checks for NordicSignal production persistence.

The endpoint intentionally exposes only storage type, row counts and timestamps.
It never returns DATABASE_URL, credentials or user-entered transaction contents.
"""

from datetime import datetime, timezone

import extra_api
from database import connect, USING_POSTGRES


_TABLES = (
    "stocks",
    "scores",
    "watchlist",
    "holdings",
    "holding_accounts",
    "holding_transactions",
    "holding_purchase_lots",
    "paper_accounts",
    "paper_trades",
    "signal_events",
    "signal_instrument_catalog",
)

_LATEST_FIELDS = (
    ("scores", "created_at"),
    ("holdings", "updated_at"),
    ("holding_transactions", "created_at"),
    ("holding_purchase_lots", "created_at"),
    ("paper_trades", "executed_at"),
    ("signal_events", "created_at"),
)


def _safe_count(conn, table):
    try:
        row = conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()
        return int(row["n"] or 0) if row else 0
    except Exception:
        return None


def _safe_latest(conn, table, field):
    try:
        row = conn.execute(f"SELECT MAX({field}) AS latest FROM {table}").fetchone()
        return row["latest"] if row else None
    except Exception:
        return None


def system_health():
    counts = {}
    latest = {}
    database_ok = False
    error = None
    conn = None
    try:
        conn = connect()
        database_ok = True
        counts = {table: _safe_count(conn, table) for table in _TABLES}
        latest = {
            table: _safe_latest(conn, table, field)
            for table, field in _LATEST_FIELDS
        }
    except Exception as exc:
        error = type(exc).__name__
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass

    warnings = []
    if not USING_POSTGRES:
        warnings.append(
            "Production is using local SQLite. On an ephemeral hosting filesystem, user-entered data can be lost on restart or redeploy."
        )
    if not database_ok:
        warnings.append("Database connectivity check failed.")

    return {
        "status": "ok" if database_ok and USING_POSTGRES else "warning" if database_ok else "error",
        "storage_backend": "postgres" if USING_POSTGRES else "sqlite",
        "persistent_storage": bool(USING_POSTGRES),
        "database_ok": database_ok,
        "counts": counts,
        "latest": latest,
        "warnings": warnings,
        "error": error,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


def install():
    if getattr(extra_api, "_system_health_runtime_v1", False):
        return
    original_install = extra_api.install

    def patched_install(app):
        original_install(app)

        @app.get("/api/system-health")
        def system_health_route():
            return system_health()

    extra_api.install = patched_install
    extra_api._system_health_runtime_v1 = True


install()
