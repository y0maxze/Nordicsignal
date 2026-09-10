"""Attach IPO Radar discovery to NordicSignal's existing external 10-minute scan path.

The existing Opportunity scheduler is already woken by Cloudflare Cron. Wrapping the
shared scan function lets the same wake-up refresh verified IPO announcements without
adding another external cron or weakening the protected write endpoint.
"""
from datetime import datetime, timezone
import logging
import threading
import time

import extra_api
from database import connect
import opportunity_tracking_runtime as tracking
import ipo_radar_runtime
import ipo_listing_registry_runtime

log = logging.getLogger("nordicsignal.ipo_autoscan")
REGISTRY_SYNC_INTERVAL_SECONDS = 6 * 60 * 60
_LOCK = threading.Lock()
_LAST_REGISTRY_SYNC_MONO = 0.0


def _now():
    return datetime.now(timezone.utc).isoformat()


def _ensure_schema():
    conn = connect()
    try:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS ipo_scheduler_state (
          id INTEGER PRIMARY KEY,
          last_scan_at TEXT,
          last_scan_status TEXT,
          last_candidate_count INTEGER,
          last_registry_sync_at TEXT,
          last_registry_status TEXT,
          updated_at TEXT NOT NULL
        );
        """)
        conn.commit()
    finally:
        conn.close()


def _write_state(scan_status, candidate_count=None, registry_status=None, registry_synced=False):
    _ensure_schema()
    now = _now()
    conn = connect()
    try:
        row = conn.execute("SELECT id,last_registry_sync_at,last_registry_status FROM ipo_scheduler_state WHERE id=1").fetchone()
        previous = dict(row) if row else {}
        last_registry_at = now if registry_synced else previous.get("last_registry_sync_at")
        last_registry_status = registry_status if registry_synced else previous.get("last_registry_status")
        if row:
            conn.execute(
                "UPDATE ipo_scheduler_state SET last_scan_at=?,last_scan_status=?,last_candidate_count=?,last_registry_sync_at=?,last_registry_status=?,updated_at=? WHERE id=1",
                (now, scan_status, candidate_count, last_registry_at, last_registry_status, now),
            )
        else:
            conn.execute(
                "INSERT INTO ipo_scheduler_state(id,last_scan_at,last_scan_status,last_candidate_count,last_registry_sync_at,last_registry_status,updated_at) VALUES(1,?,?,?,?,?,?)",
                (now, scan_status, candidate_count, last_registry_at, last_registry_status, now),
            )
        conn.commit()
    finally:
        conn.close()


def _registry_due():
    with _LOCK:
        return not _LAST_REGISTRY_SYNC_MONO or time.monotonic() - _LAST_REGISTRY_SYNC_MONO >= REGISTRY_SYNC_INTERVAL_SECONDS


def _mark_registry_sync():
    global _LAST_REGISTRY_SYNC_MONO
    with _LOCK:
        _LAST_REGISTRY_SYNC_MONO = time.monotonic()


def scan_ipo_once():
    """Refresh upcoming candidates and periodically refresh the completed-listing register."""
    scan_status = "ok"
    candidate_count = None
    registry_status = None
    registry_synced = False
    try:
        radar = ipo_radar_runtime.build_ipo_radar(force=True)
        candidate_count = int(radar.get("count") or 0)
        scan_status = str(radar.get("status") or "ok")
    except Exception:
        log.exception("IPO Radar refresh failed")
        scan_status = "unavailable"

    if _registry_due():
        try:
            result = ipo_listing_registry_runtime.sync_listings()
            registry_status = str(result.get("status") or "ok")
        except Exception:
            log.exception("IPO listing registry sync failed")
            registry_status = "unavailable"
        finally:
            _mark_registry_sync()
            registry_synced = True

    try:
        _write_state(scan_status, candidate_count, registry_status, registry_synced)
    except Exception:
        log.exception("Could not persist IPO scheduler status")
    return {
        "status": scan_status,
        "candidate_count": candidate_count,
        "registry_synced": registry_synced,
        "registry_status": registry_status,
    }


def scheduler_status():
    _ensure_schema()
    conn = connect()
    try:
        row = conn.execute("SELECT * FROM ipo_scheduler_state WHERE id=1").fetchone()
    finally:
        conn.close()
    state = dict(row) if row else {}
    return {
        "status": "ok",
        "external_scan_bridge": True,
        "upcoming_scan_interval_seconds": 10 * 60,
        "registry_sync_interval_seconds": REGISTRY_SYNC_INTERVAL_SECONDS,
        "last_scan_at": state.get("last_scan_at"),
        "last_scan_status": state.get("last_scan_status"),
        "last_candidate_count": state.get("last_candidate_count"),
        "last_registry_sync_at": state.get("last_registry_sync_at"),
        "last_registry_status": state.get("last_registry_status"),
        "generated_at": _now(),
    }


def install():
    if getattr(tracking, "_ipo_autoscan_bridge_v1", False):
        return
    _ensure_schema()
    original_scan = tracking._maybe_schedule_scan

    def scan_with_ipo(*args, **kwargs):
        state = original_scan(*args, **kwargs)
        try:
            scan_ipo_once()
        except Exception:
            # IPO discovery is additive and must never break the core opportunity scan.
            log.exception("IPO autoscan side effect failed")
        return state

    tracking._maybe_schedule_scan = scan_with_ipo
    tracking._ipo_autoscan_bridge_v1 = True
    original_install = extra_api.install

    def patched_install(app):
        original_install(app)
        @app.get("/api/ipo-radar/autoscan/status")
        def ipo_autoscan_status():
            return scheduler_status()

    extra_api.install = patched_install


install()
