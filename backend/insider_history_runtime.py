"""Persist verified insider trades seen by NordicSignal.

This creates a durable, deduplicated history from the live Euronext insider feed so
future confluence backtests are not dependent on shallow public archive pagination.
Signal-critical context is retained so internal transfers can still be excluded later.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

import extra_api
from database import connect
import insider_market_v2_runtime as market


def _text(value):
    return str(value or "").strip()


def _actor(row):
    return _text(
        row.get("person")
        or row.get("related_primary_insider")
        or row.get("insider")
        or row.get("entity")
        or row.get("actor")
    )


def _bool_int(value):
    if value is True:
        return 1
    if value is False:
        return 0
    return None


def _fingerprint(row):
    payload = {
        "ticker": _text(row.get("ticker")).upper(),
        "date": _text(row.get("trade_date") or row.get("date"))[:10],
        "actor": _actor(row).lower(),
        "direction": _text(row.get("direction") or row.get("transaction_type")).lower(),
        "shares": row.get("shares"),
        "price": row.get("price"),
        "node_id": _text(row.get("node_id")),
        "url": _text(row.get("newsweb_url") or row.get("url")),
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def ensure_table():
    conn = connect()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS insider_history (
                fingerprint TEXT PRIMARY KEY,
                ticker TEXT NOT NULL,
                company TEXT,
                actor TEXT,
                related_primary_insider TEXT,
                role TEXT,
                direction TEXT,
                activity_type TEXT,
                shares DOUBLE PRECISION,
                price DOUBLE PRECISION,
                trade_date TEXT,
                published_at TEXT,
                transaction_value DOUBLE PRECISION,
                value_basis TEXT,
                internal_transfer INTEGER,
                economic_exposure_unchanged INTEGER,
                title TEXT,
                summary TEXT,
                source TEXT,
                source_url TEXT,
                node_id TEXT,
                captured_at TEXT NOT NULL
            )
        """)
        conn.commit()
    finally:
        conn.close()


def persist_items(items):
    ensure_table()
    now = datetime.now(timezone.utc).isoformat()
    inserted = 0
    conn = connect()
    try:
        for row in items or []:
            if not isinstance(row, dict) or row.get("details_pending"):
                continue
            ticker = _text(row.get("ticker")).upper()
            direction = _text(row.get("direction") or row.get("transaction_type")).lower()
            if not ticker or direction not in {"buy", "sell"}:
                continue
            fp = _fingerprint(row)
            if conn.execute("SELECT 1 FROM insider_history WHERE fingerprint=?", (fp,)).fetchone():
                continue
            value = row.get("transaction_value")
            if value is None:
                value = row.get("display_transaction_value")
            if value is None:
                value = row.get("display_value")
            conn.execute("""
                INSERT INTO insider_history(
                    fingerprint,ticker,company,actor,related_primary_insider,role,direction,activity_type,
                    shares,price,trade_date,published_at,transaction_value,value_basis,internal_transfer,
                    economic_exposure_unchanged,title,summary,source,source_url,node_id,captured_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                fp,
                ticker,
                _text(row.get("company")) or None,
                _actor(row) or None,
                _text(row.get("related_primary_insider")) or None,
                _text(row.get("role")) or None,
                direction,
                _text(row.get("activity_type")) or None,
                row.get("shares"),
                row.get("price"),
                _text(row.get("trade_date") or row.get("date"))[:10] or None,
                _text(row.get("published_at")) or None,
                value,
                _text(row.get("transaction_value_basis") or row.get("value_basis")) or None,
                _bool_int(row.get("internal_transfer")),
                _bool_int(row.get("economic_exposure_unchanged")),
                _text(row.get("title")) or None,
                _text(row.get("summary")) or None,
                _text(row.get("source")) or None,
                _text(row.get("newsweb_url") or row.get("url")) or None,
                _text(row.get("node_id")) or None,
                now,
            ))
            inserted += 1
        conn.commit()
    finally:
        conn.close()
    return inserted


def history(limit=500, ticker=None):
    ensure_table()
    limit = max(1, min(int(limit or 500), 5000))
    conn = connect()
    try:
        if ticker:
            rows = conn.execute(
                "SELECT * FROM insider_history WHERE ticker=? ORDER BY COALESCE(trade_date,published_at) DESC LIMIT ?",
                (_text(ticker).upper(), limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM insider_history ORDER BY COALESCE(trade_date,published_at) DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def install():
    if getattr(market, "_insider_history_runtime", False):
        return
    ensure_table()
    original_feed = market.market_insider_feed

    def wrapped_feed(limit=60, days=14, refresh=False):
        result = original_feed(limit=limit, days=days, refresh=refresh)
        try:
            persist_items(result.get("items") or [])
        except Exception:
            pass
        return result

    market.market_insider_feed = wrapped_feed
    market._insider_history_runtime = True

    original_install = extra_api.install

    def patched_install(app):
        original_install(app)

        @app.get("/api/insider-history")
        def insider_history(limit: int = 500, ticker: str | None = None):
            items = history(limit=limit, ticker=ticker)
            return {
                "status": "ok",
                "items": items,
                "count": len(items),
                "source": "NordicSignal persistent verified insider history",
            }

    extra_api.install = patched_install


install()
