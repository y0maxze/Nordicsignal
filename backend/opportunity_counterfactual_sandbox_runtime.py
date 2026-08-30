"""Pre-registered, research-only counterfactual sandbox for Opportunity thresholds.

The sandbox is hard-locked until the shadow dataset quality gate passes. Candidate
filters are fixed in source code, results are split chronologically into development
and later holdout periods, and no candidate is automatically ranked or promoted.
"""
from __future__ import annotations

from statistics import median

import extra_api
import opportunity_research_provenance_runtime as provenance
import opportunity_shadow_quality_runtime as quality
import opportunity_tracking_runtime as tracking
import opportunity_version_identity_runtime as identity_runtime

HORIZONS = (5, 10, 20)
HOLDOUT_SHARE = 0.30
MIN_HOLDOUT_OBSERVATIONS = 20

CANDIDATES = (
    {"id":"baseline_rev75_vol150","name":"Baseline confluence","description":"Reversal >= 75 and bullish volume >= 1.50x.","reversal_min":75.0,"volume_min":1.50,"insider_positive_required":False},
    {"id":"research_rev72_vol150","name":"Research: reversal 72","description":"Reversal >= 72 and bullish volume >= 1.50x.","reversal_min":72.0,"volume_min":1.50,"insider_positive_required":False},
    {"id":"research_rev75_vol135","name":"Research: volume 1.35x","description":"Reversal >= 75 and bullish volume >= 1.35x.","reversal_min":75.0,"volume_min":1.35,"insider_positive_required":False},
    {"id":"research_rev70_vol135_insider","name":"Research: insider-supported","description":"Reversal >= 70, volume >= 1.35x and POSITIVE/STRONG insider evidence.","reversal_min":70.0,"volume_min":1.35,"insider_positive_required":True},
)


def _number(value):
    try: return float(value) if value is not None else None
    except (TypeError, ValueError): return None


def _eligible(snapshot, candidate):
    reversal, volume = _number(snapshot.get("reversal_score")), _number(snapshot.get("volume_ratio"))
    if reversal is None or volume is None: return False
    if reversal < float(candidate["reversal_min"]) or volume < float(candidate["volume_min"]): return False
    if candidate.get("insider_positive_required"):
        return str(snapshot.get("insider_label") or "").upper() in {"POSITIVE", "STRONG"}
    return True


def _load_rows(model_id):
    conn = tracking.connect()
    try:
        snapshots = [dict(row) for row in conn.execute(
            "SELECT id,ticker,market_date,reversal_score,volume_ratio,insider_label FROM opportunity_shadow_snapshots WHERE signal_model_id=? ORDER BY market_date,id",
            (model_id,),
        ).fetchall()]
        returns = [dict(row) for row in conn.execute(
            "SELECT r.snapshot_id,r.horizon_days,r.return_pct,r.excess_return_pct FROM opportunity_shadow_returns r JOIN opportunity_shadow_snapshots s ON s.id=r.snapshot_id WHERE s.signal_model_id=? AND r.horizon_days IN (5,10,20) AND r.return_pct IS NOT NULL AND r.excess_return_pct IS NOT NULL",
            (model_id,),
        ).fetchall()]
        return snapshots, returns
    finally: conn.close()


def _metric(values):
    values = [float(value) for value in values if value is not None]
    if not values: return {"n":0,"median_pct":None,"mean_pct":None,"positive_rate_pct":None}
    return {"n":len(values),"median_pct":round(float(median(values)),4),"mean_pct":round(sum(values)/len(values),4),"positive_rate_pct":round(sum(value>0 for value in values)/len(values)*100.0,2)}


def _segment_report(snapshot_ids, returns_by_snapshot):
    horizons = {}
    for horizon in HORIZONS:
        raw, alpha = [], []
        for snapshot_id in snapshot_ids:
            outcome = returns_by_snapshot.get((snapshot_id, horizon))
            if not outcome: continue
            raw.append(outcome.get("return_pct")); alpha.append(outcome.get("excess_return_pct"))
        raw_metric, alpha_metric = _metric(raw), _metric(alpha)
        horizons[str(horizon)] = {
            "raw_return": raw_metric,
            "market_adjusted_alpha": alpha_metric,
            "minimum_holdout_observations": MIN_HOLDOUT_OBSERVATIONS,
            "sample_sufficient": raw_metric["n"] >= MIN_HOLDOUT_OBSERVATIONS and alpha_metric["n"] >= MIN_HOLDOUT_OBSERVATIONS,
        }
    return horizons


def sandbox_report():
    gate = quality.quality_gate()
    model_id = identity_runtime._current_identity().get("signal_model_id")
    base = {
        "status":"LOCKED","research_only":True,"active_signal_model_id":model_id,
        "quality_gate_status":gate.get("status"),"quality_gate_ready":bool(gate.get("ready_for_counterfactual_research")),
        "automatic_threshold_changes":False,"automatic_candidate_ranking":False,"candidate_set_locked_in_source":True,
        "candidates":[dict(candidate) for candidate in CANDIDATES],
        "research_provenance":provenance.locked_provenance(model_id,CANDIDATES),
    }
    if not gate.get("ready_for_counterfactual_research"):
        base["meaning"] = "Counterfactual research is locked until the Shadow Dataset Quality Gate passes."
        base["quality_gate"] = gate
        return base

    snapshots, returns = _load_rows(model_id)
    dates = sorted({str(row.get("market_date") or "") for row in snapshots if row.get("market_date")})
    if len(dates) < 2:
        base["meaning"] = "Counterfactual research remains locked because chronological split dates are unavailable."
        base["research_provenance"] = provenance.locked_provenance(model_id,CANDIDATES,"chronological_split_unavailable")
        return base

    holdout_days = max(1,int(round(len(dates)*HOLDOUT_SHARE)))
    holdout_days = min(holdout_days,len(dates)-1)
    split_index = len(dates)-holdout_days
    development_dates, holdout_dates = set(dates[:split_index]), set(dates[split_index:])
    development_end, holdout_start = dates[split_index-1], dates[split_index]
    returns_by_snapshot = {(int(row["snapshot_id"]),int(row["horizon_days"])):row for row in returns}

    results = []
    for candidate in CANDIDATES:
        selected = [row for row in snapshots if _eligible(row,candidate)]
        development_ids = [int(row["id"]) for row in selected if row.get("market_date") in development_dates]
        holdout_ids = [int(row["id"]) for row in selected if row.get("market_date") in holdout_dates]
        results.append({
            "candidate":dict(candidate),"selected_snapshots":len(selected),"development_selected":len(development_ids),"holdout_selected":len(holdout_ids),
            "development":_segment_report(development_ids,returns_by_snapshot),"holdout":_segment_report(holdout_ids,returns_by_snapshot),
        })

    base.update({
        "status":"OPEN_RESEARCH_ONLY","method":"pre_registered_fixed_candidates_chronological_development_holdout",
        "market_days":len(dates),"development_market_days":len(development_dates),"holdout_market_days":len(holdout_dates),
        "development_end":development_end,"holdout_start":holdout_start,"holdout_share":HOLDOUT_SHARE,"results":results,
        "research_provenance":provenance.open_provenance(model_id,CANDIDATES,snapshots,returns,development_end,holdout_start,HOLDOUT_SHARE,len(dates)),
        "meaning":"Fixed candidate cohorts are shown in source order for research only; no winner is selected and no live threshold changes occur.",
    })
    return base


def install():
    if getattr(extra_api,"_opportunity_counterfactual_sandbox_runtime",False): return
    original_install = extra_api.install
    def patched_install(app):
        original_install(app)
        @app.get("/api/opportunity-shadow/sandbox")
        def opportunity_shadow_sandbox_route(): return sandbox_report()
    extra_api.install = patched_install
    extra_api._opportunity_counterfactual_sandbox_runtime = True


install()
