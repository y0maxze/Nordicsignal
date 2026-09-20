"""Point-in-time Smart Capital research.

Research/measurement only. This module cannot change production scores, signals,
thresholds, alerts, High Conviction, Opportunity, or position sizing.
"""
from __future__ import annotations
from math import sqrt
from statistics import fmean, median

HORIZONS = (5, 20, 60)
MIN_SAMPLE = 20


def _values(samples, horizon, field):
    key = str(horizon)
    out = []
    for sample in samples or []:
        value = (sample.get(field) or {}).get(key)
        if isinstance(value, (int, float)):
            out.append(float(value))
    return out


def _mean_ci95(values):
    values = list(values)
    n = len(values)
    if n < 2:
        return None
    avg = fmean(values)
    variance = sum((v - avg) ** 2 for v in values) / (n - 1)
    margin = 1.96 * sqrt(variance / n)
    return [round(avg - margin, 3), round(avg + margin, 3)]


def summarize(samples):
    samples = list(samples or [])
    horizons = {}
    for horizon in HORIZONS:
        excess = _values(samples, horizon, "excess_return_pct")
        raw = _values(samples, horizon, "forward_return_pct")
        horizons[str(horizon)] = {
            "n": len(excess),
            "mean_excess_return_pct": round(fmean(excess), 3) if excess else None,
            "median_excess_return_pct": round(median(excess), 3) if excess else None,
            "excess_hit_rate_pct": round(sum(v > 0 for v in excess) / len(excess) * 100, 1) if excess else None,
            "mean_excess_ci95_pct": _mean_ci95(excess),
            "mean_return_pct": round(fmean(raw), 3) if raw else None,
            "evidence_status": "insufficient" if len(excess) < MIN_SAMPLE else "research_ready",
        }
    drawdowns = [float(x["max_drawdown_pct"]) for x in samples if isinstance(x.get("max_drawdown_pct"), (int, float))]
    return {
        "model": "smart_capital_research_v1",
        "sample_count": len(samples),
        "benchmark": "OSEBX",
        "horizons": horizons,
        "median_max_drawdown_pct": round(median(drawdowns), 3) if drawdowns else None,
        "policy": "Research only. No production score, signal, threshold, alert or sizing effect.",
        "limitations": [
            "Confidence intervals are descriptive normal-approximation intervals, not proof of predictive edge.",
            "Historical performance does not imply future performance.",
            "Transaction costs, slippage and tax are excluded.",
            "Point-in-time publication availability must be preserved for every included event.",
        ],
    }


def holdout_split(samples, fraction=0.25):
    """Deterministic chronological holdout; never shuffle future observations backward."""
    ordered = sorted(list(samples or []), key=lambda x: (str(x.get("published_at") or ""), str(x.get("event_id") or "")))
    if len(ordered) < 4:
        return ordered, []
    cut = max(1, min(len(ordered) - 1, int(len(ordered) * (1.0 - fraction))))
    return ordered[:cut], ordered[cut:]
