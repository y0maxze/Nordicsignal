"""Deterministic provenance helpers for Opportunity research outputs.

Fingerprints are derived only from canonical research inputs. No secrets are included,
no database state is mutated, and the helpers never promote or tune live thresholds.
"""
from __future__ import annotations

import hashlib
import json

VERSION = "research-provenance-v1"


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def fingerprint(value):
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def candidate_set_fingerprint(candidates):
    normalized = [dict(candidate) for candidate in (candidates or [])]
    return fingerprint({"version": VERSION, "candidates": normalized})


def dataset_fingerprint(snapshots, returns):
    snapshot_rows = [
        {
            "id": int(row.get("id")),
            "ticker": str(row.get("ticker") or ""),
            "market_date": str(row.get("market_date") or ""),
            "reversal_score": row.get("reversal_score"),
            "volume_ratio": row.get("volume_ratio"),
            "insider_label": str(row.get("insider_label") or ""),
        }
        for row in (snapshots or [])
    ]
    snapshot_rows.sort(key=lambda row: (row["market_date"], row["id"], row["ticker"]))
    return_rows = [
        {
            "snapshot_id": int(row.get("snapshot_id")),
            "horizon_days": int(row.get("horizon_days")),
            "return_pct": row.get("return_pct"),
            "excess_return_pct": row.get("excess_return_pct"),
        }
        for row in (returns or [])
    ]
    return_rows.sort(key=lambda row: (row["snapshot_id"], row["horizon_days"]))
    return fingerprint({"version": VERSION, "snapshots": snapshot_rows, "returns": return_rows})


def split_fingerprint(development_end, holdout_start, holdout_share, market_days):
    return fingerprint({
        "version": VERSION,
        "development_end": development_end,
        "holdout_start": holdout_start,
        "holdout_share": holdout_share,
        "market_days": int(market_days or 0),
    })


def report_fingerprint(signal_model_id, dataset_fp, candidate_fp, split_fp):
    return fingerprint({
        "version": VERSION,
        "signal_model_id": str(signal_model_id or ""),
        "dataset_fingerprint": dataset_fp,
        "candidate_set_fingerprint": candidate_fp,
        "split_fingerprint": split_fp,
    })


def locked_provenance(signal_model_id, candidates, reason="quality_gate_locked"):
    return {
        "version": VERSION,
        "signal_model_id": signal_model_id,
        "candidate_set_fingerprint": candidate_set_fingerprint(candidates),
        "dataset_fingerprint": None,
        "split_fingerprint": None,
        "report_fingerprint": None,
        "snapshot_count": None,
        "return_count": None,
        "reproducible": False,
        "reason": reason,
    }


def open_provenance(signal_model_id, candidates, snapshots, returns, development_end, holdout_start, holdout_share, market_days):
    candidate_fp = candidate_set_fingerprint(candidates)
    dataset_fp = dataset_fingerprint(snapshots, returns)
    split_fp = split_fingerprint(development_end, holdout_start, holdout_share, market_days)
    return {
        "version": VERSION,
        "signal_model_id": signal_model_id,
        "candidate_set_fingerprint": candidate_fp,
        "dataset_fingerprint": dataset_fp,
        "split_fingerprint": split_fp,
        "report_fingerprint": report_fingerprint(signal_model_id, dataset_fp, candidate_fp, split_fp),
        "snapshot_count": len(snapshots or []),
        "return_count": len(returns or []),
        "development_end": development_end,
        "holdout_start": holdout_start,
        "reproducible": True,
        "reason": None,
    }
