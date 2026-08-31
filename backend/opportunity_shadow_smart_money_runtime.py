"""Persist and measure Smart Money metadata alongside immutable Shadow snapshots.

Uses a sidecar table keyed by snapshot_id so the original frozen shadow schema and rows
remain untouched. New captures store Smart Money only when the base snapshot is created
in the same call. A later scan must never backfill a missing sidecar with newer feature
values and pretend they were first-observed. Missing sidecars are surfaced by health.
This is research-only and never changes live Opportunity labels, thresholds or scores.
"""
from __future__ import annotations

from datetime import datetime, timezone
import extra_api
import opportunity_shadow_dataset_runtime as shadow
import opportunity_tracking_runtime as tracking
import opportunity_version_identity_runtime as identity_runtime

_BASE_CAPTURE = shadow.capture_snapshot
_BASE_STATUS = shadow.shadow_status


def _now():
    return datetime.now(timezone.utc).isoformat()


def _num(value, default=0.0):
    try:
        return float(value) if value is not None else float(default)
    except (TypeError, ValueError):
        return float(default)


def _ensure_schema():
    conn = tracking.connect()
    try:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS opportunity_shadow_smart_money (
          snapshot_id BIGINT PRIMARY KEY,
          smart_money_quality TEXT NOT NULL,
          smart_money_points INTEGER NOT NULL,
          meaningful_actors_500k_plus INTEGER NOT NULL,
          million_plus_actors INTEGER NOT NULL,
          senior_actors INTEGER NOT NULL,
          role_adjusted_qualified_value_nok DOUBLE PRECISION NOT NULL,
          captured_at TEXT NOT NULL
        );
        """)
        conn.commit()
    finally:
        conn.close()


def _smart_from_result(result):
    components = (((result or {}).get("opportunity") or {}).get("components") or {})
    return {
        "quality": str(components.get("smart_money_quality") or "LOW").upper(),
        "points": int(_num(components.get("smart_money_points"), 0)),
        "meaningful": int(_num(components.get("meaningful_actors_500k_plus"), 0)),
        "million": int(_num(components.get("million_plus_actors"), 0)),
        "senior": int(_num(components.get("senior_actors"), 0)),
        "role_adjusted": _num(components.get("role_adjusted_qualified_value_nok"), 0.0),
    }


def _persist(snapshot_id, smart):
    if not snapshot_id:
        return False
    conn = tracking.connect()
    try:
        cur = conn.execute(
            "INSERT INTO opportunity_shadow_smart_money(snapshot_id,smart_money_quality,smart_money_points,meaningful_actors_500k_plus,million_plus_actors,senior_actors,role_adjusted_qualified_value_nok,captured_at) VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(snapshot_id) DO NOTHING",
            (int(snapshot_id), smart["quality"], smart["points"], smart["meaningful"], smart["million"], smart["senior"], smart["role_adjusted"], _now()),
        )
        conn.commit()
        return bool(getattr(cur, "rowcount", 0))
    finally:
        conn.close()


def capture_snapshot_with_smart_money(result):
    info = _BASE_CAPTURE(result)
    # Preserve immutable first-observed semantics: only a newly inserted base snapshot
    # may receive sidecar features from this result. If sidecar persistence fails, a
    # later scan leaves it missing and health exposes the data-quality problem.
    if bool((info or {}).get("captured")):
        try:
            _persist((info or {}).get("snapshot_id"), _smart_from_result(result))
        except Exception:
            pass
    return info


def smart_money_performance():
    model_id = str(identity_runtime._current_identity().get("signal_model_id") or "unknown")
    conn = tracking.connect()
    try:
        snapshots = [dict(row) for row in conn.execute(
            "SELECT s.id,s.ticker,s.market_date,m.smart_money_quality,m.smart_money_points,m.meaningful_actors_500k_plus,m.million_plus_actors,m.senior_actors,m.role_adjusted_qualified_value_nok FROM opportunity_shadow_snapshots s LEFT JOIN opportunity_shadow_smart_money m ON m.snapshot_id=s.id WHERE s.signal_model_id=? ORDER BY s.market_date,s.id",
            (model_id,),
        ).fetchall()]
        returns = [dict(row) for row in conn.execute(
            "SELECT r.snapshot_id,r.horizon_days,r.return_pct,r.excess_return_pct FROM opportunity_shadow_returns r JOIN opportunity_shadow_snapshots s ON s.id=r.snapshot_id WHERE s.signal_model_id=? ORDER BY r.snapshot_id,r.horizon_days",
            (model_id,),
        ).fetchall()]
    finally:
        conn.close()

    by_id = {int(row["id"]): row for row in snapshots}
    qualities = {"LOW": [], "MEDIUM": [], "HIGH": []}
    missing = 0
    for row in snapshots:
        quality = str(row.get("smart_money_quality") or "").upper()
        if quality not in qualities:
            missing += 1
            continue
        qualities[quality].append(row)

    measurements = {q: {} for q in qualities}
    for ret in returns:
        snap = by_id.get(int(ret["snapshot_id"]))
        if not snap:
            continue
        q = str(snap.get("smart_money_quality") or "").upper()
        if q not in measurements:
            continue
        h = str(int(ret["horizon_days"]))
        measurements[q].setdefault(h, []).append(ret)

    def stats(rows):
        raw = [_num(x.get("return_pct")) for x in rows if x.get("return_pct") is not None]
        alpha = [_num(x.get("excess_return_pct")) for x in rows if x.get("excess_return_pct") is not None]
        return {
            "n": len(raw),
            "mean_return_pct": round(sum(raw) / len(raw), 3) if raw else None,
            "positive_rate_pct": round(sum(1 for x in raw if x > 0) * 100 / len(raw), 1) if raw else None,
            "alpha_n": len(alpha),
            "mean_excess_return_pct": round(sum(alpha) / len(alpha), 3) if alpha else None,
            "positive_alpha_rate_pct": round(sum(1 for x in alpha if x > 0) * 100 / len(alpha), 1) if alpha else None,
        }

    return {
        "status": "ok",
        "active_signal_model_id": model_id,
        "snapshots": len(snapshots),
        "missing_smart_money_sidecar": missing,
        "quality_counts": {q: len(rows) for q, rows in qualities.items()},
        "by_quality": {q: {h: stats(rows) for h, rows in sorted(horizons.items(), key=lambda kv: int(kv[0]))} for q, horizons in measurements.items()},
        "measurement_only": True,
        "automatic_threshold_changes": False,
        "meaning": "Forward performance of frozen Smart Money quality states in the active Shadow model only.",
        "generated_at": _now(),
    }


def shadow_status_with_smart_money():
    status = dict(_BASE_STATUS() or {})
    try:
        report = smart_money_performance()
        status["smart_money"] = {
            "quality_counts": report.get("quality_counts") or {},
            "missing_sidecar": int(report.get("missing_smart_money_sidecar") or 0),
            "performance_available": any(bool(v) for v in (report.get("by_quality") or {}).values()),
        }
    except Exception as exc:
        status["smart_money"] = {"error": str(exc)}
    return status


def install():
    if getattr(extra_api, "_opportunity_shadow_smart_money_runtime", False):
        return
    _ensure_schema()
    shadow.capture_snapshot = capture_snapshot_with_smart_money
    shadow.shadow_status = shadow_status_with_smart_money
    original_install = extra_api.install

    def patched_install(app):
        original_install(app)
        @app.get("/api/opportunity-shadow/smart-money-performance")
        def opportunity_shadow_smart_money_performance_route():
            return smart_money_performance()

    extra_api.install = patched_install
    extra_api._opportunity_shadow_smart_money_runtime = True


install()
