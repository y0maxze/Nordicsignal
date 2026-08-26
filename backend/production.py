"""Production entrypoint for NordicSignal.

The development ``main`` module keeps its eager refresh behaviour for backwards
compatibility. Render imports this module instead so the HTTP service becomes ready
immediately and expensive market refreshes warm in the background.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import gc
import logging
import os
import threading
import time

from starlette.responses import JSONResponse

import main
from database import connect

log = logging.getLogger("nordicsignal.production")
app = main.app

_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_scores_ticker_id ON scores(ticker,id)",
    "CREATE INDEX IF NOT EXISTS idx_scores_created_at ON scores(created_at)",
    "CREATE INDEX IF NOT EXISTS idx_quotes_ticker_captured ON quotes(ticker,captured_at)",
    "CREATE INDEX IF NOT EXISTS idx_holding_tx_account_date ON holding_transactions(broker,account_type,transaction_date,id)",
    "CREATE INDEX IF NOT EXISTS idx_holding_tx_ticker_type_date ON holding_transactions(ticker,transaction_type,transaction_date,id)",
    "CREATE INDEX IF NOT EXISTS idx_signal_events_class_created ON signal_events(asset_class,created_at,id)",
    "CREATE INDEX IF NOT EXISTS idx_signal_catalog_class_seen ON signal_instrument_catalog(asset_class,last_seen_at)",
)

_REFRESH_COOLDOWN_SECONDS = 60
_REFRESH_STATE_LOCK = threading.Lock()
_REFRESH_IN_PROGRESS = False
_LAST_REFRESH_FINISHED_AT = 0.0


def _bounded_env_int(name, default, low=1, high=4):
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(low, min(high, value))


# Render Free has a 512 MB RAM ceiling. Provider work is network-bound, but each
# concurrent curl/JSON parse also has a real native/Python memory cost. Two workers
# keep useful parallelism without allowing five large market responses to peak at once.
_PROVIDER_WORKERS = _bounded_env_int("NORDICSIGNAL_PROVIDER_WORKERS", 2)


def _production_refresh_all(limit=None, include_insider=True):
    """Memory-bounded replacement for main.refresh_all used by production only."""
    tickers = main.TICKERS[:limit] if limit else main.TICKERS
    results = []
    with ThreadPoolExecutor(max_workers=_PROVIDER_WORKERS) as pool:
        futures = {
            pool.submit(main.refresh_one, ticker, include_insider): ticker
            for ticker in tickers
        }
        for future in as_completed(futures):
            try:
                results.append(future.result())
            except Exception as exc:
                ticker = futures[future]
                results.append({"ticker": ticker, "source": "stored", "live_verified": False, "error": str(exc)})
    return sorted(results, key=lambda item: item.get("ticker", ""))


def _begin_provider_refresh(enforce_cooldown=True):
    """Reserve the one production slot for expensive provider-wide refresh work."""
    global _REFRESH_IN_PROGRESS
    now = time.monotonic()
    with _REFRESH_STATE_LOCK:
        if _REFRESH_IN_PROGRESS:
            return False, "in_progress", 1
        if enforce_cooldown and _LAST_REFRESH_FINISHED_AT:
            elapsed = max(0.0, now - _LAST_REFRESH_FINISHED_AT)
            if elapsed < _REFRESH_COOLDOWN_SECONDS:
                retry_after = max(1, int(_REFRESH_COOLDOWN_SECONDS - elapsed + 0.999))
                return False, "cooldown", retry_after
        _REFRESH_IN_PROGRESS = True
        return True, "ok", 0


def _finish_provider_refresh(mark_finished=True):
    """Release the refresh slot and optionally start the anti-stampede cooldown."""
    global _REFRESH_IN_PROGRESS, _LAST_REFRESH_FINISHED_AT
    with _REFRESH_STATE_LOCK:
        _REFRESH_IN_PROGRESS = False
        if mark_finished:
            _LAST_REFRESH_FINISHED_AT = time.monotonic()


def _reset_refresh_guard_for_tests():
    global _REFRESH_IN_PROGRESS, _LAST_REFRESH_FINISHED_AT
    with _REFRESH_STATE_LOCK:
        _REFRESH_IN_PROGRESS = False
        _LAST_REFRESH_FINISHED_AT = 0.0


@app.middleware("http")
async def provider_refresh_guard(request, call_next):
    """Prevent overlapping/click-spammed full refreshes in the production process."""
    if request.url.path != "/api/refresh":
        return await call_next(request)

    allowed, reason, retry_after = _begin_provider_refresh(enforce_cooldown=True)
    if not allowed:
        message = (
            "A market refresh is already running"
            if reason == "in_progress"
            else "Market data was refreshed recently"
        )
        return JSONResponse(
            {
                "status": "busy",
                "code": "REFRESH_IN_PROGRESS" if reason == "in_progress" else "REFRESH_COOLDOWN",
                "message": message,
                "retry_after_seconds": retry_after,
            },
            status_code=429,
            headers={"Retry-After": str(retry_after)},
        )

    response = None
    try:
        response = await call_next(request)
        return response
    finally:
        # Even a failed provider attempt gets a short cooldown. Immediate retries are
        # more likely to amplify an upstream outage than to repair it.
        _finish_provider_refresh(mark_finished=True)


def deduplicate_routes():
    """Drop exact shadowed route duplicates while preserving first-match behaviour."""
    seen = set()
    unique = []
    removed = []
    for route in app.router.routes:
        methods = getattr(route, "methods", None)
        path = getattr(route, "path", None)
        if not path or not methods:
            unique.append(route)
            continue
        key = (path, tuple(sorted(methods)))
        if key in seen:
            removed.append(key)
            continue
        seen.add(key)
        unique.append(route)
    if removed:
        app.router.routes[:] = unique
        log.info("Removed %d shadowed duplicate routes", len(removed))
    return removed


def ensure_indexes():
    """Create performance indexes without making optional tables a startup blocker."""
    for statement in _INDEXES:
        conn = None
        try:
            conn = connect()
            conn.execute(statement)
            conn.commit()
        except Exception as exc:
            # Optional runtime tables may legitimately be unavailable if a module was
            # disabled. One missing index must never abort application startup.
            log.warning("Index setup skipped: %s", exc)
            try:
                if conn is not None:
                    conn.rollback()
            except Exception:
                pass
        finally:
            try:
                if conn is not None:
                    conn.close()
            except Exception:
                pass


def _latest_scores_fresh(max_age_seconds=300):
    """True only when every active stock has a recent non-seed score."""
    conn = None
    try:
        conn = connect()
        row = conn.execute(
            "SELECT MIN(sc.created_at) AS oldest,COUNT(*) AS n,"
            "SUM(CASE WHEN COALESCE(sc.source,'stored') IN ('live','partial_live') THEN 1 ELSE 0 END) AS live_n "
            "FROM stocks st JOIN scores sc ON sc.id=(SELECT MAX(id) FROM scores x WHERE x.ticker=st.ticker) "
            "WHERE st.active=1"
        ).fetchone()
        if not row or int(row["n"] or 0) < len(main.TICKERS) or int(row["live_n"] or 0) < len(main.TICKERS):
            return False
        oldest = datetime.fromisoformat(str(row["oldest"]))
        if oldest.tzinfo is None:
            oldest = oldest.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - oldest).total_seconds() <= max_age_seconds
    except Exception:
        return False
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def _fresh_partial_components(ticker, max_age_seconds=120):
    """Return fresh market components that are safe to upgrade with insider data.

    Only ``partial_live`` rows qualify. This prevents an insider-only request from
    stamping a new timestamp onto stale market components when Yahoo failed during
    the first warmup phase.
    """
    conn = None
    try:
        conn = connect()
        row = conn.execute(
            "SELECT fundamentals,valuation,sentiment,created_at,COALESCE(source,'stored') source "
            "FROM scores WHERE ticker=? ORDER BY id DESC LIMIT 1",
            (ticker,),
        ).fetchone()
        if not row or row["source"] != "partial_live":
            return None
        updated = datetime.fromisoformat(str(row["created_at"]))
        if updated.tzinfo is None:
            updated = updated.replace(tzinfo=timezone.utc)
        if (datetime.now(timezone.utc) - updated).total_seconds() > max_age_seconds:
            return None
        return {
            "fundamentals": int(row["fundamentals"]),
            "valuation": int(row["valuation"]),
            "sentiment": int(row["sentiment"]),
        }
    except Exception:
        return None
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def _refresh_insider_one(ticker):
    """Upgrade one fresh partial score using only the regulatory insider provider."""
    components = _fresh_partial_components(ticker)
    if not components:
        return {"ticker": ticker, "source": "stored", "upgraded": False}

    row = next((item for item in main.UNIVERSE if item[0] == ticker), None)
    company_name = row[1] if row else ticker
    try:
        insider = main.regulatory.insider(ticker, company_name)
    except Exception as exc:
        return {"ticker": ticker, "source": "partial_live", "upgraded": False, "error": str(exc)}

    insider_value = main.insider_score(insider)
    if insider_value is None:
        return {"ticker": ticker, "source": "partial_live", "upgraded": False}

    total = main.clamp_score(
        components["fundamentals"] + components["valuation"] + components["sentiment"] + insider_value,
        0,
        100,
    )
    now = datetime.now(timezone.utc).isoformat()
    conn = None
    try:
        conn = connect()
        conn.execute(
            "INSERT INTO scores(ticker,fundamentals,insider,valuation,sentiment,total,created_at,source) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (
                ticker,
                components["fundamentals"],
                insider_value,
                components["valuation"],
                components["sentiment"],
                total,
                now,
                "live",
            ),
        )
        conn.commit()
        return {"ticker": ticker, "source": "live", "upgraded": True}
    except Exception as exc:
        try:
            if conn is not None:
                conn.rollback()
        except Exception:
            pass
        return {"ticker": ticker, "source": "partial_live", "upgraded": False, "error": str(exc)}
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def _refresh_insiders_only():
    """Run the slower regulatory phase without repeating Yahoo market requests."""
    results = []
    with ThreadPoolExecutor(max_workers=_PROVIDER_WORKERS) as pool:
        futures = {pool.submit(_refresh_insider_one, ticker): ticker for ticker in main.TICKERS}
        for future in as_completed(futures):
            try:
                results.append(future.result())
            except Exception as exc:
                ticker = futures[future]
                results.append({"ticker": ticker, "source": "partial_live", "upgraded": False, "error": str(exc)})
    return sorted(results, key=lambda item: item.get("ticker", ""))


def _market_warmup():
    """Warm public market data after the server is already accepting requests."""
    # Avoid hammering providers on rapid auto-deploys when all market rows were just
    # refreshed by the previous instance. Seed rows never qualify as fresh here.
    time.sleep(1)
    if _latest_scores_fresh():
        log.info("Skipping provider warmup because all active scores are fresh")
        return

    allowed, reason, _ = _begin_provider_refresh(enforce_cooldown=False)
    if not allowed:
        log.info("Skipping provider warmup because another refresh is %s", reason)
        return

    try:
        try:
            main.refresh_all(include_insider=False)
        except Exception:
            log.exception("Background market refresh failed")
        finally:
            # Encourage short-lived Yahoo JSON/history objects to be reclaimed before
            # the regulatory phase starts on memory-constrained Render instances.
            gc.collect()

        # Give the first dashboard requests priority before the slower regulatory pass.
        # This second phase deliberately reuses the fresh partial score components so it
        # does not repeat Yahoo quote/fundamentals/history work for all 24 instruments.
        time.sleep(3)
        try:
            _refresh_insiders_only()
        except Exception:
            log.exception("Background insider refresh failed")
        finally:
            gc.collect()
    finally:
        _finish_provider_refresh(mark_finished=True)


def production_startup():
    main.init_db()
    main.seed_db()
    ensure_indexes()
    log.info("Production provider concurrency limited to %d workers", _PROVIDER_WORKERS)
    threading.Thread(
        target=_market_warmup,
        daemon=True,
        name="nordicsignal-market-warmup",
    ).start()


# Production uses a lower-memory refresh implementation. The existing route handler
# resolves main.refresh_all at request time, so this also protects manual /api/refresh.
main.refresh_all = _production_refresh_all

# main.startup synchronously refreshed all 24 stocks before Uvicorn reported ready.
# Replace exactly that handler in production while leaving local/dev behaviour intact.
deduplicate_routes()
try:
    app.router.on_startup.remove(main.startup)
except ValueError:
    pass
if production_startup not in app.router.on_startup:
    app.router.on_startup.append(production_startup)
