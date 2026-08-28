"""Data-quality checks for NordicSignal's persisted finance state.

This endpoint does not invent a single confidence number. It exposes concrete checks
that can fail independently, so the UI and operator can see exactly what is stale or
invalid before trusting a signal.
"""
from datetime import datetime, timezone

import extra_api
from database import connect, USING_POSTGRES

SCORE_MAX_AGE_SECONDS = 30 * 60


def _now():
    return datetime.now(timezone.utc).isoformat()


def _age_seconds(value):
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return max(0, int((datetime.now(timezone.utc) - dt).total_seconds()))
    except Exception:
        return None


def _check(name, ok, detail, severity="error"):
    return {"name":name,"ok":bool(ok),"severity":severity,"detail":detail}


def data_quality_snapshot():
    checks = []
    metrics = {}
    conn = connect()
    try:
        active = conn.execute("SELECT COUNT(*) n FROM stocks WHERE active=1").fetchone()
        active_n = int(active["n"] or 0) if active else 0
        metrics["active_stocks"] = active_n
        checks.append(_check("active_universe", active_n > 0, f"{active_n} active stocks"))

        rows = conn.execute(
            "SELECT s.ticker,sc.total,sc.created_at,COALESCE(sc.source,'stored') source "
            "FROM stocks s JOIN scores sc ON sc.id=(SELECT MAX(id) FROM scores x WHERE x.ticker=s.ticker) "
            "WHERE s.active=1 ORDER BY s.ticker"
        ).fetchall()
        latest = [dict(x) for x in rows]
        metrics["latest_score_rows"] = len(latest)
        invalid_scores = [x["ticker"] for x in latest if float(x.get("total") or -1) < 0 or float(x.get("total") or 101) > 100]
        checks.append(_check("score_range", not invalid_scores, "All latest scores are 0-100" if not invalid_scores else "Invalid scores: "+", ".join(invalid_scores[:8])))
        checks.append(_check("score_coverage", len(latest) == active_n and active_n > 0, f"{len(latest)}/{active_n} active stocks have a latest score"))
        ages = [(x["ticker"], _age_seconds(x.get("created_at"))) for x in latest]
        stale = [ticker for ticker, age in ages if age is None or age > SCORE_MAX_AGE_SECONDS]
        max_age = max((age for _, age in ages if age is not None), default=None)
        metrics["oldest_score_age_seconds"] = max_age
        checks.append(_check("score_freshness", not stale, "Latest score set is fresh" if not stale else f"{len(stale)} stale/undated score rows", severity="warning"))
        seed = [x["ticker"] for x in latest if x.get("source") == "seed"]
        checks.append(_check("no_seed_scores", not seed, "No active stock is using a seed score" if not seed else "Seed score active for: "+", ".join(seed[:8])))

        try:
            row = conn.execute("SELECT COUNT(*) n FROM trend_activity_events WHERE volume_ratio<0 OR recent_volume_ratio<0").fetchone()
            bad = int(row["n"] or 0) if row else 0
            checks.append(_check("trend_volume_sanity", bad == 0, "No negative volume ratios" if bad == 0 else f"{bad} invalid trend volume rows"))
        except Exception:
            checks.append(_check("trend_volume_sanity", True, "Trend event table not populated yet", severity="info"))

        try:
            row = conn.execute("SELECT COUNT(*) n FROM holding_purchase_lots WHERE shares<=0 OR purchase_price<=0").fetchone()
            bad = int(row["n"] or 0) if row else 0
            checks.append(_check("holding_lot_sanity", bad == 0, "All purchase lots have positive shares and price" if bad == 0 else f"{bad} invalid purchase lots"))
        except Exception:
            checks.append(_check("holding_lot_sanity", True, "Purchase-lot table unavailable/not initialized", severity="info"))
    finally:
        conn.close()

    errors = [x for x in checks if not x["ok"] and x["severity"] == "error"]
    warnings = [x for x in checks if not x["ok"] and x["severity"] == "warning"]
    status = "error" if errors else "warning" if warnings else "ok"
    return {
        "status":status,
        "persistent_storage":bool(USING_POSTGRES),
        "checks":checks,
        "metrics":metrics,
        "error_count":len(errors),
        "warning_count":len(warnings),
        "source_policy":{
            "prices":"Yahoo Finance",
            "insider":"Euronext Oslo Børs / Oslo Børs Newspoint",
            "short":"Finanstilsynet SSR",
            "calendar":"Euronext financial calendar",
        },
        "generated_at":_now(),
    }


def install():
    if getattr(extra_api, "_data_quality_runtime_installed", False):
        return
    original_install = extra_api.install

    def patched_install(app):
        original_install(app)

        @app.get("/api/data-quality")
        def data_quality_route():
            return data_quality_snapshot()

    extra_api.install = patched_install
    extra_api._data_quality_runtime_installed = True


install()
