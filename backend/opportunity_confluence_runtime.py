"""Early Opportunity / Confluence Engine for NordicSignal.

Combines independent evidence from Trend/Reversal Engine v2, bullish volume and
Insider Signal v2. This module is informational only and does not modify the
aggregate 0-100 stock score.
"""
from __future__ import annotations

from datetime import datetime, timezone

import extra_api
import insider_runtime
from insider_signal_v2_runtime import analyze as analyze_insider
from providers import YahooProvider, NordicRegulatoryProvider
from trend_reversal_runtime import calculate_reversal

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

    if reversal_score >= 75:
        score += 45
        reasons.append("Reversal score >= 75")
    elif reversal_score >= 70:
        score += 32
        reasons.append("Reversal score >= 70")
    elif reversal_score >= 55:
        score += 15
        reasons.append("Reversal candidate only")

    volume_state = "NONE"
    if volume_ratio is not None and volume_ratio >= 2.0:
        score += 25
        volume_state = "STRONG"
        reasons.append("Bullish volume >= 2.0x normal")
    elif volume_ratio is not None and volume_ratio >= 1.5:
        score += 15
        volume_state = "CONFIRMED"
        reasons.append("Bullish volume >= 1.5x normal")

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

    if independent_buyers >= 3:
        score += 5
        reasons.append("3+ independent insider buyers")
    if buy_value >= 1_000_000:
        score += 5
        reasons.append("Insider purchases >= NOK 1m")

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


def _company_name(ticker):
    entry = insider_runtime.ISSUERS.get(ticker)
    return entry[0] if entry else ticker


def live_opportunity(ticker):
    symbol = str(ticker or "").strip().upper().replace(".OL", "")
    if not symbol or len(symbol) > 16 or not all(ch.isalnum() or ch in ".-" for ch in symbol):
        return {"ticker": symbol, "status": "invalid_ticker"}

    price_provider = YahooProvider()
    regulatory = NordicRegulatoryProvider()
    history = price_provider.historical(symbol, "6m")
    reversal = calculate_reversal(history)
    try:
        insider_feed = regulatory.insider(symbol, _company_name(symbol)) or {}
        insider_enriched = analyze_insider(insider_feed)
        insider_signal = insider_enriched.get("insider_signal_v2") or {}
    except Exception as exc:
        insider_signal = {"label": "NONE", "points": 0, "error": str(exc)}

    opportunity = calculate_opportunity(reversal, insider_signal)
    return {
        "ticker": symbol,
        "status": "ok",
        "opportunity": opportunity,
        "reversal": reversal,
        "insider_signal_v2": insider_signal,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def _replace_route(app, path, handler):
    for route in getattr(app, "routes", []):
        if getattr(route, "path", None) == path and "GET" in (getattr(route, "methods", None) or set()):
            route.endpoint = handler
            dependant = getattr(route, "dependant", None)
            if dependant is not None:
                dependant.call = handler
            return True
    return False


def install():
    if getattr(extra_api, "_opportunity_confluence_runtime", False):
        return
    original_install = extra_api.install

    def patched_install(app):
        original_install(app)

        def opportunity_route(ticker: str):
            return live_opportunity(ticker)

        if not _replace_route(app, "/api/opportunity/{ticker}", opportunity_route):
            app.get("/api/opportunity/{ticker}")(opportunity_route)

    extra_api.install = patched_install
    extra_api._opportunity_confluence_runtime = True


install()
