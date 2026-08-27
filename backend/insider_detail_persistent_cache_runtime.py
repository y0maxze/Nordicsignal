"""Persist parsed Euronext insider detail rows across Render restarts.

A primary-insider disclosure identified by its Euronext node id is effectively an
immutable regulatory record. The v2 scanner already caches parsed details in RAM,
but a Render restart previously discarded that cache and could trigger ~40 network
detail fetches on the next market scan. This layer mirrors non-empty parsed rows to
the database and hydrates the existing bounded RAM cache on demand.
"""

from collections import defaultdict
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


def _seed_from_persisted_market_feeds():
    """Reuse already-parsed market-feed rows from the previous process/deploy."""
    try:
        conn = connect()
        try:
            rows = conn.execute(
                "SELECT payload FROM runtime_feed_cache WHERE cache_key LIKE 'insider_market:v1:%'"
            ).fetchall()
        finally:
            conn.close()
    except Exception:
        return 0

    grouped = defaultdict(list)
    for db_row in rows or []:
        try:
            payload = json.loads(db_row["payload"])
        except Exception:
            continue
        for item in payload.get("items") or []:
            if not isinstance(item, dict) or item.get("details_pending"):
                continue
            node_id = str(item.get("node_id") or "").strip()
            if node_id:
                grouped[node_id].append(dict(item))

    seeded = 0
    for node_id, detail_rows in grouped.items():
        if _db_get(node_id):
            continue
        _db_put(node_id, detail_rows)
        seeded += 1
    return seeded


def install():
    if getattr(market, "_persistent_detail_cache_installed", False):
        return
    try:
        _ensure_schema()
        _seed_from_persisted_market_feeds()
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
