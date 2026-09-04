"""Consolidated evidence view for NordicSignal Opportunity.

Measurement only. Combines absolute forward returns, benchmark excess return and
path-risk diagnostics into one summary without changing any signal rule.
"""
import opportunity_tracking_runtime as tracking
import opportunity_benchmark_evidence_runtime as benchmark

HORIZONS = tuple(benchmark.HORIZONS)


def _horizon_row(result, horizon):
    key = str(horizon)
    absolute = (result.get("horizons") or {}).get(key) or {}
    risk = ((result.get("risk_path") or {}).get("horizons") or {}).get(key) or {}
    edge = ((result.get("benchmark_edge") or {}).get("horizons") or {}).get(key) or {}
    status = edge.get("evidence_status") or absolute.get("sample_status") or "insufficient"
    return {
        "horizon_days": horizon,
        "n": absolute.get("n") or edge.get("n") or risk.get("n") or 0,
        "mean_return_pct": absolute.get("mean_return_pct"),
        "median_return_pct": absolute.get("median_return_pct"),
        "positive_rate_pct": absolute.get("positive_rate_pct"),
        "mean_excess_return_pct": edge.get("mean_excess_return_pct"),
        "median_excess_return_pct": edge.get("median_excess_return_pct"),
        "outperformance_rate_pct": edge.get("outperformance_rate_pct"),
        "median_max_drawdown_pct": risk.get("median_max_drawdown_pct"),
        "worst_max_drawdown_pct": risk.get("worst_max_drawdown_pct"),
        "median_max_runup_pct": risk.get("median_max_runup_pct"),
        "best_max_runup_pct": risk.get("best_max_runup_pct"),
        "evidence_status": status,
    }


def opportunity_performance(limit=100):
    result = benchmark.opportunity_performance(limit=limit)
    result["edge_summary"] = {
        "benchmark": ((result.get("benchmark_edge") or {}).get("benchmark") or "OSEBX"),
        "horizons": [_horizon_row(result, h) for h in HORIZONS],
        "interpretation": "Positive excess return means Opportunity outperformed the benchmark over the same trading-day horizon.",
        "policy": "Evidence is descriptive only; no automatic score or threshold tuning.",
    }
    return result


def install():
    tracking.opportunity_performance = opportunity_performance


install()
