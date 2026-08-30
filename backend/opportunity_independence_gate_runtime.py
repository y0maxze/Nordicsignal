"""Independence diagnostics for Early Opportunity forward validation.

Raw Opportunity events are never discarded. This layer only prevents calibration
readiness from being overstated when the settled sample is concentrated in too few
stocks or sectors. It does not change signal thresholds or the aggregate stock score.
"""
from collections import Counter

import opportunity_tracking_runtime as tracking

REQUIRED_HORIZONS = (5, 10, 20)
MIN_UNIQUE_TICKERS = 8
MIN_UNIQUE_SECTORS = 4
MAX_TICKER_SHARE_PCT = 25.0
MAX_SECTOR_SHARE_PCT = 50.0

_BASE_REPORT = tracking.opportunity_performance


def _clean_sector(value):
    text = str(value or "").strip()
    return text if text else "Unknown"


def _independence_stats(rows, minimum_sample=20):
    rows = [dict(row) for row in (rows or [])]
    n = len(rows)
    ticker_counts = Counter(str(row.get("ticker") or "UNKNOWN").upper() for row in rows)
    sector_counts = Counter(_clean_sector(row.get("sector")) for row in rows)
    largest_ticker_count = max(ticker_counts.values(), default=0)
    largest_sector_count = max(sector_counts.values(), default=0)
    largest_ticker_share = (largest_ticker_count / n * 100.0) if n else 0.0
    largest_sector_share = (largest_sector_count / n * 100.0) if n else 0.0

    checks = {
        "minimum_sample": n >= int(minimum_sample),
        "unique_tickers": len(ticker_counts) >= MIN_UNIQUE_TICKERS,
        "unique_sectors": len(sector_counts) >= MIN_UNIQUE_SECTORS,
        "ticker_concentration": largest_ticker_share <= MAX_TICKER_SHARE_PCT if n else False,
        "sector_concentration": largest_sector_share <= MAX_SECTOR_SHARE_PCT if n else False,
    }
    if not checks["minimum_sample"]:
        status = "COLLECTING_DATA"
    elif all(checks.values()):
        status = "PASS"
    else:
        status = "REVIEW"

    return {
        "status": status,
        "observations": n,
        "unique_tickers": len(ticker_counts),
        "unique_sectors": len(sector_counts),
        "largest_ticker_share_pct": round(largest_ticker_share, 2),
        "largest_sector_share_pct": round(largest_sector_share, 2),
        "largest_ticker": ticker_counts.most_common(1)[0][0] if ticker_counts else None,
        "largest_sector": sector_counts.most_common(1)[0][0] if sector_counts else None,
        "checks": checks,
    }


def _settled_rows_by_horizon():
    conn = tracking.connect()
    try:
        rows = conn.execute(
            "SELECT r.horizon_days,e.ticker,COALESCE(NULLIF(s.sector,''),'Unknown') AS sector "
            "FROM opportunity_forward_returns r "
            "JOIN opportunity_events e ON e.id=r.event_id "
            "LEFT JOIN stocks s ON s.ticker=e.ticker "
            "WHERE r.horizon_days IN (5,10,20) AND r.return_pct IS NOT NULL"
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def opportunity_performance(limit=100):
    report = _BASE_REPORT(limit)
    calibration = report.setdefault("calibration", {})
    minimum_sample = int(calibration.get("minimum_sample_size") or 20)
    grouped = {horizon: [] for horizon in REQUIRED_HORIZONS}
    try:
        rows = _settled_rows_by_horizon()
    except Exception:
        rows = []
    for row in rows:
        try:
            horizon = int(row.get("horizon_days") or 0)
        except (TypeError, ValueError):
            continue
        if horizon in grouped:
            grouped[horizon].append(row)

    horizon_gate = {
        str(horizon): _independence_stats(grouped[horizon], minimum_sample)
        for horizon in REQUIRED_HORIZONS
    }
    independence_ready = all(
        horizon_gate[str(horizon)]["status"] == "PASS"
        for horizon in REQUIRED_HORIZONS
    )
    raw_sample_ready = bool(calibration.get("ready"))

    report["independence_gate"] = {
        "status": "PASS" if independence_ready else ("REVIEW" if raw_sample_ready else "COLLECTING_DATA"),
        "ready": independence_ready,
        "horizons": horizon_gate,
        "criteria": {
            "required_horizons": list(REQUIRED_HORIZONS),
            "minimum_unique_tickers": MIN_UNIQUE_TICKERS,
            "minimum_unique_sectors": MIN_UNIQUE_SECTORS,
            "maximum_single_ticker_share_pct": MAX_TICKER_SHARE_PCT,
            "maximum_single_sector_share_pct": MAX_SECTOR_SHARE_PCT,
            "unknown_or_discovery_sector_policy": "counted_as_one_conservative_sector_bucket",
        },
        "meaning": (
            "Settled observations are sufficiently distributed across stocks and sectors."
            if independence_ready
            else "Do not treat the sample as independent yet; ticker or sector concentration remains too high, or the sample is still too small."
        ),
        "automatic_threshold_changes": False,
    }

    calibration["raw_sample_ready"] = raw_sample_ready
    calibration["independence_ready"] = independence_ready
    calibration["ready"] = raw_sample_ready and independence_ready
    calibration["rule"] = (
        "Do not tune Opportunity thresholds until the settled sample minimum is reached "
        "and the sample-independence gate passes across 5d, 10d and 20d."
    )

    quality = report.get("quality_gate") or {}
    if quality:
        checks = quality.setdefault("checks", {})
        checks["sample_independence"] = independence_ready
        status = str(quality.get("status") or "COLLECTING_DATA")
        if status == "PASS_CANDIDATE" and not independence_ready:
            quality["status"] = "REVIEW" if raw_sample_ready else "COLLECTING_DATA"
            quality["quality_pass_candidate"] = False
            quality["meaning"] = (
                "Sample-size and directional checks may pass, but ticker/sector independence is not yet sufficient for calibration review."
            )
        elif status == "COLLECTING_DATA" and raw_sample_ready and not independence_ready:
            quality["status"] = "REVIEW"
            quality["quality_pass_candidate"] = False
        report["quality_gate"] = quality

    report["policy"] = "measurement_only_manual_calibration_review_with_independence_gate"
    return report


def install():
    tracking.opportunity_performance = opportunity_performance


install()
