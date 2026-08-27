"""Persist parsed Euronext insider detail rows across Render restarts.

A primary-insider disclosure identified by its Euronext node id is effectively an
immutable regulatory record. The v2 scanner already caches parsed details in RAM,
but a Render restart previously discarded that cache and could trigger ~40 network
detail fetches on the next market scan. This layer mirrors non-empty parsed rows to
the database and hydrates the existing bounded RAM cache on demand.
"""

import json
import time

from database import connect
import insider_market_v2_runtime as market


_PERSIST_TTL = 90 * 24 * 3600


def _ensure_schema():
    conn = connect()
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS insider_detail_cache ("
            "node_id TEXT PRIMARY KEY, payload TEXT NOT NULL, updated_at DOUBLE PRECISION NOT NULL)"
        )
        conn.commit()
    finally:
        conn.close()


def _db_get(node_id):
    try:
        conn = connect()
        try:
            row = conn.execute(
                "SELECT payload,updated_at FROM insider_detail_cache WHERE node_id=? LIMIT 1",
                (str(node_id),),
            ).fetchone()
        finally:
            conn.close()
    except Exception:
        return None
    if not row:
        return None
    try:
        updated_at = float(row["updated_at"])
        if time.time() - updated_at > _PERSIST_TTL:
            return None
        rows = json.loads(row["payload"])
        if not isinstance(rows, list) or not rows:
            return None
        return [dict(x) for x in rows if isinstance(x, dict)]
    except Exception:
        return None


def _db_put(node_id, rows):
    rows = [dict(x) for x in (rows or []) if isinstance(x, dict)]
    if not node_id or not rows:
        return
    payload = json.dumps(rows, ensure_ascii=False, separators=(",", ":"), default=str)
    try:
        conn = connect()
        try:
            conn.execute(
                "INSERT INTO insider_detail_cache(node_id,payload,updated_at) VALUES(?,?,?) "
                "ON CONFLICT(node_id) DO UPDATE SET payload=excluded.payload,updated_at=excluded.updated_at",
                (str(node_id), payload, time.time()),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception:
        pass


def install():
    if getattr(market, "_persistent_detail_cache_installed", False):
        return
    try:
        _ensure_schema()
    except Exception:
        # This is purely a performance layer. Live Euronext remains functional if
        # storage is temporarily unavailable.
        pass

    original_get = market._detail_cache_get
    original_put = market._detail_cache_put

    def persistent_get(node_id):
        cached = original_get(node_id)
        if cached is not None:
            return cached
        rows = _db_get(node_id)
        if rows:
            original_put(node_id, rows)
            return [dict(row) for row in rows]
        return None

    def persistent_put(node_id, rows):
        original_put(node_id, rows)
        if rows:
            _db_put(node_id, rows)

    market._detail_cache_get = persistent_get
    market._detail_cache_put = persistent_put
    market._persistent_detail_cache_installed = True


install()
