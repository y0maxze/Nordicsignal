"""Chronological walk-forward stability checks for Opportunity Learning.

This is deliberately not a threshold optimizer. It asks whether a model that was
statistically supported on earlier observations remained directionally useful on
later, untouched blocks. Folds are chronological and expanding-window; there is no
random shuffle and no future observation can enter the training side of its own fold.
"""
from __future__ import annotations

from math import ceil
from statistics import median

import opportunity_statistical_confidence_runtime as confidence

INITIAL_TRAIN_EVENTS = 20
HOLDOUT_EVENTS = 10
MIN_ELIGIBLE_FOLDS = 2
MIN_REQUIRED_HORIZONS = 2
MIN_HOLDOUT_POSITIVE_RATE_PCT = 60.0
MIN_FOLD_PASS_RATE = 2.0 / 3.0


def _number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _event_order_key(item):
    observed = str((item or {}).get("observed_at") or "")
    event_id = (item or {}).get("event_id")
    try:
        numeric = int(event_id)
    except (TypeError, ValueError):
        numeric = 10**18
    return (observed, numeric, str((item or {}).get("_stable_key") or event_id or ""))


def _ordered_horizon_rows(rows, horizon):
    selected = {}
    synthetic = 0
    for row in rows or []:
        try:
            if int((row or {}).get("horizon_days") or 0) != int(horizon):
                continue
        except (TypeError, ValueError):
            continue
        raw = _number((row or {}).get("return_pct"))
        alpha = _number((row or {}).get("excess_return_pct"))
        if raw is None or alpha is None:
            continue
        event_id = (row or {}).get("event_id")
        if event_id is None:
            synthetic += 1
            key = f"synthetic-{synthetic}"
        else:
            key = str(event_id)
        item = dict(row)
        item["return_pct"] = raw
        item["excess_return_pct"] = alpha
        item["_stable_key"] = key
        selected[key] = item
    return sorted(selected.values(), key=_event_order_key)


def _holdout_direction(values):
    sample = [float(value) for value in values if value is not None]
    n = len(sample)
    if not n:
        return {"n": 0, "median": None, "positive_rate_pct": None, "direction_pass": False}
    med = float(median(sample))
    positive_rate = sum(value > 0.0 for value in sample) / n * 100.0
    return {"n": n, "median": round(med, 4), "positive_rate_pct": round(positive_rate, 2), "direction_pass": bool(med > 0.0 and positive_rate >= MIN_HOLDOUT_POSITIVE_RATE_PCT)}


def _folds(rows, minimum_train=INITIAL_TRAIN_EVENTS, holdout_size=HOLDOUT_EVENTS):
    minimum_train = max(1, int(minimum_train))
    holdout_size = max(1, int(holdout_size))
    result = []
    train_end = minimum_train
    fold_number = 1
    while train_end + holdout_size <= len(rows):
        result.append((fold_number, rows[:train_end], rows[train_end:train_end + holdout_size]))
        train_end += holdout_size
        fold_number += 1
    return result


def _fold_report(number, train, holdout):
    train_raw = confidence._series_confidence([row["return_pct"] for row in train], INITIAL_TRAIN_EVENTS)
    train_alpha = confidence._series_confidence([row["excess_return_pct"] for row in train], INITIAL_TRAIN_EVENTS)
    training_ready = bool(train_raw["direction_supported"] and train_alpha["direction_supported"])
    holdout_raw = _holdout_direction([row["return_pct"] for row in holdout])
    holdout_alpha = _holdout_direction([row["excess_return_pct"] for row in holdout])
    holdout_pass = bool(len(holdout) == HOLDOUT_EVENTS and holdout_raw["direction_pass"] and holdout_alpha["direction_pass"])
    eligible = training_ready and len(holdout) == HOLDOUT_EVENTS
    chronology_ok = bool(train and holdout and _event_order_key(train[-1]) < _event_order_key(holdout[0]))
    status = "TRAIN_NOT_READY" if not eligible else ("PASS" if holdout_pass else "FAIL")
    return {
        "fold": int(number), "status": status, "eligible": eligible,
        "training": {"n": len(train), "first_event_id": train[0].get("event_id") if train else None, "last_event_id": train[-1].get("event_id") if train else None, "last_observed_at": train[-1].get("observed_at") if train else None, "raw_return": train_raw, "market_adjusted_alpha": train_alpha},
        "holdout": {"n": len(holdout), "first_event_id": holdout[0].get("event_id") if holdout else None, "last_event_id": holdout[-1].get("event_id") if holdout else None, "first_observed_at": holdout[0].get("observed_at") if holdout else None, "last_observed_at": holdout[-1].get("observed_at") if holdout else None, "raw_return": holdout_raw, "market_adjusted_alpha": holdout_alpha, "pass": holdout_pass},
        "leakage_guard": {"chronological": True, "training_ends_before_holdout_starts": chronology_ok},
    }


def _horizon_report(rows, horizon):
    ordered = _ordered_horizon_rows(rows, horizon)
    fold_reports = [_fold_report(number, train, holdout) for number, train, holdout in _folds(ordered)]
    eligible = [fold for fold in fold_reports if fold["eligible"] and fold["leakage_guard"]["training_ends_before_holdout_starts"]]
    passing = [fold for fold in eligible if fold["holdout"]["pass"]]
    eligible_count = len(eligible)
    pass_rate = (len(passing) / eligible_count * 100.0) if eligible_count else None
    required_passes = ceil(eligible_count * MIN_FOLD_PASS_RATE) if eligible_count else MIN_ELIGIBLE_FOLDS
    latest_pass = bool(eligible and eligible[-1]["holdout"]["pass"])
    ready = bool(eligible_count >= MIN_ELIGIBLE_FOLDS and len(passing) >= required_passes and latest_pass)
    status = "PASS" if ready else ("REVIEW" if eligible_count >= MIN_ELIGIBLE_FOLDS else "COLLECTING_DATA")
    return {
        "status": status, "ready": ready, "observations": len(ordered), "eligible_folds": eligible_count,
        "passing_folds": len(passing), "holdout_pass_rate_pct": round(pass_rate, 2) if pass_rate is not None else None,
        "required_passing_folds": required_passes, "latest_eligible_holdout_pass": latest_pass if eligible else None,
        "minimum_eligible_folds": MIN_ELIGIBLE_FOLDS,
        "observations_needed_for_two_scheduled_folds": max(0, INITIAL_TRAIN_EVENTS + HOLDOUT_EVENTS * MIN_ELIGIBLE_FOLDS - len(ordered)),
        "folds": fold_reports,
    }


def walkforward_gate(rows, required_horizons):
    horizons = {str(int(horizon)): _horizon_report(rows, int(horizon)) for horizon in required_horizons}
    passing_horizons = [int(horizon) for horizon in required_horizons if horizons[str(int(horizon))]["ready"]]
    ready = len(passing_horizons) >= MIN_REQUIRED_HORIZONS
    enough_any = any(item["eligible_folds"] >= MIN_ELIGIBLE_FOLDS for item in horizons.values())
    return {
        "status": "PASS" if ready else ("REVIEW" if enough_any else "COLLECTING_DATA"), "ready": ready,
        "method": "chronological_expanding_window_no_shuffle", "initial_training_events": INITIAL_TRAIN_EVENTS,
        "holdout_events_per_fold": HOLDOUT_EVENTS, "minimum_eligible_folds_per_horizon": MIN_ELIGIBLE_FOLDS,
        "minimum_passing_horizons": MIN_REQUIRED_HORIZONS, "minimum_holdout_positive_rate_pct": MIN_HOLDOUT_POSITIVE_RATE_PCT,
        "minimum_fold_pass_rate_pct": round(MIN_FOLD_PASS_RATE * 100.0, 2), "latest_holdout_must_pass": True,
        "passing_horizons": passing_horizons, "horizons": horizons,
        "meaning": "The active model remains directionally positive across enough chronological out-of-sample blocks." if ready else "The active model does not yet have enough successful chronological holdout evidence for threshold review.",
        "automatic_threshold_changes": False,
    }
