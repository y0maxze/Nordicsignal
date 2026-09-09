"""Persistent point-in-time archive for verified IPO Radar candidates.

Candidates are stored idempotently when first observed. This creates a clean audit
trail for later IPO evidence and gives push notifications a stable event source.
"""
from datetime import datetime, timezone
import hashlib
import json

import extra_api
from database import connect
import ipo_radar_runtime as ipo_radar


def _now():
    return datetime.now(timezone.utc).isoformat()


def _candidate_id(item):
    identity = "|".join([
        str(item.get("source_url") or ""),
        str(item.get("company") or ""),
        str(item.get("ticker") or "").upper(),
        str(item.get("expected_listing_date_text") or ""),
        str(item.get("title") or ""),
    ])
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()[:32]


def _ensure_schema():
    conn = connect()
    try:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS ipo_candidates (
          candidate_id TEXT PRIMARY KEY,
          company TEXT,
          ticker TEXT,
          listing_type TEXT,
          market TEXT,
          expected_listing_date_text TEXT,
          offer_price_nok REAL,
          title TEXT,
          source_url TEXT,
          published_at TEXT,
          first_seen_at TEXT NOT NULL,
          last_seen_at TEXT NOT NULL,
          raw_payload TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_ipo_candidates_first_seen
          ON ipo_candidates(first_seen_at);
        CREATE INDEX IF NOT EXISTS idx_ipo_candidates_ticker
          ON ipo_candidates(ticker);
        """)
        conn.commit()
    finally:
        conn.close()


def record_candidates(items):
    _ensure_schema()
    now = _now()
    conn = connect()
    inserted = 0
    try:
        for raw in items or []:
            if not raw.get("official"):
                continue
            candidate_id = _candidate_id(raw)
            existing = conn.execute("SELECT candidate_id FROM ipo_candidates WHERE candidate_id=?", (candidate_id,)).fetchone()
            payload = json.dumps(raw, ensure_ascii=False, separators=(",", ":"), default=str)
            if existing:
                conn.execute("UPDATE ipo_candidates SET last_seen_at=?,raw_payload=? WHERE candidate_id=?", (now, payload, candidate_id))
                continue
            conn.execute("INSERT INTO ipo_candidates(candidate_id,company,ticker,listing_type,market,expected_listing_date_text,offer_price_nok,title,source_url,published_at,first_seen_at,last_seen_at,raw_payload) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)", (candidate_id, raw.get("company"), str(raw.get("ticker") or "").upper() or None, raw.get("listing_type"), raw.get("market"), raw.get("expected_listing_date_text"), raw.get("offer_price_nok"), raw.get("title"), raw.get("source_url"), raw.get("published_at"), now, now, payload))
            inserted += 1
        conn.commit()
    finally:
        conn.close()
    return inserted


def recent_candidates(since=None, limit=20):
    _ensure_schema()
    conn = connect()
    try:
        if since:
            rows = conn.execute("SELECT * FROM ipo_candidates WHERE first_seen_at>? ORDER BY first_seen_at DESC LIMIT ?", (str(since), max(1, min(int(limit or 20), 100)))).fetchall()
        else:
            rows = conn.execute("SELECT * FROM ipo_candidates ORDER BY first_seen_at DESC LIMIT ?", (max(1, min(int(limit or 20), 100)),)).fetchall()
        return [dict(x) for x in rows]
    finally:
        conn.close()


def archive_status(limit=20):
    rows = recent_candidates(limit=limit)
    return {"status":"ok","count":len(rows),"items":rows,"policy":"Verified IPO candidate archive only. No score or threshold changes.","generated_at":_now()}


def install():
    if getattr(extra_api, "_ipo_archive_runtime_v1", False):
        return
    _ensure_schema()
    original_builder = ipo_radar.build_ipo_radar
    def build_and_archive(*args, **kwargs):
        result = original_builder(*args, **kwargs)
        try:
            record_candidates(result.get("items") or [])
        except Exception:
            pass
        return result
    ipo_radar.build_ipo_radar = build_and_archive
    original_install = extra_api.install
    def patched_install(app):
        original_install(app)
        @app.get("/api/ipo-radar/archive")
        def ipo_archive(limit: int = 20):
            return archive_status(limit=limit)
    extra_api.install = patched_install
    extra_api._ipo_archive_runtime_v1 = True


install()
