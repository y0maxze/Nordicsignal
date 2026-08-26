"""Correctness layer for holdings calculations that must use the complete ledger.

The UI intentionally shows a limited transaction history, but portfolio totals and
FIFO tax estimates must never silently change because older rows fell outside that
presentation window.
"""

import holdings_routes
import holdings_tax_runtime
from database import connect


def _full_transaction_summary():
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT transaction_type,COUNT(*) AS row_count,COALESCE(SUM(amount),0) AS total "
            "FROM holding_transactions GROUP BY transaction_type"
        ).fetchall()
        total_rows = conn.execute("SELECT COUNT(*) AS n FROM holding_transactions").fetchone()
    finally:
        conn.close()
    summary = {
        "transaction_count": int(total_rows["n"] or 0) if total_rows else 0,
        "deposits": 0.0,
        "withdrawals": 0.0,
        "dividends": 0.0,
        "buys": 0.0,
        "sells": 0.0,
    }
    labels = {
        "deposit": "deposits",
        "withdrawal": "withdrawals",
        "dividend": "dividends",
        "buy": "buys",
        "sell": "sells",
    }
    for row in rows:
        key = labels.get(str(row["transaction_type"] or "").lower())
        if key:
            summary[key] = float(row["total"] or 0)
    return summary


def _all_trade_transactions():
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT * FROM holding_transactions "
            "WHERE transaction_type IN ('buy','sell') "
            "ORDER BY transaction_date ASC,id ASC"
        ).fetchall()
    finally:
        conn.close()
    return [dict(row) for row in rows]


_original_snapshot = holdings_routes.build_holdings_snapshot


def build_holdings_snapshot_complete(provider=None):
    snapshot = _original_snapshot(provider)
    summary = _full_transaction_summary()
    snapshot["transaction_summary"] = summary
    snapshot["transaction_history_total"] = summary["transaction_count"]
    snapshot["transaction_history_displayed"] = len(snapshot.get("transactions") or [])

    # The previous tax wrapper intentionally raised its window to 1000 rows, but a
    # tax calculation must not have any hidden row limit. Pull every buy/sell and let
    # the FIFO engine itself filter ASK/unsupported account types.
    snapshot["realized_tax"] = holdings_tax_runtime.fifo_realized_analysis(
        _all_trade_transactions()
    )
    return snapshot


def install():
    if getattr(holdings_routes, "_complete_ledger_integrity_installed", False):
        return
    holdings_routes.build_holdings_snapshot = build_holdings_snapshot_complete
    holdings_routes._complete_ledger_integrity_installed = True
