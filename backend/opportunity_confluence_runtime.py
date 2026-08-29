"""Early Opportunity / Confluence Engine for NordicSignal.

Combines independent evidence from Trend/Reversal Engine v2, bullish volume and
Insider Signal v2. This module is informational only and does not modify the
aggregate 0-100 stock score.
"""
from __future__ import annotations

VERSION = "2026-08-30-v1"


def _num(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def calculate_opportunity(reversal=None, insider=None):
    reversal = reversal or {}
    insider = insider or {}
    if "insider_signal_v2" in insider:
        insider = insider.get("insider_signal_v2") or {}

    reversal_score = reversal.get("score")
    if reversal_score is None:
        return {
            "score": None,
            "label": "INSUFFICIENT_DATA",
            "confidence": "low",
            "reasons": ["Trend/reversal history is insufficient"],
            "components": {},
            "score_effect": 0,
            "policy": "informational_only_pending_forward_validation",
            "version": VERSION,
        }

    reversal_score = _num(reversal_score)
    metrics = reversal.get("metrics") or {}
    volume_ratio = metrics.get("volume_ratio")
    volume_ratio = _num(volume_ratio) if volume_ratio is not None else None
    insider_label = str(insider.get("label") or "NONE").upper()
    insider_points = _num(insider.get("points"))
    independent_buyers = int(_num(insider.get("independent_buyers")))
    buy_value = _num(insider.get("buy_value_nok"))

    score = 0.0
    reasons = []

    # Reversal evidence: deliberately requires stronger scores before it dominates.
    if reversal_score >= 75:
        score += 45
        reasons.append("Reversal score >= 75")
    elif reversal_score >= 70:
        score += 32
        reasons.append("Reversal score >= 70")
    elif reversal_score >= 55:
        score += 15
        reasons.append("Reversal candidate only")

    # Historical v2 backtest showed materially stronger outcomes when reversal
    # signals were accompanied by 1.5x-2.0x bullish volume.
    volume_state = "NONE"
    if volume_ratio is not None and volume_ratio >= 2.0:
        score += 25
        volume_state = "STRONG"
        reasons.append("Bullish volume >= 2.0x normal")
    elif volume_ratio is not None and volume_ratio >= 1.5:
        score += 15
        volume_state = "CONFIRMED"
        reasons.append("Bullish volume >= 1.5x normal")

    # Insider evidence remains capped until the historical insider sample grows.
    insider_weight = 0
    if insider_label == "STRONG":
        insider_weight = 20
        reasons.append("Strong insider cluster")
    elif insider_label == "POSITIVE":
        insider_weight = 12
        reasons.append("Positive insider cluster")
    elif insider_label == "MIXED":
        insider_weight = 4
    score += insider_weight

    # Small corroboration bonuses. They cannot create a signal on their own.
    if independent_buyers >= 3:
        score += 5
        reasons.append("3+ independent insider buyers")
    if buy_value >= 1_000_000:
        score += 5
        reasons.append("Insider purchases >= NOK 1m")

    # Require actual confluence for the strongest labels.
    strong_reversal = reversal_score >= 75
    volume_confirmed = volume_ratio is not None and volume_ratio >= 1.5
    insider_positive = insider_label in {"STRONG", "POSITIVE"}
    evidence_count = sum((strong_reversal, volume_confirmed, insider_positive))

    score = max(0.0, min(100.0, score))
    if evidence_count == 3 and score >= 80:
        label = "EARLY_OPPORTUNITY_HIGH"
        confidence = "high"
    elif strong_reversal and volume_confirmed and score >= 60:
        label = "EARLY_OPPORTUNITY"
        confidence = "medium_high" if insider_positive else "medium"
    elif reversal_score >= 70 and (volume_confirmed or insider_positive):
        label = "WATCH_CONFLUENCE"
        confidence = "medium"
    elif reversal_score >= 55:
        label = "REVERSAL_CANDIDATE"
        confidence = "low_medium"
    else:
        label = "NO_OPPORTUNITY"
        confidence = "low"

    return {
        "score": round(score, 1),
        "label": label,
        "confidence": confidence,
        "reasons": reasons,
        "components": {
            "reversal_score": reversal_score,
            "reversal_regime": reversal.get("regime"),
            "volume_ratio": volume_ratio,
            "volume_state": volume_state,
            "insider_label": insider_label,
            "insider_points": insider_points,
            "independent_buyers": independent_buyers,
            "buy_value_nok": buy_value,
            "evidence_count": evidence_count,
        },
        "score_effect": 0,
        "policy": "informational_only_pending_forward_validation",
        "version": VERSION,
    }


def install():
    return None


install()
