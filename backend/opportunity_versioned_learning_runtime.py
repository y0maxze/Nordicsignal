"""Version-isolated forward validation for Early Opportunity.

A calibration sample must never silently mix events emitted by different signal
rules. This layer fingerprints the actual rule functions used by Opportunity,
Trend/Reversal and Insider Signal, stamps every new event with that model identity,
and rebuilds the Learning report from the *active model only*.

Events created before this runtime are deliberately marked legacy/unverified. They
remain available for audit, but are not assumed to belong to the active model even if
their human-readable version string happens to match.

This module changes measurement/readiness only. It never changes scores, thresholds,
event generation or push behavior.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import inspect
import json
from statistics import median

import insider_signal_v2_runtime as insider_signal
import opportunity_calibration_gate_runtime as calibration_gate
import opportunity_confluence_runtime as opportunity
import opportunity_independence_gate_runtime as independence_gate
import opportunity_market_regime_runtime as market_gate
import opportunity_performance_v2_runtime as performance_v2
import opportunity_tracking_runtime as tracking
import trend_reversal_runtime as reversal

MODEL_SCHEMA_VERSION = "opportunity-model-v1"
LEARNING_POLICY_VERSION = "learning-policy-v4-version-isolated"
HORIZONS = tuple(performance_v2.HORIZONS)
REQUIRED_HORIZONS = tuple(performance_v2.CALIBRATION_HORIZONS)
MIN_SAMPLE = int(performance_v2.MIN_CALIBRATION_SAMPLE)

_BASE_REPORT = tracking.opportunity_performance
_BASE_RECORD = tracking.record_opportunity


def _now():
    return tracking._now()


def _source_text(obj):
    try:
        return inspect.getsource(obj)
    except Exception:
        return repr(obj)


def _fingerprint(parts):
    payload = "\n---\n".join(str(part or "") for part in parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _current_identity():
    signal_fingerprint = _fingerprint([
        MODEL_SCHEMA_VERSION,
        getattr(opportunity, "VERSION", "unknown"),
        _source_text(opportunity.calculate_opportunity),
        _source_text(reversal.calculate_reversal),
        _source_text(insider_signal.analyze),
    ])
    policy_fingerprint = _fingerprint([
        LEARNING_POLICY_VERSION,
        _source_text(performance_v2._stats),
        _source_text(calibration_gate._quality_gate),
        _source_text(independence_gate._independence_stats),
        _source_text(market_gate._regime_stats),
        _source_text(market_gate._alpha_stats),
    ])
    signal_version = str(getattr(opportunity, "VERSION", "unknown"))
    return {
        "schema_version": MODEL_SCHEMA_VERSION,
        "signal_version": signal_version,
        "signal_fingerprint": signal_fingerprint,
        "signal_model_id": f"{signal_version}:{signal_fingerprint}",
        "learning_policy_version": LEARNING_POLICY_VERSION,
        "learning_policy_fingerprint": policy_fingerprint,
        "learning_policy_id": f"{LEARNING_POLICY_VERSION}:{policy_fingerprint}",
    }


def _ensure_schema():
    conn = tracking.connect()
    try:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS opportunity_event_versions (
          event_id BIGINT PRIMARY KEY,
          signal_version TEXT NOT NULL,
          signal_fingerprint TEXT NOT NULL,
          signal_model_id TEXT NOT NULL,
          recorded_learning_policy_id TEXT NOT NULL,
          source TEXT NOT NULL,
          captured_at TEXT NOT NULL
        );
        """)
        conn.commit()
    finally:
        conn.close()


def _latest_event(ticker):
    conn = tracking.connect()
    try:
        row = conn.execute(
            "SELECT * FROM opportunity_events WHERE ticker=? ORDER BY id DESC LIMIT 1",
            (str(ticker or "").upper().replace(".OL", ""),),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def _persist_version(event_id, signal_version, fingerprint, model_id, policy_id, source):
    conn = tracking.connect()
    try:
        cur = conn.execute(
            "INSERT INTO opportunity_event_versions(event_id,signal_version,signal_fingerprint,signal_model_id,recorded_learning_policy_id,source,captured_at) "
            "VALUES(?,?,?,?,?,?,?) ON CONFLICT(event_id) DO NOTHING",
            (event_id, signal_version, fingerprint, model_id, policy_id, source, _now()),
        )
        conn.commit()
        return bool(getattr(cur, "rowcount", 0))
    finally:
        conn.close()


def _payload_signal_version(event):
    try:
        payload = json.loads((event or {}).get("payload") or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        return "unknown"
    value = ((payload.get("opportunity") or {}).get("version") or payload.get("opportunity_version") or "unknown")
    return str(value)


def _stamp_live_event(event, identity=None):
    if not event:
        return False
    identity = identity or _current_identity()
    return _persist_version(
        int(event["id"]),
        identity["signal_version"],
        identity["signal_fingerprint"],
        identity["signal_model_id"],
        identity["learning_policy_id"],
        "live_verified_fingerprint",
    )


def _backfill_legacy_versions(identity=None):
    """Preserve old events for audit without pretending their code fingerprint is known."""
    identity = identity or _current_identity()
    conn = tracking.connect()
    try:
        events = [dict(row) for row in conn.execute(
            "SELECT e.* FROM opportunity_events e LEFT JOIN opportunity_event_versions v ON v.event_id=e.id "
            "WHERE v.event_id IS NULL ORDER BY e.id"
        ).fetchall()]
    finally:
        conn.close()
    count = 0
    for event in events:
        version = _payload_signal_version(event)
        fingerprint = "legacy-unverified"
        model_id = f"legacy:{version}"
        try:
            if _persist_version(
                int(event["id"]), version, fingerprint, model_id,
                identity["learning_policy_id"], "pre_versioning_unverified",
            ):
                count += 1
        except Exception:
            pass
    return count


def _record_versioned(result, name=None):
    outcome = _BASE_RECORD(result, name)
    if not outcome.get("emitted"):
        return outcome
    ticker = str((result or {}).get("ticker") or "").upper().replace(".OL", "")
    try:
        _stamp_live_event(_latest_event(ticker))
    except Exception:
        pass
    return outcome


def _version_counts():
    conn = tracking.connect()
    try:
        rows = conn.execute(
            "SELECT signal_model_id,signal_version,signal_fingerprint,source,COUNT(*) AS n,MIN(e.observed_at) AS first_observed_at,MAX(e.observed_at) AS last_observed_at "
            "FROM opportunity_event_versions v JOIN opportunity_events e ON e.id=v.event_id "
            "GROUP BY signal_model_id,signal_version,signal_fingerprint,source ORDER BY MAX(e.observed_at) DESC"
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def _scoped_rows(model_id, limit=100):
    conn = tracking.connect()
    try:
        events = [dict(row) for row in conn.execute(
            "SELECT e.* FROM opportunity_events e JOIN opportunity_event_versions v ON v.event_id=e.id "
            "WHERE v.signal_model_id=? ORDER BY e.created_at DESC,e.id DESC LIMIT ?",
            (model_id, max(1, min(int(limit or 100), 500))),
        ).fetchall()]
        total_row = conn.execute(
            "SELECT COUNT(*) AS n FROM opportunity_events e JOIN opportunity_event_versions v ON v.event_id=e.id WHERE v.signal_model_id=?",
            (model_id,),
        ).fetchone()
        total_events = int(total_row["n"] if total_row else 0)
        rows = [dict(row) for row in conn.execute(
            "SELECT r.event_id,r.horizon_days,r.return_pct,e.label,e.ticker,COALESCE(NULLIF(s.sector,''),'Unknown') AS sector,"
            "c.regime,m.benchmark_return_pct,m.excess_return_pct "
            "FROM opportunity_forward_returns r "
            "JOIN opportunity_events e ON e.id=r.event_id "
            "JOIN opportunity_event_versions v ON v.event_id=e.id "
            "LEFT JOIN stocks s ON s.ticker=e.ticker "
            "LEFT JOIN opportunity_market_context c ON c.event_id=e.id "
            "LEFT JOIN opportunity_market_returns m ON m.event_id=e.id AND m.horizon_days=r.horizon_days "
            "WHERE v.signal_model_id=? AND r.return_pct IS NOT NULL ORDER BY e.created_at DESC,r.horizon_days",
            (model_id,),
        ).fetchall()]
        return total_events, events, rows
    finally:
        conn.close()


def _scoped_base_report(total_events, events, rows):
    overall = {horizon: [] for horizon in HORIZONS}
    by_label_values = {}
    label_event_counts = Counter(str(event.get("label") or "") for event in events)

    # events may be limited for display, so query counts from settled rows is not enough.
    # The caller patches exact label event counts separately when available.
    for row in rows:
        try:
            horizon = int(row.get("horizon_days") or 0)
            value = float(row["return_pct"])
        except (TypeError, ValueError, KeyError):
            continue
        if horizon not in overall:
            continue
        overall[horizon].append(value)
        label = str(row.get("label") or "")
        by_label_values.setdefault(label, {item: [] for item in HORIZONS})[horizon].append(value)

    horizon_summary = {
        str(horizon): performance_v2._stats(overall[horizon], total_events)
        for horizon in HORIZONS
    }

    labels = sorted(set(tracking.TRACKED_LABELS) | set(by_label_values))
    label_summary = {}
    for label in labels:
        values = by_label_values.get(label, {item: [] for item in HORIZONS})
        event_count = int(label_event_counts.get(label, 0))
        horizons = {
            str(horizon): performance_v2._stats(values[horizon], event_count)
            for horizon in HORIZONS
        }
        label_summary[label] = {
            "events": event_count,
            "horizons": horizons,
            "calibration_ready": all(
                horizons[str(horizon)]["n"] >= MIN_SAMPLE for horizon in REQUIRED_HORIZONS
            ),
        }

    raw_ready = all(horizon_summary[str(horizon)]["n"] >= MIN_SAMPLE for horizon in REQUIRED_HORIZONS)
    return {
        "events": total_events,
        "horizons": horizon_summary,
        "by_label": label_summary,
        "calibration": {
            "ready": raw_ready,
            "minimum_sample_size": MIN_SAMPLE,
            "required_horizons": list(REQUIRED_HORIZONS),
            "rule": "Active signal model only: do not tune until the version-scoped sample is sufficient.",
        },
        "recent_events": events[:20],
        "updated_at": _now(),
    }


def _exact_label_counts(model_id):
    conn = tracking.connect()
    try:
        return {
            str(row["label"]): int(row["n"])
            for row in conn.execute(
                "SELECT e.label,COUNT(*) AS n FROM opportunity_events e JOIN opportunity_event_versions v ON v.event_id=e.id "
                "WHERE v.signal_model_id=? GROUP BY e.label",
                (model_id,),
            ).fetchall()
        }
    finally:
        conn.close()


def _apply_exact_label_counts(report, model_id, rows):
    counts = _exact_label_counts(model_id)
    grouped = {}
    for row in rows:
        try:
            horizon = int(row.get("horizon_days") or 0)
            value = float(row["return_pct"])
        except (TypeError, ValueError, KeyError):
            continue
        label = str(row.get("label") or "")
        grouped.setdefault(label, {h: [] for h in HORIZONS})
        if horizon in HORIZONS:
            grouped[label][horizon].append(value)
    for label in sorted(set(tracking.TRACKED_LABELS) | set(counts) | set(grouped)):
        values = grouped.get(label, {h: [] for h in HORIZONS})
        event_count = counts.get(label, 0)
        horizons = {str(h): performance_v2._stats(values[h], event_count) for h in HORIZONS}
        report.setdefault("by_label", {})[label] = {
            "events": event_count,
            "horizons": horizons,
            "calibration_ready": all(horizons[str(h)]["n"] >= MIN_SAMPLE for h in REQUIRED_HORIZONS),
        }


def _apply_scoped_gates(report, rows):
    calibration = report["calibration"]
    raw_ready = bool(calibration.get("ready"))
    minimum_sample = int(calibration.get("minimum_sample_size") or MIN_SAMPLE)

    quality = calibration_gate._quality_gate(report)

    independence_horizons = {}
    regime_horizons = {}
    alpha_horizons = {}
    for horizon in REQUIRED_HORIZONS:
        subset = [row for row in rows if int(row.get("horizon_days") or 0) == horizon]
        independence_horizons[str(horizon)] = independence_gate._independence_stats(subset, minimum_sample)
        regime_horizons[str(horizon)] = market_gate._regime_stats(subset, minimum_sample)
        alpha_horizons[str(horizon)] = market_gate._alpha_stats(subset)

    independence_ready = all(independence_horizons[str(h)]["status"] == "PASS" for h in REQUIRED_HORIZONS)
    regime_ready = all(regime_horizons[str(h)]["status"] == "PASS" for h in REQUIRED_HORIZONS)
    positive_alpha_horizons = [
        h for h in REQUIRED_HORIZONS
        if alpha_horizons[str(h)].get("median_excess_return_pct") is not None
        and float(alpha_horizons[str(h)]["median_excess_return_pct"]) > 0
    ]
    alpha_consistent = len(positive_alpha_horizons) >= market_gate.MIN_POSITIVE_ALPHA_HORIZONS

    report["independence_gate"] = {
        "status": "PASS" if independence_ready else ("REVIEW" if raw_ready else "COLLECTING_DATA"),
        "ready": independence_ready,
        "horizons": independence_horizons,
        "criteria": {
            "required_horizons": list(REQUIRED_HORIZONS),
            "minimum_unique_tickers": independence_gate.MIN_UNIQUE_TICKERS,
            "minimum_unique_sectors": independence_gate.MIN_UNIQUE_SECTORS,
            "maximum_single_ticker_share_pct": independence_gate.MAX_TICKER_SHARE_PCT,
            "maximum_single_sector_share_pct": independence_gate.MAX_SECTOR_SHARE_PCT,
            "unknown_or_discovery_sector_policy": "counted_as_one_conservative_sector_bucket",
        },
        "meaning": "Version-scoped sample must be distributed across stocks and sectors.",
        "automatic_threshold_changes": False,
    }

    report["market_regime_gate"] = {
        "status": "PASS" if regime_ready else ("REVIEW" if raw_ready else "COLLECTING_DATA"),
        "ready": regime_ready,
        "benchmark": market_gate.BENCHMARK_ID,
        "horizons": regime_horizons,
        "criteria": {
            "required_horizons": list(REQUIRED_HORIZONS),
            "minimum_supported_regimes": market_gate.MIN_SUPPORTED_REGIMES,
            "minimum_observations_per_supported_regime": market_gate.MIN_EVENTS_PER_REGIME,
            "maximum_single_regime_share_pct": market_gate.MAX_SINGLE_REGIME_SHARE_PCT,
            "lookahead_policy": "regime uses benchmark trading data strictly before the event market date",
        },
        "meaning": "Version-scoped sample must span sufficiently different Oslo market regimes.",
        "automatic_threshold_changes": False,
    }
    report["market_adjusted"] = {
        "benchmark": market_gate.BENCHMARK_ID,
        "method": "stock_forward_return_minus_OSEBX_close_to_close_return",
        "horizons": alpha_horizons,
        "positive_median_excess_horizons": positive_alpha_horizons,
        "positive_median_excess_consistent": alpha_consistent,
        "minimum_positive_horizons": market_gate.MIN_POSITIVE_ALPHA_HORIZONS,
        "meaning": "Positive excess return means the active Opportunity model outperformed OSEBX over the same evaluation window.",
    }

    checks = quality.setdefault("checks", {})
    checks["sample_independence"] = independence_ready
    checks["market_regime_diversity"] = regime_ready
    checks["positive_market_adjusted_median"] = alpha_consistent
    quality["positive_alpha_horizons"] = positive_alpha_horizons
    final_ready = raw_ready and independence_ready and regime_ready
    quality["ready_for_human_review"] = final_ready
    if quality.get("status") == "PASS_CANDIDATE" and not (independence_ready and regime_ready and alpha_consistent):
        quality["status"] = "REVIEW" if raw_ready else "COLLECTING_DATA"
        quality["quality_pass_candidate"] = False
    elif quality.get("status") == "COLLECTING_DATA" and raw_ready and not final_ready:
        quality["status"] = "REVIEW"
        quality["quality_pass_candidate"] = False
    quality["meaning"] = {
        "COLLECTING_DATA": "The active model version does not yet have enough settled forward observations.",
        "REVIEW": "The active model has enough raw observations, but one or more quality/independence/regime checks still fail.",
        "PASS_CANDIDATE": "The active model version passes the current evidence gates for human calibration review; no thresholds change automatically.",
    }.get(quality.get("status"), "Version-scoped validation is active.")
    report["quality_gate"] = quality

    calibration["raw_sample_ready"] = raw_ready
    calibration["independence_ready"] = independence_ready
    calibration["market_regime_ready"] = regime_ready
    calibration["ready"] = final_ready
    calibration["rule"] = (
        "Only the active verified signal-model fingerprint counts toward calibration. "
        "Its 5d/10d/20d sample, ticker/sector independence and market-regime diversity must all pass."
    )


def _build_active_report(model_id, limit=100):
    total_events, events, rows = _scoped_rows(model_id, limit)
    report = _scoped_base_report(total_events, events, rows)
    _apply_exact_label_counts(report, model_id, rows)
    _apply_scoped_gates(report, rows)
    return report


def opportunity_performance(limit=100):
    identity = _current_identity()
    try:
        _backfill_legacy_versions(identity)
    except Exception:
        pass

    aggregate = _BASE_REPORT(limit)
    active = _build_active_report(identity["signal_model_id"], limit)
    versions = _version_counts()

    aggregate_summary = {
        "events": int(aggregate.get("events") or 0),
        "horizon_observations": {
            str(h): int(((aggregate.get("horizons") or {}).get(str(h)) or {}).get("n") or 0)
            for h in HORIZONS
        },
    }

    # Replace all calibration-facing fields with the active model's isolated sample.
    for key in (
        "events", "horizons", "by_label", "calibration", "recent_events",
        "quality_gate", "independence_gate", "market_regime_gate", "market_adjusted",
    ):
        aggregate[key] = active[key]

    active_count = int(active.get("events") or 0)
    legacy_count = sum(int(row.get("n") or 0) for row in versions if str(row.get("signal_model_id") or "").startswith("legacy:"))
    aggregate["versioning"] = {
        "status": "ACTIVE_MODEL_ISOLATED",
        "active_model": identity,
        "active_model_events": active_count,
        "legacy_unverified_events": legacy_count,
        "models": versions,
        "calibration_scope": "active_verified_signal_model_only",
        "legacy_policy": "pre-versioning events remain auditable but never count toward the active calibration sample",
        "automatic_threshold_changes": False,
    }
    aggregate["aggregate_all_versions"] = aggregate_summary
    aggregate["updated_at"] = _now()
    aggregate["policy"] = "version_isolated_measurement_only_manual_calibration_review"
    return aggregate


def install():
    _ensure_schema()
    try:
        _backfill_legacy_versions()
    except Exception:
        pass
    tracking.record_opportunity = _record_versioned
    tracking.opportunity_performance = opportunity_performance


install()
