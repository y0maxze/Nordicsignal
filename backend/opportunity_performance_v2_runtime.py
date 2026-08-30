"""Richer forward-performance measurement for Early Opportunity.

This module deliberately changes measurement only. It does not change Opportunity
thresholds or the aggregate 0-100 stock score. It extends the existing tracker with
a 1-trading-day horizon and replaces the performance report with robust summary
statistics and per-label sample diagnostics.
"""

from statistics import median

import opportunity_tracking_runtime as tracking

HORIZONS = (1, 5, 10, 20, 60)
MIN_CALIBRATION_SAMPLE = 20
CALIBRATION_HORIZONS = (5, 10, 20)


def _stats(values, event_count):
    values = [float(value) for value in values if value is not None]
    n = len(values)
    return {
        "n": n,
        "event_count": int(event_count or 0),
        "settled_event_pct": round(n / event_count * 100.0, 2) if event_count else 0.0,
        "mean_return_pct": round(sum(values) / n, 3) if n else None,
        "median_return_pct": round(float(median(values)), 3) if n else None,
        "positive_rate_pct": round(sum(value > 0 for value in values) / n * 100.0, 2) if n else None,
        "sample_status": "usable" if n >= MIN_CALIBRATION_SAMPLE else "insufficient",
        "minimum_sample_size": MIN_CALIBRATION_SAMPLE,
    }


def opportunity_performance(limit=100):
    limit = max(1, min(int(limit or 100), 500))
    conn = tracking.connect()
    try:
        total_row = conn.execute("SELECT COUNT(*) AS n FROM opportunity_events").fetchone()
        total_events = int(total_row["n"] if total_row else 0)
        events = [dict(row) for row in conn.execute(
            "SELECT * FROM opportunity_events ORDER BY created_at DESC,id DESC LIMIT ?", (limit,)
        ).fetchall()]
        label_counts = {
            str(row["label"]): int(row["n"])
            for row in conn.execute(
                "SELECT label,COUNT(*) AS n FROM opportunity_events GROUP BY label"
            ).fetchall()
        }
        returns = [dict(row) for row in conn.execute(
            "SELECT r.*,e.label FROM opportunity_forward_returns r "
            "JOIN opportunity_events e ON e.id=r.event_id "
            "ORDER BY e.created_at DESC,r.horizon_days"
        ).fetchall()]
    finally:
        conn.close()

    overall = {horizon: [] for horizon in HORIZONS}
    by_label = {
        label: {horizon: [] for horizon in HORIZONS}
        for label in sorted(tracking.TRACKED_LABELS)
    }

    for row in returns:
        try:
            horizon = int(row.get("horizon_days") or 0)
            value = float(row["return_pct"])
        except (TypeError, ValueError, KeyError):
            continue
        if horizon not in overall:
            continue
        overall[horizon].append(value)
        label = str(row.get("label") or "")
        if label not in by_label:
            by_label[label] = {item: [] for item in HORIZONS}
        by_label[label][horizon].append(value)

    horizon_summary = {
        str(horizon): _stats(overall[horizon], total_events)
        for horizon in HORIZONS
    }

    label_summary = {}
    for label, grouped in by_label.items():
        event_count = label_counts.get(label, 0)
        horizons = {
            str(horizon): _stats(grouped[horizon], event_count)
            for horizon in HORIZONS
        }
        label_summary[label] = {
            "events": event_count,
            "horizons": horizons,
            "calibration_ready": all(
                horizons[str(horizon)]["n"] >= MIN_CALIBRATION_SAMPLE
                for horizon in CALIBRATION_HORIZONS
            ),
        }

    calibration_ready = all(
        horizon_summary[str(horizon)]["n"] >= MIN_CALIBRATION_SAMPLE
        for horizon in CALIBRATION_HORIZONS
    )

    return {
        "events": total_events,
        "horizons": horizon_summary,
        "by_label": label_summary,
        "calibration": {
            "ready": calibration_ready,
            "minimum_sample_size": MIN_CALIBRATION_SAMPLE,
            "required_horizons": list(CALIBRATION_HORIZONS),
            "rule": "Do not tune Opportunity thresholds from live forward returns until the minimum settled sample is reached.",
        },
        "recent_events": events[:20],
        "updated_at": tracking._now(),
        "policy": "informational_only_pending_forward_validation",
    }


def install():
    # Existing tracker functions resolve HORIZONS dynamically, so this also makes
    # settle_forward_returns backfill 1-day observations for historical events.
    tracking.HORIZONS = HORIZONS
    tracking.opportunity_performance = opportunity_performance


install()
