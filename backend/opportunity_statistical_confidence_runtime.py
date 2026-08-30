"""Distribution-light statistical confidence diagnostics for Opportunity Learning.

This module contains pure measurement helpers only. It does not install routes,
change signal thresholds, emit events or modify scores. The version-isolated
Learning runtime consumes these helpers as an additional human-review gate.
"""
from __future__ import annotations

from math import comb, sqrt
from statistics import median

CONFIDENCE_LEVEL = 0.95
Z_95 = 1.959963984540054
MIN_REQUIRED_HORIZONS = 2
NULL_POSITIVE_RATE_PCT = 50.0


def _wilson_interval(successes, n, z=Z_95):
    n = int(n or 0)
    successes = max(0, min(int(successes or 0), n))
    if n <= 0:
        return {"n": 0, "successes": 0, "rate_pct": None, "lower_pct": None, "upper_pct": None}
    p = successes / n
    z2 = z * z
    denom = 1.0 + z2 / n
    center = (p + z2 / (2.0 * n)) / denom
    margin = (z / denom) * sqrt((p * (1.0 - p) / n) + z2 / (4.0 * n * n))
    return {
        "n": n,
        "successes": successes,
        "rate_pct": round(p * 100.0, 2),
        "lower_pct": round(max(0.0, center - margin) * 100.0, 2),
        "upper_pct": round(min(1.0, center + margin) * 100.0, 2),
    }


def _median_interval(values, confidence=CONFIDENCE_LEVEL):
    sample = sorted(float(value) for value in values if value is not None)
    n = len(sample)
    if not n:
        return {"n": 0, "median": None, "lower": None, "upper": None, "coverage": None, "order_k": None}

    tail_limit = max(0.0, min(0.5, (1.0 - float(confidence)) / 2.0))
    denominator = float(2 ** n)
    best_k = 1
    best_tail = 1.0 / denominator
    cumulative = 0.0
    for k in range(1, (n // 2) + 1):
        cumulative += comb(n, k - 1) / denominator
        if cumulative <= tail_limit:
            best_k = k
            best_tail = cumulative
        else:
            break

    lower = sample[best_k - 1]
    upper = sample[n - best_k]
    actual_coverage = max(0.0, min(1.0, 1.0 - 2.0 * best_tail))
    return {
        "n": n,
        "median": round(float(median(sample)), 4),
        "lower": round(float(lower), 4),
        "upper": round(float(upper), 4),
        "coverage": round(actual_coverage, 6),
        "order_k": best_k,
    }


def _series_confidence(values, minimum_sample):
    sample = [float(value) for value in values if value is not None]
    positive = sum(value > 0.0 for value in sample)
    wilson = _wilson_interval(positive, len(sample))
    med = _median_interval(sample)
    enough = len(sample) >= int(minimum_sample or 0)
    direction_supported = (
        enough
        and wilson["lower_pct"] is not None
        and float(wilson["lower_pct"]) > NULL_POSITIVE_RATE_PCT
        and med["lower"] is not None
        and float(med["lower"]) > 0.0
    )
    return {
        "n": len(sample),
        "minimum_sample": int(minimum_sample or 0),
        "positive_rate_wilson_95": wilson,
        "median_ci_95": med,
        "direction_supported": direction_supported,
    }


def confidence_gate(rows, required_horizons, minimum_sample):
    horizons = {}
    passing = []
    for horizon in [int(value) for value in required_horizons]:
        subset = [row for row in rows or [] if int((row or {}).get("horizon_days") or 0) == horizon]
        raw_values = [row.get("return_pct") for row in subset if row.get("return_pct") is not None]
        alpha_values = [row.get("excess_return_pct") for row in subset if row.get("excess_return_pct") is not None]
        raw = _series_confidence(raw_values, minimum_sample)
        alpha = _series_confidence(alpha_values, minimum_sample)
        passed = bool(raw["direction_supported"] and alpha["direction_supported"])
        if passed:
            passing.append(horizon)
        horizons[str(horizon)] = {
            "status": "PASS" if passed else ("REVIEW" if len(raw_values) >= int(minimum_sample or 0) else "COLLECTING_DATA"),
            "raw_return": raw,
            "market_adjusted_alpha": alpha,
        }

    ready = len(passing) >= MIN_REQUIRED_HORIZONS
    any_sample_ready = any(
        int((item.get("raw_return") or {}).get("n") or 0) >= int(minimum_sample or 0)
        for item in horizons.values()
    )
    return {
        "status": "PASS" if ready else ("REVIEW" if any_sample_ready else "COLLECTING_DATA"),
        "ready": ready,
        "confidence_level": CONFIDENCE_LEVEL,
        "required_horizons": [int(value) for value in required_horizons],
        "minimum_passing_horizons": MIN_REQUIRED_HORIZONS,
        "passing_horizons": passing,
        "horizons": horizons,
        "criteria": {
            "minimum_sample_per_series": int(minimum_sample or 0),
            "wilson_lower_positive_rate_must_exceed_pct": NULL_POSITIVE_RATE_PCT,
            "median_ci_lower_bound_must_exceed_pct": 0.0,
            "raw_and_OSEBX_adjusted_must_both_pass": True,
        },
        "meaning": (
            "At least two required horizons have 95% directional support in both raw return and OSEBX-adjusted alpha."
            if ready else
            "Observed returns remain statistically uncertain; no threshold review should rely on them yet."
        ),
        "automatic_threshold_changes": False,
    }
