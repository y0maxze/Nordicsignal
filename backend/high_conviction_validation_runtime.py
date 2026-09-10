"""Pre-registered, research-only High Conviction validation framework.

The rules below are fixed before outcome review. Matching daily observations are
collapsed into independent candidate episodes by ticker/hypothesis; only the first
snapshot in each contiguous episode is used for inference. This module never emits
a tradable signal and cannot alter live scores or thresholds.
"""
from __future__ import annotations

from datetime import date
from statistics import mean, median

import extra_api
from database import connect

MODEL_VERSION = "high_conviction_validation_v1"
HORIZON_DAYS = 20
MIN_EPISODES = 50
MIN_TICKERS = 8
MIN_REGIMES = 3
MAX_CONTIGUOUS_GAP_DAYS = 4

QUALIFYING_OPPORTUNITY = {"WATCH_CONFLUENCE", "EARLY_OPPORTUNITY", "EARLY_OPPORTUNITY_HIGH"}
POSITIVE_TREND = {"REVERSAL_CANDIDATE", "EARLY_REVERSAL", "CONFIRMED_UPTREND"}
VOLUME_CONFIRMATION = {"CONFIRMED", "STRONG"}

HYPOTHESES = (
    {
        "id": "hc_core_v1",
        "description": "Existing qualifying Opportunity state + positive reversal regime + no critical verified event risk.",
        "criteria": {
            "opportunity_label": sorted(QUALIFYING_OPPORTUNITY),
            "reversal_regime": sorted(POSITIVE_TREND),
            "critical_event_count": 0,
        },
    },
    {
        "id": "hc_confluence_v1",
        "description": "Core setup + at least two independent insider buyers + bullish volume confirmation.",
        "criteria": {
            "inherits": "hc_core_v1",
            "independent_buyers_min": 2,
            "volume_confirmation": sorted(VOLUME_CONFIRMATION),
        },
    },
)


def _matches(snapshot, hypothesis_id):
    if str(snapshot.get("opportunity_label") or "") not in QUALIFYING_OPPORTUNITY:
        return False
    if str(snapshot.get("reversal_regime") or "") not in POSITIVE_TREND:
        return False
    if int(snapshot.get("critical_event_count") or 0) != 0:
        return False
    if hypothesis_id == "hc_confluence_v1":
        if int(snapshot.get("independent_buyers") or 0) < 2:
            return False
        if str(snapshot.get("volume_confirmation") or "") not in VOLUME_CONFIRMATION:
            return False
    return hypothesis_id == "hc_core_v1" or hypothesis_id == "hc_confluence_v1"


def _day_gap(previous, current):
    try:
        return (date.fromisoformat(current) - date.fromisoformat(previous)).days
    except Exception:
        return MAX_CONTIGUOUS_GAP_DAYS + 1


def _episodes(rows, hypothesis_id):
    """Collapse contiguous matching daily snapshots into one episode.

    A non-match ends an episode. Weekend/holiday gaps up to four calendar days stay
    in the same episode. The first matching snapshot is the episode observation.
    """
    episodes = []
    active = {}
    for row in sorted((dict(x) for x in rows), key=lambda x: (str(x.get("ticker") or ""), str(x.get("market_date") or ""), int(x.get("id") or 0))):
        ticker = str(row.get("ticker") or "")
        match = _matches(row, hypothesis_id)
        state = active.get(ticker)
        if not match:
            active.pop(ticker, None)
            continue
        market_date = str(row.get("market_date") or "")
        if state and _day_gap(state["last_date"], market_date) <= MAX_CONTIGUOUS_GAP_DAYS:
            state["last_date"] = market_date
            state["snapshot_ids"].append(int(row["id"]))
            continue
        episode = {
            "ticker": ticker,
            "hypothesis_id": hypothesis_id,
            "first_snapshot_id": int(row["id"]),
            "first_market_date": market_date,
            "last_date": market_date,
            "snapshot_ids": [int(row["id"])],
            "market_regime": row.get("market_regime"),
        }
        episodes.append(episode)
        active[ticker] = episode
    return episodes


def _stats(values):
    vals = [float(v) for v in values if v is not None]
    return {
        "n": len(vals),
        "mean": round(mean(vals), 3) if vals else None,
        "median": round(median(vals), 3) if vals else None,
        "positive_rate_pct": round(sum(v > 0 for v in vals) / len(vals) * 100.0, 2) if vals else None,
    }


def validation_report(hypothesis_id="hc_core_v1"):
    valid_ids = {x["id"] for x in HYPOTHESES}
    if hypothesis_id not in valid_ids:
        return {"status": "invalid_hypothesis", "hypothesis_id": hypothesis_id, "available": sorted(valid_ids)}

    conn = connect()
    try:
        rows = conn.execute(
            "SELECT id,ticker,market_date,opportunity_label,reversal_regime,critical_event_count,"
            "independent_buyers,volume_confirmation,market_regime FROM high_conviction_shadow_snapshots "
            "WHERE model_version='high_conviction_shadow_dataset_v2' ORDER BY ticker,market_date,id"
        ).fetchall()
        outcomes = conn.execute(
            "SELECT snapshot_id,excess_return_pct,max_drawdown_pct,max_runup_pct FROM high_conviction_shadow_outcomes "
            "WHERE horizon_days=?",
            (HORIZON_DAYS,),
        ).fetchall()
    finally:
        conn.close()

    outcome_map = {int(x["snapshot_id"]): dict(x) for x in outcomes}
    episodes = _episodes(rows, hypothesis_id)
    matured = []
    for episode in episodes:
        outcome = outcome_map.get(episode["first_snapshot_id"])
        if outcome and outcome.get("excess_return_pct") is not None:
            matured.append((episode, outcome))

    tickers = {ep["ticker"] for ep, _ in matured}
    regimes = {str(ep.get("market_regime")) for ep, _ in matured if ep.get("market_regime")}
    excess = _stats([out["excess_return_pct"] for _, out in matured])
    drawdown = _stats([out["max_drawdown_pct"] for _, out in matured])
    runup = _stats([out["max_runup_pct"] for _, out in matured])

    checks = {
        "min_independent_episodes": len(matured) >= MIN_EPISODES,
        "min_distinct_tickers": len(tickers) >= MIN_TICKERS,
        "min_market_regimes": len(regimes) >= MIN_REGIMES,
        "positive_mean_excess": excess["mean"] is not None and excess["mean"] > 0,
        "positive_median_excess": excess["median"] is not None and excess["median"] > 0,
        "positive_excess_majority": excess["positive_rate_pct"] is not None and excess["positive_rate_pct"] > 50.0,
        "walk_forward_validation": False,
    }
    research_ready = all(v for k, v in checks.items() if k != "walk_forward_validation")

    return {
        "status": "ok",
        "model": MODEL_VERSION,
        "hypothesis_id": hypothesis_id,
        "pre_registered": True,
        "rule": next(x for x in HYPOTHESES if x["id"] == hypothesis_id),
        "horizon_days": HORIZON_DAYS,
        "daily_matching_snapshots": sum(1 for row in rows if _matches(dict(row), hypothesis_id)),
        "independent_episodes": len(episodes),
        "matured_independent_episodes": len(matured),
        "distinct_tickers": len(tickers),
        "market_regimes": sorted(regimes),
        "excess_return_pct": excess,
        "max_drawdown_pct": drawdown,
        "max_runup_pct": runup,
        "checks": checks,
        "research_ready_for_walk_forward": research_ready,
        "activation": {
            "enabled": False,
            "reason": "Hard-disabled. Passing descriptive gates is not sufficient; independent walk-forward validation is still required before any activation review.",
        },
        "policy": "Research only. Rules are frozen before outcome review; no automatic tuning, score changes, position sizing or buy/sell output.",
    }


def framework_status():
    return {
        "status": "ok",
        "model": MODEL_VERSION,
        "pre_registered": True,
        "hypotheses": list(HYPOTHESES),
        "episode_policy": {
            "unit": "first snapshot of each contiguous matching ticker/hypothesis episode",
            "non_match_ends_episode": True,
            "max_contiguous_calendar_gap_days": MAX_CONTIGUOUS_GAP_DAYS,
        },
        "fixed_research_gates": {
            "horizon_days": HORIZON_DAYS,
            "min_independent_episodes": MIN_EPISODES,
            "min_distinct_tickers": MIN_TICKERS,
            "min_market_regimes": MIN_REGIMES,
            "positive_mean_excess": True,
            "positive_median_excess": True,
            "positive_excess_rate_gt_pct": 50.0,
            "walk_forward_required": True,
        },
        "activation_enabled": False,
        "automatic_threshold_changes": False,
    }


def install():
    if getattr(extra_api, "_high_conviction_validation_runtime_v1", False):
        return
    original_install = extra_api.install

    def patched_install(app):
        original_install(app)

        @app.get("/api/high-conviction-validation")
        def high_conviction_validation_status():
            return framework_status()

        @app.get("/api/high-conviction-validation/{hypothesis_id}")
        def high_conviction_validation_report(hypothesis_id: str):
            return validation_report(hypothesis_id)

    extra_api.install = patched_install
    extra_api._high_conviction_validation_runtime_v1 = True


install()
